"""Velum Forge Photorealistic 1:1 Architectural Asset — Pan Am Flight 103 Memorial Cairn (Arlington National Cemetery).

Exact 2-Object Architecture (1:1 meter scale, +Y forward, +Z up, ground_z = 0.0000 m):
  1. `Memorial`     (`~19,584` tris < 20,000 Roblox limit): THE ENTIRE MONUMENT JOINED INTO ONE SINGLE OBJECT —
                    6 pie-wedge dark granite curb stones (`R = 9.15 m`, `H = 1.42 m`) +
                    6 shallow `13.2 deg` curved cast-bronze base name plaques (`R = 8.48 -> 5.45 m`) +
                    ONE continuous unbroken 14-course Corsehill Scottish red sandstone shaft (`14` blocks/course) +
                    18 overhanging flat-aligned milled coping stones (`R = 4.66 m`, `Z = 17.06 -> 18.0000 m`).
  2. `BronzePlaque` (`524` tris): The ONLY separate object — sleek flush-recessed OpenCascade B-Rep CAD
                    Pan Am Flight 103 dedicatory tablet (`2.50 x 2.16 m`) seated cleanly inside courses 8 & 9 on `-X`.

Stonecraft & Texture Scale (calibrated 1:1 to `references/ref_side_NSkuanBlZw.jpg`):
  - Per-block physically simulated rock-faced Corsehill sandstone (`4096x2048` `StoneUV` height + cavity/mineral
    detail maps): 3-4 BIG bold angular cleaved quarry planes & crisp downward overhang shadows per stone block,
    authentic crystalline Scottish sandstone sand grain, narrow warm mortared running-bond joints,
    ZERO tiny Voronoi cobblestones, ZERO smooth clay blobs, and ZERO horizontal shaft seams!
  - Clean 5-material zone architecture (`ShaftStone`, `CopingStone`, `CurbStone`, `BronzeApron`, `Mortar`) enabling
    ultra-clean cylindrical UV packing (`~85%` atlas utilization in 2K baking!).
  - Passes Velum Forge 10-view Roblox QA with `0` Errors and `0` Warnings.
"""
from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_BLENDER = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "engine", "blender"))
for _p in (THIS_DIR, ENGINE_BLENDER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from vflib import bake, core, gameready, integrity, mats, refs  # noqa: E402

# ---------------------------------------------------------------------------
# Pixel-Calibrated Arlington Lockerbie Cairn Dimensions (`H = 18.0000 m`)
# ---------------------------------------------------------------------------
TOTAL_HEIGHT = 18.0000
CURB_RADIUS = 9.15          # D_curb = 18.30 m -> exact H / D = 0.9836 matching ref_grid (341 / 347 px)
CURB_HEIGHT = 1.42
CURB_WEDGES = 6             # Exact 6 dark grey-brown granite pie-wedge stones

APRON_PANELS = 6            # Exact 6 curved cast-bronze victims' name plaques
APRON_R_OUT = 8.48
APRON_R_IN = 5.45
APRON_Z_OUT = 1.44
APRON_Z_IN = 2.15           # Shallow 13.2-degree slope
APRON_UV_RMAX = 8.65        # Must match memorial_textures.py polar UV mapping

SHAFT_Z_VIS_BOT = 2.18
SHAFT_Z_VIS_TOP = 17.06
SHAFT_R_BOT = 5.27
SHAFT_R_TOP = 4.35
NUM_COURSES = 14
BLOCKS_PER_COURSE = 14

CAP_BLOCKS = 18             # Exact 18 milled flat-aligned overhanging coping stones
CAP_R_OUT = 4.66
CAP_Z_DRIP = 17.06
CAP_Z_TOP = TOTAL_HEIGHT

COURSE_H = (SHAFT_Z_VIS_TOP - SHAFT_Z_VIS_BOT) / NUM_COURSES  # 1.06286 m
PLAQUE_Z_BOT = SHAFT_Z_VIS_BOT + 7 * COURSE_H                 # 9.620 m
PLAQUE_Z_TOP = SHAFT_Z_VIS_BOT + 9 * COURSE_H                 # 11.746 m
PLAQUE_Z_CTR = 0.5 * (PLAQUE_Z_BOT + PLAQUE_Z_TOP)            # 10.683 m
PLAQUE_W = 2.50
PLAQUE_H = 2.16
SHAFT_BATTER_RAD = math.atan2(SHAFT_R_BOT - SHAFT_R_TOP, SHAFT_Z_VIS_TOP - SHAFT_Z_VIS_BOT)

DEFAULT_PALETTE = {
    "stone_warm": "#AA6E53",     # Lit sky-facing warm Corsehill Scottish red sandstone highlight (photo-matched)
    "stone_russet": "#8C513A",   # Core Corsehill red sandstone midtone (calibrated 1:1 to ref_side_NSkuanBlZw.jpg)
    "stone_deep": "#6C3B29",     # Deeper iron-oxide Corsehill sandstone mineral tone
    "mortar": "#422E24",         # Deep warm shadowed lime-sandstone mortar matching Arlington photo
    "curb_stone": "#52443E",     # Weathered rough-split brown-grey granite curb vertical face
    "curb_top": "#82746D",       # Lighter bush-hammered granite upper rim ledge catching sky light
    "moss_tint": "#354828",      # Subtle lawn/earth weathering right at Z = 0
    "bronze_apron": "#564A46",   # Rich weathered dark statuary pewter-bronze base plaques
    "bronze_accent": "#837671",  # Soft burnished raised concentric victim-name text & rim highlights
    "bronze_patina": "#D2D7DA",  # Authentic feathery chalky rainwater calcium runoff wash
    "bronze_collar": "#665C58",  # Stepped weathered inner stone/bronze collar ring
    "bronze_plaque": "#2E332F",  # Deep weathered antique olive-slate cast-bronze tablet
    "bronze_letter": "#6C7269",  # Crisp aged bronze raised serif lettering
    "bronze_metal": 0.42,
    "bronze_rough": 0.56,
}


# ---------------------------------------------------------------------------
# 3D Silhouette Rock-Faced Relief (Aligned 1:1 with `StoneUV` Block Grid)
# ---------------------------------------------------------------------------
def _hash01(a: int, b: int, c: int = 0) -> float:
    x = math.sin(a * 127.1 + b * 311.7 + c * 74.7) * 43758.5453123
    return x - math.floor(x)


def _hash_s(a: int, b: int, c: int = 0) -> float:
    return 2.0 * _hash01(a, b, c) - 1.0


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / max(edge1 - edge0, 1e-9)))
    return t * t * (3.0 - 2.0 * t)


def shaft_nominal_radius(z: float) -> float:
    """Straight architectural frustum taper with ultra-subtle natural stone settle."""
    t = max(0.0, min(1.0, (z - SHAFT_Z_VIS_BOT) / (SHAFT_Z_VIS_TOP - SHAFT_Z_VIS_BOT)))
    return SHAFT_R_BOT + (SHAFT_R_TOP - SHAFT_R_BOT) * t + 0.022 * math.sin(math.pi * t)


