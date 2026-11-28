r"""Bake 2048x2048 Cycles PBR Textures, Build 4-Level LOD Chain & Generate 4 Showroom Variants for Sunrunner 24.

Pipeline stages:
  1. Build clean parametric LOD0 source geometry via `build_sunrunner_24.build_all()` (0 shell breaches).
  2. Author procedural marine surface shaders (planked Burmese teak + black thiokol caulk grooves,
     45-deg molded diamond non-skid, pebble-grain marine leather, brushed anodized aluminum,
     Garmin glass-bridge MFD chartplotter/sonar UI, gelcoat/antifouling micro-roughness breakup).
  3. Collapse into the 13 game-ready `MeshPart`s (`Hull`, `PaintPrimary`, `Deck`, `Console`, `Glass`,
     `LeaningPost`, `TTop`, `TrimHardware`, `Lights`, `Steering`, `Throttle`, `Motor`, `Prop`) and pack
     a single shared, non-overlapping 2048x2048 UV atlas across all 11 opaque parts.
  4. Bake real 2048x2048 Cycles OPTIX GPU PBR texture sets (`Color`, `Normal` OpenGL, `Roughness`,
     `Metalness`, `AO`, `ORM`) for 4 distinct showroom variants:
       - `bahama_teal`       : Flagship Offshore Sportfisher (Deep Bahama Teal, Oyster/Slate, Burmese Teak, Black V8)
       - `boca_grande_ice`   : Luxury Yacht Tender (Ice Blue-Mist, Pearl-White 300 V8, Saddle-Camel Leather, Blonde Teak)
       - `midnight_blackout` : Stealth Carbon Sport (Jet Anthracite, Blackout Tower, Crimson Stripe/Piping, Grey SeaDek)
       - `harbor_patrol`     : Coast Guard / Marine Police Interceptor (Rescue Orange + Blue, Rooftop Strobe Lightbars, Tactical Deck)
  5. Generate proper 4-tier LOD hierarchy (`LOD0` 97k -> `LOD1` ~46k -> `LOD2` ~21k -> `LOD3` ~9.5k tris)
     sharing the exact baked 2048x2048 PBR material & articulated `Steering`/`Throttle`/`Motor`/`Prop` pivots.
  6. Export per-variant Roblox FBX + Manifest + `studio_setup.luau` + GLB, per-LOD GLB/FBX, save the
     4-variant + LOD showroom `.blend`, and render verification sheets (`variants_lineup.png`,
     `baked_teak_nonskid_closeup.png`, `lod_comparison_sheet.png`, and per-variant hero shots).

Usage:
    & "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --python-exit-code 1 -P "assets\models\sunrunner_24\bake_lod_variants.py"
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys

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

import build_sunrunner_24 as sr  # noqa: E402
from sclib import core, export, gameready, geo, mats, render  # noqa: E402

BAKE_RES = 2048
BAKE_MARGIN_PX = 12
TEXTURES_ROOT = os.path.join(THIS_DIR, "textures")
VARIANTS_ROOT = os.path.join(THIS_DIR, "variants")
LODS_ROOT = os.path.join(THIS_DIR, "lods")
EXPORT_DIR = os.path.join(THIS_DIR, "export")
RENDERS_DIR = os.path.join(THIS_DIR, "renders")
DESIGN_OUTPUT_DIR = core.DESIGN_OUTPUT_DIR

OPAQUE_PARTS = (
    "Hull",
    "PaintPrimary",
    "Deck",
    "Console",
    "LeaningPost",
    "TTop",
    "TrimHardware",
    "Steering",
    "Throttle",
    "Motor",
    "Prop",
)

# ---------------------------------------------------------------------------
# 4 Distinct Showroom Variants (Livery + Upholstery + Engine + Patrol Gear)
# ---------------------------------------------------------------------------
VARIANTS: list[dict] = [
    {
        "id": "bahama_teal",
        "label": "Sunrunner 24 â€” Bahama Teal Offshore",
        "patrol_gear": False,
        "deck_style": "teak",
        "colors": {
            "SR_HullWhite": ("#F5F7FA", 0.15, 0.0),
            "SR_HullTeal": ("#0B556A", 0.30, 0.05),
            "SR_BootNavy": ("#146B85", 0.20, 0.0),
            "SR_AntiFoul": ("#1E242D", 0.64, 0.0),
            "SR_NonSkid": ("#4C6075", 0.88, 0.0),
            "SR_Teak": ("#8A6240", 0.52, 0.0),
            "SR_ConsoleGrey": ("#E8EDF2", 0.24, 0.0),
            "SR_DashDark": ("#181D24", 0.38, 0.0),
            "SR_VinylOyster": ("#E5DCCC", 0.46, 0.0),
            "SR_VinylCamel": ("#A8794E", 0.46, 0.0),
            "SR_VinylSlate": ("#232E3D", 0.50, 0.0),
            "SR_RubberBlack": ("#16191E", 0.78, 0.0),
            "SR_Aluminum": ("#CFD8E2", 0.22, 0.88),
            "SR_Stainless": ("#DCE3EC", 0.14, 0.94),
            "SR_PropStainless": ("#BAC4D0", 0.20, 0.90),
            "SR_MotorCowl": ("#1B2028", 0.24, 0.36),
            "SR_MotorSilver": ("#A5B1BF", 0.22, 0.84),
        },
        "glass_color": "#0B2536",
        "glass_alpha": 0.45,
    },
    {
        "id": "boca_grande_ice",
        "label": "Sunrunner 24 â€” Boca Grande Ice & Pearl V8",
        "patrol_gear": False,
        "deck_style": "teak",
        "colors": {
            "SR_HullWhite": ("#F7F9FB", 0.14, 0.0),
            "SR_HullTeal": ("#79AEC6", 0.24, 0.04),       # Ice Blue-Mist topside gelcoat
            "SR_BootNavy": ("#0F2847", 0.18, 0.0),       # Classic Yacht Navy boot stripe
            "SR_AntiFoul": ("#192331", 0.62, 0.0),
            "SR_NonSkid": ("#6D7F91", 0.86, 0.0),
            "SR_Teak": ("#A68056", 0.48, 0.0),           # Golden Blonde Burmese Teak
            "SR_ConsoleGrey": ("#F2F5F8", 0.20, 0.0),
            "SR_DashDark": ("#17202B", 0.36, 0.0),
            "SR_VinylOyster": ("#B37B4C", 0.44, 0.0),    # Saddle-Camel Tan Luxury Upholstery
            "SR_VinylCamel": ("#F0E8DC", 0.46, 0.0),
            "SR_VinylSlate": ("#3B2618", 0.48, 0.0),     # Espresso Contrast Piping & Bolster Roll
            "SR_RubberBlack": ("#1A1E24", 0.76, 0.0),
            "SR_Aluminum": ("#EEF2F6", 0.20, 0.25),      # White Powder-Coated T-Top & Leaning Post!
            "SR_Stainless": ("#DCE3EC", 0.14, 0.94),
            "SR_PropStainless": ("#C4CDD8", 0.18, 0.92),
            "SR_MotorCowl": ("#EEF2F7", 0.18, 0.18),     # Pearlescent Offshore White 300HP V8!
            "SR_MotorSilver": ("#163252", 0.24, 0.55),   # Navy Metallic Speed Spear on White V8!
        },
        "glass_color": "#103244",
        "glass_alpha": 0.42,
    },
    {
        "id": "midnight_blackout",
        "label": "Sunrunner 24 â€” Midnight Carbon Blackout",
        "patrol_gear": False,
        "deck_style": "seadek_grey",
        "colors": {
            "SR_HullWhite": ("#CFD6DF", 0.18, 0.05),     # Cool Titanium lower chine & liner
            "SR_HullTeal": ("#0C0F14", 0.22, 0.35),      # Murdered-Out Jet Carbon Metallic topsides!
            "SR_BootNavy": ("#C81922", 0.18, 0.05),      # Aggressive Crimson-Red Boot-Top Stripe!
            "SR_AntiFoul": ("#0B0D11", 0.68, 0.0),
            "SR_NonSkid": ("#1E232B", 0.90, 0.0),        # Dark Stealth Charcoal Non-Skid
            "SR_Teak": ("#3A414B", 0.68, 0.0),           # Brushed Storm-Grey EVA SeaDek Planks!
            "SR_ConsoleGrey": ("#151921", 0.28, 0.15),   # Stealth Dark Graphite Console Body
            "SR_DashDark": ("#0B0D11", 0.34, 0.0),
            "SR_VinylOyster": ("#1B2028", 0.46, 0.0),    # Jet Charcoal Sport Vinyl
            "SR_VinylCamel": ("#14181F", 0.48, 0.0),
            "SR_VinylSlate": ("#C81922", 0.44, 0.0),     # Crimson-Red Contrast Cushion Piping!
            "SR_RubberBlack": ("#0D0F13", 0.80, 0.0),
            "SR_Aluminum": ("#11151B", 0.30, 0.55),      # Matte Blackout Powder-Coated Tower!
            "SR_Stainless": ("#AEB8C4", 0.18, 0.90),
            "SR_PropStainless": ("#9BA5B2", 0.22, 0.88),
            "SR_MotorCowl": ("#0C0F14", 0.20, 0.45),     # Stealth Phantom Black V8
            "SR_MotorSilver": ("#C81922", 0.24, 0.35),   # Crimson Racing Spear on V8 Cowl!
        },
        "glass_color": "#06090E",
        "glass_alpha": 0.65,
    },
    {
        "id": "harbor_patrol",
        "label": "Sunrunner 24 â€” Coast Guard / Harbor Patrol",
        "patrol_gear": True,
        "deck_style": "tactical_nonskid",
        "colors": {
            "SR_HullWhite": ("#F2F5F8", 0.18, 0.0),
            "SR_HullTeal": ("#D43508", 0.32, 0.0),       # Deep Saturated USCG Rescue Orange!
            "SR_BootNavy": ("#0D3B82", 0.20, 0.0),       # Law-Enforcement Command Blue Stripe!
            "SR_AntiFoul": ("#14181F", 0.66, 0.0),
            "SR_NonSkid": ("#2B323C", 0.92, 0.0),        # Heavy-Duty Tactical Grey Deck
            "SR_Teak": ("#232932", 0.90, 0.0),           # Tactical Non-Skid Aft Deck (no yacht wood!)
            "SR_ConsoleGrey": ("#DCE2E9", 0.28, 0.0),
            "SR_DashDark": ("#11151B", 0.40, 0.0),
            "SR_VinylOyster": ("#1B2027", 0.54, 0.0),    # Heavy-Duty Black Tactical Cordura Seating
            "SR_VinylCamel": ("#151920", 0.55, 0.0),
            "SR_VinylSlate": ("#D43508", 0.48, 0.0),     # High-Vis Orange Safety Welt Trim
            "SR_RubberBlack": ("#101216", 0.84, 0.0),
            "SR_Aluminum": ("#181D24", 0.34, 0.50),      # Tactical Anodized Dark Gunmetal Frame
            "SR_Stainless": ("#CFD7E0", 0.18, 0.90),
            "SR_PropStainless": ("#B4BECB", 0.22, 0.88),
            "SR_MotorCowl": ("#12161C", 0.28, 0.30),
            "SR_MotorSilver": ("#D43508", 0.28, 0.15),   # Patrol Orange Cowl Identification Band
        },
        "glass_color": "#102436",
        "glass_alpha": 0.38,
    },
]


def _enable_cycles_gpu(sc: bpy.types.Scene) -> str:
    try:
        from vflib import bake as _vf_bake

        return _vf_bake.enable_cycles_gpu(sc, use_denoising=True)
    except Exception:
        pass
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
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
        for dt in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dt
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == dt]
                if devs:
                    for d in prefs.devices:
                        d.use = (d.type == dt)
                    sc.cycles.device = "GPU"
                    backend = dt
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


def _srgb_to_lin(hex_str: str) -> tuple[float, float, float]:
    return mats.linear(hex_str)


def _lin_arr_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.maximum(x, 1e-8), 1.0 / 2.4) - 0.055)


def _mix_rgba(
    nt: bpy.types.NodeTree,
    loc: tuple[float, float],
    col_a: tuple[float, float, float, float] | None = None,
    col_b: tuple[float, float, float, float] | None = None,
):
    """Create a Blender 5.2 RGBA ShaderNodeMix and return (node, fac_in, a_in, b_in, res_out)."""
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.clamp_result = True
    mx.location = loc
    fac_in = mx.inputs[0]
    a_in = mx.inputs[6]
    b_in = mx.inputs[7]
    res_out = mx.outputs[2]
    if col_a is not None:
        a_in.default_value = col_a
    if col_b is not None:
        b_in.default_value = col_b
    return mx, fac_in, a_in, b_in, res_out


# ---------------------------------------------------------------------------
# 1. Procedural Marine Shader Networks (Teak Planks, Diamond Non-Skid, Leather, MFD)
# ---------------------------------------------------------------------------
def build_procedural_material(mat_name: str, hex_col: str, rough: float, metal: float, *, deck_style: str = "teak") -> bpy.types.Material:
    """Author a procedural Blender 5.2 shader graph ready for Cycles baking."""
    mat = mats.pbr(mat_name, hex_col, roughness=rough, metallic=metal)
    nt = mat.node_tree
    b = mats.bsdf(mat)
    base_lin = _srgb_to_lin(hex_col)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1100, 0)

    if mat_name == "SR_Teak" and deck_style in ("teak", "seadek_grey"):
        # 62 mm wide fore-aft planks w/ 3.5 mm recessed black thiokol caulk seams + stretched wood/EVA grain!
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        sep.location = (-900, 180)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(sep, "Vector"))

        # Modulo plank phase: abs(fract(x / 0.062) - 0.5) -> < 0.032 is caulk seam!
        div = nt.nodes.new("ShaderNodeMath")
        div.operation = "DIVIDE"
        div.inputs[1].default_value = 0.062
        div.location = (-720, 220)
        nt.links.new(sep.outputs["X"], div.inputs[0])

        frac = nt.nodes.new("ShaderNodeMath")
        frac.operation = "FRACT"
        frac.location = (-560, 220)
        nt.links.new(div.outputs[0], frac.inputs[0])

        # Seam mask: 1.0 in plank body, 0.0 inside dark caulk seam at edges (u < 0.035 or u > 0.965)
        sub = nt.nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[1].default_value = 0.5
        sub.location = (-400, 220)
        nt.links.new(frac.outputs[0], sub.inputs[0])

        absm = nt.nodes.new("ShaderNodeMath")
        absm.operation = "ABSOLUTE"
        absm.location = (-240, 220)
        nt.links.new(sub.outputs[0], absm.inputs[0])

        seam_ramp = nt.nodes.new("ShaderNodeMapRange")
        seam_ramp.clamp = True
        seam_ramp.inputs["From Min"].default_value = 0.455
        seam_ramp.inputs["From Max"].default_value = 0.478
        seam_ramp.inputs["To Min"].default_value = 1.0  # plank center
        seam_ramp.inputs["To Max"].default_value = 0.0  # dark caulk groove!
        seam_ramp.location = (-80, 220)
        nt.links.new(absm.outputs[0], seam_ramp.inputs["Value"])

        # Fine stretched fore-aft wood fiber noise
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (28.0, 3.2, 12.0)
        mp.location = (-900, -120)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(mp, "Vector"))

        noise = nt.nodes.new("ShaderNodeTexNoise")
        mats.set_in(noise, "Scale", 8.5)
        mats.set_in(noise, "Detail", 6.0)
        mats.set_in(noise, "Roughness", 0.65)
        noise.location = (-680, -120)
        nt.links.new(mats.sock(mp, "Vector", output=True), mats.sock(noise, "Vector"))

        # Mix plank light/dark grain, then mix with black caulk seam (#141210)
        _gm, gm_fac, _gm_a, _gm_b, gm_out = _mix_rgba(
            nt,
            (-420, -40),
            tuple(c * 0.78 for c in base_lin) + (1.0,),
            tuple(min(1.0, c * 1.20) for c in base_lin) + (1.0,),
        )
        nt.links.new(mats.sock(noise, "Fac", output=True), gm_fac)

        _cm, cm_fac, _cm_a, cm_b, cm_out = _mix_rgba(
            nt,
            (-180, 40),
            (0.008, 0.007, 0.006, 1.0),  # crisp recessed black marine thiokol caulk!
            None,
        )
        nt.links.new(seam_ramp.outputs["Result"], cm_fac)
        nt.links.new(gm_out, cm_b)
        nt.links.new(cm_out, mats.sock(b, "Base Color"))

        # Roughness: caulk = 0.88, plank = rough Â± 0.07
        r_map = nt.nodes.new("ShaderNodeMapRange")
        r_map.inputs["To Min"].default_value = 0.88
        r_map.inputs["To Max"].default_value = rough
        r_map.location = (-180, -180)
        nt.links.new(seam_ramp.outputs["Result"], r_map.inputs["Value"])
        nt.links.new(r_map.outputs["Result"], mats.sock(b, "Roughness"))

        # Normal bump: recessed caulk groove + subtle fiber grain!
        h_add = nt.nodes.new("ShaderNodeMath")
        h_add.operation = "MULTIPLY_ADD"
        h_add.inputs[1].default_value = 0.14
        h_add.location = (-360, -300)
        nt.links.new(mats.sock(noise, "Fac", output=True), h_add.inputs[0])
        nt.links.new(seam_ramp.outputs["Result"], h_add.inputs[2])

        bump = nt.nodes.new("ShaderNodeBump")
        mats.set_in(bump, "Strength", 0.65)
        mats.set_in(bump, "Distance", 0.0022)
        bump.location = (-160, -320)
        nt.links.new(h_add.outputs[0], mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))

    elif mat_name == "SR_NonSkid" or (mat_name == "SR_Teak" and deck_style == "tactical_nonskid"):
        # 45-deg molded diamond marine non-skid pattern!
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(45.0))
        mp.inputs["Scale"].default_value = (135.0, 135.0, 135.0)
        mp.location = (-880, -80)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(mp, "Vector"))

        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.feature = "F1"
        vor.distance = "MANHATTAN"  # True 45-degree diamond pyramids!
        mats.set_in(vor, "Randomness", 0.08)
        mats.set_in(vor, "Scale", 1.0)
        vor.location = (-640, -80)
        nt.links.new(mats.sock(mp, "Vector", output=True), mats.sock(vor, "Vector"))

        _nm, nm_fac, _nm_a, _nm_b, nm_out = _mix_rgba(
            nt,
            (-320, 80),
            tuple(min(1.0, c * 1.10) for c in base_lin) + (1.0,),
            tuple(c * 0.84 for c in base_lin) + (1.0,),
        )
        nt.links.new(mats.sock(vor, "Distance", output=True), nm_fac)
        nt.links.new(nm_out, mats.sock(b, "Base Color"))

        r_mr = nt.nodes.new("ShaderNodeMapRange")
        r_mr.inputs["To Min"].default_value = max(0.55, rough - 0.10)
        r_mr.inputs["To Max"].default_value = min(0.98, rough + 0.06)
        r_mr.location = (-320, -100)
        nt.links.new(mats.sock(vor, "Distance", output=True), r_mr.inputs["Value"])
        nt.links.new(r_mr.outputs["Result"], mats.sock(b, "Roughness"))

        bump = nt.nodes.new("ShaderNodeBump")
        bump.invert = True
        mats.set_in(bump, "Strength", 0.55)
        mats.set_in(bump, "Distance", 0.0018)
        bump.location = (-260, -280)
        nt.links.new(mats.sock(vor, "Distance", output=True), mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))

    elif mat_name in ("SR_VinylOyster", "SR_VinylCamel", "SR_VinylSlate"):
        # Fine marine pebble-leather grain
        mats.add_bump_noise(mat, scale=360.0, strength=0.28, distance=0.0012, kind="voronoi", roughness_variation=0.06)

    elif mat_name == "SR_ScreenGlow":
        # Garmin Glass-Bridge Chartplotter / Bathymetric Sonar UI (anti-glare satin screen so softbox doesn't wash out!)
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "RINGS"
        mats.set_in(wave, "Scale", 18.0)
        mats.set_in(wave, "Distortion", 4.2)
        wave.location = (-680, -120)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(wave, "Vector"))

        _sm, sm_fac, _sm_a, _sm_b, sm_out = _mix_rgba(
            nt,
            (-320, 60),
            (0.004, 0.038, 0.095, 1.0),  # deep ocean chart background
            (0.045, 0.620, 0.780, 1.0),  # glowing cyan sonar contour rings
        )
        nt.links.new(mats.sock(wave, "Fac", output=True), sm_fac)
        nt.links.new(sm_out, mats.sock(b, "Base Color"))
        mats.set_in(b, "Roughness", 0.34)

    elif metal >= 0.5:
        # Brushed marine anodized aluminum / 316 stainless micro-grain
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (18.0, 140.0, 140.0)
        mp.location = (-880, -160)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(mp, "Vector"))
        ns = nt.nodes.new("ShaderNodeTexNoise")
        mats.set_in(ns, "Scale", 6.0)
        mats.set_in(ns, "Detail", 5.0)
        ns.location = (-640, -160)
        nt.links.new(mats.sock(mp, "Vector", output=True), mats.sock(ns, "Vector"))
        r_mr = nt.nodes.new("ShaderNodeMapRange")
        r_mr.inputs["To Min"].default_value = max(0.06, rough - 0.05)
        r_mr.inputs["To Max"].default_value = min(0.60, rough + 0.06)
        r_mr.location = (-340, -120)
        nt.links.new(mats.sock(ns, "Fac", output=True), r_mr.inputs["Value"])
        nt.links.new(r_mr.outputs["Result"], mats.sock(b, "Roughness"))
        bump = nt.nodes.new("ShaderNodeBump")
        mats.set_in(bump, "Strength", 0.10)
        mats.set_in(bump, "Distance", 0.0005)
        bump.location = (-340, -280)
        nt.links.new(mats.sock(ns, "Fac", output=True), mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))
    else:
        # Subtle gelcoat / antifouling surface roughness breakup (never sterile flat plastic!)
        mats.add_bump_noise(mat, scale=85.0, strength=0.06, distance=0.0004, kind="noise", roughness_variation=0.035)

    return mat


def apply_variant_materials(variant: dict) -> dict[str, bpy.types.Material]:
    """Rebuild all SR_* materials in-place with the variant's palette & procedural detail."""
    built: dict[str, bpy.types.Material] = {}
    for mat_name, (hex_c, r_val, m_val) in variant["colors"].items():
        built[mat_name] = build_procedural_material(
            mat_name, hex_c, r_val, m_val, deck_style=variant["deck_style"]
        )
    # ScreenGlow + per-variant Glass + Emissive Nav/Patrol Lights
    vid = variant["id"]
    built["SR_ScreenGlow"] = build_procedural_material("SR_ScreenGlow", "#0E384D", 0.08, 0.0)
    built["SR_WindshieldGlass"] = mats.pbr(
        f"M_Sunrunner24_{vid}_Glass",
        variant["glass_color"],
        roughness=0.04,
        coat=0.7,
        specular=0.92,
        transmission=0.0,
        alpha=variant["glass_alpha"],
        role="glass",
        roblox_material="Glass",
    )
    built["SR_NavRed"] = mats.pbr("SR_NavRed", "#FF2424", roughness=0.12, emission="#FF2424", emission_strength=3.5, role="neon")
    built["SR_NavGreen"] = mats.pbr("SR_NavGreen", "#1EE65A", roughness=0.12, emission="#1EE65A", emission_strength=3.5, role="neon")
    built["SR_LightWhite"] = mats.pbr("SR_LightWhite", "#FFFDF6", roughness=0.10, emission="#FFFDF6", emission_strength=2.8, role="neon")
    built["SR_StrobeBlue"] = mats.pbr("SR_StrobeBlue", "#1A6BFF", roughness=0.08, emission="#1A6BFF", emission_strength=4.2, role="neon")
    return built


