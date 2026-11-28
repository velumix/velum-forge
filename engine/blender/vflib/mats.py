"""PBR material library.

Every material made here stores its flat game values as custom properties
(`sc_srgb`, `sc_roughness`, `sc_metallic`, `sc_role`, `sc_alpha`) so `palette.py` can bake a
game-ready texture atlas without parsing node trees. Procedural micro-detail (bump noise) is
render-only and never leaks into exports.

Roles: "solid" (palette textured), "paint" (recolorable plain MeshPart in Roblox),
"glass" (transparent Glass), "neon" (emissive Neon).
"""

import bpy


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def parse_color(color):
    """'#RRGGBB' or (r, g, b) in 0..1 sRGB -> sRGB tuple."""
    if isinstance(color, str):
        h = color.lstrip("#")
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(float(c) for c in color[:3])


def linear(color):
    return tuple(srgb_to_linear(c) for c in parse_color(color))


def bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def output_node(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL")


def sock(node, *keys, output=False):
    socks = node.outputs if output else node.inputs
    for k in keys:
        for s in socks:
            if s.identifier == k or s.name == k:
                return s
    return None


def set_in(node, keys, value):
    if isinstance(keys, str):
        keys = (keys,)
    s = sock(node, *keys)
    if s is None or not hasattr(s, "default_value"):
        return False
    try:
        cur = s.default_value
        if hasattr(cur, "__len__") and not isinstance(value, (int, float)):
            n = len(cur)
            value = tuple(value)[:n] + (1.0,) * max(0, n - len(value))
        s.default_value = value
        return True
    except (TypeError, ValueError):
        return False


def _new_node_material(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        mat.use_nodes = True  # deprecated (always on) in Blender 5.x
    except (AttributeError, TypeError):
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = (0, 0)
    nt.links.new(sock(b, "BSDF", output=True), sock(out, "Surface"))
    return mat, b


def _set_blend(mat, blended):
    for attr, val in (("surface_render_method", "BLENDED" if blended else "DITHERED"),
                      ("blend_method", "BLEND" if blended else "OPAQUE")):
        try:
            setattr(mat, attr, val)
        except (AttributeError, TypeError):
            pass


def pbr(name, color="#FFFFFF", roughness=0.5, metallic=0.0, *, coat=0.0, coat_roughness=0.05,
        transmission=0.0, ior=1.45, alpha=1.0, emission=None, emission_strength=0.0,
        specular=0.5, role="solid", roblox_material=None):
    """Create (or rebuild in place) a Principled material and record its game values."""
    mat, b = _new_node_material(name)
    srgb = parse_color(color)
    lin = tuple(srgb_to_linear(c) for c in srgb)
    set_in(b, "Base Color", lin + (1.0,))
    set_in(b, "Roughness", roughness)
    set_in(b, "Metallic", metallic)
    set_in(b, ("Specular IOR Level", "Specular"), specular)
    set_in(b, ("Coat Weight", "Clearcoat"), coat)
    set_in(b, ("Coat Roughness", "Clearcoat Roughness"), coat_roughness)
    set_in(b, ("Transmission Weight", "Transmission"), transmission)
    set_in(b, "IOR", ior)
    set_in(b, "Alpha", alpha)
    if emission is not None:
        set_in(b, ("Emission Color", "Emission"), linear(emission) + (1.0,))
        set_in(b, "Emission Strength", emission_strength)
    _set_blend(mat, alpha < 1.0 or transmission > 0.0)
    mat.diffuse_color = lin + (alpha,)
    mat.roughness = roughness
    mat.metallic = metallic
    mat["sc_srgb"] = list(srgb)
    mat["sc_roughness"] = float(roughness)
    mat["sc_metallic"] = float(metallic)
    mat["sc_alpha"] = float(alpha)
    mat["sc_role"] = role
    if roblox_material:
        mat["sc_roblox_material"] = roblox_material
    return mat


def add_bump_noise(mat, scale=150.0, strength=0.25, distance=0.002, kind="noise", detail=4.0,
                   roughness_variation=0.0):
    """Render-only micro detail: procedural bump (noise / voronoi) in object space."""
    nt = mat.node_tree
    b = bsdf(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-900, -300)
    if kind == "voronoi":
        tex = nt.nodes.new("ShaderNodeTexVoronoi")
        height = sock(tex, "Distance", output=True)
    else:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        set_in(tex, "Detail", detail)
        height = sock(tex, "Fac", output=True)
    tex.location = (-650, -300)
    set_in(tex, "Scale", scale)
    nt.links.new(sock(tc, "Object", output=True), sock(tex, "Vector"))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-300, -300)
    set_in(bump, "Strength", strength)
    set_in(bump, "Distance", distance)
    nt.links.new(height, sock(bump, "Height"))
    nt.links.new(sock(bump, "Normal", output=True), sock(b, "Normal"))
    if roughness_variation > 0:
        base_r = mat.get("sc_roughness", 0.5)
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.location = (-300, -50)
        set_in(mr, "To Min", max(0.0, base_r - roughness_variation))
        set_in(mr, "To Max", min(1.0, base_r + roughness_variation))
        nt.links.new(height, sock(mr, "Value"))
        nt.links.new(sock(mr, "Result", output=True), sock(b, "Roughness"))
    return mat


# Flat game values. `detail` entries only affect renders.
PRESETS = {
    "gelcoat_white": dict(color="#F3F3EF", roughness=0.16, coat=0.7, roblox_material="SmoothPlastic"),
    "gelcoat_offwhite": dict(color="#E4E1D8", roughness=0.3, coat=0.3),
    "hull_bottom": dict(color="#EDEDE8", roughness=0.28, coat=0.4),
    "antifoul": dict(color="#1C2633", roughness=0.75),
    "paint_primary": dict(color="#00A6B4", roughness=0.14, coat=1.0, role="paint", roblox_material="SmoothPlastic"),
    "paint_accent": dict(color="#E8197D", roughness=0.14, coat=1.0, role="paint", roblox_material="SmoothPlastic"),
    "liner": dict(color="#ECEAE3", roughness=0.35, coat=0.2),
    "nonskid": dict(color="#D9D7CF", roughness=0.8,
                    detail=dict(kind="voronoi", scale=220.0, strength=0.35, distance=0.0015)),
    "vinyl_white": dict(color="#F2EFE7", roughness=0.42,
                        detail=dict(scale=420.0, strength=0.12, distance=0.0008, roughness_variation=0.06)),
    "vinyl_accent": dict(color="#00A6B4", roughness=0.42,
                         detail=dict(scale=420.0, strength=0.12, distance=0.0008)),
    "vinyl_dark": dict(color="#2A2D33", roughness=0.5,
                       detail=dict(scale=420.0, strength=0.12, distance=0.0008)),
    "piping": dict(color="#1E2024", roughness=0.45),
    "chrome": dict(color="#E9EBEE", roughness=0.07, metallic=1.0, roblox_material="Metal"),
    "stainless": dict(color="#C6CACE", roughness=0.24, metallic=1.0, roblox_material="Metal"),
    "black_plastic": dict(color="#1B1C1F", roughness=0.42),
    "dash_black": dict(color="#141518", roughness=0.75),
    "rubber": dict(color="#121212", roughness=0.85),
    "rubrail": dict(color="#2C2E33", roughness=0.4),
    "glass_tint": dict(color="#33474D", roughness=0.03, transmission=0.85, alpha=0.4, role="glass",
                       roblox_material="Glass"),
    "screen": dict(color="#06121A", roughness=0.08, emission="#103A55", emission_strength=1.5),
    "gauge_face": dict(color="#0E1013", roughness=0.25),
    "gauge_ring": dict(color="#D8DADC", roughness=0.12, metallic=1.0),
    "nav_red": dict(color="#FF2020", roughness=0.1, emission="#FF2020", emission_strength=6.0, role="neon",
                    roblox_material="Neon"),
    "nav_green": dict(color="#20FF50", roughness=0.1, emission="#20FF50", emission_strength=6.0, role="neon",
                      roblox_material="Neon"),
    "nav_white": dict(color="#FFFFFF", roughness=0.1, emission="#FFFFFF", emission_strength=6.0, role="neon",
                      roblox_material="Neon"),
    "teak": dict(color="#9A6A3D", roughness=0.62,
                 detail=dict(scale=60.0, strength=0.15, distance=0.001)),
    "drive_grey": dict(color="#2A2C30", roughness=0.32, metallic=0.4),
    "prop_steel": dict(color="#B9BCC0", roughness=0.2, metallic=1.0),
    "carbon": dict(color="#1F2124", roughness=0.3),
    "decal_dark": dict(color="#1A1D22", roughness=0.3),
}


def preset(key, name=None, **overrides):
    """Material from `PRESETS[key]`; any pbr() kwarg can be overridden (e.g. color=)."""
    kw = dict(PRESETS[key])
    detail = kw.pop("detail", None)
    kw.update(overrides)
    mat = pbr(name or ("SC_" + key), **kw)
    if detail:
        add_bump_noise(mat, **detail)
    return mat


def library(keys, prefix="SC_", **per_key_overrides):
    """Build several presets at once -> dict key -> material.

    library(["chrome", "paint_primary"], paint_primary=dict(color="#FF0000"))
    """
    out = {}
    for k in keys:
        out[k] = preset(k, prefix + k, **per_key_overrides.get(k, {}))
    return out


def assign(ob, mats):
    """Append material(s) to the mesh's slots (mesh-level so they survive joins/exports)."""
    if not isinstance(mats, (list, tuple)):
        mats = [mats]
    for m in mats:
        if m is not None:
            ob.data.materials.append(m)
    return ob

