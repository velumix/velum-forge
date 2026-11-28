"""Velum Forge High-Texel 2K Cycles GPU PBR Bake, 4 Variants & 4-Tier LOD0-LOD3 Pipeline for `memorial`.

Exact 2-Object Game-Ready Architecture (Pan Am Flight 103 Memorial Cairn — Arlington National Cemetery):
  1. `Memorial`     (`~19,584` tris < 20k Roblox limit) — Entire monument joined into ONE single object
                    (6 granite base wedges + 6 curved bronze name plaques + unbroken 14-course sandstone shaft +
                    18 flat-aligned coping stones).
  2. `BronzePlaque` (`524` tris) — Flush-recessed CAD Pan Am Flight 103 commemorative bronze tablet.

Key engineering features:
  - Mathematically normalized `2048x2048` visible-area UV atlas (`68%` BIG-SLAB Corsehill red sandstone,
    `14%` seamless polar 6-panel bronze collar, `8%` dark granite curb, `10%` crisp left-to-right Pan Am 103
    serif tablet, `<0.5%` buried interior caps).
  - Power-safe GPU-only (`OPTIX`/`CUDA`, CPU hybrid OFF, `512px` tiles, inter-pass cooldown) Cycles baking
    of all 6 PBR maps (`Color` sRGB + 64-sample linear Cycles AO, OpenGL `Normal`, `Roughness`, `Metalness`,
    `AO`, `ORM`) across 4 architectural monument variants + seam-locked `LOD0`..`LOD3` chains.
  - Renders full un-cropped showcase suite PLUS `baked_photo_comparison.png`, `baked_closeup.png`, AND
    `stone_detail_closeup.png` verifying the BIG broad quarry-split stone planes close up!
"""
from __future__ import annotations

