"""Unified `vforge` CLI for Velum Forge (Generate, Perspective/Ortho Refs, QA, Optional Review Loop, Bake & Studio)."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import CAD_ENGINE_DIR, EXAMPLES_DIR, REPO_ROOT, __version__
from .bake_guard import (
    build_safe_blender_bake_cmd,
    build_safe_cycles_env,
    default_safe_threads,
    gpu_bake_lock,
    windows_creationflags,
)
from .doctor import find_blender_exe, find_venv_python, install_ai_integrations, run_doctor, set_custom_blender_exe
from .generator import build_agent_handoff_prompt, build_ai_cli_invocation, generate_parametric_scripts, slugify
from .references import stage_local_reference_files, sync_references_into_spec
from .review import (
    build_next_iteration_prompt,
    get_review_config,
    load_review_history,
    record_iteration_review,
    set_review_config,
    snapshot_iteration_renders,
)
from .scaffold import scaffold_asset
from .studio_server import launch_studio


def _run_qa_cli(
    asset_path: str,
    profile: str = "auto",
    forward_axis: str = "+Y",
    ref_path: str = "",
    fast: bool = False,
    ortho_grid: bool = False,
    snapshot_iteration: bool = False,
    threads: int | None = None,
    device: str = "auto",
    user_addons: bool = False,
    max_tris: int | None = None,
    high_poly: bool = False,
) -> int:
    t_count = max(1, int(threads if threads is not None else default_safe_threads()))
    asset_p = Path(asset_path).resolve()
    asset_dir = asset_p.parent
    spec: dict = {}
    if (asset_dir / "asset_spec.json").is_file():
        try:
            spec = json.loads((asset_dir / "asset_spec.json").read_text(encoding="utf-8-sig"))
        except Exception:
            spec = {}

    is_high_poly = bool(high_poly or spec.get("high_poly_uncapped", False))
    if profile == "auto":
        resolved_profile = str(spec.get("qa_profile") or ("game" if is_high_poly else "roblox"))
        if is_high_poly and resolved_profile == "roblox":
            resolved_profile = "game"
    else:
        resolved_profile = profile

    if max_tris is not None:
        resolved_max_tris = int(max_tris)
    elif is_high_poly:
        resolved_max_tris = 0
    elif spec.get("qa_max_tris") is not None:
        resolved_max_tris = int(spec["qa_max_tris"])
    else:
        resolved_max_tris = 300000

    if platform.system() == "Windows":
        ps_exe = shutil.which("powershell") or "powershell.exe"
        cmd = [
            ps_exe,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(CAD_ENGINE_DIR / "run_qa.ps1"),
            "-Asset",
            asset_path,
            "-Profile",
            resolved_profile,
            "-MaxTris",
            str(resolved_max_tris),
            "-ForwardAxis",
            forward_axis,
            "-Threads",
            str(t_count),
            "-Device",
            device,
        ]
        if is_high_poly:
            cmd.append("-HighPoly")
        if ref_path:
            cmd.extend(["-Ref", ref_path])
        if fast:
            cmd.append("-Fast")
        if ortho_grid:
            cmd.append("-OrthoGrid")
        if snapshot_iteration:
            cmd.append("-SnapshotIteration")
        if user_addons:
            cmd.append("-UserAddons")
        return subprocess.call(cmd, cwd=str(REPO_ROOT))

    # Cross-platform macOS / Linux path: run Blender QA pipeline + compose_sheet.py + optional snapshot
    blender_exe = find_blender_exe() or "blender"
    out_d = REPO_ROOT / ".qa-out" / asset_p.stem
    out_d.mkdir(parents=True, exist_ok=True)
    safe_env = build_safe_cycles_env(threads=t_count, device=device, cooldown=0.0, tile_size=512)

    b_cmd = [blender_exe, "-b"]
    if not user_addons:
        b_cmd.append("--factory-startup")
    b_cmd.extend([
        "-t",
        str(t_count),
        "--python-exit-code",
        "1",
        "-P",
        str(REPO_ROOT / "engine" / "blender" / "qa_pipeline.py"),
        "--",
        "--input",
        str(asset_p),
        "--out-dir",
        str(out_d),
        "--profile",
        resolved_profile,
        "--max-tris",
        str(resolved_max_tris),
        "--forward-axis",
        forward_axis,
    ])
    if is_high_poly:
        b_cmd.append("--high-poly")
    if fast:
        b_cmd.append("--fast")
    if ortho_grid:
        b_cmd.append("--ortho-grid")
    if (asset_dir / "asset_spec.json").is_file():
        b_cmd.extend(["--spec", str(asset_dir / "asset_spec.json")])

    rc = subprocess.call(b_cmd, cwd=str(REPO_ROOT), env=safe_env)
    if rc != 0:
        return rc

    py = find_venv_python()
    c_cmd = [
        py,
        str(CAD_ENGINE_DIR / "compose_sheet.py"),
        "--manifest",
        str(out_d / "render_manifest.json"),
        "--qa-json",
        str(out_d / "qa_report.json"),
        "--out-material",
        str(out_d / "contact_sheet_material.png"),
        "--out-diagnostic",
        str(out_d / "contact_sheet_diagnostic.png"),
        "--out-ref",
        str(out_d / "ref_comparison.png"),
    ]
    if ortho_grid:
        c_cmd.append("--ortho-grid")
    if ref_path:
        c_cmd.extend(["--ref", str(Path(ref_path).resolve())])
    if (asset_dir / "references").is_dir():
        c_cmd.extend(["--ref-dir", str(asset_dir / "references")])
    if (asset_dir / "reviews" / "review_history.json").is_file():
        c_cmd.extend(["--review-history", str(asset_dir / "reviews" / "review_history.json")])

    rc_c = subprocess.call(c_cmd, cwd=str(REPO_ROOT))
    if rc_c != 0:
        return rc_c

    renders_dir = asset_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    for src_name, dst_name in (
        ("contact_sheet_material.png", "qa_contact_material.png"),
        ("contact_sheet_diagnostic.png", "qa_contact_diagnostic.png"),
        ("ref_comparison.png", "ref_comparison.png"),
        ("qa_report.json", "qa_report.json"),
    ):
        sp = out_d / src_name
        if sp.is_file():
            shutil.copy2(sp, renders_dir / dst_name)
    for rc_tile in out_d.glob("tile_refcam_*.png"):
        shutil.copy2(rc_tile, renders_dir / rc_tile.name.replace("tile_", "", 1))

    if snapshot_iteration:
        snapshot_iteration_renders(asset_dir)
    return 0


def _parse_rubric_kv(items: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        try:
            out[k.strip()] = float(v.strip())
        except ValueError:
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vforge",
        description="Velum Forge — Perspective & Ortho Reference 3D CAD, Cycles PBR Baking, Optional Rating Reviews & Studio",
    )
    parser.add_argument("--version", action="version", version=f"velum-forge {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    # 1. GENERATE
    p_gen = sub.add_parser("generate", help="Generate a 3D asset from a prompt + optional reference images!")
    p_gen.add_argument("name", help="Asset name or slug (e.g. 'red_snapper', 'ocean_dr_800', or 'patrol_rib_28')")
    p_gen.add_argument("--prompt", default="", help="Detailed natural-language description of proportions, parts & materials")
    p_gen.add_argument("--kind", default="fish", choices=["fish", "boat", "building", "arch", "prop", "cad"], help="3D archetype")
    p_gen.add_argument("--length", type=float, default=1.20, help="Target real-world length/frontage in meters (default: 1.20)")
    p_gen.add_argument("--profile", default="auto", choices=["auto", "roblox", "game", "render", "print"], help="QA profile ('auto' uses 'game' for building/arch, 'roblox' otherwise)")
    p_gen.add_argument("--bake-res", type=int, default=2048, help="Per-set PBR bake resolution (default: 2048)")
    p_gen.add_argument("--ref", action="append", default=[], help="Reference image path(s) — repeat --ref for multiple angles")
    p_gen.add_argument("--ref-view", default="auto", help="Reference view tag (auto, hero, street_view, closeup, ortho_side, ortho_front, ortho_top)")
    p_gen.add_argument("--ortho-grid", action="store_true", help="Enable optional metric blueprint grid (strictly for ortho blueprints)")
    p_gen.add_argument("--iterate", action="store_true", help="Enable optional Iterative Critic & Honest Rating Review Loop (always 10.0/10 target)")
    p_gen.add_argument("--rate-to-10", action="store_true", help="Enable Strict 10/10 Honest Rating Loop (do not rush or fake score)")
    p_gen.add_argument("--high-poly", action="store_true", help="Opt-in High-Poly Uncapped Mode (no 300k/20k tri caps + ArchViz segment floors)")
    p_gen.add_argument("--target-score", type=float, default=10.0, help="Target honest rating (locked at 10.0/10 strict)")
    p_gen.add_argument("--max-iterations", type=int, default=0, help="Iteration cap when --iterate is enabled (0 = unlimited until 10.0/10)")
    p_gen.add_argument("--allow-qa-warnings", action="store_true", help="Do not cap rating on QA warnings during iterative review")
    p_gen.add_argument("--focus-notes", default="", help="Optional review critic focus instructions")
    p_gen.add_argument("--engine", default="parametric", choices=["parametric", "claude", "codex", "gemini", "handoff"], help="Generation engine")
    p_gen.add_argument("--dir", default=str(EXAMPLES_DIR), help="Parent output directory")

    # 2. ADD-REF & BRIEF
    p_ref = sub.add_parser("add-ref", help="Attach reference image(s) to an asset folder and analyze palette/cameras")
    p_ref.add_argument("asset_dir", help="Target asset directory")
    p_ref.add_argument("images", nargs="+", help="One or more PNG/JPG/WebP reference images")
    p_ref.add_argument("--view", default="auto", help="View type (auto, hero, street_view, closeup, ortho_side, ortho_front, ortho_top)")
    p_ref.add_argument("--projection", default="auto", choices=["auto", "perspective", "ortho_blueprint"])
    p_ref.add_argument("--lens", type=float, default=None, help="Optional focal length in mm for perspective photos (e.g. 28, 35, 50)")

    p_brf = sub.add_parser("brief", help="Print the complete AI Agent Handoff Prompt (or Next-Iteration Critique Prompt)")
    p_brf.add_argument("asset_dir", help="Target asset directory")
    p_brf.add_argument("--next-iteration", action="store_true", help="Print the targeted Next-Iteration Defect Fix prompt instead")
    p_brf.add_argument("--rate-to-10", action=argparse.BooleanOptionalAction, default=None, help="Include or suppress strict 10/10 rating loop in printed brief")
    p_brf.add_argument("--high-poly", action=argparse.BooleanOptionalAction, default=None, help="Include or suppress High-Poly Uncapped Mode (no 300k cap) in printed brief")

    # 3. REVIEW (Optional Core Feature: Iterative Critic & Honest Rating Reviews)
    p_rev = sub.add_parser("review", help="Optional Iterative Critic & Honest Rating Review tools (config, snapshot, log, status, prompt)")
    rev_sub = p_rev.add_subparsers(dest="review_cmd")

    p_rcfg = rev_sub.add_parser("config", help="Enable/disable or configure the Iterative Review Loop for an asset")
    p_rcfg.add_argument("asset_dir", help="Target asset directory")
    grp_en = p_rcfg.add_mutually_exclusive_group()
    grp_en.add_argument("--enable", action="store_true", help="Enable Iterative Review & Rating mode (always 10.0/10 strict target)")
    grp_en.add_argument("--disable", action="store_true", help="Disable Iterative Review mode (single-pass)")
    p_rcfg.add_argument("--rate-to-10", action="store_true", help="Enable Strict 10/10 mode (always enforced when enabled)")
    p_rcfg.add_argument("--high-poly", action=argparse.BooleanOptionalAction, default=None, help="Toggle opt-in High-Poly Uncapped Mode (--max-tris 0) on this asset")
    p_rcfg.add_argument("--target", type=float, default=None, help="Target honest rating (locked at 10.0/10)")
    p_rcfg.add_argument("--max-iter", type=int, default=None, help="Optional iteration tracking cap (0 = unlimited; never approves below 10.0/10)")
    p_rcfg.add_argument("--allow-qa-warnings", action="store_true", help="Allow QA warnings without capping rating at 8.9")
    p_rcfg.add_argument("--require-zero-warnings", action="store_true", help="Require 0 QA warnings to approve")
    p_rcfg.add_argument("--focus", default=None, help="Custom critic focus notes")

    p_rsnap = rev_sub.add_parser("snapshot", help="Archive current renders/ & qa_report.json into reviews/iter_XX/")
    p_rsnap.add_argument("asset_dir", help="Target asset directory")
    p_rsnap.add_argument("--iteration", type=int, default=None, help="Explicit iteration number")

    p_rlog = rev_sub.add_parser("log", help="Log an Honest Iteration Review (rating, strengths, categorized defects)")
    p_rlog.add_argument("asset_dir", help="Target asset directory")
    p_rlog.add_argument("--score", type=float, default=None, help="Honest overall rating (0.0 - 10.0)")
    p_rlog.add_argument("--rubric", action="append", default=[], help="Rubric subscore key=val (repeatable)")
    p_rlog.add_argument("--summary", default="", help="Concise honest summary of this iteration")
    p_rlog.add_argument("--strength", action="append", default=[], help="Strength / win bullet (repeatable)")
    p_rlog.add_argument("--defect", action="append", default=[], help="Defect as 'Category|critical/major/minor|Description|Fix' (repeatable)")
    p_rlog.add_argument("--iteration", type=int, default=None, help="Explicit iteration number")
    p_rlog.add_argument("--json-file", default="", help="Optional JSON file containing review payload")
    p_rlog.add_argument("--no-snapshot", action="store_true", help="Skip snapshotting renders/ before logging")
    p_rlog.add_argument("--json", action="store_true", help="Output JSON instead of formatted Markdown review")

    p_rstat = rev_sub.add_parser("status", help="Show iteration rating history, trajectory & approval verdict")
    p_rstat.add_argument("asset_dir", help="Target asset directory")
    p_rstat.add_argument("--json", action="store_true")

    p_rprm = rev_sub.add_parser("prompt", help="Print the targeted Next-Iteration Defect Fix prompt for an AI agent")
    p_rprm.add_argument("asset_dir", help="Target asset directory")

    # 4. SYSTEM / STUDIO / QA / BAKE / INSPECT
    p_doc = sub.add_parser("doctor", help="Check Blender 5.2+, CAD B-Rep venv, GPU & AI agent plugins")
    p_doc.add_argument("--json", action="store_true")

    p_sb = sub.add_parser("set-blender", help="Manually set & persist custom blender.exe path in ~/.velum-forge/config.json")
    p_sb.add_argument("path", help="Path to blender.exe (or its installation folder)")

    p_ai = sub.add_parser("install-ai", help="Install Velum Forge plugin & skills into Antigravity, Claude Code & workspace")
    p_ai.add_argument("--workspace", default="", help="Optional project folder to populate .agents/skills & .cursor/rules")
    p_ai.add_argument("--no-antigravity", action="store_true")
    p_ai.add_argument("--no-claude", action="store_true")

    p_stu = sub.add_parser("studio", help="Launch the interactive Velum Forge Desktop Studio App")
    p_stu.add_argument("--port", type=int, default=8765)
    p_stu.add_argument("--no-open", action="store_true")

    sub.add_parser("setup-gui", help="Launch the Setup & Workflow Installer GUI")

    p_new = sub.add_parser("new", help="Scaffold a blank 3D asset generator (`boat`, `fish`, `building`, `arch`, `prop`, `cad`)")
    p_new.add_argument("kind", choices=["boat", "fish", "building", "arch", "prop", "cad"])
    p_new.add_argument("name", help="Asset name or slug")
    p_new.add_argument("--dir", default=str(EXAMPLES_DIR))

    p_qa = sub.add_parser("qa", help="Run the 10-view visual & geometric QA gate (+ matched perspective & multi-ref comparison)")
    p_qa.add_argument("asset", help="Path to .py, .blend, .glb, .fbx, or .step asset")
    p_qa.add_argument("--profile", default="auto", choices=["auto", "roblox", "game", "render", "print"])
    p_qa.add_argument("--max-tris", type=int, default=None, help="BVH check tri threshold (default: 300000 or 0 when --high-poly; auto-reads asset_spec.json)")
    p_qa.add_argument("--high-poly", action="store_true", help="Opt-in High-Poly Uncapped Mode (no 300k BVH cap / no 20k part cap)")
    p_qa.add_argument("--forward-axis", default="+Y", choices=["+Y", "-Y"])
    p_qa.add_argument("--ref", default="", help="Optional explicit reference image path for side-by-side comparison")
    p_qa.add_argument("--ortho-grid", action="store_true", help="Overlay subtle metric blueprint grid strictly on ORTHO views")
    p_qa.add_argument("--snapshot-iteration", action="store_true", help="Archive renders & qa_report.json into reviews/iter_XX/")
    p_qa.add_argument("--threads", type=int, default=None, help="Cap Blender CPU threads (default: safe <= 8)")
    p_qa.add_argument("--device", default="auto", choices=["auto", "gpu", "optix", "cuda", "hip", "oneapi", "metal", "cpu"], help="Cycles compute device")
    p_qa.add_argument("--user-addons", action="store_true", help="Load user Blender add-ons instead of --factory-startup")
    p_qa.add_argument("--fast", action="store_true")

    p_bake = sub.add_parser("bake", help="Run hardware-safe headless Blender 5.2+ 2K Cycles PBR bake + variants + LODs script")
    p_bake.add_argument("script", help="Path to bake_lod_variants.py")
    p_bake.add_argument("--threads", type=int, default=None, help="Cap Blender/OIDN CPU threads (default: safe <= 8)")
    p_bake.add_argument("--device", default="auto", choices=["auto", "gpu", "optix", "cuda", "hip", "oneapi", "metal", "cpu"], help="Cycles compute device (default: auto GPU-only)")
    p_bake.add_argument("--cooldown", type=float, default=1.0, help="Seconds to pause between heavy Cycles passes (default: 1.0)")
    p_bake.add_argument("--tile-size", type=int, default=512, help="Cycles tile size in px to prevent power/VRAM spikes (default: 512)")
    p_bake.add_argument("--no-lock", action="store_true", help="Bypass the sequential cross-process GPU bake lock")
    p_bake.add_argument("--user-addons", action="store_true", help="Load user Blender add-ons instead of --factory-startup")

    p_ins = sub.add_parser("inspect", help="Inspect mesh watertightness, Euler number, m/studs size & 20k tri cap")
    p_ins.add_argument("mesh", help="Path to .glb/.stl/.obj/.ply")
    p_ins.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd in (None, "studio"):
        port = getattr(args, "port", 8765)
        no_open = getattr(args, "no_open", False)
        launch_studio(port=port, open_window=not no_open)
        return 0

    if args.cmd == "generate":
        slug = slugify(args.name)
        title = args.name.replace("_", " ").title()
        asset_dir = Path(args.dir).resolve() / slug
        staged = stage_local_reference_files(asset_dir, args.ref, view=args.ref_view) if args.ref else []
        hp_on = bool(args.high_poly)
        if args.profile == "auto":
            resolved_profile = "game" if (hp_on or args.kind in ("building", "arch")) else "roblox"
        else:
            resolved_profile = args.profile
        iter_enabled = bool(args.iterate or args.rate_to_10)
        review_cfg = {
            "enabled": iter_enabled,
            "target_score": 10.0,
            "max_iterations": int(args.max_iterations),
            "require_zero_qa_warnings": not bool(args.allow_qa_warnings),
            "strict_ten": True,
            "focus_notes": str(args.focus_notes or ""),
        }
        created = generate_parametric_scripts(
            asset_dir,
            slug=slug,
            title=title,
            kind=args.kind,
            prompt=args.prompt or title,
            length_m=args.length,
            references=staged,
            profile=resolved_profile,
            bake_res=args.bake_res,
            ortho_blueprint_grid=bool(args.ortho_grid),
            review_loop=review_cfg,
            rate_to_ten=True if iter_enabled else None,
            high_poly_uncapped=hp_on,
        )
        print(f"[Velum Forge] Staged spec & baseline generator at: {asset_dir}")
        if args.engine == "handoff":
            print("\n=== COPY & PASTE INTO ANTIGRAVITY / CURSOR / CLAUDE ===\n")
            print(build_agent_handoff_prompt(asset_dir))
            return 0
        if args.engine in ("claude", "codex", "gemini"):
            ai_cmd = build_ai_cli_invocation(args.engine, asset_dir)
            if not ai_cmd:
                print(f"ERROR: AI CLI '{args.engine}' not found on PATH. Printing AI Handoff Prompt instead:\n", file=sys.stderr)
                print(build_agent_handoff_prompt(asset_dir))
                return 1
            return subprocess.call(ai_cmd, cwd=str(asset_dir))

        rc = _run_qa_cli(
            created["build_script"],
            profile=resolved_profile,
            forward_axis="+Y",
            ortho_grid=bool(args.ortho_grid),
            snapshot_iteration=iter_enabled,
            max_tris=(0 if hp_on else 300000),
            high_poly=hp_on,
        )
        if rc != 0:
            return rc
        if created.get("bake_script"):
            blender_exe = find_blender_exe()
            if blender_exe:
                cmd = build_safe_blender_bake_cmd(blender_exe, created["bake_script"])
                env = build_safe_cycles_env()
                with gpu_bake_lock(enabled=True, label=slug):
                    return subprocess.call(cmd, env=env, creationflags=windows_creationflags())
        return 0

    if args.cmd == "add-ref":
        ad = Path(args.asset_dir).resolve()
        res = stage_local_reference_files(ad, args.images, view=args.view, projection=args.projection, lens_mm=args.lens)
        sync_references_into_spec(ad, res)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "brief":
        ad = Path(args.asset_dir).resolve()
        print(
            build_next_iteration_prompt(ad)
            if args.next_iteration
            else build_agent_handoff_prompt(ad, rate_to_ten=args.rate_to_10, high_poly=args.high_poly)
        )
        return 0

    if args.cmd == "review":
        if not args.review_cmd:
            p_rev.print_help()
            return 0
        ad = Path(args.asset_dir).resolve()
        if args.review_cmd == "config":
            en = True if args.enable else (False if args.disable else None)
            req_w = False if args.allow_qa_warnings else (True if args.require_zero_warnings else None)
            cfg = set_review_config(
                ad,
                enabled=en,
                target_score=args.target,
                max_iterations=args.max_iter,
                require_zero_qa_warnings=req_w,
                strict_ten=True if args.rate_to_10 else None,
                focus_notes=args.focus,
                high_poly_uncapped=args.high_poly,
            )
            print(json.dumps(cfg, indent=2))
            return 0
        if args.review_cmd == "snapshot":
            snap = snapshot_iteration_renders(ad, iteration=args.iteration)
            print(json.dumps(snap, indent=2))
            return 0
        if args.review_cmd == "log":
            if args.json_file:
                payload = json.loads(Path(args.json_file).read_text(encoding="utf-8-sig"))
                entry = record_iteration_review(
                    ad,
                    honest_rating=payload.get("honest_rating", args.score),
                    rubric_scores=payload.get("rubric_scores"),
                    summary=payload.get("summary", args.summary),
                    strengths=payload.get("strengths", args.strength),
                    defects=payload.get("defects", args.defect),
                    iteration=payload.get("iteration", args.iteration),
                    snapshot_renders=not args.no_snapshot,
                    notes=payload.get("notes", ""),
                )
            else:
                entry = record_iteration_review(
                    ad,
                    honest_rating=args.score,
                    rubric_scores=_parse_rubric_kv(args.rubric) or None,
                    summary=args.summary,
                    strengths=args.strength,
                    defects=args.defect,
                    iteration=args.iteration,
                    snapshot_renders=not args.no_snapshot,
                )
            if args.json:
                print(json.dumps(entry, indent=2))
            else:
                print(entry["markdown"])
            return 0
        if args.review_cmd == "status":
            hist = load_review_history(ad)
            if args.json:
                print(json.dumps(hist, indent=2))
            else:
                cfg = hist.get("config") or get_review_config(ad)
                print(f"=== Velum Forge Review Status: {hist.get('asset_title')} ===")
                print(f"Iterative Mode: {'ENABLED' if cfg.get('enabled') else 'DISABLED (Optional)'} | Target: {cfg.get('target_score')}/10 | Max Iters: {cfg.get('max_iterations')}")
                print(f"Status: {hist.get('status')} | Latest: {hist.get('latest_rating')} | Best: {hist.get('best_rating')}")
                for it in hist.get("iterations") or []:
                    d = it.get("delta_from_previous")
                    ds = f" ({d:+.1f})" if isinstance(d, (int, float)) else ""
                    qa = it.get("qa_snapshot") or {}
                    qa_s = f"QA={'PASS' if qa.get('pass') else 'FAIL'}({qa.get('errors_count',0)}E/{qa.get('warnings_count',0)}W)" if qa.get("available") else "QA=n/a"
                    print(f"  Iter {it['iteration']}: {float(it['honest_rating']):.1f} / 10{ds}  [{it['verdict']}]  {qa_s}  defects={len(it.get('defects') or [])}")
                if hist.get("progression_sheet"):
                    print(f"Progression Sheet: {hist['progression_sheet']}")
            return 0
        if args.review_cmd == "prompt":
            print(build_next_iteration_prompt(ad))
            return 0

    if args.cmd == "setup-gui":
        from .installer_gui import run_installer_gui

        return run_installer_gui()

    if args.cmd == "set-blender":
        res = set_custom_blender_exe(args.path)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if args.cmd == "doctor":
        rep = run_doctor()
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            print(f"=== Velum Forge Doctor (v{__version__}) ===")
            for chk in rep["checks"]:
                badge = "[OK]  " if chk["ok"] else "[WARN]"
                print(f"  {badge} {chk['label']:38s} -> {chk['detail']}")
        return 0 if rep["ok"] else 1

    if args.cmd == "install-ai":
        res = install_ai_integrations(
            antigravity=not args.no_antigravity,
            claude_code=not args.no_claude,
            workspace_dir=args.workspace or None,
        )
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "new":
        res = scaffold_asset(args.kind, args.name, args.dir)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "qa":
        return _run_qa_cli(
            args.asset,
            profile=args.profile,
            forward_axis=args.forward_axis,
            ref_path=args.ref,
            fast=args.fast,
            ortho_grid=args.ortho_grid,
            snapshot_iteration=args.snapshot_iteration,
            threads=args.threads,
            device=args.device,
            user_addons=args.user_addons,
            max_tris=args.max_tris,
            high_poly=bool(args.high_poly),
        )

    if args.cmd == "bake":
        blender_exe = find_blender_exe()
        if not blender_exe:
            print("ERROR: Blender 5.2+ executable not found.", file=sys.stderr)
            return 1
        cmd = build_safe_blender_bake_cmd(
            blender_exe,
            args.script,
            threads=args.threads,
            user_addons=args.user_addons,
        )
        env = build_safe_cycles_env(
            threads=args.threads,
            device=args.device,
            cooldown=args.cooldown,
            tile_size=args.tile_size,
        )
        with gpu_bake_lock(enabled=not args.no_lock, label=Path(args.script).parent.name):
            return subprocess.call(cmd, env=env, creationflags=windows_creationflags())

    if args.cmd == "inspect":
        py = find_venv_python()
        cmd = [py, str(CAD_ENGINE_DIR / "cad_bridge.py"), "inspect", args.mesh]
        if args.json:
            cmd.append("--json")
        return subprocess.call(cmd)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
