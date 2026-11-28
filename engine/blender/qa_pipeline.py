"""Headless Blender 5.2+ visual QA and multi-angle render pipeline for Velum Forge.

Usage:
    blender -b [scene.blend] --python-exit-code 1 -P tools/blender/qa_pipeline.py -- \
        [--input <asset.py|mesh>] --out-dir <dir> [--collection Name] [--objects A B] \
        [--profile roblox|game|render|print] [--renderer auto|cycles|workbench] [--fast]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import runpy
import sys
from collections import defaultdict

import bpy
from mathutils import Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(THIS_DIR))
QA_SKILLS_SCRIPTS = THIS_DIR

for p in (THIS_DIR, QA_SKILLS_SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import qa_check  # noqa: E402

STUDIO_COLLECTIONS = {"SC_Studio", "PreviewStudio", "QA_Studio"}
MATERIAL_VIEWS = [
    ("hero", "HERO 3/4", "PERSP", (0.85, -1.0, 0.45)),
    ("front", "FRONT (ORTHO)", "ORTHO", (0.0, -1.0, 0.0)),
    ("side", "SIDE (ORTHO)", "ORTHO", (1.0, 0.0, 0.0)),
    ("back", "BACK (ORTHO)", "ORTHO", (0.0, 1.0, 0.0)),
    ("top", "TOP (ORTHO)", "ORTHO", (0.0, -0.001, 1.0)),
    ("rear_34", "REAR 3/4", "PERSP", (-0.85, 1.0, 0.45)),
]


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _ensure_object_mode() -> None:
    ob = bpy.context.view_layer.objects.active
    if ob and ob.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass


def _clear_default_scene() -> None:
    _ensure_object_mode()
    for ob in list(bpy.data.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and data.users == 0:
            for coll in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras):
                try:
                    if coll.get(data.name) == data:
                        coll.remove(data)
                        break
                except (TypeError, ReferenceError):
                    pass


def _import_asset(path: str) -> None:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        _clear_default_scene()
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        _clear_default_scene()
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        _clear_default_scene()
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == ".stl":
        _clear_default_scene()
        bpy.ops.wm.stl_import(filepath=path)
    elif ext == ".py":
        script_dir = os.path.dirname(os.path.abspath(path))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            runpy.run_path(path, run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise RuntimeError(f"Build script exited with code {exc.code}: {path}") from exc
    else:
        raise ValueError(f"Unsupported --input extension: {ext}")


def _collection_is_excluded(col: bpy.types.Collection) -> bool:
    name = col.name
    return name in STUDIO_COLLECTIONS or name.endswith("_ref") or name.startswith("EXPORT_")


def _select_targets(collection_name: str | None, object_names: list[str] | None) -> list[bpy.types.Object]:
    if object_names:
        missing = [n for n in object_names if n not in bpy.data.objects]
        if missing:
            raise KeyError(f"Requested objects not found: {missing}")
        return [bpy.data.objects[n] for n in object_names if bpy.data.objects[n].type == "MESH"]

    if collection_name:
        col = bpy.data.collections.get(collection_name)
        if col is None:
            raise KeyError(f"Collection not found: {collection_name}")
        return [o for o in col.all_objects if o.type == "MESH"]

    # Default: gather visible/renderable MESH objects outside studio/ref collections.
    excluded_objs: set[bpy.types.Object] = set()
    for col in bpy.data.collections:
        if _collection_is_excluded(col):
            excluded_objs.update(col.all_objects)

    candidates = [
        o
        for o in bpy.context.scene.objects
        if o.type == "MESH" and o not in excluded_objs and not o.hide_render
    ]
    if not candidates:
        candidates = [
            o for o in bpy.context.scene.objects if o.type == "MESH" and o not in excluded_objs
        ]
    # Ignore leftover starter Cube when other meshes exist
    non_cube = [o for o in candidates if o.name != "Cube"]
    return non_cube or candidates


def _world_bbox(obs: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e18, 1e18, 1e18))
    hi = Vector((-1e18, -1e18, -1e18))
    found = False
    for ob in obs:
        eo = ob.evaluated_get(dg)
        me = eo.to_mesh()
        try:
            mw = ob.matrix_world
            for v in me.vertices:
                w = mw @ v.co
                lo.x = min(lo.x, w.x)
                lo.y = min(lo.y, w.y)
                lo.z = min(lo.z, w.z)
                hi.x = max(hi.x, w.x)
                hi.y = max(hi.y, w.y)
                hi.z = max(hi.z, w.z)
                found = True
        finally:
            eo.to_mesh_clear()
    if not found:
        return Vector((0, 0, 0)), Vector((1, 1, 1))
    return lo, hi


def _bbox_corners(lo: Vector, hi: Vector) -> list[Vector]:
    return [
        Vector((x, y, z))
        for x in (lo.x, hi.x)
        for y in (lo.y, hi.y)
        for z in (lo.z, hi.z)
    ]


def _frame_camera(
    cam: bpy.types.Object,
    lo: Vector,
    hi: Vector,
    direction: tuple[float, float, float],
    proj_type: str,
    res_x: int,
    res_y: int,
) -> None:
    center = (lo + hi) * 0.5
    radius = max((hi - lo).length * 0.5, 1e-3)
    d = Vector(direction).normalized()
    rot_q = (-d).to_track_quat("-Z", "Y")
    cam.rotation_euler = rot_q.to_euler()
    aspect = res_x / max(res_y, 1)

    if proj_type == "ORTHO":
        cam.data.type = "ORTHO"
        right = rot_q @ Vector((1.0, 0.0, 0.0))
        up = rot_q @ Vector((0.0, 1.0, 0.0))
        corners = _bbox_corners(lo, hi)
        xs = [(c - center).dot(right) for c in corners]
        ys = [(c - center).dot(up) for c in corners]
        span_x = max(xs) - min(xs)
        span_y = max(ys) - min(ys)
        cam.data.ortho_scale = max(span_x, span_y * aspect, 1e-3) * 1.15
        dist = radius * 4.0 + 1.0
        cam.location = center + d * dist
    else:
        cam.data.type = "PERSP"
        cam.data.lens = 50.0
        fov_h = 2.0 * math.atan(cam.data.sensor_width / (2.0 * cam.data.lens))
        fov_v = 2.0 * math.atan(math.tan(fov_h * 0.5) / aspect)
        dist = radius / math.sin(min(fov_h, fov_v) * 0.5) * 1.12
        cam.location = center + d * dist

    cam.data.clip_start = max(0.005, dist / 500.0)
    cam.data.clip_end = max(dist * 20.0, 100.0)


def _configure_cycles_gpu(scene: bpy.types.Scene, samples: int) -> str:
    try:
        from vflib import bake as _vf_bake

        dev = _vf_bake.enable_cycles_gpu(scene, use_denoising=True)
        scene.cycles.samples = samples
        return dev
    except Exception:
        pass

    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    cpus = os.cpu_count() or 8
    env_t = os.environ.get("VELUM_BLENDER_THREADS", "").strip()
    safe_threads = int(env_t) if env_t.isdigit() and int(env_t) > 0 else min(8, max(2, cpus // 2))
    env_ts = os.environ.get("VELUM_CYCLES_TILE_SIZE", "").strip()
    safe_tile = int(env_ts) if env_ts.isdigit() and int(env_ts) >= 64 else 512
    try:
        scene.render.threads_mode = "FIXED"
        scene.render.threads = safe_threads
        scene.cycles.use_auto_tile = True
        scene.cycles.tile_size = safe_tile
    except Exception:
        pass

    device_used = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == dev_type]
                if devs:
                    for d in prefs.devices:
                        d.use = (d.type == dev_type)
                    scene.cycles.device = "GPU"
                    device_used = dev_type
                    break
            except Exception:
                continue
    except Exception:
        pass
    if device_used == "CPU":
        scene.cycles.device = "CPU"

    scene.cycles.use_denoising = True
    if device_used == "OPTIX":
        try:
            scene.cycles.denoising_use_gpu = True
        except Exception:
            pass
        try:
            scene.cycles.denoiser = "OPTIX"
        except Exception:
            pass
    elif device_used != "CPU":
        try:
            scene.cycles.denoiser = "OPENIMAGEDENOISE"
            scene.cycles.denoising_use_gpu = True
        except Exception:
            pass
    return device_used


def _render_still(scene: bpy.types.Scene, out_png: str) -> str:
    """Render via `vflib.bake.render_still_safe` (atomic fsync + GPU-only guard + cooldown)."""
    try:
        from vflib import bake as _vf_bake

        return _vf_bake.render_still_safe(scene, out_png)
    except Exception:
        pass
    import shutil
    import tempfile
    import time

    abs_dst = os.path.abspath(out_png)
    dst_dir = os.path.dirname(abs_dst)
    os.makedirs(dst_dir, exist_ok=True)
    tmp_p = os.path.join(tempfile.gettempdir(), f"__vf_qa_{os.getpid()}_{os.path.basename(abs_dst)}")
    staged = os.path.join(dst_dir, f".__vf_stage_{os.getpid()}_{os.path.basename(abs_dst)}")
    scene.render.filepath = tmp_p
    bpy.ops.render.render(write_still=True)
    try:
        shutil.copy2(tmp_p, staged)
        try:
            with open(staged, "rb+") as fh:
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            pass
        for attempt in range(6):
            try:
                os.replace(staged, abs_dst)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.4)
    finally:
        for p in (tmp_p, staged):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
    return out_png


def _build_studio(lo: Vector, hi: Vector) -> tuple[bpy.types.Collection, bpy.types.World]:
    col = bpy.data.collections.new("QA_Studio")
    bpy.context.scene.collection.children.link(col)
    center = (lo + hi) * 0.5
    radius = max((hi - lo).length * 0.5, 0.25)

    def add_area(name: str, offset: tuple[float, float, float], size: float, energy: float, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.size = size
        ld.energy = energy
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        col.objects.link(ob)
        loc = center + Vector(offset) * radius
        ob.location = loc
        ob.rotation_euler = (center - loc).to_track_quat("-Z", "Y").to_euler()
        return ob

    scale_e = radius * radius
    add_area("QA_Key", (1.8, -1.6, 2.6), radius * 1.8, 115.0 * scale_e)
    add_area("QA_Fill", (-2.2, -1.2, 1.1), radius * 2.2, 52.0 * scale_e, (0.90, 0.95, 1.0))
    add_area("QA_BowFill", (1.3, 2.2, 1.5), radius * 2.0, 82.0 * scale_e, (0.98, 0.98, 1.0))
    add_area("QA_Rim", (-1.1, 2.3, 1.9), radius * 1.6, 65.0 * scale_e)

    world = bpy.data.worlds.new("QA_StudioWorld")
    try:
        world.use_nodes = True
    except (AttributeError, TypeError):
        pass
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    lp = nt.nodes.new("ShaderNodeLightPath")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.36
    ramp.color_ramp.elements[0].color = (0.50, 0.54, 0.60, 1.0)
    ramp.color_ramp.elements[1].position = 0.56
    ramp.color_ramp.elements[1].color = (0.94, 0.96, 0.99, 1.0)
    env_bg = nt.nodes.new("ShaderNodeBackground")
    env_bg.inputs["Strength"].default_value = 0.95
    cam_bg = nt.nodes.new("ShaderNodeBackground")
    cam_bg.inputs["Color"].default_value = (0.82, 0.85, 0.89, 1.0)
    cam_bg.inputs["Strength"].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], env_bg.inputs["Color"])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(env_bg.outputs["Background"], mix.inputs[1])
    nt.links.new(cam_bg.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return col, world


def _build_backface_material() -> bpy.types.Material:
    mat = bpy.data.materials.new("QA_BackfaceMat")
    try:
        mat.use_nodes = True
    except (AttributeError, TypeError):
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    front = nt.nodes.new("ShaderNodeBsdfDiffuse")
    front.inputs["Color"].default_value = (0.14, 0.44, 0.88, 1.0)
    back = nt.nodes.new("ShaderNodeEmission")
    back.inputs["Color"].default_value = (1.0, 0.06, 0.06, 1.0)
    back.inputs["Strength"].default_value = 2.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geom.outputs["Backfacing"], mix.inputs["Fac"])
    nt.links.new(front.outputs["BSDF"], mix.inputs[1])
    nt.links.new(back.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def _set_workbench(scene: bpy.types.Scene, color_type: str, cavity: bool = True) -> None:
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = color_type
    sh.show_cavity = cavity
    sh.show_object_outline = True
    sh.background_type = "VIEWPORT"
    sh.background_color = (0.86, 0.89, 0.93)


def _compute_suncity_metrics(targets: list[bpy.types.Object], profile: str, qa: dict) -> dict:
    lo, hi = _world_bbox(targets)
    size = hi - lo
    sc_part_tris: dict[str, int] = defaultdict(int)
    total_tris = 0
    for ob in targets:
        t = int(qa.get("objects", {}).get(ob.name, {}).get("tris", 0))
        total_tris += t
        part_name = ob.get("sc_part", ob.name)
        sc_part_tris[str(part_name)] += t

    if profile == "roblox":
        for part_name, t in sc_part_tris.items():
            if t > 20000:
                msg = (
                    f"sc_part '{part_name}': combined {t} tris > Roblox 20,000 limit "
                    "(split joined repeated/separable objects—e.g. 2+ stools or chairs—into separate linked instances or sub-parts before reducing detail)"
                )
                if msg not in qa["errors"]:
                    qa["errors"].append(msg)
                    qa["pass"] = False

    sockets = sorted(o.name for o in bpy.context.scene.objects if o.name.startswith("SOCKET_"))
    seats = sorted(o.name for o in bpy.context.scene.objects if o.name.startswith("SEAT_"))
    return {
        "object_count": len(targets),
        "total_tris": total_tris,
        "sc_part_tris": dict(sorted(sc_part_tris.items(), key=lambda kv: -kv[1])),
        "bbox_min_m": [round(lo.x, 4), round(lo.y, 4), round(lo.z, 4)],
        "bbox_max_m": [round(hi.x, 4), round(hi.y, 4), round(hi.z, 4)],
        "size_m": [round(size.x, 4), round(size.y, 4), round(size.z, 4)],
        "size_studs_sclib": [round(size.x * 3.0, 2), round(size.y * 3.0, 2), round(size.z * 3.0, 2)],
        "size_studs_metric": [round(size.x / 0.28, 2), round(size.y / 0.28, 2), round(size.z / 0.28, 2)],
        "x_symmetry_offset_m": round(abs(lo.x + hi.x), 4),
        "sockets": sockets,
        "seats": seats,
    }


def _oriented_dir(direction: tuple[float, float, float], forward_axis: str, is_top: bool = False) -> tuple[float, float, float]:
    if forward_axis == "+Y" and not is_top:
        return (-direction[0], -direction[1], direction[2])
    return direction


def _load_asset_spec(args: argparse.Namespace) -> dict:
    candidates: list[str] = []
    if getattr(args, "spec", ""):
        candidates.append(os.path.abspath(args.spec))
    if args.input:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(args.input)), "asset_spec.json"))
    for c in candidates:
        if c and os.path.isfile(c):
            try:
                with open(c, "r", encoding="utf-8-sig") as fh:
                    return json.load(fh)
            except Exception:
                return {}
    return {}


def _discover_ref_cameras() -> list[bpy.types.Object]:
    cams = [
        o for o in bpy.data.objects
        if o.type == "CAMERA" and (o.name.startswith("VF_RefCam_") or o.get("vf_ref_image"))
    ]
    cams.sort(key=lambda o: o.name)
    return cams


def _frame_perspective_spec(
    cam: bpy.types.Object,
    lo: Vector,
    hi: Vector,
    cam_cfg: dict,
    res_x: int,
    res_y: int,
) -> None:
    center = (lo + hi) * 0.5
    radius = max((hi - lo).length * 0.5, 0.25)
    lens_mm = float(cam_cfg.get("lens_mm") or 35.0)
    cam.data.type = "PERSP"
    cam.data.lens = lens_mm
    aspect = res_x / max(res_y, 1)

    if "location" in cam_cfg and "target" in cam_cfg:
        loc = Vector(cam_cfg["location"])
        tgt = Vector(cam_cfg["target"])
    else:
        az = math.radians(float(cam_cfg.get("azimuth_deg", 38.0)))
        el = math.radians(float(cam_cfg.get("elevation_deg", 16.0)))
        dist_scale = float(cam_cfg.get("distance_scale", 1.18))
        fov_h = 2.0 * math.atan(cam.data.sensor_width / (2.0 * max(lens_mm, 8.0)))
        fov_v = 2.0 * math.atan(math.tan(fov_h * 0.5) / aspect)
        dist = radius / max(math.sin(min(fov_h, fov_v) * 0.5), 0.12) * dist_scale
        d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
        loc = center + d * dist
        if cam_cfg.get("eye_height_m") is not None:
            loc.z = float(cam_cfg["eye_height_m"])
        tgt = Vector(cam_cfg["target"]) if "target" in cam_cfg else center

    direction = tgt - loc
    if direction.length < 1e-6:
        direction = Vector((0.0, 1.0, 0.0))
    cam.location = loc
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    dist_eff = max(direction.length, 0.5)
    cam.data.clip_start = max(0.01, dist_eff / 500.0)
    cam.data.clip_end = max(dist_eff * 25.0, 200.0)


def run_pipeline(args: argparse.Namespace) -> dict:
    if args.input:
        _import_asset(os.path.abspath(args.input))

    _ensure_object_mode()
    targets = _select_targets(args.collection, args.objects)
    if not targets:
        raise RuntimeError("No target MESH objects found to inspect and render.")

    os.makedirs(args.out_dir, exist_ok=True)
    spec = _load_asset_spec(args)
    is_high_poly = bool(getattr(args, "high_poly", False) or spec.get("high_poly_uncapped", False))
    if args.profile == "auto":
        resolved_profile = str(spec.get("qa_profile") or ("game" if is_high_poly else "roblox"))
        if is_high_poly and resolved_profile == "roblox":
            resolved_profile = "game"
    else:
        resolved_profile = args.profile

    if args.max_tris is not None and args.max_tris >= 0:
        resolved_max_tris = int(args.max_tris)
    elif is_high_poly:
        resolved_max_tris = 0
    elif spec.get("qa_max_tris") is not None:
        resolved_max_tris = int(spec["qa_max_tris"])
    else:
        resolved_max_tris = 300000

    asset_name = args.asset_name or spec.get("title") or (
        os.path.splitext(os.path.basename(args.input))[0]
        if args.input
        else args.collection
        or (os.path.splitext(os.path.basename(bpy.data.filepath))[0] if bpy.data.filepath else "SceneAsset")
    )

    qa = qa_check.run(objects=[o.name for o in targets], profile=resolved_profile, max_tris=resolved_max_tris)
    metrics = _compute_suncity_metrics(targets, resolved_profile, qa)
    qa.update(metrics)
    qa["asset_name"] = asset_name
    qa["profile"] = resolved_profile
    qa["max_tris"] = resolved_max_tris
    qa["high_poly_uncapped"] = is_high_poly

    res_x = 512 if args.fast else args.res_x
    res_y = 384 if args.fast else args.res_y
    use_workbench_material = args.fast or args.renderer == "workbench"

    sc = bpy.context.scene
    saved = {
        "engine": sc.render.engine,
        "rx": sc.render.resolution_x,
        "ry": sc.render.resolution_y,
        "pct": sc.render.resolution_percentage,
        "fp": sc.render.filepath,
        "fmt": sc.render.image_settings.file_format,
        "cam": sc.camera,
        "world": sc.world,
        "vt": sc.view_settings.view_transform,
        "mat_override": bpy.context.view_layer.material_override,
        "bg_type": sc.display.shading.background_type,
        "bg_color": tuple(sc.display.shading.background_color),
        "obj_colors": {o: tuple(o.color) for o in targets},
        "hide_render": {o: o.hide_render for o in sc.objects},
    }

    lo, hi = _world_bbox(targets)
    radius = max((hi - lo).length * 0.5, 0.25)
    studio_col = None
    studio_world = None
    backface_mat = None
    temp_obs: list[bpy.types.Object] = []
    tiles: dict[str, dict] = {}
    ref_pairs: list[dict] = []

    try:
        for o in sc.objects:
            o.hide_render = o not in targets

        studio_col, studio_world = _build_studio(lo, hi)
        sc.world = studio_world

        cam_data = bpy.data.cameras.new("QA_RenderCam")
        cam = bpy.data.objects.new("QA_RenderCam", cam_data)
        studio_col.objects.link(cam)
        sc.camera = cam

        sc.render.resolution_x = res_x
        sc.render.resolution_y = res_y
        sc.render.resolution_percentage = 100
        sc.render.image_settings.media_type = "IMAGE"
        sc.render.image_settings.file_format = "PNG"

        if use_workbench_material:
            _set_workbench(sc, "MATERIAL", cavity=True)
            renderer_label = "Workbench"
        else:
            dev = _configure_cycles_gpu(sc, samples=24)
            try:
                sc.view_settings.view_transform = "AgX"
            except TypeError:
                try:
                    sc.view_settings.view_transform = "Standard"
                except TypeError:
                    pass
            renderer_label = f"Cycles {dev}"

        qa["renderer"] = renderer_label

        # 1) 6-view Material sheet + 4th Diagnostic tile (Underbody / Bottom)
        for key, label, proj, direction in MATERIAL_VIEWS:
            d = _oriented_dir(direction, args.forward_axis, is_top=(key == "top"))
            _frame_camera(cam, lo, hi, d, proj, res_x, res_y)
            out_png = os.path.join(args.out_dir, f"tile_{key}.png")
            _render_still(sc, out_png)
            tile_meta = {"path": out_png, "label": label, "projection": proj}
            if proj == "ORTHO":
                tile_meta["ortho_scale_m"] = round(float(cam.data.ortho_scale), 4)
            tiles[key] = tile_meta

        # 1b) Matched Perspective Reference Cameras (`VF_RefCam_*` in scene OR perspective refs in asset_spec.json)
        matched_ref_paths: set[str] = set()
        scene_ref_cams = _discover_ref_cameras()
        for r_idx, rcam in enumerate(scene_ref_cams[:8]):
            sc.camera = rcam
            out_png = os.path.join(args.out_dir, f"tile_refcam_{r_idx:02d}.png")
            _render_still(sc, out_png)
            ref_img = str(rcam.get("vf_ref_image") or "")
            vw = str(rcam.get("vf_ref_view") or rcam.name)
            lens_mm = round(float(rcam.data.lens), 1)
            lbl = f"MATCHED CAM: {vw.upper()} (PERSP {lens_mm:g}mm)"
            tiles[f"refcam_{r_idx:02d}"] = {"path": out_png, "label": lbl, "projection": "PERSP", "lens_mm": lens_mm}
            if ref_img and os.path.isfile(ref_img):
                matched_ref_paths.add(os.path.normcase(os.path.abspath(ref_img)))
                ref_pairs.append({
                    "ref_path": os.path.abspath(ref_img),
                    "ref_label": f"REFERENCE ({os.path.basename(ref_img)}) [{vw.upper()}]",
                    "model_path": out_png,
                    "model_label": f"MODEL — {lbl}",
                    "projection": "PERSP",
                    "lens_mm": lens_mm,
                })
        sc.camera = cam

        # Fallback: pair any remaining spec references (perspective cameras or ortho blueprints)
        ortho_key_map = {
            "ortho_front": "front",
            "front": "front",
            "ortho_back": "back",
            "back": "back",
            "ortho_top": "top",
            "top": "top",
            "ortho_side": "side",
            "side": "side",
        }
        persp_fallback_idx = len(scene_ref_cams)
        spec_base_dir = os.path.dirname(os.path.abspath(args.spec or args.input)) if (getattr(args, "spec", "") or args.input) else ""
        for s_ref in (spec.get("references") or [])[:8]:
            raw_rp = str(s_ref.get("path") or s_ref.get("filename") or "")
            rp = raw_rp
            if rp and not os.path.isabs(rp) and spec_base_dir:
                rp = os.path.join(spec_base_dir, rp)
            if (not rp or not os.path.isfile(rp)) and raw_rp and spec_base_dir:
                cand_rp = os.path.join(spec_base_dir, "references", os.path.basename(raw_rp))
                if os.path.isfile(cand_rp):
                    rp = cand_rp
            if not rp or not os.path.isfile(rp):
                continue
            norm_rp = os.path.normcase(os.path.abspath(rp))
            if norm_rp in matched_ref_paths:
                continue
            matched_ref_paths.add(norm_rp)
            vw = str(s_ref.get("view") or "hero").lower()
            proj = str(s_ref.get("projection") or ("ortho_blueprint" if vw in ortho_key_map else "perspective")).lower()
            if proj == "ortho_blueprint":
                tk = ortho_key_map.get(vw, "side")
                tile_info = tiles.get(tk) or tiles.get("side")
                if tile_info:
                    ref_pairs.append({
                        "ref_path": os.path.abspath(rp),
                        "ref_label": f"BLUEPRINT ({os.path.basename(rp)}) [{tk.upper()} ORTHO]",
                        "model_path": tile_info["path"],
                        "model_label": f"MODEL — {tile_info['label']}",
                        "projection": "ORTHO",
                        "ortho_scale_m": tile_info.get("ortho_scale_m"),
                    })
            else:
                cam_cfg = dict(s_ref.get("camera") or {})
                _frame_perspective_spec(cam, lo, hi, cam_cfg, res_x, res_y)
                out_png = os.path.join(args.out_dir, f"tile_refcam_{persp_fallback_idx:02d}.png")
                _render_still(sc, out_png)
                lens_mm = round(float(cam.data.lens), 1)
                lbl = f"MATCHED CAM: {vw.upper()} (PERSP {lens_mm:g}mm)"
                tiles[f"refcam_{persp_fallback_idx:02d}"] = {"path": out_png, "label": lbl, "projection": "PERSP", "lens_mm": lens_mm}
                ref_pairs.append({
                    "ref_path": os.path.abspath(rp),
                    "ref_label": f"REFERENCE ({os.path.basename(rp)}) [{vw.upper()}]",
                    "model_path": out_png,
                    "model_label": f"MODEL — {lbl}",
                    "projection": "PERSP",
                    "lens_mm": lens_mm,
                })
                persp_fallback_idx += 1

        # Underbody / Bottom in same material look
        bottom_dir = _oriented_dir((0.75, -0.75, -0.75), args.forward_axis)
        _frame_camera(cam, lo, hi, bottom_dir, "PERSP", res_x, res_y)
        bottom_png = os.path.join(args.out_dir, "tile_diag_bottom.png")
        _render_still(sc, bottom_png)
        tiles["diag_bottom"] = {"path": bottom_png, "label": "UNDERBODY / BOTTOM", "projection": "PERSP"}

        # 2) Diagnostic 1: Wireframe (Hero 3/4)
        hero_dir = _oriented_dir((0.85, -1.0, 0.45), args.forward_axis)
        _frame_camera(cam, lo, hi, hero_dir, "PERSP", res_x, res_y)
        _set_workbench(sc, "OBJECT", cavity=True)
        wire_t = max(radius * 0.0035, 0.0005)
        for ob in targets:
            ob.color = (0.82, 0.84, 0.87, 1.0)
            w = ob.copy()
            w.data = ob.data
            w.color = (0.04, 0.05, 0.07, 1.0)
            wf = w.modifiers.new("QA_Wire", "WIREFRAME")
            wf.thickness = wire_t
            wf.use_even_offset = False
            wf.use_relative_offset = False
            wf.use_replace = True
            studio_col.objects.link(w)
            w.hide_render = False
            temp_obs.append(w)

        wire_png = os.path.join(args.out_dir, "tile_diag_wire.png")
        _render_still(sc, wire_png)
        tiles["diag_wire"] = {"path": wire_png, "label": "WIREFRAME (HERO 3/4)", "projection": "PERSP"}

        for w in temp_obs:
            bpy.data.objects.remove(w, do_unlink=True)
        temp_obs.clear()

        # 3) Diagnostic 2: Part Colors (Hero 3/4)
        _set_workbench(sc, "RANDOM", cavity=True)
        parts_png = os.path.join(args.out_dir, "tile_diag_parts.png")
        _render_still(sc, parts_png)
        tiles["diag_parts"] = {"path": parts_png, "label": "PART COLORS (HERO 3/4)", "projection": "PERSP"}

        # 4) Diagnostic 3: Face Orientation (Blue=Outward / Red=Flipped)
        _configure_cycles_gpu(sc, samples=16)
        backface_mat = _build_backface_material()
        bpy.context.view_layer.material_override = backface_mat
        normals_png = os.path.join(args.out_dir, "tile_diag_normals.png")
        _render_still(sc, normals_png)
        tiles["diag_normals"] = {
            "path": normals_png,
            "label": "FACE ORIENTATION (BLUE=OUT / RED=FLIPPED)",
            "projection": "PERSP",
        }

        qa_path = os.path.join(args.out_dir, "qa_report.json")
        with open(qa_path, "w", encoding="utf-8") as fh:
            json.dump(qa, fh, indent=2)

        man_path = os.path.join(args.out_dir, "render_manifest.json")
        with open(man_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "asset_name": asset_name,
                    "ortho_grid": bool(getattr(args, "ortho_grid", False) or spec.get("ortho_blueprint_grid", False)),
                    "size_m": metrics["size_m"],
                    "tiles": tiles,
                    "ref_pairs": ref_pairs,
                },
                fh,
                indent=2,
            )

        print(f"@@QA_DONE@@ {json.dumps({'pass': qa['pass'], 'tris': qa['total_tris'], 'qa_json': qa_path, 'manifest': man_path, 'ref_pairs': len(ref_pairs)})}", flush=True)
        return qa

    finally:
        for w in temp_obs:
            if w and w.name in bpy.data.objects:
                bpy.data.objects.remove(w, do_unlink=True)
        bpy.context.view_layer.material_override = saved["mat_override"]
        if backface_mat is not None and backface_mat.name in bpy.data.materials:
            bpy.data.materials.remove(backface_mat)
        for o, h in saved["hide_render"].items():
            if o and o.name in bpy.data.objects:
                o.hide_render = h
        for o, c in saved["obj_colors"].items():
            if o and o.name in bpy.data.objects:
                o.color = c
        sc.camera = saved["cam"]
        sc.world = saved["world"]
        sc.render.engine = saved["engine"]
        sc.render.resolution_x = saved["rx"]
        sc.render.resolution_y = saved["ry"]
        sc.render.resolution_percentage = saved["pct"]
        sc.render.filepath = saved["fp"]
        sc.render.image_settings.file_format = saved["fmt"]
        try:
            sc.view_settings.view_transform = saved["vt"]
        except TypeError:
            pass
        sc.display.shading.background_type = saved["bg_type"]
        sc.display.shading.background_color = saved["bg_color"]
        if studio_col is not None and studio_col.name in bpy.data.collections:
            for ob in list(studio_col.objects):
                data = ob.data
                bpy.data.objects.remove(ob, do_unlink=True)
                if data is not None and data.users == 0:
                    for coll in (bpy.data.lights, bpy.data.cameras):
                        try:
                            if coll.get(data.name) == data:
                                coll.remove(data)
                                break
                        except (TypeError, ReferenceError):
                            pass
            bpy.data.collections.remove(studio_col)
        if studio_world is not None and studio_world.name in bpy.data.worlds:
            bpy.data.worlds.remove(studio_world)


def main() -> int:
    parser = argparse.ArgumentParser(description="Velum Forge Blender visual QA pipeline.")
    parser.add_argument("--input", default="", help="Asset file (.py, .glb, .gltf, .fbx, .obj, .stl)")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--collection", default="", help="Target collection name")
    parser.add_argument("--objects", nargs="*", default=None, help="Target object names")
    parser.add_argument("--profile", default="roblox", choices=["auto", "roblox", "game", "render", "print"])
    parser.add_argument("--max-tris", type=int, default=-1, help="BVH check tri threshold (-1 = auto from spec/300000, 0 = unlimited)")
    parser.add_argument("--high-poly", action="store_true", help="Opt-in High-Poly Uncapped Mode (no 300k BVH cap / no 20k part cap)")
    parser.add_argument("--renderer", default="auto", choices=["auto", "cycles", "workbench"])
    parser.add_argument("--fast", action="store_true", help="Fast Workbench material render at 512x384")
    parser.add_argument("--res-x", type=int, default=640)
    parser.add_argument("--res-y", type=int, default=480)
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--forward-axis", default="-Y", choices=["-Y", "+Y"])
    parser.add_argument("--spec", default="", help="Optional path to asset_spec.json")
    parser.add_argument("--ortho-grid", action="store_true", help="Enable optional metric blueprint grid on ORTHO views only")
    args = parser.parse_args(_argv())

    run_pipeline(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


