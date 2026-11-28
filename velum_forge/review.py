"""Optional Iterative Visual Critic & Honest Rating Review Engine (`velum_forge.review`).

Provides an opt-in, configurable critique loop for any Velum Forge asset:
- Stores configuration in `<asset_dir>/asset_spec.json` (`review_loop.enabled`: True/False).
- Archives per-iteration renders & `qa_report.json` under `<asset_dir>/reviews/iter_XX/`.
- Records brutally honest 0.0-10.0 ratings, rubric breakdowns, strengths, and categorized defects
  in `<asset_dir>/reviews/review_history.json` + `<asset_dir>/reviews/REVIEW_LOG.md`.
- Enforces objective QA gate caps (e.g. cannot claim >= 9.0/10 while `qa_report.json` has errors).
- Composes `<asset_dir>/reviews/iteration_progression.png` showing visual + rating evolution.
- Generates focused next-iteration critique prompts targeting unresolved defects.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

DEFAULT_RUBRIC_WEIGHTS: dict[str, float] = {
    "silhouette_proportions": 0.20,
    "reference_fidelity": 0.25,
    "detail_craft": 0.20,
    "materials_lighting": 0.15,
    "geometric_qa": 0.10,
    "scene_continuity": 0.10,
}

RUBRIC_LABELS: dict[str, str] = {
    "silhouette_proportions": "Silhouette, Massing & Real-World Scale",
    "reference_fidelity": "Reference Fidelity (Matched Angles & Proportions)",
    "detail_craft": "Secondary Detail Craft (Hardware, Trim, Foliage/Anatomy)",
    "materials_lighting": "Materials, PBR Realism & Legible Signage",
    "geometric_qa": "Geometric QA Gate (Normals, Contacts, UVs, Budgets)",
    "scene_continuity": "Grounding, Seam Transitions & Edge Clearance",
}

DEFAULT_REVIEW_CONFIG: dict[str, Any] = {
    "enabled": False,
    "target_score": 10.0,
    "max_iterations": 0,
    "require_zero_qa_errors": True,
    "require_zero_qa_warnings": True,
    "strict_ten": True,
    "focus_notes": "",
    "rubric_weights": dict(DEFAULT_RUBRIC_WEIGHTS),
}

# Palette for Pillow visual progression sheet
_BG = (15, 20, 30)
_CARD = (23, 31, 46)
_HEADER = (28, 37, 54)
_BORDER = (52, 65, 88)
_TEXT = (241, 245, 249)
_MUTED = (148, 163, 184)
_GREEN = (34, 197, 94)
_AMBER = (245, 158, 11)
_RED = (239, 68, 68)
_CYAN = (34, 211, 238)
_INK = (11, 18, 32)


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
    return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def normalize_review_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a clean, validated review loop configuration dict (rating target locked at 10.0/10)."""
    cfg = copy.deepcopy(DEFAULT_REVIEW_CONFIG)
    if isinstance(raw, dict):
        if "enabled" in raw:
            cfg["enabled"] = bool(raw["enabled"])
        if "max_iterations" in raw and raw["max_iterations"] is not None:
            cfg["max_iterations"] = max(0, min(50, int(raw["max_iterations"])))
        if "require_zero_qa_errors" in raw:
            cfg["require_zero_qa_errors"] = bool(raw["require_zero_qa_errors"])
        if "require_zero_qa_warnings" in raw:
            cfg["require_zero_qa_warnings"] = bool(raw["require_zero_qa_warnings"])
        if "focus_notes" in raw and raw["focus_notes"] is not None:
            cfg["focus_notes"] = str(raw["focus_notes"]).strip()
        if isinstance(raw.get("rubric_weights"), dict):
            weights = {}
            for k, default_w in DEFAULT_RUBRIC_WEIGHTS.items():
                try:
                    weights[k] = max(0.0, float(raw["rubric_weights"].get(k, default_w)))
                except (TypeError, ValueError):
                    weights[k] = default_w
            total_w = sum(weights.values())
            if total_w > 0:
                cfg["rubric_weights"] = {k: round(v / total_w, 4) for k, v in weights.items()}
    # Strict Always-10/10 rule: never approve or settle for any score below 10.0 / 10
    cfg["target_score"] = 10.0
    cfg["strict_ten"] = True
    return cfg


def get_review_config(asset_dir: str | Path) -> dict[str, Any]:
    """Read `review_loop` configuration from `<asset_dir>/asset_spec.json`."""
    ad = Path(asset_dir).resolve()
    spec = _load_json(ad / "asset_spec.json")
    return normalize_review_config(spec.get("review_loop"))


