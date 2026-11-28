"""Reference image staging, perspective vs ortho blueprint classification, palette extraction & `asset_spec.json`."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .review import normalize_review_config

ORTHO_VIEWS = {"ortho_side", "ortho_front", "ortho_back", "ortho_top", "side", "front", "back", "top"}
PERSPECTIVE_VIEWS = {"hero", "street_view", "quarter_left", "quarter_right", "closeup", "aerial", "interior", "photo"}

# Default perspective camera presets (azimuth_deg: 0=+Y front, 90=+X right; elevation_deg; lens_mm)
DEFAULT_CAMERA_PRESETS: dict[str, dict[str, Any]] = {
    "hero": {"lens_mm": 50.0, "azimuth_deg": 40.0, "elevation_deg": 20.0, "distance_scale": 1.15},
    "street_view": {"lens_mm": 28.0, "azimuth_deg": 32.0, "elevation_deg": 4.0, "eye_height_m": 1.65, "distance_scale": 1.18},
    "quarter_left": {"lens_mm": 35.0, "azimuth_deg": -45.0, "elevation_deg": 14.0, "distance_scale": 1.15},
    "quarter_right": {"lens_mm": 35.0, "azimuth_deg": 45.0, "elevation_deg": 14.0, "distance_scale": 1.15},
    "closeup": {"lens_mm": 55.0, "azimuth_deg": 18.0, "elevation_deg": 10.0, "distance_scale": 0.72},
    "aerial": {"lens_mm": 35.0, "azimuth_deg": 38.0, "elevation_deg": 48.0, "distance_scale": 1.25},
    "interior": {"lens_mm": 24.0, "azimuth_deg": 0.0, "elevation_deg": 5.0, "eye_height_m": 1.60, "distance_scale": 0.85},
    "photo": {"lens_mm": 35.0, "azimuth_deg": 35.0, "elevation_deg": 16.0, "distance_scale": 1.15},
}


def classify_reference_view(filename: str, explicit_view: str = "auto", explicit_projection: str = "auto") -> tuple[str, str]:
    """Infer `(view, projection)` where `projection` is `'perspective'` or `'ortho_blueprint'`.

    Only classifies as `ortho_blueprint` when explicitly requested or when the filename clearly
    indicates an orthographic elevation/blueprint (avoiding false ortho grids on real photos!).
    """
    low = Path(filename).stem.lower()
    ev = (explicit_view or "auto").strip().lower()
    ep = (explicit_projection or "auto").strip().lower()

    if ev != "auto":
        view = ev
    elif any(k in low for k in ("street", "streetview", "gsv", "curb", "corner", "facade")):
        view = "street_view"
    elif any(k in low for k in ("aerial", "drone", "bird", "satellite")):
        view = "aerial"
    elif any(k in low for k in ("close", "detail", "macro", "door", "sign", "trim")):
        view = "closeup"
    elif any(k in low for k in ("interior", "inside", "lobby", "cockpit")):
        view = "interior"
    elif any(k in low for k in ("ortho_top", "blueprint_top", "top_plan", "floorplan", "plan_view")):
        view = "ortho_top"
    elif any(k in low for k in ("ortho_front", "blueprint_front", "front_elevation", "front_ortho")):
        view = "ortho_front"
    elif any(k in low for k in ("ortho_back", "blueprint_back", "rear_elevation", "back_ortho")):
        view = "ortho_back"
    elif any(k in low for k in ("ortho_side", "blueprint_side", "side_elevation", "side_ortho", "profile_blueprint")):
        view = "ortho_side"
    elif any(k in low for k in ("blueprint", "ortho", "elevation")):
        view = "ortho_side"
    elif "side" in low or "profile" in low:
        view = "ortho_side"
    elif "front" in low:
        view = "ortho_front"
    elif "top" in low:
        view = "ortho_top"
    else:
        # Default real photos, pasted screenshots, and multi-angle captures to perspective!
        view = "hero"

    if ep in ("perspective", "ortho_blueprint"):
        proj = ep
    elif ep == "ortho":
        proj = "ortho_blueprint"
    elif view in ORTHO_VIEWS:
        proj = "ortho_blueprint"
    else:
        proj = "perspective"

    return view, proj


def default_camera_for_reference(view: str, projection: str, lens_mm: float | None = None) -> dict[str, Any]:
    """Return default camera specification for a reference image."""
    if projection == "ortho_blueprint":
        axis_map = {
            "ortho_front": "front",
            "front": "front",
            "ortho_back": "back",
            "back": "back",
            "ortho_top": "top",
            "top": "top",
            "ortho_side": "side",
            "side": "side",
        }
        return {"type": "ORTHO", "ortho_axis": axis_map.get(view, "side")}

    preset = dict(DEFAULT_CAMERA_PRESETS.get(view, DEFAULT_CAMERA_PRESETS["hero"]))
    preset["type"] = "PERSP"
    if lens_mm is not None and lens_mm > 0:
        preset["lens_mm"] = round(float(lens_mm), 1)
    return preset


def analyze_reference_image(
    img_path: str | Path,
    *,
    view: str = "auto",
    projection: str = "auto",
    lens_mm: float | None = None,
    camera: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract dimensions, foreground aspect ratio, dominant hex palette, and perspective/ortho camera metadata."""
    p = Path(img_path)
    with Image.open(p) as im:
        rgba = im.convert("RGBA")
        w, h = rgba.size
        arr = np.asarray(rgba, dtype=np.uint8)

    alpha = arr[..., 3]
    rgb = arr[..., :3].astype(np.float32)
    if np.min(alpha) < 240 and np.any(alpha > 32):
        fg_mask = alpha > 32
    else:
        corners = np.vstack([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
        bg_med = np.median(corners, axis=0)
        dist = np.linalg.norm(rgb - bg_med[None, None, :], axis=-1)
        fg_mask = dist > 24.0

    ys, xs = np.where(fg_mask)
    if len(xs) > 50 and len(ys) > 50:
        subj_w = int(xs.max() - xs.min() + 1)
        subj_h = int(ys.max() - ys.min() + 1)
        subj_aspect = round(subj_w / max(subj_h, 1), 3)
        fg_pixels = arr[fg_mask][:, :3]
    else:
        subj_w, subj_h = w, h
        subj_aspect = round(w / max(h, 1), 3)
        fg_pixels = arr.reshape(-1, 4)[:, :3]

    small = Image.fromarray(fg_pixels.reshape(-1, 1, 3).astype(np.uint8)).quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    pal = small.getpalette() or []
    scored_clusters: list[tuple[float, str]] = []
    for cnt, idx in (small.getcolors() or []):
        base = idx * 3
        if base + 2 < len(pal):
            r_c, g_c, b_c = pal[base], pal[base + 1], pal[base + 2]
            c_max = max(r_c, g_c, b_c)
            c_min = min(r_c, g_c, b_c)
            sat = (c_max - c_min) / max(c_max, 1)
            weight = 0.08 if sat < 0.12 else (0.45 + sat * 2.4)
            scored_clusters.append((float(cnt) * weight, f"#{r_c:02X}{g_c:02X}{b_c:02X}"))
    scored_clusters.sort(key=lambda item: item[0], reverse=True)
    hex_colors: list[str] = []
    for _score, hx in scored_clusters:
        if hx not in hex_colors:
            hex_colors.append(hx)
        if len(hex_colors) >= 5:
            break

    if not hex_colors:
        hex_colors = ["#12687A", "#E8B914", "#EEF2EB", "#1E293B"]

    resolved_view, resolved_proj = classify_reference_view(p.name, explicit_view=view, explicit_projection=projection)
    cam_spec = default_camera_for_reference(resolved_view, resolved_proj, lens_mm=lens_mm)
    if isinstance(camera, dict):
        cam_spec.update({k: v for k, v in camera.items() if v is not None})

    return {
        "filename": p.name,
        "path": str(p.resolve()),
        "view": resolved_view,
        "projection": resolved_proj,
        "camera": cam_spec,
        "width_px": w,
        "height_px": h,
        "subject_aspect_w_over_h": subj_aspect,
        "dominant_palette": hex_colors,
    }


def save_uploaded_reference(
    asset_dir: Path,
    filename: str,
    data_url_or_bytes: str | bytes,
    *,
    view: str = "auto",
    projection: str = "auto",
    lens_mm: float | None = None,
    camera: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a base64 data-URL or raw bytes into `<asset_dir>/references/` and analyze it."""
    ref_dir = asset_dir / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", os.path.basename(filename)) or "reference.png"
    if view != "auto" and view not in safe_name.lower():
        stem, ext = os.path.splitext(safe_name)
        safe_name = f"ref_{view}_{stem}{ext or '.png'}"

    dst = ref_dir / safe_name
    if isinstance(data_url_or_bytes, str):
        raw_b64 = data_url_or_bytes.split(",", 1)[-1] if "," in data_url_or_bytes else data_url_or_bytes
        raw = base64.b64decode(raw_b64)
    else:
        raw = data_url_or_bytes

    dst.write_bytes(raw)
    with Image.open(dst) as im:
        if dst.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            png_dst = dst.with_suffix(".png")
            im.convert("RGBA").save(png_dst, format="PNG")
            dst.unlink(missing_ok=True)
            dst = png_dst

    return analyze_reference_image(dst, view=view, projection=projection, lens_mm=lens_mm, camera=camera)


def stage_local_reference_files(
    asset_dir: Path,
    file_paths: list[str],
    *,
    view: str = "auto",
    projection: str = "auto",
    lens_mm: float | None = None,
) -> list[dict[str, Any]]:
    """Copy local reference image files into `<asset_dir>/references/` and analyze them."""
    ref_dir = asset_dir / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for fp in file_paths:
        src = Path(fp)
        if not src.is_file():
            continue
        dst = ref_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        results.append(analyze_reference_image(dst, view=view, projection=projection, lens_mm=lens_mm))
    return results


def sync_references_into_spec(asset_dir: Path, added_refs: list[dict[str, Any]]) -> Path | None:
    """Append newly staged references into `<asset_dir>/asset_spec.json` if it exists."""
    spec_path = asset_dir / "asset_spec.json"
    if not spec_path.is_file():
        return None
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None

    existing = list(spec.get("references") or [])
    by_path = {str(r.get("path", "")).lower(): idx for idx, r in enumerate(existing)}
    for r in added_refs:
        key = str(r.get("path", "")).lower()
        if key in by_path:
            existing[by_path[key]] = r
        else:
            existing.append(r)

    merged_palette: list[str] = list(spec.get("extracted_palette") or [])
    for r in existing:
        for hx in r.get("dominant_palette", []):
            if hx not in merged_palette:
                merged_palette.append(hx)

    spec["references"] = existing
    spec["extracted_palette"] = merged_palette[:6] or ["#0E7490", "#EAB308", "#F1F5F9", "#1E293B"]
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec_path


def write_asset_spec(
    asset_dir: Path,
    *,
    slug: str,
    title: str,
    kind: str,
    prompt: str,
    length_m: float = 1.20,
    profile: str = "auto",
    bake_res: int = 2048,
    variants_count: int = 4,
    rate_to_ten: bool | None = None,
    high_poly_uncapped: bool = False,
    references: list[dict[str, Any]] | None = None,
    ortho_blueprint_grid: bool = False,
    review_loop: dict[str, Any] | None = None,
) -> Path:
    """Write `<asset_dir>/asset_spec.json` — the single source of truth read by Velum Forge & AI agents."""
    hp_on = bool(high_poly_uncapped)
    if profile == "auto":
        resolved_profile = "game" if (hp_on or kind in ("building", "arch")) else "roblox"
    else:
        resolved_profile = profile
    qa_max_tris = 0 if hp_on else 300000
    refs = [dict(r) for r in (references or [])]
    # Spread default azimuths automatically when multiple perspective photos share the same default angle
    spread_az = [32.0, 0.0, -32.0, 145.0, -145.0, 62.0, -62.0, 180.0]
    seen_persp = 0
    for r in refs:
        if r.get("projection") == "perspective":
            cam = dict(r.get("camera") or {})
            if "location" not in cam and not cam.get("custom_azimuth"):
                if seen_persp > 0:
                    cam["azimuth_deg"] = spread_az[seen_persp % len(spread_az)]
                    r["camera"] = cam
            seen_persp += 1
    merged_palette: list[str] = []
    for r in refs:
        for hx in r.get("dominant_palette", []):
            if hx not in merged_palette:
                merged_palette.append(hx)

    has_ortho = any(r.get("projection") == "ortho_blueprint" for r in refs)
    raw_review = dict(review_loop) if isinstance(review_loop, dict) else {}
    if rate_to_ten is True and raw_review.get("enabled") is not False:
        raw_review.setdefault("enabled", True)
    review_cfg = normalize_review_config(raw_review or None)

    qa_cmd = f'vforge qa "{asset_dir / f"build_{slug}.py"}" --profile {resolved_profile}'
    if hp_on:
        qa_cmd += " --high-poly --max-tris 0"
    elif resolved_profile == "game":
        qa_cmd += " --max-tris 300000"
    qa_cmd += " --forward-axis +Y"
    if ortho_blueprint_grid and has_ortho:
        qa_cmd += " --ortho-grid"
    if review_cfg["enabled"]:
        qa_cmd += " --snapshot-iteration"

    spec = {
        "schema": "velum-forge/asset-spec/v2",
        "slug": slug,
        "title": title,
        "kind": kind,
        "prompt": prompt,
        "target_length_m": float(length_m),
        "qa_profile": resolved_profile,
        "high_poly_uncapped": hp_on,
        "qa_max_tris": qa_max_tris,
        "bake_res": int(bake_res),
        "variants_count": int(variants_count),
        "ortho_blueprint_grid": bool(ortho_blueprint_grid and has_ortho),
        "rate_to_ten": bool(review_cfg["enabled"] or (rate_to_ten is True)),
        "review_loop": review_cfg,
        "extracted_palette": merged_palette[:6] or ["#0E7490", "#EAB308", "#F1F5F9", "#1E293B"],
        "references": refs,
        "workflow_commands": {
            "qa": qa_cmd,
            "bake": f'vforge bake "{asset_dir / "bake_lod_variants.py"}"',
            "review_status": f'vforge review status "{asset_dir}"',
            "review_prompt": f'vforge review prompt "{asset_dir}"',
        },
    }
    spec_path = asset_dir / "asset_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec_path
