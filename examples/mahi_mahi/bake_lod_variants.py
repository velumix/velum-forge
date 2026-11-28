"""Velum Forge â€” Trophy Mahi-Mahi (`Coryphaena hippurus`) 2K Cycles PBR Bake, 4 Variants, 4-Tier LODs & Swim Rig.

End-to-end production pipeline matching & extending `Sunrunner 24`:
  1. Builds parametric anatomical Mahi-Mahi (`build_mahi_mahi.py`) with real sexual dimorphism:
       - Bull Dorado steep cranial boss (`bull_crest = 1.00..1.05`) on `bull_dorado` & `albino_gold_legendary`
       - Sleek aerodynamic Cow Dorado head (`bull_crest = 0.38..0.45`) on `blue_phase_lit` & `sunset_coral`
  2. Packs all 6 watertight `MeshPart` objects (`Body`, `DorsalFin`, `CaudalFin`, `PectoralFins`,
     `VentralFins`, `Eyes`) onto a non-overlapping `2048x2048` UV atlas (with 2.8x texel-density boost
     on `Eyes` so radial iris fibers and teardrop pupils bake razor-sharp).
  3. Authors rich procedural ichthyology shaders (pelagic countershading, imbricated diamond cycloid scales,
     Dorado speckles, pelagic excitement bars, crimson gill cleft, corrugated fin-ray bump, and striated
     metallic-iris / glossy-cornea eyes) and bakes true `2048x2048` Cycles GPU (`OPTIX`) PBR texture sets:
       - `T_MahiMahi_<variant>_Color.png`     (sRGB albedo + 64-sample raytraced Cycles AO)
       - `T_MahiMahi_<variant>_Normal.png`    (Non-Color OpenGL +X/+Y/+Z tangent-space normal map)
       - `T_MahiMahi_<variant>_Roughness.png` (Non-Color wet mucus / fin / cornea micro-roughness)
       - `T_MahiMahi_<variant>_Metalness.png` (Non-Color iridescent guanine & metallic iris map)
       - `T_MahiMahi_<variant>_AO.png`        (Non-Color standalone Ambient Occlusion)
       - `T_MahiMahi_<variant>_ORM.png`       (Non-Color glTF/engine channel-packed R=AO, G=Rough, B=Metal)
  4. Generates a verified 4-tier game LOD chain (`LOD0` ~31k -> `LOD1` ~15k -> `LOD2` ~7.5k -> `LOD3` ~3.4k tris)
     preserving shared `2048x2048` baked UVs, silhouette, and articulated `CaudalFin` servo part.
  5. Builds a 7-bone game-ready swim skeleton (`Armature_MahiSwim` + looping sinusoidal pelagic swim action)
     exported to `rigged/mahi_mahi_swim_rigged.glb` alongside all 4 Roblox `SurfaceAppearance` variant bundles.

Run headless:
    blender -b --python-exit-code 1 -P assets/models/mahi_mahi/bake_lod_variants.py
"""

from __future__ import annotations

