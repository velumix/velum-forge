---
name: velum-cad-brep
description: Precision OpenCascade B-Rep mechanical CAD modeling with build123d and cad_bridge.py. Use for machined, cast, or industrial hard-surface components (hydrants, parking meters, trash bins, wheels, cleats, throttles, propellers, brackets, enclosures, fasteners) exported as STEP + watertight 1:1 meter GLB for Blender assembly — and learn when to use structured quad-flow bmesh instead.
---

# Velum OpenCascade B-Rep CAD (`build123d` -> `cad_bridge.py`)

Use `build123d` + `engine/cad/cad_bridge.py` whenever a component requires exact **boolean unions/subtractions, circular bolt arrays, chamfered/filleted cast iron or machined metal housings, threaded collars, marine hardware, or street utilities**.

---

## 1. When to Use `build123d` B-Rep CAD vs. Structured Quad-Flow `bmesh`

Choose the right geometry generator up front so downstream editing, Subdivision Surface, and `Alt+J` / `Un-Subdivide` work as expected:

| Use **`build123d` OpenCascade B-Rep** (`engine/cad/cad_bridge.py`) | Use **Structured Quad-Flow `bmesh`** (`vflib.geo` / `vflib.quadflow`) |
| :--- | :--- |
| Fire hydrants, bollard posts, street lamp heads, parking meters, cast-iron drain grates, slotted trash bins | Bistro chairs, dining tables, barstools, velvet/tufted banquettes, sofas, architectural frames & moldings |
| Marine cleats, propellers, throttle levers, steering wheels, flanged deck vents, winches, machined brackets | Cups, saucers, wine/cocktail glasses, bottles, plates, vases, canopies, umbrellas, architectural hulls |
| Multi-cut industrial enclosures, precision gear teeth, countersunk fastener plates (`STEP` export needed) | Any hero prop where clean `Alt+J` (`>= 80%` quad recovery), `Subdivision Surface`, and `Decimate -> Un-Subdivide` are required |

**Why:** OpenCascade B-Rep exports Delaunay triangle fans across planar/filleted surfaces (`import_cad_to_bmesh`). That is ideal and watertight for machined metal hardware, but breaks manual loop selection, SubD smoothing, and `Un-Subdivide` on curved hospitality furniture and tableware.

---

## 2. Standard `cad_bridge.py` Pipeline (`1:1 m`, `+Z` Up)

1. Author parametric parts in `.venv\Scripts\python.exe` with `build123d` (`mm` or `m`, strictly converted to **`1.0 unit = 1.0 m`** at export).
2. Export both parametric `.step` (for CAD archival/inspection) and watertight triangulated `.glb` via `engine/cad/cad_bridge.py` (`cad_bridge.export_cad_part(...)` / `export_cad_assembly(...)`).
3. Keep hardware pivots centered cleanly (`X=0, Y=0, Z_min=0.0000 m`) so Blender assembly scripts can spawn linked instances cleanly across streets, decks, or hulls.
4. Import into Blender via `vflib.geo.import_cad_to_bmesh(...)` (automatically ensures outward signed-volume normals, `quad_method="FIXED"`, clean material slot mapping, and `vf_asset_set` tagging).

---

## 3. Quality Guardrails

- Check fillet radii stay strictly below half the thinnest adjacent wall thickness (`r_fillet < 0.45 * min_wall`) so OpenCascade Booleans never create inverted/zero-thickness shells.
- Verify imported GLB meshes show **`0` non-manifold edges**, **`0` negative signed-volume islands**, and **exact meter scale (`scale=(1,1,1)`)** in `vforge qa`.
- Group small repeating CAD utilities (e.g., street meters, hydrants, deck cleats) onto dedicated modular `vf_asset_set` groups (`2048x2048` PBR bake) or assign `DOWNWEIGHT_PARTS` only for tiny micro-screws/bolts inside larger hero hardware.
