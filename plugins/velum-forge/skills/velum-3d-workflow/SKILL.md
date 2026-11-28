---
name: velum-3d-workflow
description: Master 6-stage Velum Forge runbook for building production-grade, zero-clipping, Cycles-baked 2K PBR 3D assets (vehicles, boats, architecture/environments, props, wildlife/fish) with matched perspective reference cameras, optional Honest Rating Iteration Reviews, multi-variant finishes, instance-aware LOD0-LOD3 chains, and automated 10-view QA. Activate first on any end-to-end 3D asset build or overhaul request.
---

# Velum Forge — Master 6-Stage 3D Asset Workflow (v1.2)

Use this skill whenever asked to create, overhaul, or productionize a 3D model. Every Velum Forge asset passes **6 deterministic engineering gates** plus an **optional Iterative Visual Critic & Honest Rating Review Loop**.

## Pipeline Architecture

```text
Stage 0: Archetype Routing, Spec & Refs (`--profile game` vs `--profile roblox`, Persp Cams OR Ortho Blueprints)
   │
Stage 1: Precision CAD Hardware (build123d -> STEP + 1:1m watertight GLB)     [velum-cad-brep]
   │
Stage 2: Multi-Datum / Quad-Flow / Organic BMesh in Meters (+Y fwd, Z=0)      [velum-architecture-environments / velum-organic-species]
   │
Stage 3: Hard BVH Shell-Integrity, Clearances, Joint Locks & Signed-Volume Normals
   │
Stage 4: Automated 10-View QA + Multi-Angle `ref_comparison.png` (`PASS` 0E/0W)
   │
Stage 4B (OPTIONAL): Iterative Visual Critic & Honest Rating Loop (`vforge review` / `--rate-to-10`)
   │      Snapshot -> Honest X.X/10 Rating + Categorized Defects -> Fix -> Re-QA until >= Target
   │
Stage 5: Dedicated 2K (`2048x2048`) Per-Set Cycles GPU PBR Bake + Variants    [velum-pbr-bake-lods]
   │
Stage 6: Instance-Aware LOD0..LOD3 + TEXTURE_SETS Export (0 `_src`) + Visual Review
```

## Stage-by-Stage Execution Checklist

### Stage 0 — Archetype Routing, Perspective vs. Ortho Refs & `asset_spec.json`
- **Select Archetype & QA Profile Before Modeling:**

| Archetype | Companion Skills & Refs | Default QA Profile |
| :--- | :--- | :--- |
| **`building` / `arch`** (landmarks, restaurants, interiors, streetscapes, foliage) | `velum-architecture-environments` + `velum-cad-brep` (utility hardware only) + `velum-pbr-bake-lods` — Ref: `examples/news_cafe_south_beach/` | **`--profile game`** (`--max-tris 300000`, dedicated 2K PBR per `vf_asset_set`) |
| **`boat` / `vehicle` / `prop`** | `velum-cad-brep` + `velum-pbr-bake-lods` — Refs: `examples/sunrunner_24/`, `examples/cruiser_boat_7c/` | `--profile roblox` (or `--profile game` for high-poly) |
| **`fish` / `creature` / `organic`** | `velum-organic-species` + `velum-pbr-bake-lods` — Ref: `examples/mahi_mahi/` | `--profile roblox` (or `--profile game` for high-poly) |
| **`cad`** (precision mechanical assembly) | `velum-cad-brep` + `velum-pbr-bake-lods` | `--profile roblox` / `--profile print` |

