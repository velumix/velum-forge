---
name: velum-architecture-environments
description: Production standard for architectural landmarks, restaurants, commercial interiors, hospitality furniture, urban streetscapes, signage, and realistic 3D botanicals in Blender 5.2+ using Velum Forge.
---

# Velum Architecture & Environments

Use this skill alongside `velum-3d-workflow` whenever building **buildings, restaurants, storefronts, interiors, urban streetscapes, patios, seating/tables, custom lighting/bars, signage, or exterior landscaping**. Reference implementation: `examples/news_cafe_south_beach/`.

---

## 1. Multi-Datum Elevation Locking (Zero Negative Embedding / Zero Gaps)

Architectural environments never rest on a single `Z = 0` slab. Define explicit named elevation constants in a single shared module (or top of the build script) and reference them everywhere:

- `Z_ROAD = 0.000` (lowest road/street base datum)
- `Z_SW` (top of sidewalk/terrace slab, e.g., `0.152 m` above road curb)
- `Z_FLOOR_INT` (interior finished floor, e.g., `Z_SW + 0.025 m`)
- Explicit landing/step/balcony/parapet datums (`Z_STEP_1`, `Z_MEZZ`, `Z_BALCONY_2`, `Z_BALCONY_3`, `Z_ROOF`)
- **Rule:** Never place interior furniture, doors, storefront frames, planters, host stands, or street furniture with `Z < local_floor_z`. Anchor every part bottom strictly flush (`+0.000 m`) or seated into a physical curb/socket (`+0.002 m` max seat tolerance where appropriate).

---

## 2. Deterministic Obstacle Clearance Registry

Before placing patio tables, chairs, umbrellas, planters, host stands, or sidewalk fixtures, maintain a `2D` exclusion registry (`list[(x, y, radius)]`) populated by:

- Structural columns, pilasters, building corners, and awning support posts
- Umbrella center poles and weighted stone/cast bases
- Curb ramps, bollards, hydrants, parking meters, bike racks, and tree wells
- **Rule:** Validate every placed furniture cluster against the clearance registry (`dist >= r_item + r_obstacle + walkway_margin`) so chairs, table rims, and bistro umbrellas never intersect poles, walls, or tree trunks.

---

## 3. Structural Joint Locks & Micro-Detail Rules

Furniture, railings, awnings, bar fixtures, and architectural trim fail visual inspection when tubes miss collars, float, or punch through opposite faces:

- **Footrails & Handrails:** Build closed rail rings with zero-twist `vflib.geo.add_torus_ring` and cast outer **T-collars** / sleeve ferrules that wrap the rail circumference. Terminate radial spokes, struts, and leg stretchers **strictly inside the collar centerline** (`r_end <= r_collar_center`), never protruding out the far side.
- **Brackets & Wall Mounts:** Add flush rear mounting flanges anchored directly to wall/bar apron surfaces (`0.000 m` gap).
- **Chairs & Barstools:** Tuck curved rear/front legs smoothly into the seat hoop skirt, fit flat floor glides/ferrules at `Z_local = 0.000 m`, and span woven/upholstered seats and backrest panels across **360 deg** into the perimeter frame groove.
- **Storefront Awnings & Canopies:** Verify downward awning pitch (`z_front < z_wall_mount`) so rain sheds forward away from the facade, attach tension arms to the storefront transom/header, and clear operable doors/windows cleanly.
- **Breeze Blocks & Fretwork:** Use manifold geometric blocks (`vflib.geo.add_breeze_block`) recessed inside solid perimeter frames/coping rails rather than floating paper planes.

---

## 4. Real 3D Interior Architecture & Decor (Never Flat Wall Stickers)

