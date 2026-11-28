"""Automated verification suite for Velum Forge v1.2 features:
- Perspective vs. Ortho Blueprint reference classification & camera defaults
- Optional Iterative Critic & Honest Rating Review engine (`velum_forge.review`)
- Multi-reference side-by-side contact sheet + strictly-ortho optional metric grid (`compose_sheet.py`)
- Studio HTTP API endpoints (`studio_server.py`)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from velum_forge import bake_guard, cli, doctor, generator, references, review, scaffold, studio_server  # noqa: E402


def _make_sample_png(path: Path, color: tuple[int, int, int], label: str, size=(640, 480)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, size[0] - 40, size[1] - 40], outline=(240, 240, 240), width=4)
    d.text((60, 60), label, fill=(255, 255, 255))
    im.save(path, format="PNG")
    return path


class TestVelumForgeV12(unittest.TestCase):
    def test_perspective_vs_ortho_classification(self) -> None:
        # Real photos & Street View captures must default to perspective (never ortho!)
        self.assertEqual(references.classify_reference_view("gsv_800_ocean_dr.jpg"), ("street_view", "perspective"))
        self.assertEqual(references.classify_reference_view("IMG_4821.png"), ("hero", "perspective"))
        self.assertEqual(references.classify_reference_view("pasted_photo_1.png"), ("hero", "perspective"))
        self.assertEqual(references.classify_reference_view("doorway_closeup.jpg"), ("closeup", "perspective"))
        self.assertEqual(references.classify_reference_view("drone_aerial.png"), ("aerial", "perspective"))

        # Explicit orthographic blueprints classify as ortho_blueprint
        self.assertEqual(references.classify_reference_view("boat_side_ortho.png"), ("ortho_side", "ortho_blueprint"))
        self.assertEqual(references.classify_reference_view("hull_blueprint_front.png"), ("ortho_front", "ortho_blueprint"))
        self.assertEqual(references.classify_reference_view("deck_floorplan.png"), ("ortho_top", "ortho_blueprint"))
        self.assertEqual(
            references.classify_reference_view("photo.png", explicit_view="hero", explicit_projection="perspective"),
            ("hero", "perspective"),
        )

    def test_optional_review_loop_and_qa_caps(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ad = Path(td) / "ocean_dr_800"
            ad.mkdir(parents=True)
            renders = ad / "renders"
            _make_sample_png(renders / "ref_comparison.png", (36, 72, 110), "Iter 1 Render")
            _make_sample_png(renders / "qa_contact_material.png", (42, 60, 88), "QA Material")

            # Default is OFF (optional!), but target is always strictly locked at 10.0/10
            cfg0 = review.get_review_config(ad)
            self.assertFalse(cfg0["enabled"])
            self.assertEqual(cfg0["target_score"], 10.0)
            self.assertTrue(cfg0["strict_ten"])

            # Even if caller passes target_score=9.0, review loop locks target_score=10.0
            cfg1 = review.set_review_config(ad, enabled=True, target_score=9.0, max_iterations=3, focus_notes="Botanicals & glazing")
            self.assertTrue(cfg1["enabled"])
            self.assertEqual(cfg1["target_score"], 10.0)
            self.assertTrue(cfg1["strict_ten"])

            # QA report WITH errors must cap an inflated score at 7.9/10!
            (renders / "qa_report.json").write_text(
                json.dumps(
                    {
                        "pass": False,
                        "total_tris": 48210,
                        "errors": ["floating/detached part in BreezeBlock_04", "z-fighting: Curb<->Sidewalk"],
                        "warnings": ["UV overlap 12% on Signage"],
                    }
                ),
                encoding="utf-8",
            )
            it1 = review.record_iteration_review(
                ad,
                honest_rating=6.2,
                summary="Massing and 8th St rhythm are strong, but clear defects hold it back from 10/10.",
                strengths=["Perforated 3D breeze blocks", "Strong building massing"],
                defects=[
                    "Botanicals|major|Buttonwood trees look like smooth icosphere blobs|Replace with branching boughs and broad-leaf canopy",
                    "Upper Windows|major|Solid stucco walls partially hide recessed L2/L3 glazing|Carve clean openings and seat dark reflective glass",
                ],
            )
            self.assertEqual(it1["iteration"], 1)
            self.assertEqual(it1["honest_rating"], 6.2)
            self.assertEqual(it1["verdict"], "ITERATE")

            # Iteration 2: even if someone claims 9.2 while QA still has 1 error, cap forces 7.9!
            _make_sample_png(renders / "ref_comparison.png", (40, 108, 92), "Iter 2 Render")
            (renders / "qa_report.json").write_text(
                json.dumps(
                    {
                        "pass": False,
                        "total_tris": 51200,
                        "errors": ["floating/detached part in BreezeBlock_04 (6mm gap)"],
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            it2 = review.record_iteration_review(
                ad,
                honest_rating=9.2,
                summary="Huge jump on dark windows and palm fronds, but QA still has a floating block.",
                strengths=["Legible News Cafe script above umbrellas", "100% outward blue face orientation"],
                defects=["Geometric QA|critical|Floating breeze blocks due to 6mm gap|Bridge masonry mortar joints"],
            )
            self.assertEqual(it2["honest_rating"], 7.9)
            self.assertIn("Capped at 7.9/10", it2["cap_reason"])
            self.assertEqual(it2["delta_from_previous"], 1.7)
            self.assertEqual(it2["verdict"], "ITERATE")

            # Next-iteration prompt includes unresolved defect, previous score & always-10/10 rule
            nxt = review.build_next_iteration_prompt(ad)
            self.assertIn("Iteration 3 Refinement", nxt)
            self.assertIn("7.9 / 10", nxt)
            self.assertIn("Floating breeze blocks", nxt)
            self.assertIn("10.0 / 10", nxt)

            # Iteration 3: QA clean (0E/0W) + 9.3/10 must STILL iterate (never approve below 10.0/10!)
            _make_sample_png(renders / "ref_comparison.png", (28, 120, 96), "Iter 3 Render")
            (renders / "qa_report.json").write_text(
                json.dumps({"pass": True, "total_tris": 54100, "errors": [], "warnings": []}),
                encoding="utf-8",
            )
            it3 = review.record_iteration_review(
                ad,
                honest_rating=9.3,
                summary="Strong 9.3 pass, one minor awning polish item still short of 10/10.",
                strengths=["Organic shade tree canopy", "Zero QA errors or warnings"],
                defects=["Signage|minor|Awning lettering slightly small|Scale News Cafe typography"],
            )
            self.assertEqual(it3["honest_rating"], 9.3)
            self.assertEqual(it3["verdict"], "ITERATE")

            # Iteration 4: Claiming 10.0/10 while defects remain is capped at 9.5 & stays ITERATE
            it4 = review.record_iteration_review(
                ad,
                honest_rating=10.0,
                summary="Trying to rush 10/10 with defect still listed.",
                strengths=["Great framing"],
                defects=["Trim|minor|Missing drip cap|Add bevel trim"],
            )
            self.assertEqual(it4["honest_rating"], 9.5)
            self.assertEqual(it4["verdict"], "ITERATE")

            # Iteration 5: QA clean (0E/0W) + 0 defects + 10.0/10 -> APPROVED!
            _make_sample_png(renders / "ref_comparison.png", (28, 130, 88), "Iter 5 Final Render")
            it5 = review.record_iteration_review(
                ad,
                honest_rating=10.0,
                summary="All Street View angles match 10/10 with organic tropical canopy and clean 0E/0W QA.",
                strengths=["Organic shade tree canopy", "Zero QA errors or warnings"],
                defects=[],
            )
            self.assertEqual(it5["honest_rating"], 10.0)
            self.assertEqual(it5["verdict"], "APPROVED")
            self.assertTrue((ad / "reviews" / "REVIEW_LOG.md").is_file())
            self.assertTrue((ad / "reviews" / "iteration_progression.png").is_file())

    def test_compose_sheet_multi_ref_and_strict_ortho_grid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            tiles = {}
            for key, lbl, proj in (
                ("hero", "HERO 3/4", "PERSP"),
                ("front", "FRONT (ORTHO)", "ORTHO"),
                ("side", "SIDE (ORTHO)", "ORTHO"),
                ("back", "BACK (ORTHO)", "ORTHO"),
                ("top", "TOP (ORTHO)", "ORTHO"),
                ("rear_34", "REAR 3/4", "PERSP"),
                ("diag_wire", "WIREFRAME", "PERSP"),
                ("diag_parts", "PARTS", "PERSP"),
                ("diag_normals", "NORMALS", "PERSP"),
                ("diag_bottom", "BOTTOM", "PERSP"),
            ):
                p = _make_sample_png(d / f"tile_{key}.png", (70, 90, 120), lbl)
                tiles[key] = {"path": str(p), "label": lbl, "projection": proj, "ortho_scale_m": 4.0 if proj == "ORTHO" else None}

            r1 = _make_sample_png(d / "gsv_corner.png", (120, 80, 60), "Street View 1")
            r2 = _make_sample_png(d / "gsv_front.png", (100, 120, 60), "Street View 2")
            r3 = _make_sample_png(d / "side_ortho.png", (60, 110, 120), "Ortho Side")

            m1 = _make_sample_png(d / "tile_refcam_00.png", (80, 100, 140), "Matched Cam 1")
            m2 = _make_sample_png(d / "tile_refcam_01.png", (90, 110, 140), "Matched Cam 2")

            manifest = {
                "asset_name": "OceanDr800",
                "ortho_grid": True,
                "tiles": tiles,
                "ref_pairs": [
                    {"ref_path": str(r1), "ref_label": "REFERENCE (gsv_corner.png) [STREET_VIEW]", "model_path": str(m1), "model_label": "MODEL — PERSP 28mm", "projection": "PERSP"},
                    {"ref_path": str(r2), "ref_label": "REFERENCE (gsv_front.png) [STREET_VIEW]", "model_path": str(m2), "model_label": "MODEL — PERSP 28mm", "projection": "PERSP"},
                    {"ref_path": str(r3), "ref_label": "BLUEPRINT (side_ortho.png) [SIDE ORTHO]", "model_path": tiles["side"]["path"], "model_label": "MODEL — SIDE (ORTHO)", "projection": "ORTHO", "ortho_scale_m": 4.0},
                ],
            }
            qa = {"pass": True, "asset_name": "OceanDr800", "profile": "roblox", "renderer": "Cycles OPTIX", "total_tris": 18200, "object_count": 5, "size_m": [16.0, 11.0, 10.5], "ground_z": 0.0, "errors": [], "warnings": []}
            man_p = d / "render_manifest.json"
            qa_p = d / "qa_report.json"
            hist_p = d / "review_history.json"
            man_p.write_text(json.dumps(manifest), encoding="utf-8")
            qa_p.write_text(json.dumps(qa), encoding="utf-8")
            hist_p.write_text(json.dumps({"iterations": [{"iteration": 2, "honest_rating": 7.8}]}), encoding="utf-8")

            out_mat = d / "material.png"
            out_diag = d / "diagnostic.png"
            out_ref = d / "ref_comparison.png"
            rc = subprocess.call(
                [
                    sys.executable,
                    str(REPO_ROOT / "engine" / "cad" / "compose_sheet.py"),
                    "--manifest", str(man_p),
                    "--qa-json", str(qa_p),
                    "--out-material", str(out_mat),
                    "--out-diagnostic", str(out_diag),
                    "--out-ref", str(out_ref),
                    "--review-history", str(hist_p),
                    "--ortho-grid",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(out_mat.is_file())
            self.assertTrue(out_diag.is_file())
            self.assertTrue(out_ref.is_file())
            with Image.open(out_ref) as im:
                # 3 stacked pairs should be substantially taller than single-pair comparison!
                self.assertGreater(im.height, 1000)

    def test_studio_api_review_endpoints(self) -> None:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), studio_server.StudioHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                ad = Path(td) / "api_test_asset"
                ad.mkdir()
                _make_sample_png(ad / "renders" / "qa_contact_material.png", (30, 80, 120), "API Test Render")

                # 1. GET /
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                    self.assertEqual(resp.status, 200)
                    html = resp.read().decode("utf-8")
                    self.assertIn("Enable Iterative Visual Critic", html)
                    self.assertIn("Metric Calibration Grid (Ortho Blueprints Only)", html)

                # 2. POST /api/review/config (target always locked to 10.0; high_poly_uncapped toggle works!)
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/review/config",
                    data=json.dumps({
                        "asset_dir": str(ad),
                        "enabled": True,
                        "target_score": 8.5,
                        "max_iterations": 4,
                        "high_poly_uncapped": True,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(body["ok"])
                    self.assertTrue(body["config"]["enabled"])
                    self.assertEqual(body["config"]["target_score"], 10.0)
                    self.assertIn("[HIGH-POLY UNCAPPED MODE: ON", body["handoff_prompt"])
                    self.assertIn("--max-tris 0", body["handoff_prompt"])

                # Turn high_poly_uncapped OFF again and verify default 300k guard returns
                req_off = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/review/config",
                    data=json.dumps({"asset_dir": str(ad), "high_poly_uncapped": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req_off) as resp:
                    body_off = json.loads(resp.read().decode("utf-8"))
                    self.assertNotIn("[HIGH-POLY UNCAPPED MODE: ON", body_off["handoff_prompt"])

                # 3. POST /api/review/log
                req2 = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/review/log",
                    data=json.dumps(
                        {
                            "asset_dir": str(ad),
                            "honest_rating": 7.4,
                            "summary": "Solid pass 1",
                            "strengths": ["Clean proportions"],
                            "defects": ["Trim|major|Missing bevel|Add 12mm chamfer"],
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req2) as resp:
                    body2 = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(body2["ok"])
                    self.assertEqual(body2["entry"]["honest_rating"], 7.4)

                # 4. GET /api/review/prompt
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/review/prompt?asset_dir={urllib.parse.quote(str(ad))}") as resp:
                    body3 = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(body3["ok"])
                    self.assertIn("Missing bevel", body3["prompt"])
        finally:
            srv.shutdown()
            srv.server_close()

    def test_bake_guard_flags_env_and_sequential_lock(self) -> None:
        cmd_safe = bake_guard.build_safe_blender_bake_cmd("blender.exe", "bake.py", threads=6, user_addons=False)
        self.assertIn("--factory-startup", cmd_safe)
        self.assertIn("-t", cmd_safe)
        self.assertIn("6", cmd_safe)
        self.assertTrue(any(part.endswith("safe_bake_runner.py") for part in cmd_safe))
        self.assertIn("--", cmd_safe)
        self.assertTrue(cmd_safe[cmd_safe.index("--") + 1].endswith("bake.py"))

        cmd_extra = bake_guard.build_safe_blender_bake_cmd(
            "blender.exe", "bake.py", threads=4, extra_script_args=["--fast"]
        )
        self.assertEqual(cmd_extra[-1], "--fast")

        cmd_addons = bake_guard.build_safe_blender_bake_cmd("blender.exe", "bake.py", threads=8, user_addons=True)
        self.assertNotIn("--factory-startup", cmd_addons)

        env = bake_guard.build_safe_cycles_env(threads=6, device="optix", cooldown=1.5, tile_size=256)
        self.assertEqual(env["VELUM_BLENDER_THREADS"], "6")
        self.assertEqual(env["VELUM_CYCLES_DEVICE"], "optix")
        self.assertEqual(env["VELUM_BAKE_COOLDOWN"], "1.5")
        self.assertEqual(env["VELUM_CYCLES_TILE_SIZE"], "256")
        self.assertEqual(env["OMP_NUM_THREADS"], "6")
        self.assertEqual(env["TBB_NUM_THREADS"], "6")
        self.assertEqual(env["OPENBLAS_NUM_THREADS"], "6")
        self.assertEqual(env["MKL_NUM_THREADS"], "6")

        cflags = bake_guard.windows_creationflags()
        if sys.platform == "win32":
            self.assertEqual(cflags, getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000))
        else:
            self.assertEqual(cflags, 0)

        # Verify stale PID lock recovery & clean acquire/release
        with tempfile.TemporaryDirectory() as td:
            lf = Path(td) / "gpu_bake.lock"
            lf.write_text(json.dumps({"pid": 9999999, "label": "stale"}), encoding="utf-8")
            with bake_guard.gpu_bake_lock(enabled=True, lock_file=lf, label="live_test"):
                self.assertTrue(lf.is_file())
            self.assertFalse(lf.exists())

    def test_multi_perspective_azimuth_spread(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ad = Path(td) / "multi_gsv"
            p1 = _make_sample_png(ad / "references" / "gsv_01.png", (40, 80, 120), "GSV 1")
            p2 = _make_sample_png(ad / "references" / "gsv_02.png", (60, 100, 120), "GSV 2")
            r1 = references.analyze_reference_image(p1)
            r2 = references.analyze_reference_image(p2)
            spec_p = references.write_asset_spec(
                ad, slug="multi_gsv", title="Multi GSV", kind="arch", prompt="Street", references=[r1, r2]
            )
            spec = json.loads(spec_p.read_text(encoding="utf-8"))
            az0 = spec["references"][0]["camera"]["azimuth_deg"]
            az1 = spec["references"][1]["camera"]["azimuth_deg"]
            self.assertNotEqual(az0, az1)


class TestVelumForgeMergedFeatures(unittest.TestCase):
    def test_building_and_arch_auto_profile_and_strict_ten(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            for kind in ("building", "arch"):
                ad = Path(td) / f"cafe_{kind}"
                created = generator.generate_parametric_scripts(
                    ad,
                    slug=f"cafe_{kind}",
                    title=f"Cafe {kind.title()}",
                    kind=kind,
                    prompt="Art Deco corner bistro",
                    length_m=14.0,
                    references=[],
                    rate_to_ten=True,
                )
                spec = json.loads(Path(created["spec"]).read_text(encoding="utf-8"))
                self.assertEqual(spec["qa_profile"], "game")
                self.assertEqual(spec["bake_res"], 2048)
                self.assertTrue(spec["rate_to_ten"])
                self.assertTrue(spec["review_loop"]["enabled"])
                self.assertTrue(spec["review_loop"]["strict_ten"])
                self.assertEqual(spec["review_loop"]["target_score"], 10.0)

                build_src = Path(created["build_script"]).read_text(encoding="utf-8")
                bake_src = Path(created["bake_script"]).read_text(encoding="utf-8")
                self.assertIn("quadflow", build_src)
                self.assertIn("refs.load_references", build_src)
                self.assertIn("shared_non_color", bake_src)
                self.assertIn("export.export_roblox", bake_src)

                brief = generator.build_agent_handoff_prompt(ad)
                self.assertIn("velum-architecture-environments", brief)
                self.assertIn("10 out of 10", brief)
                self.assertIn("split them into separate linked instances", brief)
                self.assertNotIn("[HIGH-POLY UNCAPPED MODE: ON", brief)

    def test_high_poly_uncapped_toggle_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # Default OFF
            ad_def = Path(td) / "bistro_default"
            created_def = generator.generate_parametric_scripts(
                ad_def,
                slug="bistro_default",
                title="Bistro Default",
                kind="building",
                prompt="Corner bistro",
                length_m=14.0,
                references=[],
            )
            spec_def = json.loads(Path(created_def["spec"]).read_text(encoding="utf-8"))
            self.assertFalse(spec_def["high_poly_uncapped"])
            self.assertEqual(spec_def["qa_max_tris"], 300000)
            brief_def = generator.build_agent_handoff_prompt(ad_def)
            self.assertNotIn("[HIGH-POLY UNCAPPED MODE: ON", brief_def)
            self.assertIn("--max-tris 300000", brief_def)

            # Explicit prompt override high_poly=True activates uncapped block without changing spec
            brief_ovr = generator.build_agent_handoff_prompt(ad_def, high_poly=True)
            self.assertIn("[HIGH-POLY UNCAPPED MODE: ON", brief_ovr)
            self.assertIn("--high-poly --max-tris 0", brief_ovr)
            self.assertIn("24–36", brief_ovr)

            # Opt-in ON persisted in asset_spec.json
            ad_hp = Path(td) / "bistro_high_poly"
            created_hp = generator.generate_parametric_scripts(
                ad_hp,
                slug="bistro_high_poly",
                title="Bistro High Poly",
                kind="prop",
                prompt="Photorealistic hero patio",
                length_m=2.0,
                references=[],
                high_poly_uncapped=True,
                rate_to_ten=True,
            )
            spec_hp = json.loads(Path(created_hp["spec"]).read_text(encoding="utf-8"))
            self.assertTrue(spec_hp["high_poly_uncapped"])
            self.assertEqual(spec_hp["qa_max_tris"], 0)
            self.assertEqual(spec_hp["qa_profile"], "game")
            brief_hp = generator.build_agent_handoff_prompt(ad_hp)
            self.assertIn("[HIGH-POLY UNCAPPED MODE: ON", brief_hp)
            self.assertIn("--profile game --high-poly --max-tris 0", brief_hp)
            self.assertIn("NEVER stop, approve, or proceed to Stage 5 baking below `10.0 / 10`", brief_hp)

    def test_scaffold_building_and_arch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            for kind in ("building", "arch"):
                res = scaffold.scaffold_asset(kind, f"test_{kind}", td)
                btxt = Path(res["build_script"]).read_text(encoding="utf-8")
                ktxt = Path(res["bake_script"]).read_text(encoding="utf-8")
                self.assertIn("quadflow", btxt)
                self.assertIn("refs.load_references", btxt)
                self.assertIn("prepare_dedicated_set_uvs", ktxt)

    def test_doctor_expects_five_skills(self) -> None:
        skills_root = REPO_ROOT / "plugins" / "velum-forge" / "skills"
        found = sorted(p.name for p in skills_root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
        self.assertEqual(
            found,
            [
                "velum-3d-workflow",
                "velum-architecture-environments",
                "velum-cad-brep",
                "velum-organic-species",
                "velum-pbr-bake-lods",
            ],
        )

    def test_studio_discover_assets_and_new_examples(self) -> None:
        discovered = {a["name"]: a for a in studio_server.discover_assets()}
        for expected in ("mahi_mahi", "sunrunner_24", "news_cafe_south_beach", "cruiser_boat_7c", "memorial"):
            self.assertIn(expected, discovered)
        nc = discovered["news_cafe_south_beach"]
        self.assertEqual(nc["kind"], "building")
        self.assertEqual(nc["qa_profile"], "game")
        self.assertEqual(nc["bake_res"], 2048)
        self.assertEqual(len(nc["references"]), 5)


if __name__ == "__main__":
    import urllib.parse

    unittest.main(verbosity=2)