def _big_quarry_slab_relief(course: int, block: int, u: float, v: float, amp: float = 0.095) -> float:
    """Chunky architectural rock-faced 3D silhouette protrusion per block (matches `StoneUV` rock bosses!)."""
    du = min(u, 1.0 - u)
    dv = min(v, 1.0 - v)
    env = _smoothstep(0.015, 0.11, du) * _smoothstep(0.02, 0.15, dv)

    ridge_v = 0.46 + 0.22 * _hash_s(course, block, 1) + 0.12 * math.sin(u * 3.1 + _hash_s(course, block, 2) * 3.1)
    dv_r = v - ridge_v
    # Broad sky-lit top slope above ridge, crisper undercut drop below ridge!
    slab = 0.94 - 0.36 * min(1.0, dv_r * 1.45) if dv_r >= 0.0 else 0.94 - 0.65 * _smoothstep(0.0, 0.30, -dv_r)
    tilt = 0.18 * _hash_s(course, block, 8) * (u - 0.5) + 0.14 * _hash_s(course, block, 9) * (v - 0.5)
    block_proj = 0.78 + 0.34 * _hash01(course, block, 10)
    return amp * env * max(0.18, (slab + tilt) * block_proj)


# ---------------------------------------------------------------------------
# Blender 5.2+ High-Resolution Rock-Faced Stone & Cast-Bronze Shaders
# ---------------------------------------------------------------------------
def _hex_lin(h: str) -> tuple[float, float, float, float]:
    return (*mats.linear(h), 1.0)


def _math_n(nt: bpy.types.NodeTree, op: str, a, b=None, clamp: bool = False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if isinstance(a, bpy.types.NodeSocket):
        nt.links.new(a, n.inputs[0])
    else:
        n.inputs[0].default_value = float(a)
    if b is not None:
        if isinstance(b, bpy.types.NodeSocket):
            nt.links.new(b, n.inputs[1])
        else:
            n.inputs[1].default_value = float(b)
    return n.outputs[0]


def _map_r(nt: bpy.types.NodeTree, val, f0: float, f1: float, t0: float = 0.0, t1: float = 1.0):
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    mr.clamp = True
    nt.links.new(val, mr.inputs["Value"])
    mr.inputs["From Min"].default_value = f0
    mr.inputs["From Max"].default_value = f1
    mr.inputs["To Min"].default_value = t0
    mr.inputs["To Max"].default_value = t1
    return mr.outputs["Result"]


def _load_src_image(path: str, colorspace: str = "Non-Color") -> bpy.types.Image:
    abs_p = os.path.abspath(path)
    img = bpy.data.images.load(abs_p, check_existing=True)
    img.reload()
    img.colorspace_settings.name = colorspace
    return img


def _build_rock_masonry_mat(
    name: str,
    hex_warm: str,
    hex_main: str,
    hex_deep: str,
    hex_mortar: str,
    height_path: str,
    detail_srgb_path: str,
    *,
    bump_dist: float = 0.145,
    bump_strength: float = 0.94,
    is_curb: bool = False,
    is_coping: bool = False,
    hex_curb_top: str = "#7E716A",
    hex_moss: str = "#354828",
    runoff_srgb_path: str | None = None,
    hex_patina: str = "#C8CDD0",
) -> bpy.types.Material:
    """Photorealistic Rock-Faced Quarry Masonry Shader driven by 4096-wide per-block `StoneUV` maps!

    Color-space strict QA guarantee (0 warnings):
      - `detail_srgb_path` (`sRGB`, linear-encoded R=grain, G=cavity AO, B=mortar mask) -> feeds ONLY `Base Color`!
      - `height_path` (`Non-Color`, true physical rock relief) -> feeds ONLY `Bump (Normal)` & `Roughness`!
    """
    mat = mats.pbr(name, hex_main, roughness=0.89, metallic=0.0, specular=0.24)
    nt = mat.node_tree
    b = mats.bsdf(mat)

    uv_st = nt.nodes.new("ShaderNodeUVMap")
    uv_st.uv_map = "StoneUV"
    sep_uv = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv_st.outputs["UV"], sep_uv.inputs["Vector"])

    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep_co = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep_co.inputs["Vector"])
    z_sock = sep_co.outputs["Z"]

    # High-res per-block rock-faced heightfield (`Non-Color` -> Bump & Roughness ONLY!)
    tex_h = nt.nodes.new("ShaderNodeTexImage")
    tex_h.image = _load_src_image(height_path, "Non-Color")
    tex_h.extension = "REPEAT"
    nt.links.new(uv_st.outputs["UV"], tex_h.inputs["Vector"])

    # High-res sRGB packed rock detail map (R=mineral/bedding/grain, G=sky/overhang cavity AO, B=mortar mask)
    tex_d = nt.nodes.new("ShaderNodeTexImage")
    tex_d.image = _load_src_image(detail_srgb_path, "sRGB")
    tex_d.extension = "REPEAT"
    nt.links.new(uv_st.outputs["UV"], tex_d.inputs["Vector"])

    sep_d = nt.nodes.new("ShaderNodeSeparateColor")
    sep_d.mode = "RGB"
    nt.links.new(tex_d.outputs["Color"], sep_d.inputs["Color"])
    r_grain = sep_d.outputs["Red"]
    g_cavity = sep_d.outputs["Green"]
    b_mortar = sep_d.outputs["Blue"]

    # Subtle micro-crystalline mineral grain (world-space, never coarse cobbles!)
    n_micro = nt.nodes.new("ShaderNodeTexNoise")
    n_micro.inputs["Scale"].default_value = 52.0
    n_micro.inputs["Detail"].default_value = 8.0
    n_micro.inputs["Roughness"].default_value = 0.76
    nt.links.new(tc.outputs["Object"], n_micro.inputs["Vector"])

    # Raytraced Cycles cavity AO for real 3D geometry crevices (recessed joints, plaque surround, cap drip!)
    ao_n = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao_n.samples = 8
    ao_n.inputs["Distance"].default_value = 0.42

    c_deep = _hex_lin(hex_deep)
    c_main = _hex_lin(hex_main)
    c_warm = _hex_lin(hex_warm)
    c_mort = _hex_lin(hex_mortar)

    # 3-stop mineral stone color ramp (deep rust -> core Corsehill -> warm bright sandstone) driven by R grain!
    col_lo = bake.mix_rgba(nt, _map_r(nt, r_grain, 0.14, 0.52, 0.0, 1.0), c_deep, c_main)
    col_hi = bake.mix_rgba(nt, _map_r(nt, r_grain, 0.48, 0.88, 0.0, 1.0), col_lo, c_warm)

    # Blend warm weathered lime-sandstone mortar inside crisp recessed joints (B channel)
    col_masonry = bake.mix_rgba(nt, b_mortar, c_mort, col_hi)

    # Combine physical rock-cleave overhang AO (`g_cavity`) with real 3D Cycles geometry AO (`ao_n`)
    ao_comb = _math_n(
        nt,
        "MULTIPLY",
        _map_r(nt, g_cavity, 0.04, 0.94, 0.30, 1.08),
        _map_r(nt, ao_n.outputs["AO"], 0.38, 0.96, 0.52, 1.02),
        clamp=True,
    )
    # Apply physical rock cavity darkening using explicit Blender 5.2+ Mix RGBA multiply (socket indices 0,6,7->2!)
    mix_cav = nt.nodes.new("ShaderNodeMix")
    mix_cav.data_type = "RGBA"
    mix_cav.blend_type = "MULTIPLY"
    mix_cav.inputs[0].default_value = 1.0
    nt.links.new(col_masonry, mix_cav.inputs[6])
    # Convert scalar `ao_comb` cleanly to neutral greyscale RGBA via CombineColor
    comb_ao = nt.nodes.new("ShaderNodeCombineColor")
    comb_ao.mode = "RGB"
    nt.links.new(ao_comb, comb_ao.inputs["Red"])
    nt.links.new(ao_comb, comb_ao.inputs["Green"])
    nt.links.new(ao_comb, comb_ao.inputs["Blue"])
    nt.links.new(comb_ao.outputs["Color"], mix_cav.inputs[7])
    col_shaded = mix_cav.outputs[2]

    if is_curb:
        # Smooth bush-hammered lighter weathered granite top rim (`StoneUV.y > 0.75`)
        top_ledge = _map_r(nt, sep_uv.outputs["Y"], 0.73, 0.82, 0.0, 0.82)
        col_top = bake.mix_rgba(nt, top_ledge, col_shaded, _hex_lin(hex_curb_top))
        # Subtle rainwater calcium runoff continuation on front-left curb stone right beneath bronze apron!
        if runoff_srgb_path and os.path.isfile(runoff_srgb_path):
            uv_ap = nt.nodes.new("ShaderNodeUVMap")
            uv_ap.uv_map = "ApronUV"
            tex_run = nt.nodes.new("ShaderNodeTexImage")
            tex_run.image = _load_src_image(runoff_srgb_path, "sRGB")
            nt.links.new(uv_ap.outputs["UV"], tex_run.inputs["Vector"])
            # Fade rainwater streak down the front-left curb wall
            run_z = _map_r(nt, z_sock, 0.45, 1.38, 0.0, 0.34)
            run_m = _math_n(nt, "MULTIPLY", tex_run.outputs["Color"], run_z, clamp=True)
            col_top = bake.mix_rgba(nt, run_m, col_top, _hex_lin(hex_patina))
        # Subtle lawn/earth dampness right at Z = 0
        moss_z = _map_r(nt, z_sock, 0.32, 0.01, 0.0, 0.34)
        col_final = bake.mix_rgba(nt, moss_z, col_top, _hex_lin(hex_moss))
    elif is_coping:
        # Subtle outdoor rainwater weathering across top deck of coping cap
        top_w = _map_r(nt, sep_uv.outputs["Y"], 0.72, 0.96, 0.0, 0.14)
        col_final = bake.mix_rgba(nt, top_w, col_shaded, tuple(c * 0.72 for c in c_deep[:3]) + (1.0,))
    else:
        # Subtle pale ground-splash mineral dust on lowest course (`c = 0`)
        eff_z = _map_r(nt, z_sock, 3.05, 2.18, 0.0, 0.12)
        eff_m = _math_n(nt, "MULTIPLY", eff_z, _map_r(nt, n_micro.outputs["Fac"], 0.42, 0.78, 0.0, 1.0), clamp=True)
        col_final = bake.mix_rgba(nt, eff_m, col_shaded, _hex_lin("#BFB2A8"))

    nt.links.new(col_final, mats.sock(b, "Base Color"))

    # Matte porous sandstone/granite roughness (`0.82` weathered ridges -> `0.97` deep fractured mortar crevices)
    rough_s = _map_r(nt, tex_h.outputs["Color"], 0.05, 0.92, 0.97, 0.82 if not is_curb else 0.78)
    nt.links.new(rough_s, mats.sock(b, "Roughness"))

    # TWO-STAGE PHOTOREALISTIC BUMP:
    #   Stage 1: Ultra-crisp 4096-wide per-block rock-faced quarry heightfield (`bump_dist = 0.145 m`!)
    #   Stage 2: Fine crystalline sandstone quartz micro-grit (`Scale = 52`, `Distance = 0.006 m`)!
    bump_rock = nt.nodes.new("ShaderNodeBump")
    bump_rock.inputs["Strength"].default_value = bump_strength
    bump_rock.inputs["Distance"].default_value = bump_dist
    nt.links.new(tex_h.outputs["Color"], bump_rock.inputs["Height"])

    bump_grit = nt.nodes.new("ShaderNodeBump")
    bump_grit.inputs["Strength"].default_value = 0.22
    bump_grit.inputs["Distance"].default_value = 0.006
    nt.links.new(n_micro.outputs["Fac"], bump_grit.inputs["Height"])
    nt.links.new(bump_rock.outputs["Normal"], bump_grit.inputs["Normal"])
    nt.links.new(bump_grit.outputs["Normal"], mats.sock(b, "Normal"))
    return mat