- **Framed Artworks & Mirrors:** Build single-manifold **45 deg mitered frames** (`vflib.geo.add_mitered_frame`) + gilded brass inner fillets + stepped museum mat boards + recessed glass/art planes + 3D brass picture lights overhead (`vflib.geo.add_spline_tube` + shade). Never paste flat single-quad posters on walls.
- **Banquettes, Sofas & Upholstered Seating:** Build sculpted multi-ring **channel-tufted** seat/back profiles using `vflib.geo.add_quad_grid_box` / revolved lofted bolsters, rolled lumbar cushions, recessed kickbases/plinths (`Z = Z_FLOOR_INT`), and perimeter piping — never blocky beveled boxes.
- **Bar & Kitchen Back-of-House:** Include stepped bottle speed-rails, brass gallery rails, under-counter refrigeration/espresso hardware, espresso portafilters, glassware racks, and warm under-shelf LED coves.

---

## 5. Realistic 3D Botanicals (Zero Blobs or Broomsticks)

Never represent trees or shrubs with displaced icospheres, metaballs, or rigid straight cone spokes:

- **Coconut / Royal Palms:** Curved tapered trunks built via `vflib.geo.add_spline_tube` with alternating **sawtooth leaf-scar rings**, woody crownshafts, and gracefully drooping **curved pinnate fronds** fitted with angled individual leaflets (`vflib.geo.add_curved_leaf`) and coconut clusters.
- **Coastal / Deciduous Trees (Sea Grape / Tropical Canopy):** Gnarled forked boughs (`add_spline_tube` branching hierarchies), fluted/fissured bark profiles, and layered leaf clusters with natural pitch/roll variation.
- **Bougainvillea & Planters:** Terracotta/stone planters with soil mounds sitting **below** the rim (never exposed planter base boxes poking through sidewalks!), climbing woody vines, dark ovate leaves, and **3-bract papery blossoms** (`vflib.geo.add_bougainvillea_cluster`).
- **Botanical De-Confliction:** Run `vflib.geo.deconflict_botanical_islands` (bounded non-oscillating impulse separation on overlapping foliage/petal islands) so leaves and bracts never Z-fight or slice cleanly through each other while staying anchored to their stems.

---

## 6. Structured Quad-Flow Topology for Architectural Hero Props

Tables, chairs, barstools, cups, saucers, glasses, planters, and architectural moldings must convert cleanly between tris and quads (`Alt+J` / `UNSUBDIV` / Subdivision Surface):

- Author with explicit quad-grid / revolved / swept `bmesh` helpers (`vflib.geo.add_torus_ring`, `add_revolved_profile`, `add_revolved_ring`, `add_quad_sphere`, `add_quad_grid_box`, `add_spline_tube`) using continuous edge loops and polar/grid pole rings.
- Triangulate exported meshes exclusively via `bmesh.ops.triangulate(..., quad_method="FIXED")` (`vflib.geo.finalize_mesh_data` / `finalize_part`) so diagonal pairing recovers **>= 80%** clean quads on `bpy.ops.mesh.tris_convert_to_quads()` (`Alt+J`).
- Verify hero props with `vflib.integrity.verify_quad_flow(...)` and visual `WIREFRAME` modifier proof sheets (never rely on Cycles `ShaderNodeWireframe`, which auto-triangulates quads).

---

## 7. Modular Outliner Hierarchy, Linked Instancing & `vf_asset_set`

Large scenes **must never** be joined into 1–2 monolithic meshes that crush all chairs, interior decor, facades, and trees onto a single cramped UV atlas:

- Split the scene into semantic Outliner sub-collections using `vflib.geo.sub_collection(...)` (e.g., `Architecture/Shell`, `Architecture/Windows`, `Architecture/Balconies`, `Interior/Bar`, `Interior/Banquettes`, `Patio/Tables`, `Patio/Chairs`, `Patio/Umbrellas`, `Botanicals/Palms`, `Streetscape/Curbs_And_Props`).
- Stamp repeating assets (bistro chairs, barstools, marble tables, espresso cups, banquettes, palms, awnings, breeze blocks) with **linked `Mesh` datablocks** (`vflib.geo.spawn_instance(...)`, local pivot centered at `X=0, Y=0, Z=0`), tagging each part with `ob["vf_asset_set"] = "<set_key>"` and `ob["vf_instanced"] = True`.
- **Split-Before-Decimate (`> 20k` Tris Rule):** If any object exceeds `20,000` tris because multiple repeated or separable items are joined together (e.g., 2+ barstools, dining chairs, tables + tableware, lighting fixtures, or architectural props), **split them into individual linked instances or logical sub-objects FIRST** rather than lowering poly detail or decimating. Each single instance stays crisp, lightweight, and comfortably under `20k` tris while multiplying UV texel density.
- Group texture baking by `vf_asset_set` and bake **each set onto its own dedicated `2048x2048` (2K) 6-map PBR atlas** (delivering 15x–45x higher texel density than monolithic atlases).
- Save clean `.blend` scenes with **zero `_src` Outliner suffixes**.