- **Opt-In High-Poly Uncapped Mode (`--high-poly` / `--max-tris 0`, OFF by default):** Standard builds keep `--profile roblox` (`<20k`/part) or `--profile game --max-tris 300000`. ONLY when explicitly toggled via `--high-poly`, `high_poly_uncapped: true`, Studio UI toggle, or explicit prompt instruction (*"High-Poly Uncapped Mode"*, *"no 300k cap"*, *"photorealistic high-poly"*), run `--profile game --high-poly --max-tris 0`, ignore both `300k` and `20k` caps (still keep linked instances for 2K texel density), and build to full News Cafe ArchViz segment floors (`24–36` segs furniture/rings/globes, `16–24` segs tableware/bottles, `12–16` segs + Catmull-Rom `substeps=3` tubes, `bevel` micro-bevels, `style="quatrefoil"` breeze blocks, `20–24`-seg palm trunks w/ `14–18` fronds × `16–22` `3`-seg curved leaflet pairs).
- **Split-Into-Instances First (`> 20k` Tris) Rule:** Whenever any object exceeds `20,000` triangles, **NEVER immediately decimate or drop polygon detail**. First inspect whether it combines repeated or separable assets (e.g., 2+ barstools joined together, multiple chairs, or table+tableware) and **split them into separate linked `Mesh` instances** (`vflib.geo.finalize_mesh_data` + `vflib.geo.spawn_instance`, centered at local pivots with `vf_instanced = True`) or distinct semantic sub-parts along structural seams so each instance stays high-detail and under `20,000` tris with higher UV texel density!
- **Real Perspective Photos (`projection: "perspective"` — Street View, 3/4 shots, close-ups, aerials):**
  - Do **NOT** force flat ortho blueprint planes or ortho grids onto perspective photos!
  - Call `refs.load_references(THIS_DIR, subject_objects=meshes)` (or `refs.add_perspective_ref_camera(...)` with matching `lens_mm`) so Blender mounts real matched perspective cameras (`VF_RefCam_*`) and `vforge qa` renders a multi-angle side-by-side `renders/ref_comparison.png`.
- **Orthographic Blueprints (`projection: "ortho_blueprint"` — Side/Front/Back/Top elevations ONLY):**
  - `refs.load_references(THIS_DIR)` mounts `1:1 m` orthographic planes in `VF_References_ref`; pass `--ortho-grid` to `vforge qa` strictly on ortho elevations.
- **Starting from CLI:**
  ```powershell
  vforge generate red_snapper --kind fish --length 0.85 --ref path\to\snapper_photo.jpg --prompt "Northern Red Snapper"
  vforge generate ocean_dr_800 --kind building --length 18.0 --ref gsv1.jpg --ref gsv2.jpg --iterate
  vforge generate ocean_dr_800 --kind building --length 18.0 --ref gsv1.jpg --high-poly --iterate --engine handoff
  ```

### Stage 1 — Precision Mechanical CAD Sub-Assemblies (`velum-cad-brep`)
- Build machined/cast industrial hardware (steering wheels, cleats, propellers, hydrants, parking meters, trash bins, door pulls, brackets) in `build123d` (`engine/cad/cad_bridge.py`) via `export_cad_part()` / `export_cad_assembly()`, and import `1:1 m` `.glb` parts into Blender.
- Never use B-Rep Delaunay tessellation on hospitality furniture or tableware where `FIXED` quad-flow (`Alt+J` / SubD / `UNSUBDIV`) is needed.

### Stage 2 — Multi-Datum, Structured Quad-Flow & Organic Forms (`vflib`)
- Add `<velum-forge>/engine/blender` to `sys.path` and import `from vflib import core, mats, gameready, integrity, bake, lod, export, quadflow, render, refs`.
- **Coordinate standard:** `1 unit = 1.0 m`, `+X` = Right, `+Y` = Forward (`vflib` convention; Roblox `-Z`), `+Z` = Up, `scale = (1, 1, 1)`.
- **Grounding & Instancing:** Rest single assets at `Z = 0.0000 m`; anchor buildings/streetscapes to explicit datums (`Z_ROAD`, `Z_SW`, `Z_FLOOR_INT`), center repeating props at local pivots as linked instances (`vf_asset_set`, `vf_instanced = True`), and translate safely via `vflib.geo.ground_objects_safe` (never moving shared `ob.data` `N` times!).
- **Structured `FIXED` Quad-Flow (`vflib.quadflow` / `vflib.geo`):** Use `add_torus_ring`, `add_spline_tube`, `add_revolved_profile`, `add_revolved_ring`, `add_quad_sphere`, `add_quad_grid_box`, `add_mitered_frame`, `add_uv_mapped_sign_plate`, `add_curved_leaf`, `add_bougainvillea_cluster`, `add_breeze_block` finalized with `quad_method="FIXED"` and UV clamp `[0.001, 0.999]` **before** degenerate-triangle nudge.

### Stage 3 — Hard BVH Shell-Integrity, Clearances & Signed-Volume Gate
- Clamp interior geometry inside curved outer shells (`vflib.integrity`), terminate rails/tubes inside T-collars (`r_end <= r_collar_center`), maintain `2D` obstacle exclusion circles, and run `vflib.geo.deconflict_botanical_islands`.
- Enforce outward normals on every closed island via `integrity.ensure_positive_signed_volume(bm)` / `quadflow.ensure_all_islands_outward(bm)` and keep walls `>= 1.6 mm` thick (`half_thickness >= 0.80 mm`). Verify `vflib.integrity.verify_quad_flow(ob)` (`>= 80%` `Alt+J`) on hero furniture.