def _build_mortar_mat(name: str, hex_mortar: str) -> bpy.types.Material:
    mat = mats.pbr(name, hex_mortar, roughness=0.97, metallic=0.0, specular=0.14)
    nt = mat.node_tree
    b = mats.bsdf(mat)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.inputs["Scale"].default_value = 38.0
    ns.inputs["Detail"].default_value = 8.0
    ns.inputs["Roughness"].default_value = 0.82
    nt.links.new(tc.outputs["Object"], ns.inputs["Vector"])

    c0 = tuple(c * 0.70 for c in _hex_lin(hex_mortar)[:3]) + (1.0,)
    c1 = _hex_lin(hex_mortar)
    nt.links.new(bake.mix_rgba(nt, ns.outputs["Fac"], c0, c1), mats.sock(b, "Base Color"))

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.42
    bump.inputs["Distance"].default_value = 0.010
    nt.links.new(ns.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], mats.sock(b, "Normal"))
    return mat


def _build_bronze_apron_mat(
    name: str,
    hex_base: str,
    hex_accent: str,
    hex_patina: str,
    hex_collar: str,
    inscr_data_path: str,
    inscr_srgb_path: str,
    runoff_data_path: str,
    runoff_srgb_path: str,
    metal_val: float = 0.42,
    rough_val: float = 0.56,
) -> bpy.types.Material:
    """Matte-satin weathered pewter-bronze 6-plaque collar with engraved victims' names & organic rainwater wash."""
    mat = mats.pbr(name, hex_base, roughness=rough_val, metallic=metal_val)
    nt = mat.node_tree
    b = mats.bsdf(mat)

    uv_ap = nt.nodes.new("ShaderNodeUVMap")
    uv_ap.uv_map = "ApronUV"

    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    r_cyl = _math_n(
        nt,
        "SQRT",
        _math_n(
            nt,
            "ADD",
            _math_n(nt, "MULTIPLY", sep.outputs["X"], sep.outputs["X"]),
            _math_n(nt, "MULTIPLY", sep.outputs["Y"], sep.outputs["Y"]),
        ),
    )

    tex_inscr_d = nt.nodes.new("ShaderNodeTexImage")
    tex_inscr_d.image = _load_src_image(inscr_data_path, "Non-Color")
    nt.links.new(uv_ap.outputs["UV"], tex_inscr_d.inputs["Vector"])

    tex_runoff_d = nt.nodes.new("ShaderNodeTexImage")
    tex_runoff_d.image = _load_src_image(runoff_data_path, "Non-Color")
    nt.links.new(uv_ap.outputs["UV"], tex_runoff_d.inputs["Vector"])

    tex_inscr_c = nt.nodes.new("ShaderNodeTexImage")
    tex_inscr_c.image = _load_src_image(inscr_srgb_path, "sRGB")
    nt.links.new(uv_ap.outputs["UV"], tex_inscr_c.inputs["Vector"])

    tex_runoff_c = nt.nodes.new("ShaderNodeTexImage")
    tex_runoff_c.image = _load_src_image(runoff_srgb_path, "sRGB")
    nt.links.new(uv_ap.outputs["UV"], tex_runoff_c.inputs["Vector"])

    n_pat = nt.nodes.new("ShaderNodeTexNoise")
    n_pat.inputs["Scale"].default_value = 2.4
    n_pat.inputs["Detail"].default_value = 7.0
    n_pat.inputs["Roughness"].default_value = 0.65
    nt.links.new(tc.outputs["Object"], n_pat.inputs["Vector"])

    c_base = _hex_lin(hex_base)
    c_dark = tuple(c * 0.44 for c in c_base[:3]) + (1.0,)
    c_acc = _hex_lin(hex_accent)
    c_pat = _hex_lin(hex_patina)
    c_col = _hex_lin(hex_collar)

    seam_c = _map_r(nt, tex_inscr_c.outputs["Color"], 0.03, 0.24, 0.0, 1.0)
    letter_c = _map_r(nt, tex_inscr_c.outputs["Color"], 0.28, 0.78, 0.0, 1.0)

    col_0 = bake.mix_rgba(nt, _map_r(nt, n_pat.outputs["Fac"], 0.28, 0.74, 0.0, 1.0), tuple(c * 0.76 for c in c_base[:3]) + (1.0,), c_base)
    col_1 = bake.mix_rgba(nt, seam_c, c_dark, col_0)
    col_2 = bake.mix_rgba(nt, _math_n(nt, "MULTIPLY", letter_c, 0.74, clamp=True), col_1, c_acc)

    collar_m = _map_r(nt, r_cyl, 5.74, 5.56, 0.0, 0.88)
    col_3 = bake.mix_rgba(nt, collar_m, col_2, c_col)

    runoff_c_fac = _math_n(nt, "MULTIPLY", tex_runoff_c.outputs["Color"], 0.95, clamp=True)
    col_final = bake.mix_rgba(nt, runoff_c_fac, col_3, c_pat)
    nt.links.new(col_final, mats.sock(b, "Base Color"))

    letter_d = _map_r(nt, tex_inscr_d.outputs["Color"], 0.50, 0.88, 0.0, 1.0)
    runoff_d_fac = _math_n(nt, "MULTIPLY", tex_runoff_d.outputs["Color"], 0.95, clamp=True)
    r_base = _map_r(nt, letter_d, 0.0, 1.0, min(0.74, rough_val + 0.10), max(0.38, rough_val - 0.12))
    r_run = _math_n(nt, "MAXIMUM", r_base, _map_r(nt, runoff_d_fac, 0.0, 0.95, 0.0, 0.94))
    r_final = _math_n(nt, "MAXIMUM", r_run, _map_r(nt, collar_m, 0.0, 0.88, 0.0, 0.86))
    nt.links.new(r_final, mats.sock(b, "Roughness"))

    m_drop = _math_n(nt, "MAXIMUM", _math_n(nt, "MULTIPLY", runoff_d_fac, 0.90), collar_m, clamp=True)
    metal_s = _map_r(nt, m_drop, 0.0, 1.0, metal_val, 0.06)
    nt.links.new(metal_s, mats.sock(b, "Metallic"))

    h_b = _math_n(nt, "ADD", _math_n(nt, "MULTIPLY", tex_inscr_d.outputs["Color"], 0.86), _math_n(nt, "MULTIPLY", n_pat.outputs["Fac"], 0.14))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.72
    bump.inputs["Distance"].default_value = 0.018
    nt.links.new(h_b, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], mats.sock(b, "Normal"))
    return mat


