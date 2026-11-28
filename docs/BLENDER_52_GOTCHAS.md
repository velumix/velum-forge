# Blender 5.2+ Headless & Cycles Baking Gotchas

Every item in this field guide was discovered and verified in production on Blender 5.2 LTS. Keep this checklist in mind whenever writing headless `bpy` automation.

---

## 1. `ShaderNodeMix(data_type="RGBA")` Socket Name Collision
In Blender 5.x, `ShaderNodeMix` exposes multiple input/output sockets with **identical `.name` strings** (`"A"`, `"B"`, `"Result"`) for `Float`, `Vector`, and `RGBA`:
- `mx.outputs["Result"]` or searching `.name == "Result"` returns **`outputs[0]` (`Float`)**, silently stripping RGB color channels!
- **Correct indices for `data_type = "RGBA"`:**
  - `mx.inputs[0]` -> Factor (`Float`)
  - `mx.inputs[6]` -> Color A (`RGBA`)
  - `mx.inputs[7]` -> Color B (`RGBA`)
  - `mx.outputs[2]` -> Color Result (`RGBA`)
- Helper: `vflib.bake.mix_rgba(nt, fac, col_a, col_b)`.

---

## 2. `Image.pixels.foreach_set` Writes Raw Bytes on `float_buffer=False`
When saving a baked float array (`bc_lin * ao_fac`, which is in **scene-linear** color space) into an 8-bit `bpy.data.images.new(..., float_buffer=False)` image tagged `colorspace_settings.name = "sRGB"`:
- `img.pixels.foreach_set(...)` does **not** apply linear-to-sRGB gamma conversion — it quantizes `[0..1]` linearly into `[0..255]`, making midtones ~2.2x too dark!
- **Fix:** Apply exact IEC 61966-2-1 sRGB transfer (`vflib.bake.lin_arr_to_srgb(arr)`) before `foreach_set`.
- Conversely, for data maps (`Normal`, `Roughness`, `Metalness`, `AO`, `ORM`), tag `colorspace_settings.name = "Non-Color"` and write linear `[0..1]` values directly without gamma encoding.

---

## 3. `ShaderNodeTexVoronoi`: `.distance` Replaced `.metric`
In Blender 5.x, `vor.metric = "MANHATTAN"` raises `AttributeError`. Use:
```python
vor = nt.nodes.new("ShaderNodeTexVoronoi")
vor.feature = "DISTANCE_TO_EDGE"  # or "F1", "SMOOTH_F1"
vor.distance = "MANHATTAN"        # "EUCLIDEAN", "MANHATTAN", "CHEBYCHEV", "MINKOWSKI"
```

---

## 4. Headless (`-b`) `bpy.ops.object.mode_set(mode="EDIT")` Poll Failure
Wrapping `bpy.ops.object.mode_set(mode="EDIT")` + `bpy.ops.mesh.select_all(action="SELECT")` solely inside `with bpy.context.temp_override(...)` in background mode (`blender -b`, where no `VIEW_3D` area exists) can fail with `Operator bpy.ops.mesh.select_all.poll() failed`.
- **Fix:** Set selection and active object directly on `bpy.context.view_layer` before calling `mode_set`:
```python
core.ensure_object_mode()
for o in bpy.context.view_layer.objects:
    o.select_set(False)
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
# ... UV / mesh ops ...
bpy.ops.object.mode_set(mode="OBJECT")
ob.select_set(False)
```

---

## 5. Cloud-Synced Folders (`OneDrive` / `Dropbox`) Locking `OpenImageIO` Writes & Power-Loss Corruption
When Cycles writes several high-res PNGs rapidly into a OneDrive-synced folder, OneDrive's background indexer briefly locks newly created files, causing Blender's `OpenImageIO` saver to throw `Could not open file`. In addition, bare `shutil.copy2` writes can leave zero-filled (`0x00`) corrupted files if power is cut before the OS NTFS cache flushes.
- **Fix:** Always render/save into `tempfile.gettempdir()` first, stage to a sibling temp file, call `os.fsync()`, and atomically replace via `os.replace()` inside a 6-attempt `PermissionError` retry loop (`vflib.bake.render_still_safe` & `vflib.bake.save_png_8bit`).

---

## 6. Freed StructRNA References When Clearing Studio Collections
`vflib.core.clear_collection(studio_col)` automatically removes zero-user datablocks (`Light`, `Camera`, `Mesh`). Calling `bpy.data.lights.remove(light_data)` afterward raises `ReferenceError: StructRNA of type AreaLight has been removed`. Let `clear_collection` clean up datablocks on its own.

---

## 7. Hybrid GPU + All-Core CPU Power Spikes (`d.use = True`) & CPU OIDN Denoising Spikes
On high-core-count workstations (e.g. 16-core/32-thread Ryzen 9 + RTX GPU), two silent Cycles defaults cause simultaneous GPU + all-core CPU transient spikes during `vforge bake`:
1. **Never loop `for d in prefs.devices: d.use = True`:** That activates **both** the GPU (`OPTIX`/`CUDA`) and all CPU cores simultaneously! Always filter strictly to GPU-only:
   ```python
   for d in prefs.devices:
       d.use = (d.type == dev_type)
   ```
