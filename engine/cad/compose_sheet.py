"""Compose labeled material, diagnostic, and multi-reference comparison contact sheets from QA renders.

Supports:
- Multi-reference side-by-side comparison (`ref_pairs` from `render_manifest.json`, matching EVERY
  perspective Street View / 3/4 photo to its exact rendered camera, OR ortho blueprints to ortho views).
- Opt-in subtle metric calibration grid (`--ortho-grid`) drawn STRICTLY on ORTHO blueprint tiles,
  never cluttering perspective photos!
- Optional Honest Rating badge in the header when `reviews/review_history.json` exists.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


BG_DARK = (20, 24, 32)
PANEL_HEADER = (27, 33, 45)
BORDER = (48, 58, 76)
TEXT_PRIMARY = (238, 242, 247)
TEXT_MUTED = (165, 177, 194)
GREEN = (34, 197, 94)
RED = (239, 68, 68)
AMBER = (245, 158, 11)
CYAN = (34, 211, 238)
DARK_INK = (11, 18, 32)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["arialbd.ttf", "consolab.ttf", "segoeuib.ttf"]
        if bold
        else ["arial.ttf", "consola.ttf", "segoeui.ttf"]
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


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> str:
    if _text_size(draw, text, font)[0] <= max_w:
        return text
    suffix = "..."
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _text_size(draw, text[:mid] + suffix, font)[0] <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + suffix


def _open_tile(path: str | None, fallback_size: tuple[int, int], placeholder_label: str) -> Image.Image:
    if path and os.path.exists(path):
        with Image.open(path) as im:
            return im.convert("RGB")
    im = Image.new("RGB", fallback_size, (34, 40, 52))
    d = ImageDraw.Draw(im)
    f = _load_font(18, bold=True)
    msg = f"Missing tile: {placeholder_label}"
    tw, th = _text_size(d, msg, f)
    d.text(((fallback_size[0] - tw) // 2, (fallback_size[1] - th) // 2), msg, fill=AMBER, font=f)
    return im


def _resize_cover_pad(im: Image.Image, target_w: int, target_h: int, bg=(30, 35, 45)) -> Image.Image:
    if im.size == (target_w, target_h):
        return im
    src_w, src_h = im.size
    scale = min(target_w / max(src_w, 1), target_h / max(src_h, 1))
    nw = max(1, int(round(src_w * scale)))
    nh = max(1, int(round(src_h * scale)))
    resized = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), bg)
    canvas.paste(resized, ((target_w - nw) // 2, (target_h - nh) // 2))
    return canvas


def _apply_ortho_blueprint_grid(im: Image.Image, ortho_scale_m: float | None = None) -> Image.Image:
    """Draw a subtle calibrated metric grid strictly on ORTHO blueprint renders (never perspective!)."""
    rgba = im.convert("RGBA")
    overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = rgba.size

    if ortho_scale_m and ortho_scale_m > 0:
        # Pick clean metric grid spacing (0.1m, 0.25m, 0.5m, 1m, 2m, 5m)
        raw_step = ortho_scale_m / 8.0
        for cand in (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0):
            if cand >= raw_step:
                step_m = cand
                break
        else:
            step_m = 10.0
        px_per_m = w / float(ortho_scale_m)
        step_px = max(24.0, step_m * px_per_m)
        scale_lbl = f"ORTHO GRID: {step_m:g}m / div"
    else:
        step_px = max(32.0, w / 8.0)
        scale_lbl = "ORTHO BLUEPRINT GRID"

    cx, cy = w * 0.5, h * 0.5
    line_col = (34, 211, 238, 68)
    axis_col = (34, 211, 238, 128)

    k = 0
    while True:
        off = k * step_px
        col = axis_col if k == 0 else line_col
        drawn = False
        if cx + off < w:
            x = int(round(cx + off))
            d.line([(x, 0), (x, h)], fill=col, width=1)
            drawn = True
        if k > 0 and cx - off >= 0:
            x = int(round(cx - off))
            d.line([(x, 0), (x, h)], fill=col, width=1)
            drawn = True
        if not drawn:
            break
        k += 1

    k = 0
    while True:
        off = k * step_px
        col = axis_col if k == 0 else line_col
        drawn = False
        if cy + off < h:
            y = int(round(cy + off))
            d.line([(0, y), (w, y)], fill=col, width=1)
            drawn = True
        if k > 0 and cy - off >= 0:
            y = int(round(cy - off))
            d.line([(0, y), (w, y)], fill=col, width=1)
            drawn = True
        if not drawn:
            break
        k += 1

    f_badge = _load_font(12, bold=True)
    bw, bh = _text_size(d, scale_lbl, f_badge)
    d.rounded_rectangle([8, h - bh - 14, 18 + bw, h - 6], radius=4, fill=(15, 23, 42, 195))
    d.text((13, h - bh - 11), scale_lbl, fill=(103, 232, 249, 255), font=f_badge)

    return Image.alpha_composite(rgba, overlay).convert("RGB")


def _draw_header(
    canvas: Image.Image,
    qa: dict[str, Any],
    subtitle: str,
    header_h: int = 76,
    review_badge: str = "",
) -> None:
    draw = ImageDraw.Draw(canvas)
    w = canvas.width
    draw.rectangle([0, 0, w, header_h], fill=BG_DARK)
    draw.line([(0, header_h - 1), (w, header_h - 1)], fill=BORDER, width=2)

    passed = bool(qa.get("pass", False))
    pill_text = "PASS" if passed else "FAIL"
    pill_bg = GREEN if passed else RED
    pill_fg = DARK_INK if passed else (255, 255, 255)

    font_pill = _load_font(20, bold=True)
    font_title = _load_font(22, bold=True)
    font_meta = _load_font(15, bold=False)

    pad_x = 18
    pill_w, pill_h = 84, 38
    pill_y = (header_h - pill_h) // 2
    draw.rounded_rectangle([pad_x, pill_y, pad_x + pill_w, pill_y + pill_h], radius=8, fill=pill_bg)
    ptw, pth = _text_size(draw, pill_text, font_pill)
    draw.text(
        (pad_x + (pill_w - ptw) // 2, pill_y + (pill_h - pth) // 2 - 2),
        pill_text,
        fill=pill_fg,
        font=font_pill,
    )

    right_reserve = 18
    if review_badge:
        f_rb = _load_font(15, bold=True)
        rbw, rbh = _text_size(draw, review_badge, f_rb)
        rw = rbw + 24
        rh = 34
        rx0 = w - rw - 16
        ry0 = (header_h - rh) // 2
        draw.rounded_rectangle([rx0, ry0, rx0 + rw, ry0 + rh], radius=8, fill=(30, 41, 59), outline=CYAN, width=2)
        draw.text((rx0 + 12, ry0 + (rh - rbh) // 2 - 1), review_badge, fill=CYAN, font=f_rb)
        right_reserve = rw + 30

    asset_name = str(qa.get("asset_name") or "Asset")
    profile = str(qa.get("profile") or "roblox")
    renderer = str(qa.get("renderer") or "")
    title_x = pad_x + pill_w + 16
    title_str = f"{asset_name}  |  {subtitle}"
    if renderer:
        title_str += f"  ({renderer}, profile={profile})"
    else:
        title_str += f"  (profile={profile})"
    draw.text(
        (title_x, 12),
        _truncate(draw, title_str, font_title, max(120, w - title_x - right_reserve)),
        fill=TEXT_PRIMARY,
        font=font_title,
    )

    total_tris = qa.get("total_tris", 0)
    obj_count = qa.get("object_count", len(qa.get("objects", {})))
    size_m = qa.get("size_m") or [0, 0, 0]
    size_studs = qa.get("size_studs_sclib") or [round(v * 3.0, 2) for v in size_m]
    err_n = len(qa.get("errors", []))
    warn_n = len(qa.get("warnings", []))
    ground_z = qa.get("ground_z")

    meta_parts = [
        f"Tris: {total_tris:,}",
        f"Parts/Meshes: {obj_count}",
        f"Size(m): {size_m[0]:.3g} x {size_m[1]:.3g} x {size_m[2]:.3g}",
        f"Studs(3/m): {size_studs[0]:.2g} x {size_studs[1]:.2g} x {size_studs[2]:.2g}",
        f"Ground Z: {ground_z if ground_z is not None else 'n/a'}",
        f"Errors: {err_n}  Warnings: {warn_n}",
    ]
    meta_str = "   |   ".join(meta_parts)
    draw.text(
        (title_x, 44),
        _truncate(draw, meta_str, font_meta, max(120, w - title_x - right_reserve)),
        fill=TEXT_MUTED,
        font=font_meta,
    )


def _compose_grid(
    tile_specs: list[tuple[str, str | None, dict[str, Any]]],
    cols: int,
    rows: int,
    qa: dict[str, Any],
    subtitle: str,
    out_path: str,
    footer_lines: list[tuple[str, tuple[int, int, int]]] | None = None,
    ortho_grid: bool = False,
    review_badge: str = "",
) -> str:
    base_size = (640, 480)
    for _, path, _ in tile_specs:
        if path and os.path.exists(path):
            with Image.open(path) as im:
                base_size = im.size
            break

    tile_w, tile_h = base_size
    header_h = 76
    label_h = 34
    gap = 12
    pad = 14
    footer_h = (20 + len(footer_lines) * 24) if footer_lines else 0

    cell_w = tile_w
    cell_h = label_h + tile_h
    canvas_w = pad * 2 + cols * cell_w + (cols - 1) * gap
    canvas_h = header_h + pad * 2 + rows * cell_h + (rows - 1) * gap + footer_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), BG_DARK)
    _draw_header(canvas, qa, subtitle, header_h=header_h, review_badge=review_badge)
    draw = ImageDraw.Draw(canvas)
    font_label = _load_font(15, bold=True)

    for idx, (label, path, meta) in enumerate(tile_specs):
        r = idx // cols
        c = idx % cols
        x0 = pad + c * (cell_w + gap)
        y0 = header_h + pad + r * (cell_h + gap)

        draw.rectangle([x0 - 2, y0 - 2, x0 + cell_w + 1, y0 + cell_h + 1], outline=BORDER, width=2)
        draw.rectangle([x0, y0, x0 + cell_w - 1, y0 + label_h - 1], fill=PANEL_HEADER)
        draw.text((x0 + 10, y0 + 7), _truncate(draw, label, font_label, cell_w - 20), fill=TEXT_PRIMARY, font=font_label)

        tile_im = _open_tile(path, (tile_w, tile_h), label)
        if tile_im.size != (tile_w, tile_h):
            tile_im = _resize_cover_pad(tile_im, tile_w, tile_h)
        # Apply optional metric grid STRICTLY to ORTHO blueprint tiles — never perspective renders!
        if ortho_grid and str(meta.get("projection", "")).upper() == "ORTHO":
            tile_im = _apply_ortho_blueprint_grid(tile_im, meta.get("ortho_scale_m"))
        canvas.paste(tile_im, (x0, y0 + label_h))

    if footer_lines:
        fy0 = canvas_h - footer_h
        draw.line([(0, fy0), (canvas_w, fy0)], fill=BORDER, width=2)
        font_foot = _load_font(14, bold=False)
        for i, (line, color) in enumerate(footer_lines):
            txt = _truncate(draw, line, font_foot, canvas_w - 32)
            draw.text((16, fy0 + 10 + i * 24), txt, fill=color, font=font_foot)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path, format="PNG")
    return out_path


def _build_footer_lines(qa: dict[str, Any]) -> list[tuple[str, tuple[int, int, int]]]:
    lines: list[tuple[str, tuple[int, int, int]]] = []
    for err in qa.get("errors", [])[:3]:
        lines.append((f"[ERROR] {err}", RED))
    remaining = 4 - len(lines)
    if remaining > 0:
        for warn in qa.get("warnings", [])[:remaining]:
            lines.append((f"[WARN]  {warn}", AMBER))
    if not lines:
        lines.append(("[OK]    No automated QA errors or warnings detected.", GREEN))
    else:
        total_e = len(qa.get("errors", []))
        total_w = len(qa.get("warnings", []))
        if total_e + total_w > len(lines):
            lines.append(
                (f"... +{total_e + total_w - len(lines)} more item(s) in qa_report.json", TEXT_MUTED)
            )
    return lines


def _compose_multi_ref_comparison(
    pairs: list[dict[str, Any]],
    qa: dict[str, Any],
    out_path: str,
    ortho_grid: bool = False,
    review_badge: str = "",
) -> str:
    """Compose a 1-to-N side-by-side Reference vs Matched Model sheet (perspective & ortho aware)."""
    valid_pairs = [
        p for p in pairs
        if p.get("ref_path") and os.path.exists(p["ref_path"]) and p.get("model_path") and os.path.exists(p["model_path"])
    ][:8]
    if not valid_pairs:
        return ""

    # Single pair -> crisp large view; multiple pairs -> stacked or 2-column paired grid
    pair_count = len(valid_pairs)
    if pair_count == 1:
        tile_w, tile_h = 680, 510
        pair_cols = 1
    elif pair_count <= 3:
        tile_w, tile_h = 600, 400
        pair_cols = 1
    else:
        tile_w, tile_h = 460, 320
        pair_cols = 2

    pair_rows = math.ceil(pair_count / pair_cols)
    header_h = 76
    label_h = 32
    pad = 14
    inner_gap = 10
    pair_gap_x = 22
    pair_gap_y = 18

    pair_w = tile_w * 2 + inner_gap
    pair_h = label_h + tile_h
    canvas_w = pad * 2 + pair_cols * pair_w + (pair_cols - 1) * pair_gap_x
    canvas_h = header_h + pad * 2 + pair_rows * pair_h + (pair_rows - 1) * pair_gap_y

    canvas = Image.new("RGB", (canvas_w, canvas_h), BG_DARK)
    subtitle = (
        "REFERENCE COMPARISON"
        if pair_count == 1
        else f"MULTI-ANGLE REFERENCE COMPARISON ({pair_count} MATCHED VIEWS)"
    )
    _draw_header(canvas, qa, subtitle, header_h=header_h, review_badge=review_badge)
    draw = ImageDraw.Draw(canvas)
    font_label = _load_font(14, bold=True)

    for idx, p in enumerate(valid_pairs):
        r = idx // pair_cols
        c = idx % pair_cols
        px0 = pad + c * (pair_w + pair_gap_x)
        py0 = header_h + pad + r * (pair_h + pair_gap_y)
        is_ortho = str(p.get("projection", "")).upper() == "ORTHO"

        with Image.open(p["ref_path"]) as r_im:
            ref_scaled = _resize_cover_pad(r_im.convert("RGB"), tile_w, tile_h, bg=(24, 28, 36))
        with Image.open(p["model_path"]) as m_im:
            mod_scaled = _resize_cover_pad(m_im.convert("RGB"), tile_w, tile_h, bg=(24, 28, 36))

        if ortho_grid and is_ortho:
            ref_scaled = _apply_ortho_blueprint_grid(ref_scaled, p.get("ortho_scale_m"))
            mod_scaled = _apply_ortho_blueprint_grid(mod_scaled, p.get("ortho_scale_m"))

        # Left: Reference
        draw.rectangle([px0 - 2, py0 - 2, px0 + tile_w + 1, py0 + pair_h + 1], outline=BORDER, width=2)
        draw.rectangle([px0, py0, px0 + tile_w - 1, py0 + label_h - 1], fill=PANEL_HEADER)
        r_lbl = _truncate(draw, str(p.get("ref_label") or os.path.basename(p["ref_path"])), font_label, tile_w - 16)
        draw.text((px0 + 8, py0 + 7), r_lbl, fill=CYAN if not is_ortho else AMBER, font=font_label)
        canvas.paste(ref_scaled, (px0, py0 + label_h))

        # Right: Model
        mx0 = px0 + tile_w + inner_gap
        draw.rectangle([mx0 - 2, py0 - 2, mx0 + tile_w + 1, py0 + pair_h + 1], outline=BORDER, width=2)
        draw.rectangle([mx0, py0, mx0 + tile_w - 1, py0 + label_h - 1], fill=PANEL_HEADER)
        m_lbl = _truncate(draw, str(p.get("model_label") or "MODEL"), font_label, tile_w - 16)
        draw.text((mx0 + 8, py0 + 7), m_lbl, fill=TEXT_PRIMARY, font=font_label)
        canvas.paste(mod_scaled, (mx0, py0 + label_h))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    canvas.save(out_path, format="PNG")
    return out_path


def _load_review_badge(history_path: str) -> str:
    if not history_path or not os.path.isfile(history_path):
        return ""
    try:
        data = json.loads(Path(history_path).read_text(encoding="utf-8-sig"))
        iters = data.get("iterations") or []
        if iters:
            last = iters[-1]
            return f"ITER {last['iteration']}  •  {float(last['honest_rating']):.1f} / 10"
    except Exception:
        pass
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compose labeled QA & multi-reference contact sheets.")
    parser.add_argument("--manifest", help="Path to render_manifest.json from qa_pipeline.py")
    parser.add_argument("--tiles", help="Optional JSON mapping tile keys to file paths")
    parser.add_argument("--qa-json", required=True, help="Path to qa_report.json")
    parser.add_argument("--out-material", required=True, help="Output path for material 6-view contact sheet")
    parser.add_argument("--out-diagnostic", required=True, help="Output path for diagnostic 4-view contact sheet")
    parser.add_argument("--ref", default="", help="Optional explicit reference image path")
    parser.add_argument("--ref-dir", default="", help="Optional directory containing multiple reference photos")
    parser.add_argument("--out-ref", default="", help="Output path for reference comparison sheet")
    parser.add_argument("--ortho-grid", action="store_true", help="Overlay subtle metric grid strictly on ORTHO blueprint tiles")
    parser.add_argument("--review-history", default="", help="Optional path to reviews/review_history.json for rating header badge")
    args = parser.parse_args(argv)

    with open(args.qa_json, encoding="utf-8") as fh:
        qa = json.load(fh)

    tiles: dict[str, dict[str, Any]] = {}
    ref_pairs: list[dict[str, Any]] = []
    manifest_ortho_grid = False

    if args.manifest and os.path.exists(args.manifest):
        with open(args.manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
        tiles.update(manifest.get("tiles", {}))
        ref_pairs.extend(manifest.get("ref_pairs", []))
        manifest_ortho_grid = bool(manifest.get("ortho_grid", False))

    use_ortho_grid = bool(args.ortho_grid or manifest_ortho_grid)
    review_badge = _load_review_badge(args.review_history)

    if args.tiles:
        raw = json.loads(args.tiles)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, str):
                    tiles[k] = {"path": v, "label": k.upper()}
                elif isinstance(v, dict):
                    tiles[k] = v

    def tile_entry(key: str, default_label: str, default_proj: str = "PERSP") -> tuple[str, str | None, dict[str, Any]]:
        item = dict(tiles.get(key) or {})
        item.setdefault("projection", default_proj)
        return item.get("label", default_label), item.get("path"), item

    material_specs = [
        tile_entry("hero", "HERO 3/4", "PERSP"),
        tile_entry("front", "FRONT (ORTHO)", "ORTHO"),
        tile_entry("side", "SIDE (ORTHO)", "ORTHO"),
        tile_entry("back", "BACK (ORTHO)", "ORTHO"),
        tile_entry("top", "TOP (ORTHO)", "ORTHO"),
        tile_entry("rear_34", "REAR 3/4", "PERSP"),
    ]
    _compose_grid(
        material_specs,
        cols=3,
        rows=2,
        qa=qa,
        subtitle="6-VIEW MATERIAL SHEET",
        out_path=args.out_material,
        ortho_grid=use_ortho_grid,
        review_badge=review_badge,
    )

    diagnostic_specs = [
        tile_entry("diag_wire", "WIREFRAME (HERO 3/4)", "PERSP"),
        tile_entry("diag_parts", "PART COLORS (HERO 3/4)", "PERSP"),
        tile_entry("diag_normals", "FACE ORIENTATION (BLUE=OUT / RED=FLIPPED)", "PERSP"),
        tile_entry("diag_bottom", "UNDERBODY / BOTTOM", "PERSP"),
    ]
    _compose_grid(
        diagnostic_specs,
        cols=2,
        rows=2,
        qa=qa,
        subtitle="4-VIEW DIAGNOSTIC SHEET",
        out_path=args.out_diagnostic,
        footer_lines=_build_footer_lines(qa),
        ortho_grid=False,
        review_badge=review_badge,
    )

    # Multi-reference comparison sheet
    if args.out_ref:
        existing_ref_paths = {os.path.normcase(os.path.abspath(p["ref_path"])) for p in ref_pairs if p.get("ref_path")}

        def _append_fallback_ref(rp: str) -> None:
            if not rp or not os.path.exists(rp):
                return
            nrp = os.path.normcase(os.path.abspath(rp))
            if nrp in existing_ref_paths:
                return
            existing_ref_paths.add(nrp)
            low = os.path.basename(rp).lower()
            is_ortho = any(k in low for k in ("ortho", "blueprint", "elevation")) or ("side" in low or "front" in low or "top" in low)
            use_key = "side" if "side" in low else ("front" if "front" in low else ("top" if "top" in low else "hero"))
            mod_label, mod_path, mod_meta = tile_entry(use_key, "MODEL", "ORTHO" if is_ortho else "PERSP")
            if mod_path and os.path.exists(mod_path):
                ref_pairs.append({
                    "ref_path": os.path.abspath(rp),
                    "ref_label": f"{'BLUEPRINT' if is_ortho else 'REFERENCE'} ({os.path.basename(rp)})",
                    "model_path": mod_path,
                    "model_label": f"MODEL — {mod_label}",
                    "projection": "ORTHO" if is_ortho else "PERSP",
                    "ortho_scale_m": mod_meta.get("ortho_scale_m"),
                })

        if args.ref:
            _append_fallback_ref(args.ref)
        if args.ref_dir and os.path.isdir(args.ref_dir):
            for fn in sorted(os.listdir(args.ref_dir)):
                if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    _append_fallback_ref(os.path.join(args.ref_dir, fn))

        if ref_pairs:
            _compose_multi_ref_comparison(
                ref_pairs,
                qa=qa,
                out_path=args.out_ref,
                ortho_grid=use_ortho_grid,
                review_badge=review_badge,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
