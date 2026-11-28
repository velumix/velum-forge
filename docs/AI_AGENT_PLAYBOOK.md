# Velum Forge — AI Agent 3D Engineering Playbook

This playbook teaches any AI coding/3D agent (**Google Antigravity**, **Claude Code**, **OpenAI Codex**, **Cursor**) how to produce studio-grade, zero-clipping, Cycles-baked 3D assets indistinguishable from hand-crafted AAA / Roblox flagship production work.

---

## 1. Why Naive AI 3D Scripts Fail (And How Velum Forge Solves Each Failure)

| Common AI 3D Failure | Root Cause | Velum Forge Solution |
| :--- | :--- | :--- |
| **Interior parts poking through curved hulls/bodies** | Extruding floors, bulkheads, lockers, or fin roots vertically/horizontally with fixed widths | Clamp coordinates analytically to the inner wall envelope + run a hard `BVHTree` overlap/raycast gate (`vflib.integrity`) that raises `RuntimeError` on any breach. |
| **Toy-like primitive kitbashing** | Gluing raw cylinders/spheres together for wheels, cleats, props, or fish bodies | Hybrid pipeline: **OpenCascade B-Rep CAD (`build123d`)** for filleted mechanical hardware + **analytical multi-station `bmesh` lofts** with sculpted surface relief for hulls & anatomy. |
| **Inverted red normals on forked/concave parts** | `bmesh.ops.recalc_face_normals` heuristic flips sign on thin V-boomerangs (e.g., scissor tail fins) | Compute exact 3D signed volume $\frac{1}{6}\sum v_0 \cdot (v_1 \times v_2)$ on every closed manifold and reverse faces if `< 0` (`ensure_positive_signed_volume`). |
| **Materials exporting blank grey to glTF / Roblox** | Procedural Blender nodes (`Noise`, `Voronoi`, `Wave`, `Bump`, `Mix`) are ignored by game exporters | Bake procedural shaders in Cycles GPU (`OPTIX`) onto a non-overlapping `2048x2048` UV atlas (`Color`, OpenGL `Normal`, `Roughness`, `Metalness`, `AO`, `ORM`) and wire `ShaderNodeTexImage` directly to `Principled BSDF`. |
| **Stair-stepped painted stripes on shared UV atlases** | `uv.smart_project` merges coplanar faces across material boundaries, causing diagonal pixel aliasing | Split multi-material edges BEFORE `smart_project` + `pack_islands`, bake with `12–14 px` `EXTEND` margin, and re-weld 3D vertices (`remove_doubles`) afterward (`vflib.bake.split_material_border_uv_islands`). |
| **Torn stripes or inner-liner poke-through on LODs** | Unconstrained `COLLAPSE` decimation collapses across UV seams and flattens curved outer shells into inner liners | Mark UV seams (`seams_from_islands`), set `dec.delimit = {'UV', 'SEAM', 'SHARP'}`, use `DISSOLVE` (`1.8°–3.4°`) on double-walled shells, and push thin exterior decal bands outboard by `+3..+13 mm` (`vflib.lod`). |
| **Perspective photos broken by ortho blueprint grids** | Parking real Street View / 3/4 perspective photos onto flat ortho planes causes foreshortening & lens mismatch | Separate **`perspective`** references (matched `VF_RefCam_*` Blender perspective cameras with real `lens_mm` + camera background overlay) from **`ortho_blueprint`** references (1:1m ortho planes + opt-in `--ortho-grid`). |
| **Blurry 2K textures on buildings / crowded interiors** | Cramping 100+ meshes onto one atlas or leaking floor shadows across 45 linked chairs | Partition into dedicated `vf_asset_set` `2048x2048` 2K sets (`isolate_for_ao=True`, `shared_non_color` cache), preserve Dual-UV `GraphicUV`, and use `> 20k` Split-Into-Instances-First (`vflib.quadflow`) before any decimation. |
| **Premature "looks great" / grade-inflated single-pass slop** | Stopping after Iteration 1 despite blob botanicals, buried glazing, clipping umbrellas, or floating parts | Optional **Iterative Visual Critic & Honest Rating Loop (`vforge review`)**: archive snapshots, rate honestly (`0–10`, hard-capped on `qa_report.json` errors/warnings, with `--rate-to-10` strict mode), log categorized defects, and iterate until `>= target_score`! |

---

## 2. Step-by-Step Workflow for Any New Asset

### Step A: Research Real-World Dimensions & Proportions First
Never invent proportions. Look up exact real-world measurements in **meters**:
- Naval vessels: Length Overall (`LOA`), Beam, Deadrise angles (e.g., `21°` transom planing V twisting to `57°` wave-piercing bow entry), Console eye height (`~1.45 m`), Wheel diameter (`0.38 m`).
- Wildlife / Fish: Total Length (`TL`), Body Depth % of `TL` (e.g., `22.8%` for `Coryphaena hippurus`), Width-to-Height compression ratio (`~1:2.5`), Orbital eye position, Fin ray counts.

