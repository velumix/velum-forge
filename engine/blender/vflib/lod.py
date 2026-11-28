"""Seam-Locked 4-Tier Instance-Aware Game LOD Chain Generator (`vflib.lod`)."""
from __future__ import annotations

import math
import os

import bmesh
import bpy

from . import core, gameready

DEFAULT_LOD_TIERS = [
    (1, 0.48, set(), 0.50),
    (2, 0.24, set(), 0.25),
    (3, 0.11, set(), 0.10),
]


def _normalize_parts(lod0_parts: dict[str, bpy.types.Object] | list[bpy.types.Object]) -> dict[str, bpy.types.Object]:
    if isinstance(lod0_parts, dict):
        return lod0_parts
    return {o.name: o for o in lod0_parts if o is not None and o.type == "MESH"}


def build_lod_chain(
    lod0_parts: dict[str, bpy.types.Object] | list[bpy.types.Object],
    out_lods_dir: str,
    asset_slug: str,
    *,
    collection_prefix: str = "Asset",
    tiers: list[tuple[int, float, set[str], float]] | None = None,
    planar_parts: set[str] | None = None,
    planar_sets: set[str] | None = None,
    outboard_decal_parts: set[str] | None = None,
) -> dict[str, dict]:
    """Build `LOD1..LOD3` collections + standalone `.glb` files preserving baked UVs & instancing."""
    parts_map = _normalize_parts(lod0_parts)
    use_tiers = tiers or DEFAULT_LOD_TIERS
    planar = planar_parts or set()
    planar_s = planar_sets or set()
    decal_out = outboard_decal_parts or set()
    os.makedirs(out_lods_dir, exist_ok=True)

    unique_l0 = len({o.data.as_pointer() for o in parts_map.values() if o.data is not None})
    summary: dict[str, dict] = {
        "LOD0": {
            "tris": sum(gameready.triangle_count(o, False) for o in parts_map.values()),
            "parts": len(parts_map),
            "unique_meshes": unique_l0,
            "screen_size": 1.0,
        }
    }

    for lvl, ratio, culled, scr_sz in use_tiers:
        l_col = core.fresh_collection(f"{collection_prefix}_LOD{lvl}")
        lvl_objs: list[bpy.types.Object] = []
        mesh_cache: dict[int, bpy.types.Mesh] = {}

        for pname, src in parts_map.items():
            if pname in culled or src.data is None:
                continue
            asset_set = str(src.get("vf_asset_set", ""))
            is_planar = (pname in planar) or (asset_set in planar_s) or (pname in planar_s)
            is_decal = pname in decal_out

            cp = src.copy()
            cp.name = f"{pname}_LOD{lvl}"
            l_col.objects.link(cp)
            cp["sc_part"] = pname
            cp["sc_role"] = src.get("sc_role", "solid")
            if asset_set:
                cp["vf_asset_set"] = asset_set
            if src.get("vf_instanced"):
                cp["vf_instanced"] = True

            ptr = src.data.as_pointer()
            if ptr in mesh_cache and not is_decal:
                cp.data = mesh_cache[ptr]
                lvl_objs.append(cp)
                continue

            cp.data = src.data.copy()
            cp.data.name = cp.name

            dec = cp.modifiers.new("VF_LOD_Decimate", "DECIMATE")
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

            if is_planar or is_decal:
                bm = bmesh.new()
                bm.from_mesh(cp.data)
                if is_planar:
                    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="FIXED")
                if is_decal:
                    mw = cp.matrix_world
                    dx = {1: 0.003, 2: 0.008, 3: 0.013}.get(lvl, 0.006)
                    for v in bm.verts:
                        wco = mw @ v.co
                        if abs(wco.x) > 0.02:
                            v.co.x += math.copysign(dx, wco.x)
                bm.to_mesh(cp.data)
                bm.free()
                cp.data.update()

            if not is_decal:
                mesh_cache[ptr] = cp.data
            lvl_objs.append(cp)

        glb_lod = os.path.join(out_lods_dir, f"{asset_slug}_LOD{lvl}.glb")
        if lvl_objs:
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
        unique_cnt = len({o.data.as_pointer() for o in lvl_objs if o.data is not None})
        summary[f"LOD{lvl}"] = {
            "tris": tris,
            "parts": len(lvl_objs),
            "unique_meshes": unique_cnt,
            "screen_size": scr_sz,
            "glb": f"lods/{asset_slug}_LOD{lvl}.glb",
        }
        core.log(f"[LOD{lvl}] {tris} tris across {len(lvl_objs)} parts ({unique_cnt} unique meshes) -> {glb_lod}")

    return summary