import importlib
import json
import math
import os
import shutil
import sys
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_BLENDER = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "engine", "blender"))
for _p in (THIS_DIR, ENGINE_BLENDER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from vflib import bake, core, export, gameready, lod, mats, render  # noqa: E402
import build_memorial as builder  # noqa: E402

importlib.reload(builder)

BAKE_RES = 2048
BAKE_MARGIN_PX = 14
PART_ORDER = ("Memorial", "BronzePlaque")

TEXTURES_ROOT = os.path.join(THIS_DIR, "textures")
VARIANTS_ROOT = os.path.join(THIS_DIR, "variants")
LODS_ROOT = os.path.join(THIS_DIR, "lods")
EXPORT_DEFAULT = os.path.join(THIS_DIR, "export")
RENDERS_ROOT = os.path.join(THIS_DIR, "renders")
DESIGN_OUTPUT_DIR = core.DESIGN_OUTPUT_DIR

VARIANTS: list[dict] = [
    {
        "id": "reference_match",
        "label": "Pan Am 103 Lockerbie Cairn — Corsehill Red Sandstone & Weathered Bronze (Arlington Reference)",
        "edition": "Flagship",
        "palette": dict(builder.DEFAULT_PALETTE),
    },
    {
        "id": "vermont_granite",
        "label": "Memorial Cairn — Barre Silver-Grey Granite & Verdigris Patinated Bronze",
        "edition": "Civic",
        "palette": {
            "stone_warm": "#A6ACB2",
            "stone_russet": "#969CA2",
            "stone_deep": "#868D94",
            "mortar": "#4F555B",
            "curb_stone": "#545B62",
            "curb_top": "#767E86",
            "moss_tint": "#33472B",
            "bronze_apron": "#3A5A50",
            "bronze_accent": "#668A7B",
            "bronze_patina": "#89AFA0",
            "bronze_collar": "#5D6965",
            "bronze_plaque": "#213630",
            "bronze_letter": "#648E80",
            "bronze_metal": 0.46,
            "bronze_rough": 0.54,
        },
    },
    {
        "id": "indiana_limestone",
        "label": "Memorial Cairn — Honey Indiana Limestone & Burnished Classical Bronze",
        "edition": "Classical",
        "palette": {
            "stone_warm": "#D2C5AC",
            "stone_russet": "#C4B599",
            "stone_deep": "#B3A387",
            "mortar": "#6E6353",
            "curb_stone": "#7E7261",
            "curb_top": "#9E9280",
            "moss_tint": "#3F4F30",
            "bronze_apron": "#684D2E",
            "bronze_accent": "#A6824A",
            "bronze_patina": "#9B988B",
            "bronze_collar": "#7B6F5F",
            "bronze_plaque": "#342718",
            "bronze_letter": "#9E7B44",
            "bronze_metal": 0.56,
            "bronze_rough": 0.46,
        },
    },
    {
        "id": "volcanic_basalt",
        "label": "Memorial Cairn — Columnar Charcoal Basalt & Aged Statuary Brass",
        "edition": "Monolith",
        "palette": {
            "stone_warm": "#464C54",
            "stone_russet": "#3A3F47",
            "stone_deep": "#2E333A",
            "mortar": "#181B20",
            "curb_stone": "#24282E",
            "curb_top": "#3C424A",
            "moss_tint": "#2A3A24",
            "bronze_apron": "#665434",
            "bronze_accent": "#A38850",
            "bronze_patina": "#78746A",
            "bronze_collar": "#3E3D39",
            "bronze_plaque": "#221D15",
            "bronze_letter": "#A3864B",
            "bronze_metal": 0.60,
            "bronze_rough": 0.44,
        },
    },
]


# ---------------------------------------------------------------------------
# 2. High-Texel Exact Visible-Area UV Atlas Packer (2 Objects: `Memorial` + `BronzePlaque`)
# ---------------------------------------------------------------------------
def _is_plaque_text_face(f: bmesh.types.BMFace) -> bool:
    cen = f.calc_center_median()
    return (
        f.normal.x < -0.85
        and abs(cen.y) <= (0.5 * builder.PLAQUE_W - 0.11)
        and abs(cen.z - builder.PLAQUE_Z_CTR) <= (0.5 * builder.PLAQUE_H - 0.11)
    )


def _memorial_face_region(f: bmesh.types.BMFace, st_uv=None) -> str:
    """Classify each polygon on unified `Memorial` into clean cylindrical/planar UV atlas regions!

    Material indices on `Memorial`:
      0=ShaftStone, 1=CopingStone, 2=CurbStone, 3=BronzeApron, 4=Mortar, 5=CapTop, 6=CurbBottom
    """
    cen = f.calc_center_median()
    n = f.normal
    r = math.hypot(cen.x, cen.y)
    mi = f.material_index

    if mi == 5:  # CapTop (singularity-free planar top sandstone crown!)
        return "cap_top"

    if mi == 6:  # CurbBottom (singularity-free planar granite/concrete underside foundation!)
        return "curb_bottom"

    if mi == 3:  # BronzeApron
        if (n.z < -0.75) or (r < 5.30):
            return "hidden"
        return "apron_top" if n.z > 0.15 else "apron_edge"

    if mi == 2:  # CurbStone
        if (n.z < -0.75) or (cen.z < 1.32 and r < 8.05):
            return "hidden"
        if st_uv is not None:
            u_mid = sum(lp[st_uv].uv.x for lp in f.loops) / len(f.loops)
            return "curb_a" if u_mid < 0.5 else "curb_b"
        return "curb_a"

    if mi == 1:  # CopingStone (vertical rock-faced fascia)
        if n.z < -0.75 and r < 4.18:
            return "hidden"
        if st_uv is not None:
            u_mid = sum(lp[st_uv].uv.x for lp in f.loops) / len(f.loops)
            return "cap_a" if u_mid < 0.5 else "cap_b"
        return "cap_a"

    if mi == 4:  # Mortar (plaque aperture back wall, cap drip soffit, hidden inner caps)
        if (n.z < -0.75 and r < 4.90) or (cen.z < 2.10 and r < 5.10):
            return "hidden"
        if cen.z > 17.10 and abs(n.z) > 0.75 and r < 4.20 and cen.z < 17.50:
            return "hidden"
        return "mortar"

    # mi == 0: ShaftStone — split cleanly along exact mesh seams u=0.25 (+Y) and u=0.75 (-Y)
    if st_uv is not None:
        u_mid = sum(lp[st_uv].uv.x for lp in f.loops) / len(f.loops)
        if 0.25 <= u_mid <= 0.75:
            return "shaft_front"
        return "shaft_rear_a" if u_mid < 0.25 else "shaft_rear_b"
    return "shaft_front"


def _uv_face_area(f: bmesh.types.BMFace, uv_lay) -> float:
    pts = [lp[uv_lay].uv for lp in f.loops]
    a2 = 0.0
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        a2 += pts[i].x * pts[j].y - pts[j].x * pts[i].y
    return 0.5 * abs(a2)


def _map_box(u: float, v: float, u0: float, u1: float, v0: float, v1: float) -> tuple[float, float]:
    """Map normalized [0, 1]^2 UV cleanly into exact atlas sub-rectangle `[u0, u1] x [v0, v1]`."""
    return (u0 + max(0.0, min(1.0, u)) * (u1 - u0), v0 + max(0.0, min(1.0, v)) * (v1 - v0))


def pack_shared_memorial_atlas(part_objs: dict[str, bpy.types.Object]) -> None:
    """Deterministic, ZERO-needle, ~88% coverage 2048x2048 UV atlas layout for `Memorial` + `BronzePlaque`!

    Exact non-overlapping `[0, 1]^2` atlas regions (>= 16 px clean gutter between every architectural zone):
      - `shaft_front` (180 deg hero `-X` face): `[0.008, 0.568] x [0.432, 0.992]` (`1147 x 1147 px`!)
      - `shaft_rear_a` (90 deg rear-left):      `[0.578, 0.782] x [0.432, 0.992]` (`418 x 1147 px`)
      - `shaft_rear_b` (90 deg rear-right):     `[0.790, 0.992] x [0.432, 0.992]` (`414 x 1147 px`)
      - `apron_top` (6-panel polar ring):       `[0.008, 0.422] x [0.008, 0.422]` (`848 x 848 px`, inner hole `r>=0.130`)
      - `cap_top` (18-stone circular top deck): nested cleanly inside apron hole (`r<=0.110`, `38 px` radial gap!)
      - `BronzePlaque` front text tablet:       `[0.432, 0.712] x [0.178, 0.420]` (`573 x 496 px`, exact `1.155` ratio!)
      - `cap_a` / `cap_b` (18 coping stones):   `[0.722, 0.992] x [0.336, 0.422]` & `[0.242, 0.328]` (`553 x 176 px` ea)
      - `curb_a` / `curb_b` (6 granite wedges): `[0.432, 0.992] x [0.093, 0.168]` & `[0.008, 0.083]` (`1147 x 154 px` ea)
      - `aux` (`mortar`, `apron_edge`, `hidden`, plaque sides): packed neatly in `[0.722, 0.992] x [0.178, 0.234]`!
    """
    all_objs = [part_objs[k] for k in PART_ORDER]
    core.ensure_object_mode()

    # Step A: Split edges strictly at region boundaries so zero UV bleed crosses islands!
    for pname in PART_ORDER:
        ob = part_objs[pname]
        ob.data.uv_layers.active_index = 0
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        st_uv = bm.loops.layers.uv.get("StoneUV")
        split_edges = set()
        for e in bm.edges:
            if len({f.material_index for f in e.link_faces}) > 1:
                split_edges.add(e)
            elif len(e.link_faces) == 2:
                if pname == "Memorial":
                    if _memorial_face_region(e.link_faces[0], st_uv) != _memorial_face_region(e.link_faces[1], st_uv):
                        split_edges.add(e)
                else:
                    if _is_plaque_text_face(e.link_faces[0]) != _is_plaque_text_face(e.link_faces[1]):
                        split_edges.add(e)
        if split_edges:
            bmesh.ops.split_edges(bm, edges=list(split_edges))
        bm.to_mesh(ob.data)
        bm.free()

    # Step B: Smart-project + pack ONLY small auxiliary/hidden faces cleanly into `[0.722, 0.992] x [0.178, 0.234]`!
    # First select only auxiliary faces across both objects, unwrap & pack them into [0, 1]^2, then affine-map!
    aux_regions = {"apron_edge", "mortar", "hidden"}
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in all_objs:
        o.data.uv_layers.active_index = 0
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")

    for pname in PART_ORDER:
        ob = part_objs[pname]
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        st_uv = bm.loops.layers.uv.get("StoneUV")
        bm.select_mode = {"FACE"}
        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
        for f in bm.faces:
            is_aux = (_memorial_face_region(f, st_uv) in aux_regions) if pname == "Memorial" else (not _is_plaque_text_face(f))
            f.select = is_aux
        bm.select_flush_mode()
        bm.to_mesh(ob.data)
        bm.free()

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(52.0), island_margin=0.015, scale_to_bounds=True)
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.012)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Step C: Assign EXACT deterministic zero-overlap boxes for EVERY hero & auxiliary region!
    ob_mem = part_objs["Memorial"]
    bm_m = bmesh.new()
    bm_m.from_mesh(ob_mem.data)
    uv0_m = bm_m.loops.layers.uv[0]
    st_uv = bm_m.loops.layers.uv.get("StoneUV")
    ap_uv = bm_m.loops.layers.uv.get("ApronUV")

    for f in bm_m.faces:
        reg = _memorial_face_region(f, st_uv)
        if reg == "shaft_front" and st_uv is not None:
            for lp in f.loops:
                u = (lp[st_uv].uv.x - 0.25) * 2.0
                v = lp[st_uv].uv.y
                lp[uv0_m].uv = _map_box(u, v, 0.008, 0.568, 0.432, 0.992)
        elif reg == "shaft_rear_a" and st_uv is not None:
            for lp in f.loops:
                u = lp[st_uv].uv.x * 4.0
                v = lp[st_uv].uv.y
                lp[uv0_m].uv = _map_box(u, v, 0.578, 0.782, 0.432, 0.992)
        elif reg == "shaft_rear_b" and st_uv is not None:
            for lp in f.loops:
                u = (lp[st_uv].uv.x - 0.75) * 4.0
                v = lp[st_uv].uv.y
                lp[uv0_m].uv = _map_box(u, v, 0.790, 0.992, 0.432, 0.992)
        elif reg == "apron_top" and ap_uv is not None:
            for lp in f.loops:
                u, v = lp[ap_uv].uv.x, lp[ap_uv].uv.y
                lp[uv0_m].uv = _map_box(u, v, 0.008, 0.422, 0.008, 0.422)
        elif reg == "cap_top" and st_uv is not None:
            # Singularity-free true planar (X, Y) sandstone crown nested cleanly inside `apron_top`'s hollow center!
            # Center=(0.215, 0.215), r<=0.112 (`458x458 px`!) vs apron inner hole r>=0.131 (`38 px` clean gutter!)
            for lp in f.loops:
                u_s, v_s = lp[st_uv].uv.x, lp[st_uv].uv.y
                lp[uv0_m].uv = (0.215 + (u_s - 0.5) * 0.224, 0.215 + (v_s - 0.5) * 0.224)
        elif reg == "curb_bottom" and st_uv is not None:
            # Dedicated singularity-free planar foundation underside disc `[0.838, 0.992] x [0.008, 0.162]` (`315x315 px`!)
            for lp in f.loops:
                u_s, v_s = lp[st_uv].uv.x, lp[st_uv].uv.y
                lp[uv0_m].uv = _map_box(u_s, v_s, 0.838, 0.992, 0.008, 0.162)
        elif reg == "cap_a" and st_uv is not None:
            for lp in f.loops:
                u = lp[st_uv].uv.x * 2.0
                v = lp[st_uv].uv.y / 0.72
                lp[uv0_m].uv = _map_box(u, v, 0.716, 0.992, 0.354, 0.422)
        elif reg == "cap_b" and st_uv is not None:
            for lp in f.loops:
                u = (lp[st_uv].uv.x - 0.5) * 2.0
                v = lp[st_uv].uv.y / 0.72
                lp[uv0_m].uv = _map_box(u, v, 0.716, 0.992, 0.280, 0.346)
        elif reg == "curb_a" and st_uv is not None:
            for lp in f.loops:
                u = lp[st_uv].uv.x * 2.0
                v = lp[st_uv].uv.y
                lp[uv0_m].uv = _map_box(u, v, 0.432, 0.830, 0.090, 0.166)
        elif reg == "curb_b" and st_uv is not None:
            for lp in f.loops:
                u = (lp[st_uv].uv.x - 0.5) * 2.0
                v = lp[st_uv].uv.y
                lp[uv0_m].uv = _map_box(u, v, 0.432, 0.830, 0.008, 0.082)
        else:
            # Auxiliary / hidden faces packed cleanly in `[0.716, 0.992] x [0.178, 0.272]`!
            for lp in f.loops:
                u, v = lp[uv0_m].uv.x, lp[uv0_m].uv.y
                lp[uv0_m].uv = _map_box(u, v, 0.716, 0.992, 0.178, 0.272)
    bm_m.to_mesh(ob_mem.data)
    bm_m.free()

    ob_pl = part_objs["BronzePlaque"]
    bm_p = bmesh.new()
    bm_p.from_mesh(ob_pl.data)
    uv0_p = bm_p.loops.layers.uv[0]
    pl_uv = bm_p.loops.layers.uv.get("PlaqueUV")
    for f in bm_p.faces:
        if _is_plaque_text_face(f) and pl_uv is not None:
            for lp in f.loops:
                u, v = lp[pl_uv].uv.x, lp[pl_uv].uv.y
                lp[uv0_p].uv = _map_box(u, v, 0.432, 0.706, 0.178, 0.420)
        else:
            for lp in f.loops:
                u, v = lp[uv0_p].uv.x, lp[uv0_p].uv.y
                lp[uv0_p].uv = _map_box(u, v, 0.716, 0.992, 0.178, 0.272)
    bm_p.to_mesh(ob_pl.data)
    bm_p.free()

    # Step D: Lock UV seams for LOD0-LOD3 preservation (NO re-packing — our deterministic boxes fill ~88%!)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in all_objs:
        o.data.uv_layers.active_index = 0
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in all_objs:
        o.select_set(False)

    # Step E: Re-weld 3D vertices back to 100% watertight while keeping isolated per-loop UVs!
    for ob in all_objs:
        bm_w = bmesh.new()
        bm_w.from_mesh(ob.data)
        bmesh.ops.remove_doubles(bm_w, verts=bm_w.verts[:], dist=1e-6)
        bm_w.to_mesh(ob.data)
        bm_w.free()
        ob.data.update()