def set_review_config(
    asset_dir: str | Path,
    *,
    enabled: bool | None = None,
    target_score: float | None = None,
    max_iterations: int | None = None,
    require_zero_qa_errors: bool | None = None,
    require_zero_qa_warnings: bool | None = None,
    strict_ten: bool | None = None,
    focus_notes: str | None = None,
    high_poly_uncapped: bool | None = None,
) -> dict[str, Any]:
    """Update and persist `review_loop` (locked 10.0/10 target) & optional `high_poly_uncapped` in `asset_spec.json`."""
    ad = Path(asset_dir).resolve()
    ad.mkdir(parents=True, exist_ok=True)
    spec_path = ad / "asset_spec.json"
    spec = _load_json(spec_path)
    if not spec:
        slug = ad.name
        spec = {
            "schema": "velum-forge/asset-spec/v2",
            "slug": slug,
            "title": slug.replace("_", " ").title(),
            "kind": "prop",
            "prompt": slug.replace("_", " ").title(),
            "target_length_m": 1.2,
            "qa_profile": "roblox",
            "high_poly_uncapped": False,
            "qa_max_tris": 300000,
            "ortho_blueprint_grid": False,
            "references": [],
        }

    cfg = normalize_review_config(spec.get("review_loop"))
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    elif strict_ten is True:
        cfg["enabled"] = True
    if max_iterations is not None:
        cfg["max_iterations"] = max(0, min(50, int(max_iterations)))
    if require_zero_qa_errors is not None:
        cfg["require_zero_qa_errors"] = bool(require_zero_qa_errors)
    if require_zero_qa_warnings is not None:
        cfg["require_zero_qa_warnings"] = bool(require_zero_qa_warnings)
    if focus_notes is not None:
        cfg["focus_notes"] = str(focus_notes).strip()

    # Always keep target locked at 10.0 / 10 regardless of caller override
    cfg["target_score"] = 10.0
    cfg["strict_ten"] = True

    if high_poly_uncapped is not None:
        hp = bool(high_poly_uncapped)
        spec["high_poly_uncapped"] = hp
        spec["qa_max_tris"] = 0 if hp else 300000
        if hp:
            spec["qa_profile"] = "game"
        elif spec.get("kind") not in ("building", "arch") and spec.get("qa_profile") == "game":
            spec["qa_profile"] = "roblox"
        slug = spec.get("slug") or ad.name
        qa_prof = spec.get("qa_profile", "game" if hp else "roblox")
        qa_cmd = f'vforge qa "{ad / f"build_{slug}.py"}" --profile {qa_prof}'
        if hp:
            qa_cmd += " --high-poly --max-tris 0"
        elif qa_prof == "game":
            qa_cmd += " --max-tris 300000"
        qa_cmd += " --forward-axis +Y"
        if cfg["enabled"]:
            qa_cmd += " --snapshot-iteration"
        wf = dict(spec.get("workflow_commands") or {})
        wf["qa"] = qa_cmd
        spec["workflow_commands"] = wf

    spec["review_loop"] = cfg
    spec["rate_to_ten"] = bool(cfg["enabled"])
    _write_json(spec_path, spec)
    return cfg