2. **Never leave default CPU `OPENIMAGEDENOISE` with `AUTO` threads:** Blender 5.2/5.3 defaults `sc.cycles.denoiser = "OPENIMAGEDENOISE"` with `denoising_use_gpu = False` and `threads_mode = "AUTO"`, firing an all-core AVX2 CPU spike right on top of a hot GPU pass!
- **Fix (Built Automatically into `vflib.bake.enable_cycles_gpu`, `engine/blender/safe_bake_runner.py` & `vforge bake`):**
  - Strictly GPU-only device selection (`d.use = (d.type == dev_type)`).
  - GPU denoising (`sc.cycles.denoiser = "OPTIX"` on OptiX GPUs, or `denoising_use_gpu = True` on CUDA/HIP/ONEAPI/Metal).
  - Fixed CPU thread cap (`sc.render.threads_mode = "FIXED"`, `-t 8` / `VELUM_BLENDER_THREADS=8`, plus `OMP`/`TBB`/`OPENBLAS`/`MKL_NUM_THREADS=8`) and Windows `BELOW_NORMAL_PRIORITY_CLASS`.
  - Safe tile size (`sc.cycles.use_auto_tile = True`, `tile_size = 512`) + deduplicated `1.0 s` GC + thermal cooldown (`VELUM_BAKE_COOLDOWN=1.0`) between heavy Cycles passes.
  - Runtime operator interception via `engine/blender/safe_bake_runner.py` on `bpy.ops.object.bake` and `bpy.ops.render.render`, guaranteeing even legacy or AI-generated bake scripts cannot re-enable CPU hybrid rendering or skip cooldowns in headless `-b` mode.
  - Crash-safe (`fsync`'d) cross-process sequential GPU lock (`~/.velum-forge/gpu_bake.lock`) so concurrent bakes never overlap, plus `--factory-startup` by default in headless batch jobs (opt in with `--user-addons`).

---

## 8. `TEX_SKY` Node (`aerosol_density` vs. `dust_density` in Blender 5.3)
In Blender 5.3, `ShaderNodeTexSky` (Nishita sky) replaced `dust_density` with `aerosol_density`. Direct assignment raises `AttributeError`.
- **Fix:** Guard every sky-node attribute write:
```python
if hasattr(sky, "aerosol_density"):
    sky.aerosol_density = 0.28
elif hasattr(sky, "dust_density"):
    sky.dust_density = 0.28
```

---

## 9. UV Clamp-Before-Nudge Ordering (Edge Collapse Bug)
If you nudge degenerate UV triangles (`abs(area_2d) < 1e-10`) **before** clamping UVs inside `[0.001, 0.999]`, boundary-hugging triangles near `u=0` or `u=1` get clamped *after* nudging and collapse back onto the edge line.
- **Fix:** Always clamp every UV vertex inside `[0.001, 0.999]` **first**, then detect near-zero-area UV faces and apply a `0.00015` separation offset (`vflib.bake.reweld_and_clamp_uvs`).

---

## 10. Cycles `ShaderNodeWireframe` Auto-Triangulates Quads
Cycles/EEVEE `ShaderNodeWireframe` tessellates every quad into diagonal triangles at render time, making clean quad topology look triangulated in shader renders.
- **Fix:** To prove clean quad loops visually (`vflib.integrity.verify_quad_flow` / `render_quad_flow_proof`), run `tris_convert_to_quads` on a duplicate verification object and render it with a **`WIREFRAME` modifier** (never `ShaderNodeWireframe`).

---

## 11. `runpy.run_path` Raises `SystemExit(0)` on Build Scripts
Modular build scripts ending with `if __name__ == "__main__": raise SystemExit(main())` raise `SystemExit(0)` when loaded inside headless QA harnesses via `runpy.run_path(..., run_name="__main__")`.
- **Fix:** Catch `SystemExit` in `qa_pipeline.py` and treat `exc.code in (0, None)` as normal completion.

---

## 12. Sky-Glare Matte Canvas Washout & Helper Fill Light Glass Discs
Under high-altitude Nishita sunlight, Blender's default `Specular IOR Level = 0.5` turns striped awning/umbrella cotton fabrics milky white. Meanwhile, invisible studio helper `AREA` fill lights (`VF_IntFill`) appear as bright circular discs in storefront glass and picture frames.
- **Fix:** Set `Specular IOR Level` to `0.06–0.08` (`Roughness >= 0.80`) on matte canvas/linen fabrics, and set `light_obj.visible_glossy = False` on helper fill lights.

---

## 13. Instance-Safe `Z = 0` Grounding (`users > 1` Linked Meshes)
Looping over objects and translating `ob.data` vertices directly shifts a shared `Mesh` datablock `N` times (sending linked instances flying dozens of meters into the sky or underground).
- **Fix:** Use `vflib.geo.ground_objects_safe(objs)`: transform instanced objects via `ob.location.z` and translate any unique non-instanced `ob.data` at most once (tracked via `seen_mesh_ptrs`).

---

## 14. Non-Destructive Roblox Export Naming (`_src` Suffix Leak)
Renaming conflicting source objects to `<name>_src` inside `export_roblox()` without restoring them leaves permanent `_src` suffixes across Outliner collections when saving the `.blend`.
- **Fix:** Wrap export cleanup in `try ... finally` and restore every original source object name after writing `.fbx` / `.glb` / `.luau`.