def add_harbor_patrol_equipment(col: bpy.types.Collection, v_mats: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    """Add authentic Law-Enforcement / Coast Guard rooftop dual LED strobe lightbars & bow searchlight!"""
    added: list[bpy.types.Object] = []
    # Dual low-profile armored LED emergency lightbar pods on port & starboard T-top roof!
    for side, sx, lens_mat in (("Port", -0.34, v_mats["SR_NavRed"]), ("Starboard", 0.34, v_mats["SR_StrobeBlue"])):
        plinth = sr.build_box(
            f"Patrol_LightbarBase_{side}",
            (0.34, 0.14, 0.032),
            col,
            v_mats["SR_DashDark"],
            location=(sx, 0.48, 2.742),
            bevel=0.006,
            part="TTop",
        )
        cap = sr.build_box(
            f"Patrol_LightbarCap_{side}",
            (0.35, 0.15, 0.016),
            col,
            v_mats["SR_Aluminum"],
            location=(sx, 0.48, 2.792),
            bevel=0.005,
            part="TTop",
        )
        lens = sr.build_box(
            f"Patrol_LightbarStrobe_{side}",
            (0.32, 0.125, 0.036),
            col,
            lens_mat,
            location=(sx, 0.48, 2.768),
            bevel=0.006,
            part="Lights",
            role="neon",
        )
        added.extend([plinth, cap, lens])

    # Remote-controlled forward hardtop marine searchlight pod
    s_ped = geo.cylinder("Patrol_SearchlightPed", 0.034, 0.052, col, v_mats["SR_DashDark"], location=(0.0, 0.92, 2.715), seg=18, bevel=0.004)
    sr.finalize_mesh(s_ped, part="TTop")
    s_head = sr.build_box("Patrol_SearchlightBody", (0.13, 0.15, 0.105), col, v_mats["SR_HullWhite"], location=(0.0, 0.94, 2.785), bevel=0.014, part="TTop")
    s_lens = sr.build_box("Patrol_SearchlightLens", (0.10, 0.020, 0.075), col, v_mats["SR_LightWhite"], location=(0.0, 1.012, 2.785), bevel=0.004, part="Lights", role="neon")
    added.extend([s_ped, s_head, s_lens])
    return added


# ---------------------------------------------------------------------------
# 2. Collapse into 13 Game-Ready Parts & Pack Shared Non-Overlapping 2K UV Atlas
# ---------------------------------------------------------------------------
def build_joined_lod0_parts(src_col: bpy.types.Collection, dest_col_name: str) -> tuple[bpy.types.Collection, dict[str, bpy.types.Object]]:
    """Join source sub-meshes by `sc_part` into 13 clean world-space LOD0 MeshParts."""
    dest_col = core.fresh_collection(dest_col_name)
    groups: dict[str, list[bpy.types.Object]] = {}
    for ob in core.objects_in(src_col, types=("MESH",)):
        pname = ob.get("sc_part")
        if pname and not ob.hide_render:
            groups.setdefault(pname, []).append(ob)

    part_objs: dict[str, bpy.types.Object] = {}
    for pname, srcs in groups.items():
        baked_copies = [gameready.bake_object(o, f"__{dest_col_name}_{pname}_{i}", dest_col) for i, o in enumerate(srcs)]
        joined = gameready.join(baked_copies, f"{dest_col_name}_{pname}")
        gameready.collapse_materials(joined)
        joined["sc_part"] = pname
        joined["sc_role"] = srcs[0].get("sc_role", "solid")
        # Ensure single consistent UV map named "UVMap"
        while len(joined.data.uv_layers) > 1:
            joined.data.uv_layers.remove(joined.data.uv_layers[-1])
        if not joined.data.uv_layers:
            joined.data.uv_layers.new(name="UVMap")
        else:
            joined.data.uv_layers[0].name = "UVMap"
        joined.data.uv_layers.active_index = 0
        # Temporarily split material-boundary edges so smart_project isolates boot-stripes/reveals into separate UV islands!
        bm_s = bmesh.new()
        bm_s.from_mesh(joined.data)
        mat_border_edges = [ed for ed in bm_s.edges if len({f.material_index for f in ed.link_faces}) > 1]
        if mat_border_edges:
            bmesh.ops.split_edges(bm_s, edges=mat_border_edges)
        bm_s.to_mesh(joined.data)
        bm_s.free()
        part_objs[pname] = joined

    # Pack all opaque textured MeshParts onto ONE shared non-overlapping [0..1]^2 UV atlas!
    opaque = [part_objs[k] for k in OPAQUE_PARTS if k in part_objs]
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in opaque:
        o.select_set(True)
    bpy.context.view_layer.objects.active = opaque[0]
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(62.0), island_margin=0.004, correct_aspect=True, scale_to_bounds=False)
        bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.004)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        for o in opaque:
            o.select_set(False)

    # Re-weld 3D vertices back to 100% watertight while preserving the isolated per-loop UVs!
    for o in opaque:
        bm_w = bmesh.new()
        bm_w.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm_w, verts=bm_w.verts[:], dist=1e-6)
        bm_w.to_mesh(o.data)
        bm_w.free()
        o.data.update()

    return dest_col, part_objs