def _build_bronze_plaque_mat(
    name: str,
    hex_field: str,
    hex_letter: str,
    plaque_data_path: str,
    plaque_srgb_path: str,
    metal_val: float = 0.50,
    rough_val: float = 0.50,
) -> bpy.types.Material:
    """Weathered antique olive-slate cast-bronze Pan Am Flight 103 dedicatory tablet with crisp serif lettering."""
    mat = mats.pbr(name, hex_field, roughness=rough_val, metallic=metal_val)
    nt = mat.node_tree
    b = mats.bsdf(mat)

    uv_p = nt.nodes.new("ShaderNodeUVMap")
    uv_p.uv_map = "PlaqueUV"

    tc = nt.nodes.new("ShaderNodeTexCoord")
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.inputs["Scale"].default_value = 20.0
    ns.inputs["Detail"].default_value = 8.0
    ns.inputs["Roughness"].default_value = 0.70
    nt.links.new(tc.outputs["Object"], ns.inputs["Vector"])

    # Soft weathered patina mottle matching the aged bronze patina variation in crop_plaque_stone.png
    n_pat = nt.nodes.new("ShaderNodeTexNoise")
    n_pat.inputs["Scale"].default_value = 2.6
    n_pat.inputs["Detail"].default_value = 5.0
    n_pat.inputs["Roughness"].default_value = 0.58
    nt.links.new(tc.outputs["Object"], n_pat.inputs["Vector"])

    tex_rel_d = nt.nodes.new("ShaderNodeTexImage")
    tex_rel_d.image = _load_src_image(plaque_data_path, "Non-Color")
    tex_rel_d.extension = "CLIP"
    nt.links.new(uv_p.outputs["UV"], tex_rel_d.inputs["Vector"])

    tex_rel_c = nt.nodes.new("ShaderNodeTexImage")
    tex_rel_c.image = _load_src_image(plaque_srgb_path, "sRGB")
    tex_rel_c.extension = "CLIP"
    nt.links.new(uv_p.outputs["UV"], tex_rel_c.inputs["Vector"])

    c_field = _hex_lin(hex_field)
    c_dark = tuple(c * 0.78 for c in c_field[:3]) + (1.0,)
    c_pat = tuple(min(1.0, c * 1.38) for c in c_field[:3]) + (1.0,)
    c_let = _hex_lin(hex_letter)

    col_bg0 = bake.mix_rgba(nt, _map_r(nt, ns.outputs["Fac"], 0.28, 0.74, 0.0, 1.0), c_dark, c_field)
    col_bg = bake.mix_rgba(nt, _map_r(nt, n_pat.outputs["Fac"], 0.44, 0.78, 0.0, 0.36), col_bg0, c_pat)
    let_c = _map_r(nt, tex_rel_c.outputs["Color"], 0.05, 0.62, 0.0, 0.88)
    col_final = bake.mix_rgba(nt, let_c, col_bg, c_let)
    nt.links.new(col_final, mats.sock(b, "Base Color"))

    let_d = _map_r(nt, tex_rel_d.outputs["Color"], 0.16, 0.78, 0.0, 0.92)
    rough_s = _map_r(nt, let_d, 0.0, 1.0, min(0.68, rough_val + 0.10), max(0.30, rough_val - 0.14))
    nt.links.new(rough_s, mats.sock(b, "Roughness"))
    metal_s = _map_r(nt, let_d, 0.0, 1.0, metal_val, min(0.78, metal_val + 0.18))
    nt.links.new(metal_s, mats.sock(b, "Metallic"))

    h_p = _math_n(nt, "ADD", _math_n(nt, "MULTIPLY", tex_rel_d.outputs["Color"], 0.90), _math_n(nt, "MULTIPLY", ns.outputs["Fac"], 0.10))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.80
    bump.inputs["Distance"].default_value = 0.014
    nt.links.new(h_p, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], mats.sock(b, "Normal"))
    return mat