### Stage 4 — 10-View Automated QA + Multi-Angle Reference Comparison (`0` Errors, `0` Warnings)
- Run:
  ```powershell
  vforge qa path\to\build_asset.py --profile roblox --forward-axis +Y
  vforge qa path\to\build_building.py --profile game --forward-axis +Y --max-tris 300000 --snapshot-iteration
  vforge qa path\to\build_building.py --profile game --high-poly --max-tris 0 --forward-axis +Y --snapshot-iteration
  ```
- **Always inspect visually** (`read_file`): `renders/qa_contact_material.png`, `renders/qa_contact_diagnostic.png`, `renders/ref_comparison.png`, individual `renders/refcam_*.png` shots, plus Street View / interior / macro joint close-ups. Check zero red backfaces, zero spikes, zero floating/clipping, and zero glossy fill-light discs in glass (`visible_glossy = False`).

### Stage 4B (OPTIONAL) — Iterative Visual Critic & Strict Always-10/10 Loop (`vforge review`)
Check `asset_spec.json["review_loop"]["enabled"]` (or whether iterative review was requested).
- **If `enabled == false`:** skip straight to Stage 5 once Stage 4 passes (`0` errors, `0` warnings).
- **If `enabled == true` (always Strict `10.0 / 10`):**
  1. Visually inspect ALL rendered views against ALL reference photos + `qa_report.json`.
  2. Be **brutally honest — NO grade inflation!** Rate yourself honestly from `0` to `10` until the outcome genuinely becomes a **`10 out of 10`**. Do not rush, do not fake or inflate the rating, and **NEVER approve or proceed to Stage 5 below `10.0 / 10`** (even `9.0`, `9.5`, or `9.6` must keep iterating!). When High-Poly Uncapped Mode (`--high-poly`) is active, flag faceted low-segment (`<= 10` segs) hero props or sparse foliage as `[MAJOR]` defects blocking `10/10`.
  3. Record each iteration via `vforge review log` (`velum_forge.review` enforces automatic QA/defect caps at `7.9/10` on errors, `8.9/10` on warnings, and `9.5/10` when defects remain, archives snapshots, updates `reviews/REVIEW_LOG.md`, and renders `reviews/iteration_progression.png`):
     ```powershell
     vforge review log path\to\asset_dir --score 7.8 --summary "Progress check" --strength "Outward blue normals" --defect "Botanicals|major|Blob bushes|Build 3D curved botanical sprays"
     ```
  4. Keep iterating until **`honest_rating == 10.0 / 10`**, `0` unresolved defects, AND `QA PASS (0E/0W)`.

### Stage 5 — Dedicated `2048x2048` Per-Set Cycles GPU PBR Bake & Variants (`velum-pbr-bake-lods`)
- Partition large scenes by `ob["vf_asset_set"]` (`vflib.bake.group_objects_by_asset_set`) and bake **each set onto its own `2048x2048` (2K)** 6-map atlas (`Color` `sRGB` via `lin_arr_to_srgb` + OpenGL `Normal`, `Roughness`, `Metalness`, `AO`, `ORM` `Non-Color`) via hardware-safe GPU-only Cycles (`vforge bake` / `enable_cycles_gpu`), with `isolate_for_ao=True`, `GraphicUV` preservation, and `shared_non_color` single-pack variant reuse.

### Stage 6 — Instance-Aware `LOD0`–`LOD3`, Clean Export & Live Delivery
- Generate instance-aware `LOD0`–`LOD3` (`100% / ~50% / ~25% / ~10%` via `vflib.lod.build_lod_chain`, `delimit={'UV', 'SEAM', 'SHARP'}`, planar `DISSOLVE` on flat glass/awnings).
- Visually inspect `variants_lineup.png`, `baked_closeup.png`, `lod_comparison_sheet.png`, and `reviews/iteration_progression.png`.
- Export via `vflib.export.export_roblox(..., prebaked_texture_sets=..., max_tris=...)` writing per-set `TEXTURE_SETS` in `.studio_setup.luau` and restoring all `_src` Outliner renames (`0` `_src` suffixes), then sync to `core.DESIGN_OUTPUT_DIR`.