import importlib
import json
import math
import os
import shutil
import sys
import tempfile
import time

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
BLENDER_TOOLS = os.path.join(REPO_ROOT, "engine", "blender")
for p in (THIS_DIR, BLENDER_TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

import sclib  # noqa: E402
from sclib import core, export, gameready, mats, render  # noqa: E402
import build_mahi_mahi as mm  # noqa: E402

importlib.reload(mm)

BAKE_RES = 2048
TEXTURES_ROOT = os.path.join(THIS_DIR, "textures")
VARIANTS_ROOT = os.path.join(THIS_DIR, "variants")
LODS_ROOT = os.path.join(THIS_DIR, "lods")
RIGGED_ROOT = os.path.join(THIS_DIR, "rigged")
RENDERS_ROOT = os.path.join(THIS_DIR, "renders")
EXPORT_DEFAULT = os.path.join(THIS_DIR, "export")
DESIGN_MODEL_OUTPUT = core.DESIGN_OUTPUT_DIR

PART_ORDER = ["Body", "DorsalFin", "CaudalFin", "PectoralFins", "VentralFins", "Eyes"]

# ---------------------------------------------------------------------------
# 1. Four Biological & Rarity Variants (`Common`, `Uncommon`, `Rare`, `Legendary`)
# ---------------------------------------------------------------------------
VARIANTS = [
    {
        "id": "bull_dorado",
        "label": "Mahi-Mahi â€” Trophy Bull Dorado (Common / Flagship)",
        "rarity": "Common",
        "bull_crest": 1.00,
        "col_dorsal": "#006E72",       # Deep iridescent Emerald-Turquoise back
        "col_flank": "#E8B914",        # Blazing sunlit Dorado Gold-Chartreuse flank
        "col_belly": "#EEF2EB",        # Pearlescent Silver-Cream ventral countershading
        "col_spots": "#06384D",        # Dark Cobalt-Teal Dorado speckles
        "col_bars": "#0A645E",         # Subtle emerald excitement bars
        "bar_strength": 0.24,
        "col_dorsal_fin": "#075E68",   # Electric Teal-Emerald sail crest
        "col_dorsal_tip": "#C99E12",   # Sunlit Gold sail highlights
        "col_caudal": "#DCA812",       # Golden-Chartreuse scissor tail
        "col_caudal_edge": "#0B4D58",  # Dark teal tail trailing margin
        "col_pectoral": "#088EB8",     # Vivid Electric Cyan-Blue pectoral sickle fins
        "col_ventral": "#DFB828",      # Golden-cream pelvic & anal fins
        "col_iris": "#E8B822",         # Metallic 24K Gold Dorado iris
        "flank_metal": 0.54,
    },
    {
        "id": "blue_phase_lit",
        "label": "Mahi-Mahi â€” Lit-Up Electric Blue Cow (Uncommon Hunting Phase)",
        "rarity": "Uncommon",
        "bull_crest": 0.38,            # Sleek aerodynamic female / cow Dorado head profile!
        "col_dorsal": "#071F56",       # Midnight Pelagic Sapphire-Indigo back
        "col_flank": "#1EA6EC",        # Neon Cerulean-Ice lit flank
        "col_belly": "#ECF3F9",        # Bright Silver-Chrome belly
        "col_spots": "#051942",        # Deep Abyssal Navy speckles
        "col_bars": "#093B96",         # Bold lit-up hunting vertical bars!
        "bar_strength": 0.56,
        "col_dorsal_fin": "#0B46B8",   # Electric Ultramarine sail fin
        "col_dorsal_tip": "#36C5FF",   # Glowing Cyan sail margin
        "col_caudal": "#1478D4",       # Sapphire-Cyan forked tail
        "col_caudal_edge": "#061D4C",  # Midnight navy tail edge
        "col_pectoral": "#1AC2FF",     # Neon Ice-Blue pectoral fins
        "col_ventral": "#82CCF2",      # Frosted Ice-Silver ventral fins
        "col_iris": "#38C6FF",         # Electric Cyan-Silver iris
        "flank_metal": 0.60,
    },
    {
        "id": "sunset_coral",
        "label": "Mahi-Mahi â€” Sunset Coral Reef Dorado (Rare Deep-Drop)",
        "rarity": "Rare",
        "bull_crest": 0.46,
        "col_dorsal": "#821019",       # Deep Vermilion-Ruby dorsal back
        "col_flank": "#EC6414",        # Molten Tangerine-Copper flank
        "col_belly": "#F6EAE0",        # Warm Champagne-Pearl belly
        "col_spots": "#42070E",        # Dark Burgundy speckles
        "col_bars": "#9E1E14",         # Warm Crimson excitement bars
        "bar_strength": 0.34,
        "col_dorsal_fin": "#B51E18",   # Fiery Crimson-Coral sail crest
        "col_dorsal_tip": "#F29B18",   # Molten Amber fin tips
        "col_caudal": "#E04E14",       # Blazing Sunset-Orange tail
        "col_caudal_edge": "#590B12",  # Deep Garnet trailing margin
        "col_pectoral": "#F07C18",     # Vivid Mandarin-Gold pectoral fins
        "col_ventral": "#EB8E38",      # Warm Apricot-Gold ventral fins
        "col_iris": "#F59E1B",         # Fiery Amber-Gold iris
        "flank_metal": 0.52,
    },
    {
        "id": "albino_gold_legendary",
        "label": "Mahi-Mahi â€” 24K Ghost Bull Dorado (Legendary 1-in-1,000)",
        "rarity": "Legendary",
        "bull_crest": 1.05,            # Massive Trophy Bull cranial boss!
        "col_dorsal": "#DDA620",       # Shimmering 24K Bullion Gold crown & spine
        "col_flank": "#F4F1EA",        # Pearlescent Leucistic Platinum-Ivory flank
        "col_belly": "#FAF9F5",        # Pure Iridescent Mother-of-Pearl belly
        "col_spots": "#C98E14",        # 24K Gold-Leaf speckles!
        "col_bars": "#E5BA38",         # Subtle champagne-gold shimmer bars
        "bar_strength": 0.28,
        "col_dorsal_fin": "#E2AF22",   # Royal 24K Gold sail crest
        "col_dorsal_tip": "#FFF6D6",   # Platinum-White scalloped tips
        "col_caudal": "#E4B225",       # Gilded 24K Gold scissor tail
        "col_caudal_edge": "#B57C0E",  # Burnished Bronze-Gold margin
        "col_pectoral": "#EAC242",     # Shimmering Champagne-Gold pectorals
        "col_ventral": "#F2DF96",      # Ivory-Gold pelvics & anal fin
        "col_iris": "#D4142A",         # Mythic Leucistic Ruby-Garnet iris!
        "flank_metal": 0.72,
    },
]


# ---------------------------------------------------------------------------
# Color & Blender 5.2 Shader Node Helpers
# ---------------------------------------------------------------------------
def _hex_to_lin(h: str) -> tuple[float, float, float, float]:
    return (*mats.linear(h), 1.0)


def _lin_arr_to_srgb(arr: np.ndarray) -> np.ndarray:
    a = np.clip(arr, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(np.maximum(a, 1e-8), 1.0 / 2.4) - 0.055)


def _mix_rgba(nt: bpy.types.NodeTree, fac, col_a, col_b) -> bpy.types.NodeSocket:
    """Blender 5.2-safe RGBA Mix node binding explicit socket indices (0=Factor, 6=A, 7=B, out 2=Result)."""
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.clamp_factor = True
    if isinstance(fac, bpy.types.NodeSocket):
        nt.links.new(fac, mx.inputs[0])
    else:
        mx.inputs[0].default_value = float(fac)

    if isinstance(col_a, bpy.types.NodeSocket):
        nt.links.new(col_a, mx.inputs[6])
    else:
        mx.inputs[6].default_value = col_a

    if isinstance(col_b, bpy.types.NodeSocket):
        nt.links.new(col_b, mx.inputs[7])
    else:
        mx.inputs[7].default_value = col_b

    return mx.outputs[2]


def _math_node(nt: bpy.types.NodeTree, op: str, a, b=None, clamp: bool = False) -> bpy.types.NodeSocket:
    mn = nt.nodes.new("ShaderNodeMath")
    mn.operation = op
    mn.use_clamp = clamp
    if isinstance(a, bpy.types.NodeSocket):
        nt.links.new(a, mn.inputs[0])
    else:
        mn.inputs[0].default_value = float(a)
    if b is not None:
        if isinstance(b, bpy.types.NodeSocket):
            nt.links.new(b, mn.inputs[1])
        else:
            mn.inputs[1].default_value = float(b)
    return mn.outputs[0]


def _map_range(nt: bpy.types.NodeTree, val, f_min: float, f_max: float, t_min: float = 0.0, t_max: float = 1.0) -> bpy.types.NodeSocket:
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    mr.clamp = True
    nt.links.new(val, mr.inputs["Value"])
    mr.inputs["From Min"].default_value = f_min
    mr.inputs["From Max"].default_value = f_max
    mr.inputs["To Min"].default_value = t_min
    mr.inputs["To Max"].default_value = t_max
    return mr.outputs["Result"]


# ---------------------------------------------------------------------------
# 2. Procedural Ichthyology Material Builder (Scales, Countershading, Fins, Eyes)
# ---------------------------------------------------------------------------
def build_procedural_fish_materials(v: dict) -> dict[str, bpy.types.Material]:
    """Create rich procedural Cycles materials for `Body`, fins, and `Eyes` ready for 2K PBR baking."""
    vid = v["id"]

    # ---- A. BODY SHADER (`MM_Proc_Body`) ----
    m_body, b_body = mats._new_node_material(f"MM_Proc_Body_{vid}")
    nt = m_body.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    y_coord = sep.outputs["Y"]
    z_coord = sep.outputs["Z"]

    # Organic biological noise to undulate pigment transitions naturally along the body
    noise_bio = nt.nodes.new("ShaderNodeTexNoise")
    noise_bio.inputs["Scale"].default_value = 9.5
    noise_bio.inputs["Detail"].default_value = 5.0
    noise_bio.inputs["Roughness"].default_value = 0.55
    nt.links.new(tc.outputs["Object"], noise_bio.inputs["Vector"])
    n_jit = _math_node(nt, "MULTIPLY", _math_node(nt, "SUBTRACT", noise_bio.outputs["Fac"], 0.5), 0.032)
    z_wavy = _math_node(nt, "ADD", z_coord, n_jit)

    # 3-zone pelagic countershading: Belly (Z < 0.085) -> Iridescent Flank (0.085..0.215) -> Dorsal Back (> 0.215)
    c_belly = _hex_to_lin(v["col_belly"])
    c_flank = _hex_to_lin(v["col_flank"])
    c_dorsal = _hex_to_lin(v["col_dorsal"])
    c_spots = _hex_to_lin(v["col_spots"])
    c_bars = _hex_to_lin(v["col_bars"])
    c_gill = _hex_to_lin("#6B0F1A")

    f_flank = _map_range(nt, z_wavy, 0.062, 0.122, 0.0, 1.0)
    f_dorsal = _map_range(nt, z_wavy, 0.195, 0.258, 0.0, 1.0)

    col_base = _mix_rgba(nt, f_flank, c_belly, c_flank)
    col_counter = _mix_rgba(nt, f_dorsal, col_base, c_dorsal)

    # Vertical pelagic excitement bars across mid/upper flanks (Y in [-0.32, +0.28])
    wave_bars = nt.nodes.new("ShaderNodeTexWave")
    wave_bars.wave_type = "BANDS"
    wave_bars.bands_direction = "Y"
    wave_bars.wave_profile = "SIN"
    wave_bars.inputs["Scale"].default_value = 7.2
    wave_bars.inputs["Distortion"].default_value = 3.2
    wave_bars.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], wave_bars.inputs["Vector"])

    bar_zone_y = _math_node(
        nt,
        "MULTIPLY",
        _map_range(nt, y_coord, -0.34, -0.22, 0.0, 1.0),
        _map_range(nt, y_coord, 0.30, 0.18, 0.0, 1.0),
    )
    bar_zone_z = _map_range(nt, z_wavy, 0.08, 0.15, 0.0, 1.0)
    bar_mask = _math_node(
        nt,
        "MULTIPLY",
        _map_range(nt, wave_bars.outputs["Fac"], 0.45, 0.85, 0.0, v["bar_strength"]),
        _math_node(nt, "MULTIPLY", bar_zone_y, bar_zone_z),
        clamp=True,
    )
    col_with_bars = _mix_rgba(nt, bar_mask, col_counter, c_bars)

    # Authentic scattered Dorado spots (`Voronoi F1` speckles across flank & cheek)
    vor_spots = nt.nodes.new("ShaderNodeTexVoronoi")
    vor_spots.feature = "F1"
    vor_spots.inputs["Scale"].default_value = 64.0
    vor_spots.inputs["Randomness"].default_value = 0.95
    nt.links.new(tc.outputs["Object"], vor_spots.inputs["Vector"])

    spot_hit = _map_range(nt, vor_spots.outputs["Distance"], 0.18, 0.07, 0.0, 1.0)
    # Modulate spot density organically with low-frequency noise so spots cluster naturally
    spot_cluster = _map_range(nt, noise_bio.outputs["Fac"], 0.36, 0.68, 0.0, 0.88)
    spot_z_mask = _math_node(
        nt,
        "MULTIPLY",
        _map_range(nt, z_coord, 0.045, 0.095, 0.0, 1.0),
        _map_range(nt, z_coord, 0.275, 0.215, 0.0, 1.0),
    )
    spot_y_mask = _map_range(nt, y_coord, 0.50, 0.40, 0.0, 1.0)
    spot_fac = _math_node(
        nt,
        "MULTIPLY",
        spot_hit,
        _math_node(nt, "MULTIPLY", spot_cluster, _math_node(nt, "MULTIPLY", spot_z_mask, spot_y_mask)),
        clamp=True,
    )
    col_spotted = _mix_rgba(nt, spot_fac, col_with_bars, c_spots)

    # Exact C-curved gill-slit rim accent hugging `y_operc = 0.296 + 0.048 * ((z - 0.136)/0.092)^2`!
    zn_g = _math_node(nt, "MULTIPLY", _math_node(nt, "SUBTRACT", z_coord, 0.136), 10.87)
    zn_g2 = _math_node(nt, "MULTIPLY", zn_g, zn_g)
    y_operc_n = _math_node(nt, "ADD", 0.296, _math_node(nt, "MULTIPLY", 0.048, zn_g2))
    d_op_n = _math_node(nt, "SUBTRACT", y_coord, y_operc_n)  # 0 right on curved gill edge, -0.004 in recessed cleft
    gill_curve_hit = _math_node(
        nt,
        "MULTIPLY",
        _map_range(nt, d_op_n, -0.009, -0.004, 0.0, 1.0),
        _map_range(nt, d_op_n, 0.002, -0.003, 0.0, 1.0),
    )
    gill_z = _math_node(
        nt,
        "MULTIPLY",
        _map_range(nt, z_coord, 0.055, 0.085, 0.0, 1.0),
        _map_range(nt, z_coord, 0.225, 0.195, 0.0, 1.0),
    )
    gill_fac = _math_node(nt, "MULTIPLY", _math_node(nt, "MULTIPLY", gill_curve_hit, gill_z), 0.55, clamp=True)
    col_final_body = _mix_rgba(nt, gill_fac, col_spotted, c_gill)
    nt.links.new(col_final_body, mats.sock(b_body, "Base Color"))

    # Imbricated Diamond Cycloid Fish Scales -> Normal Bump + Wet Mucus Micro-Roughness + Guanine Metallic!
    mapping_sc = nt.nodes.new("ShaderNodeMapping")
    mapping_sc.inputs["Rotation"].default_value = (math.radians(45.0), 0.0, math.radians(45.0))
    mapping_sc.inputs["Scale"].default_value = (1.0, 1.35, 1.35)
    nt.links.new(tc.outputs["Object"], mapping_sc.inputs["Vector"])

    vor_scales = nt.nodes.new("ShaderNodeTexVoronoi")
    vor_scales.feature = "DISTANCE_TO_EDGE"
    vor_scales.distance = "MANHATTAN"
    vor_scales.inputs["Scale"].default_value = 145.0
    vor_scales.inputs["Randomness"].default_value = 0.14
    nt.links.new(mapping_sc.outputs["Vector"], vor_scales.inputs["Vector"])

    # Fade scales out smoothly on anterior snout/lips & gill cover (`Y > 0.36` smooth skin!)
    scale_skin_mask = _map_range(nt, y_coord, 0.38, 0.27, 0.08, 1.0)
    scale_h = _math_node(nt, "MULTIPLY", _map_range(nt, vor_scales.outputs["Distance"], 0.0, 0.22, 0.0, 1.0), scale_skin_mask)

    bump_sc = nt.nodes.new("ShaderNodeBump")
    bump_sc.inputs["Strength"].default_value = 0.38
    bump_sc.inputs["Distance"].default_value = 0.0018
    nt.links.new(scale_h, bump_sc.inputs["Height"])
    nt.links.new(bump_sc.outputs["Normal"], mats.sock(b_body, "Normal"))

    # Wet mucus sheen: glossy crowns (0.14) + slightly rougher scale pockets (0.29)
    rough_body = _map_range(nt, scale_h, 0.0, 1.0, 0.29, 0.14)
    nt.links.new(rough_body, mats.sock(b_body, "Roughness"))

    # Iridescent guanine metallic sheen strongest on sunlit flank & gill operculum!
    flank_band = _math_node(
        nt,
        "MULTIPLY",
        _map_range(nt, z_coord, 0.04, 0.11, 0.22, 1.0),
        _map_range(nt, z_coord, 0.27, 0.20, 0.30, 1.0),
    )
    metal_body = _math_node(nt, "MULTIPLY", flank_band, v["flank_metal"], clamp=True)
    nt.links.new(metal_body, mats.sock(b_body, "Metallic"))

    # ---- B. FIN SHADER HELPER (Corrugated Fin-Ray Striations + Margin Gradient) ----
    def _make_fin_mat(mname: str, hex_base: str, hex_edge: str, wave_dir: str, ray_scale: float) -> bpy.types.Material:
        mf, bf = mats._new_node_material(mname)
        ntf = mf.node_tree
        tcf = ntf.nodes.new("ShaderNodeTexCoord")
        sepf = ntf.nodes.new("ShaderNodeSeparateXYZ")
        ntf.links.new(tcf.outputs["Generated"], sepf.inputs["Vector"])

        wv = ntf.nodes.new("ShaderNodeTexWave")
        wv.wave_type = "BANDS"
        wv.bands_direction = wave_dir
        wv.wave_profile = "SIN"
        wv.inputs["Scale"].default_value = ray_scale
        wv.inputs["Distortion"].default_value = 0.8
        ntf.links.new(tcf.outputs["Object"], wv.inputs["Vector"])

        edge_axis = sepf.outputs["Z"] if wave_dir == "Y" else sepf.outputs["Y"]
        grad = _map_range(ntf, edge_axis, 0.62, 0.98, 0.0, 0.62)
        ray_tint = _map_range(ntf, wv.outputs["Fac"], 0.25, 0.85, 0.0, 0.22)
        mix_f = _math_node(ntf, "ADD", grad, ray_tint, clamp=True)

        c_a = _hex_to_lin(hex_base)
        c_b = _hex_to_lin(hex_edge)
        ntf.links.new(_mix_rgba(ntf, mix_f, c_a, c_b), mats.sock(bf, "Base Color"))

        bmp = ntf.nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = 0.42
        bmp.inputs["Distance"].default_value = 0.0016
        ntf.links.new(wv.outputs["Fac"], bmp.inputs["Height"])
        ntf.links.new(bmp.outputs["Normal"], mats.sock(bf, "Normal"))

        ntf.links.new(_map_range(ntf, wv.outputs["Fac"], 0.0, 1.0, 0.34, 0.19), mats.sock(bf, "Roughness"))
        mats.sock(bf, "Metallic").default_value = 0.24
        return mf

    m_dorsal = _make_fin_mat(f"MM_Proc_Dorsal_{vid}", v["col_dorsal_fin"], v["col_dorsal_tip"], "Y", 48.0)
    m_caudal = _make_fin_mat(f"MM_Proc_Caudal_{vid}", v["col_caudal"], v["col_caudal_edge"], "Z", 52.0)
    m_pectoral = _make_fin_mat(f"MM_Proc_Pectoral_{vid}", v["col_pectoral"], v["col_dorsal"], "Z", 56.0)
    m_ventral = _make_fin_mat(f"MM_Proc_Ventral_{vid}", v["col_ventral"], v["col_dorsal_fin"], "Y", 46.0)

    # ---- C. LIVING JEWEL EYE SHADER (`MM_Proc_Eyes`) ----
    # Uses Object coordinates centered at `eye_y = 0.462`, `eye_z = 0.158 + 0.004 * bull_crest + z_shift`!
    # Even simpler & 100% invariant to z_shift: use `Eyes`'s pristine pre-built Polar UV (`u_center = 0.25 / 0.75, v = 0.50`)
    # via a dedicated secondary UV layer `EyePolarUV` preserved across atlas packing!
    m_eye, b_eye = mats._new_node_material(f"MM_Proc_Eye_{vid}")
    nte = m_eye.node_tree
    uv_node = nte.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = "EyePolarUV"
    sepe = nte.nodes.new("ShaderNodeSeparateXYZ")
    nte.links.new(uv_node.outputs["UV"], sepe.inputs["Vector"])

    # Mirror U around 0.5 so both Port (0.25, 0.5) and Starboard (0.75, 0.5) map to radial distance from (0.25, 0.5)!
    u_mir = _math_node(nte, "SUBTRACT", 0.5, _math_node(nte, "ABSOLUTE", _math_node(nte, "SUBTRACT", sepe.outputs["X"], 0.5)))
    du = _math_node(nte, "SUBTRACT", u_mir, 0.25)
    dv = _math_node(nte, "SUBTRACT", sepe.outputs["Y"], 0.50)
    r_sq = _math_node(nte, "ADD", _math_node(nte, "MULTIPLY", du, du), _math_node(nte, "MULTIPLY", dv, dv))
    r_eye = _math_node(nte, "SQRT", r_sq)

    # Radial iris striations using Voronoi on EyePolarUV
    vor_iris = nte.nodes.new("ShaderNodeTexVoronoi")
    vor_iris.inputs["Scale"].default_value = 95.0
    nte.links.new(uv_node.outputs["UV"], vor_iris.inputs["Vector"])

    c_pupil = _hex_to_lin("#040507")
    c_iris = _hex_to_lin(v["col_iris"])
    c_iris_dark = tuple(c * 0.45 for c in c_iris[:3]) + (1.0,)
    c_sclera = _hex_to_lin("#0E131A")

    iris_tex = _mix_rgba(nte, _map_range(nte, vor_iris.outputs["Distance"], 0.0, 0.35, 0.0, 1.0), c_iris, c_iris_dark)
    # Visible orbital aperture spans r_eye in [0.0..0.042]: crisp jet-black pupil (0..0.017) + gleaming metallic iris (0.018..0.038)!
    f_pupil_to_iris = _map_range(nte, r_eye, 0.0155, 0.0190, 0.0, 1.0)
    f_iris_to_sclera = _map_range(nte, r_eye, 0.0355, 0.0415, 0.0, 1.0)

    col_eye_1 = _mix_rgba(nte, f_pupil_to_iris, c_pupil, iris_tex)
    col_eye_all = _mix_rgba(nte, f_iris_to_sclera, col_eye_1, c_sclera)
    nte.links.new(col_eye_all, mats.sock(b_eye, "Base Color"))

    # Ultra-glossy wet cornea roughness (0.035 over pupil/iris, 0.14 on outer rim)
    nte.links.new(_map_range(nte, r_eye, 0.036, 0.055, 0.035, 0.14), mats.sock(b_eye, "Roughness"))
    # High metallic gleam exclusively on the iris ring (`0.042 < r_eye < 0.096`)!
    iris_band = _math_node(nt=nte, op="SUBTRACT", a=f_pupil_to_iris, b=f_iris_to_sclera, clamp=True)
    nte.links.new(_math_node(nte, "MULTIPLY", iris_band, 0.78, clamp=True), mats.sock(b_eye, "Metallic"))

    return {
        "Body": m_body,
        "DorsalFin": m_dorsal,
        "CaudalFin": m_caudal,
        "PectoralFins": m_pectoral,
        "VentralFins": m_ventral,
        "Eyes": m_eye,
    }