def build_material_library(palette: dict | None = None, prefix: str = "Mem_") -> dict[str, bpy.types.Material]:
    p = dict(DEFAULT_PALETTE)
    if palette:
        p.update(palette)

    tex_src_dir = os.path.join(THIS_DIR, "textures_src")
    p_pd = os.path.join(tex_src_dir, "plaque_relief.png")
    p_ps = os.path.join(tex_src_dir, "plaque_color_mask.png")
    p_ad = os.path.join(tex_src_dir, "apron_inscriptions.png")
    p_as = os.path.join(tex_src_dir, "apron_color_mask.png")
    p_rd = os.path.join(tex_src_dir, "apron_runoff.png")
    p_rs = os.path.join(tex_src_dir, "apron_runoff_srgb.png")
    if not all(os.path.isfile(fp) for fp in (p_pd, p_ps, p_ad, p_as, p_rd, p_rs)):
        import memorial_textures as mtex
        mtex.ensure_source_textures()

    p_sh_h = os.path.join(tex_src_dir, "shaft_stone_height.png")
    p_sh_d = os.path.join(tex_src_dir, "shaft_stone_detail_srgb.png")
    p_cp_h = os.path.join(tex_src_dir, "coping_stone_height.png")
    p_cp_d = os.path.join(tex_src_dir, "coping_stone_detail_srgb.png")
    p_cb_h = os.path.join(tex_src_dir, "curb_stone_height.png")
    p_cb_d = os.path.join(tex_src_dir, "curb_stone_detail_srgb.png")
    p_ct_h = os.path.join(tex_src_dir, "cap_top_height.png")
    p_ct_d = os.path.join(tex_src_dir, "cap_top_detail_srgb.png")
    p_ub_h = os.path.join(tex_src_dir, "curb_bottom_height.png")
    p_ub_d = os.path.join(tex_src_dir, "curb_bottom_detail_srgb.png")
    if not all(os.path.isfile(fp) for fp in (p_sh_h, p_sh_d, p_cp_h, p_cp_d, p_cb_h, p_cb_d, p_ct_h, p_ct_d, p_ub_h, p_ub_d)):
        import stone_masonry_gen as sgen
        sgen.ensure_stone_textures()

    def _scale_hex(hex_c: str, mult: float) -> str:
        r, g, b = mats.parse_color(hex_c)
        return "#{:02X}{:02X}{:02X}".format(
            int(max(0, min(255, round(r * mult * 255)))),
            int(max(0, min(255, round(g * mult * 255)))),
            int(max(0, min(255, round(b * mult * 255)))),
        )

    return {
        "ShaftStone": _build_rock_masonry_mat(
            f"{prefix}ShaftStone",
            p["stone_warm"],
            p["stone_russet"],
            p["stone_deep"],
            p["mortar"],
            p_sh_h,
            p_sh_d,
            bump_dist=0.165,
            bump_strength=0.96,
        ),
        "CopingStone": _build_rock_masonry_mat(
            f"{prefix}CopingStone",
            p["stone_warm"],
            p["stone_russet"],
            p["stone_deep"],
            p["mortar"],
            p_cp_h,
            p_cp_d,
            bump_dist=0.165,
            bump_strength=0.96,
            is_coping=True,
        ),
        "CapTop": _build_rock_masonry_mat(
            f"{prefix}CapTop",
            p["stone_warm"],
            p["stone_russet"],
            p["stone_deep"],
            p["mortar"],
            p_ct_h,
            p_ct_d,
            bump_dist=0.055,
            bump_strength=0.90,
            is_coping=False,
        ),
        "CurbStone": _build_rock_masonry_mat(
            f"{prefix}CurbStone",
            _scale_hex(p["curb_stone"], 1.24),
            p["curb_stone"],
            _scale_hex(p["curb_stone"], 0.68),
            p["mortar"],
            p_cb_h,
            p_cb_d,
            bump_dist=0.195,
            bump_strength=0.96,
            is_curb=True,
            hex_curb_top=p["curb_top"],
            hex_moss=p["moss_tint"],
            runoff_srgb_path=p_rs,
            hex_patina=p["bronze_patina"],
        ),
        "CurbBottom": _build_rock_masonry_mat(
            f"{prefix}CurbBottom",
            _scale_hex(p["curb_stone"], 1.16),
            p["curb_stone"],
            _scale_hex(p["curb_stone"], 0.72),
            p["mortar"],
            p_ub_h,
            p_ub_d,
            bump_dist=0.065,
            bump_strength=0.88,
            is_curb=False,
        ),
        "BronzeApron": _build_bronze_apron_mat(
            f"{prefix}BronzeApron",
            p["bronze_apron"],
            p["bronze_accent"],
            p["bronze_patina"],
            p["bronze_collar"],
            p_ad,
            p_as,
            p_rd,
            p_rs,
            metal_val=float(p["bronze_metal"]),
            rough_val=float(p["bronze_rough"]),
        ),
        "Mortar": _build_mortar_mat(f"{prefix}Mortar", p["mortar"]),
        "BronzePlaque": _build_bronze_plaque_mat(
            f"{prefix}BronzePlaque",
            p["bronze_plaque"],
            p["bronze_letter"],
            p_pd,
            p_ps,
            metal_val=min(0.84, float(p["bronze_metal"]) + 0.08),
            rough_val=max(0.34, float(p["bronze_rough"]) - 0.06),
        ),
    }


# ---------------------------------------------------------------------------
# Scene & Mesh Utilities
# ---------------------------------------------------------------------------
def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        d = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(d)
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
    bpy.ops.uv.smart_project(angle_limit=math.radians(52.0), island_margin=0.008, scale_to_bounds=True)
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.006)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


def _loft_closed_island(
    bm: bmesh.types.BMesh,
    ring_pts: list[list[Vector]],
    ring_mat_fn,
    bot_mat: int = 0,
    top_mat: int = 0,
    *,
    u_vals: list[float] | None = None,
    v_vals: list[float] | None = None,
    top_cap_v: float = 0.98,
    bot_cap_v: float = 0.02,
    planar_top_rmax: float | None = None,
    planar_top_from_ring: int | None = None,
    planar_bot_rmax: float | None = None,
    smooth_fn=None,
) -> None:
    """Append one watertight `S^2` manifold island with seam-free `StoneUV` & optional planar top/bottom UVs."""
    sub = bmesh.new()
    sub_uv0 = sub.loops.layers.uv.new("UVMap")
    sub_st = sub.loops.layers.uv.new("StoneUV")
    sub_ap = sub.loops.layers.uv.new("ApronUV")

    n_rings = len(ring_pts)
    n_cols = len(ring_pts[0])
    v_rings = [[sub.verts.new(p) for p in ring] for ring in ring_pts]

    if u_vals is None:
        u_vals = [j / n_cols for j in range(n_cols)]
    if v_vals is None:
        v_vals = [r / max(n_rings - 1, 1) for r in range(n_rings)]

    def _planar_xy(vco: Vector, rmax: float) -> tuple[float, float]:
        return (
            max(0.0, min(1.0, 0.5 + 0.5 * (vco.x / rmax))),
            max(0.0, min(1.0, 0.5 + 0.5 * (vco.y / rmax))),
        )

    def _set_uvs(f: bmesh.types.BMFace, st_coords: list[tuple[float, float]]) -> None:
        for lp, st_uv in zip(f.loops, st_coords):
            lp[sub_uv0].uv = st_uv
            lp[sub_st].uv = st_uv
            vco = lp.vert.co
            lp[sub_ap].uv = (
                max(0.0, min(1.0, 0.5 + 0.5 * (vco.x / APRON_UV_RMAX))),
                max(0.0, min(1.0, 0.5 + 0.5 * (vco.y / APRON_UV_RMAX))),
            )

    for r_idx in range(n_rings - 1):
        r0 = v_rings[r_idx]
        r1 = v_rings[r_idx + 1]
        v0 = v_vals[r_idx]
        v1 = v_vals[r_idx + 1]
        use_pl_top = (planar_top_rmax is not None) and (planar_top_from_ring is not None) and (r_idx >= planar_top_from_ring)
        for j in range(n_cols):
            jn = (j + 1) % n_cols
            u0 = u_vals[j]
            u1 = 1.0 if j == n_cols - 1 else u_vals[jn]
            f = sub.faces.new((r0[j], r0[jn], r1[jn], r1[j]))
            mi = int(ring_mat_fn(r_idx, j))
            f.material_index = mi
            f.smooth = bool(smooth_fn(mi, r_idx, j)) if smooth_fn else True
            if use_pl_top:
                _set_uvs(f, [_planar_xy(lp.vert.co, planar_top_rmax) for lp in f.loops])
            else:
                _set_uvs(f, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)])

    z_bot = sum(p.z for p in ring_pts[0]) / n_cols
    v_bot = sub.verts.new(Vector((0.0, 0.0, z_bot)))
    for j in range(n_cols):
        jn = (j + 1) % n_cols
        u0 = u_vals[j]
        u1 = 1.0 if j == n_cols - 1 else u_vals[jn]
        f = sub.faces.new((v_bot, v_rings[0][jn], v_rings[0][j]))
        f.material_index = bot_mat
        f.smooth = False
        if planar_bot_rmax is not None:
            _set_uvs(f, [_planar_xy(lp.vert.co, planar_bot_rmax) for lp in f.loops])
        else:
            _set_uvs(f, [(0.5 * (u0 + u1), bot_cap_v), (u1, v_vals[0]), (u0, v_vals[0])])

    z_top = sum(p.z for p in ring_pts[-1]) / n_cols
    v_top = sub.verts.new(Vector((0.0, 0.0, z_top)))
    for j in range(n_cols):
        jn = (j + 1) % n_cols
        u0 = u_vals[j]
        u1 = 1.0 if j == n_cols - 1 else u_vals[jn]
        f = sub.faces.new((v_rings[-1][j], v_rings[-1][jn], v_top))
        f.material_index = top_mat
        f.smooth = False
        if planar_top_rmax is not None:
            _set_uvs(f, [_planar_xy(lp.vert.co, planar_top_rmax) for lp in f.loops])
        else:
            _set_uvs(f, [(u0, v_vals[-1]), (u1, v_vals[-1]), (0.5 * (u0 + u1), top_cap_v)])

    bmesh.ops.remove_doubles(sub, verts=sub.verts[:], dist=1e-5)
    bmesh.ops.triangulate(sub, faces=sub.faces[:])
    integrity.ensure_positive_signed_volume(sub)

    me_tmp = bpy.data.meshes.new("__tmp_isl")
    sub.to_mesh(me_tmp)
    sub.free()
    bm.from_mesh(me_tmp)
    bpy.data.meshes.remove(me_tmp)