def find_latest_qa_report(asset_dir: str | Path) -> Path | None:
    """Locate the freshest `qa_report.json` for `asset_dir` (in `renders/`, asset root, or `.qa-out/`)."""
    ad = Path(asset_dir).resolve()
    candidates: list[Path] = []
    for p in (ad / "renders" / "qa_report.json", ad / "qa_report.json"):
        if p.is_file():
            candidates.append(p)

    # Search workspace `.qa-out/` matching build script stem or asset folder name
    stems = {ad.name, f"build_{ad.name}"}
    for pyf in ad.glob("build_*.py"):
        stems.add(pyf.stem)

    search_roots = [ad.parent.parent / ".qa-out", ad.parent / ".qa-out"]
    from . import REPO_ROOT

    search_roots.append(REPO_ROOT / ".qa-out")
    for qa_root in search_roots:
        if not qa_root.is_dir():
            continue
        for stem in stems:
            cand = qa_root / stem / "qa_report.json"
            if cand.is_file():
                candidates.append(cand)

    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def score_qa_report(qa: dict[str, Any] | None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute an objective 0-10 geometric QA subscore and hard rating cap from `qa_report.json`."""
    c = normalize_review_config(cfg)
    if not qa:
        return {
            "available": False,
            "pass": None,
            "errors_count": 0,
            "warnings_count": 0,
            "total_tris": 0,
            "qa_score": 7.0,
            "rating_cap": 10.0,
            "cap_reason": "",
            "errors": [],
            "warnings": [],
        }

    errors = list(qa.get("errors") or [])
    warnings = list(qa.get("warnings") or [])
    err_n = len(errors)
    warn_n = len(warnings)
    passed = bool(qa.get("pass", err_n == 0)) and err_n == 0

    # Objective geometric QA subscore
    score = 10.0 - err_n * 2.0 - warn_n * 0.45
    score = round(max(1.0, min(10.0, score)), 1)

    rating_cap = 10.0
    cap_reason = ""
    if err_n > 0 and c["require_zero_qa_errors"]:
        rating_cap = min(rating_cap, 7.9)
        cap_reason = f"Capped at 7.9/10 because qa_report.json has {err_n} error(s)."
    elif warn_n > 0 and c["require_zero_qa_warnings"]:
        rating_cap = min(rating_cap, 8.9)
        cap_reason = f"Capped at 8.9/10 because qa_report.json has {warn_n} warning(s)."

    return {
        "available": True,
        "pass": passed,
        "errors_count": err_n,
        "warnings_count": warn_n,
        "total_tris": int(qa.get("total_tris") or 0),
        "ground_z": qa.get("ground_z"),
        "size_m": qa.get("size_m"),
        "qa_score": score,
        "rating_cap": rating_cap,
        "cap_reason": cap_reason,
        "errors": errors[:12],
        "warnings": warnings[:12],
    }


def load_review_history(asset_dir: str | Path) -> dict[str, Any]:
    """Load `<asset_dir>/reviews/review_history.json` (returning an empty structured history if absent)."""
    ad = Path(asset_dir).resolve()
    cfg = get_review_config(ad)
    hist_path = ad / "reviews" / "review_history.json"
    data = _load_json(hist_path)
    if not data:
        spec = _load_json(ad / "asset_spec.json")
        return {
            "schema": "velum-forge/review-history/v1",
            "asset_slug": spec.get("slug") or ad.name,
            "asset_title": spec.get("title") or ad.name.replace("_", " ").title(),
            "config": cfg,
            "iterations": [],
            "latest_rating": None,
            "best_rating": None,
            "status": "NOT_STARTED",
            "progression_sheet": None,
        }
    data["config"] = cfg
    return data


def snapshot_iteration_renders(asset_dir: str | Path, iteration: int | None = None) -> dict[str, Any]:
    """Archive current `renders/*.png` and `qa_report.json` into `<asset_dir>/reviews/iter_XX/`."""
    ad = Path(asset_dir).resolve()
    hist = load_review_history(ad)
    if iteration is None:
        existing_iters = [int(it.get("iteration", 0)) for it in hist.get("iterations", [])]
        next_iter = (max(existing_iters) + 1) if existing_iters else 1
        # If iter_XX already exists without being logged yet, reuse that folder cleanly
        iter_num = next_iter
    else:
        iter_num = max(1, int(iteration))

    snap_dir = ad / "reviews" / f"iter_{iter_num:02d}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    copied_images: list[str] = []
    renders_dir = ad / "renders"
    if renders_dir.is_dir():
        for png in sorted(renders_dir.glob("*.png")):
            dst = snap_dir / png.name
            shutil.copy2(png, dst)
            copied_images.append(str(dst.resolve()))

    # Also capture previews if renders/ was empty
    if not copied_images and (ad / "previews").is_dir():
        for png in sorted((ad / "previews").glob("*.png")):
            dst = snap_dir / png.name
            shutil.copy2(png, dst)
            copied_images.append(str(dst.resolve()))

    qa_src = find_latest_qa_report(ad)
    qa_dst_str = None
    if qa_src and qa_src.is_file():
        qa_dst = snap_dir / "qa_report.json"
        shutil.copy2(qa_src, qa_dst)
        qa_dst_str = str(qa_dst.resolve())

        # Also copy contact sheets from `.qa-out` if they weren't in `renders/`
        for name_src, name_dst in (
            ("contact_sheet_material.png", "qa_contact_material.png"),
            ("contact_sheet_diagnostic.png", "qa_contact_diagnostic.png"),
            ("ref_comparison.png", "ref_comparison.png"),
        ):
            src_img = qa_src.parent / name_src
            dst_img = snap_dir / name_dst
            if src_img.is_file() and not dst_img.is_file():
                shutil.copy2(src_img, dst_img)
                copied_images.append(str(dst_img.resolve()))

    # Pick the best representative thumbnail for this iteration
    primary_thumb = None
    for preferred in ("ref_comparison.png", "qa_contact_material.png", "variants_lineup.png", "baked_closeup.png"):
        cand = snap_dir / preferred
        if cand.is_file():
            primary_thumb = str(cand.resolve())
            break
    if not primary_thumb and copied_images:
        primary_thumb = copied_images[0]

    return {
        "iteration": iter_num,
        "snapshot_dir": str(snap_dir.resolve()),
        "images": sorted(set(copied_images)),
        "primary_image": primary_thumb,
        "qa_report": qa_dst_str,
    }


def parse_defect_spec(raw: str | dict[str, Any]) -> dict[str, str]:
    """Parse either a dict defect or `'Category|severity|Description|Fix'` pipe-delimited string."""
    if isinstance(raw, dict):
        sev = str(raw.get("severity") or "major").lower().strip()
        if sev not in ("critical", "major", "minor"):
            sev = "major"
        return {
            "category": str(raw.get("category") or "General").strip() or "General",
            "severity": sev,
            "description": str(raw.get("description") or "").strip(),
            "fix_action": str(raw.get("fix_action") or "").strip(),
        }

    parts = [p.strip() for p in str(raw).split("|")]
    if len(parts) >= 4:
        cat, sev, desc, fix = parts[0], parts[1].lower(), parts[2], parts[3]
    elif len(parts) == 3:
        cat, sev, desc, fix = parts[0], parts[1].lower(), parts[2], ""
    elif len(parts) == 2:
        cat, sev, desc, fix = parts[0], "major", parts[1], ""
    else:
        cat, sev, desc, fix = "General", "major", parts[0], ""
    if sev not in ("critical", "major", "minor"):
        sev = "major"
    return {"category": cat or "General", "severity": sev, "description": desc, "fix_action": fix}


def format_iteration_markdown(entry: dict[str, Any], target_score: float = 10.0) -> str:
    """Format an iteration review in crisp, honest, scannable markdown."""
    it_num = entry.get("iteration", 1)
    rating = float(entry.get("honest_rating", 0.0))
    delta = entry.get("delta_from_previous")
    delta_txt = f" ({delta:+.1f} from Iteration {it_num - 1})" if isinstance(delta, (int, float)) else ""

    lines = [f"### Iteration {it_num} Review — Honest Rating: {rating:.1f} / 10{delta_txt}", ""]

    summary = str(entry.get("summary") or "").strip()
    strengths = [str(s).strip() for s in (entry.get("strengths") or []) if str(s).strip()]
    defects = [parse_defect_spec(d) for d in (entry.get("defects") or [])]
    qa_snap = entry.get("qa_snapshot") or {}

    if summary:
        lines.append(summary)
        lines.append("")

    if strengths:
        lines.append("**What Improved / Strengths:**")
        for s in strengths:
            lines.append(f"- {s}")
        lines.append("")

    if defects:
        lead = (
            f"**Defects Holding It Back from {target_score:.1f}/10:**"
            if rating < target_score
            else "**Minor Notes / Polish Opportunities:**"
        )
        lines.append(lead)
        for d in defects:
            sev = d["severity"].upper()
            fix_s = f" -> *Fix:* {d['fix_action']}" if d["fix_action"] else ""
            lines.append(f"- **[{sev}] {d['category']}**: {d['description']}{fix_s}")
        lines.append("")

    if qa_snap.get("available"):
        badge = "PASS" if qa_snap.get("pass") else "FAIL"
        lines.append(
            f"- **Geometric QA Gate (`qa_report.json`)**: `{badge}` "
            f"(Errors: `{qa_snap.get('errors_count', 0)}`, Warnings: `{qa_snap.get('warnings_count', 0)}`, "
            f"Tris: `{qa_snap.get('total_tris', 0):,}`)"
        )
        if entry.get("cap_reason"):
            lines.append(f"  - *{entry['cap_reason']}*")
        lines.append("")

    rubric = entry.get("rubric_scores") or {}
    if rubric:
        rubric_parts = [f"{k.replace('_', ' ').title()}: `{float(v):.1f}`" for k, v in rubric.items()]
        lines.append("**Rubric Breakdown:** " + " | ".join(rubric_parts))
        lines.append("")

    lines.append(f"**Verdict:** `{entry.get('verdict', 'ITERATE')}` (Target: `{target_score:.1f} / 10`)")
    return "\n".join(lines).strip() + "\n"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["arialbd.ttf", "segoeuib.ttf", "consolab.ttf"]
        if bold
        else ["arial.ttf", "segoeui.ttf", "consola.ttf"]
    )
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in candidates:
        p = fonts_dir / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_image(im: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = im.size
    scale = min(target_w / max(src_w, 1), target_h / max(src_h, 1))
    nw = max(1, int(round(src_w * scale)))
    nh = max(1, int(round(src_h * scale)))
    resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), (12, 16, 25))
    canvas.paste(resized, ((target_w - nw) // 2, (target_h - nh) // 2))
    return canvas


def compose_iteration_progression_sheet(asset_dir: str | Path) -> str | None:
    """Compose `<asset_dir>/reviews/iteration_progression.png` comparing all logged iterations."""
    ad = Path(asset_dir).resolve()
    hist = load_review_history(ad)
    iters = hist.get("iterations") or []
    if not iters:
        return None

    cfg = hist.get("config") or DEFAULT_REVIEW_CONFIG
    target = 10.0
    title = hist.get("asset_title") or ad.name

    shown = iters[-4:]  # Show up to 4 most recent iterations cleanly side-by-side
    cols = len(shown)
    tile_w, tile_h = 540, 340
    header_h = 80
    card_top_h = 58
    card_bot_h = 112
    pad = 18
    gap = 16

    card_w = tile_w
    card_h = card_top_h + tile_h + card_bot_h
    canvas_w = pad * 2 + cols * card_w + (cols - 1) * gap
    canvas_h = header_h + pad * 2 + card_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), _BG)
    draw = ImageDraw.Draw(canvas)

    f_title = _load_font(22, bold=True)
    f_sub = _load_font(14, bold=False)
    f_card = _load_font(17, bold=True)
    f_pill = _load_font(16, bold=True)
    f_small = _load_font(13, bold=False)

    # Top header
    draw.rectangle([0, 0, canvas_w, header_h], fill=_HEADER)
    draw.line([(0, header_h - 1), (canvas_w, header_h - 1)], fill=_BORDER, width=2)
    draw.text((pad, 14), f"{title}  |  ITERATION PROGRESSION & HONEST RATINGS", fill=_TEXT, font=f_title)
    scores_trail = "  ->  ".join(f"Iter {it['iteration']}: {float(it['honest_rating']):.1f}/10" for it in iters)
    draw.text(
        (pad, 47),
        f"Target: {target:.1f} / 10 (Strict)   |   Status: {hist.get('status', 'IN_PROGRESS')}   |   Trajectory: {scores_trail}",
        fill=_MUTED,
        font=f_sub,
    )

    for idx, it in enumerate(shown):
        x0 = pad + idx * (card_w + gap)
        y0 = header_h + pad
        rating = float(it.get("honest_rating", 0.0))
        delta = it.get("delta_from_previous")
        qa_snap = it.get("qa_snapshot") or {}
        defects = it.get("defects") or []

        draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=10, fill=_CARD, outline=_BORDER, width=2)

        # Card header bar
        pill_col = _GREEN if rating >= target else (_AMBER if rating >= 7.0 else _RED)
        draw.text((x0 + 14, y0 + 12), f"ITERATION {it['iteration']}", fill=_CYAN, font=f_card)
        if isinstance(delta, (int, float)):
            d_col = _GREEN if delta >= 0 else _RED
            draw.text((x0 + 14, y0 + 35), f"{delta:+.1f} vs previous", fill=d_col, font=f_small)
        else:
            draw.text((x0 + 14, y0 + 35), "Baseline pass", fill=_MUTED, font=f_small)

        # Score pill
        score_txt = f"{rating:.1f} / 10"
        sw, sh = _text_size(draw, score_txt, f_pill)
        pw = sw + 24
        ph = 32
        px0 = x0 + card_w - pw - 12
        py0 = y0 + 13
        draw.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=8, fill=pill_col)
        draw.text((px0 + 12, py0 + (ph - sh) // 2 - 1), score_txt, fill=_INK, font=f_pill)

        # Image tile
        img_path = it.get("primary_image") or ""
        if img_path and os.path.isfile(img_path):
            with Image.open(img_path) as im:
                tile = _fit_image(im.convert("RGB"), tile_w - 4, tile_h)
            canvas.paste(tile, (x0 + 2, y0 + card_top_h))
        else:
            draw.rectangle([x0 + 2, y0 + card_top_h, x0 + card_w - 2, y0 + card_top_h + tile_h], fill=(12, 16, 25))
            msg = "No render snapshot archived"
            mw, mh = _text_size(draw, msg, f_sub)
            draw.text((x0 + (card_w - mw) // 2, y0 + card_top_h + (tile_h - mh) // 2), msg, fill=_MUTED, font=f_sub)

        # Card footer: QA summary + top defects
        fy = y0 + card_top_h + tile_h + 10
        if qa_snap.get("available"):
            qa_lbl = f"QA: {'PASS' if qa_snap.get('pass') else 'FAIL'} ({qa_snap.get('errors_count', 0)}E / {qa_snap.get('warnings_count', 0)}W)"
            qa_col = _GREEN if (qa_snap.get("pass") and qa_snap.get("warnings_count", 0) == 0) else (_AMBER if qa_snap.get("pass") else _RED)
        else:
            qa_lbl = "QA: Not recorded"
            qa_col = _MUTED
        draw.text((x0 + 14, fy), f"{qa_lbl}   |   Defects: {len(defects)}   |   {it.get('verdict', '')}", fill=qa_col, font=f_small)

        for d_idx, d_item in enumerate(defects[:3]):
            d = parse_defect_spec(d_item)
            line = f"• [{d['severity'].upper()}] {d['category']}: {d['description']}"
            if len(line) > 76:
                line = line[:73] + "..."
            draw.text((x0 + 14, fy + 22 + d_idx * 22), line, fill=_TEXT, font=f_small)
        if not defects:
            draw.text((x0 + 14, fy + 26), "• No defects flagged on this iteration.", fill=_GREEN, font=f_small)

    out_path = ad / "reviews" / "iteration_progression.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG")
    # Also mirror into renders/ so Showroom thumbnail strip shows it automatically
    renders_copy = ad / "renders" / "iteration_progression.png"
    if (ad / "renders").is_dir():
        shutil.copy2(out_path, renders_copy)
    return str(out_path.resolve())


def record_iteration_review(
    asset_dir: str | Path,
    *,
    honest_rating: float | None = None,
    rubric_scores: dict[str, float] | None = None,
    summary: str = "",
    strengths: list[str] | None = None,
    defects: list[str | dict[str, Any]] | None = None,
    renders_inspected: list[str] | None = None,
    qa_report_path: str | Path | None = None,
    snapshot_renders: bool = True,
    iteration: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Record an honest structured review for an iteration, update logs, and render progression sheet."""
    ad = Path(asset_dir).resolve()
    cfg = get_review_config(ad)
    hist = load_review_history(ad)
    existing = list(hist.get("iterations") or [])

    if iteration is None:
        it_num = (max(int(x.get("iteration", 0)) for x in existing) + 1) if existing else 1
    else:
        it_num = max(1, int(iteration))

    snap = snapshot_iteration_renders(ad, iteration=it_num) if snapshot_renders else {
        "iteration": it_num,
        "snapshot_dir": str((ad / "reviews" / f"iter_{it_num:02d}").resolve()),
        "images": [],
        "primary_image": None,
        "qa_report": None,
    }

    # Load QA report
    qa_file = Path(qa_report_path) if qa_report_path else (Path(snap["qa_report"]) if snap.get("qa_report") else find_latest_qa_report(ad))
    qa_data = _load_json(qa_file) if (qa_file and qa_file.is_file()) else None
    qa_snap = score_qa_report(qa_data, cfg)

    # Normalize rubric scores & compute rating
    clean_rubric: dict[str, float] = {}
    if isinstance(rubric_scores, dict) and rubric_scores:
        for k in DEFAULT_RUBRIC_WEIGHTS:
            if k in rubric_scores and rubric_scores[k] is not None:
                clean_rubric[k] = round(max(0.0, min(10.0, float(rubric_scores[k]))), 1)
    if qa_snap["available"] and "geometric_qa" not in clean_rubric:
        clean_rubric["geometric_qa"] = qa_snap["qa_score"]

    if honest_rating is not None:
        raw_rating = round(max(0.0, min(10.0, float(honest_rating))), 1)
    elif clean_rubric:
        weights = cfg.get("rubric_weights") or DEFAULT_RUBRIC_WEIGHTS
        num = sum(clean_rubric[k] * weights.get(k, 0.1) for k in clean_rubric)
        den = sum(weights.get(k, 0.1) for k in clean_rubric)
        raw_rating = round(num / max(den, 1e-6), 1)
    else:
        raw_rating = qa_snap["qa_score"]

    parsed_defects = [parse_defect_spec(d) for d in (defects or []) if d]
    clean_strengths = [str(s).strip() for s in (strengths or []) if str(s).strip()]

    # Apply objective QA gate cap + unresolved-defect cap so broken or flawed builds never claim 10/10
    final_rating = min(raw_rating, qa_snap["rating_cap"])
    cap_reason = qa_snap["cap_reason"] if final_rating < raw_rating else ""
    if parsed_defects and final_rating >= 10.0:
        final_rating = 9.5
        d_msg = "Capped at 9.5/10 because unresolved defect(s) remain — fix all defects before approving 10.0/10."
        cap_reason = f"{cap_reason} {d_msg}".strip()

    prev_entries = [x for x in existing if int(x.get("iteration", 0)) < it_num]
    prev_rating = float(prev_entries[-1]["honest_rating"]) if prev_entries else None
    delta = round(final_rating - prev_rating, 1) if prev_rating is not None else None

    target = 10.0
    max_iters = int(cfg.get("max_iterations", 0))
    qa_ok = (
        (not qa_snap["available"])
        or (
            (qa_snap["errors_count"] == 0 or not cfg["require_zero_qa_errors"])
            and (qa_snap["warnings_count"] == 0 or not cfg["require_zero_qa_warnings"])
        )
    )

    if final_rating >= 10.0 and qa_ok and len(parsed_defects) == 0:
        verdict = "APPROVED"
    else:
        verdict = "ITERATE"

    entry: dict[str, Any] = {
        "iteration": it_num,
        "timestamp": _utc_now_iso(),
        "honest_rating": final_rating,
        "raw_rating": raw_rating,
        "cap_reason": cap_reason,
        "delta_from_previous": delta,
        "target_score": target,
        "verdict": verdict,
        "summary": str(summary or "").strip(),
        "strengths": clean_strengths,
        "defects": parsed_defects,
        "rubric_scores": clean_rubric,
        "qa_snapshot": qa_snap,
        "snapshot_dir": snap["snapshot_dir"],
        "primary_image": snap["primary_image"],
        "renders_inspected": renders_inspected or snap["images"],
        "notes": str(notes or "").strip(),
    }
    entry["markdown"] = format_iteration_markdown(entry, target_score=target)

    # Replace if re-logging same iteration number, otherwise append sorted
    updated = [x for x in existing if int(x.get("iteration", 0)) != it_num]
    updated.append(entry)
    updated.sort(key=lambda x: int(x.get("iteration", 0)))

    reviews_dir = ad / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    _write_json(reviews_dir / f"iteration_{it_num:02d}.json", entry)

    hist["iterations"] = updated
    hist["latest_rating"] = updated[-1]["honest_rating"]
    hist["best_rating"] = max(float(x["honest_rating"]) for x in updated)
    hist["status"] = updated[-1]["verdict"]
    hist["config"] = cfg
    _write_json(reviews_dir / "review_history.json", hist)

    # Write combined human-readable REVIEW_LOG.md
    max_iter_label = "Unlimited until 10.0 / 10" if max_iters <= 0 else str(max_iters)
    md_header = [
        f"# Velum Forge Iterative Review Log — {hist.get('asset_title', ad.name)}",
        "",
        f"- **Iterative Mode Enabled:** `{cfg['enabled']}`",
        f"- **Target Honest Rating:** `{target:.1f} / 10` (Strict — Never Proceed Below 10.0 | Cap: `{max_iter_label}`)",
        f"- **Current Status:** `{hist['status']}` | **Latest Rating:** `{hist['latest_rating']:.1f} / 10` | **Best:** `{hist['best_rating']:.1f} / 10`",
        "",
        "---",
        "",
    ]
    md_body = "\n---\n\n".join(x.get("markdown") or format_iteration_markdown(x, target) for x in updated)
    (reviews_dir / "REVIEW_LOG.md").write_text("\n".join(md_header) + md_body, encoding="utf-8")

    # Compose visual progression contact sheet
    sheet_path = compose_iteration_progression_sheet(ad)
    if sheet_path:
        hist["progression_sheet"] = sheet_path
        _write_json(reviews_dir / "review_history.json", hist)

    return entry


def build_next_iteration_prompt(asset_dir: str | Path) -> str:
    """Build a targeted AI critique & refinement prompt from the latest review + `qa_report.json`."""
    ad = Path(asset_dir).resolve()
    spec = _load_json(ad / "asset_spec.json")
    hist = load_review_history(ad)
    cfg = hist.get("config") or get_review_config(ad)
    iters = hist.get("iterations") or []
    title = spec.get("title") or ad.name.replace("_", " ").title()
    slug = spec.get("slug") or ad.name
    target = 10.0
    hp_on = bool(spec.get("high_poly_uncapped", False))
    qa_profile = "game" if hp_on else str(spec.get("qa_profile", "roblox"))
    qa_flags = f"--profile {qa_profile}"
    if hp_on:
        qa_flags += " --high-poly --max-tris 0"
    elif qa_profile == "game":
        qa_flags += " --max-tris 300000"
    qa_flags += " --forward-axis +Y --snapshot-iteration"

    strict_rule = (
        "\n- **Strict Always-10/10 Rule:** Rate yourself honestly from `0` to `10` until the outcome genuinely becomes a `10 out of 10`. "
        "It should look brilliant. Do not rush, do not fake or inflate the rating, and NEVER stop, approve, or proceed to Stage 5 baking "
        "on any rating below `10.0 / 10` (e.g., `9.0`, `9.5`, or `9.6` must keep iterating!).\n"
    )
    hp_critic_note = (
        "- **High-Poly Uncapped Critic Floor:** NEVER slash radial segments or botanical density to chase a tri limit (`--max-tris 0` is uncapped). "
        "Faceted low-segment cylinders (`<= 10` segs on hero props), sparse stick-like palms, or un-beveled boxy trim are `[MAJOR]` defects blocking `10.0 / 10`.\n"
        if hp_on
        else ""
    )

    if not iters:
        next_it = 1
        return (
            f"Run **Iteration 1 Honest Review** on **{title}** (`{ad}`):\n\n"
            f"1. Visually inspect every rendered image in `{ad / 'renders'}` (especially `ref_comparison.png`, `qa_contact_material.png`, and `qa_contact_diagnostic.png`) directly against all reference photos in `{ad / 'references'}`.\n"
            f"2. Check `qa_report.json` for any floating parts, z-fighting, UV overlaps, inverted normals, or tri budget violations.\n"
            f"3. Give an **honest 0.0-10.0 rating** (no grade inflation — call out primitive blobs, missing trim, clipping, signage issues, or flat materials explicitly).\n"
            f"4. Log the review with:\n"
            f"   `vforge review log \"{ad}\" --score <X.X> --summary \"...\" --strength \"...\" --defect \"Category|major|Defect description|Exact fix\"`\n"
            f"5. Fix every defect and keep iterating until **Honest Rating == 10.0 / 10** and **QA = PASS (0 Errors, 0 Warnings)**.{strict_rule}{hp_critic_note}"
        )

    last = iters[-1]
    next_it = int(last["iteration"]) + 1
    defects = [parse_defect_spec(d) for d in (last.get("defects") or [])]
    defect_lines = "\n".join(
        f"  {i}. **[{d['severity'].upper()}] {d['category']}**: {d['description']}"
        + (f" — *Fix:* {d['fix_action']}" if d["fix_action"] else "")
        for i, d in enumerate(defects, 1)
    ) or "  - (Push silhouette, micro-bevels, interior craft, botanical density & PBR realism to true 10.0 / 10.)"

    qa_snap = last.get("qa_snapshot") or {}
    qa_lines = ""
    if qa_snap.get("errors") or qa_snap.get("warnings"):
        e_txt = "\n".join(f"  - [ERROR] {e}" for e in qa_snap.get("errors", []))
        w_txt = "\n".join(f"  - [WARN]  {w}" for w in qa_snap.get("warnings", []))
        qa_lines = f"\n**Unresolved Geometric QA Gate Items (`qa_report.json`):**\n{e_txt}\n{w_txt}\n"

    focus = f"\n**Additional Review Focus:** {cfg['focus_notes']}\n" if cfg.get("focus_notes") else ""

    return (
        f"Execute **Iteration {next_it} Refinement** for Velum Forge asset **{title}** (`{slug}` in `{ad}`):\n\n"
        f"- **Previous Honest Rating:** `{float(last['honest_rating']):.1f} / 10` (Iteration {last['iteration']})\n"
        f"- **Target Honest Rating:** `{target:.1f} / 10` (Strict — Do Not Proceed Below `10.0 / 10`)\n"
        f"- **Archived Previous Renders:** `{last.get('snapshot_dir', ad / 'reviews')}`\n"
        f"{focus}{strict_rule}{hp_critic_note}\n"
        f"**Mandatory Defects to Fix in Iteration {next_it}:**\n{defect_lines}\n"
        f"{qa_lines}\n"
        f"**Verification & Logging Steps After Rebuilding:**\n"
        f"1. Re-run `vforge qa \"{ad / f'build_{slug}.py'}\" {qa_flags}`.\n"
        f"2. Visually inspect all updated renders + `renders/ref_comparison.png` against every reference photo.\n"
        f"3. Write an honest Iteration {next_it} Review (stating score delta vs `{float(last['honest_rating']):.1f}/10`, what improved, and any remaining defects) and log it via:\n"
        f"   `vforge review log \"{ad}\" --score <X.X> --summary \"...\" --strength \"...\" --defect \"Category|severity|Description|Fix\"`\n"
        f"4. NEVER proceed to Stage 5 baking below `10.0 / 10` — keep iterating until **Honest Rating == 10.0 / 10**, `0` unresolved defects, and **QA PASS (0 Errors, 0 Warnings)**."
    )
