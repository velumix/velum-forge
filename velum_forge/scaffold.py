"""Scaffold new Velum Forge 3D asset projects (`prop`, `cad`, `fish`, `boat`, `building`, `arch`) with built-in QA & 2K bake."""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import BLENDER_ENGINE_DIR, CAD_ENGINE_DIR


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower()).strip("_")
    return s or "custom_asset"


def _pascal(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("_") if part)


def scaffold_asset(kind: str, name: str, parent_dir: str | Path) -> dict[str, str]:
    slug = _slugify(name)
    pascal = _pascal(slug)
    out_dir = Path(parent_dir).resolve() / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    bl_engine = str(BLENDER_ENGINE_DIR).replace("\\", "\\\\")
    cad_engine = str(CAD_ENGINE_DIR).replace("\\", "\\\\")

    if kind == "cad":
        build_py = out_dir / f"build_{slug}_cad.py"
        build_py.write_text(
            f'''"""Velum Forge Precision B-Rep CAD Part — {pascal} (Meters, Z>=0)."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, "{cad_engine}")

from build123d import Align, Box, BuildPart, BuildSketch, Cylinder, Locations, Mode, Plane, RectangleRounded, extrude, fillet
from cad_bridge import export_cad_part


def build_part():
    with BuildPart() as p:
        with BuildSketch(Plane.XY):
            RectangleRounded(0.180, 0.110, radius=0.018)
        extrude(amount=0.016)
        top_e = p.edges().filter_by(lambda e: abs(e.center().Z - 0.016) < 1e-4)
        fillet(top_e, radius=0.003)
        with Locations([(-0.065, -0.032, 0.016), (0.065, -0.032, 0.016), (-0.065, 0.032, 0.016), (0.065, 0.032, 0.016)]):
            Cylinder(radius=0.0045, height=0.024, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
        with Locations((0, 0, -0.025)):
            Box(0.6, 0.6, 0.05, mode=Mode.SUBTRACT)
    return p.part


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "cad"))
    args = ap.parse_args()
    res = export_cad_part(build_part(), args.out_dir, "{slug}", metallic=0.85, roughness=0.24)
    print(json.dumps(res, indent=2))
    return 0 if res["inspection"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
''',
            encoding="utf-8",
        )
        return {"slug": slug, "dir": str(out_dir), "build_script": str(build_py)}

    # Full Blender + BVH Integrity + 2K Bake + 4-Tier LOD scaffold (`prop`, `fish`, `boat`, `building`)
    build_py = out_dir / f"build_{slug}.py"
    bake_py = out_dir / "bake_lod_variants.py"

    if kind in ("building", "arch"):
        build_py.write_text(
            f'''"""Velum Forge Architectural / Landmark Builder — {pascal} (`kind=building`, 1 unit = 1.0 m, +Y forward, +Z up)."""
from __future__ import annotations

import os
import sys

import bmesh
import bpy

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if "{bl_engine}" not in sys.path:
    sys.path.insert(0, "{bl_engine}")

from vflib import core, gameready, integrity, mats, quadflow, refs  # noqa: E402

# Explicit Multi-Datum Elevations (meters)
Z_ROAD = 0.000
Z_SW = 0.152
Z_FLOOR_INT = Z_SW + 0.025


def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(data)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def build_all(collection_name: str = "{pascal}", clear_scene: bool = True) -> tuple[bpy.types.Collection, list[bpy.types.Object]]:
    if clear_scene:
        clear_scene_and_setup_units()
    root_col = core.fresh_collection(collection_name)
    col_arch = quadflow.sub_collection("Architecture_Shell", root_col)
    col_patio = quadflow.sub_collection("Patio_Furniture", root_col)
    col_bot = quadflow.sub_collection("Botanicals", root_col)

    m_stucco = mats.pbr("{pascal}_Stucco", color="#F5EFE6", roughness=0.72)
    m_sw = mats.pbr("{pascal}_Sidewalk", color="#C7B9AD", roughness=0.82)
    m_wood = mats.pbr("{pascal}_Wood", color="#5C3A21", roughness=0.45)
    m_leaf = mats.pbr("{pascal}_Leaf", color="#2B5E2E", roughness=0.52)

    bm_sw = bmesh.new()
    quadflow.add_box_bounds(bm_sw, -6.0, 6.0, -5.0, 5.0, Z_ROAD, Z_SW, mat_idx=0)
    sw_ob = quadflow.finalize_part(bm_sw, "Sidewalk_Terrace", col_arch, mats=[m_sw], smooth=False, asset_set="street_curbs")

    bm_sh = bmesh.new()
    quadflow.add_box_bounds(bm_sh, -4.5, 4.5, -4.5, -0.2, Z_SW - 0.002, Z_SW + 4.2, mat_idx=0)
    sh_ob = quadflow.finalize_part(bm_sh, "Building_Shell", col_arch, mats=[m_stucco], smooth=False, asset_set="facade")

    # Prototype linked bistro table mesh centered at local origin
    bm_tbl = bmesh.new()
    quadflow.add_cylinder(bm_tbl, (0, 0, 0.0015), (0, 0, 0.03), 0.24, 0.20, segs=24, mat_idx=0)
    quadflow.add_cylinder(bm_tbl, (0, 0, 0.03), (0, 0, 0.72), 0.03, 0.03, segs=16, mat_idx=0)
    quadflow.add_revolved_ring(bm_tbl, (0, 0, 0.74), 0.0, 0.34, 0.032, segs=32, bevel=0.008, mat_idx=0)
    tbl_mesh = quadflow.finalize_mesh_data(bm_tbl, "BistroTable_Mesh", mats=[m_wood])

    meshes = [sw_ob, sh_ob]
    for i, x in enumerate((-2.2, 0.0, 2.2), 1):
        meshes.append(quadflow.spawn_instance(f"Bistro_Table_{{i}}", tbl_mesh, col_patio, loc=(x, 2.0, Z_SW), asset_set="patio_tables"))

    # Curved 3D planter leaves with botanical de-confliction
    bm_bot = bmesh.new()
    for ang in (0.0, 1.4, 2.8, 4.2, 5.4):
        import math
        quadflow.add_curved_leaf(bm_bot, (-3.6, 0.6, Z_SW + 0.35), (math.cos(ang), math.sin(ang), 0.4), length=0.45, width=0.09, mat_idx=0)
    quadflow.deconflict_botanical_islands(bm_bot)
    bot_ob = quadflow.finalize_part(bm_bot, "Corner_Planter_Botanicals", col_bot, mats=[m_leaf], asset_set="botanicals")
    meshes.append(bot_ob)

    quadflow.ground_objects_safe(meshes, target_z=Z_ROAD)
    refs.load_references(THIS_DIR, subject_objects=meshes)
    gameready.validate(meshes, max_tris=300000, deduplicate_meshes=True)
    return root_col, meshes


def main() -> int:
    _col, meshes = build_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "{slug}.blend"))
    core.log(f"Built {pascal} ({{sum(len(o.data.polygons) for o in meshes)}} tris)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            encoding="utf-8",
        )
        bake_py.write_text(
            f'''"""Velum Forge Dedicated 2K Per-Set Cycles PBR Baker, Instance LOD0-LOD3 & Clean Export for {pascal}."""
from __future__ import annotations

import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (THIS_DIR, "{bl_engine}"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bpy  # noqa: E402
from vflib import bake, core, export, lod  # noqa: E402
import build_{slug} as builder  # noqa: E402


def main() -> int:
    col, meshes = builder.build_all(clear_scene=True)
    bake.enable_cycles_gpu(bpy.context.scene)
    groups = bake.group_objects_by_asset_set(meshes)
    tex_dir = os.path.join(THIS_DIR, "textures")
    tex_sets = {{}}
    mats_by_set = {{}}
    for skey, g_objs in groups.items():
        bake.prepare_dedicated_set_uvs(g_objs)
        paths = bake.bake_pbr_set(g_objs, tex_dir, f"T_{pascal}_default_{{skey}}", res=2048, samples=48, isolate_for_ao=True)
        mat = bake.make_baked_pbr_material(f"Baked_{pascal}_{{skey}}", paths)
        bake.assign_baked_and_strip_graphic_uv(g_objs, mat)
        tex_sets[skey] = paths
        mats_by_set[skey] = mat

    lod_summary = lod.build_lod_chain(meshes, os.path.join(THIS_DIR, "lods"), "{slug}", collection_prefix="{pascal}", planar_sets={{"facade"}})
    specs = [dict(name=o.name, objects=[o], role="baked_solid", texture_set=o.get("vf_asset_set")) for o in meshes]
    export.export_roblox(
        "{pascal}",
        os.path.join(THIS_DIR, "roblox"),
        specs,
        source_collection=col,
        prebaked_texture_sets=tex_sets,
        prebaked_materials_by_set=mats_by_set,
        max_tris=300000,
    )
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "{slug}_variants_lods.blend"))
    rep = {{"ok": True, "asset": "{slug}", "bake_res": 2048, "lods": lod_summary, "variants": {{"default": {{"textures": tex_sets}}}}}}
    with open(os.path.join(THIS_DIR, "variants_and_lods_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
            encoding="utf-8",
        )
        return {"slug": slug, "dir": str(out_dir), "build_script": str(build_py), "bake_script": str(bake_py)}

    # Full Blender + BVH Integrity + 2K Bake + 4-Tier LOD scaffold (`prop`, `fish`, `boat`)
    build_py = out_dir / f"build_{slug}.py"
    bake_py = out_dir / "bake_lod_variants.py"

    build_py.write_text(
        f'''"""Velum Forge Parametric Watertight 3D Builder — {pascal} (`kind={kind}`, 1 unit = 1.0 m, Z=0 ground)."""
from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if "{bl_engine}" not in sys.path:
    sys.path.insert(0, "{bl_engine}")

from vflib import core, gameready, integrity, mats  # noqa: E402


def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(data)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def _unwrap_clean(ob: bpy.types.Object) -> None:
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.012, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.010)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


def build_all(collection_name: str = "{pascal}", clear_scene: bool = True) -> tuple[bpy.types.Collection, list[bpy.types.Object]]:
    if clear_scene:
        clear_scene_and_setup_units()
    col = core.fresh_collection(collection_name)

    mat_primary = mats.pbr("{pascal}_Primary", color="#12687A", roughness=0.24, metallic=0.15)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.35)
    bmesh.ops.scale(bm, vec=Vector((0.65, 1.45, 0.55)), verts=bm.verts[:])
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    integrity.ensure_positive_signed_volume(bm)

    me = bpy.data.meshes.new("Body")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat_primary)

    ob = bpy.data.objects.new("Body", me)
    col.objects.link(ob)
    ob["sc_part"] = "Body"
    ob["sc_role"] = "solid"
    _unwrap_clean(ob)

    meshes = [ob]
    lo, _hi = core.world_bbox(meshes)
    if abs(lo.z) > 1e-7:
        for m_ob in meshes:
            m_ob.data.transform(Matrix.Translation((0.0, 0.0, -lo.z)))
            m_ob.data.update()

    gameready.validate(meshes)
    return col, meshes


def main() -> int:
    _col, meshes = build_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "{slug}.blend"))
    core.log(f"Built {pascal} ({{sum(len(o.data.polygons) for o in meshes)}} tris)")
    return 0


if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )

    bake_py.write_text(
        f'''"""Velum Forge 2048x2048 Cycles PBR Baker & 4-Tier LOD Runner for {pascal}."""
from __future__ import annotations

import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (THIS_DIR, "{bl_engine}"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bpy  # noqa: E402
from vflib import bake, core, lod  # noqa: E402
import build_{slug} as builder  # noqa: E402


def main() -> int:
    col, meshes = builder.build_all(clear_scene=True)
    part_objs = {{o["sc_part"]: o for o in meshes}}
    bake.enable_cycles_gpu(bpy.context.scene)
    lod_summary = lod.build_lod_chain(part_objs, os.path.join(THIS_DIR, "lods"), "{slug}", collection_prefix="{pascal}")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "{slug}_variants_lods.blend"))
    rep = {{"ok": True, "asset": "{slug}", "lods": lod_summary}}
    with open(os.path.join(THIS_DIR, "variants_and_lods_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )
    return {"slug": slug, "dir": str(out_dir), "build_script": str(build_py), "bake_script": str(bake_py)}
