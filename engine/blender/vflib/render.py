"""Look-dev & verification renders that never disturb the user's scene settings.

    from sclib import render
    render.render_views(objs, out_dir, views=("hero", "stern", "side", "top"), backdrop="sea")

Studio objects live in the `SC_Studio` collection (hidden in the viewport, visible to renders).
"""

import math
import os

import bpy
from mathutils import Vector

from . import core, mats

# Directions are from the subject towards the camera (Blender axes: +Y = front, +X = right).
VIEWS = {
    "hero": dict(dir=(0.95, 1.05, 0.48), lens=50, margin=1.02),
    "front": dict(dir=(0.0, 1.0, 0.18), lens=60, margin=1.05),
    "stern": dict(dir=(0.85, -1.0, 0.5), lens=50, margin=1.02),
    "rear_left": dict(dir=(-0.9, -1.0, 0.45), lens=50, margin=1.02),
    "side": dict(dir=(1.0, 0.0, 0.06), lens=70, margin=1.0),
    "top": dict(dir=(0.0, -0.001, 1.0), lens=50, margin=1.0),
    "cockpit": dict(dir=(0.35, -0.55, 0.85), lens=35, margin=0.62),
    "low": dict(dir=(1.0, 0.7, -0.12), lens=40, margin=1.0),
}
EEVEE_IDS = ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT")


def set_engine(scene, engine):
    candidates = EEVEE_IDS if engine.upper().startswith("EEVEE") else (engine,)
    for eid in candidates:
        try:
            scene.render.engine = eid
            return eid
        except TypeError:
            continue
    return scene.render.engine


def _area(col, name, loc, target, size, power, color=(1, 1, 1)):
    ld = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
    ld.type = "AREA"
    ld.size = size
    ld.energy = power
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    col.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def _world(name, top, horizon, strength):
    w = bpy.data.worlds.get(name) or bpy.data.worlds.new(name)
    try:
        w.use_nodes = True
    except (AttributeError, TypeError):
        pass
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    grad = nt.nodes.new("ShaderNodeValToRGB")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(mats.sock(tc, "Generated", output=True), mats.sock(sep, "Vector"))
    nt.links.new(mats.sock(sep, "Z", output=True), mats.sock(grad, "Fac"))
    ramp = grad.color_ramp
    ramp.elements[0].position = 0.5
    ramp.elements[0].color = mats.linear(horizon) + (1,)
    ramp.elements[1].position = 0.85
    ramp.elements[1].color = mats.linear(top) + (1,)
    nt.links.new(mats.sock(grad, "Color", output=True), mats.sock(bg, "Color"))
    mats.set_in(bg, "Strength", strength)
    nt.links.new(mats.sock(bg, "Background", output=True), mats.sock(out, "Surface"))
    return w


def setup_studio(objs, backdrop="product"):
    """Build lights + backdrop around `objs`. backdrop: 'product' (light cyclorama) or 'sea'."""
    col = core.fresh_collection("SC_Studio")
    lo, hi = core.world_bbox(objs)
    c = (lo + hi) / 2
    r = max((hi - lo).length / 2, 0.5)
    tgt = (c.x, c.y, c.z)
    _area(col, "SC_Key", (c.x + r * 1.6, c.y + r * 1.2, c.z + r * 2.6), tgt, r * 1.6, 120 * r * r)
    _area(col, "SC_Fill", (c.x - r * 2.2, c.y + r * 0.6, c.z + r * 1.0), tgt, r * 2.0, 35 * r * r,
          (0.85, 0.92, 1.0))
    _area(col, "SC_Rim", (c.x - r * 0.6, c.y - r * 2.4, c.z + r * 1.8), tgt, r * 1.4, 90 * r * r)
    if backdrop == "sea":
        world = _world("SC_StudioSky", "#5D8FC9", "#D9E6F2", 1.0)
        water = mats.pbr("SC_StudioWater", "#0F3C55", roughness=0.06, specular=0.6)
        mats.add_bump_noise(water, scale=1.6, strength=0.35, distance=0.06, detail=6.0)
        from . import geo
        plane = geo.box("SC_Water", (r * 60, r * 60, 0.01), col, water, location=(c.x, c.y, -0.005),
                        weighted=False)
        plane.visible_shadow = False
    else:
        world = _world("SC_StudioWorld", "#FFFFFF", "#E8EAED", 0.8)
        floor = mats.pbr("SC_StudioFloor", "#F4F4F4", roughness=0.6)
        from . import geo
        geo.box("SC_Floor", (r * 40, r * 40, 0.01), col, floor, location=(c.x, c.y, lo.z - 0.006),
                weighted=False)
    bpy.context.scene.world = world
    col.hide_viewport = True
    return col