### Step B: Build Mechanical Sub-Parts in `build123d` (`engine/cad/`)
Run CAD hardware generation via `.venv` Python (`engine/cad/cad_bridge.py`) to produce exact `.step` + watertight `1:1 m` `.glb` parts before assembling the scene in Blender.

### Step C: Build Watertight `S^2` Primary Meshes, Quad-Flow Furniture & Sockets in Blender (`engine/blender/vflib/`)
- Keep every individual Roblox `MeshPart` strictly `< 20,000` triangles (`ROBLOX_MAX_TRIS_PER_MESH`); use `--profile game --max-tris 300000` for standard architecture, OR opt-in **`--profile game --high-poly --max-tris 0`** when High-Poly Uncapped Mode is toggled/requested (unlimited BVH + News Cafe ArchViz segment floors: `24–36` hero furniture/rings, `16–24` tableware, `12–16` + `substeps=3` tubes, `bevel`, `style="quatrefoil"`, dense 3D foliage).
- **Split-Into-Instances First (`> 20k` Tris):** If an object exceeds `20,000` tris because it joins repeated or separable items (e.g., 2+ barstools or chairs merged together), split them into separate linked instances (`vflib.quadflow.spawn_instance`) before ever reducing polygon detail.
- Use `FIXED`-diagonal quad-flow `bmesh` primitives (`vflib.quadflow`, passing `>= 80%` `Alt+J`) on hero furniture/tableware and `ground_objects_safe` for multi-datum grounding (`Z_ROAD`, `Z_SW`, `Z_FLOOR_INT`).
- Keep closed hydrofoil / panel / curved leaf thickness `>= 1.6 mm` (`half_thickness >= 0.80 mm`) so `qa_check.py` (`--eps 0.001`) reports `0` hidden back-to-back face warnings.

### Step D: Pass the 10-View Visual & Geometric QA Gate (`0` Errors, `0` Warnings)
Run `vforge qa <build_script.py> --profile roblox --forward-axis +Y` (or `--profile game --max-tris 300000`, or `--profile game --high-poly --max-tris 0` when High-Poly Uncapped Mode is toggled ON; add `--ortho-grid` ONLY for orthographic blueprints; add `--snapshot-iteration` when Iterative Review mode is enabled).
**Never trust exit code `0` alone** — open and inspect `contact_sheet_material.png`, `contact_sheet_diagnostic.png`, and multi-angle `ref_comparison.png` with a vision tool (`read_file`) to verify proportions, silhouette, framing, and zero clipping from all angles!

### Step D2 (Optional): Iterative Visual Critic & Strict Always-10/10 Loop (`vforge review`)
When `review_loop.enabled` is turned ON in `asset_spec.json` (via `--iterate`, `--rate-to-10`, `vforge review config <dir> --enable`, or Studio UI):
1. Compare all matched perspective / QA renders directly against every reference photo + `qa_report.json`.
2. Write an honest **Iteration N Review — Honest Rating: X.X / 10** calling out specific defects by category (never inflating a `6.2/10` pass — do not rush or fake scores! When High-Poly Uncapped Mode is ON, faceted `<= 10`-seg hero props or sparse palms block `10/10`).
3. Log it via `vforge review log <dir> --score <X.X> --summary "..." --strength "..." --defect "Category|severity|Description|Fix"` — Velum Forge automatically archives iteration snapshots, enforces objective QA/defect caps, updates `reviews/REVIEW_LOG.md`, and renders `reviews/iteration_progression.png`.
4. Fix every defect and **NEVER stop, approve, or proceed to Stage 5 below `10.0 / 10`** — iterate until **`honest_rating == 10.0 / 10`**, `0` unresolved defects, and `0` QA errors/warnings.

### Step E: Bake Dedicated `2048x2048` Per-Set Cycles GPU PBR Atlases, Build 4 Variants & Generate Instance-Aware `LOD0`–`LOD3`
Run `vforge bake <bake_lod_variants.py>` (automatically routed through `safe_bake_runner.py` GPU-only guard + `isolate_for_ao=True` + `shared_non_color` cache + Dual-UV `GraphicUV`), then visually inspect:
1. `variants_lineup.png`
2. `baked_closeup.png`
3. `lod_comparison_sheet.png` (and ensure `0` `_src` Outliner suffixes remain!)
4. `T_<Asset>_<variant>_<set>_Color.png` & `T_<Asset>_<variant>_<set>_Normal.png`