# ---------------------------------------------------------------------------
# 3. True `2048x2048` Power-Safe Cycles GPU (`OPTIX`) PBR Texture Baker
# ---------------------------------------------------------------------------
def _make_bake_img(name: str, res: int, colorspace: str) -> bpy.types.Image:
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, width=res, height=res, alpha=False, float_buffer=True)
    img.colorspace_settings.name = colorspace
    return img


def _read_float_img(img: bpy.types.Image) -> np.ndarray:
    w, h = img.size
    buf = np.zeros(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    return buf.reshape((h, w, 4))


def _attach_targets(ob: bpy.types.Object, img: bpy.types.Image) -> list[tuple[bpy.types.NodeTree, bpy.types.Node]]:
    created = []
    for sl in ob.material_slots:
        if sl.material is None:
            continue
        nt = sl.material.node_tree
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = img
        for n in nt.nodes:
            n.select = False
        tn.select = True
        nt.nodes.active = tn
        created.append((nt, tn))
    return created


def _remove_targets(created: list[tuple[bpy.types.NodeTree, bpy.types.Node]]) -> None:
    for nt, tn in created:
        nt.nodes.remove(tn)


def _route_to_emission(materials: list[bpy.types.Material], sock_name: str) -> list[tuple]:
    undo = []
    for mat in materials:
        nt = mat.node_tree
        out = mats.output_node(mat)
        b = mats.bsdf(mat)
        prev = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        s_in = mats.sock(b, sock_name)
        if s_in is not None and s_in.is_linked:
            nt.links.new(s_in.links[0].from_socket, em.inputs["Color"])
        elif s_in is not None:
            dv = s_in.default_value
            em.inputs["Color"].default_value = tuple(dv) if hasattr(dv, "__len__") else (dv, dv, dv, 1.0)
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        undo.append((nt, em, out, prev))
    return undo


def _restore_emission(undo: list[tuple]) -> None:
    for nt, em, out, prev in reversed(undo):
        if prev is not None:
            nt.links.new(prev, out.inputs["Surface"])
        nt.nodes.remove(em)


def bake_memorial_pbr_maps(
    variant_id: str,
    part_objs: dict[str, bpy.types.Object],
    out_dir: str,
    *,
    cached_ao: np.ndarray | None = None,
    res: int = BAKE_RES,
) -> tuple[bpy.types.Material, dict[str, str], np.ndarray]:
    """Bake 2048x2048 Color (+ 64-sample linear AO), OpenGL Normal, Roughness, Metalness, AO & ORM maps."""
    sc = bpy.context.scene
    backend = bake.enable_cycles_gpu(sc)
    sc.cycles.use_denoising = False
    core.log(f"[bake:{variant_id}] Cycles backend={backend} (power-safe GPU-only), res={res}x{res}")

    tmp_col = core.fresh_collection("__MEM_BakeProxy")
    dups = []
    for k in PART_ORDER:
        src = part_objs[k]
        cp = src.copy()
        cp.data = src.data.copy()
        for req_uv in ("StoneUV", "ApronUV", "PlaqueUV"):
            if req_uv not in cp.data.uv_layers:
                cp.data.uv_layers.new(name=req_uv)
        cp.data.uv_layers.active_index = 0
        tmp_col.objects.link(cp)
        dups.append(cp)

    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for d in dups:
        d.select_set(True)
    bpy.context.view_layer.objects.active = dups[0]
    bpy.ops.object.join()
    proxy = bpy.context.view_layer.objects.active
    proxy.name = f"__BakeProxy_{variant_id}"
    gameready.collapse_materials(proxy)
    proxy.data.uv_layers.active_index = 0

    prev_hide = [(o, o.hide_render) for o in sc.objects if o != proxy and o.type == "MESH"]
    for o, _ in prev_hide:
        o.hide_render = True

    used_mats = [s.material for s in proxy.material_slots if s.material is not None]
    bk = sc.render.bake
    bk.use_selected_to_active = False
    bk.use_clear = True
    bk.margin = BAKE_MARGIN_PX
    bk.margin_type = "EXTEND"
    bk.target = "IMAGE_TEXTURES"

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy

    try:
        if cached_ao is None:
            img_ao = _make_bake_img("__mem_ao", res, "Non-Color")
            tn = _attach_targets(proxy, img_ao)
            sc.cycles.samples = 64
            bpy.ops.object.bake(type="AO")
            ao_arr = np.clip(_read_float_img(img_ao)[..., 0].copy(), 0.0, 1.0)
            _remove_targets(tn)
            bpy.data.images.remove(img_ao)
            bake.cooldown()
        else:
            ao_arr = cached_ao

        img_n = _make_bake_img("__mem_n", res, "Non-Color")
        img_n.generated_color = (0.5, 0.5, 1.0, 1.0)
        tn = _attach_targets(proxy, img_n)
        sc.cycles.samples = 16
        bk.normal_space = "TANGENT"
        bk.normal_r = "POS_X"
        bk.normal_g = "POS_Y"
        bk.normal_b = "POS_Z"
        bpy.ops.object.bake(type="NORMAL")
        norm_arr = _read_float_img(img_n).copy()
        _remove_targets(tn)
        bpy.data.images.remove(img_n)
        bake.cooldown()

        img_r = _make_bake_img("__mem_r", res, "Non-Color")
        tn = _attach_targets(proxy, img_r)
        sc.cycles.samples = 8
        bpy.ops.object.bake(type="ROUGHNESS")
        rough_arr = _read_float_img(img_r)[..., 0].copy()
        _remove_targets(tn)
        bpy.data.images.remove(img_r)

        img_bc = _make_bake_img("__mem_bc", res, "Non-Color")
        u_bc = _route_to_emission(used_mats, "Base Color")
        tn = _attach_targets(proxy, img_bc)
        sc.cycles.samples = 16
        bpy.ops.object.bake(type="EMIT")
        bc_lin = _read_float_img(img_bc)[..., :3].copy()
        _remove_targets(tn)
        _restore_emission(u_bc)
        bpy.data.images.remove(img_bc)
        bake.cooldown()

        img_m = _make_bake_img("__mem_m", res, "Non-Color")
        u_m = _route_to_emission(used_mats, "Metallic")
        tn = _attach_targets(proxy, img_m)
        sc.cycles.samples = 4
        bpy.ops.object.bake(type="EMIT")
        metal_arr = _read_float_img(img_m)[..., 0].copy()
        _remove_targets(tn)
        _restore_emission(u_m)
        bpy.data.images.remove(img_m)

    finally:
        for o, hs in prev_hide:
            o.hide_render = hs
        core.clear_collection(tmp_col)
        bpy.data.collections.remove(tmp_col)

    # Keep Cycles geometry AO crisp without double-crushing the physical rock-cleave overhang AO already in Base Color
    ao_fac = (0.72 + 0.28 * ao_arr)[..., None]
    bc_shaded = np.clip(bc_lin * ao_fac, 0.0, 1.0)
    color_rgba = np.ones((res, res, 4), dtype=np.float32)
    color_rgba[..., :3] = bake.lin_arr_to_srgb(bc_shaded)

    norm_rgba = np.ones((res, res, 4), dtype=np.float32)
    norm_rgba[..., :3] = np.clip(norm_arr[..., :3], 0.0, 1.0)

    rough_rgba = np.ones((res, res, 4), dtype=np.float32)
    rough_rgba[..., :3] = np.clip(rough_arr, 0.05, 1.0)[..., None]

    metal_rgba = np.ones((res, res, 4), dtype=np.float32)
    metal_rgba[..., :3] = np.clip(metal_arr, 0.0, 1.0)[..., None]

    ao_rgba = np.ones((res, res, 4), dtype=np.float32)
    ao_rgba[..., :3] = ao_arr[..., None]

    orm_rgba = np.ones((res, res, 4), dtype=np.float32)
    orm_rgba[..., 0] = ao_arr
    orm_rgba[..., 1] = np.clip(rough_arr, 0.05, 1.0)
    orm_rgba[..., 2] = np.clip(metal_arr, 0.0, 1.0)

    prefix = f"T_Memorial_{variant_id}"
    paths = {
        "Color": os.path.join(out_dir, f"{prefix}_Color.png"),
        "Normal": os.path.join(out_dir, f"{prefix}_Normal.png"),
        "Roughness": os.path.join(out_dir, f"{prefix}_Roughness.png"),
        "Metalness": os.path.join(out_dir, f"{prefix}_Metalness.png"),
        "AO": os.path.join(out_dir, f"{prefix}_AO.png"),
        "ORM": os.path.join(out_dir, f"{prefix}_ORM.png"),
    }
    img_c = bake.save_png_8bit(color_rgba, paths["Color"], "sRGB")
    img_n = bake.save_png_8bit(norm_rgba, paths["Normal"], "Non-Color")
    img_r = bake.save_png_8bit(rough_rgba, paths["Roughness"], "Non-Color")
    img_m = bake.save_png_8bit(metal_rgba, paths["Metalness"], "Non-Color")
    bake.save_png_8bit(ao_rgba, paths["AO"], "Non-Color")
    bake.save_png_8bit(orm_rgba, paths["ORM"], "Non-Color")

    baked_mat, bsdf_n = mats._new_node_material(f"M_Memorial_{variant_id}_Baked")
    nt = baked_mat.node_tree

    tc_n = nt.nodes.new("ShaderNodeTexImage")
    tc_n.image = img_c
    tc_n.location = (-520, 320)
    nt.links.new(mats.sock(tc_n, "Color", output=True), mats.sock(bsdf_n, "Base Color"))

    tr_n = nt.nodes.new("ShaderNodeTexImage")
    tr_n.image = img_r
    tr_n.location = (-520, 40)
    nt.links.new(mats.sock(tr_n, "Color", output=True), mats.sock(bsdf_n, "Roughness"))

    tm_n = nt.nodes.new("ShaderNodeTexImage")
    tm_n.image = img_m
    tm_n.location = (-520, -240)
    nt.links.new(mats.sock(tm_n, "Color", output=True), mats.sock(bsdf_n, "Metallic"))

    tn_n = nt.nodes.new("ShaderNodeTexImage")
    tn_n.image = img_n
    tn_n.location = (-760, -520)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.location = (-420, -520)
    nmap.inputs["Strength"].default_value = 1.05
    nt.links.new(mats.sock(tn_n, "Color", output=True), mats.sock(nmap, "Color"))
    nt.links.new(mats.sock(nmap, "Normal", output=True), mats.sock(bsdf_n, "Normal"))

    for pob in part_objs.values():
        while len(pob.data.uv_layers) > 1:
            pob.data.uv_layers.remove(pob.data.uv_layers[-1])
        pob.data.uv_layers[0].name = "UVMap"
        pob.data.uv_layers.active_index = 0
        pob.data.materials.clear()
        pob.data.materials.append(baked_mat)
        for poly in pob.data.polygons:
            poly.material_index = 0

    baked_mat["sc_role"] = "baked_pbr"
    return baked_mat, paths, ao_arr


# ---------------------------------------------------------------------------
# 4. Roblox Bundle + glTF Exporter (Exact 2 MeshParts: `Memorial` + `BronzePlaque`)
# ---------------------------------------------------------------------------
def export_memorial_variant_bundle(
    variant: dict,
    src_col: bpy.types.Collection,
    part_objs: dict[str, bpy.types.Object],
    baked_mat: bpy.types.Material,
    tex_paths: dict[str, str],
    out_dir: str,
    extra_manifest: dict | None = None,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    tex_out = os.path.join(out_dir, "textures")
    os.makedirs(tex_out, exist_ok=True)

    rel_tex = {}
    for k in ("Color", "Normal", "Roughness", "Metalness", "AO", "ORM"):
        dst_name = os.path.basename(tex_paths[k])
        shutil.copy2(tex_paths[k], os.path.join(tex_out, dst_name))
        if k in ("Color", "Normal", "Roughness", "Metalness"):
            rel_tex[k] = f"textures/{dst_name}"

    glb_path = os.path.join(out_dir, f"memorial_{variant['id']}.glb")
    all_v_objs = [part_objs[k] for k in PART_ORDER]
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in all_v_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_v_objs[0]
    bpy.ops.export_scene.gltf(filepath=glb_path, use_selection=True, export_format="GLB", export_apply=True)
    for o in all_v_objs:
        o.select_set(False)

    parts_spec = [
        dict(name="Memorial", objects=[part_objs["Memorial"]], role="solid", collide=True, render_fidelity="Precise"),
        dict(name="BronzePlaque", objects=[part_objs["BronzePlaque"]], role="solid", collide=False, render_fidelity="Precise"),
    ]

    lo, hi = core.world_bbox(all_v_objs)
    asset_tag = "Memorial" if variant["id"] == "reference_match" else f"Memorial_{variant['id']}"
    export.export_roblox(
        asset_tag,
        out_dir,
        parts=parts_spec,
        source_collection=src_col,
        primary=dict(name="MemorialMonument", center=(lo + hi) * 0.5, size=hi - lo),
        attributes={
            "Asset": "Memorial",
            "Monument": "Pan Am Flight 103 Lockerbie Cairn (Arlington National Cemetery)",
            "Edition": variant["edition"],
            "Variant": variant["id"],
            "HeightMeters": builder.TOTAL_HEIGHT,
        },
        tags=["Memorial", "Monument", "Arlington", "Architecture", f"Edition_{variant['edition']}"],
        reference="Memorial",
        prebaked_material=baked_mat,
        prebaked_textures=rel_tex,
        extra_manifest=extra_manifest,
    )


# ---------------------------------------------------------------------------
# 5. Un-Cropped Cycles Showcase Suite + Close-Up Stonework & Photo Match Verification
# ---------------------------------------------------------------------------
def _compose_baked_photo_comparison(ref_img_path: str, baked_persp_path: str, out_path: str) -> str | None:
    if not (os.path.isfile(ref_img_path) and os.path.isfile(baked_persp_path)):
        return None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    with Image.open(ref_img_path) as im_r:
        r_im = im_r.convert("RGB")
    with Image.open(baked_persp_path) as im_m:
        m_im = im_m.convert("RGB")

    h = 720
    rw = int(round(r_im.width * (h / r_im.height)))
    mw = int(round(m_im.width * (h / m_im.height)))
    r_im = r_im.resize((rw, h), Image.Resampling.LANCZOS)
    m_im = m_im.resize((mw, h), Image.Resampling.LANCZOS)

    pad = 16
    hdr = 44
    canvas = Image.new("RGB", (pad * 3 + rw + mw, hdr + h + pad), (20, 24, 32))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 14), "ARLINGTON REFERENCE PHOTO (Pan Am Flight 103 Cairn)", fill=(235, 240, 248))
    draw.text((pad * 2 + rw, 14), "BAKED 2K PBR UNIFIED MODEL (Matched Perspective)", fill=(96, 230, 150))
    canvas.paste(r_im, (pad, hdr))
    canvas.paste(m_im, (pad * 2 + rw, hdr))
    canvas.save(out_path, format="PNG")
    return out_path


