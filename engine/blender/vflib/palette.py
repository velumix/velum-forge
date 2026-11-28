"""Palette atlas texturing (the classic game-ready "gradient/palette" technique).

Every material used by an asset becomes one flat cell in a small atlas (Color / Roughness /
Metalness PNGs). Each face's UVs collapse onto its material's cell centre, so an entire asset
renders with ONE material and three tiny textures, and vertices only split at material borders.
Roblox: the three PNGs map 1:1 onto SurfaceAppearance ColorMap / RoughnessMap / MetalnessMap.
"""

import os

import bpy
import numpy as np

from . import core, mats

MAPS = (("Color", "sRGB"), ("Roughness", "Non-Color"), ("Metalness", "Non-Color"))


def collect_materials(objs):
    seen = []
    for ob in objs:
        if ob.type != "MESH":
            continue
        for m in ob.data.materials:
            if m is not None and m not in seen:
                seen.append(m)
    return seen


def _linear_to_srgb(c):
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def game_values(m):
    """(srgb, roughness, metallic) for a material, from sc_ props or its Principled BSDF."""
    if "sc_srgb" in m:
        return tuple(m["sc_srgb"]), float(m.get("sc_roughness", 0.5)), float(m.get("sc_metallic", 0.0))
    try:
        b = mats.bsdf(m)
        base = mats.sock(b, "Base Color").default_value
        srgb = tuple(_linear_to_srgb(c) for c in base[:3])
        return srgb, mats.sock(b, "Roughness").default_value, mats.sock(b, "Metallic").default_value
    except (StopIteration, AttributeError):
        return tuple(m.diffuse_color[:3]), m.roughness, m.metallic


def _grid_for(n):
    g = 4
    while g * g < n:
        g *= 2
    return g


def _write_image(name, arr, colorspace, path):
    size = arr.shape[0]
    img = bpy.data.images.get(name)
    if img is not None and tuple(img.size) != (size, size):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(name, size, size, alpha=False)
    try:
        img.colorspace_settings.name = colorspace
    except TypeError:
        pass
    img.pixels.foreach_set(arr.astype(np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


def build_atlas(materials, name, out_dir, size=256):
    """Bake the atlas PNGs into out_dir. Returns (rects, images) where rects[mat.name] = (u0, v0, u1, v1)."""
    os.makedirs(out_dir, exist_ok=True)
    g = _grid_for(len(materials))
    cell = size // g
    if cell < 8:
        raise ValueError(f"palette too small: {len(materials)} materials in {size}px")
    color = np.ones((size, size, 4), np.float32)
    rough = np.ones((size, size, 4), np.float32)
    metal = np.ones((size, size, 4), np.float32)
    metal[..., :3] = 0.0
    rects = {}
    for i, m in enumerate(materials):
        cx, cy = i % g, i // g
        x0, y0 = cx * cell, cy * cell
        srgb, r, mt = game_values(m)
        color[y0:y0 + cell, x0:x0 + cell, :3] = srgb
        rough[y0:y0 + cell, x0:x0 + cell, :3] = r
        metal[y0:y0 + cell, x0:x0 + cell, :3] = mt
        rects[m.name] = (x0 / size, y0 / size, (x0 + cell) / size, (y0 + cell) / size)
    images = {}
    for (suffix, cs), arr in zip(MAPS, (color, rough, metal)):
        img_name = f"{name}_{suffix}"
        images[suffix] = _write_image(img_name, arr, cs, os.path.join(out_dir, img_name + ".png"))
    core.log(f"palette {name}: {len(materials)} materials, {g}x{g} grid, {size}px -> {out_dir}")
    return rects, images


def apply_uvs(ob, rects, uv_name="UVMap"):
    """Collapse each face's UVs onto the centre of its material's palette cell."""
    me = ob.data
    for layer in list(me.uv_layers):
        me.uv_layers.remove(layer)
    uv = me.uv_layers.new(name=uv_name)
    me.uv_layers.active = uv
    centers = []
    for m in me.materials:
        r = rects.get(m.name) if m else None
        if r is None:
            r = next(iter(rects.values()))
        centers.append(((r[0] + r[2]) / 2, (r[1] + r[3]) / 2))
    if not centers:
        centers = [(0.5, 0.5)]
    mi = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    loop_total = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", loop_total)
    loop_mat = np.repeat(np.clip(mi, 0, len(centers) - 1), loop_total)
    c = np.array(centers, np.float32)
    uv.data.foreach_set("uv", c[loop_mat].ravel())
    me.update()


def palette_material(name, images):
    """Blender material that renders exactly what the game will see (atlas textures)."""
    mat, b = mats._new_node_material(name)
    nt = mat.node_tree
    y = 300
    for suffix, target in (("Color", "Base Color"), ("Roughness", "Roughness"), ("Metalness", "Metallic")):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = images[suffix]
        tex.interpolation = "Closest"
        tex.location = (-500, y)
        y -= 300
        nt.links.new(mats.sock(tex, "Color", output=True), mats.sock(b, target))
    mat["sc_role"] = "palette"
    return mat


def assign_single(ob, mat):
    me = ob.data
    me.materials.clear()
    me.materials.append(mat)
    me.polygons.foreach_set("material_index", [0] * len(me.polygons))
    me.update()