---

## 8. Dual-UV Signage, 2D Artwork & Lighting/Material Hygiene

- **Programmatic 2D Graphics (`textures_src/`):** Generate crisp typography, awnings logos, street signs (`ONE WAY`, `STOP`, Miami street markers), menus, and gallery artwork via Pillow (`PIL`) into `textures_src/`.
- **Dual-UV Baking:** Keep raw artwork readable on a dedicated `GraphicUV` UV layer mapped cleanly onto sign faces (`vflib.geo.add_uv_mapped_sign_plate`), while baking the full scene PBR atlas onto `UVMap` (`vflib.bake.prepare_sign_fixture_uvs` / `prepare_continuous_graphic_atlas_uvs`). Remove `GraphicUV` only after baking (`vflib.bake.assign_baked_and_strip_graphic_uv`).
- **Sky-Glare & Interior Fill Light Hygiene:**
  - Keep matte awning and umbrella canvases at low `Specular IOR Level` (`0.06–0.08`) so Nishita daylight never washes fabric stripes white.
  - Set `ob.visible_glossy = False` on any invisible helper interior fill/bounce area lights so circular white discs never reflect in storefront glass, picture glass, or chrome.

---

## 9. Mandatory Architectural QA Cameras, Opt-In High-Poly Toggle & Always-10/10 Review

- **Standard vs Opt-In High-Poly Uncapped Mode:** By default, run `vforge qa` with `--profile game --max-tris 300000` (or `--profile roblox` for strict `<20k`/part). When **High-Poly Uncapped Mode** is explicitly toggled (`--high-poly`, `high_poly_uncapped: true`, Studio UI toggle, or explicit prompt request such as *"photorealistic high-poly"* / *"no 300k cap"*), pass **`--profile game --high-poly --max-tris 0`** and adhere strictly to News Cafe ArchViz fidelity floors:
  - **Never slash radial segments or botanicals to chase a tri cap** (`--max-tris 0` = unlimited BVH; still use linked instances for 2K texel density).
  - Hero furniture/tabletops/rings/globes: `24–36` radial segs; curved bentwood/legs: `12–16` segs + Catmull-Rom `substeps=3` (`add_spline_tube(..., substeps=3)`); tableware/bottles: `16–24` segs; micro-beveled architectural trim (`add_box(..., bevel=0.004..0.020)`) & `20–24`-seg curved curbs/breeze blocks (`add_breeze_block(..., style="quatrefoil")`); coconut palms (`20–24`-seg curved trunks, `14–18` fronds × `16–22` pairs of `3`-seg curved V-folded leaflets) + dense branched shade trees & hedges (`40k–250k+` botanical tris).
- In addition to standard turntable + contact sheets, render and visually inspect:
  1. **Street-level pedestrian hero angles** matched to reference photography/Street View.
  2. **Interior eye-level shots** showing bar counter, speed rails, framed 3D paintings, and banquette channel-tufting.
  3. **Macro joint & tabletop close-ups** (`baked_macro_bistro.png`) proving zero rail overhang, clean T-collars, crisp 2K text/signage, and flush `Z` grounding.
- **Strict Always-`10.0 / 10` Self-Rating Standard:** Whenever Iterative Critic / Honest Rating is active, the target is **ALWAYS `10.0 / 10`** with `0` QA errors, `0` QA warnings, and `0` unresolved defects — never rush, never fake scores, and never stop or proceed to baking below **`10 / 10`**. When High-Poly Uncapped Mode is ON, faceted low-segment (`<= 10` segs) hero props block `10.0 / 10`.
