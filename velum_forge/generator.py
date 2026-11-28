"""Reference-driven 3D Asset Generator & AI Agent Orchestrator (`velum_forge.generator`).

Supports three seamless generation modes:
  1. `parametric` — Instant offline reference-calibrated multi-part generator (uses reference aspect ratio,
     dominant hex palette, real-world meters, and matched perspective cameras or ortho blueprints)
     + automatic 10-view QA & multi-angle `ref_comparison.png`!
  2. `claude` / `codex` / `gemini` — Drives an installed local multimodal AI CLI (`claude`, `codex`, `gemini`)
     to inspect `<asset_dir>/references/*`, write bespoke `build_<slug>.py` + `bake_lod_variants.py`,
     pass the 10-view QA gate (`0` errors, `0` warnings), optionally execute the Honest Rating
     Iteration Review Loop, and bake 2K Cycles PBR textures + LOD0-LOD3.
  3. `handoff` — Stages `asset_spec.json` + `references/` and outputs a 1-click copyable prompt for
     interactive IDE agents (Google Antigravity, Cursor, Windsurf, Claude Code).
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

from . import BLENDER_ENGINE_DIR, CAD_ENGINE_DIR, EXAMPLES_DIR, REPO_ROOT
from .references import write_asset_spec
from .review import get_review_config, normalize_review_config


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_")
    return s or "custom_asset"


def pascal_case(slug: str) -> str:
    return "".join(w.capitalize() for w in slug.split("_") if w)


def detect_ai_clis() -> list[dict[str, Any]]:
    """Detect installed local AI coding CLIs (`claude`, `codex`, `gemini`) on PATH or npm global bin."""
    appdata = os.environ.get("APPDATA", "")
    home = Path.home()

    specs = [
        ("claude", "Claude Code CLI (Multimodal Reference Vision + Code)", [
            shutil.which("claude"),
            str(Path(appdata) / "npm" / "claude.cmd") if appdata else None,
            str(home / ".local" / "bin" / ("claude.exe" if platform.system() == "Windows" else "claude")),
        ]),
        ("codex", "OpenAI Codex CLI", [
            shutil.which("codex"),
            str(Path(appdata) / "npm" / "codex.cmd") if appdata else None,
        ]),
        ("gemini", "Google Gemini CLI", [
            shutil.which("gemini"),
            str(Path(appdata) / "npm" / "gemini.cmd") if appdata else None,
        ]),
    ]

    found: list[dict[str, Any]] = []
    for cid, label, cands in specs:
        exe = next((c for c in cands if c and os.path.isfile(c)), None)
        found.append({"id": cid, "label": label, "installed": exe is not None, "exe": exe})
    return found


def build_agent_handoff_prompt(
    asset_dir: Path,
    *,
    rate_to_ten: bool | None = None,
    high_poly: bool | None = None,
) -> str:
    """Build a crystal-clear, copy-paste-ready prompt for Antigravity, Cursor, Claude Code, or Codex."""
    spec_file = asset_dir / "asset_spec.json"
    spec = json.loads(spec_file.read_text(encoding="utf-8-sig")) if spec_file.is_file() else {}
    slug = spec.get("slug", asset_dir.name)
    title = spec.get("title", slug)
    kind = spec.get("kind", "prop")
    prompt = spec.get("prompt", title)
    length_m = spec.get("target_length_m", 1.2)
    is_arch = kind in ("building", "arch")
    hp_on = bool(spec.get("high_poly_uncapped", False)) if high_poly is None else bool(high_poly)
    qa_profile = "game" if hp_on else spec.get("qa_profile", "game" if is_arch else "roblox")
    bake_res = int(spec.get("bake_res", 2048))
    refs = spec.get("references", [])
    pal = spec.get("extracted_palette", [])
    ortho_grid = bool(spec.get("ortho_blueprint_grid", False))
    review_cfg = normalize_review_config(spec.get("review_loop"))
    if rate_to_ten is True:
        review_cfg["enabled"] = True
    elif rate_to_ten is False:
        review_cfg["enabled"] = False
    elif spec.get("rate_to_ten") and not review_cfg["enabled"]:
        review_cfg["enabled"] = True
    review_cfg["target_score"] = 10.0
    review_cfg["strict_ten"] = True

    persp_refs = [r for r in refs if r.get("projection", "perspective") != "ortho_blueprint"]
    ortho_refs = [r for r in refs if r.get("projection") == "ortho_blueprint"]

    def _fmt_ref(r: dict[str, Any]) -> str:
        proj = r.get("projection", "perspective")
        cam = r.get("camera") or {}
        cam_hint = f", lens={cam.get('lens_mm')}mm" if proj == "perspective" and cam.get("lens_mm") else ""
        return (
            f"  - `{r['path']}` (mode=`{proj}`, view=`{r.get('view', 'hero')}`{cam_hint}, "
            f"aspect={r.get('subject_aspect_w_over_h')}, palette={r.get('dominant_palette')})"
        )

    ref_lines = "\n".join(_fmt_ref(r) for r in refs) or (
        "  - (No reference images attached — research real-world dimensions & proportions first)"
    )

    if persp_refs and not ortho_refs:
        ref_strategy = (
            "   - **Perspective Reference Workflow (NO Ortho Blueprint Grid):** All attached images are real perspective photos. "
            "Use matched Blender perspective cameras (`vflib.refs.load_references(THIS_DIR)` or `refs.add_perspective_ref_camera(...)` "
            "with matching focal length `28mm`/`35mm`/`50mm` and real eye-level/3-4 viewpoints) so `vforge qa` renders exact matched camera pairs in `renders/ref_comparison.png`."
        )
    elif ortho_refs and not persp_refs:
        grid_note = " with `--ortho-grid` enabled" if ortho_grid else " (optional `--ortho-grid` available)"
        ref_strategy = (
            f"   - **Ortho Blueprint Workflow:** Load 1:1m orthographic blueprint planes via `refs.load_references(THIS_DIR, show_ortho_grid={ortho_grid})`{grid_note}."
        )
    elif persp_refs and ortho_refs:
        ref_strategy = (
            "   - **Hybrid Reference Workflow:** `refs.load_references(THIS_DIR)` automatically mounts `ortho_blueprint` images on 1:1m ortho planes "
            "and spawns matched `VF_RefCam_*` perspective cameras (with camera background overlay) for all perspective photos!"
        )
    else:
        ref_strategy = "   - Call `refs.load_references(THIS_DIR)` if references are added later."

    extra_skill = (
        "`velum-architecture-environments`, "
        if is_arch
        else ("`velum-organic-species`, " if kind == "fish" else "")
    )
    if hp_on:
        budget_rule = (
            "**[HIGH-POLY UNCAPPED MODE: ON — NO 300k / 20k TRI CAP]**\n"
            "   - Use `--profile game --high-poly --max-tris 0` (unlimited BVH & geometry budget — ignore any 300k scene limit or 20k per-part limit). Keep repeating props as linked `Mesh` instances (`vf_asset_set`, `vf_instanced = True`) and split any merged multi-prop object strictly for clean 2K PBR UV texel density — NEVER decimate or slash radial segments/foliage to chase a tri limit.\n"
            "   - **Photorealistic ArchViz Geometry Floors (News Cafe Standard):**\n"
            "     - Hero furniture, tabletops, cushions, barstools, rings & globes: `24–36` radial segments; curved bentwood tubes & splayed legs: `12–16` segs + Catmull-Rom smoothing (`vflib.quadflow.add_spline_tube(..., substeps=3)`).\n"
            "     - Tableware, wine glasses, cups, bottles & brass sconces: `16–24` radial segments (`>= 80%` `Alt+J` quad recovery).\n"
            "     - Architectural trim, window frames/sills, columns & curbs: micro-beveled edges (`vflib.quadflow.add_box(..., bevel=0.004..0.020)`) and smooth `20–24`-seg curved arches, curbs & Art Deco quatrefoil breeze blocks (`add_breeze_block(..., style=\"quatrefoil\")`).\n"
            "     - 3D Botanicals: `20–24`-seg curved ringed palm trunks with `14–18` arching fronds × `16–22` pairs of `3`-seg curved V-folded leaflets; dense multi-branch shade trees & lush 3D hedges/bougainvillea (`40k–250k+` botanical tris expected).\n"
            "     - Critic Rule: faceted low-segment cylinders (`<= 10` segs on hero props), sparse stick-like palms, or un-beveled boxy trim are `[MAJOR]` defects that block `10.0 / 10`."
        )
    else:
        base_rule = (
            "Real-world meter scale (`+Y` forward, `+Z` up, `ground_objects_safe`), multi-datum grounding (`Z_ROAD`, `Z_SW`, `Z_FLOOR_INT`), `2D` obstacle clearances, structured `FIXED` quad-flow furniture (`>= 80%` `Alt+J` quads), 3D curved botanicals (`deconflict_botanical_islands`), modular Outliner instancing + `vf_asset_set` (if any object exceeds `20k` tris because repeated/separable items like 2+ stools or chairs are joined together, split them into separate linked instances or sub-parts before reducing detail), and `--profile game --max-tris 300000`."
            if is_arch
            else "Real-world meter scale (`+Y` forward, `+Z` up, `ground_objects_safe`), `< 20,000` tris per `MeshPart` (`--profile roblox` — if any object exceeds `20k` tris because repeated/separable items like 2+ stools or props are joined together, split them into separate linked instances or sub-parts first instead of lowering detail), `>= 1.6 mm` wall thickness, positive signed volume normals, and `0` BVH shell breaches."
        )
        budget_rule = (
            f"{base_rule}\n"
            "   - *(High-Poly Uncapped Mode is OFF by default. Pass `--high-poly`, toggle `High-Poly Photorealistic Mode` in Studio UI, or explicitly request High-Poly Uncapped Mode in your prompt to remove the 300k/20k tri caps and enforce News Cafe ArchViz high-poly segment floors.)*"
        )

    qa_flags = f"--profile {qa_profile}"
    if hp_on:
        qa_flags += " --high-poly --max-tris 0"
    elif qa_profile == "game":
        qa_flags += " --max-tris 300000"
    qa_flags += " --forward-axis +Y"
    if ortho_grid and ortho_refs:
        qa_flags += " --ortho-grid"
    if review_cfg["enabled"]:
        qa_flags += " --snapshot-iteration"

    if review_cfg["enabled"]:
        focus_line = f"\n   - Critic Focus Notes: {review_cfg['focus_notes']}" if review_cfg.get("focus_notes") else ""
        qa_warn_req = " and `0` Warnings" if review_cfg["require_zero_qa_warnings"] else ""
        review_section = (
            f"5. **Optional Iterative Critic & Honest Rating Loop (`ENABLED` — Strict Target `10.0 / 10`, Never Proceed Below `10/10`):**\n"
            f"   - After inspecting ALL rendered views (`renders/ref_comparison.png`, `renders/qa_contact_material.png`, `renders/qa_contact_diagnostic.png`, and individual `renders/refcam_*.png`) against every reference photo + `qa_report.json`:\n"
            f"   - Write a brutally honest **Iteration N Review — Honest Rating: X.X / 10** (NO grade inflation — explicitly list strengths AND categorized defects such as primitive foliage blobs, faceted low-segment props, buried windows, clipping umbrellas/props, blurry signage, floating parts, or UV overlaps).{focus_line}\n"
            f"   - **Strict Always-10/10 Rule:** Rate yourself honestly from `0` to `10` until the outcome genuinely becomes a `10 out of 10`. It should look brilliant. Do not rush, do not fake or inflate the rating, and **NEVER stop, approve, or proceed to Stage 5 baking below `10.0 / 10`** (even `9.0`, `9.5`, or `9.6` must keep iterating!).\n"
            f"   - Persist every iteration review so Velum Forge tracks progression & builds `reviews/iteration_progression.png`:\n"
            f"     `vforge review log \"{asset_dir}\" --score <X.X> --summary \"...\" --strength \"...\" --defect \"Category|major|Defect|Exact fix\"`\n"
            f"   - Keep iterating (fixing all defects and geometric QA issues) until **Honest Rating == 10.0 / 10**, `0` unresolved defects, and **QA PASS (`0` Errors{qa_warn_req})**.\n\n"
            f"6. **Bake Dedicated `{bake_res}x{bake_res}` Per-Set Cycles GPU PBR Maps, Variants & Instance-Aware `LOD0`–`LOD3`:**\n"
            f"   - Run: `vforge bake \"{asset_dir / 'bake_lod_variants.py'}\"` (`isolate_for_ao=True`, Dual-UV `GraphicUV`, clean Outliner with `0` `_src` suffixes) and inspect `renders/variants_lineup.png`, `renders/lod_comparison_sheet.png`, and `reviews/iteration_progression.png`."
        )
    else:
        review_section = (
            f"5. **Bake Dedicated `{bake_res}x{bake_res}` Per-Set Cycles GPU PBR Maps, Variants & Instance-Aware `LOD0`–`LOD3`:**\n"
            f"   - *(Iterative Rating Review Loop is `OFF` for this asset — single-pass QA mode. Toggle it ON anytime with `vforge review config \"{asset_dir}\" --enable` — when enabled, target is always `10.0 / 10`.)*\n"
            f"   - Run: `vforge bake \"{asset_dir / 'bake_lod_variants.py'}\"` (`isolate_for_ao=True`, Dual-UV `GraphicUV`, clean Outliner with `0` `_src` suffixes) and inspect `renders/variants_lineup.png` and `renders/lod_comparison_sheet.png`."
        )

    return (
        f"Build and refine the Velum Forge 3D asset **{title}** (`{slug}`, archetype=`{kind}`, target_length=`{length_m} m`) "
        f"in `{asset_dir}` following the Velum Forge 6-Gate Standard:\n\n"
        f"1. **Read Spec & Inspect Every Reference Image First:**\n"
        f"   - Spec JSON: `{spec_file}`\n"
        f"   - User Description: {prompt}\n"
        f"   - Extracted Reference Palette: {', '.join(pal)}\n"
        f"   - Reference Images (visually inspect EVERY image before modeling!):\n{ref_lines}\n"
        f"{ref_strategy}\n\n"
        f"2. **Read Velum Forge Skills & Guardrails (`{REPO_ROOT}`):**\n"
        f"   - Activate `velum-3d-workflow`, {extra_skill}`velum-cad-brep`, `velum-organic-species`, and `velum-pbr-bake-lods`.\n"
        f"   - Engine imports: `sys.path.insert(0, r\"{BLENDER_ENGINE_DIR}\")` -> `from vflib import core, mats, gameready, integrity, bake, lod, export, quadflow, refs`.\n\n"
        f"3. **Author Bespoke Geometry & Shaders (`build_{slug}.py` + `bake_lod_variants.py`):**\n"
        f"   - {budget_rule}\n\n"
        f"4. **Verify 10-View QA + Multi-Angle Side-by-Side Reference Comparison (`PASS` 0 Errors, 0 Warnings):**\n"
        f"   - Run: `vforge qa \"{asset_dir / f'build_{slug}.py'}\" {qa_flags}`\n"
        f"   - Visually inspect `renders/qa_contact_material.png`, `renders/qa_contact_diagnostic.png`, and `renders/ref_comparison.png`!\n\n"
        f"{review_section}"
    )


def generate_parametric_scripts(
    asset_dir: Path,
    *,
    slug: str,
    title: str,
    kind: str,
    prompt: str,
    length_m: float,
    references: list[dict[str, Any]],
    profile: str = "auto",
    bake_res: int = 2048,
    ortho_blueprint_grid: bool = False,
    review_loop: dict[str, Any] | None = None,
    rate_to_ten: bool | None = None,
    high_poly_uncapped: bool = False,
) -> dict[str, str]:
    """Write reference-calibrated multi-part `build_<slug>.py` + `bake_lod_variants.py` + `asset_spec.json`."""
    asset_dir.mkdir(parents=True, exist_ok=True)
    hp_on = bool(high_poly_uncapped)
    if profile == "auto":
        resolved_profile = "game" if (hp_on or kind in ("building", "arch")) else "roblox"
    else:
        resolved_profile = profile
    spec_path = write_asset_spec(
        asset_dir,
        slug=slug,
        title=title,
        kind=kind,
        prompt=prompt,
        length_m=length_m,
        profile=resolved_profile,
        bake_res=bake_res,
        rate_to_ten=rate_to_ten,
        high_poly_uncapped=hp_on,
        references=references,
        ortho_blueprint_grid=ortho_blueprint_grid,
        review_loop=review_loop,
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    pal = spec["extracted_palette"]
    c_primary = pal[0] if len(pal) > 0 else "#0E7490"
    c_secondary = pal[1] if len(pal) > 1 else "#EAB308"
    c_belly = pal[2] if len(pal) > 2 else "#F1F5F9"
    c_accent = pal[3] if len(pal) > 3 else "#1E293B"

    ref_aspect = next((r["subject_aspect_w_over_h"] for r in references if r.get("subject_aspect_w_over_h")), None)
    pascal = pascal_case(slug)
    bl_engine = str(BLENDER_ENGINE_DIR).replace("\\", "\\\\")
    cad_engine = str(CAD_ENGINE_DIR).replace("\\", "\\\\")

    build_py = asset_dir / f"build_{slug}.py"
    bake_py = asset_dir / "bake_lod_variants.py"

    if kind == "fish":
        depth_ratio = round(max(0.16, min(0.42, 0.82 / ref_aspect)), 3) if ref_aspect and ref_aspect > 1.2 else 0.24
        build_py.write_text(
            f'''"""Velum Forge Reference-Calibrated Organic Species — {title} (`{length_m} m` LOA).

