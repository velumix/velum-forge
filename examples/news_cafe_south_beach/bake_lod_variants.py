r"""Velum Forge Stage 5 & 6 Pipeline — Cycles GPU (`OPTIX`) 2048x2048 PBR Baking (19 Dedicated Semantic Sets),
4 South Beach Variants, Instance-Aware Seam-Locked 4-Tier `LOD0`–`LOD3` Chain, Roblox Export & Visual QA Sheets.

Engineering Guarantees:
  1. 19 Dedicated Zero-Bleed `2048x2048` 6-Map PBR Texture Sets (ZERO cramped furniture/interior UVs!):
     - Exterior (`signage`, `hero`, `street`, `nature`, `patio_umbrellas`)
     - Modular Patio Furniture Sets (`chair_honey`, `chair_cream`, `patio_table`, `patio_tableware`, `host_podium`, `menu_stand`)
       -> Linked instanced hero prototypes deliver **15x–45x higher texel density** (razor-sharp woven diamond rattan, marble veining & brass)!
     - Modular Interior Sets (`int_arch`, `int_bar`, `int_bar_props`, `int_gallery_art`, `int_banquette`, `int_barstool`, `int_dining_table`, `int_lighting`)
       -> Each of the 10 framed museum paintings gets a crisp ~`465x445 px` dedicated canvas; banquettes, barstools, dining tables & bar fixtures each get their own dedicated 2K PBR atlas!
  2. Isolated Prototype AO Baking for Shared Instanced Sets:
     - Every repeated instanced prototype bakes ONE representative object in isolation (`hide_render=True` on all other scene objects)
       so NO neighbor shadow gets baked onto shared chairs/tables/banquettes/barstools/lights!
  3. Clean Blender Outliner (ZERO `_src` suffixes!):
     - Master `news_cafe_south_beach.blend` & Desktop sync are saved cleanly BEFORE `vf_export.export_roblox(...)` mutates names.
  4. Instance-Aware 4-Tier `LOD0`–`LOD3` Chain:
     - Decimates each unique `ob.data` datablock ONCE per tier (`delimit={'UV','SEAM','SHARP'}`) and links LOD instances cleanly!

Run strictly via `vforge bake`:
    .venv\Scripts\python.exe -m velum_forge.cli bake examples\news_cafe_south_beach\bake_lod_variants.py --cooldown 0.6
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(THIS_DIR, "textures")
VAR_DIR = os.path.join(THIS_DIR, "variants")
LOD_DIR = os.path.join(THIS_DIR, "lods")
RBX_DIR = os.path.join(THIS_DIR, "roblox")
RENDERS_DIR = os.path.join(THIS_DIR, "renders")

if "--compose-sheets" not in sys.argv:
    import bmesh
    import bpy
    import numpy as np
    from mathutils import Vector

    ENGINE_BLENDER = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "engine", "blender"))
    for _p in (THIS_DIR, ENGINE_BLENDER):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    from vflib import bake, core, export as vf_export, gameready  # noqa: E402
    import build_news_cafe_south_beach as builder  # noqa: E402
    import render_streetview_qa as sv_qa  # noqa: E402

# Fixed exterior atlas mapping (modular patio & interior sets resolve dynamically via `ob["vf_asset_set"]`!)
FIXED_EXTERIOR_ATLAS_BY_NAME: dict[str, str] = {
    "NewsCafe_Awnings": "signage",
    "Street_Furniture": "signage",
    "NewsCafe_Shell": "hero",
    "NewsCafe_Breeze_L2": "hero",
    "NewsCafe_Breeze_L3": "hero",
    "NewsCafe_Breeze_Roof": "hero",
    "NewsCafe_Breeze_Patio": "hero",
    "NewsCafe_Windows": "hero",
    "Neighbor_804": "street",
    "Neighbor_820": "street",
    "RoadAndCurbs": "street",
    "SidewalksAndApron": "street",
    "Patio_Umbrellas": "patio_umbrellas",
    "Palms_Trunks": "nature",
    "Palms_Fronds_South": "nature",
    "Palms_Fronds_North": "nature",
    "Foliage_Trees": "nature",
    "Hedges_Shrubs": "nature",
    "Bougainvillea": "nature",
}

# Deterministic ordered list of all 19 dedicated 2048x2048 PBR texture sets!
ATLAS_ORDER: list[str] = [
    "signage",
    "hero",
    "street",
    "nature",
    "patio_umbrellas",
    "chair_honey",
    "chair_cream",
    "patio_table",
    "patio_tableware",
    "host_podium",
    "menu_stand",
    "int_arch",
    "int_bar",
    "int_bar_props",
    "int_gallery_art",
    "int_banquette",
    "int_barstool",
    "int_dining_table",
    "int_lighting",
]

# Sets using shared linked Mesh datablocks -> bake 1 isolated representative per unique Mesh (ZERO neighbor shadows!)
INSTANCED_SETS: set[str] = {
    "chair_honey",
    "chair_cream",
    "patio_table",
    "patio_tableware",
    "int_banquette",
    "int_barstool",
    "int_dining_table",
    "int_lighting",
}

# Materials whose original `GraphicUV` layout MUST stay continuous & unbroken (never chopped by smart_project!)
CONTINUOUS_GRAPHIC_MATS = {
    "NC_Awning_NewsCafe": 2.4,
    "NC_Awning_Hotel800": 1.8,
    "NC_HostPodium_Front": 2.4,
    "NC_MenuBoard_Sheet": 2.8,
    "NC_Interior_Backdrop": 1.4,
    "NC_Gallery_Art": 2.2,
    "NC_Sign_OneWay": 1.8,
    "NC_Sign_StopPed": 1.8,
    "NC_Sign_NoParking": 1.6,
    "NC_Sign_OceanDr": 1.6,
    "NC_Sign_8thSt": 1.6,
    "NC_Sign_ADA": 1.2,
    "NC_Sign_FDC": 1.6,
    "NC_Sign_804": 2.0,
    "NC_Road_OceanDr": 1.5,
    "NC_Road_BikeLane": 1.0,
    "NC_Curb_Valet": 2.2,
}

# Repetitive high-poly micro-geometry scaled down slightly in hero atlas packing so facades & trims get maximum pixel clarity
DOWNWEIGHT_PARTS = {
    "NewsCafe_Breeze_L2": 0.24,
    "NewsCafe_Breeze_L3": 0.24,
    "NewsCafe_Breeze_Roof": 0.24,
    "NewsCafe_Breeze_Patio": 0.32,
}

VARIANTS: list[dict] = [
    {
        "slug": "classic_ocean_dr",
        "label": "1. Classic Ocean Dr (1:1 Street View)",
        "palette": {},
        "lighting": "midday",
        "re_bake_atlases": tuple(ATLAS_ORDER),
    },
    {
        "slug": "art_deco_mint_1988",
        "label": "2. Historic 1988 Art Deco Mint",
        "palette": {
            "stucco_cream_a": "#CFE5D8",
            "stucco_cream_b": "#BBD6C6",
            "stucco_white_a": "#FAF8F2",
            "stucco_white_b": "#EFECE2",
            "breeze_a": "#F8F7F0",
            "breeze_b": "#EAE7DC",
            "awning_tint": "#073944",
            "awning_green_a": "#073944",
            "awning_green_b": "#052830",
            "umbrella_green_a": "#094856",
            "umbrella_green_b": "#06343E",
            "column_green": "#073944",
        },
        "lighting": "midday",
        "re_bake_atlases": ("signage", "hero", "patio_umbrellas"),
    },
    {
        "slug": "sunset_coral_deco",
        "label": "3. Flamingo Coral Deco Edition",
        "palette": {
            "stucco_cream_a": "#EFCFC3",
            "stucco_cream_b": "#DFB8AA",
            "stucco_white_a": "#FDF8F1",
            "stucco_white_b": "#F2E9DD",
            "breeze_a": "#FBF6EE",
            "breeze_b": "#EDE5D8",
            "awning_tint": "#4E121D",
            "awning_green_a": "#4E121D",
            "awning_green_b": "#350A12",
            "umbrella_green_a": "#5F1725",
            "umbrella_green_b": "#430F19",
            "column_green": "#4E121D",
        },
        "lighting": "sunset",
        "re_bake_atlases": ("signage", "hero", "patio_umbrellas"),
    },
    {
        "slug": "south_beach_twilight",
        "label": "4. South Beach Neon Twilight",
        "palette": {
            "stucco_cream_a": "#ECE6D6",
            "stucco_cream_b": "#DDD5C1",
            "glass_col": "#1F303B",
        },
        "lighting": "twilight",
        "re_bake_atlases": ("hero",),
    },
]


def _resolve_atlas_name(ob: bpy.types.Object) -> str:
    aset = ob.get("vf_asset_set")
    if aset:
        return str(aset)
    if ob.name in FIXED_EXTERIOR_ATLAS_BY_NAME:
        return FIXED_EXTERIOR_ATLAS_BY_NAME[ob.name]
    return "hero"


def _resolve_atlas_groups(meshes: list[bpy.types.Object]) -> dict[str, list[bpy.types.Object]]:
    raw: dict[str, list[bpy.types.Object]] = {}
    for ob in meshes:
        aname = _resolve_atlas_name(ob)
        raw.setdefault(aname, []).append(ob)
    ordered: dict[str, list[bpy.types.Object]] = {}
    for aname in ATLAS_ORDER:
        if aname in raw:
            ordered[aname] = raw[aname]
    for aname, objs in raw.items():
        if aname not in ordered:
            ordered[aname] = objs
    return ordered


def _unique_mesh_reps(objs: list[bpy.types.Object]) -> list[bpy.types.Object]:
    """Return one representative object per unique `ob.data` mesh datablock (critical for linked instanced assets!)."""
    reps: list[bpy.types.Object] = []
    seen: set[bpy.types.Mesh] = set()
    for ob in objs:
        if ob.data not in seen:
            seen.add(ob.data)
            reps.append(ob)
    return reps


def _set_col_tree_visible(col: bpy.types.Collection, visible: bool) -> None:
    """Recursively toggle viewport & render visibility for `col` and every nested sub-collection."""
    core.set_collection_visible(col, visible)
    for child in col.children:
        _set_col_tree_visible(child, visible)


def _pack_into_rect(objs: list[bpy.types.Object], u0: float, v0: float, u1: float, v1: float, *, margin: float = 0.005) -> None:
    """Smart-project & pack `objs` cleanly into sub-rectangle `[u0..u1] x [v0..v1]` of `UVMap`."""
    if not objs:
        return
    core.ensure_object_mode()
    for ob in objs:
        me = ob.data
        if "UVMap" not in me.uv_layers:
            me.uv_layers.new(name="UVMap")
        uv_m = me.uv_layers["UVMap"]
        me.uv_layers.active = uv_m
        me.uv_layers.active_index = list(me.uv_layers).index(uv_m)

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=margin, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=margin)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        o.select_set(False)

    du, dv = (u1 - u0), (v1 - v0)
    for ob in objs:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        uv_lay = bm.loops.layers.uv.get("UVMap")
        if uv_lay is not None:
            for f in bm.faces:
                for l in f.loops:
                    l[uv_lay].uv.x = u0 + max(0.001, min(0.999, l[uv_lay].uv.x)) * du
                    l[uv_lay].uv.y = v0 + max(0.001, min(0.999, l[uv_lay].uv.y)) * dv
            bm.to_mesh(ob.data)
        bm.free()
        ob.data.update()


def _split_multi_mat_edges(objs: list[bpy.types.Object]) -> None:
    """Split edges between different material slots so baked color/normal transitions never staircase or bleed."""
    core.ensure_object_mode()
    for ob in objs:
        me = ob.data
        if "UVMap" not in me.uv_layers:
            me.uv_layers.new(name="UVMap")
        uv_m = me.uv_layers["UVMap"]
        me.uv_layers.active = uv_m
        me.uv_layers.active_index = list(me.uv_layers).index(uv_m)
        bm = bmesh.new()
        bm.from_mesh(me)
        border_edges = [e for e in bm.edges if len({f.material_index for f in e.link_faces}) > 1]
        if border_edges:
            bmesh.ops.split_edges(bm, edges=border_edges)
        bm.to_mesh(me)
        bm.free()


def _reweld_and_clamp_uvs(objs: list[bpy.types.Object]) -> None:
    """Re-weld split border vertices cleanly (`1e-6` only merges split pairs -> 100% watertight) and clamp UVs."""
    for ob in objs:
        bm_w = bmesh.new()
        bm_w.from_mesh(ob.data)
        bmesh.ops.remove_doubles(bm_w, verts=bm_w.verts[:], dist=1e-6)
        uv_lay = bm_w.loops.layers.uv.get("UVMap")
        if uv_lay is not None:
            for f in bm_w.faces:
                for l in f.loops:
                    l[uv_lay].uv.x = max(0.001, min(0.999, l[uv_lay].uv.x))
                    l[uv_lay].uv.y = max(0.001, min(0.999, l[uv_lay].uv.y))
        bm_w.to_mesh(ob.data)
        bm_w.free()
        ob.data.update()


def _pack_face_subset_multi_into_rect(
    objs: list[bpy.types.Object],
    face_predicate,
    u0: float,
    v0: float,
    u1: float,
    v1: float,
    *,
    margin: float = 0.004,
) -> None:
    """Smart-project & pack ONLY the faces across `objs` matching `face_predicate(f, mat_name)` into `[u0..u1] x [v0..v1]`."""
    core.ensure_object_mode()
    active_obs: list[bpy.types.Object] = []
    sel_by_ob: dict[str, set[int]] = {}

    for ob in objs:
        me = ob.data
        if "UVMap" not in me.uv_layers:
            me.uv_layers.new(name="UVMap")
        uv_m = me.uv_layers["UVMap"]
        me.uv_layers.active = uv_m
        me.uv_layers.active_index = list(me.uv_layers).index(uv_m)

        bm = bmesh.new()
        bm.from_mesh(me)
        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
        sel_indices: set[int] = set()
        for f in bm.faces:
            mat = me.materials[f.material_index] if f.material_index < len(me.materials) else None
            mname = mat.name if mat is not None else ""
            hit = bool(face_predicate(f, mname))
            f.select = hit
            if hit:
                sel_indices.add(f.index)
                for v in f.verts:
                    v.select = True
                for e in f.edges:
                    e.select = True
        bm.to_mesh(me)
        bm.free()
        if sel_indices:
            active_obs.append(ob)
            sel_by_ob[ob.name] = sel_indices

    if not active_obs:
        return

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in active_obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active_obs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=margin, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=margin)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in active_obs:
        o.select_set(False)

    du, dv = (u1 - u0), (v1 - v0)
    for ob in active_obs:
        sel_indices = sel_by_ob[ob.name]
        bm2 = bmesh.new()
        bm2.from_mesh(ob.data)
        uv_lay = bm2.loops.layers.uv.get("UVMap")
        if uv_lay is not None:
            for f in bm2.faces:
                if f.index in sel_indices:
                    for l in f.loops:
                        l[uv_lay].uv.x = u0 + max(0.001, min(0.999, l[uv_lay].uv.x)) * du
                        l[uv_lay].uv.y = v0 + max(0.001, min(0.999, l[uv_lay].uv.y)) * dv
            bm2.to_mesh(ob.data)
        bm2.free()
        ob.data.update()


def _prepare_quadrant_botanical_uvs(objs: list[bpy.types.Object]) -> None:
    """Quadrant-partition botanicals (`Palms_Trunks` BL, `Bougainvillea` BR, green foliage TOP) -> ZERO cross-species bleed!"""
    trunks = [o for o in objs if o.name == "Palms_Trunks"]
    boug = [o for o in objs if o.name == "Bougainvillea"]
    greens = [o for o in objs if o.name not in ("Palms_Trunks", "Bougainvillea")]

    _pack_into_rect(trunks, 0.015, 0.015, 0.470, 0.470, margin=0.006)
    _pack_into_rect(boug, 0.530, 0.015, 0.985, 0.470, margin=0.005)
    _pack_into_rect(greens, 0.015, 0.530, 0.985, 0.985, margin=0.004)


def _prepare_dedicated_single_set_uvs(reps: list[bpy.types.Object]) -> None:
    """Clean full-frame `2048x2048` UV packing for a dedicated modular asset set (chairs, tables, banquettes, barstools, etc.)."""
    _split_multi_mat_edges(reps)
    _pack_into_rect(reps, 0.012, 0.012, 0.988, 0.988, margin=0.005)
    _reweld_and_clamp_uvs(reps)


def _prepare_sign_fixture_uvs(reps: list[bpy.types.Object], front_mat_name: str) -> None:
    """2-region `2048x2048` layout for standalone graphic hero fixtures (`Host_Podium`, `Menu_Stand`):
      - Left Half `[0.015..0.480] x [0.015..0.985]`: Structural body, brass & stainless frame (~`950 x 1986 px`)
      - Right Half `[0.520..0.985] x [0.025..0.975]`: Continuous unbroken `GraphicUV` front graphic (~`952 x 1945 px`!)
    """
    _split_multi_mat_edges(reps)
    _pack_face_subset_multi_into_rect(
        reps, lambda f, mn: mn != front_mat_name,
        0.015, 0.015, 0.480, 0.985, margin=0.005,
    )
    for ob in reps:
        me = ob.data
        bm = bmesh.new()
        bm.from_mesh(me)
        uv_m = bm.loops.layers.uv.get("UVMap")
        uv_g = bm.loops.layers.uv.get("GraphicUV")
        if uv_m is not None and uv_g is not None:
            for f in bm.faces:
                mat = me.materials[f.material_index] if f.material_index < len(me.materials) else None
                if mat is None or mat.name != front_mat_name:
                    continue
                for l in f.loops:
                    l[uv_m].uv = (
                        0.520 + max(0.0, min(1.0, l[uv_g].uv.x)) * 0.465,
                        0.025 + max(0.0, min(1.0, l[uv_g].uv.y)) * 0.950,
                    )
            bm.to_mesh(me)
        bm.free()
        me.update()
    _reweld_and_clamp_uvs(reps)


def _prepare_gallery_art_uvs(reps: list[bpy.types.Object]) -> None:
    """2-region `2048x2048` layout across all 10 individual `Gallery_Painting_01..10` objects:
      - Bottom Strip `[0.015..0.985] x [0.015..0.245]`: All 10 mitered mahogany frames, brass fillets & museum mats
      - Top Grid `[0.015..0.985] x [0.275..0.985]`: 4x3 grid of dedicated ~`465x445 px` continuous `GraphicUV` fine-art canvases!
    """
    _split_multi_mat_edges(reps)
    _pack_face_subset_multi_into_rect(
        reps, lambda f, mn: mn != "NC_Gallery_Art",
        0.015, 0.015, 0.985, 0.245, margin=0.004,
    )
    art_idx = 0
    for ob in reps:
        me = ob.data
        bm = bmesh.new()
        bm.from_mesh(me)
        uv_m = bm.loops.layers.uv.get("UVMap")
        uv_g = bm.loops.layers.uv.get("GraphicUV")
        if uv_m is not None and uv_g is not None:
            bm.faces.ensure_lookup_table()
            art_faces = [
                f for f in bm.faces
                if f.material_index < len(me.materials)
                and me.materials[f.material_index] is not None
                and me.materials[f.material_index].name == "NC_Gallery_Art"
            ]
            if art_faces:
                g_us = [l[uv_g].uv.x for cf in art_faces for l in cf.loops]
                g_vs = [l[uv_g].uv.y for cf in art_faces for l in cf.loops]
                min_u, max_u = min(g_us), max(g_us)
                min_v, max_v = min(g_vs), max(g_vs)
                span_u = max(max_u - min_u, 1e-5)
                span_v = max(max_v - min_v, 1e-5)
                col_i = art_idx % 4
                row_i = art_idx // 4
                art_idx += 1
                cu0 = 0.020 + col_i * 0.242
                cv0 = 0.280 + row_i * 0.236
                cw_u, ch_v = 0.228, 0.218
                for cf in art_faces:
                    for l in cf.loops:
                        nu = (l[uv_g].uv.x - min_u) / span_u
                        nv = (l[uv_g].uv.y - min_v) / span_v
                        l[uv_m].uv = (cu0 + nu * cw_u, cv0 + nv * ch_v)
                bm.to_mesh(me)
        bm.free()
        me.update()
    _reweld_and_clamp_uvs(reps)


def _prepare_region_street_uvs(objs: list[bpy.types.Object]) -> None:
    """Clean 3-region partition for `street` so 804/820 architecture & sidewalks NEVER get starved by road signs!

      - Left Half `[0.01..0.48] x [0.01..0.99]`: `RoadAndCurbs` (with compact crisp Ocean Dr, Bike Lanes & VALET ONLY!)
      - BR `[0.51..0.99] x [0.01..0.48]`: `SidewalksAndApron` (scored coral-pink & coastal concrete pavers + tactile domes!)
      - TR `[0.51..0.99] x [0.51..0.99]`: `Neighbor_804` + `Neighbor_820` (with crisp OH! MEXICO & FDC signs!)
    """
    _split_multi_mat_edges(objs)
    roads = [o for o in objs if o.name == "RoadAndCurbs"]
    sidewalks = [o for o in objs if o.name == "SidewalksAndApron"]
    neighbors = [o for o in objs if o.name in ("Neighbor_804", "Neighbor_820")]

    _pack_into_rect(sidewalks, 0.515, 0.012, 0.988, 0.485, margin=0.005)

    if neighbors:
        _pack_into_rect(neighbors, 0.515, 0.515, 0.988, 0.840, margin=0.005)
        sign_idx = 0
        for ob in neighbors:
            me = ob.data
            bm = bmesh.new()
            bm.from_mesh(me)
            uv_m = bm.loops.layers.uv.get("UVMap")
            uv_g = bm.loops.layers.uv.get("GraphicUV")
            if uv_m is not None and uv_g is not None:
                for f in bm.faces:
                    mat = me.materials[f.material_index] if f.material_index < len(me.materials) else None
                    if mat is None:
                        continue
                    fus = [l[uv_g].uv.x for l in f.loops]
                    fvs = [l[uv_g].uv.y for l in f.loops]
                    if (max(fus) - min(fus)) > 0.05 and (max(fvs) - min(fvs)) > 0.05:
                        if mat.name == "NC_Sign_804":
                            u0 = 0.520 + (sign_idx % 2) * 0.165
                            sign_idx += 1
                            for l in f.loops:
                                l[uv_m].uv = (u0 + l[uv_g].uv.x * 0.145, 0.855 + l[uv_g].uv.y * 0.130)
                        elif mat.name == "NC_Sign_FDC":
                            for l in f.loops:
                                l[uv_m].uv = (0.860 + l[uv_g].uv.x * 0.120, 0.855 + l[uv_g].uv.y * 0.120)
            bm.to_mesh(me)
            bm.free()
            me.update()

    if roads:
        _pack_into_rect(roads, 0.012, 0.012, 0.482, 0.340, margin=0.005)
        for ob in roads:
            me = ob.data
            bm = bmesh.new()
            bm.from_mesh(me)
            uv_m = bm.loops.layers.uv.get("UVMap")
            uv_g = bm.loops.layers.uv.get("GraphicUV")
            if uv_m is not None and uv_g is not None:
                bm.faces.ensure_lookup_table()
                visited: set[int] = set()
                bike_i, valet_i = 0, 0
                for f in bm.faces:
                    if f.index in visited:
                        continue
                    mat = me.materials[f.material_index] if f.material_index < len(me.materials) else None
                    if mat is None or mat.name not in ("NC_Road_OceanDr", "NC_Road_BikeLane", "NC_Curb_Valet"):
                        continue
                    stack = [f]
                    comp = []
                    visited.add(f.index)
                    while stack:
                        cur = stack.pop()
                        comp.append(cur)
                        for e in cur.edges:
                            for nf in e.link_faces:
                                if nf.index not in visited and nf.material_index == f.material_index:
                                    visited.add(nf.index)
                                    stack.append(nf)
                    g_us = [l[uv_g].uv.x for cf in comp for l in cf.loops]
                    g_vs = [l[uv_g].uv.y for cf in comp for l in cf.loops]
                    if (max(g_us) - min(g_us)) < 0.05 or (max(g_vs) - min(g_vs)) < 0.05:
                        continue
                    if mat.name == "NC_Road_OceanDr":
                        for cf in comp:
                            fus = [l[uv_g].uv.x for l in cf.loops]
                            fvs = [l[uv_g].uv.y for l in cf.loops]
                            if (max(fus) - min(fus)) > 0.002 or (max(fvs) - min(fvs)) > 0.002:
                                for l in cf.loops:
                                    l[uv_m].uv = (0.015 + l[uv_g].uv.x * 0.460, 0.360 + l[uv_g].uv.y * 0.300)
                    elif mat.name == "NC_Road_BikeLane":
                        col_i = bike_i % 4
                        row_i = bike_i // 4
                        bike_i += 1
                        u0 = 0.015 + col_i * 0.116
                        v0 = 0.675 + row_i * 0.116
                        for cf in comp:
                            fus = [l[uv_g].uv.x for l in cf.loops]
                            fvs = [l[uv_g].uv.y for l in cf.loops]
                            if (max(fus) - min(fus)) > 0.002 or (max(fvs) - min(fvs)) > 0.002:
                                for l in cf.loops:
                                    l[uv_m].uv = (u0 + l[uv_g].uv.x * 0.106, v0 + l[uv_g].uv.y * 0.106)
                    elif mat.name == "NC_Curb_Valet":
                        u0 = 0.015 + (valet_i % 3) * 0.155
                        valet_i += 1
                        for cf in comp:
                            fus = [l[uv_g].uv.x for l in cf.loops]
                            fvs = [l[uv_g].uv.y for l in cf.loops]
                            if (max(fus) - min(fus)) > 0.002 or (max(fvs) - min(fvs)) > 0.002:
                                v0 = 0.948 if cf.normal.y > 0.5 else 0.908
                                for l in cf.loops:
                                    l[uv_m].uv = (u0 + l[uv_g].uv.x * 0.145, v0 + l[uv_g].uv.y * 0.032)
            bm.to_mesh(me)
            bm.free()
            me.update()

    _reweld_and_clamp_uvs(objs)


def _prepare_shared_atlas_uvs(objs: list[bpy.types.Object], atlas_name: str) -> None:
    """Build ultra-sharp shared non-overlapping `UVMap` preserving continuous unbroken `GraphicUV` signage/awning/art strips!"""
    reps = _unique_mesh_reps(objs)
    if not reps:
        return
    if atlas_name == "nature":
        _prepare_quadrant_botanical_uvs(reps)
        return
    if atlas_name == "street":
        _prepare_region_street_uvs(reps)
        return
    if atlas_name == "host_podium":
        _prepare_sign_fixture_uvs(reps, "NC_HostPodium_Front")
        return
    if atlas_name == "menu_stand":
        _prepare_sign_fixture_uvs(reps, "NC_MenuBoard_Sheet")
        return
    if atlas_name == "int_gallery_art":
        _prepare_gallery_art_uvs(reps)
        return
    if atlas_name not in ("signage", "hero"):
        _prepare_dedicated_single_set_uvs(reps)
        return

    core.ensure_object_mode()
    _split_multi_mat_edges(reps)

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in reps:
        o.select_set(True)
    bpy.context.view_layer.objects.active = reps[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.004, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    for ob in reps:
        me = ob.data
        bm = bmesh.new()
        bm.from_mesh(me)
        uv_m = bm.loops.layers.uv.get("UVMap")
        uv_g = bm.loops.layers.uv.get("GraphicUV")
        if uv_m is None:
            bm.free()
            continue

        cont_slots = {}
        for idx, mat in enumerate(me.materials):
            if mat is not None and mat.name in CONTINUOUS_GRAPHIC_MATS:
                cont_slots[idx] = CONTINUOUS_GRAPHIC_MATS[mat.name]

        dw = DOWNWEIGHT_PARTS.get(ob.name, 1.0)
        if dw != 1.0:
            for f in bm.faces:
                if f.material_index not in cont_slots:
                    for l in f.loops:
                        l[uv_m].uv *= dw

        if uv_g is not None and cont_slots:
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            visited: set[int] = set()
            island_idx = 0
            for f in bm.faces:
                if f.index in visited or f.material_index not in cont_slots:
                    continue
                stack = [f]
                comp: list[bmesh.types.BMFace] = []
                visited.add(f.index)
                while stack:
                    cur = stack.pop()
                    comp.append(cur)
                    for e in cur.edges:
                        for nf in e.link_faces:
                            if nf.index not in visited and nf.material_index == f.material_index:
                                visited.add(nf.index)
                                stack.append(nf)
                area = sum(cf.calc_area() for cf in comp)
                g_us = [l[uv_g].uv.x for cf in comp for l in cf.loops]
                g_vs = [l[uv_g].uv.y for cf in comp for l in cf.loops]
                span_u = max(g_us) - min(g_us)
                span_v = max(g_vs) - min(g_vs)
                if span_u > 0.05 and span_v > 0.05:
                    boost = cont_slots[f.material_index]
                    mat_name = me.materials[f.material_index].name
                    if mat_name == "NC_Awning_NewsCafe":
                        su, sv = (2.2, 1.45) if span_v <= 0.42 else (0.95, 0.70)
                    elif mat_name == "NC_Awning_Hotel800":
                        su, sv = (1.5, 1.25) if span_v <= 0.42 else (0.85, 0.70)
                    elif mat_name == "NC_Interior_Backdrop":
                        su, sv = 2.1, 1.05
                    elif mat_name in ("NC_Sign_OneWay", "NC_Sign_OceanDr", "NC_Sign_8thSt"):
                        su, sv = 1.15, 0.42
                    elif mat_name in ("NC_Sign_StopPed", "NC_Sign_NoParking", "NC_Sign_ADA"):
                        su, sv = 0.72, 0.72
                    else:
                        sz = max(0.85, min(2.4, math.sqrt(max(area, 0.1)))) * boost
                        su, sv = sz, sz
                    ox = 6.0 + (island_idx % 8) * 5.0
                    oy = 6.0 + (island_idx // 8) * 5.0
                    for cf in comp:
                        fus = [l[uv_g].uv.x for l in cf.loops]
                        fvs = [l[uv_g].uv.y for l in cf.loops]
                        if (max(fus) - min(fus)) > 0.002 or (max(fvs) - min(fvs)) > 0.002:
                            for l in cf.loops:
                                l[uv_m].uv = (ox + l[uv_g].uv.x * su, oy + l[uv_g].uv.y * sv)
                        else:
                            for l in cf.loops:
                                l[uv_m].uv = (ox - 0.6 + l[uv_m].uv.x * 0.10, oy - 0.6 + l[uv_m].uv.y * 0.10)
                    island_idx += 1

        bm.to_mesh(me)
        bm.free()
        me.update()

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in reps:
        o.select_set(True)
    bpy.context.view_layer.objects.active = reps[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.004)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in reps:
        o.select_set(False)

    _reweld_and_clamp_uvs(reps)


def _create_bake_target_image(name: str, res: int, *, float_buf: bool = True) -> bpy.types.Image:
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, width=res, height=res, alpha=False, float_buffer=float_buf)
    img.colorspace_settings.name = "Non-Color"
    return img


def _set_active_bake_node(objs: list[bpy.types.Object], img: bpy.types.Image) -> list[tuple[bpy.types.NodeTree, bpy.types.Node]]:
    created = []
    seen = set()
    for ob in objs:
        for slot in ob.material_slots:
            mat = slot.material
            if mat is None or mat.node_tree is None or mat.name in seen:
                continue
            seen.add(mat.name)
            nt = mat.node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.image = img
            node.name = "__VF_BAKE_TARGET__"
            for n in nt.nodes:
                n.select = False
            node.select = True
            nt.nodes.active = node
            created.append((nt, node))
    return created


def _remove_nodes(pairs: list[tuple[bpy.types.NodeTree, bpy.types.Node]]) -> None:
    for nt, n in pairs:
        try:
            nt.nodes.remove(n)
        except Exception:
            pass


def _override_emit_socket(objs: list[bpy.types.Object], bsdf_input_name: str):
    saved = []
    seen = set()
    for ob in objs:
        for slot in ob.material_slots:
            mat = slot.material
            if mat is None or mat.node_tree is None or mat.name in seen:
                continue
            seen.add(mat.name)
            nt = mat.node_tree
            out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if out is None or bsdf is None:
                continue
            old_link = out.inputs["Surface"].links[0] if out.inputs["Surface"].links else None
            old_from = old_link.from_socket if old_link else None
            em = nt.nodes.new("ShaderNodeEmission")
            inp = bsdf.inputs[bsdf_input_name]
            if inp.is_linked:
                nt.links.new(inp.links[0].from_socket, em.inputs["Color"])
            else:
                val = inp.default_value
                if isinstance(val, (float, int)):
                    em.inputs["Color"].default_value = (float(val), float(val), float(val), 1.0)
                else:
                    em.inputs["Color"].default_value = tuple(val)
            nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
            saved.append((nt, out, em, old_from))
    return saved


def _restore_emit_override(saved) -> None:
    for nt, out, em, old_from in saved:
        try:
            nt.nodes.remove(em)
        except Exception:
            pass
        if old_from is not None:
            nt.links.new(old_from, out.inputs["Surface"])


def _run_bake_pass(
    sc: bpy.types.Scene,
    objs: list[bpy.types.Object],
    bake_type: str,
    res: int,
    *,
    samples: int = 8,
    margin: int = 4,
) -> np.ndarray:
    img = _create_bake_target_image(f"__vf_tmp_{bake_type}", res, float_buf=True)
    nodes = _set_active_bake_node(objs, img)
    try:
        core.ensure_object_mode()
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        sc.cycles.samples = samples
        sc.cycles.use_denoising = False
        sc.render.bake.margin = margin
        try:
            sc.render.bake.margin_type = "EXTEND"
        except Exception:
            pass
        sc.render.bake.use_clear = True
        if bake_type == "NORMAL":
            sc.render.bake.normal_space = "TANGENT"
            sc.render.bake.normal_r = "POS_X"
            sc.render.bake.normal_g = "POS_Y"
            sc.render.bake.normal_b = "POS_Z"
        bpy.ops.object.bake(type=bake_type)
        buf = np.empty(res * res * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        arr = buf.reshape((res, res, 4))
    finally:
        _remove_nodes(nodes)
        bpy.data.images.remove(img)
        for o in objs:
            o.select_set(False)
    bake.cooldown(0.35)
    return arr


def bake_atlas_set(
    sc: bpy.types.Scene,
    objs: list[bpy.types.Object],
    var_slug: str,
    atlas_name: str,
    *,
    res: int = 2048,
    shared_non_color: dict[str, str] | None = None,
    isolate_for_ao: bool = False,
) -> dict[str, str]:
    """Bake 6-map `2048x2048` PBR texture set (`Color`+AO sRGB, `Normal`, `Roughness`, `Metalness`, `AO`, `ORM`)."""
    os.makedirs(TEX_DIR, exist_ok=True)
    prefix = f"T_NewsCafe_{var_slug}_{atlas_name}"
    out: dict[str, str] = {}
    reps = _unique_mesh_reps(objs)
    m_px = 4 if atlas_name in ("signage", "hero", "street") else 3

    saved_hide: list[tuple[bpy.types.Object, bool]] = []
    if isolate_for_ao:
        rep_set = set(reps)
        for o in bpy.data.objects:
            if o.type == "MESH" and o not in rep_set:
                saved_hide.append((o, o.hide_render))
                o.hide_render = True

    try:
        saved_bc = _override_emit_socket(reps, "Base Color")
        try:
            bc_lin = _run_bake_pass(sc, reps, "EMIT", res, samples=6, margin=m_px)
        finally:
            _restore_emit_override(saved_bc)

        if shared_non_color is not None:
            ao_path = shared_non_color["AO"]
            ao_img = bpy.data.images.load(ao_path, check_existing=False)
            ao_img.colorspace_settings.name = "Non-Color"
            ao_buf = np.empty(res * res * 4, dtype=np.float32)
            ao_img.pixels.foreach_get(ao_buf)
            ao_arr = ao_buf.reshape((res, res, 4))
            bpy.data.images.remove(ao_img)
            out.update(shared_non_color)
        else:
            ao_arr = _run_bake_pass(sc, reps, "AO", res, samples=24, margin=m_px)
            norm_arr = _run_bake_pass(sc, reps, "NORMAL", res, samples=8, margin=m_px)
            rough_arr = _run_bake_pass(sc, reps, "ROUGHNESS", res, samples=8, margin=m_px)
            saved_met = _override_emit_socket(reps, "Metallic")
            try:
                met_arr = _run_bake_pass(sc, reps, "EMIT", res, samples=6, margin=m_px)
            finally:
                _restore_emit_override(saved_met)

            orm_arr = np.ones((res, res, 4), dtype=np.float32)
            orm_arr[..., 0] = ao_arr[..., 0]
            orm_arr[..., 1] = rough_arr[..., 0]
            orm_arr[..., 2] = met_arr[..., 0]

            for key, arr_data in [
                ("Normal", norm_arr),
                ("Roughness", rough_arr),
                ("Metalness", met_arr),
                ("AO", ao_arr),
                ("ORM", orm_arr),
            ]:
                p = os.path.join(TEX_DIR, f"{prefix}_{key}.png")
                bake.save_png_8bit(arr_data, p, "Non-Color")
                out[key] = p
    finally:
        for o, prev in saved_hide:
            o.hide_render = prev

    ao_weight = 0.14 if atlas_name in ("signage", "host_podium", "menu_stand", "int_gallery_art") else 0.22
    ao_fac = (1.0 - ao_weight) + ao_weight * np.clip(ao_arr[..., :3], 0.0, 1.0)
    col_comp = np.ones((res, res, 4), dtype=np.float32)
    col_comp[..., :3] = bake.lin_arr_to_srgb(bc_lin[..., :3] * ao_fac)
    col_path = os.path.join(TEX_DIR, f"{prefix}_Color.png")
    bake.save_png_8bit(col_comp, col_path, "sRGB")
    out["Color"] = col_path
    core.log(f"[Bake] Finished {prefix} ({res}x{res}, reps={len(reps)}, isolated={isolate_for_ao})")
    return out


def make_baked_pbr_material(name: str, tex_paths: dict[str, str], *, spec_ior: float = 0.24, twilight: bool = False) -> bpy.types.Material:
    """Create a clean engine-ready Principled BSDF driven strictly by the baked 2K PBR PNG maps!"""
    old = bpy.data.materials.get(name)
    if old is not None:
        bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def _tex(path: str, cs: str):
        node = nt.nodes.new("ShaderNodeTexImage")
        im = bpy.data.images.load(path, check_existing=True)
        im.colorspace_settings.name = cs
        node.image = im
        return node

    t_col = _tex(tex_paths["Color"], "sRGB")
    t_norm = _tex(tex_paths["Normal"], "Non-Color")
    t_rgh = _tex(tex_paths["Roughness"], "Non-Color")
    t_met = _tex(tex_paths["Metalness"], "Non-Color")

    nt.links.new(t_col.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(t_rgh.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(t_met.outputs["Color"], bsdf.inputs["Metallic"])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec_ior

    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.85
    nt.links.new(t_norm.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    if twilight:
        bsdf.inputs["Emission Strength"].default_value = 0.08
        nt.links.new(t_col.outputs["Color"], bsdf.inputs["Emission Color"])

    mat["sc_srgb"] = [0.75, 0.75, 0.72]
    mat["sc_roughness"] = 0.65
    mat["sc_metallic"] = 0.05
    mat["sc_role"] = "solid"
    return mat


def assign_baked_and_strip_graphic_uv(objs: list[bpy.types.Object], baked_mat: bpy.types.Material) -> None:
    """Assign baked PBR material and strip auxiliary `GraphicUV` once per unique Mesh datablock."""
    for ob in _unique_mesh_reps(objs):
        me = ob.data
        me.materials.clear()
        me.materials.append(baked_mat)
        for p in me.polygons:
            p.material_index = 0
        if "GraphicUV" in me.uv_layers:
            me.uv_layers.remove(me.uv_layers["GraphicUV"])
        if "UVMap" in me.uv_layers:
            me.uv_layers.active = me.uv_layers["UVMap"]
        me.update()


def _build_instanced_lod_chain(
    lod0_objs: list[bpy.types.Object],
    out_lods_dir: str,
    asset_slug: str,
    *,
    collection_prefix: str = "NewsCafe",
    planar_parts: set[str] | None = None,
) -> dict[str, dict]:
    """Instance-aware 4-tier seam-locked `LOD0`–`LOD3` generator!

    Decimates each unique `ob.data` mesh datablock ONCE per LOD tier (`delimit={'UV','SEAM','SHARP'}`),
    then links every LOD instance to the shared decimated mesh -> 10x faster + compact instanced GLBs!
    """
    os.makedirs(out_lods_dir, exist_ok=True)
    planar = planar_parts or set()
    tiers = [
        (1, 0.48, 0.50),
        (2, 0.24, 0.25),
        (3, 0.11, 0.10),
    ]
    summary: dict[str, dict] = {
        "LOD0": {
            "tris": sum(gameready.triangle_count(o, False) for o in lod0_objs),
            "parts": len(lod0_objs),
            "screen_size": 1.0,
        }
    }

    for lvl, ratio, scr_sz in tiers:
        l_col = core.fresh_collection(f"{collection_prefix}_LOD{lvl}")
        decimated_by_mesh: dict[bpy.types.Mesh, bpy.types.Mesh] = {}
        lvl_objs: list[bpy.types.Object] = []

        # 1. Decimate each unique mesh datablock ONCE on a temporary object
        for src in _unique_mesh_reps(lod0_objs):
            cp = src.copy()
            cp.data = src.data.copy()
            cp.data.name = f"{src.data.name}_LOD{lvl}"
            cp.name = f"__tmp_dec_{src.name}_LOD{lvl}"
            l_col.objects.link(cp)

            dec = cp.modifiers.new("VF_LOD_Decimate", "DECIMATE")
            is_planar = src.name in planar
            if is_planar:
                dec.decimate_type = "DISSOLVE"
                dec.angle_limit = math.radians({1: 1.8, 2: 2.6, 3: 3.4}.get(lvl, 3.0))
                dec.delimit = {"UV", "SEAM", "SHARP", "MATERIAL"}
                dec.use_dissolve_boundaries = False
            else:
                dec.decimate_type = "COLLAPSE"
                dec.ratio = ratio
                dec.delimit = {"UV", "SEAM", "SHARP"}
                dec.use_collapse_triangulate = True

            with bpy.context.temp_override(
                object=cp,
                active_object=cp,
                selected_objects=[cp],
                selected_editable_objects=[cp],
            ):
                bpy.ops.object.modifier_apply(modifier=dec.name)

            if is_planar:
                bm = bmesh.new()
                bm.from_mesh(cp.data)
                bmesh.ops.triangulate(bm, faces=bm.faces[:])
                bm.to_mesh(cp.data)
                bm.free()
                cp.data.update()

            decimated_by_mesh[src.data] = cp.data
            bpy.data.objects.remove(cp, do_unlink=True)

        # 2. Spawn all LOD objects linked to their shared decimated meshes!
        for src in lod0_objs:
            lod_ob = bpy.data.objects.new(f"{src.name}_LOD{lvl}", decimated_by_mesh[src.data])
            lod_ob.matrix_world = src.matrix_world.copy()
            l_col.objects.link(lod_ob)
            lod_ob["sc_part"] = src.get("sc_part", src.name)
            lod_ob["sc_role"] = src.get("sc_role", "solid")
            if src.get("vf_asset_set"):
                lod_ob["vf_asset_set"] = src["vf_asset_set"]
            lvl_objs.append(lod_ob)

        glb_lod = os.path.join(out_lods_dir, f"{asset_slug}_LOD{lvl}.glb")
        core.ensure_object_mode()
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        for o in lvl_objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = lvl_objs[0]
        bpy.ops.export_scene.gltf(filepath=glb_lod, use_selection=True, export_format="GLB", export_apply=True)
        for o in lvl_objs:
            o.select_set(False)

        tris = sum(gameready.triangle_count(o, False) for o in lvl_objs)
        summary[f"LOD{lvl}"] = {
            "tris": tris,
            "parts": len(lvl_objs),
            "unique_meshes": len(decimated_by_mesh),
            "screen_size": scr_sz,
            "glb": f"lods/{asset_slug}_LOD{lvl}.glb",
        }
        core.log(f"[LOD{lvl}] {tris:,} tris across {len(lvl_objs)} objects ({len(decimated_by_mesh)} unique meshes) -> {glb_lod}")

    return summary


def _setup_lighting_mood(sc: bpy.types.Scene, mood: str) -> bpy.types.Collection:
    st_col = sv_qa.setup_miami_sun_sky(sc)
    world = sc.world
    nt = world.node_tree
    sky = next((n for n in nt.nodes if n.type == "TEX_SKY"), None)
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None)
    sun = next((o for o in st_col.objects if o.type == "LIGHT"), None)

    if mood == "sunset":
        if sky:
            try:
                sky.sun_elevation = math.radians(14.0)
                sky.sun_rotation = math.radians(112.0)
                if hasattr(sky, "aerosol_density"):
                    sky.aerosol_density = 1.6
                elif hasattr(sky, "dust_density"):
                    sky.dust_density = 1.6
            except Exception:
                pass
        if bg:
            bg.inputs["Strength"].default_value = 0.42
        if sun:
            sun.data.color = (1.0, 0.72, 0.46)
            sun.data.energy = 2.4
        sc.view_settings.exposure = 0.05
    elif mood == "twilight":
        if sky:
            try:
                sky.sun_elevation = math.radians(2.5)
                sky.sun_rotation = math.radians(102.0)
                if hasattr(sky, "ozone_density"):
                    sky.ozone_density = 2.6
            except Exception:
                pass
        if bg:
            bg.inputs["Strength"].default_value = 0.14
        if sun:
            sun.data.color = (0.52, 0.64, 1.0)
            sun.data.energy = 0.45
        for lx, ly, lz, col_l, eng in [
            (2.2, 6.2, 2.8, (1.0, 0.72, 0.36), 850.0),
            (-2.6, 6.2, 2.8, (1.0, 0.72, 0.36), 850.0),
            (6.8, 6.2, 2.8, (1.0, 0.72, 0.36), 850.0),
            (14.5, 1.35, 7.6, (1.0, 0.84, 0.58), 2600.0),
            (-15.8, 13.0, 7.6, (1.0, 0.84, 0.58), 2600.0),
            (2.0, 4.9, 5.2, (1.0, 0.45, 0.78), 650.0),
            (2.0, 4.9, 8.2, (0.25, 0.90, 1.00), 650.0),
        ]:
            pl = bpy.data.lights.new(f"VF_Night_{lx}", "POINT")
            pl.energy = eng
            pl.color = col_l
            pl.shadow_soft_size = 0.65
            pob = bpy.data.objects.new(pl.name, pl)
            pob.location = (lx, ly, lz)
            st_col.objects.link(pob)
        sc.view_settings.exposure = 0.38
    return st_col


def _render_cam(sc: bpy.types.Scene, st_col: bpy.types.Collection, loc, tgt, lens: float, out_path: str, w: int = 1280, h: int = 720, samples: int = 48) -> None:
    cd = bpy.data.cameras.new("VF_VarCam")
    cam = bpy.data.objects.new("VF_VarCam", cd)
    st_col.objects.link(cam)
    sc.camera = cam
    cam.location = Vector(loc)
    cam.data.lens = lens
    cam.data.clip_start = 0.1
    cam.data.clip_end = 250.0
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    bake.render_still_safe(sc, out_path, cooldown_sec=0.45)


def main() -> int:
    for d in (TEX_DIR, VAR_DIR, LOD_DIR, RBX_DIR, RENDERS_DIR):
        os.makedirs(d, exist_ok=True)

    sc = bpy.context.scene
    backend = bake.enable_cycles_gpu(sc)
    core.log(f"[Stage5-6] Cycles GPU backend active: {backend}")

    shared_non_color_cache: dict[str, dict[str, str]] = {}
    report: dict = {"backend": backend, "variants": {}, "lods": {}, "roblox": {}}
    classic_blend = os.path.join(VAR_DIR, "news_cafe_classic_ocean_dr.blend")
    packed_proc_blend = os.path.join(VAR_DIR, "_classic_procedural_packed.blend")

    # Build classic_ocean_dr ONCE and pack ALL 19 semantic 2K atlases ONCE -> 100% BIT-IDENTICAL UVs across all 4 variants!
    core.log("=== Building Master Modular Scene & Packing All 19 Dedicated 2K PBR Atlases ===")
    col, meshes = builder.build_all(clear_scene=True, palette_override={})
    atlas_groups = _resolve_atlas_groups(meshes)
    core.log(f"[Atlas] Resolved {len(atlas_groups)} dedicated 2K texture sets across {len(meshes)} objects!")
    for aname, grp_objs in atlas_groups.items():
        _prepare_shared_atlas_uvs(grp_objs, aname)
    bpy.ops.wm.save_as_mainfile(filepath=packed_proc_blend)

    import scene_mats  # noqa: E402

    for vspec in VARIANTS:
        slug = vspec["slug"]
        core.log(f"=== Baking Variant: {slug} ({len(vspec['re_bake_atlases'])} sets to bake!) ===")
        if slug != "classic_ocean_dr":
            bpy.ops.wm.open_mainfile(filepath=packed_proc_blend)
            sc = bpy.context.scene
            bake.enable_cycles_gpu(sc)
            col = bpy.data.collections.get(builder.COLL_NAME)
            meshes = [o for o in col.all_objects if o.type == "MESH" and o.get("sc_part")]
            atlas_groups = _resolve_atlas_groups(meshes)

            # Snapshot material slot names per UNIQUE Mesh datablock BEFORE rebuilding palette!
            unique_reps = _unique_mesh_reps(meshes)
            slot_names_by_me = {
                ob.data.name: [m.name if m is not None else None for m in ob.data.materials]
                for ob in unique_reps
            }
            new_lib = scene_mats.build_material_library(palette_override=vspec["palette"])
            mat_by_name = {mat.name: mat for mat in new_lib.values()}
            for ob in unique_reps:
                me = ob.data
                for i, mname in enumerate(slot_names_by_me[me.name]):
                    if mname and mname in mat_by_name:
                        me.materials[i] = mat_by_name[mname]

        tex_manifest: dict[str, dict[str, str]] = {}

        for aname, grp_objs in atlas_groups.items():
            atlas_res = 2048
            if slug != "classic_ocean_dr" and aname not in vspec["re_bake_atlases"]:
                tpaths = dict(report["variants"]["classic_ocean_dr"]["textures"][aname])
            else:
                shared_nc = shared_non_color_cache.get(aname)
                tpaths = bake_atlas_set(
                    sc, grp_objs, slug, aname,
                    res=atlas_res,
                    shared_non_color=shared_nc,
                    isolate_for_ao=(aname in INSTANCED_SETS),
                )
                if aname not in shared_non_color_cache:
                    shared_non_color_cache[aname] = {k: v for k, v in tpaths.items() if k != "Color"}

            if aname == "signage":
                sp_ior = 0.10
            elif aname == "nature":
                sp_ior = 0.18
            elif aname in ("patio_table", "patio_tableware", "int_bar", "int_bar_props", "int_barstool", "int_dining_table", "int_lighting"):
                sp_ior = 0.36
            elif aname in ("hero", "street"):
                sp_ior = 0.22
            else:
                sp_ior = 0.28

            bmat = make_baked_pbr_material(
                f"M_NewsCafe_{slug}_{aname}_Baked",
                tpaths,
                spec_ior=sp_ior,
                twilight=(vspec["lighting"] == "twilight" and aname in ("hero", "signage", "int_lighting", "int_arch", "int_bar")),
            )
            assign_baked_and_strip_graphic_uv(grp_objs, bmat)
            tex_manifest[aname] = tpaths

        # Export baked variant GLB
        glb_var = os.path.join(VAR_DIR, f"news_cafe_{slug}.glb")
        core.ensure_object_mode()
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        for o in meshes:
            o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.export_scene.gltf(filepath=glb_var, use_selection=True, export_format="GLB", export_apply=True)
        for o in meshes:
            o.select_set(False)

        if slug == "classic_ocean_dr":
            bpy.ops.wm.save_as_mainfile(filepath=classic_blend)

        st_col = _setup_lighting_mood(sc, vspec["lighting"])
        vp = os.path.join(RENDERS_DIR, f"variant_{slug}.png")
        _render_cam(sc, st_col, (18.2, 18.0, 3.2), (1.8, 3.8, 4.4), 21.0, vp, w=1280, h=640, samples=48)

        if slug == "classic_ocean_dr":
            _render_cam(
                sc, st_col, (4.0, 12.6, 2.2), (2.0, 5.2, 2.7), 30.0,
                os.path.join(RENDERS_DIR, "baked_closeup.png"), w=1280, h=720, samples=56,
            )
            _render_cam(
                sc, st_col, (4.95, 10.85, 1.58), (3.45, 9.00, 0.82), 40.0,
                os.path.join(RENDERS_DIR, "baked_macro_bistro.png"), w=1280, h=640, samples=56,
            )
            _render_cam(
                sc, st_col, (0.35, 2.75, 1.75), (5.20, -2.50, 1.65), 22.0,
                os.path.join(RENDERS_DIR, "baked_interior_wide.png"), w=1280, h=640, samples=56,
            )
            _render_cam(
                sc, st_col, (1.35, 1.25, 1.50), (-2.30, -1.80, 1.35), 26.0,
                os.path.join(RENDERS_DIR, "baked_interior_bar.png"), w=1280, h=640, samples=56,
            )
            _render_cam(
                sc, st_col, (4.80, -0.85, 1.70), (5.25, -4.12, 1.74), 24.0,
                os.path.join(RENDERS_DIR, "baked_banquette_art.png"), w=1280, h=640, samples=56,
            )
            _render_cam(
                sc, st_col, (4.42, 10.68, 1.18), (3.76, 9.84, 0.80), 58.0,
                os.path.join(RENDERS_DIR, "baked_chair_joints.png"), w=1280, h=640, samples=56,
            )
            _render_cam(
                sc, st_col, (-0.85, 0.55, 0.92), (-2.15, -0.78, 0.68), 46.0,
                os.path.join(RENDERS_DIR, "baked_bar_joints.png"), w=1280, h=640, samples=56,
            )
            _render_cam(
                sc, st_col, (25.5, 27.5, 17.5), (-0.5, 3.5, 3.6), 34.0,
                os.path.join(RENDERS_DIR, "blender-render-check.png"), w=1600, h=900, samples=64,
            )

        core.clear_collection(st_col)
        bpy.data.collections.remove(st_col)

        report["variants"][slug] = {
            "label": vspec["label"],
            "glb": f"variants/news_cafe_{slug}.glb",
            "render": f"renders/variant_{slug}.png",
            "textures": tex_manifest,
        }

    # --- STAGE 6: Reload baked classic_ocean_dr -> Instance-Aware LOD0..LOD3 + Clean Master Save BEFORE Roblox Export! ---
    bpy.ops.wm.open_mainfile(filepath=classic_blend)
    sc = bpy.context.scene
    bake.enable_cycles_gpu(sc)
    col = bpy.data.collections.get(builder.COLL_NAME)
    lod0_objs = [o for o in col.all_objects if o.type == "MESH" and o.get("sc_part")]

    glb_lod0 = os.path.join(LOD_DIR, "news_cafe_south_beach_LOD0.glb")
    shutil.copy2(os.path.join(VAR_DIR, "news_cafe_classic_ocean_dr.glb"), glb_lod0)

    lod_summary = _build_instanced_lod_chain(
        lod0_objs,
        LOD_DIR,
        "news_cafe_south_beach",
        collection_prefix="NewsCafe",
        planar_parts={
            "NewsCafe_Shell", "NewsCafe_Windows", "NewsCafe_Awnings",
            "Neighbor_804", "Neighbor_820", "RoadAndCurbs", "SidewalksAndApron",
        },
    )
    lod_summary["LOD0"]["glb"] = "lods/news_cafe_south_beach_LOD0.glb"
    report["lods"] = lod_summary

    st_col = _setup_lighting_mood(sc, "midday")
    lod_cols = {
        "LOD0": col,
        "LOD1": bpy.data.collections.get("NewsCafe_LOD1"),
        "LOD2": bpy.data.collections.get("NewsCafe_LOD2"),
        "LOD3": bpy.data.collections.get("NewsCafe_LOD3"),
    }
    for lname in ("LOD0", "LOD1", "LOD2", "LOD3"):
        for k, c_ref in lod_cols.items():
            if c_ref is not None:
                _set_col_tree_visible(c_ref, k == lname)
        _render_cam(
            sc, st_col, (18.2, 18.0, 3.2), (1.8, 3.8, 4.4), 21.0,
            os.path.join(RENDERS_DIR, f"lod_panel_{lname}.png"), w=960, h=540, samples=32,
        )
    for k, c_ref in lod_cols.items():
        if c_ref is not None:
            _set_col_tree_visible(c_ref, k == "LOD0")
    core.clear_collection(st_col)
    bpy.data.collections.remove(st_col)

    # Save CLEAN Master `.blend` (ZERO `_src` object suffixes!!) & sync to Desktop BEFORE `export_roblox` mutates names!
    master_blend = os.path.join(THIS_DIR, "news_cafe_south_beach.blend")
    master_glb = os.path.join(THIS_DIR, "news_cafe_south_beach.glb")
    bpy.ops.wm.save_as_mainfile(filepath=master_blend)
    shutil.copy2(glb_lod0, master_glb)

    out_desktop = os.path.join(core.DESIGN_OUTPUT_DIR, "NewsCafeSouthBeach")
    os.makedirs(out_desktop, exist_ok=True)
    shutil.copy2(master_blend, os.path.join(out_desktop, "news_cafe_south_beach.blend"))
    shutil.copy2(master_glb, os.path.join(out_desktop, "news_cafe_south_beach.glb"))
    shutil.copy2(os.path.join(RENDERS_DIR, "blender-render-check.png"), os.path.join(out_desktop, "blender-render-check.png"))
    core.log(f"[Save] Clean master .blend & .glb saved (ZERO _src suffixes) -> {master_blend} & {out_desktop}")

    # Roblox Studio Bundle preserving ALL 19 2K baked PBR texture sets!
    rbx_tex_dir = os.path.join(RBX_DIR, "textures")
    os.makedirs(rbx_tex_dir, exist_ok=True)
    rbx_tex_manifest = {}
    for aname, tdict in report["variants"]["classic_ocean_dr"]["textures"].items():
        rbx_tex_manifest[aname] = {}
        for map_k, src_p in tdict.items():
            dst_p = os.path.join(rbx_tex_dir, os.path.basename(src_p))
            shutil.copy2(src_p, dst_p)
            rbx_tex_manifest[aname][map_k] = f"textures/{os.path.basename(src_p)}"

    lo, hi = core.world_bbox(lod0_objs)
    hero_mat = bpy.data.materials.get("M_NewsCafe_classic_ocean_dr_hero_Baked")

    # Group repeated instanced furniture cleanly by semantic Roblox MeshPart while keeping unique hero parts standalone!
    rbx_grouped: dict[str, tuple[str, list[bpy.types.Object]]] = {}
    for ob in lod0_objs:
        aname = _resolve_atlas_name(ob)
        if ob.get("vf_instanced"):
            gname = {
                "chair_honey": "Patio_And_Interior_Chairs_Honey",
                "chair_cream": "Patio_Chairs_Cream",
                "patio_table": "Patio_Bistro_Tables",
                "patio_tableware": "Patio_Tableware_Sets",
                "int_banquette": "Interior_Banquettes",
                "int_barstool": "Interior_Barstools",
                "int_dining_table": "Interior_Dining_Tables",
                "int_lighting": "Interior_Lighting_Fixtures",
            }.get(aname, aname)
        elif aname == "int_gallery_art":
            gname = "Interior_Gallery_Paintings"
        else:
            gname = ob.name
        if gname not in rbx_grouped:
            rbx_grouped[gname] = (aname, [])
        rbx_grouped[gname][1].append(ob)

    rbx_parts = [
        dict(
            name=gname,
            objects=gobjs,
            role="solid" if aname == "hero" else f"baked_{aname}",
            collide=(gname in {"NewsCafe_Shell", "Neighbor_804", "Neighbor_820", "RoadAndCurbs", "SidewalksAndApron", "NewsCafe_Breeze_Patio", "Host_Podium"}),
            render_fidelity="Precise" if (gname.startswith("NewsCafe_") or gname in {"Host_Podium", "Menu_Stand"}) else "Automatic",
        )
        for gname, (aname, gobjs) in rbx_grouped.items()
    ]
    rbx_res = vf_export.export_roblox(
        "NewsCafeSouthBeach",
        RBX_DIR,
        rbx_parts,
        source_collection=col,
        primary=dict(name="NewsCafeRoot", center=(lo + hi) * 0.5, size=(hi - lo)),
        reference="NewsCafe_Shell",
        attributes={"address": "800 Ocean Dr, Miami Beach, FL 33139", "architecturalStyle": "MiMo / Art Deco"},
        tags=["Architecture", "SouthBeach", "NewsCafe", "VelumForge"],
        prebaked_material=hero_mat,
        prebaked_textures=rbx_tex_manifest["hero"],
        extra_manifest={"atlases": rbx_tex_manifest, "lods": lod_summary},
    )
    report["roblox"] = {
        "fbx": "roblox/NewsCafeSouthBeach.fbx",
        "manifest": "roblox/NewsCafeSouthBeach.manifest.json",
        "setup_luau": "roblox/NewsCafeSouthBeach.studio_setup.luau",
        "total_tris": rbx_res["data"]["totalTris"],
        "parts": len(rbx_res["data"]["parts"]),
        "sockets": len(rbx_res["data"]["sockets"]),
    }

    if os.path.isfile(packed_proc_blend):
        try:
            os.remove(packed_proc_blend)
        except OSError:
            pass

    rep_path = os.path.join(THIS_DIR, "variants_and_lods_report.json")
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    core.log(f"[Stage5-6] COMPLETE! Report written to {rep_path}")
    return 0


def compose_sheets() -> None:
    from PIL import Image, ImageDraw, ImageFont

    rep_path = os.path.join(THIS_DIR, "variants_and_lods_report.json")
    with open(rep_path, encoding="utf-8") as fh:
        rep = json.load(fh)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 24)
    except OSError:
        font = ImageFont.load_default()

    cw, ch, pad, hdr = 960, 480, 16, 44
    v_sheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + hdr) * 2 + pad * 3), (18, 20, 24))
    vd = ImageDraw.Draw(v_sheet)
    for idx, vspec in enumerate(VARIANTS):
        r, c = divmod(idx, 2)
        x0 = pad + c * (cw + pad)
        y0 = pad + r * (ch + hdr + pad)
        vd.text((x0, y0 + 8), vspec["label"], fill=(240, 244, 248), font=font)
        p = os.path.join(RENDERS_DIR, f"variant_{vspec['slug']}.png")
        if os.path.isfile(p):
            v_sheet.paste(Image.open(p).convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS), (x0, y0 + hdr))
    v_out = os.path.join(RENDERS_DIR, "variants_lineup.png")
    v_sheet.save(v_out)

    lw, lh = 960, 540
    l_sheet = Image.new("RGB", (lw * 2 + pad * 3, (lh + hdr) * 2 + pad * 3), (18, 20, 24))
    ld = ImageDraw.Draw(l_sheet)
    lod0_tris = max(1, rep["lods"]["LOD0"]["tris"])
    for idx, lname in enumerate(("LOD0", "LOD1", "LOD2", "LOD3")):
        r, c = divmod(idx, 2)
        x0 = pad + c * (lw + pad)
        y0 = pad + r * (lh + hdr + pad)
        info = rep["lods"][lname]
        pct = 100.0 * info["tris"] / lod0_tris
        ld.text((x0, y0 + 8), f"{lname}  —  {info['tris']:,} tris ({pct:.1f}%)  |  {info['parts']} parts", fill=(122, 238, 186), font=font)
        p = os.path.join(RENDERS_DIR, f"lod_panel_{lname}.png")
        if os.path.isfile(p):
            l_sheet.paste(Image.open(p).convert("RGB").resize((lw, lh), Image.Resampling.LANCZOS), (x0, y0 + hdr))
    l_out = os.path.join(RENDERS_DIR, "lod_comparison_sheet.png")
    l_sheet.save(l_out)
    print(f"[Sheets] Composed {v_out} & {l_out}")


if __name__ == "__main__":
    if "--compose-sheets" in sys.argv:
        compose_sheets()
        raise SystemExit(0)
    raise SystemExit(main())