def frame_camera(cam, objs, direction, lens=50, margin=1.05, aspect=16 / 9):
    lo, hi = core.world_bbox(objs)
    c = (lo + hi) / 2
    r = (hi - lo).length / 2
    cam.data.lens = lens
    fov_h = 2 * math.atan(cam.data.sensor_width / 2 / lens)
    fov_v = 2 * math.atan(math.tan(fov_h / 2) / aspect)
    dist = r / math.sin(min(fov_h, fov_v) / 2) * margin
    d = Vector(direction).normalized()
    cam.location = c + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = max(0.01, dist / 1000)
    cam.data.clip_end = dist * 50


def render_views(objs, out_dir, views=("hero",), res=(1600, 900), engine="EEVEE", samples=64,
                 backdrop="product", prefix="", studio=True):
    """Render named VIEWS of `objs` to out_dir/<prefix><view>.png and restore scene settings."""
    sc = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    saved = dict(camera=sc.camera, engine=sc.render.engine, rx=sc.render.resolution_x,
                 ry=sc.render.resolution_y, pct=sc.render.resolution_percentage, path=sc.render.filepath,
                 world=sc.world, fmt=sc.render.image_settings.file_format)
    if studio:
        setup_studio(objs, backdrop)
    cam_data = bpy.data.cameras.get("SC_StudioCam") or bpy.data.cameras.new("SC_StudioCam")
    cam = bpy.data.objects.get("SC_StudioCam") or bpy.data.objects.new("SC_StudioCam", cam_data)
    studio_col = bpy.data.collections.get("SC_Studio") or core.fresh_collection("SC_Studio")
    if cam.name not in studio_col.objects:
        studio_col.objects.link(cam)
    sc.camera = cam
    from . import bake

    used = set_engine(sc, engine)
    if used == "CYCLES":
        bake.enable_cycles_gpu(sc, use_denoising=True)
        sc.cycles.samples = samples
    else:
        bake.configure_safe_threads(sc)
        try:
            sc.eevee.taa_render_samples = samples
            sc.eevee.use_raytracing = True
        except AttributeError:
            pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    paths = []
    try:
        for v in views:
            spec = VIEWS[v] if isinstance(v, str) else v
            name = v if isinstance(v, str) else spec.get("name", "view")
            frame_camera(cam, objs, spec["dir"], spec.get("lens", 50), spec.get("margin", 1.05), res[0] / res[1])
            out_path = os.path.join(out_dir, f"{prefix}{name}.png")
            bake.render_still_safe(sc, out_path)
            paths.append(out_path)
            core.log("rendered", out_path)
    finally:
        sc.camera = saved["camera"]
        sc.render.engine = saved["engine"]
        sc.render.resolution_x, sc.render.resolution_y = saved["rx"], saved["ry"]
        sc.render.resolution_percentage = saved["pct"]
        sc.render.filepath = saved["path"]
        sc.render.image_settings.file_format = saved["fmt"]
        if saved["world"] is not None:
            sc.world = saved["world"]
    return paths


def frame_viewport(objs=None):
    """Point every 3D viewport at `objs` (or everything) so MCP `look` sees the asset."""
    wm = bpy.context.window_manager
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            with bpy.context.temp_override(window=win, area=area, region=region):
                if objs:
                    for o in bpy.context.view_layer.objects:
                        o.select_set(o in objs)
                    bpy.ops.view3d.view_selected()
                else:
                    bpy.ops.view3d.view_all()