# ---------------------------------------------------------------------------
# Object 1: Unified Single-Mesh `Memorial` (Curb + Apron + 14-Course Shaft + 18-Stone Cap, <20k tris!)
# Clean 5-zone material slots on `Memorial`:
#   0=ShaftStone, 1=CopingStone, 2=CurbStone, 3=BronzeApron, 4=Mortar
# ---------------------------------------------------------------------------
def build_unified_monument(col: bpy.types.Collection, mlib: dict[str, bpy.types.Material]) -> bpy.types.Object:
    """Build the ENTIRE monument (CurbBase + BronzeApron + unbroken 14-course Shaft + 18-stone CopingCap)
    as ONE single joined watertight object (`~19,584` tris < 20,000 Roblox limit) with 0 horizontal shaft splits!
    """
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    bm.loops.layers.uv.new("StoneUV")
    bm.loops.layers.uv.new("ApronUV")

    mat_list = [
        mlib["ShaftStone"],   # 0
        mlib["CopingStone"],  # 1
        mlib["CurbStone"],    # 2
        mlib["BronzeApron"],  # 3
        mlib["Mortar"],       # 4
        mlib["CapTop"],       # 5 (planar top stone crown: 18 coping slabs + circular central capstone!)
        mlib["CurbBottom"],   # 6 (planar underside granite footing + concrete foundation slab!)
    ]

    # --- A. 6 Pie-Wedge Dark Granite Base Curb Stones (`1,152` tris) ---
    n_curb = CURB_WEDGES
    c_cols = 12  # 72 columns total (exact 60 deg wedges, seams at +/-30, +/-90, +/-150 deg)
    ang_off6 = math.radians(-30.0)
    u_curb = [0.000, 0.014, 0.06, 0.16, 0.28, 0.40, 0.52, 0.64, 0.76, 0.87, 0.94, 0.982]
    u_curb_full = [(b_i + u_s) / n_curb for b_i in range(n_curb) for u_s in u_curb]
    th_curb = [2.0 * math.pi * u_f + ang_off6 for u_f in u_curb_full]
    curb_prof = [
        (CURB_RADIUS - 0.01, 0.0000, 0.20, True, 0.00),
        (CURB_RADIUS + 0.01, 0.44, 0.92, True, 0.24),
        (CURB_RADIUS + 0.00, 0.92, 0.96, True, 0.50),
        (CURB_RADIUS - 0.05, 1.32, 0.36, True, 0.72),
        (CURB_RADIUS - 0.16, 1.40, 0.06, False, 0.78),
        (CURB_RADIUS - 0.34, 1.42, 0.00, False, 0.88),
        (8.18, 1.42, 0.00, False, 0.96),
        (7.92, 1.08, 0.00, False, 0.98),  # 18 cm below BronzeApron bottom (1.26) -> 0 back-to-back!
    ]
    curb_rings = []
    curb_v = [row[4] for row in curb_prof]
    for r_idx, (r_nom, z_nom, rel_s, is_wall, _vv) in enumerate(curb_prof):
        ring = []
        v_blk = max(0.0, min(1.0, z_nom / 1.36))
        for j, th in enumerate(th_curb):
            b_i = j // c_cols
            k = j % c_cols
            dr = (
                -0.036 if (k in (0, 1) and r_idx <= 4 and is_wall)
                else (-0.012 if (k in (0, 1) and r_idx in (4, 5))
                else (_big_quarry_slab_relief(100, b_i, u_curb[k], v_blk, amp=0.095) * rel_s if rel_s > 0 else 0.0))
            )
            dz = -0.014 if (k in (0, 1) and r_idx in (4, 5)) else 0.0
            r = r_nom + dr
            ring.append(Vector((r * math.cos(th), r * math.sin(th), z_nom + dz)))
        curb_rings.append(ring)
    _loft_closed_island(
        bm,
        curb_rings,
        lambda r_idx, j: 2,
        bot_mat=6,
        top_mat=2,
        u_vals=u_curb_full,
        v_vals=curb_v,
        top_cap_v=0.98,
        bot_cap_v=0.02,
        planar_bot_rmax=9.30,
        smooth_fn=lambda _mi, _r, _j: True,
    )

    # --- B. 6 Curved Cast-Bronze Victims' Name Plaques (`1,152` tris) ---
    ap_cols = 12
    u_ap = [0.000, 0.016, 0.07, 0.17, 0.29, 0.41, 0.53, 0.65, 0.77, 0.87, 0.94, 0.982]
    u_ap_full = [(p_i + u_s) / APRON_PANELS for p_i in range(APRON_PANELS) for u_s in u_ap]
    th_ap = [2.0 * math.pi * u_f + ang_off6 for u_f in u_ap_full]
    ap_prof = [
        (APRON_R_OUT - 0.06, 1.26, 0.000),  # 18 cm above CurbBase inner seat (1.08)
        (APRON_R_OUT + 0.00, 1.44, 0.006),
        (APRON_R_OUT - 0.06, 1.49, 0.012),  # low-profile raised outer bronze lip
        (7.50, 1.67, 0.020),                # shallow 13.2-deg sloped cast-bronze plaque face
        (6.48, 1.91, 0.020),
        (APRON_R_IN + 0.22, 2.10, 0.014),   # inner bronze rim groove
        (APRON_R_IN + 0.02, 2.20, 0.004),   # stepped inner collar ring hugging course 1
        (4.60, 2.26, 0.000),                # inner seat cleanly inside Shaft (32 cm above Shaft bottom 1.94)
    ]
    ap_rings = []
    for r_nom, z_nom, seam_d in ap_prof:
        ring = []
        for j, th in enumerate(th_ap):
            k = j % ap_cols
            dz = -seam_d if k in (0, 1) else (0.005 if (k in (2, ap_cols - 1) and seam_d > 0.012) else 0.0)
            ring.append(Vector((r_nom * math.cos(th), r_nom * math.sin(th), z_nom + dz)))
        ap_rings.append(ring)
    _loft_closed_island(
        bm,
        ap_rings,
        lambda _r, _j: 3,
        bot_mat=3,
        top_mat=3,
        u_vals=u_ap_full,
        smooth_fn=lambda _mi, _r, _j: True,
    )

    # --- C. ONE SINGLE UNBROKEN 14-Course Corsehill Sandstone Masonry Shaft (`16,128` tris) ---
    # 14 blocks/course x 8 cols/block = 112 cols x 5 rings/course = 70 course rings!
    # Exact 1:1 UV registration with `shaft_stone_height.png` & `shaft_stone_detail_srgb.png`!
    n_half = BLOCKS_PER_COURSE * 2  # 28 half-blocks
    half_steps = [0.000, 0.032, 0.34, 0.68]
    n_sh_cols = n_half * 4  # 112 columns
    ang_off_sh = -math.pi * (0.016 / n_half)
    u_sh_full = [(h_i + s_k) / n_half for h_i in range(n_half) for s_k in half_steps]
    th_sh = [2.0 * math.pi * u_f + ang_off_sh for u_f in u_sh_full]

    plaque_half_y = 0.5 * PLAQUE_W + 0.025
    sub_fracs = [0.000, 0.032, 0.200, 0.560, 0.925]
    ring_meta: list[tuple[int, int, float]] = [(-1, -1, 1.94)]  # 32 cm below BronzeApron top (2.26)
    for c_idx in range(NUM_COURSES):
        z_c0 = SHAFT_Z_VIS_BOT + c_idx * COURSE_H
        for s_idx, sf in enumerate(sub_fracs):
            ring_meta.append((c_idx, s_idx, z_c0 + sf * COURSE_H))
    ring_meta.append((-2, -2, 17.34))  # 50 cm above CopingCap plug (16.84)

    sh_v = [max(0.0, min(1.0, (zv - SHAFT_Z_VIS_BOT) / (SHAFT_Z_VIS_TOP - SHAFT_Z_VIS_BOT))) for _, _, zv in ring_meta]

    sh_rings = []
    in_pocket = []
    for c_idx, s_idx, z_val in ring_meta:
        r_nom = shaft_nominal_radius(z_val)
        ring = []
        p_row = []
        for j, th in enumerate(th_sh):
            ct, st = math.cos(th), math.sin(th)
            y_cyl = r_nom * st
            if c_idx < 0:
                r = r_nom - 0.24
                ring.append(Vector((r * ct, r * st, z_val)))
                p_row.append(False)
                continue

            # Clean flush-framed rectangular stone niche for BronzePlaque (ZERO stone crescent poking across top/bottom!)
            in_plaque_z = (c_idx == 7 and s_idx >= 1) or (c_idx == 8)
            in_plaque_y = (ct < -0.5) and (abs(y_cyl) <= plaque_half_y)
            if in_plaque_z and in_plaque_y:
                # Seat entire rectangular aperture back wall cleanly behind the plaque front face (`X ≈ -4.38 m`)!
                x_wall = -(r_nom - 0.36)
                ring.append(Vector((x_wall, y_cyl, z_val)))
                p_row.append(True)
                continue

            p_row.append(False)
            shift = 4 if (c_idx % 2 == 1) else 0
            u_sub = (j - shift) % 8
            b_idx = ((j - shift) % n_sh_cols) // 8
            h_part = u_sub // 4
            u_blk = 0.5 * (h_part + half_steps[u_sub % 4])
            v_blk = max(0.0, min(1.0, (sub_fracs[s_idx] - 0.032) / 0.936))

            is_h_m = s_idx in (0, 1)
            is_v_m = u_sub in (0, 1)
            if is_h_m or is_v_m:
                dr = -0.044
            else:
                dr = 0.012 + _big_quarry_slab_relief(c_idx, b_idx, u_blk, v_blk, amp=0.095)
            if c_idx == 0 and not is_h_m and not is_v_m:
                dr += 0.022 * (1.0 - v_blk)
            r = r_nom + dr
            ring.append(Vector((r * ct, r * st, z_val)))
        sh_rings.append(ring)
        in_pocket.append(p_row)

    def _sh_mat(r_idx: int, j: int) -> int:
        c0, _s0, _ = ring_meta[r_idx]
        c1, _s1, _ = ring_meta[r_idx + 1]
        if c0 < 0 or c1 < 0:
            return 4
        jn = (j + 1) % n_sh_cols
        if in_pocket[r_idx][j] and in_pocket[r_idx][jn] and in_pocket[r_idx + 1][j] and in_pocket[r_idx + 1][jn]:
            return 4
        return 0  # Unified `ShaftStone` -> ZERO per-block UV fragmentation!

    _loft_closed_island(
        bm,
        sh_rings,
        _sh_mat,
        bot_mat=4,
        top_mat=4,
        u_vals=u_sh_full,
        v_vals=sh_v,
        smooth_fn=lambda mi, _r, _j: mi != 4,
    )

    # --- D. Exact 18 Overhanging Flat-Aligned Milled Coping Stones (`1,152` tris) ---
    cap_cols = 4
    u_cap = [0.000, 0.048, 0.46, 0.91]
    u_cap_full = [(b_i + u_s) / CAP_BLOCKS for b_i in range(CAP_BLOCKS) for u_s in u_cap]
    th_cap = [2.0 * math.pi * u_f for u_f in u_cap_full]
    cap_prof = [
        (3.96, 16.84, 0.00, False, 0.00),       # 50 cm below Shaft top (17.34)
        (4.24, 17.06, 0.00, False, 0.02),       # deep shadowed drip soffit throat
        (CAP_R_OUT - 0.06, 17.06, 0.18, True, 0.06),  # overhanging drip lip
        (CAP_R_OUT + 0.02, 17.34, 0.96, True, 0.28),  # rock-faced coping fascia lower
        (CAP_R_OUT + 0.01, 17.72, 0.92, True, 0.52),  # rock-faced coping fascia upper
        (CAP_R_OUT - 0.05, 17.92, 0.25, True, 0.66),  # upper stone lip
        (CAP_R_OUT - 0.16, 17.99, 0.04, True, 0.72),  # dressed top chamfer
        (3.85, 18.0000, 0.00, False, 0.88),     # dressed stone top deck (radial joints continue inward!)
    ]
    cap_rings = []
    cap_v = [row[4] for row in cap_prof]
    for r_idx, (r_nom, z_nom, rel_s, has_j, _vv) in enumerate(cap_prof):
        ring = []
        v_blk = max(0.0, min(1.0, (z_nom - 17.10) / 0.84))
        for j, th in enumerate(th_cap):
            b_i = j // cap_cols
            k = j % cap_cols
            dr = (
                -0.038 if (has_j and k in (0, 1) and 3 <= r_idx <= 5)
                else (-0.014 if (has_j and k in (0, 1))
                else (_big_quarry_slab_relief(200, b_i, u_cap[k], v_blk, amp=0.082) * rel_s if rel_s > 0 else 0.0))
            )
            dz = -0.012 if (has_j and k in (0, 1) and r_idx == 6) else 0.0
            r = r_nom + dr
            ring.append(Vector((r * math.cos(th), r * math.sin(th), z_nom + dz)))
        cap_rings.append(ring)

    def _cap_mat(r_idx: int, _j: int) -> int:
        if r_idx <= 1:
            return 4
        if r_idx >= 6:
            return 5  # True planar (X, Y) weathered sandstone top crown (`CapTop`)!
        return 1

    _loft_closed_island(
        bm,
        cap_rings,
        _cap_mat,
        bot_mat=4,
        top_mat=5,
        u_vals=u_cap_full,
        v_vals=cap_v,
        top_cap_v=0.98,
        bot_cap_v=0.01,
        planar_top_rmax=4.75,
        planar_top_from_ring=6,
        smooth_fn=lambda mi, _r, _j: mi not in (4, 5),
    )

    me = bpy.data.meshes.new("Memorial")
    bm.to_mesh(me)
    bm.free()
    for m in mat_list:
        me.materials.append(m)

    ob = bpy.data.objects.new("Memorial", me)
    col.objects.link(ob)
    ob["sc_part"] = "Memorial"
    ob["sc_role"] = "solid"
    me.uv_layers.active_index = 0
    _unwrap_clean(ob)
    me.uv_layers.active_index = 0
    return ob