# ---------------------------------------------------------------------------
# 3. True 2048x2048 Cycles OPTIX GPU PBR Texture Baker
# ---------------------------------------------------------------------------
def _make_bake_image(name: str, res: int, colorspace: str) -> bpy.types.Image:
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, width=res, height=res, alpha=False, float_buffer=True)
    img.colorspace_settings.name = colorspace
    return img


def _attach_bake_targets(ob: bpy.types.Object, img: bpy.types.Image) -> list[tuple[bpy.types.NodeTree, bpy.types.Node]]:
    created = []
    for slot in ob.material_slots:
        if slot.material is None:
            continue
        nt = slot.material.node_tree
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = img
        tn.label = "__SC_BAKE_TARGET__"
        for n in nt.nodes:
            n.select = False
        tn.select = True
        nt.nodes.active = tn
        created.append((nt, tn))
    return created


def _remove_bake_targets(created: list[tuple[bpy.types.NodeTree, bpy.types.Node]]) -> None:
    for nt, tn in created:
        nt.nodes.remove(tn)


def _route_socket_to_emission(materials: list[bpy.types.Material], sock_name: str) -> list[tuple]:
    undo = []
    for mat in materials:
        nt = mat.node_tree
        out = mats.output_node(mat)
        b = mats.bsdf(mat)
        prev_from = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].is_linked else None
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        s_in = mats.sock(b, sock_name)
        if s_in is not None and s_in.is_linked:
            nt.links.new(s_in.links[0].from_socket, em.inputs["Color"])
        elif s_in is not None:
            dv = s_in.default_value
            em.inputs["Color"].default_value = tuple(dv) if hasattr(dv, "__len__") else (dv, dv, dv, 1.0)
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        undo.append((nt, em, out, prev_from))
    return undo


