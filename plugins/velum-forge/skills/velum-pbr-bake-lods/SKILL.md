---
name: velum-pbr-bake-lods
description: Cycles GPU (OPTIX/CUDA) 2048x2048 dedicated per-set PBR texture baking, Blender 5.2+/5.3 shader & color-space guardrails, Dual-UV graphic baking, UV clamp-before-nudge packing, single-pack multi-variant reuse, and instance-aware 4-tier LOD0-LOD3 chains. Activate whenever baking textures, creating variants, or generating LODs.
---

# Velum Forge — Dedicated 2K Cycles PBR Baking, Variants & Instance-Aware LODs

Procedural Blender nodes (`TexNoise`, `TexVoronoi`, `TexWave`, `Bump`, `Mix`) render in Cycles but **export blank** to glTF, Roblox `SurfaceAppearance`, Unity, and Unreal. Partition large scenes by `ob["vf_asset_set"]` (`vflib.bake.group_objects_by_asset_set`), bake each set onto its own dedicated **`2048x2048` (2K)** non-overlapping UV atlas, and build **instance-aware `LOD1`–`LOD3`** from the baked `LOD0` parts.

## Seven Hard-Won Blender 5.2+/5.3 Rules (Never Violate These!)

1. **`ShaderNodeMix(data_type="RGBA")` Socket Indices:**
   - In Blender 5.2+, `ShaderNodeMix` contains multiple sockets identically named `"A"`, `"B"`, and `"Result"` (`Float`, `Vector`, `RGBA`). Looking up `"A"` or `"Result"` by name binds the **scalar `Float` socket (`outputs[0]`)**, turning colored procedural wood/scales grayscale or white!
   - **Always use `vflib.bake.mix_rgba(nt, fac, col_a, col_b)`** (binds `inputs[0]` Factor, `inputs[6]` RGBA A, `inputs[7]` RGBA B, `outputs[2]` RGBA Result).
2. **`Image.pixels.foreach_set` on 8-bit `sRGB` Images (`float_buffer=False`):**
   - `foreach_set` writes `[0..1]` directly into raw 8-bit PNG bytes without linear-to-sRGB gamma encoding.
   - Always bake Base Color & AO into `float_buffer=True` `"Non-Color"` images, composite AO in linear space (`bc_lin * (0.72 + 0.28 * ao)`), then convert via **`vflib.bake.lin_arr_to_srgb()`** before calling `save_png_8bit(..., "sRGB")`.
3. **Zero-Staircase Stripes & UV Clamp-Before-Nudge Ordering:**
   - `bpy.ops.uv.smart_project` splits only by face angle, merging coplanar faces across painted waterline or stripe boundaries!
   - **Fix (`vflib.bake.split_material_border_uv_islands` / `prepare_dedicated_set_uvs`):** Split `bmesh` edges where material indices differ BEFORE `smart_project` + `pack_islands` + `seams_from_islands()`, then re-weld 3D vertices (`bmesh.ops.remove_doubles(..., dist=1e-6)`).
   - **Clamp-Before-Nudge (`vflib.bake.reweld_and_clamp_uvs`):** Always clamp every UV vertex inside `[0.001, 0.999]` **FIRST**, then detect near-zero-area degenerate UV faces (`abs(area2) < 1e-10`) and nudge by `0.00015`. Reversing that order collapses boundary-hugging triangles back onto the clamp edge!
4. **Headless (`-b`) Edit Mode Selection & `TEX_SKY` Guard:**
   - In background mode (`-b`), `temp_override` alone does not satisfy `bpy.ops.object.mode_set(mode="EDIT")`. Set `ob.select_set(True)` and `bpy.context.view_layer.objects.active = ob` directly on `view_layer` first.
   - Guard `ShaderNodeTexSky`: check `hasattr(sky, "aerosol_density")` (Blender 5.3+) before falling back to `sky.dust_density`.
5. **Cloud / OneDrive Sync File-Lock Immunity & Crash-Safe Atomic Writes:**
   - Writing Cycles renders or PNG textures directly into a synced folder (`OneDrive`, `Dropbox`) intermittently fails with `OpenImageIO write failed`, and bare copies can corrupt on sudden power loss. Always render/save to `tempfile.gettempdir()` first and copy via `os.fsync()` + atomic `os.replace()` with retry (`vflib.bake.render_still_safe` & `vflib.bake.save_png_8bit`).