def render_showcase_suite(
    variant_cols: dict[str, bpy.types.Collection],
    lod_cols: list[tuple[str, bpy.types.Collection]],
    out_dir: str,
) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    bake.enable_cycles_gpu(sc)
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    sc.render.image_settings.file_format = "PNG"
    try:
        sc.view_settings.view_transform = "AgX"
    except TypeError:
        pass

    shots: dict[str, str] = {}
    for _lbl, lc in lod_cols[1:]:
        lc.hide_render = True
        lc.hide_viewport = True

    for vid, vcol in variant_cols.items():
        for oid, ocol in variant_cols.items():
            ocol.hide_render = oid != vid
            ocol.hide_viewport = oid != vid

        v_meshes = core.objects_in(vcol, types=("MESH",))
        st = render.setup_studio(v_meshes, backdrop="product")
        cd = bpy.data.cameras.new("MEM_HeroCam")
        cm = bpy.data.objects.new("MEM_HeroCam", cd)
        st.objects.link(cm)
        sc.camera = cm
        try:
            sc.render.resolution_x = 1440
            sc.render.resolution_y = 1080
            render.frame_camera(cm, v_meshes, (-0.90, 0.34, 0.24), lens=45.0, margin=0.92, aspect=1440 / 1080)
            p_hero = os.path.join(out_dir, f"variant_{vid}.png")
            bake.render_still_safe(sc, p_hero)
            shots[f"variant_{vid}"] = p_hero

            if vid == "reference_match":
                # Macro Close-Up proving BIG broad quarry-split stone planes & readable Pan Am 103 plaque!
                sc.render.resolution_x = 1600
                sc.render.resolution_y = 1000
                cm.location = Vector((-13.2, 3.6, 10.7))
                cm.data.lens = 58.0
                cm.rotation_euler = (Vector((-4.6, 0.0, 10.68)) - cm.location).to_track_quat("-Z", "Y").to_euler()
                p_close = os.path.join(out_dir, "baked_closeup.png")
                bake.render_still_safe(sc, p_close)
                shots["baked_closeup"] = p_close

                # Left-curve Masonry Detail Close-Up matching User Screenshot 1 angle (8-10 rock-faced courses!)
                sc.render.resolution_x = 1000
                sc.render.resolution_y = 1600
                cm.location = Vector((-14.2, 5.2, 9.6))
                cm.data.lens = 48.0
                cm.rotation_euler = (Vector((-3.8, 1.8, 9.8)) - cm.location).to_track_quat("-Z", "Y").to_euler()
                p_stone_cl = os.path.join(out_dir, "stone_detail_closeup.png")
                bake.render_still_safe(sc, p_stone_cl)
                shots["stone_detail_closeup"] = p_stone_cl

                # Top Crown Close-Up verifying planar 18-slab coping crown & central capstone (zero pinch!)
                sc.render.resolution_x = 1200
                sc.render.resolution_y = 1000
                cm.location = Vector((-9.5, 4.2, 26.5))
                cm.data.lens = 50.0
                cm.rotation_euler = (Vector((0.0, 0.0, 17.8)) - cm.location).to_track_quat("-Z", "Y").to_euler()
                p_top = os.path.join(out_dir, "baked_top_closeup.png")
                bake.render_still_safe(sc, p_top)
                shots["baked_top_closeup"] = p_top

                # Bottom Underside Close-Up verifying planar granite footing & foundation slab (zero radial stretch!)
                # Temporarily hide studio floor & add soft underbody fill light so the underside texture is fully lit!
                floor_obs = [o for o in st.objects if o.type == "MESH"]
                for fo in floor_obs:
                    fo.hide_render = True
                ld_u = bpy.data.lights.new("UnderFill", type="AREA")
                ld_u.energy = 16000.0
                ld_u.size = 24.0
                lo_u = bpy.data.objects.new("UnderFill", ld_u)
                lo_u.location = Vector((-4.0, 4.0, -14.0))
                lo_u.rotation_euler = (Vector((0.0, 0.0, 0.0)) - lo_u.location).to_track_quat("-Z", "Y").to_euler()
                st.objects.link(lo_u)
                cm.location = Vector((-16.5, 9.5, -13.5))
                cm.data.lens = 42.0
                cm.rotation_euler = (Vector((0.0, 0.0, 0.8)) - cm.location).to_track_quat("-Z", "Y").to_euler()
                p_bot = os.path.join(out_dir, "baked_bottom_closeup.png")
                bake.render_still_safe(sc, p_bot)
                shots["baked_bottom_closeup"] = p_bot
                st.objects.unlink(lo_u)
                bpy.data.objects.remove(lo_u)
                bpy.data.lights.remove(ld_u)
                for fo in floor_obs:
                    fo.hide_render = False

                # Eye-level Perspective Match (3:2 aspect matching exact un-cropped framing of ref_side_NSkuanBlZw.jpg!)
                sc.render.resolution_x = 1200
                sc.render.resolution_y = 800
                cm.location = Vector((-40.5, 0.0, 9.0))
                cm.data.lens = 42.0
                cm.data.clip_end = 300.0
                cm.rotation_euler = (Vector((0.0, 0.0, 8.95)) - cm.location).to_track_quat("-Z", "Y").to_euler()
                p_persp = os.path.join(out_dir, "baked_ref_perspective.png")
                bake.render_still_safe(sc, p_persp)
                shots["baked_ref_perspective"] = p_persp

                ref_jpg = os.path.join(THIS_DIR, "references", "ref_side_NSkuanBlZw.jpg")
                comp_p = _compose_baked_photo_comparison(ref_jpg, p_persp, os.path.join(out_dir, "baked_photo_comparison.png"))
                if comp_p:
                    shots["baked_photo_comparison"] = comp_p
        finally:
            core.clear_collection(st)
            bpy.data.collections.remove(st)

    # All 4 Variants Un-Cropped Echelon Lineup facing -X
    y_offsets = {
        "reference_match": -32.25,
        "vermont_granite": -10.75,
        "indiana_limestone": 10.75,
        "volcanic_basalt": 32.25,
    }
    x_offsets = {
        "reference_match": 0.0,
        "vermont_granite": 2.4,
        "indiana_limestone": 4.8,
        "volcanic_basalt": 7.2,
    }
    lineup_meshes = []
    for vid, vcol in variant_cols.items():
        vcol.hide_render = False
        vcol.hide_viewport = False
        dx, dy = x_offsets[vid], y_offsets[vid]
        for o in vcol.objects:
            o.location.x += dx
            o.location.y += dy
            if o.type == "MESH":
                lineup_meshes.append(o)
    bpy.context.view_layer.update()

    st_line = render.setup_studio(lineup_meshes, backdrop="product")
    cd = bpy.data.cameras.new("MEM_LineupCam")
    cm = bpy.data.objects.new("MEM_LineupCam", cd)
    st_line.objects.link(cm)
    sc.camera = cm
    try:
        sc.render.resolution_x = 2000
        sc.render.resolution_y = 1125
        cm.location = Vector((-106.0, -14.0, 25.5))
        cm.data.lens = 38.0
        cm.data.clip_end = 500.0
        cm.rotation_euler = (Vector((3.6, 0.0, 8.2)) - cm.location).to_track_quat("-Z", "Y").to_euler()
        p_lineup = os.path.join(out_dir, "variants_lineup.png")
        bake.render_still_safe(sc, p_lineup)
        shots["variants_lineup"] = p_lineup
    finally:
        core.clear_collection(st_line)
        bpy.data.collections.remove(st_line)

    for vid, vcol in variant_cols.items():
        dx, dy = x_offsets[vid], y_offsets[vid]
        for o in vcol.objects:
            o.location.x -= dx
            o.location.y -= dy
    bpy.context.view_layer.update()

    # 4-Panel `LOD0`..`LOD3` Comparison Sheet (2x2 grid — full un-cropped monument curb-to-cap!)
    for vcol in variant_cols.values():
        vcol.hide_render = True
    lod_tiles = []
    for lbl, lcol in lod_cols:
        for _l2, lc2 in lod_cols:
            lc2.hide_render = lc2 != lcol
        l_meshes = core.objects_in(lcol, types=("MESH",))
        st_l = render.setup_studio(l_meshes, backdrop="product")
        cd = bpy.data.cameras.new("MEM_LODCam")
        cm = bpy.data.objects.new("MEM_LODCam", cd)
        st_l.objects.link(cm)
        sc.camera = cm
        try:
            sc.render.resolution_x = 960
            sc.render.resolution_y = 600
            sc.cycles.samples = 48
            render.frame_camera(cm, l_meshes, (-0.90, 0.34, 0.24), lens=45.0, margin=0.92, aspect=960 / 600)
            tp = os.path.join(tempfile.gettempdir(), f"__vf_mem_lod_{os.getpid()}_{lbl}.png")
            sc.render.filepath = tp
            bpy.ops.render.render(write_still=True)
            im = bpy.data.images.load(tp)
            px = np.zeros(960 * 600 * 4, dtype=np.float32)
            im.pixels.foreach_get(px)
            bpy.data.images.remove(im)
            os.remove(tp)
            lod_tiles.append((lbl, px.reshape((600, 960, 4))))
        finally:
            core.clear_collection(st_l)
            bpy.data.collections.remove(st_l)

    if len(lod_tiles) == 4:
        grid = np.ones((1200, 1920, 4), dtype=np.float32)
        grid[600:1200, 0:960] = lod_tiles[0][1]
        grid[600:1200, 960:1920] = lod_tiles[1][1]
        grid[0:600, 0:960] = lod_tiles[2][1]
        grid[0:600, 960:1920] = lod_tiles[3][1]
        grid[598:602, :, :3] = 0.14
        grid[:, 958:962, :3] = 0.14
        p_lod = os.path.join(out_dir, "lod_comparison_sheet.png")
        bake.save_png_8bit(grid, p_lod, "sRGB")
        shots["lod_sheet"] = p_lod

    final_y = {
        "reference_match": 0.0,
        "vermont_granite": 22.0,
        "indiana_limestone": 44.0,
        "volcanic_basalt": 66.0,
    }
    for vid, vcol in variant_cols.items():
        vcol.hide_render = False
        vcol.hide_viewport = False
        for o in vcol.objects:
            o.location.y += final_y[vid]
    for _lbl, lcol in lod_cols[1:]:
        lcol.hide_render = True
        lcol.hide_viewport = True
    bpy.context.view_layer.update()

    return shots


