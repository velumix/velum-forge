"""Blender 3D Reference Loader (`vflib.refs`) — Perspective Matched Cameras + Ortho Blueprints.

Handles BOTH real-world reference workflows cleanly:
1. **Perspective Photos** (`projection == "perspective"` — Street View, 3/4 shots, close-ups, aerials):
   Spawns matched perspective Blender cameras (`VF_RefCam_XX_<view>`) with the exact focal length
   (`lens_mm`) and attaches the reference photo as the camera's background image overlay so artists
   and `qa_pipeline.py` can compare model vs. photo through the exact matching perspective lens!
2. **Orthographic Blueprints** (`projection == "ortho_blueprint"` — Side/Front/Top elevations ONLY):
   Places 1:1 m orthographic blueprint planes inside `VF_References_ref` and optionally creates a
   calibrated metric wireframe grid (`show_ortho_grid=True`) — never cluttering perspective photos!

Everything lives inside `VF_References_ref`, which `qa_pipeline.py` and game exporters ignore.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

import bmesh
import bpy
from mathutils import Vector

from . import core

ORTHO_VIEWS = {"ortho_side", "ortho_front", "ortho_back", "ortho_top", "side", "front", "back", "top"}


def _infer_projection(item: dict[str, Any]) -> str:
    proj = str(item.get("projection") or "").lower().strip()
    if proj in ("perspective", "ortho_blueprint"):
        return proj
    if proj == "ortho":
        return "ortho_blueprint"
    view = str(item.get("view") or "hero").lower().strip()
    return "ortho_blueprint" if view in ORTHO_VIEWS else "perspective"


def _create_metric_ortho_grid(
    col: bpy.types.Collection,
    name: str,
    width_m: float,
    height_m: float,
    step_m: float,
    location: tuple[float, float, float],
    rotation_euler: tuple[float, float, float],
) -> bpy.types.Object:
    """Create a lightweight non-rendering wireframe metric calibration grid (ortho blueprints only)."""
    bm = bmesh.new()
    step = max(0.05, float(step_m))
    hw = max(step, width_m * 0.5)
    hh = max(step, height_m * 0.5)

    nx = int(math.ceil(hw / step))
    ny = int(math.ceil(hh / step))
    for ix in range(-nx, nx + 1):
        x = ix * step
        if abs(x) <= hw + 1e-5:
            v0 = bm.verts.new((x, -hh, 0.0))
            v1 = bm.verts.new((x, hh, 0.0))
            bm.edges.new((v0, v1))
    for iy in range(-ny, ny + 1):
        y = iy * step
        if abs(y) <= hh + 1e-5:
            v0 = bm.verts.new((-hw, y, 0.0))
            v1 = bm.verts.new((hw, y, 0.0))
            bm.edges.new((v0, v1))

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = location
    ob.rotation_euler = rotation_euler
    ob.display_type = "WIRE"
    ob.hide_render = True
    ob.color = (0.14, 0.82, 0.94, 0.55)
    col.objects.link(ob)
    return ob


def add_perspective_ref_camera(
    name: str,
    image_path: str = "",
    *,
    location: tuple[float, float, float] | Vector,
    target: tuple[float, float, float] | Vector,
    lens_mm: float = 35.0,
    view_label: str = "perspective",
    alpha: float = 0.35,
    col: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    """Create a matched perspective reference camera (`VF_RefCam_*`) with optional photo overlay.

    `qa_pipeline.py` automatically discovers all `VF_RefCam_*` cameras in the scene and renders
    them for the multi-reference side-by-side comparison sheet (`ref_comparison.png`)!
    """
    target_col = col or bpy.data.collections.get("VF_References_ref") or core.fresh_collection("VF_References_ref")
    cam_name = name if name.startswith("VF_RefCam_") else f"VF_RefCam_{name}"
    cam_data = bpy.data.cameras.new(cam_name)
    cam_data.type = "PERSP"
    cam_data.lens = float(lens_mm)
    cam_data.clip_start = 0.02
    cam_data.clip_end = 500.0

    loc_v = Vector(location)
    tgt_v = Vector(target)
    direction = tgt_v - loc_v
    if direction.length < 1e-6:
        direction = Vector((0.0, 1.0, 0.0))

    cam_ob = bpy.data.objects.new(cam_name, cam_data)
    cam_ob.location = loc_v
    cam_ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam_ob["vf_ref_projection"] = "perspective"
    cam_ob["vf_ref_view"] = view_label
    cam_ob["vf_ref_lens_mm"] = float(lens_mm)
    if image_path:
        cam_ob["vf_ref_image"] = os.path.abspath(image_path)
        if os.path.isfile(image_path):
            try:
                img = bpy.data.images.load(image_path, check_existing=True)
                cam_data.show_background_images = True
                bg = cam_data.background_images.new()
                bg.image = img
                bg.alpha = float(alpha)
                bg.display_depth = "FRONT"
                bg.frame_method = "FIT"
            except Exception:
                pass

    target_col.objects.link(cam_ob)
    return cam_ob


def _compute_auto_perspective_camera(
    center: Vector,
    radius: float,
    cam_cfg: dict[str, Any],
) -> tuple[Vector, Vector, float]:
    """Compute `(location, target, lens_mm)` from explicit coords or azimuth/elevation/eye_height."""
    lens_mm = float(cam_cfg.get("lens_mm") or 35.0)
    if "location" in cam_cfg and "target" in cam_cfg:
        return Vector(cam_cfg["location"]), Vector(cam_cfg["target"]), lens_mm

    az = math.radians(float(cam_cfg.get("azimuth_deg", 38.0)))
    el = math.radians(float(cam_cfg.get("elevation_deg", 16.0)))
    dist_scale = float(cam_cfg.get("distance_scale", 1.18))

    # Sensor width 36mm standard full-frame Blender camera
    fov_h = 2.0 * math.atan(36.0 / (2.0 * max(lens_mm, 8.0)))
    fov_v = 2.0 * math.atan(math.tan(fov_h * 0.5) / (4.0 / 3.0))
    dist = max(radius, 0.25) / max(math.sin(min(fov_h, fov_v) * 0.5), 0.12) * dist_scale

    # +Y forward, +X right, +Z up
    dx = math.sin(az) * math.cos(el)
    dy = math.cos(az) * math.cos(el)
    dz = math.sin(el)
    loc = center + Vector((dx, dy, dz)) * dist

    if cam_cfg.get("eye_height_m") is not None:
        loc.z = float(cam_cfg["eye_height_m"])

    tgt = Vector(cam_cfg["target"]) if "target" in cam_cfg else center.copy()
    return loc, tgt, lens_mm


def load_references(
    asset_dir: str,
    *,
    subject_objects: list[bpy.types.Object] | None = None,
    show_ortho_grid: bool | None = None,
) -> bpy.types.Collection | None:
    """Load references from `<asset_dir>/asset_spec.json` or `<asset_dir>/references/`.

    - Perspective photos -> Matched Blender `VF_RefCam_*` perspective cameras with background overlay.
    - Ortho blueprints -> 1:1 m orthographic reference planes + optional metric calibration grid.
    """
    spec_path = os.path.join(asset_dir, "asset_spec.json")
    target_len = 1.20
    refs: list[dict[str, Any]] = []
    spec_ortho_grid = False

    if os.path.isfile(spec_path):
        try:
            with open(spec_path, "r", encoding="utf-8-sig") as fh:
                spec = json.load(fh)
            target_len = float(spec.get("target_length_m", 1.20))
            refs = list(spec.get("references") or [])
            spec_ortho_grid = bool(spec.get("ortho_blueprint_grid", False))
        except Exception:
            pass

    if not refs:
        ref_dir = os.path.join(asset_dir, "references")
        if os.path.isdir(ref_dir):
            for fn in sorted(os.listdir(ref_dir)):
                if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    low = fn.lower()
                    is_ortho = any(k in low for k in ("ortho", "blueprint", "elevation", "side", "front", "top"))
                    vw = (
                        "ortho_front" if "front" in low else
                        "ortho_top" if "top" in low else
                        "ortho_side" if is_ortho else
                        "street_view" if "street" in low else "hero"
                    )
                    refs.append({
                        "path": os.path.join(ref_dir, fn),
                        "view": vw,
                        "projection": "ortho_blueprint" if is_ortho else "perspective",
                    })

    if not refs:
        return None

    use_ortho_grid = spec_ortho_grid if show_ortho_grid is None else bool(show_ortho_grid)

    # Determine bounding box for smart perspective camera auto-framing
    meshes = subject_objects or [
        o for o in bpy.context.scene.objects
        if o.type == "MESH" and not o.name.startswith(("QA_", "SC_", "VF_"))
    ]
    if meshes:
        lo, hi = core.world_bbox(meshes)
        center = (lo + hi) * 0.5
        radius = max((hi - lo).length * 0.5, target_len * 0.5)
    else:
        center = Vector((0.0, 0.0, target_len * 0.25))
        radius = max(target_len * 0.5, 0.35)

    # Suffix `_ref` ensures `qa_pipeline.py` automatically excludes reference objects from mesh QA!
    ref_col = core.fresh_collection("VF_References_ref")
    grid_step = 1.0 if target_len >= 4.0 else (0.25 if target_len >= 1.0 else 0.05)

    for idx, item in enumerate(refs[:8]):
        raw_p = str(item.get("path") or item.get("filename") or "")
        img_p = raw_p
        if img_p and not os.path.isabs(img_p):
            img_p = os.path.join(asset_dir, img_p)
        if not img_p or not os.path.isfile(img_p):
            cand = os.path.join(asset_dir, "references", os.path.basename(raw_p))
            if raw_p and os.path.isfile(cand):
                img_p = cand
        if not img_p or not os.path.isfile(img_p):
            continue

        proj = _infer_projection(item)
        view = str(item.get("view") or ("ortho_side" if proj == "ortho_blueprint" else "hero"))

        if proj == "perspective":
            cam_cfg = dict(item.get("camera") or {})
            # Spread multiple auto perspective cameras slightly in azimuth if user didn't give exact coords
            if "location" not in cam_cfg and "azimuth_deg" not in cam_cfg:
                default_azimuths = [35.0, -35.0, 145.0, -145.0, 15.0, -15.0, 75.0, -75.0]
                cam_cfg["azimuth_deg"] = default_azimuths[idx % len(default_azimuths)]
            loc, tgt, lens_mm = _compute_auto_perspective_camera(center, radius, cam_cfg)
            add_perspective_ref_camera(
                f"VF_RefCam_{idx:02d}_{view}",
                img_p,
                location=loc,
                target=tgt,
                lens_mm=lens_mm,
                view_label=view,
                col=ref_col,
            )
            continue

        # Orthographic blueprint plane (strictly for `ortho_blueprint` references!)
        try:
            img = bpy.data.images.load(img_p, check_existing=True)
        except Exception:
            continue

        emp = bpy.data.objects.new(f"RefPlane_{view}_{idx:02d}", None)
        emp.empty_display_type = "IMAGE"
        emp.data = img
        emp.empty_display_size = target_len
        emp.use_empty_image_alpha = True
        emp.color = (1.0, 1.0, 1.0, 0.42)
        emp["vf_ref_projection"] = "ortho_blueprint"
        emp["vf_ref_view"] = view
        emp["vf_ref_image"] = os.path.abspath(img_p)

        if view in ("front", "ortho_front"):
            loc = (0.0, -target_len * 0.75, target_len * 0.25)
            rot = (math.radians(90.0), 0.0, 0.0)
        elif view in ("back", "ortho_back"):
            loc = (0.0, target_len * 0.75, target_len * 0.25)
            rot = (math.radians(90.0), 0.0, math.radians(180.0))
        elif view in ("top", "ortho_top"):
            loc = (0.0, 0.0, -0.02)
            rot = (0.0, 0.0, math.radians(90.0))
        else:
            loc = (-target_len * 0.45, 0.0, target_len * 0.22)
            rot = (math.radians(90.0), 0.0, math.radians(90.0))

        emp.location = loc
        emp.rotation_euler = rot
        emp.hide_render = True
        ref_col.objects.link(emp)

        if use_ortho_grid:
            _create_metric_ortho_grid(
                ref_col,
                f"VF_OrthoGrid_{view}_{idx:02d}",
                width_m=target_len * 1.1,
                height_m=target_len * 0.75,
                step_m=grid_step,
                location=loc,
                rotation_euler=rot,
            )

    return ref_col


# Backward-compatible alias for all existing Velum Forge scripts
load_reference_planes = load_references