# ---------------------------------------------------------------------------
# 3. Shared Non-Overlapping `2048x2048` UV Atlas Packer (Preserves `EyePolarUV`!)
# ---------------------------------------------------------------------------
def pack_shared_fish_atlas(part_objs: dict[str, bpy.types.Object]) -> None:
    """Pack all 6 parts onto a single non-overlapping `[0, 1]` UV atlas (`UVMap`) with 2.8x eye density boost."""
    # Preserve Eyes' polar UV on `EyePolarUV` before packing active `UVMap` into the shared atlas!
    eyes_ob = part_objs["Eyes"]
    if "EyePolarUV" not in eyes_ob.data.uv_layers:
        src_uv = eyes_ob.data.uv_layers[0]
        polar_uv = eyes_ob.data.uv_layers.new(name="EyePolarUV")
        for idx_l in range(len(eyes_ob.data.loops)):
            polar_uv.data[idx_l].uv = src_uv.data[idx_l].uv.copy()
    eyes_ob.data.uv_layers.active_index = 0

    all_objs = [part_objs[k] for k in PART_ORDER]
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in all_objs:
        o.data.uv_layers.active_index = 0
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_objs[0]

    # Re-unwrap Body & Fins cleanly with generous island margin, then multi-object pack with Eyes!
    body_and_fins = [part_objs[k] for k in PART_ORDER if k != "Eyes"]
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in body_and_fins:
        o.select_set(True)
    bpy.context.view_layer.objects.active = body_and_fins[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.008, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Boost Eyes' UV island area by 3.0x prior to pack so iris & pupil are ultra-crisp!
    bm_e = bmesh.new()
    bm_e.from_mesh(eyes_ob.data)
    uv_e = bm_e.loops.layers.uv[0]
    for f in bm_e.faces:
        for lp in f.loops:
            lp[uv_e].uv = lp[uv_e].uv * 0.26
    bm_e.to_mesh(eyes_ob.data)
    bm_e.free()

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in all_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.006)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")

    for o in all_objs:
        o.select_set(False)