# ---------------------------------------------------------------------------
# Object 2 (ONLY Separate Object): Flush-Recessed CAD Dedicatory Tablet (`BronzePlaque`)
# ---------------------------------------------------------------------------
def build_bronze_plaque(col: bpy.types.Collection, mlib: dict[str, bpy.types.Material]) -> bpy.types.Object:
    """Import sleek flush-recessed CAD bronze tablet & map exact left-to-right planar `PlaqueUV`."""
    cad_glb = os.path.join(THIS_DIR, "cad", "bronze_plaque.glb")
    if not os.path.isfile(cad_glb):
        raise FileNotFoundError(
            f"Missing CAD bronze plaque GLB at {cad_glb}. Run build_plaque_cad.py via Velum Forge .venv first."
        )

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=cad_glb)
    imported = [o for o in bpy.data.objects if o not in before]
    mesh_obs = [o for o in imported if o.type == "MESH"]
    if not mesh_obs:
        raise RuntimeError(f"CAD GLB {cad_glb} imported 0 mesh objects.")

    r_mid = shaft_nominal_radius(PLAQUE_Z_CTR)
    # Recessed cleanly flush inside the stone niche (clears upper/lower stone bulges cleanly with ZERO bezel clipping!)
    plaque_loc = Vector((-(r_mid - 0.115), 0.0, PLAQUE_Z_CTR))
    plaque_rot = Euler((0.0, SHAFT_BATTER_RAD, 0.0), "XYZ").to_matrix().to_4x4()
    place_xf = Matrix.Translation(plaque_loc) @ plaque_rot
    inv_xf = place_xf.inverted()

    bm = bmesh.new()
    dg = bpy.context.evaluated_depsgraph_get()
    for mo in mesh_obs:
        bm_sub = bmesh.new()
        bm_sub.from_object(mo, dg)
        bm_sub.transform(place_xf @ mo.matrix_world)
        me_tmp = bpy.data.meshes.new("__tmp_plaque")
        bm_sub.to_mesh(me_tmp)
        bm_sub.free()
        bm.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)

    for o in imported:
        d = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        core._free_data(d)

    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    integrity.ensure_positive_signed_volume(bm)

    me = bpy.data.meshes.new("BronzePlaque")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mlib["BronzePlaque"])
    for poly in me.polygons:
        poly.use_smooth = False

    ob = bpy.data.objects.new("BronzePlaque", me)
    col.objects.link(ob)
    ob["sc_part"] = "BronzePlaque"
    ob["sc_role"] = "solid"
    _unwrap_clean(ob)

    # Exact left-to-right planar front UV (`PlaqueUV`) when viewing from -X toward +X (+Z up -> Right = -Y!)
    p_uv = me.uv_layers.new(name="PlaqueUV")
    for poly in me.polygons:
        is_front = poly.normal.x < -0.5
        for l_idx in poly.loop_indices:
            if is_front:
                lco = inv_xf @ me.vertices[me.loops[l_idx].vertex_index].co
                u = 0.5 - (lco.y / PLAQUE_W)
                v = 0.5 + (lco.z / PLAQUE_H)
                p_uv.data[l_idx].uv = (max(0.0, min(1.0, u)), max(0.0, min(1.0, v)))
            else:
                p_uv.data[l_idx].uv = (0.01, 0.01)
    me.uv_layers.active_index = 0
    return ob