Prompt: {prompt}
Reference Palette: {pal} | Calibrated Depth Ratio: {depth_ratio}
"""
from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if "{bl_engine}" not in sys.path:
    sys.path.insert(0, "{bl_engine}")

from vflib import core, gameready, integrity, mats, refs  # noqa: E402

LOA = {float(length_m):.4f}
DEPTH_RATIO = {depth_ratio}
SNOUT_Y = LOA * 0.48
PEDUNCLE_Y = -LOA * 0.31
TAIL_Y = -LOA * 0.52


def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        d = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(d)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def _unwrap_clean(ob: bpy.types.Object) -> None:
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.012, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.010)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


def _tube_with_caps(rings: list[list[Vector]], cap_a: Vector, cap_b: Vector) -> bmesh.types.BMesh:
    bm = bmesh.new()
    va = bm.verts.new(cap_a)
    bm_r = [[bm.verts.new(p) for p in r] for r in rings]
    vb = bm.verts.new(cap_b)
    nc = len(bm_r[0])
    for j in range(nc):
        jn = (j + 1) % nc
        bm.faces.new((va, bm_r[0][jn], bm_r[0][j]))
    for i in range(len(bm_r) - 1):
        for j in range(nc):
            jn = (j + 1) % nc
            bm.faces.new((bm_r[i][j], bm_r[i][jn], bm_r[i + 1][jn], bm_r[i + 1][j]))
    for j in range(nc):
        jn = (j + 1) % nc
        bm.faces.new((bm_r[-1][j], bm_r[-1][jn], vb))
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    integrity.ensure_positive_signed_volume(bm)
    return bm


def _make_mesh_ob(bm: bmesh.types.BMesh, name: str, col: bpy.types.Collection, mat: bpy.types.Material) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob["sc_part"] = name
    ob["sc_role"] = "solid"
    _unwrap_clean(ob)
    return ob


def _contours(u: float) -> tuple[float, float, float]:
    max_h = LOA * DEPTH_RATIO
    env = math.sin(math.pi * math.pow(max(0.0, min(1.0, u)), 0.62))
    half_h = max(0.014 * LOA, 0.5 * max_h * env)
    half_w = max(0.010 * LOA, 0.22 * max_h * env)
    return -half_h, half_h, half_w


def build_all(collection_name: str = "{pascal}", clear_scene: bool = True, mat_override: dict | None = None):
    if clear_scene:
        clear_scene_and_setup_units()
    col = core.fresh_collection(collection_name)

    m_body = (mat_override or {{}}).get("Body") or mats.pbr("{pascal}_Body", color="{c_primary}", roughness=0.22, metallic=0.35)
    m_fin = (mat_override or {{}}).get("Fins") or mats.pbr("{pascal}_Fins", color="{c_secondary}", roughness=0.28, metallic=0.20)
    m_eye = (mat_override or {{}}).get("Eyes") or mats.pbr("{pascal}_Eyes", color="#090D16", roughness=0.04, metallic=0.10)

    rings = []
    for i in range(1, 96):
        u = i / 96.0
        y = SNOUT_Y - u * (SNOUT_Y - PEDUNCLE_Y)
        zb, zt, hw = _contours(u)
        ring = []
        for j in range(48):
            th = (2.0 * math.pi * j) / 48.0
            zn = 0.5 * (1.0 + math.cos(th))
            z = zb + (zt - zb) * zn
            x = max(0.0012, hw * abs(math.sin(th))) * (1.0 if math.sin(th) >= 0 else -1.0)
            ring.append(Vector((x, y, z)))
        rings.append(ring)
    body = _make_mesh_ob(_tube_with_caps(rings, Vector((0, SNOUT_Y + 0.003, 0)), Vector((0, PEDUNCLE_Y - 0.003, 0))), "Body", col, m_body)

    d_rings = []
    for i in range(1, 56):
        s = i / 56.0
        u = 0.22 + s * 0.62
        y = SNOUT_Y - u * (SNOUT_Y - PEDUNCLE_Y)
        _, zt, _ = _contours(u)
        fh = LOA * 0.095 * math.sin(math.pi * math.pow(s, 0.7))
        d_rings.append([
            Vector((math.sin(2.0 * math.pi * j / 20.0) * max(0.001, 0.0025 * (1.0 - 0.6 * (0.5 * (1.0 - math.cos(2.0 * math.pi * j / 20.0))))),
                    y - 0.02 * s, zt - 0.004 + (0.5 * (1.0 - math.cos(2.0 * math.pi * j / 20.0))) * max(0.004, fh)))
            for j in range(20)
        ])
    y_d0 = SNOUT_Y - 0.22 * (SNOUT_Y - PEDUNCLE_Y)
    y_d1 = SNOUT_Y - 0.84 * (SNOUT_Y - PEDUNCLE_Y)
    dorsal = _make_mesh_ob(_tube_with_caps(d_rings, Vector((0, y_d0, _contours(0.22)[1] - 0.003)), Vector((0, y_d1, _contours(0.84)[1] - 0.003))), "DorsalFin", col, m_fin)

    c_rings = []
    span_z = LOA * DEPTH_RATIO * 0.72
    for i in range(1, 64):
        s = i / 64.0
        v = 2.0 * s - 1.0
        av = abs(v)
        y_l = PEDUNCLE_Y + 0.014 * max(0.0, 1.0 - (av / 0.2) ** 2) - (LOA * 0.16) * (av ** 1.1)
        chord = max(0.012, LOA * 0.065 * (1.0 - 0.55 * av))
        c_rings.append([
            Vector((math.sin(2.0 * math.pi * j / 20.0) * 0.0018,
                    y_l - (0.5 * (1.0 - math.cos(2.0 * math.pi * j / 20.0))) * chord,
                    v * span_z))
            for j in range(20)
        ])
    caudal = _make_mesh_ob(_tube_with_caps(c_rings, Vector((0, TAIL_Y, -span_z)), Vector((0, TAIL_Y, span_z))), "CaudalFin", col, m_fin)

    bm_e = bmesh.new()
    ey = SNOUT_Y - 0.12 * (SNOUT_Y - PEDUNCLE_Y)
    _, _, hw_e = _contours(0.12)
    for side in (-1.0, 1.0):
        bmesh.ops.create_uvsphere(bm_e, u_segments=20, v_segments=14, radius=LOA * 0.016,
                                  matrix=Matrix.Translation((side * (hw_e * 0.88), ey, LOA * 0.018)))
    bmesh.ops.triangulate(bm_e, faces=bm_e.faces[:])
    integrity.ensure_positive_signed_volume(bm_e)
    eyes = _make_mesh_ob(bm_e, "Eyes", col, m_eye)

    meshes = [body, dorsal, caudal, eyes]
    lo, _ = core.world_bbox(meshes)
    if abs(lo.z) > 1e-7:
        for o in meshes:
            o.data.transform(Matrix.Translation((0, 0, -lo.z)))
            o.data.update()

    errs = integrity.verify_socket_contact(body, meshes, forbid_medial_cross_names={{"Eyes"}})
    if errs:
        raise RuntimeError("Integrity check failed: " + "; ".join(errs))

    refs.load_references(THIS_DIR, subject_objects=meshes)
    gameready.validate(meshes)
    return col, meshes


def main() -> int:
    _, meshes = build_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "{slug}.blend"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(THIS_DIR, "{slug}.glb"), export_format="GLB", export_apply=True)
    return 0


if __name__ == "__main__":
    main()
''',
            encoding="utf-8",
        )
    elif kind == "cad":
        build_py.write_text(
            f'''"""Velum Forge Reference-Calibrated B-Rep CAD Part — {title} (`{length_m} m`).