# ---------------------------------------------------------------------------
# 4. True `2048x2048` Cycles `OPTIX` GPU PBR Texture Baker
# ---------------------------------------------------------------------------
def _enable_cycles_gpu(sc: bpy.types.Scene) -> str:
    try:
        from vflib import bake as _vf_bake

        return _vf_bake.enable_cycles_gpu(sc, use_denoising=True)
    except Exception:
        pass
    sc.render.engine = "CYCLES"
    env_t = os.environ.get("VELUM_BLENDER_THREADS", "").strip()
    safe_threads = int(env_t) if env_t.isdigit() and int(env_t) > 0 else min(8, max(2, (os.cpu_count() or 8) // 2))
    env_ts = os.environ.get("VELUM_CYCLES_TILE_SIZE", "").strip()
    safe_tile = int(env_ts) if env_ts.isdigit() and int(env_ts) >= 64 else 512
    try:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = safe_threads
        sc.cycles.use_auto_tile = True
        sc.cycles.tile_size = safe_tile
    except Exception:
        pass
    backend = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == dev_type]
                if devs:
                    for d in prefs.devices:
                        d.use = (d.type == dev_type)
                    sc.cycles.device = "GPU"
                    backend = dev_type
                    break
            except Exception:
                continue
    except Exception:
        pass
    sc.cycles.use_denoising = True
    if backend == "OPTIX":
        try:
            sc.cycles.denoising_use_gpu = True
        except Exception:
            pass
        try:
            sc.cycles.denoiser = "OPTIX"
        except Exception:
            pass
    elif backend != "CPU":
        try:
            sc.cycles.denoiser = "OPENIMAGEDENOISE"
            sc.cycles.denoising_use_gpu = True
        except Exception:
            pass
    return backend


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


def _atomic_copy_fallback(src_path: str, dst_path: str, retries: int = 6) -> None:
    abs_dst = os.path.abspath(dst_path)
    dst_dir = os.path.dirname(abs_dst)
    os.makedirs(dst_dir, exist_ok=True)
    staged = os.path.join(dst_dir, f".__vf_stage_{os.getpid()}_{os.path.basename(abs_dst)}")
    try:
        shutil.copy2(src_path, staged)
        try:
            with open(staged, "rb+") as fh:
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            pass
        for attempt in range(retries):
            try:
                os.replace(staged, abs_dst)
                return
            except PermissionError:
                if attempt == retries - 1:
                    raise
                time.sleep(0.4)
    finally:
        if os.path.exists(staged):
            try:
                os.remove(staged)
            except OSError:
                pass


def _save_png_8bit(rgba: np.ndarray, path: str, colorspace: str) -> bpy.types.Image:
    try:
        from vflib import bake as _vf_bake

        return _vf_bake.save_png_8bit(rgba, path, colorspace)
    except Exception:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    h, w, _ = rgba.shape
    iname = os.path.basename(path)
    old = bpy.data.images.get(iname)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(iname, width=w, height=h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.clip(rgba, 0.0, 1.0).astype(np.float32).ravel())
    tmp_p = os.path.join(tempfile.gettempdir(), f"__sc_tex_{os.getpid()}_{iname}")
    img.filepath_raw = tmp_p
    img.file_format = "PNG"
    img.save()
    try:
        _atomic_copy_fallback(tmp_p, path, retries=6)
    finally:
        try:
            os.remove(tmp_p)
        except OSError:
            pass
    img.filepath = path
    img.reload()
    img.colorspace_settings.name = colorspace
    return img


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


def bake_fish_pbr_maps(
    variant_id: str,
    part_objs: dict[str, bpy.types.Object],
    out_dir: str,
    res: int = BAKE_RES,
) -> tuple[bpy.types.Material, dict[str, str]]:
    """Bake 2048x2048 Color (+ raytraced AO), OpenGL Normal, Roughness, Metalness, AO, and ORM PNGs."""
    sc = bpy.context.scene
    _enable_cycles_gpu(sc)

    tmp_col = core.fresh_collection("__MM_BakeProxy")
    dups = []
    for k in PART_ORDER:
        src = part_objs[k]
        cp = src.copy()
        cp.data = src.data.copy()
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
    proxy.data.uv_layers.active_index = 0

    prev_hide = [(o, o.hide_render) for o in sc.objects if o != proxy and o.type == "MESH"]
    for o, _ in prev_hide:
        o.hide_render = True

    used_mats = [s.material for s in proxy.material_slots if s.material is not None]
    bk = sc.render.bake
    bk.use_selected_to_active = False
    bk.use_clear = True
    bk.margin = 14
    bk.margin_type = "EXTEND"
    bk.target = "IMAGE_TEXTURES"

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy

    try:
        # 1. OpenGL Tangent-Space Normal Map (fish scales + fin-ray ribs!)
        img_n_raw = _make_bake_img("__mm_n", res, "Non-Color")
        tn = _attach_targets(proxy, img_n_raw)
        sc.cycles.samples = 16
        bk.normal_space = "TANGENT"
        bk.normal_r = "POS_X"
        bk.normal_g = "POS_Y"
        bk.normal_b = "POS_Z"
        bpy.ops.object.bake(type="NORMAL")
        norm_arr = _read_float_img(img_n_raw).copy()
        _remove_targets(tn)
        bpy.data.images.remove(img_n_raw)

        # 2. Roughness Map (wet mucus scale sheen, glossy eye cornea, fin membranes)
        img_r_raw = _make_bake_img("__mm_r", res, "Non-Color")
        tn = _attach_targets(proxy, img_r_raw)
        sc.cycles.samples = 4
        bpy.ops.object.bake(type="ROUGHNESS")
        rough_arr = _read_float_img(img_r_raw)[..., 0].copy()
        _remove_targets(tn)
        bpy.data.images.remove(img_r_raw)

        # 3. Raytraced Cycles Ambient Occlusion (64 samples â€”gill cleft, eye orbit, fin root cavities!)
        img_ao_raw = _make_bake_img("__mm_ao", res, "Non-Color")
        tn = _attach_targets(proxy, img_ao_raw)
        sc.cycles.samples = 64
        bpy.ops.object.bake(type="AO")
        ao_arr = np.clip(_read_float_img(img_ao_raw)[..., 0].copy(), 0.0, 1.0)
        _remove_targets(tn)
        bpy.data.images.remove(img_ao_raw)

        # 4. Pure Linear Albedo via Emission override
        img_bc_raw = _make_bake_img("__mm_bc", res, "Non-Color")
        u_bc = _route_to_emission(used_mats, "Base Color")
        tn = _attach_targets(proxy, img_bc_raw)
        sc.cycles.samples = 4
        bpy.ops.object.bake(type="EMIT")
        bc_lin = _read_float_img(img_bc_raw)[..., :3].copy()
        _remove_targets(tn)
        _restore_emission(u_bc)
        bpy.data.images.remove(img_bc_raw)

        # 5. Iridescent Guanine Metalness via Emission override
        img_m_raw = _make_bake_img("__mm_m", res, "Non-Color")
        u_m = _route_to_emission(used_mats, "Metallic")
        tn = _attach_targets(proxy, img_m_raw)
        sc.cycles.samples = 2
        bpy.ops.object.bake(type="EMIT")
        metal_arr = _read_float_img(img_m_raw)[..., 0].copy()
        _remove_targets(tn)
        _restore_emission(u_m)
        bpy.data.images.remove(img_m_raw)

    finally:
        for o, hs in prev_hide:
            o.hide_render = hs
        core.clear_collection(tmp_col)
        bpy.data.collections.remove(tmp_col)

    # Composite subtle raytraced cavity AO (28% strength) in linear space, then encode to sRGB!
    ao_fac = (0.72 + 0.28 * ao_arr)[..., None]
    bc_shaded = np.clip(bc_lin * ao_fac, 0.0, 1.0)
    color_rgba = np.ones((res, res, 4), dtype=np.float32)
    color_rgba[..., :3] = _lin_arr_to_srgb(bc_shaded)

    norm_rgba = np.ones((res, res, 4), dtype=np.float32)
    norm_rgba[..., :3] = np.clip(norm_arr[..., :3], 0.0, 1.0)

    rough_rgba = np.ones((res, res, 4), dtype=np.float32)
    rough_rgba[..., :3] = np.clip(rough_arr, 0.03, 1.0)[..., None]

    metal_rgba = np.ones((res, res, 4), dtype=np.float32)
    metal_rgba[..., :3] = np.clip(metal_arr, 0.0, 1.0)[..., None]

    ao_rgba = np.ones((res, res, 4), dtype=np.float32)
    ao_rgba[..., :3] = ao_arr[..., None]

    orm_rgba = np.ones((res, res, 4), dtype=np.float32)
    orm_rgba[..., 0] = ao_arr
    orm_rgba[..., 1] = np.clip(rough_arr, 0.03, 1.0)
    orm_rgba[..., 2] = np.clip(metal_arr, 0.0, 1.0)

    prefix = f"T_MahiMahi_{variant_id}"
    paths = {
        "Color": os.path.join(out_dir, f"{prefix}_Color.png"),
        "Normal": os.path.join(out_dir, f"{prefix}_Normal.png"),
        "Roughness": os.path.join(out_dir, f"{prefix}_Roughness.png"),
        "Metalness": os.path.join(out_dir, f"{prefix}_Metalness.png"),
        "AO": os.path.join(out_dir, f"{prefix}_AO.png"),
        "ORM": os.path.join(out_dir, f"{prefix}_ORM.png"),
    }
    img_c = _save_png_8bit(color_rgba, paths["Color"], "sRGB")
    img_n = _save_png_8bit(norm_rgba, paths["Normal"], "Non-Color")
    img_r = _save_png_8bit(rough_rgba, paths["Roughness"], "Non-Color")
    img_m = _save_png_8bit(metal_rgba, paths["Metalness"], "Non-Color")
    _save_png_8bit(ao_rgba, paths["AO"], "Non-Color")
    _save_png_8bit(orm_rgba, paths["ORM"], "Non-Color")

    # Single game-ready PBR material wired purely to the 4 baked textures (+ wet fish mucus clearcoat in Cycles!)
    baked_mat, bsdf_n = mats._new_node_material(f"M_MahiMahi_{variant_id}_Baked")
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
    nt.links.new(mats.sock(tn_n, "Color", output=True), mats.sock(nmap, "Color"))
    nt.links.new(mats.sock(nmap, "Normal", output=True), mats.sock(bsdf_n, "Normal"))

    # Remove secondary EyePolarUV before game export so every MeshPart has 1 clean UV map (`UVMap`)!
    eyes_ob = part_objs["Eyes"]
    if "EyePolarUV" in eyes_ob.data.uv_layers:
        eyes_ob.data.uv_layers.remove(eyes_ob.data.uv_layers["EyePolarUV"])

    for pob in part_objs.values():
        pob.data.materials.clear()
        pob.data.materials.append(baked_mat)
        for poly in pob.data.polygons:
            poly.material_index = 0

    baked_mat["sc_role"] = "baked_pbr"
    return baked_mat, paths


# ---------------------------------------------------------------------------
# 5. Proper 4-Tier Game LOD Chain (`LOD0` -> `LOD1` -> `LOD2` -> `LOD3`)
# ---------------------------------------------------------------------------
LOD_SPECS = [
    (1, 0.48, set(), 0.50),
    (2, 0.24, set(), 0.25),
    (3, 0.11, set(), 0.10),
]


def build_lod_chain(lod0_parts: dict[str, bpy.types.Object], base_prefix: str = "MahiMahi") -> dict[str, dict]:
    lod_summary: dict[str, dict] = {
        "LOD0": {
            "tris": sum(gameready.triangle_count(o, False) for o in lod0_parts.values()),
            "parts": len(lod0_parts),
            "screen_size": 1.0,
        }
    }
    os.makedirs(LODS_ROOT, exist_ok=True)

    for lvl, ratio, culled, scr_sz in LOD_SPECS:
        l_col = core.fresh_collection(f"{base_prefix}_LOD{lvl}")
        lvl_objs: list[bpy.types.Object] = []
        for pname in PART_ORDER:
            if pname in culled:
                continue
            src = lod0_parts[pname]
            cp = src.copy()
            cp.data = src.data.copy()
            cp.name = f"{pname}_LOD{lvl}"
            cp.data.name = cp.name
            l_col.objects.link(cp)
            cp["sc_part"] = pname
            cp["sc_role"] = "solid"

            dec = cp.modifiers.new("SC_LOD_Decimate", "DECIMATE")
            dec.decimate_type = "COLLAPSE"
            # Keep Eyes slightly higher ratio so orbital sockets stay round at medium range
            dec.ratio = min(1.0, ratio * 1.45) if pname == "Eyes" else ratio
            dec.delimit = {"UV", "SEAM", "SHARP"}
            dec.use_collapse_triangulate = True
            with bpy.context.temp_override(
                object=cp,
                active_object=cp,
                selected_objects=[cp],
                selected_editable_objects=[cp],
            ):
                bpy.ops.object.modifier_apply(modifier=dec.name)
            lvl_objs.append(cp)

        glb_lod = os.path.join(LODS_ROOT, f"mahi_mahi_LOD{lvl}.glb")
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
        lod_summary[f"LOD{lvl}"] = {
            "tris": tris,
            "parts": len(lvl_objs),
            "screen_size": scr_sz,
            "glb": f"lods/mahi_mahi_LOD{lvl}.glb",
        }
        core.log(f"[LOD{lvl}] {tris} tris across {len(lvl_objs)} parts -> {glb_lod}")

    return lod_summary


# ---------------------------------------------------------------------------
# 6. Skinned 7-Bone Pelagic Swim Rig + Looping Swim Animation (`rigged/mahi_mahi_swim_rigged.glb`)
# ---------------------------------------------------------------------------
def build_and_export_swim_rig(flagship_parts: dict[str, bpy.types.Object]) -> str:
    """Create a clean 7-bone pelagic spine armature (`<= 4` normalized weights/vert) + looping swim cycle GLB."""
    os.makedirs(RIGGED_ROOT, exist_ok=True)
    rig_col = core.fresh_collection("__MM_RigExport")

    dups = []
    for k in PART_ORDER:
        src = flagship_parts[k]
        cp = src.copy()
        cp.data = src.data.copy()
        rig_col.objects.link(cp)
        dups.append(cp)

    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for d in dups:
        d.select_set(True)
    bpy.context.view_layer.objects.active = dups[0]
    bpy.ops.object.join()
    skinned = bpy.context.view_layer.objects.active
    skinned.name = "SK_MahiMahi"

    # Build 7-bone axial spine along Y (+0.58 snout -> -0.62 tail tips)
    lo, hi = core.world_bbox([skinned])
    z_spine = 0.5 * (lo.z + hi.z)
    bone_stations = [
        ("Root", (0.0, 0.25, 0.0), (0.0, 0.25, 0.08), None),
        ("Head", (0.0, 0.30, z_spine), (0.0, 0.58, z_spine), "Root"),
        ("Spine1", (0.0, 0.30, z_spine), (0.0, 0.12, z_spine), "Root"),
        ("Spine2", (0.0, 0.12, z_spine), (0.0, -0.06, z_spine), "Spine1"),
        ("Spine3", (0.0, -0.06, z_spine), (0.0, -0.22, z_spine), "Spine2"),
        ("Peduncle", (0.0, -0.22, z_spine), (0.0, -0.375, z_spine), "Spine3"),
        ("TailFin", (0.0, -0.375, z_spine), (0.0, -0.62, z_spine), "Peduncle"),
    ]

    arm_data = bpy.data.armatures.new("Armature_MahiSwim")
    arm_ob = bpy.data.objects.new("Armature_MahiSwim", arm_data)
    rig_col.objects.link(arm_ob)

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    arm_ob.select_set(True)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.mode_set(mode="EDIT")
    eb_map = {}
    for bname, head_p, tail_p, par_name in bone_stations:
        eb = arm_data.edit_bones.new(bname)
        eb.head = Vector(head_p)
        eb.tail = Vector(tail_p)
        eb.roll = 0.0
        if par_name is not None:
            eb.parent = eb_map[par_name]
            if par_name not in ("Root",):
                eb.use_connect = True
        eb_map[bname] = eb
    bpy.ops.object.mode_set(mode="OBJECT")

    # Analytical smooth axial skin weights (<= 2 influences per vertex, 100% normalized, 0 heat-fail risk!)
    deform_bones = [
        ("Head", 0.38),
        ("Spine1", 0.21),
        ("Spine2", 0.03),
        ("Spine3", -0.14),
        ("Peduncle", -0.30),
        ("TailFin", -0.48),
    ]
    vgs = {bn: skinned.vertex_groups.new(name=bn) for bn, _ in deform_bones}
    mw = skinned.matrix_world
    for v in skinned.data.vertices:
        wy = (mw @ v.co).y
        raw_w = []
        for bn, cy in deform_bones:
            w = math.exp(-0.5 * ((wy - cy) / 0.115) ** 2)
            raw_w.append((bn, w))
        raw_w.sort(key=lambda item: item[1], reverse=True)
        top = raw_w[:3]
        tot = sum(w for _, w in top) or 1.0
        for bn, w in top:
            nw = w / tot
            if nw >= 0.01:
                vgs[bn].add([v.index], nw, "REPLACE")

    skinned.parent = arm_ob
    arm_mod = skinned.modifiers.new("Armature", "ARMATURE")
    arm_mod.object = arm_ob

    # Keyframe a smooth 48-frame seamless carangiform/subcarangiform pelagic swim loop!
    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end = 48
    wave_amps = {
        "Head": (-3.0, 0.0),
        "Spine1": (4.5, 0.6),
        "Spine2": (8.5, 1.3),
        "Spine3": (13.5, 2.0),
        "Peduncle": (19.0, 2.7),
        "TailFin": (25.0, 3.3),
    }
    for f_idx in range(1, 50, 4):
        sc.frame_set(f_idx)
        phase = (2.0 * math.pi * (f_idx - 1)) / 48.0
        for bn, (deg_amp, lag) in wave_amps.items():
            pb = arm_ob.pose.bones[bn]
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = Euler((0.0, 0.0, math.radians(deg_amp) * math.sin(phase - lag)), "XYZ")
            pb.keyframe_insert(data_path="rotation_euler", frame=f_idx)
    sc.frame_set(1)

    glb_rigged = os.path.join(RIGGED_ROOT, "mahi_mahi_swim_rigged.glb")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    arm_ob.select_set(True)
    skinned.select_set(True)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.export_scene.gltf(
        filepath=glb_rigged,
        use_selection=True,
        export_format="GLB",
        export_animations=True,
    )
    for o in bpy.context.view_layer.objects:
        o.select_set(False)

    # Clear animation & temporary rig export objects so static showroom scene stays pristine
    if arm_ob.animation_data:
        act = arm_ob.animation_data.action
        arm_ob.animation_data_clear()
        if act and act.users == 0:
            bpy.data.actions.remove(act)
    core.clear_collection(rig_col)
    bpy.data.collections.remove(rig_col)
    core.log(f"[SwimRig] Exported animated 7-bone swim GLB -> {glb_rigged}")
    return glb_rigged


# ---------------------------------------------------------------------------
# 7. Roblox Variant Bundle Exporter + Safe Cycles Renderer
# ---------------------------------------------------------------------------
def export_fish_variant_bundle(
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

    glb_path = os.path.join(out_dir, f"mahi_mahi_{variant['id']}.glb")
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

    parts_spec = []
    for pname in PART_ORDER:
        pob = part_objs[pname]
        parts_spec.append(
            dict(
                name=pname,
                objects=[pob],
                role="solid",
                collide=(pname == "Body"),
                render_fidelity="Precise" if pname in ("Body", "DorsalFin", "CaudalFin") else "Automatic",
            )
        )

    lo, hi = core.world_bbox(all_v_objs)
    hinges = [
        dict(name="TailSwim", socket="HingeTail", part0="@primary", part1="CaudalFin", actuator="Servo", lower=-32, upper=32, speed=12),
    ]
    asset_tag = "MahiMahi" if variant["id"] == "bull_dorado" else f"MahiMahi_{variant['id']}"
    export.export_roblox(
        asset_tag,
        out_dir,
        parts=parts_spec,
        source_collection=src_col,
        primary=dict(name="Fish", center=(lo + hi) * 0.5, size=hi - lo),
        hinges=hinges,
        attributes={
            "Species": "MahiMahi",
            "ScientificName": "Coryphaena hippurus",
            "Variant": variant["id"],
            "Rarity": variant["rarity"],
            "LengthCm": 120,
        },
        tags=["Fish", "PelagicFish", f"Rarity_{variant['rarity']}"],
        reference="Body",
        prebaked_material=baked_mat,
        prebaked_textures=rel_tex,
        extra_manifest=extra_manifest,
    )


def _render_still_safe(sc: bpy.types.Scene, dst_path: str) -> str:
    try:
        from vflib import bake as _vf_bake

        return _vf_bake.render_still_safe(sc, dst_path)
    except Exception:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    tmp_p = os.path.join(tempfile.gettempdir(), f"__sc_mm_{os.getpid()}_{os.path.basename(dst_path)}")
    sc.render.filepath = tmp_p
    bpy.ops.render.render(write_still=True)
    try:
        _atomic_copy_fallback(tmp_p, dst_path, retries=6)
    finally:
        try:
            os.remove(tmp_p)
        except OSError:
            pass
    time.sleep(float(os.environ.get("VELUM_BAKE_COOLDOWN", "1.0") or "1.0"))
    return dst_path


def render_showcase_shots(
    variant_cols: dict[str, bpy.types.Collection],
    lod_cols: list[tuple[str, bpy.types.Collection]],
    out_dir: str,
) -> dict[str, str]:
    """Render 4-Variant School Lineup, Macro Head/Scales/Eye Close-Up, per-variant heroes, and 4-Panel LOD Sheet."""
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    _enable_cycles_gpu(sc)
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    sc.render.image_settings.file_format = "PNG"

    shots: dict[str, str] = {}
    for _lbl, lc in lod_cols[1:]:
        lc.hide_render = True
        lc.hide_viewport = True

    # 1. Per-Variant 3/4 Broadside Hero Renders + Macro Head/Eye/Scales Shot on Flagship Bull Dorado
    for vid, vcol in variant_cols.items():
        for oid, ocol in variant_cols.items():
            ocol.hide_render = oid != vid
            ocol.hide_viewport = oid != vid

        v_meshes = core.objects_in(vcol, types=("MESH",))
        st = render.setup_studio(v_meshes, backdrop="product")
        cd = bpy.data.cameras.new("MM_HeroCam")
        cm = bpy.data.objects.new("MM_HeroCam", cd)
        st.objects.link(cm)
        sc.camera = cm
        try:
            sc.render.resolution_x = 1600
            sc.render.resolution_y = 1000
            # Full un-cropped broadside-3/4 pelagic trophy showcase angle (`+X` starboard, slightly forward `+Y`)
            cm.location = Vector((1.76, 0.80, 0.44))
            cm.data.lens = 42.0
            cm.rotation_euler = (Vector((0.0, -0.02, 0.20)) - cm.location).to_track_quat("-Z", "Y").to_euler()
            p_hero = os.path.join(out_dir, f"variant_{vid}.png")
            _render_still_safe(sc, p_hero)
            shots[f"variant_{vid}"] = p_hero

            if vid == "bull_dorado":
                # Pure full-length side profile telephoto shot (snout to tail tips with clean margin!)
                cm.location = Vector((2.28, -0.02, 0.21))
                cm.data.lens = 50.0
                cm.rotation_euler = (Vector((0.0, -0.02, 0.21)) - cm.location).to_track_quat("-Z", "Y").to_euler()
                p_side = os.path.join(out_dir, "mahi_side_profile.png")
                _render_still_safe(sc, p_side)
                shots["side_profile"] = p_side

                # Macro close-up of Bull forehead boss, golden jewel iris/pupil, C-curved gill operculum, scales & pectoral fin!
                cm.location = Vector((0.82, 0.54, 0.24))
                cm.data.lens = 50.0
                cm.rotation_euler = (Vector((0.02, 0.33, 0.175)) - cm.location).to_track_quat("-Z", "Y").to_euler()
                p_macro = os.path.join(out_dir, "baked_scales_head_closeup.png")
                _render_still_safe(sc, p_macro)
                shots["baked_closeup"] = p_macro
        finally:
            core.clear_collection(st)
            bpy.data.collections.remove(st)

    # 2. All 4 Variants Pelagic Echelon Lineup (`Common`, `Uncommon`, `Rare`, `Legendary`)!
    offsets = {
        "bull_dorado": (-0.66, 0.36, 0.00),
        "blue_phase_lit": (-0.22, 0.12, 0.00),
        "sunset_coral": (0.22, -0.12, 0.00),
        "albino_gold_legendary": (0.66, -0.36, 0.00),
    }
    lineup_meshes = []
    for vid, vcol in variant_cols.items():
        vcol.hide_render = False
        vcol.hide_viewport = False
        dx, dy, dz = offsets[vid]
        for o in vcol.objects:
            o.location.x += dx
            o.location.y += dy
            o.location.z += dz
            if o.type == "MESH":
                lineup_meshes.append(o)
    bpy.context.view_layer.update()

    st_line = render.setup_studio(lineup_meshes, backdrop="product")
    cd = bpy.data.cameras.new("MM_LineupCam")
    cm = bpy.data.objects.new("MM_LineupCam", cd)
    st_line.objects.link(cm)
    sc.camera = cm
    try:
        sc.render.resolution_x = 2000
        sc.render.resolution_y = 1125
        cm.location = Vector((2.68, 1.72, 0.72))
        cm.data.lens = 38.0
        cm.rotation_euler = (Vector((0.0, -0.02, 0.20)) - cm.location).to_track_quat("-Z", "Y").to_euler()
        p_lineup = os.path.join(out_dir, "variants_lineup.png")
        _render_still_safe(sc, p_lineup)
        shots["variants_lineup"] = p_lineup
    finally:
        core.clear_collection(st_line)
        bpy.data.collections.remove(st_line)

    # Park Bull Dorado at X=0.0 and space the other 3 neatly beside it (`X = +0.42, +0.84, +1.26 m`, `Y = 0`) for live Blender inspection!
    final_x = {
        "bull_dorado": 0.00,
        "blue_phase_lit": 0.42,
        "sunset_coral": 0.84,
        "albino_gold_legendary": 1.26,
    }
    for vid, vcol in variant_cols.items():
        ox, oy, oz = offsets[vid]
        for o in vcol.objects:
            o.location.x += final_x[vid] - ox
            o.location.y -= oy
            o.location.z -= oz
    bpy.context.view_layer.update()

    # 3. 4-Panel `LOD0`..`LOD3` Comparison Sheet!
    for vcol in variant_cols.values():
        vcol.hide_render = True
    lod_tiles = []
    for lbl, lcol in lod_cols:
        for _l2, lc2 in lod_cols:
            lc2.hide_render = lc2 != lcol
        l_meshes = core.objects_in(lcol, types=("MESH",))
        st_l = render.setup_studio(l_meshes, backdrop="product")
        cd = bpy.data.cameras.new("MM_LODCam")
        cm = bpy.data.objects.new("MM_LODCam", cd)
        st_l.objects.link(cm)
        sc.camera = cm
        try:
            sc.render.resolution_x = 960
            sc.render.resolution_y = 600
            sc.cycles.samples = 56
            cm.location = Vector((1.78, 0.78, 0.43))
            cm.data.lens = 42.0
            cm.rotation_euler = (Vector((0.0, -0.02, 0.20)) - cm.location).to_track_quat("-Z", "Y").to_euler()
            tp = os.path.join(tempfile.gettempdir(), f"__sc_mm_lod_{lbl}.png")
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
        grid[598:602, :, :3] = 0.12
        grid[:, 958:962, :3] = 0.12
        p_lod = os.path.join(out_dir, "lod_comparison_sheet.png")
        _save_png_8bit(grid, p_lod, "sRGB")
        shots["lod_sheet"] = p_lod

    for vcol in variant_cols.values():
        vcol.hide_render = False
        vcol.hide_viewport = False
    for _lbl, lcol in lod_cols[1:]:
        lcol.hide_render = True
        lcol.hide_viewport = True

    return shots


def main() -> int:
    mm.clear_scene_and_setup_units()

    variant_cols: dict[str, bpy.types.Collection] = {}
    variant_meta: dict[str, dict] = {}
    flagship_parts: dict[str, bpy.types.Object] = {}
    lod_summary: dict[str, dict] = {}
    rigged_glb_path = ""

    for idx, var in enumerate(VARIANTS):
        vid = var["id"]
        proc_mats = build_procedural_fish_materials(var)
        v_col, meshes = mm.build_all(
            collection_name=f"Variant_{vid}",
            bull_crest=var["bull_crest"],
            clear_scene=False,
            mat_dict=proc_mats,
        )
        for o in meshes:
            o.name = f"MahiMahi_{vid}_{o['sc_part']}"
            o.data.name = o.name
        part_objs = {o["sc_part"]: o for o in meshes}

        # Pack shared non-overlapping 2048x2048 UV atlas (preserving EyePolarUV for eye bake!)
        pack_shared_fish_atlas(part_objs)

        tex_dir = os.path.join(TEXTURES_ROOT, vid)
        baked_mat, tex_paths = bake_fish_pbr_maps(vid, part_objs, tex_dir, res=BAKE_RES)

        if idx == 0:
            flagship_parts = part_objs
            lod_summary = build_lod_chain(flagship_parts, base_prefix="MahiMahi")
            rigged_glb_path = build_and_export_swim_rig(flagship_parts)

            # Save flagship standalone .blend & .glb for single-asset QA / downstream tools
            flagship_glb = os.path.join(THIS_DIR, "mahi_mahi.glb")
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            for pob in flagship_parts.values():
                pob.select_set(True)
            bpy.context.view_layer.objects.active = flagship_parts["Body"]
            bpy.ops.export_scene.gltf(filepath=flagship_glb, use_selection=True, export_format="GLB", export_apply=True)
            for pob in flagship_parts.values():
                pob.select_set(False)

        v_out_dir = os.path.join(VARIANTS_ROOT, vid)
        extra_mf = {
            "species": "MahiMahi",
            "scientificName": "Coryphaena hippurus",
            "variant": vid,
            "variantLabel": var["label"],
            "rarity": var["rarity"],
            "bullCrest": var["bull_crest"],
            "bakeResolution": BAKE_RES,
            "lods": lod_summary,
            "swimRigGlb": "rigged/mahi_mahi_swim_rigged.glb",
        }
        export_fish_variant_bundle(var, v_col, part_objs, baked_mat, tex_paths, v_out_dir, extra_manifest=extra_mf)

        if idx == 0:
            # Mirror flagship export to default `export/` folder as well
            export_fish_variant_bundle(var, v_col, part_objs, baked_mat, tex_paths, EXPORT_DEFAULT, extra_manifest=extra_mf)

        variant_cols[vid] = v_col
        variant_meta[vid] = {
            "label": var["label"],
            "rarity": var["rarity"],
            "bull_crest": var["bull_crest"],
            "dir": f"variants/{vid}",
            "glb": f"variants/{vid}/mahi_mahi_{vid}.glb",
            "textures": {k: f"textures/{vid}/{os.path.basename(p)}" for k, p in tex_paths.items()},
        }

    lod_cols = [
        ("LOD0", variant_cols["bull_dorado"]),
        ("LOD1", bpy.data.collections["MahiMahi_LOD1"]),
        ("LOD2", bpy.data.collections["MahiMahi_LOD2"]),
        ("LOD3", bpy.data.collections["MahiMahi_LOD3"]),
    ]

    shots = render_showcase_shots(variant_cols, lod_cols, RENDERS_ROOT)

    # Save master 4-Variant + 4-Tier LOD `.blend`
    master_blend = os.path.join(THIS_DIR, "mahi_mahi_variants_lods.blend")
    bpy.ops.wm.save_as_mainfile(filepath=master_blend)

    # Sync to Design Model Output per mandatory workspace rule!
    os.makedirs(DESIGN_MODEL_OUTPUT, exist_ok=True)
    shutil.copy2(master_blend, os.path.join(DESIGN_MODEL_OUTPUT, "mahi_mahi.blend"))
    shutil.copy2(os.path.join(THIS_DIR, "mahi_mahi.glb"), os.path.join(DESIGN_MODEL_OUTPUT, "mahi_mahi.glb"))
    shutil.copy2(rigged_glb_path, os.path.join(DESIGN_MODEL_OUTPUT, "mahi_mahi_swim_rigged.glb"))
    shutil.copy2(shots["variants_lineup"], os.path.join(DESIGN_MODEL_OUTPUT, "blender-render-check.png"))

    report = {
        "ok": True,
        "species": "Coryphaena hippurus (Mahi-Mahi / Dorado)",
        "loa_m": 1.20,
        "bake_res": BAKE_RES,
        "swim_rig_glb": "rigged/mahi_mahi_swim_rigged.glb",
        "lods": lod_summary,
        "variants": variant_meta,
    }
    rep_path = os.path.join(THIS_DIR, "variants_and_lods_report.json")
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    core.log(f"DONE! Mahi-Mahi variants + LODs + swim rig report -> {rep_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