# ---------------------------------------------------------------------------
# Main Entrypoint
# ---------------------------------------------------------------------------
def main() -> int:
    builder.clear_scene_and_setup_units()

    variant_cols: dict[str, bpy.types.Collection] = {}
    variant_meta: dict[str, dict] = {}
    flagship_parts: dict[str, bpy.types.Object] = {}
    lod_summary: dict[str, dict] = {}
    cached_ao: np.ndarray | None = None

    for idx, var in enumerate(VARIANTS):
        vid = var["id"]
        v_col, meshes = builder.build_all(
            collection_name=f"Variant_{vid}",
            clear_scene=False,
            palette_override=var["palette"],
            mat_prefix=f"Mem_{vid}_",
        )
        for o in meshes:
            o.name = f"Memorial_{vid}_{o['sc_part']}"
            o.data.name = o.name
        part_objs = {o["sc_part"]: o for o in meshes}

        pack_shared_memorial_atlas(part_objs)

        tex_dir = os.path.join(TEXTURES_ROOT, vid)
        baked_mat, tex_paths, cached_ao = bake_memorial_pbr_maps(
            vid, part_objs, tex_dir, cached_ao=cached_ao, res=BAKE_RES
        )

        if idx == 0:
            flagship_parts = part_objs
            lod_summary = lod.build_lod_chain(
                flagship_parts,
                LODS_ROOT,
                "memorial",
                collection_prefix="Memorial",
            )

            flagship_glb = os.path.join(THIS_DIR, "memorial.glb")
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            for pob in flagship_parts.values():
                pob.select_set(True)
            bpy.context.view_layer.objects.active = flagship_parts["Memorial"]
            bpy.ops.export_scene.gltf(filepath=flagship_glb, use_selection=True, export_format="GLB", export_apply=True)
            for pob in flagship_parts.values():
                pob.select_set(False)

        v_out_dir = os.path.join(VARIANTS_ROOT, vid)
        extra_mf = {
            "asset": "Memorial",
            "monument": "Pan Am Flight 103 Memorial Cairn (Arlington National Cemetery)",
            "variant": vid,
            "variantLabel": var["label"],
            "edition": var["edition"],
            "heightMeters": builder.TOTAL_HEIGHT,
            "bakeResolution": BAKE_RES,
            "lods": lod_summary,
        }
        export_memorial_variant_bundle(var, v_col, part_objs, baked_mat, tex_paths, v_out_dir, extra_manifest=extra_mf)

        if idx == 0:
            export_memorial_variant_bundle(var, v_col, part_objs, baked_mat, tex_paths, EXPORT_DEFAULT, extra_manifest=extra_mf)

        variant_cols[vid] = v_col
        variant_meta[vid] = {
            "label": var["label"],
            "edition": var["edition"],
            "dir": f"variants/{vid}",
            "glb": f"variants/{vid}/memorial_{vid}.glb",
            "textures": {k: f"textures/{vid}/{os.path.basename(p)}" for k, p in tex_paths.items()},
        }

    lod_cols = [
        ("LOD0", variant_cols["reference_match"]),
        ("LOD1", bpy.data.collections["Memorial_LOD1"]),
        ("LOD2", bpy.data.collections["Memorial_LOD2"]),
        ("LOD3", bpy.data.collections["Memorial_LOD3"]),
    ]

    shots = render_showcase_suite(variant_cols, lod_cols, RENDERS_ROOT)

    master_blend = os.path.join(THIS_DIR, "memorial_variants_lods.blend")
    bpy.ops.wm.save_as_mainfile(filepath=master_blend)

    os.makedirs(DESIGN_OUTPUT_DIR, exist_ok=True)
    shutil.copy2(master_blend, os.path.join(DESIGN_OUTPUT_DIR, "memorial.blend"))
    shutil.copy2(os.path.join(THIS_DIR, "memorial.glb"), os.path.join(DESIGN_OUTPUT_DIR, "memorial.glb"))
    shutil.copy2(shots["variants_lineup"], os.path.join(DESIGN_OUTPUT_DIR, "blender-render-check.png"))

    report = {
        "ok": True,
        "asset": "memorial",
        "monument": "Pan Am Flight 103 Memorial Cairn (Arlington National Cemetery)",
        "height_m": builder.TOTAL_HEIGHT,
        "bake_res": BAKE_RES,
        "lods": lod_summary,
        "variants": variant_meta,
        "renders": {k: os.path.relpath(v, THIS_DIR).replace("\\", "/") for k, v in shots.items()},
    }
    rep_path = os.path.join(THIS_DIR, "variants_and_lods_report.json")
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    core.log(f"DONE! Unified 2-object Memorial 2K PBR bake + 4 variants + 4-tier LODs -> {rep_path}")
    return 0