Prompt: {prompt}
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, "{cad_engine}")
from build123d import Align, Box, BuildPart, BuildSketch, Cylinder, Locations, Mode, Plane, RectangleRounded, extrude, fillet
from cad_bridge import export_cad_part

L = {float(length_m):.4f}


def build_part():
    w = L * 0.62
    h = L * 0.14
    with BuildPart() as p:
        with BuildSketch(Plane.XY):
            RectangleRounded(L, w, radius=min(L, w) * 0.12)
        extrude(amount=h)
        with BuildSketch(Plane.XY.offset(h * 0.5)):
            RectangleRounded(L * 0.52, w * 0.48, radius=min(L, w) * 0.08)
        extrude(amount=h * 1.4)
        top_e = p.edges().filter_by(lambda e: e.center().Z > h * 0.8)
        if top_e:
            fillet(top_e, radius=max(0.001, h * 0.12))
        dx, dy = L * 0.36, w * 0.32
        with Locations([(-dx, -dy, h), (dx, -dy, h), (-dx, dy, h), (dx, dy, h)]):
            Cylinder(radius=max(0.002, L * 0.028), height=h * 2.0, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
        with Locations((0, 0, -0.5)):
            Box(L * 4, L * 4, 1.0, mode=Mode.SUBTRACT)
    return p.part


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "cad"))
    args = ap.parse_args()
    res = export_cad_part(build_part(), args.out_dir, "{slug}", color="{c_primary}", metallic=0.85, roughness=0.24)
    print(json.dumps(res, indent=2))
    return 0 if res["inspection"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
''',
            encoding="utf-8",
        )
        return {"slug": slug, "dir": str(asset_dir), "spec": str(spec_path), "build_script": str(build_py)}
    elif kind in ("building", "arch"):
        width_m = max(6.0, float(length_m))
        depth_m = round(width_m * 0.72, 3)
        height_m = round(max(4.4, width_m * 0.52), 3)
        build_py.write_text(
            f'''"""Velum Forge Architectural / Landmark Builder — {title} (`kind={kind}`, `{width_m} m` frontage).

Prompt: {prompt}
Reference Palette: {pal}
"""
from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if "{bl_engine}" not in sys.path:
    sys.path.insert(0, "{bl_engine}")

from vflib import core, gameready, integrity, mats, quadflow, refs  # noqa: E402

# Multi-datum elevation constants (meters, +Y forward, +Z up)
Z_ROAD = 0.000
Z_SW = 0.152
Z_FLOOR_INT = Z_SW + 0.025
W_EXT = {width_m:.4f}
D_EXT = {depth_m:.4f}
H_EXT = {height_m:.4f}


def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        d = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(d)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def _clear_obstacles(xy: tuple[float, float], r_item: float, obstacles: list[tuple[float, float, float]], margin: float = 0.12) -> bool:
    return all(((xy[0] - ox) ** 2 + (xy[1] - oy) ** 2) ** 0.5 >= (r_item + orad + margin) for ox, oy, orad in obstacles)


def build_all(collection_name: str = "{pascal}", clear_scene: bool = True, mat_override: dict | None = None):
    if clear_scene:
        clear_scene_and_setup_units()
    root_col = core.fresh_collection(collection_name)
    col_arch = quadflow.sub_collection("Architecture_Shell", root_col)
    col_int = quadflow.sub_collection("Interior_Bar_And_Decor", root_col)
    col_patio = quadflow.sub_collection("Patio_Furniture", root_col)
    col_bot = quadflow.sub_collection("Botanicals", root_col)

    ov = mat_override or {{}}
    m_stucco = ov.get("Facade") or mats.pbr("{pascal}_Facade", color="{c_belly}", roughness=0.72, metallic=0.0)
    m_sw = ov.get("Sidewalk") or mats.pbr("{pascal}_Sidewalk", color="#C4B6AA", roughness=0.84, metallic=0.0)
    m_awn = ov.get("Awning") or mats.pbr("{pascal}_Awning", color="{c_primary}", roughness=0.86, metallic=0.0)
    if m_awn.node_tree is not None:
        bsdf = m_awn.node_tree.nodes.get("Principled BSDF")
        if bsdf and "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.07
    m_wood = ov.get("Furniture") or mats.pbr("{pascal}_Wood", color="#5B3922", roughness=0.42, metallic=0.0)
    m_brass = ov.get("Brass") or mats.pbr("{pascal}_Brass", color="{c_secondary}", roughness=0.22, metallic=0.92)
    m_art = ov.get("Art") or mats.pbr("{pascal}_Art", color="#1E293B", roughness=0.38, metallic=0.05)
    m_leaf = ov.get("Botanical") or mats.pbr("{pascal}_Botanical", color="#2B6130", roughness=0.52, metallic=0.0)
    m_bloom = mats.pbr("{pascal}_Bloom", color="#C22564", roughness=0.55, metallic=0.0)

    # 1. Sidewalk & Curb Base + Facade Shell (+Y forward!) + Interior Floor Slab + Upper Story
    bm_sw = bmesh.new()
    quadflow.add_box_bounds(bm_sw, -0.58 * W_EXT, 0.58 * W_EXT, -0.55 * D_EXT, 0.65 * D_EXT, Z_ROAD, Z_SW, mat_idx=0)
    sw_ob = quadflow.finalize_part(bm_sw, "Sidewalk_Terrace", col_arch, mats=[m_sw], smooth=False, asset_set="street_curbs")

    bm_sh = bmesh.new()
    quadflow.add_box_bounds(bm_sh, -0.45 * W_EXT, 0.45 * W_EXT, -0.48 * D_EXT, 0.0, Z_SW - 0.002, Z_FLOOR_INT, mat_idx=0)
    quadflow.add_box_bounds(bm_sh, -0.45 * W_EXT, 0.45 * W_EXT, -0.48 * D_EXT, -0.42 * D_EXT, Z_FLOOR_INT - 0.003, Z_SW + H_EXT * 0.62 + 0.003, mat_idx=0)
    quadflow.add_box_bounds(bm_sh, -0.45 * W_EXT, -0.41 * W_EXT, -0.417 * D_EXT, 0.0, Z_FLOOR_INT - 0.003, Z_SW + H_EXT * 0.62 + 0.003, mat_idx=0)
    quadflow.add_box_bounds(bm_sh, 0.41 * W_EXT, 0.45 * W_EXT, -0.417 * D_EXT, 0.0, Z_FLOOR_INT - 0.003, Z_SW + H_EXT * 0.62 + 0.003, mat_idx=0)
    quadflow.add_box_bounds(bm_sh, -0.452 * W_EXT, 0.452 * W_EXT, -0.482 * D_EXT, 0.002, Z_SW + H_EXT * 0.62, Z_SW + H_EXT, mat_idx=0)
    sh_ob = quadflow.finalize_part(bm_sh, "Building_Facade_Shell", col_arch, mats=[m_stucco], smooth=False, asset_set="facade")

    bm_awn = bmesh.new()
    quadflow.add_box(bm_awn, (0.0, 0.78, Z_SW + H_EXT * 0.54), (0.86 * W_EXT, 1.65, 0.08), mat_idx=0, rot_euler=(math.radians(-14.0), 0.0, 0.0))
    awn_ob = quadflow.finalize_part(bm_awn, "Storefront_Awning", col_arch, mats=[m_awn], smooth=False, asset_set="awnings")

    # 2. 3D Interior Bar Counter, Speed Footrail & 45-deg Mitered Art Frame facing +Y
    bm_bar = bmesh.new()
    quadflow.add_quad_grid_box(bm_bar, (0.0, -0.24 * D_EXT, Z_FLOOR_INT + 0.52 + 0.0016), (0.48 * W_EXT, 0.68, 1.04), segs=(4, 2, 2), radius=0.015, mat_idx=0)
    quadflow.add_torus_ring(bm_bar, (0.0, -0.24 * D_EXT + 0.46, Z_FLOOR_INT + 0.18), 0.18, 0.016, major_segs=24, minor_segs=10, axis=(0, 1, 0), mat_idx=1)
    quadflow.add_spline_tube(bm_bar, [(-0.22 * W_EXT, -0.24 * D_EXT + 0.46, Z_FLOOR_INT + 0.18), (0.22 * W_EXT, -0.24 * D_EXT + 0.46, Z_FLOOR_INT + 0.18)], 0.018, segs=16, mat_idx=1)
    bar_ob = quadflow.finalize_part(bm_bar, "Interior_Bar_Counter", col_int, mats=[m_wood, m_brass], asset_set="interior_bar")

    bm_art = bmesh.new()
    quadflow.add_mitered_frame(bm_art, (0.0, -0.42 * D_EXT + 0.014, Z_FLOOR_INT + 1.85), 1.35, 0.92, facing_axis="+Y", mat_idx=0)
    quadflow.add_uv_mapped_sign_plate(bm_art, (0.0, -0.42 * D_EXT + 0.014, Z_FLOOR_INT + 1.85), 1.26, 0.83, thickness=0.018, facing_axis="+Y", mat_front=1, mat_back=0)
    art_ob = quadflow.finalize_part(bm_art, "Interior_Mitered_Artwork", col_int, mats=[m_brass, m_art], asset_set="interior_art")

    # 3. Structured Quad-Flow Bistro Table & Chair Prototype Meshes (linked instances!)
    bm_tbl = bmesh.new()
    quadflow.add_revolved_profile(
        bm_tbl,
        [
            (0.0, 0.004), (0.14, 0.004), (0.21, 0.002), (0.235, 0.0), (0.24, 0.004),
            (0.23, 0.03), (0.12, 0.05), (0.04, 0.07),
            (0.036, 0.28), (0.034, 0.50), (0.032, 0.72),
            (0.14, 0.73), (0.06, 0.73), (0.0, 0.73),
        ],
        segs=28, mat_idx=1,
    )
    quadflow.add_revolved_ring(bm_tbl, (0.0, 0.0, 0.732), 0.0, 0.36, 0.032, segs=32, bevel=0.008, mat_idx=0)
    tbl_mesh = quadflow.finalize_mesh_data(bm_tbl, "BistroTable_QuadFlow", mats=[m_wood, m_brass])

    bm_chr = bmesh.new()
    quadflow.add_revolved_ring(bm_chr, (0.0, 0.0, 0.45), 0.0, 0.205, 0.032, segs=24, bevel=0.006, mat_idx=0)
    quadflow.add_torus_ring(bm_chr, (0.0, 0.0, 0.20), 0.174, 0.011, major_segs=24, minor_segs=10, mat_idx=0)
    for ang_deg in (42, 138, 222, 318):
        a = math.radians(ang_deg)
        quadflow.add_cylinder(bm_chr, (0.18 * math.cos(a), 0.18 * math.sin(a), 0.0015), (0.17 * math.cos(a), 0.17 * math.sin(a), 0.45), 0.013, 0.012, segs=12, mat_idx=0)
    quadflow.add_spline_tube(bm_chr, [(-0.135, -0.135, 0.44), (-0.135, -0.175, 0.76), (0.0, -0.185, 0.87), (0.135, -0.175, 0.76), (0.135, -0.135, 0.44)], 0.013, segs=12, mat_idx=0)
    chr_mesh = quadflow.finalize_mesh_data(bm_chr, "BistroChair_QuadFlow", mats=[m_wood])

    # 4. Deterministic Obstacle Clearances & Front (+Y) Patio Placement
    obstacles = [(-0.42 * W_EXT, 0.05, 0.35), (0.42 * W_EXT, 0.05, 0.35)]
    meshes = [sw_ob, sh_ob, awn_ob, bar_ob, art_ob]
    n_sets = max(2, min(5, int(W_EXT // 2.8)))
    for i in range(n_sets):
        tx = -0.32 * W_EXT + (i / max(1, n_sets - 1)) * (0.64 * W_EXT)
        ty = 0.28 * D_EXT
        if _clear_obstacles((tx, ty), 0.75, obstacles):
            obstacles.append((tx, ty, 0.75))
            meshes.append(quadflow.spawn_instance(f"Patio_Table_{{i+1}}", tbl_mesh, col_patio, loc=(tx, ty, Z_SW), asset_set="patio_tables"))
            meshes.append(quadflow.spawn_instance(f"Patio_Chair_{{i+1}}L", chr_mesh, col_patio, loc=(tx - 0.56, ty, Z_SW), rot=(0, 0, -0.5 * math.pi), asset_set="patio_chairs"))
            meshes.append(quadflow.spawn_instance(f"Patio_Chair_{{i+1}}R", chr_mesh, col_patio, loc=(tx + 0.56, ty, Z_SW), rot=(0, 0, 0.5 * math.pi), asset_set="patio_chairs"))

    # 5. Realistic 3D Curved Planter Botanicals + Stem Connections
    bm_bot = bmesh.new()
    for px in (-0.43 * W_EXT, 0.43 * W_EXT):
        py = 0.15 * D_EXT
        quadflow.add_revolved_profile(bm_bot, [(0.0, Z_SW + 0.004), (0.18, Z_SW + 0.004), (0.215, Z_SW), (0.22, Z_SW + 0.004), (0.28, Z_SW + 0.48), (0.25, Z_SW + 0.48), (0.21, Z_SW + 0.42), (0.0, Z_SW + 0.42)], segs=24, center=(px, py, 0.0), mat_idx=0)
        quadflow.add_cylinder(bm_bot, (px, py, Z_SW + 0.40), (px, py, Z_SW + 0.72), 0.025, 0.012, segs=10, mat_idx=0)
        for k in range(7):
            ang = (2.0 * math.pi * k) / 7.0
            lz = Z_SW + 0.45 + 0.024 * k
            quadflow.add_curved_leaf(bm_bot, (px + 0.008 * math.cos(ang), py + 0.008 * math.sin(ang), lz), (math.cos(ang), math.sin(ang), 0.38), length=0.40, width=0.075, mat_idx=0)
        quadflow.add_bougainvillea_cluster(bm_bot, (px, py, Z_SW + 0.70), radius=0.05, bract_mat_idx=1, stamen_mat_idx=1)
    bot_ob = quadflow.finalize_part(bm_bot, "Corner_Planters_3D_Botanicals", col_bot, mats=[m_leaf, m_bloom], asset_set="botanicals")
    meshes.append(bot_ob)

    quadflow.ground_objects_safe(meshes, target_z=Z_ROAD)
    refs.load_references(THIS_DIR, subject_objects=meshes)
    gameready.validate(meshes, max_tris={2_000_000 if hp_on else 300000}, deduplicate_meshes=True)
    return root_col, meshes


def main() -> int:
    _, meshes = build_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "{slug}.blend"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(THIS_DIR, "{slug}.glb"), export_format="GLB", export_apply=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            encoding="utf-8",
        )
        bake_py.write_text(
            f'''"""Velum Forge Dedicated {int(bake_res)}x{int(bake_res)} Per-Set Cycles Bake, 4 Variants & Instance LOD0-LOD3 for {title}."""
from __future__ import annotations

import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (THIS_DIR, "{bl_engine}"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from vflib import bake, core, export, lod, mats, render  # noqa: E402
import build_{slug} as builder  # noqa: E402

BAKE_RES = {int(bake_res)}
VARIANTS = [
    ("reference_match", "{c_primary}", "{c_secondary}"),
    ("ocean_dr_mint", "#7BB59D", "#D4AF37"),
    ("sunset_coral_deco", "#E07A5F", "#F2CC8F"),
    ("midnight_bistro", "#1D3557", "#E6B86A"),
]


def main() -> int:
    builder.clear_scene_and_setup_units()
    col, meshes = builder.build_all(clear_scene=False)
    bake.enable_cycles_gpu(bpy.context.scene)

    groups = bake.group_objects_by_asset_set(meshes)
    tex_dir = os.path.join(THIS_DIR, "textures")
    os.makedirs(tex_dir, exist_ok=True)

    # Single-pack UVs once per vf_asset_set so all variants and LODs share exact UVs
    for _skey, g_objs in groups.items():
        bake.prepare_dedicated_set_uvs(g_objs)

    flagship_tex_sets = {{}}
    flagship_mats_by_set = {{}}
    variant_reports = {{}}
    re_bake_variant_sets = {{"facade", "awnings", "interior_bar", "patio_tables"}}

    for vidx, (vid, c1, c2) in enumerate(VARIANTS):
        v_tex_sets = {{}}
        for skey, g_objs in groups.items():
            if vidx > 0 and skey not in re_bake_variant_sets:
                v_tex_sets[skey] = dict(flagship_tex_sets[skey])
                continue
            for o in bake.unique_mesh_reps(g_objs):
                for m in o.data.materials:
                    if m and m.node_tree is not None:
                        bsdf = m.node_tree.nodes.get("Principled BSDF")
                        if bsdf and ("Awning" in m.name or "Facade" in m.name):
                            mats.set_in(bsdf, "Base Color", mats.linear(c1 if "Awning" in m.name else "{c_belly}"))
                        elif bsdf and "Brass" in m.name:
                            mats.set_in(bsdf, "Base Color", mats.linear(c2))
            shared_nc = flagship_tex_sets.get(skey) if vidx > 0 else None
            paths = bake.bake_pbr_set(
                g_objs, tex_dir, f"T_{pascal}_{{vid}}_{{skey}}",
                res=BAKE_RES, samples=32, isolate_for_ao=True, cooldown_s=0.4,
                shared_non_color=shared_nc,
            )
            v_tex_sets[skey] = paths
            if vidx == 0:
                mat = bake.make_baked_pbr_material(f"Baked_{pascal}_{{skey}}", paths)
                flagship_tex_sets[skey] = paths
                flagship_mats_by_set[skey] = mat
        variant_reports[vid] = {{"color": c1, "accent": c2, "textures": v_tex_sets}}

    for skey, g_objs in groups.items():
        bake.assign_baked_and_strip_graphic_uv(g_objs, flagship_mats_by_set[skey])

    lod_summary = lod.build_lod_chain(
        meshes, os.path.join(THIS_DIR, "lods"), "{slug}",
        collection_prefix="{pascal}", planar_sets={{"facade", "awnings", "street_curbs"}},
    )
    specs = [dict(name=o.name, objects=[o], role="baked_solid", texture_set=o.get("vf_asset_set")) for o in meshes]
    export.export_roblox(
        "{pascal}", os.path.join(THIS_DIR, "roblox"), specs,
        source_collection=col, prebaked_texture_sets=flagship_tex_sets,
        prebaked_materials_by_set=flagship_mats_by_set, max_tris={2_000_000 if hp_on else 300000},
    )

    for l_idx in (1, 2, 3):
        lc = bpy.data.collections.get(f"{pascal}_LOD{{l_idx}}")
        if lc:
            lc.hide_render = True
            lc.hide_viewport = True

    sc = bpy.context.scene
    sc.cycles.samples = 64
    st = render.setup_studio(meshes, backdrop="outdoor")
    lo, hi = core.world_bbox(meshes)
    ctr = (lo + hi) * 0.5
    rad = max((hi - lo).length * 0.5, 1.0)
    cd = bpy.data.cameras.new("VF_HeroCam")
    cm = bpy.data.objects.new("VF_HeroCam", cd)
    st.objects.link(cm)
    sc.camera = cm
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    cm.location = ctr + Vector((rad * 1.15, rad * 1.55, rad * 0.45))
    cm.data.lens = 35.0
    cm.rotation_euler = (ctr - cm.location).to_track_quat("-Z", "Y").to_euler()
    os.makedirs(os.path.join(THIS_DIR, "renders"), exist_ok=True)
    out_hero = os.path.join(THIS_DIR, "renders", "blender-render-check.png")
    bake.render_still_safe(sc, out_hero)
    core.clear_collection(st)
    bpy.data.collections.remove(st)

    master_blend = os.path.join(THIS_DIR, "{slug}_variants_lods.blend")
    bpy.ops.wm.save_as_mainfile(filepath=master_blend)
    rep = {{
        "ok": True,
        "asset": "{slug}",
        "kind": "{kind}",
        "bake_res": BAKE_RES,
        "lods": lod_summary,
        "variants": variant_reports,
    }}
    with open(os.path.join(THIS_DIR, "variants_and_lods_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            encoding="utf-8",
        )
        return {
            "slug": slug,
            "dir": str(asset_dir),
            "spec": str(spec_path),
            "build_script": str(build_py),
            "bake_script": str(bake_py),
        }
    else:
        beam_ratio = 0.34 if kind == "boat" else 0.58
        height_ratio = 0.28 if kind == "boat" else 0.48
        build_py.write_text(
            f'''"""Velum Forge Reference-Calibrated 3D Asset — {title} (`{length_m} m`, `kind={kind}`).

Prompt: {prompt}
Reference Palette: {pal}
"""
from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if "{bl_engine}" not in sys.path:
    sys.path.insert(0, "{bl_engine}")

from vflib import core, gameready, integrity, mats, refs  # noqa: E402

LOA = {float(length_m):.4f}
BEAM = LOA * {beam_ratio}
HEIGHT = LOA * {height_ratio}


def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        d = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(d)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def _unwrap_clean(ob: bpy.types.Object) -> None:
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.012, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.010)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


def _make_part(bm: bmesh.types.BMesh, name: str, col: bpy.types.Collection, mat: bpy.types.Material) -> bpy.types.Object:
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    integrity.ensure_positive_signed_volume(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob["sc_part"] = name
    ob["sc_role"] = "solid"
    _unwrap_clean(ob)
    return ob


def build_all(collection_name: str = "{pascal}", clear_scene: bool = True, mat_override: dict | None = None):
    if clear_scene:
        clear_scene_and_setup_units()
    col = core.fresh_collection(collection_name)
    m_hull = (mat_override or {{}}).get("Hull") or mats.pbr("{pascal}_Primary", color="{c_primary}", roughness=0.18, metallic=0.12)
    m_deck = (mat_override or {{}}).get("Deck") or mats.pbr("{pascal}_Secondary", color="{c_belly}", roughness=0.35, metallic=0.05)
    m_acc = (mat_override or {{}}).get("Accent") or mats.pbr("{pascal}_Accent", color="{c_accent}", roughness=0.22, metallic=0.65)

    bm_h = bmesh.new()
    rings = []
    for i in range(1, 56):
        t = i / 56.0
        y = -0.5 * LOA + t * LOA
        w_t = 0.5 * BEAM * math.pow(math.sin(math.pi * min(1.0, (1.0 - t) * 1.15 if t > 0.35 else 0.72 + 0.28 * (t / 0.35))), 0.65)
        w_t = max(0.01 * LOA, w_t)
        z_keel = HEIGHT * 0.28 * (max(0.0, (t - 0.55) / 0.45) ** 2.0)
        z_sheer = HEIGHT * (0.76 + 0.24 * (t ** 1.4))
        ring = []
        for j in range(32):
            th = (2.0 * math.pi * j) / 32.0
            zn = 0.5 * (1.0 + math.cos(th))
            x = w_t * math.sin(th) * (0.55 + 0.45 * zn)
            z = z_keel + (z_sheer - z_keel) * zn
            ring.append(bm_h.verts.new(Vector((x, y, z))))
        rings.append(ring)
    va = bm_h.verts.new(Vector((0, -0.5 * LOA - 0.01, HEIGHT * 0.45)))
    vb = bm_h.verts.new(Vector((0, 0.5 * LOA + 0.01, HEIGHT * 0.96)))
    for j in range(32):
        jn = (j + 1) % 32
        bm_h.faces.new((va, rings[0][jn], rings[0][j]))
        bm_h.faces.new((rings[-1][j], rings[-1][jn], vb))
    for i in range(len(rings) - 1):
        for j in range(32):
            jn = (j + 1) % 32
            bm_h.faces.new((rings[i][j], rings[i][jn], rings[i + 1][jn], rings[i + 1][j]))
    hull = _make_part(bm_h, "Hull", col, m_hull)

    bm_c = bmesh.new()
    bmesh.ops.create_cube(bm_c, size=1.0)
    bmesh.ops.scale(bm_c, vec=Vector((BEAM * 0.42, LOA * 0.22, HEIGHT * 0.65)), verts=bm_c.verts[:])
    bmesh.ops.translate(bm_c, vec=Vector((0.0, LOA * 0.04, HEIGHT * 0.92)), verts=bm_c.verts[:])
    bmesh.ops.bevel(bm_c, geom=bm_c.edges[:], offset=min(BEAM, HEIGHT) * 0.05, segments=3, affect="EDGES")
    console = _make_part(bm_c, "Console", col, m_deck)

    bm_m = bmesh.new()
    bmesh.ops.create_cube(bm_m, size=1.0)
    bmesh.ops.scale(bm_m, vec=Vector((BEAM * 0.22, LOA * 0.10, HEIGHT * 0.58)), verts=bm_m.verts[:])
    bmesh.ops.translate(bm_m, vec=Vector((0.0, -0.5 * LOA - LOA * 0.03, HEIGHT * 0.65)), verts=bm_m.verts[:])
    bmesh.ops.bevel(bm_m, geom=bm_m.edges[:], offset=min(BEAM, HEIGHT) * 0.04, segments=3, affect="EDGES")
    motor = _make_part(bm_m, "Hardware", col, m_acc)

    meshes = [hull, console, motor]
    lo, _ = core.world_bbox(meshes)
    if abs(lo.z) > 1e-7:
        for o in meshes:
            o.data.transform(Matrix.Translation((0, 0, -lo.z)))
            o.data.update()

    refs.load_references(THIS_DIR, subject_objects=meshes)
    gameready.validate(meshes)
    return col, meshes


def main() -> int:
    _, meshes = build_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "{slug}.blend"))
    bpy.ops.export_scene.gltf(filepath=os.path.join(THIS_DIR, "{slug}.glb"), export_format="GLB", export_apply=True)
    return 0


if __name__ == "__main__":
    main()
''',
            encoding="utf-8",
        )

    # Write complete 4-Variant + 4-Tier LOD + Studio Showcase Renderer script (`bake_lod_variants.py`)
    bake_py.write_text(
        f'''"""Velum Forge 4-Variant Showcase, LOD0-LOD3 & Render Generator for {title}."""
from __future__ import annotations

import json
import os
import shutil
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (THIS_DIR, "{bl_engine}"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from vflib import bake, core, lod, mats, render  # noqa: E402
import build_{slug} as builder  # noqa: E402

VARIANTS = [
    ("reference_match", "{c_primary}", "{c_secondary}"),
    ("cobalt_edition", "#0F4C81", "#38BDF8"),
    ("crimson_sport", "#881337", "#F59E0B"),
    ("gold_legendary", "#D97706", "#FEF08A"),
]


def main() -> int:
    builder.clear_scene_and_setup_units()
    variant_cols = {{}}
    flagship_parts = {{}}
    lod_summary = {{}}

    for idx, (vid, c1, c2) in enumerate(VARIANTS):
        m_ov = {{
            "Body": mats.pbr(f"{{vid}}_body", color=c1, roughness=0.22, metallic=0.32),
            "Fins": mats.pbr(f"{{vid}}_fins", color=c2, roughness=0.28, metallic=0.22),
            "Hull": mats.pbr(f"{{vid}}_hull", color=c1, roughness=0.18, metallic=0.15),
            "Deck": mats.pbr(f"{{vid}}_deck", color="{c_belly}", roughness=0.34, metallic=0.05),
            "Accent": mats.pbr(f"{{vid}}_accent", color=c2, roughness=0.22, metallic=0.65),
        }}
        vcol, meshes = builder.build_all(collection_name=f"Variant_{{vid}}", clear_scene=False, mat_override=m_ov)
        for o in meshes:
            o.name = f"{pascal}_{{vid}}_{{o['sc_part']}}"
            o.data.name = o.name
        p_objs = {{o["sc_part"]: o for o in meshes}}
        variant_cols[vid] = vcol

        v_dir = os.path.join(THIS_DIR, "variants", vid)
        os.makedirs(v_dir, exist_ok=True)
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.export_scene.gltf(filepath=os.path.join(v_dir, f"{slug}_{{vid}}.glb"), use_selection=True, export_format="GLB", export_apply=True)
        for o in meshes:
            o.select_set(False)

        if idx == 0:
            flagship_parts = p_objs
            lod_summary = lod.build_lod_chain(flagship_parts, os.path.join(THIS_DIR, "lods"), "{slug}", collection_prefix="{pascal}")

    lo, hi = core.world_bbox(list(flagship_parts.values()))
    span_x = max((hi.x - lo.x) * 2.25, (hi.y - lo.y) * 0.42, 0.25)
    all_m = []
    for idx, (vid, vcol) in enumerate(variant_cols.items()):
        dx = (idx - 1.5) * span_x
        for o in vcol.objects:
            o.location.x += dx
            if o.type == "MESH":
                all_m.append(o)
    bpy.context.view_layer.update()

    for l_idx in (1, 2, 3):
        lc = bpy.data.collections.get(f"{pascal}_LOD{{l_idx}}")
        if lc:
            lc.hide_render = True
            lc.hide_viewport = True

    sc = bpy.context.scene
    bake.enable_cycles_gpu(sc)
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    st = render.setup_studio(all_m, backdrop="product")
    lo_all, hi_all = core.world_bbox(all_m)
    ctr = (lo_all + hi_all) * 0.5
    rad = max((hi_all - lo_all).length * 0.5, 0.3)
    cd = bpy.data.cameras.new("VF_LineupCam")
    cm = bpy.data.objects.new("VF_LineupCam", cd)
    st.objects.link(cm)
    sc.camera = cm
    sc.render.resolution_x = 1800
    sc.render.resolution_y = 1012
    cm.location = ctr + Vector((rad * 1.15, rad * 1.75, rad * 0.68))
    cm.data.lens = 35.0
    cm.rotation_euler = (ctr - cm.location).to_track_quat("-Z", "Y").to_euler()
    out_lineup = os.path.join(THIS_DIR, "renders", "variants_lineup.png")
    bake.render_still_safe(sc, out_lineup)
    core.clear_collection(st)
    bpy.data.collections.remove(st)

    master_blend = os.path.join(THIS_DIR, "{slug}_variants_lods.blend")
    bpy.ops.wm.save_as_mainfile(filepath=master_blend)
    os.makedirs(core.DESIGN_OUTPUT_DIR, exist_ok=True)
    shutil.copy2(master_blend, os.path.join(core.DESIGN_OUTPUT_DIR, "{slug}.blend"))
    shutil.copy2(out_lineup, os.path.join(core.DESIGN_OUTPUT_DIR, "blender-render-check.png"))

    rep = {{
        "ok": True,
        "asset": "{slug}",
        "bake_res": 2048,
        "lods": lod_summary,
        "variants": {{vid: {{"color": c1, "accent": c2}} for vid, c1, c2 in VARIANTS}},
    }}
    with open(os.path.join(THIS_DIR, "variants_and_lods_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )

    return {
        "slug": slug,
        "dir": str(asset_dir),
        "spec": str(spec_path),
        "build_script": str(build_py),
        "bake_script": str(bake_py),
    }


def build_ai_cli_invocation(engine_id: str, asset_dir: Path, *, next_iteration: bool = False) -> list[str] | None:
    """Return non-interactive command line to run `claude`, `codex`, or `gemini` on `<asset_dir>`."""
    clis = {c["id"]: c for c in detect_ai_clis()}
    if engine_id == "auto":
        chosen = next((c for c in detect_ai_clis() if c["installed"]), None)
    else:
        c_item = clis.get(engine_id)
        chosen = c_item if (c_item and c_item["installed"]) else None

    if not chosen or not chosen["exe"]:
        return None

    if next_iteration:
        from .review import build_next_iteration_prompt

        brief = build_next_iteration_prompt(asset_dir)
    else:
        brief = build_agent_handoff_prompt(asset_dir)

    exe = str(chosen["exe"])
    cid = chosen["id"]

    if cid == "claude":
        return [exe, "-p", brief, "--dangerously-skip-permissions"]
    if cid == "codex":
        return [exe, "exec", "--full-auto", brief]
    if cid == "gemini":
        return [exe, "-p", brief, "-y"]
    return None