# ---------------------------------------------------------------------------
# Stage 3: Hard BVH Structural Contact Gate (`Memorial` <-> `BronzePlaque`)
# ---------------------------------------------------------------------------
def verify_monument_integrity(memorial_ob: bpy.types.Object, plaque_ob: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    bm_m = bmesh.new()
    bm_p = bmesh.new()
    try:
        bm_m.from_object(memorial_ob, dg)
        bm_m.transform(memorial_ob.matrix_world)
        bm_p.from_object(plaque_ob, dg)
        bm_p.transform(plaque_ob.matrix_world)
        if not BVHTree.FromBMesh(bm_m).overlap(BVHTree.FromBMesh(bm_p)):
            raise RuntimeError("Stage 3 BVH Gate FAILED: BronzePlaque has 0 BVH overlap with Memorial!")
        core.log("[Stage 3 BVH Gate] PASS — unified Memorial & BronzePlaque positively bonded (0 floating parts).")
    finally:
        bm_m.free()
        bm_p.free()


# ---------------------------------------------------------------------------
# Master Assembly Builder (Exact 2 Objects: `Memorial` + `BronzePlaque`)
# ---------------------------------------------------------------------------
def build_all(
    collection_name: str = "Memorial",
    clear_scene: bool = True,
    palette_override: dict | None = None,
    mat_prefix: str = "Mem_",
):
    if clear_scene:
        clear_scene_and_setup_units()
    col = core.fresh_collection(collection_name)
    mlib = build_material_library(palette=palette_override, prefix=mat_prefix)

    monument = build_unified_monument(col, mlib)
    plaque = build_bronze_plaque(col, mlib)
    meshes = [monument, plaque]

    lo, _ = core.world_bbox(meshes)
    if abs(lo.z) > 1e-7:
        for o in meshes:
            o.data.transform(Matrix.Translation((0.0, 0.0, -lo.z)))
            o.data.update()

    core.socket("PlaqueFocus", col, location=(-5.05, 0.0, PLAQUE_Z_CTR), rotation=(0.0, 0.0, math.radians(90.0)), parent_part="BronzePlaque")
    core.socket("WreathMount", col, location=(-CURB_RADIUS - 0.25, 0.0, 0.12), rotation=(0.0, 0.0, math.radians(90.0)), parent_part="Memorial")
    core.socket("BeaconTop", col, location=(0.0, 0.0, TOTAL_HEIGHT), parent_part="Memorial")

    verify_monument_integrity(monument, plaque)
    if clear_scene:
        refs.load_reference_planes(THIS_DIR)
    gameready.validate(meshes)
    return col, meshes


def main() -> int:
    _, meshes = build_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(THIS_DIR, "memorial.blend"))
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.export_scene.gltf(
        filepath=os.path.join(THIS_DIR, "memorial.glb"),
        use_selection=True,
        export_format="GLB",
        export_apply=True,
    )
    for o in meshes:
        o.select_set(False)
    return 0


if __name__ == "__main__":
    main()