6. **Hardware-Safe Cycles GPU-Only & GPU Denoising (Never Hybrid GPU + All-Core CPU!):**
   - Never write `for d in prefs.devices: d.use = True` — that enables both GPU and all CPU cores simultaneously! Always call **`vflib.bake.enable_cycles_gpu(sc)`**, which enforces strictly GPU-only (`d.use = (d.type == dev_type)`), GPU denoising (`OPTIX` or `OPENIMAGEDENOISE` with `denoising_use_gpu = True`), capped CPU threads (`FIXED` <= `8`), `512 px` tiling, and `1.0 s` GC + thermal cooldown between heavy passes.
   - `vforge bake` routes scripts through `engine/blender/safe_bake_runner.py` (intercepting every headless `bpy.ops.object.bake` and `bpy.ops.render.render` call), applies `--factory-startup`, `-t 8`, `OMP`/`TBB`/`OPENBLAS`/`MKL` thread caps, Windows `BELOW_NORMAL_PRIORITY_CLASS`, and a crash-safe sequential cross-process GPU lock so overlapping bakes never spike your GPU/PSU:
     ```powershell
     vforge bake <script.py> [--threads 8] [--device auto|gpu|optix|cuda|hip|oneapi|metal|cpu] [--cooldown 1.0] [--tile-size 512] [--no-lock] [--user-addons]
     ```
7. **Dedicated Per-Set 2K Baking, Isolated Prototype AO & Dual-UV Signage:**
   - Never cramp unrelated facades, patios, furniture, bars, and botanicals onto one UV atlas — group by `vf_asset_set` (`2048x2048` each, `15x–45x` texel density).
   - Enable **`isolate_for_ao=True`** when baking instanced sets (`unique_mesh_reps`) so shadows aren't baked onto one shared prototype and tiled across all copies!
   - Preserve Dual-UV `GraphicUV` artwork (`prepare_sign_fixture_uvs`, `prepare_continuous_graphic_atlas_uvs`), weight tiny rivets/screws down (`downweight_parts`), and strip `GraphicUV` via `assign_baked_and_strip_graphic_uv`.
   - Reuse the single-packed `UVMap` across variants via `shared_non_color=...` (`5x` faster variant re-bakes).

## Standard 6-Map `2048x2048` Output Set
| Map | Filename | Color Space | Bake Pass |
| :--- | :--- | :---: | :--- |
| **Albedo + Cavity AO** | `T_<Asset>_<var>_<set>_Color.png` | `sRGB` | `DIFFUSE` (`COLOR`) × linear `AO` -> `lin_arr_to_srgb` |
| **Tangent Normal (OpenGL)** | `T_<Asset>_<var>_<set>_Normal.png` | `Non-Color` | `NORMAL` (`TANGENT`, `+X / +Y / +Z`) |
| **Roughness** | `T_<Asset>_<var>_<set>_Roughness.png` | `Non-Color` | `ROUGHNESS` |
| **Metalness** | `T_<Asset>_<var>_<set>_Metalness.png` | `Non-Color` | `EMIT` (Metallic socket override) |
| **Ambient Occlusion** | `T_<Asset>_<var>_<set>_AO.png` | `Non-Color` | `AO` (`isolate_for_ao=True`) |
| **Channel-Packed ORM** | `T_<Asset>_<var>_<set>_ORM.png` | `Non-Color` | `R = AO`, `G = Roughness`, `B = Metalness` |

> **Blender `ShaderNodeTexVoronoi` 5.2 API Note:** Use `vor.distance = "MANHATTAN"` (not `.metric`, which was removed in 5.x).

## Instance-Aware & Seam-Locked 4-Tier LOD Rules (`LOD0` -> `LOD1` -> `LOD2` -> `LOD3`)
- Always mark UV island borders as seams (`bpy.ops.uv.seams_from_islands()`) before replacing multi-slot procedural materials with the single baked material.
- Decimate at most once per unique `ob.data` (`mesh_cache` in `vflib.lod.build_lod_chain`) so linked instances share decimated meshes.
- On `COLLAPSE` decimation (`LOD1 ~0.50`, `LOD2 ~0.25`, `LOD3 ~0.10`), set `dec.delimit = {"UV", "SEAM", "SHARP"}` so UV seams never tear into sawtooth triangles!
- Use planar `DISSOLVE` (`1.8° / 2.6° / 3.4°`, `delimit = {"UV", "SEAM", "SHARP"}`) on double-walled hulls or flat architectural windows/awnings (`planar_parts` / `planar_sets`), and push thin exterior decal ribbons (`PaintPrimary`) outboard by `+3..+13 mm`.
- Export per-set `TEXTURE_SETS` in `.studio_setup.luau`, restore all `_src` Outliner renames in `finally:`, and visually inspect `lod_comparison_sheet.png`!