def _restore_emission(undo: list[tuple]) -> None:
    for nt, em, out, prev_from in reversed(undo):
        nt.nodes.remove(em)
        if prev_from is not None:
            nt.links.new(prev_from, out.inputs["Surface"])


def _atomic_copy_fallback(src_path: str, dst_path: str, retries: int = 6) -> None:
    import time as _time

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
                _time.sleep(0.4)
    finally:
        if os.path.exists(staged):
            try:
                os.remove(staged)
            except OSError:
                pass


def _save_png_8bit(arr_rgba: np.ndarray, path: str, colorspace: str) -> bpy.types.Image:
    try:
        from vflib import bake as _vf_bake

        return _vf_bake.save_png_8bit(arr_rgba, path, colorspace)
    except Exception:
        pass
    import tempfile as _tempfile

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    h, w, _ = arr_rgba.shape
    name = os.path.splitext(os.path.basename(path))[0]
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, width=w, height=h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.clip(arr_rgba, 0.0, 1.0).astype(np.float32).ravel())
    tmp_p = os.path.join(_tempfile.gettempdir(), f"__sc_tex_{os.getpid()}_{os.path.basename(path)}")
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


def bake_variant_pbr_maps(
    part_objs: dict[str, bpy.types.Object],
    variant_id: str,
    out_dir: str,
    *,
    cached_ao: np.ndarray | None = None,
    res: int = BAKE_RES,
) -> tuple[bpy.types.Material, dict[str, str], np.ndarray]:
    """Bake 2048x2048 Color (w/ Cycles AO), OpenGL Normal, Roughness, Metalness, AO & ORM maps!"""
    sc = bpy.context.scene
    backend = _enable_cycles_gpu(sc)
    core.log(f"[bake:{variant_id}] Cycles backend={backend}, resolution={res}x{res}")

    # Temporarily hide all other scene meshes so Cycles rays only see this boat!
    opaque_list = [part_objs[k] for k in OPAQUE_PARTS if k in part_objs]
    tmp_col = core.fresh_collection("__SC_BakeTmp")
    dups = [gameready.bake_object(o, f"__bake_{i}", tmp_col) for i, o in enumerate(opaque_list)]
    proxy = gameready.join(dups, "__SC_BakeProxy")
    gameready.collapse_materials(proxy)

    prev_hide: list[tuple[bpy.types.Object, bool]] = []
    for o in bpy.data.objects:
        if o.type == "MESH" and o != proxy:
            prev_hide.append((o, o.hide_render))
            o.hide_render = True

    sc.render.bake.target = "IMAGE_TEXTURES"
    sc.render.bake.use_clear = True
    sc.render.bake.use_selected_to_active = False
    sc.render.bake.margin = BAKE_MARGIN_PX
    sc.render.bake.margin_type = "EXTEND"
    sc.cycles.use_denoising = False

    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    proxy.select_set(True)
    bpy.context.view_layer.objects.active = proxy

    used_mats = [s.material for s in proxy.material_slots if s.material is not None]

    def _read_float_img(img: bpy.types.Image) -> np.ndarray:
        buf = np.zeros(res * res * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape((res, res, 4))

    try:
        # 1. Ambient Occlusion (32 samples â€” reusable across identical geometry!)
        if cached_ao is None:
            img_ao_raw = _make_bake_image("__raw_ao", res, "Non-Color")
            t_nodes = _attach_bake_targets(proxy, img_ao_raw)
            sc.cycles.samples = 32
            bpy.ops.object.bake(type="AO")
            ao_arr = _read_float_img(img_ao_raw)[..., 0].copy()
            _remove_bake_targets(t_nodes)
            bpy.data.images.remove(img_ao_raw)
        else:
            ao_arr = cached_ao

        # 2. OpenGL Tangent-Space Normal Map (16 samples)
        img_n_raw = _make_bake_image("__raw_n", res, "Non-Color")
        img_n_raw.generated_color = (0.5, 0.5, 1.0, 1.0)
        t_nodes = _attach_bake_targets(proxy, img_n_raw)
        sc.cycles.samples = 16
        sc.render.bake.normal_space = "TANGENT"
        sc.render.bake.normal_r = "POS_X"
        sc.render.bake.normal_g = "POS_Y"
        sc.render.bake.normal_b = "POS_Z"
        bpy.ops.object.bake(type="NORMAL")
        norm_arr = _read_float_img(img_n_raw)
        _remove_bake_targets(t_nodes)
        bpy.data.images.remove(img_n_raw)

        # 3. Roughness Map (4 samples)
        img_r_raw = _make_bake_image("__raw_r", res, "Non-Color")
        t_nodes = _attach_bake_targets(proxy, img_r_raw)
        sc.cycles.samples = 4
        bpy.ops.object.bake(type="ROUGHNESS")
        rough_arr = _read_float_img(img_r_raw)[..., 0].copy()
        _remove_bake_targets(t_nodes)
        bpy.data.images.remove(img_r_raw)

        # 4. Base Color (via Emission override, 2 samples -> linear float!)
        img_bc_raw = _make_bake_image("__raw_bc", res, "Non-Color")
        undo_bc = _route_socket_to_emission(used_mats, "Base Color")
        t_nodes = _attach_bake_targets(proxy, img_bc_raw)
        sc.cycles.samples = 2
        bpy.ops.object.bake(type="EMIT")
        bc_lin = _read_float_img(img_bc_raw)[..., :3].copy()
        _remove_bake_targets(t_nodes)
        _restore_emission(undo_bc)
        bpy.data.images.remove(img_bc_raw)

        # 5. Metalness (via Emission override, 1 sample)
        img_m_raw = _make_bake_image("__raw_m", res, "Non-Color")
        undo_m = _route_socket_to_emission(used_mats, "Metallic")
        t_nodes = _attach_bake_targets(proxy, img_m_raw)
        sc.cycles.samples = 1
        bpy.ops.object.bake(type="EMIT")
        metal_arr = _read_float_img(img_m_raw)[..., 0].copy()
        _remove_bake_targets(t_nodes)
        _restore_emission(undo_m)
        bpy.data.images.remove(img_m_raw)

    finally:
        for o, h_state in prev_hide:
            o.hide_render = h_state
        core.clear_collection(tmp_col)
        bpy.data.collections.remove(tmp_col)

    # Composite physical Cycles AO (32% strength) in linear space, then encode to sRGB for 8-bit PNG buffer!
    ao_clamped = np.clip(ao_arr, 0.0, 1.0)
    ao_factor = (0.68 + 0.32 * ao_clamped)[..., None]
    bc_shaded_lin = np.clip(bc_lin * ao_factor, 0.0, 1.0)
    color_srgb_rgba = np.ones((res, res, 4), dtype=np.float32)
    color_srgb_rgba[..., :3] = _lin_arr_to_srgb(bc_shaded_lin)

    norm_rgba = np.ones((res, res, 4), dtype=np.float32)
    norm_rgba[..., :3] = np.clip(norm_arr[..., :3], 0.0, 1.0)

    rough_rgba = np.ones((res, res, 4), dtype=np.float32)
    rough_rgba[..., :3] = np.clip(rough_arr, 0.04, 1.0)[..., None]

    metal_rgba = np.ones((res, res, 4), dtype=np.float32)
    metal_rgba[..., :3] = np.clip(metal_arr, 0.0, 1.0)[..., None]

    ao_rgba = np.ones((res, res, 4), dtype=np.float32)
    ao_rgba[..., :3] = ao_clamped[..., None]

    orm_rgba = np.ones((res, res, 4), dtype=np.float32)
    orm_rgba[..., 0] = ao_clamped
    orm_rgba[..., 1] = np.clip(rough_arr, 0.04, 1.0)
    orm_rgba[..., 2] = np.clip(metal_arr, 0.0, 1.0)

    prefix = f"T_Sunrunner24_{variant_id}"
    paths = {
        "Color": os.path.join(out_dir, f"{prefix}_Color.png"),
        "Normal": os.path.join(out_dir, f"{prefix}_Normal.png"),
        "Roughness": os.path.join(out_dir, f"{prefix}_Roughness.png"),
        "Metalness": os.path.join(out_dir, f"{prefix}_Metalness.png"),
        "AO": os.path.join(out_dir, f"{prefix}_AO.png"),
        "ORM": os.path.join(out_dir, f"{prefix}_ORM.png"),
    }
    img_c = _save_png_8bit(color_srgb_rgba, paths["Color"], "sRGB")
    img_n = _save_png_8bit(norm_rgba, paths["Normal"], "Non-Color")
    img_r = _save_png_8bit(rough_rgba, paths["Roughness"], "Non-Color")
    img_m = _save_png_8bit(metal_rgba, paths["Metalness"], "Non-Color")
    _save_png_8bit(ao_rgba, paths["AO"], "Non-Color")
    _save_png_8bit(orm_rgba, paths["ORM"], "Non-Color")

    # Build clean game-ready single-material PBR shader wired exclusively to the 4 baked PNGs!
    baked_mat, bsdf_node = mats._new_node_material(f"M_Sunrunner24_{variant_id}_Baked")
    nt = baked_mat.node_tree

    tex_c = nt.nodes.new("ShaderNodeTexImage")
    tex_c.image = img_c
    tex_c.location = (-520, 320)
    nt.links.new(mats.sock(tex_c, "Color", output=True), mats.sock(bsdf_node, "Base Color"))

    tex_r = nt.nodes.new("ShaderNodeTexImage")
    tex_r.image = img_r
    tex_r.location = (-520, 40)
    nt.links.new(mats.sock(tex_r, "Color", output=True), mats.sock(bsdf_node, "Roughness"))

    tex_m = nt.nodes.new("ShaderNodeTexImage")
    tex_m.image = img_m
    tex_m.location = (-520, -240)
    nt.links.new(mats.sock(tex_m, "Color", output=True), mats.sock(bsdf_node, "Metallic"))

    tex_n = nt.nodes.new("ShaderNodeTexImage")
    tex_n.image = img_n
    tex_n.location = (-760, -520)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.location = (-420, -520)
    nt.links.new(mats.sock(tex_n, "Color", output=True), mats.sock(nmap, "Color"))
    nt.links.new(mats.sock(nmap, "Normal", output=True), mats.sock(bsdf_node, "Normal"))

    baked_mat["sc_role"] = "baked_pbr"
    return baked_mat, paths, ao_clamped


# ---------------------------------------------------------------------------
# 4. Proper 4-Tier LOD Chain Generator (LOD0 -> LOD1 -> LOD2 -> LOD3)
# ---------------------------------------------------------------------------
LOD_SPECS = [
    # (lod_level, base_ratio, hull_ratio, cull_parts, screen_size)
    (1, 0.46, 0.58, set(), 0.50),
    (2, 0.21, 0.30, set(), 0.25),
    (3, 0.09, 0.14, {"Steering", "Throttle", "Glass"}, 0.10),
]


def build_lod_chain(lod0_parts: dict[str, bpy.types.Object], base_prefix: str = "Sunrunner24") -> dict[str, dict]:
    """Generate LOD1, LOD2, LOD3 collections preserving baked UVs, silhouette & servo parts."""
    lod_summary: dict[str, dict] = {
        "LOD0": {
            "tris": sum(gameready.triangle_count(o, False) for o in lod0_parts.values()),
            "parts": len(lod0_parts),
            "screen_size": 1.0,
        }
    }

    for lvl, r_def, r_hull, culled, scr_sz in LOD_SPECS:
        col_name = f"{base_prefix}_LOD{lvl}"
        l_col = core.fresh_collection(col_name)
        lvl_objs: list[bpy.types.Object] = []
        for pname, src in lod0_parts.items():
            if pname in culled:
                continue
            ratio = r_hull if pname in ("Hull", "PaintPrimary") else r_def
            cp = src.copy()
            cp.data = src.data.copy()
            cp.name = f"{pname}_LOD{lvl}"
            cp.data.name = cp.name
            l_col.objects.link(cp)
            cp["sc_part"] = pname
            cp["sc_role"] = src.get("sc_role", "solid")

            dec = cp.modifiers.new("SC_LOD_Decimate", "DECIMATE")
            if pname == "Hull":
                # Planar decimation on Hull preserves outer-vs-inner wall clearance (0 liner poke-through!)
                # and keeps waterline / boot-stripe UV borders 100% razor-sharp across LOD1..LOD3!
                dec.decimate_type = "DISSOLVE"
                dec.angle_limit = math.radians({1: 1.8, 2: 2.6, 3: 3.4}[lvl])
                dec.delimit = {"UV", "SEAM", "SHARP", "MATERIAL"}
                dec.use_dissolve_boundaries = False
            else:
                dec.decimate_type = "COLLAPSE"
                dec.ratio = {1: 0.85, 2: 0.72, 3: 0.58}[lvl] if pname == "PaintPrimary" else ratio
                dec.delimit = {"UV", "SEAM", "SHARP"}
                dec.use_collapse_triangulate = True
            with bpy.context.temp_override(
                object=cp,
                active_object=cp,
                selected_objects=[cp],
                selected_editable_objects=[cp],
            ):
                bpy.ops.object.modifier_apply(modifier=dec.name)
            if pname in ("Hull", "PaintPrimary"):
                bm_t = bmesh.new()
                bm_t.from_mesh(cp.data)
                if pname == "Hull":
                    bmesh.ops.triangulate(bm_t, faces=bm_t.faces[:])
                else:
                    # Push simplified hull-band decal outboard & slightly down (-Z on bow flare) so chords never touch Hull!
                    mw = cp.matrix_world
                    dx_out = {1: 0.003, 2: 0.008, 3: 0.013}[lvl]
                    dz_out = {1: -0.001, 2: -0.003, 3: -0.005}[lvl]
                    for v in bm_t.verts:
                        wco = mw @ v.co
                        if abs(wco.x) > 0.02:
                            v.co.x += math.copysign(dx_out, wco.x)
                            if wco.y > 0.5:
                                v.co.z += dz_out
                bm_t.to_mesh(cp.data)
                bm_t.free()
                cp.data.update()
            lvl_objs.append(cp)

        # Export standalone GLB & Roblox-scaled FBX for each LOD level!
        os.makedirs(LODS_ROOT, exist_ok=True)
        glb_lod = os.path.join(LODS_ROOT, f"sunrunner_24_LOD{lvl}.glb")
        core.ensure_object_mode()
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        for o in lvl_objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = lvl_objs[0]
        bpy.ops.export_scene.gltf(filepath=glb_lod, use_selection=True, export_format="GLB", export_apply=True)
        for o in lvl_objs:
            o.select_set(False)

        lod_tris = sum(gameready.triangle_count(o, False) for o in lvl_objs)
        lod_summary[f"LOD{lvl}"] = {
            "tris": lod_tris,
            "parts": len(lvl_objs),
            "screen_size": scr_sz,
            "glb": f"lods/sunrunner_24_LOD{lvl}.glb",
        }
        core.log(f"[LOD{lvl}] {lod_tris} tris across {len(lvl_objs)} parts -> {glb_lod}")

    return lod_summary


# ---------------------------------------------------------------------------
# 5. Export Variants + Render Lineup, Baked Macro Close-Up & LOD Sheet
# ---------------------------------------------------------------------------
def export_variant_bundle(
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

    # Export textured GLB (metric, embeds baked 2048x2048 PNGs + NormalMap!)
    glb_path = os.path.join(out_dir, f"sunrunner_24_{variant['id']}.glb")
    all_v_objs = list(part_objs.values())
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in all_v_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = all_v_objs[0]
    bpy.ops.export_scene.gltf(filepath=glb_path, use_selection=True, export_format="GLB", export_apply=True)
    for o in all_v_objs:
        o.select_set(False)

    # Export Roblox FBX + Manifest + Studio Setup Luau (with baked 2K SurfaceAppearance maps!)
    collide_parts = {"Hull", "Deck", "Console", "LeaningPost", "TTop"}
    paint_srgb = mats.parse_color(variant["colors"]["SR_HullTeal"][0])
    glass_srgb = mats.parse_color(variant["glass_color"])

    parts_spec = []
    for pname, pob in part_objs.items():
        role = pob.get("sc_role", "solid")
        spec = dict(
            name=pname,
            objects=[pob],
            role="solid" if pname in OPAQUE_PARTS and pname != "PaintPrimary" else role,
            collide=pname in collide_parts,
            render_fidelity="Precise" if pname in ("Hull", "PaintPrimary") else "Automatic",
        )
        if pname == "PaintPrimary":
            spec["role"] = "paint"
            spec["material"] = "SmoothPlastic"
            spec["color"] = paint_srgb
        elif pname == "Glass":
            spec["role"] = "glass"
            spec["transparency"] = round(1.0 - variant["glass_alpha"], 2)
            spec["color"] = glass_srgb
        parts_spec.append(spec)

    lo, hi = core.world_bbox(all_v_objs)
    hinges = [
        dict(name="Steering", socket="HingeSteering", part0="@primary", part1="Steering", actuator="Servo", lower=-180, upper=180, speed=8),
        dict(name="Throttle", socket="HingeThrottle", part0="@primary", part1="Throttle", actuator="Servo", lower=-45, upper=45, speed=6),
        dict(name="Motor", socket="HingeMotor", part0="@primary", part1="Motor", actuator="Servo", lower=-38, upper=38, speed=6),
        dict(name="Prop", socket="HingeProp", part0="Motor", part1="Prop", actuator="Motor", torque=1e6),
    ]
    asset_tag_name = "Sunrunner24" if variant["id"] == "bahama_teal" else f"Sunrunner24_{variant['id']}"
    export.export_roblox(
        asset_tag_name,
        out_dir,
        parts=parts_spec,
        source_collection=src_col,
        primary=dict(name="Boat", center=(lo + hi) * 0.5, size=hi - lo),
        hinges=hinges,
        attributes={"BoatType": "CenterConsole", "Variant": variant["id"], "MaxSpeed": 52 if variant["patrol_gear"] else 46},
        tags=["Boat", "PatrolBoat"] if variant["patrol_gear"] else ["Boat"],
        reference="Hull",
        prebaked_material=baked_mat,
        prebaked_textures=rel_tex,
        extra_manifest=extra_manifest,
    )


import tempfile
import time


def _render_still_safe(sc: bpy.types.Scene, dst_path: str) -> str:
    """Render to local temp dir first, then copy to OneDrive destination with retry & thermal cooldown."""
    try:
        from vflib import bake as _vf_bake

        return _vf_bake.render_still_safe(sc, dst_path)
    except Exception:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    tmp_p = os.path.join(tempfile.gettempdir(), f"__sc_rnd_{os.getpid()}_{os.path.basename(dst_path)}")
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


def render_variants_and_lods(
    variant_cols: dict[str, bpy.types.Collection],
    lod_cols: list[tuple[str, bpy.types.Collection]],
    out_dir: str,
) -> dict[str, str]:
    """Render 4-Variant Marina Lineup, Baked Deck Macro Close-Up, per-variant heroes, and 4-Panel LOD Sheet."""
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    _enable_cycles_gpu(sc)
    sc.cycles.samples = 80
    sc.cycles.use_denoising = True
    sc.render.image_settings.file_format = "PNG"

    saved_shots: dict[str, str] = {}

    # Hide LOD collections during variant renders
    for _lbl, lc in lod_cols:
        lc.hide_render = True
        lc.hide_viewport = True

    # 1. Per-variant hero shots + Baked Cockpit/Teak/Non-Skid Macro Close-Up on default variant!
    for vid, vcol in variant_cols.items():
        for other_id, other_col in variant_cols.items():
            other_col.hide_render = other_id != vid
            other_col.hide_viewport = other_id != vid

        v_meshes = core.objects_in(vcol, types=("MESH",))
        studio_col = render.setup_studio(v_meshes, backdrop="product")
        cam_d = bpy.data.cameras.new("SR_VarCam")
        cam = bpy.data.objects.new("SR_VarCam", cam_d)
        studio_col.objects.link(cam)
        sc.camera = cam
        try:
            sc.render.resolution_x = 1600
            sc.render.resolution_y = 1000
            cam.location = Vector((9.10, 8.75, 3.68))
            cam.data.lens = 45.0
            cam.rotation_euler = (Vector((0.0, 0.35, 1.38)) - cam.location).to_track_quat("-Z", "Y").to_euler()
            p_hero = os.path.join(out_dir, f"variant_{vid}.png")
            _render_still_safe(sc, p_hero)
            saved_shots[f"variant_{vid}"] = p_hero

            if vid == "bahama_teal":
                # Macro close-up of baked Burmese teak planks, caulk grooves, diamond non-skid, MFD UI & cavity AO!
                cam.location = Vector((0.55, -2.55, 2.38))
                cam.data.lens = 38.0
                cam.rotation_euler = (Vector((-0.02, -0.55, 1.25)) - cam.location).to_track_quat("-Z", "Y").to_euler()
                p_macro = os.path.join(out_dir, "baked_teak_nonskid_closeup.png")
                _render_still_safe(sc, p_macro)
                saved_shots["baked_closeup"] = p_macro
        finally:
            core.clear_collection(studio_col)
            bpy.data.collections.remove(studio_col)

    # 2. All 4 Variants Side-by-Side Showroom Echelon Lineup!
    offsets_x = {
        "bahama_teal": -5.55,
        "boca_grande_ice": -1.85,
        "midnight_blackout": 1.85,
        "harbor_patrol": 5.55,
    }
    offsets_y = {
        "bahama_teal": 1.95,
        "boca_grande_ice": 0.65,
        "midnight_blackout": -0.65,
        "harbor_patrol": -1.95,
    }
    all_lineup_meshes: list[bpy.types.Object] = []
    for vid, vcol in variant_cols.items():
        vcol.hide_render = False
        vcol.hide_viewport = False
        dx = offsets_x[vid]
        dy = offsets_y[vid]
        for o in vcol.objects:
            o.location.x += dx
            o.location.y += dy
            if o.type == "MESH":
                all_lineup_meshes.append(o)
    bpy.context.view_layer.update()

    studio_line = render.setup_studio(all_lineup_meshes, backdrop="product")
    cam_d = bpy.data.cameras.new("SR_LineupCam")
    cam = bpy.data.objects.new("SR_LineupCam", cam_d)
    studio_line.objects.link(cam)
    sc.camera = cam
    try:
        sc.render.resolution_x = 2000
        sc.render.resolution_y = 1125
        cam.location = Vector((15.60, 14.10, 3.90))
        cam.data.lens = 34.0
        cam.rotation_euler = (Vector((-0.15, 0.05, 1.30)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        p_lineup = os.path.join(out_dir, "variants_lineup.png")
        _render_still_safe(sc, p_lineup)
        saved_shots["variants_lineup"] = p_lineup
    finally:
        core.clear_collection(studio_line)
        bpy.data.collections.remove(studio_line)

    # Move Bahama_Teal to X = 0.0 and park the other 3 neatly beside it (X = +3.85, +7.70, +11.55 m, Y = 0) for live Blender inspection!
    final_x = {
        "bahama_teal": 0.0,
        "boca_grande_ice": 3.85,
        "midnight_blackout": 7.70,
        "harbor_patrol": 11.55,
    }
    for vid, vcol in variant_cols.items():
        shift_x = final_x[vid] - offsets_x[vid]
        shift_y = -offsets_y[vid]
        for o in vcol.objects:
            o.location.x += shift_x
            o.location.y += shift_y
    bpy.context.view_layer.update()

    # 3. 4-Panel LOD Comparison Sheet (`LOD0`, `LOD1`, `LOD2`, `LOD3`)!
    for vcol in variant_cols.values():
        vcol.hide_render = True
    lod_tiles: list[tuple[str, np.ndarray]] = []
    for lbl, lcol in lod_cols:
        for _l2, lc2 in lod_cols:
            lc2.hide_render = lc2 != lcol
        l_meshes = core.objects_in(lcol, types=("MESH",))
        st_l = render.setup_studio(l_meshes, backdrop="product")
        cd = bpy.data.cameras.new("SR_LODCam")
        cm = bpy.data.objects.new("SR_LODCam", cd)
        st_l.objects.link(cm)
        sc.camera = cm
        try:
            sc.render.resolution_x = 960
            sc.render.resolution_y = 600
            sc.cycles.samples = 48
            cm.location = Vector((8.90, 8.55, 3.55))
            cm.data.lens = 45.0
            cm.rotation_euler = (Vector((0.0, 0.35, 1.38)) - cm.location).to_track_quat("-Z", "Y").to_euler()
            tp = os.path.join(tempfile.gettempdir(), f"__sc_lod_{lbl.split()[0]}.png")
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

    # Compose 2x2 grid (1920x1200) for LOD0..LOD3 comparison
    if len(lod_tiles) == 4:
        grid = np.ones((1200, 1920, 4), dtype=np.float32)
        # Note: Blender image rows run bottom-to-top (row 0 = bottom):
        # Top-Left = LOD0, Top-Right = LOD1, Bottom-Left = LOD2, Bottom-Right = LOD3
        grid[600:1200, 0:960] = lod_tiles[0][1]
        grid[600:1200, 960:1920] = lod_tiles[1][1]
        grid[0:600, 0:960] = lod_tiles[2][1]
        grid[0:600, 960:1920] = lod_tiles[3][1]
        # Crisp dark divider hairlines
        grid[598:602, :, :3] = 0.12
        grid[:, 958:962, :3] = 0.12
        p_lod_sheet = os.path.join(out_dir, "lod_comparison_sheet.png")
        _save_png_8bit(grid, p_lod_sheet, "sRGB")
        saved_shots["lod_sheet"] = p_lod_sheet

    # Restore visibility for live desktop Blender inspection: all 4 Showroom Variants visible, LOD1..3 tucked cleanly!
    for vcol in variant_cols.values():
        vcol.hide_render = False
        vcol.hide_viewport = False
    for idx_l, (_lbl, lcol) in enumerate(lod_cols):
        if idx_l > 0:
            lcol.hide_render = True
            lcol.hide_viewport = True

    return saved_shots


def main() -> int:
    # 1. Build clean parametric source boat (verifies 0 shell breaches!)
    src_col, _raw_meshes = sr.build_all()

    variant_cols: dict[str, bpy.types.Collection] = {}
    variant_manifests: dict[str, dict] = {}
    cached_civilian_ao: np.ndarray | None = None
    flagship_parts: dict[str, bpy.types.Object] = {}
    lod_summary: dict[str, dict] = {}

    for var in VARIANTS:
        vid = var["id"]
        v_mats = apply_variant_materials(var)

        extra_patrol_objs: list[bpy.types.Object] = []
        if var["patrol_gear"]:
            extra_patrol_objs = add_harbor_patrol_equipment(src_col, v_mats)

        try:
            col_name = f"Variant_{vid}"
            v_col, part_objs = build_joined_lod0_parts(src_col, col_name)
            tex_dir = os.path.join(TEXTURES_ROOT, vid)
            use_ao = None if var["patrol_gear"] else cached_civilian_ao
            baked_mat, tex_paths, ao_out = bake_variant_pbr_maps(
                part_objs, vid, tex_dir, cached_ao=use_ao, res=BAKE_RES
            )
            if not var["patrol_gear"] and cached_civilian_ao is None:
                cached_civilian_ao = ao_out

            # Assign the single baked 2048x2048 PBR material onto all opaque parts, and per-variant Glass onto Glass!
            for pname in OPAQUE_PARTS:
                if pname in part_objs:
                    pob = part_objs[pname]
                    pob.data.materials.clear()
                    pob.data.materials.append(baked_mat)
                    pob.data.polygons.foreach_set("material_index", [0] * len(pob.data.polygons))
                    pob.data.update()
            if "Glass" in part_objs:
                gob = part_objs["Glass"]
                gob.data.materials.clear()
                gob.data.materials.append(v_mats["SR_WindshieldGlass"])
                gob.data.polygons.foreach_set("material_index", [0] * len(gob.data.polygons))
                gob.data.update()

            if vid == "bahama_teal":
                flagship_parts = part_objs
                lod_summary = build_lod_chain(flagship_parts, base_prefix="Sunrunner24")
                # Also export LOD0 GLB
                os.makedirs(LODS_ROOT, exist_ok=True)
                shutil.copy2(
                    os.path.join(THIS_DIR, "sunrunner_24.glb") if os.path.exists(os.path.join(THIS_DIR, "sunrunner_24.glb")) else tex_paths["Color"],
                    os.path.join(LODS_ROOT, "__tmp"),
                ) if False else None

            var_out = os.path.join(VARIANTS_ROOT, vid)
            extra_meta = {
                "variant": vid,
                "variantLabel": var["label"],
                "bakeResolution": BAKE_RES,
                "lods": lod_summary,
                "availableVariants": [v["id"] for v in VARIANTS],
            }
            export_variant_bundle(var, src_col, part_objs, baked_mat, tex_paths, var_out, extra_manifest=extra_meta)

            if vid == "bahama_teal":
                # Also populate primary `export/` & `sunrunner_24.glb` with baked 2048x2048 textures + LOD metadata!
                export_variant_bundle(var, src_col, part_objs, baked_mat, tex_paths, EXPORT_DIR, extra_manifest=extra_meta)
                shutil.copy2(os.path.join(var_out, f"sunrunner_24_{vid}.glb"), os.path.join(THIS_DIR, "sunrunner_24.glb"))
                shutil.copy2(os.path.join(var_out, f"sunrunner_24_{vid}.glb"), os.path.join(LODS_ROOT, "sunrunner_24_LOD0.glb"))

            variant_cols[vid] = v_col
            variant_manifests[vid] = {
                "label": var["label"],
                "dir": f"variants/{vid}",
                "glb": f"variants/{vid}/sunrunner_24_{vid}.glb",
                "textures": {k: f"textures/{vid}/{os.path.basename(v)}" for k, v in tex_paths.items()},
            }
        finally:
            for po in extra_patrol_objs:
                me = po.data
                bpy.data.objects.remove(po, do_unlink=True)
                if me and me.users == 0:
                    bpy.data.meshes.remove(me)

    # Hide raw build source collection so viewport cleanly displays the 4 Baked Showroom Variants!
    src_col.hide_viewport = True
    src_col.hide_render = True

    lod_cols = [("LOD0", variant_cols["bahama_teal"])] + [
        (f"LOD{i}", bpy.data.collections[f"Sunrunner24_LOD{i}"]) for i in (1, 2, 3)
    ]
    shots = render_variants_and_lods(variant_cols, lod_cols, RENDERS_DIR)

    # Frame all 4 Showroom Variants in Material Preview mode with studio lighting so Blender opens ready to inspect!
    visible_meshes = [o for vc in variant_cols.values() for o in core.objects_in(vc, types=("MESH",))]
    render.frame_viewport(visible_meshes)
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == "VIEW_3D":
                for sp in area.spaces:
                    if sp.type == "VIEW_3D":
                        sp.shading.type = "MATERIAL"
                        sp.overlay.show_extras = False

    showroom_blend = os.path.join(THIS_DIR, "sunrunner_24_variants_lods.blend")
    bpy.ops.wm.save_as_mainfile(filepath=showroom_blend)
    core.log("saved master baked variants + LODs blend ->", showroom_blend)

    # Sync to Design Model Output
    os.makedirs(DESIGN_OUTPUT_DIR, exist_ok=True)
    sr._safe_copy(showroom_blend, os.path.join(DESIGN_OUTPUT_DIR, "sunrunner_24_variants_lods.blend"))
    sr._safe_copy(showroom_blend, os.path.join(DESIGN_OUTPUT_DIR, "sunrunner_24.blend"))
    sr._safe_copy(os.path.join(THIS_DIR, "sunrunner_24.glb"), os.path.join(DESIGN_OUTPUT_DIR, "sunrunner_24.glb"))
    for v in VARIANTS:
        vid = v["id"]
        sr._safe_copy(
            os.path.join(VARIANTS_ROOT, vid, f"sunrunner_24_{vid}.glb"),
            os.path.join(DESIGN_OUTPUT_DIR, f"sunrunner_24_{vid}.glb"),
        )
    if "variants_lineup" in shots:
        sr._safe_copy(shots["variants_lineup"], os.path.join(DESIGN_OUTPUT_DIR, "blender-render-check.png"))
    for k, spath in shots.items():
        sr._safe_copy(spath, os.path.join(DESIGN_OUTPUT_DIR, f"sunrunner24_{os.path.basename(spath)}"))

    summary_json = os.path.join(THIS_DIR, "variants_and_lods_report.json")
    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump({"ok": True, "bake_res": BAKE_RES, "lods": lod_summary, "variants": variant_manifests}, fh, indent=2)
    core.log("DONE! Report written to", summary_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