def rerender_from_saved_blend() -> int:
    master_blend = os.path.join(THIS_DIR, "memorial_variants_lods.blend")
    bpy.ops.wm.open_mainfile(filepath=master_blend)
    variant_cols = {v["id"]: bpy.data.collections[f"Variant_{v['id']}"] for v in VARIANTS}
    for vcol in variant_cols.values():
        for o in vcol.objects:
            o.location = Vector((0.0, 0.0, 0.0))
    bpy.context.view_layer.update()

    lod_cols = [
        ("LOD0", variant_cols["reference_match"]),
        ("LOD1", bpy.data.collections["Memorial_LOD1"]),
        ("LOD2", bpy.data.collections["Memorial_LOD2"]),
        ("LOD3", bpy.data.collections["Memorial_LOD3"]),
    ]
    shots = render_showcase_suite(variant_cols, lod_cols, RENDERS_ROOT)
    bpy.ops.wm.save_as_mainfile(filepath=master_blend)
    os.makedirs(DESIGN_OUTPUT_DIR, exist_ok=True)
    shutil.copy2(master_blend, os.path.join(DESIGN_OUTPUT_DIR, "memorial.blend"))
    shutil.copy2(shots["variants_lineup"], os.path.join(DESIGN_OUTPUT_DIR, "blender-render-check.png"))
    return 0


if __name__ == "__main__":
    if "--rerender" in sys.argv:
        raise SystemExit(rerender_from_saved_blend())
    raise SystemExit(main())
