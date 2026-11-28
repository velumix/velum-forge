r"""Cruiser Boat 7C — Cycles GPU (OPTIX) 2048x2048 PBR Texture Baker, 4 Showroom Variants & Seam-Locked LOD0–LOD3 Pipeline.

Stages:
  1. Build clean 1:1 reference-locked LOD0 source geometry via `build_cruiser_boat_7c.build_all()` (0 shell breaches, 0 Errors, 0 Warnings).
  2. Author procedural Cycles marine shader networks prior to baking:
       - Planked Burmese teak (`C7_Teak`) w/ 3.5 mm recessed black marine thiokol caulk seams + stretched wood grain bump
       - Dark European walnut hardwood salon sole (`C7_WalnutFloor`) & glossy walnut cabinetry (`C7_WalnutCab`)
       - Veined Carrara white galley marble (`C7_Marble`)
       - 45-degree molded diamond marine non-skid (`C7_DeckWhite` using `Voronoi MANHATTAN`)
       - Marine pebble-grain leather upholstery (`C7_VinylWhite`, `C7_VinylGrey`, `C7_VinylDark`)
       - Woven Sunbrella marine canvas sunroof (`C7_SunroofCanvas`)
       - Anisotropic brushed 316 stainless & Nibral bronze (`C7_Stainless`, `C7_PropBronze`, `C7_PodGrey`)
       - Glowing Garmin glass-bridge bathymetric chartplotter UI (`C7_ScreenGlow`)
       - Subtle gelcoat/metallic/antifouling micro-roughness breakup (`C7_HullTopsides`, `C7_HullWhite`, `C7_HullAccent`, `C7_AntiFoul`)
  3. Collapse into 14 game-ready `MeshPart`s and pack a single non-overlapping 2048x2048 shared UV atlas across all 12 opaque parts
     via `vflib.bake.split_material_border_uv_islands()` (zero staircase artifacts, seams locked for LOD decimation!).
  4. Bake real Cycles GPU (OPTIX) 2048x2048 PBR maps (`Color` sRGB w/ 28% linear Cycles AO + `lin_arr_to_srgb`, OpenGL `Normal`,
     `Roughness`, `Metalness`, `AO`, `ORM`) for 4 distinct luxury 60-ft yacht variants:
       - `reference_pearl`    : Flagship Pure White Gelcoat, Silver Boot Stripe, Burmese Teak, Oyster/Grey Lounge (1:1 Reference Match!)
       - `mediterranean_navy` : Riviera Deep Navy Hull Topsides, Champagne Boot Stripe, Blonde Teak, Saddle-Tan/Cream Upholstery
       - `stealth_graphite`   : Metallic Anthracite Hull, Crimson Boot Stripe, Storm-Grey EVA SeaDek, Blackout Hardtop Trim
       - `monaco_champagne`   : Warm Champagne-Bronze Metallic Hull, Espresso Boot Stripe, Pearl Superstructure, Honey Teak
  5. Build seam-locked 4-tier LOD hierarchy (`LOD0` 100% -> `LOD1` ~50% -> `LOD2` ~25% -> `LOD3` ~10%) preserving baked UVs,
     silhouette, and articulated `Steering`/`Throttle`/`Props` parts, with outboard `HullAccent` offset preventing hull poke-through.
  6. Export per-variant Roblox FBX + Manifest + `.studio_setup.luau` + textured GLB, per-LOD GLB (`lods/cruiser_boat_7c_LOD0..3.glb`),
     master `cruiser_boat_7c_variants_lods.blend`, render showcase verification sheets (`variants_lineup.png`, `baked_closeup.png`,
     `lod_comparison_sheet.png`, per-variant heroes), and sync outputs to `core.DESIGN_OUTPUT_DIR`.
"""
from __future__ import annotations

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
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
BLENDER_ENGINE = os.path.join(REPO_ROOT, "engine", "blender")
for p in (THIS_DIR, BLENDER_ENGINE):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_cruiser_boat_7c as cb  # noqa: E402
from vflib import bake, core, export, gameready, mats, render  # noqa: E402

BAKE_RES = 2048
BAKE_MARGIN_PX = 8
TEXTURES_ROOT = os.path.join(THIS_DIR, "textures")
VARIANTS_ROOT = os.path.join(THIS_DIR, "variants")
LODS_ROOT = os.path.join(THIS_DIR, "lods")
EXPORT_DIR = os.path.join(THIS_DIR, "export")
RENDERS_DIR = os.path.join(THIS_DIR, "renders")
DESIGN_OUTPUT_DIR = core.DESIGN_OUTPUT_DIR

OPAQUE_PARTS = (
    "Hull",
    "HullAccent",
    "Deck",
    "Superstructure",
    "InteriorSalon",
    "Flybridge",
    "RailsHardware",
    "Electronics",
    "Propulsion",
    "Props",
    "Steering",
    "Throttle",
)

# ---------------------------------------------------------------------------
# 4 Distinct Luxury 60-ft Flybridge Motor Yacht Variants
# ---------------------------------------------------------------------------
VARIANTS: list[dict] = [
    {
        "id": "reference_pearl",
        "label": "Cruiser Boat 7C — Flagship Reference Pearl (1:1 Ref)",
        "deck_style": "teak",
        "colors": {
            "C7_HullTopsides": ("#F4F6F9", 0.14, 0.00),   # Flagship Pure White Gelcoat (`ref_side` & `ref_front` 1:1!)
            "C7_HullWhite": ("#F4F6F9", 0.14, 0.00),
            "C7_HullAccent": ("#15191F", 0.22, 0.10),
            "C7_BootStripe": ("#9AA4B0", 0.24, 0.35),     # Metallic Silver-Slate Boot Stripe
            "C7_AntiFoul": ("#141C26", 0.68, 0.00),       # Deep Navy Antifouling Bottom
            "C7_DeckWhite": ("#EBF0F4", 0.74, 0.00),      # 45-deg Molded Diamond Non-Skid
            "C7_Teak": ("#9C734B", 0.52, 0.00),           # Honey Burmese Teak Planks
            "C7_WalnutFloor": ("#4A3929", 0.34, 0.00),    # Dark Walnut Hardwood Salon Sole
            "C7_WalnutCab": ("#3B2A1C", 0.24, 0.00),      # Glossy Walnut Cabinetry
            "C7_Marble": ("#EBEDE9", 0.18, 0.00),         # Veined Carrara Galley Marble
            "C7_VinylWhite": ("#EFF1EE", 0.44, 0.00),     # Pure Oyster Marine Leather
            "C7_VinylGrey": ("#B2B8C0", 0.48, 0.00),      # Cool Slate Sunpad Leather
            "C7_VinylDark": ("#2A3038", 0.52, 0.00),      # Charcoal Contrast Backrest
            "C7_SunroofCanvas": ("#D6D9DC", 0.85, 0.00),  # Woven Light-Grey Sunroof Canvas
            "C7_DashDark": ("#181C22", 0.36, 0.08),
            "C7_BlackTrim": ("#111419", 0.26, 0.25),
            "C7_Stainless": ("#DFE5EC", 0.14, 0.95),
            "C7_PodGrey": ("#2D333B", 0.34, 0.55),
            "C7_PropBronze": ("#C9A86A", 0.16, 0.94),
        },
        "glass_tint": "#122230",
        "glass_alpha": 0.48,
    },
    {
        "id": "mediterranean_navy",
        "label": "Cruiser Boat 7C — Mediterranean Flagship Navy",
        "deck_style": "teak",
        "colors": {
            "C7_HullTopsides": ("#112A48", 0.15, 0.12),   # Deep Riviera Flagship Navy Gelcoat!
            "C7_HullWhite": ("#F6F8FA", 0.14, 0.00),      # Pure Pearl-White Superstructure & Hardtop
            "C7_HullAccent": ("#0A1626", 0.20, 0.18),     # Obsidian Navy Intake Louvers
            "C7_BootStripe": ("#C8AB70", 0.22, 0.55),     # Classic Yacht Champagne-Gold Boot Stripe!
            "C7_AntiFoul": ("#101720", 0.68, 0.00),
            "C7_DeckWhite": ("#EEF1F5", 0.74, 0.00),
            "C7_Teak": ("#B38A57", 0.48, 0.00),           # Golden Blonde Burmese Teak!
            "C7_WalnutFloor": ("#5A4330", 0.32, 0.00),
            "C7_WalnutCab": ("#422E1E", 0.22, 0.00),
            "C7_Marble": ("#F2F0E8", 0.16, 0.00),         # Warm Calacatta Gold Marble
            "C7_VinylWhite": ("#F3ECE0", 0.44, 0.00),     # Warm Ivory Marine Leather
            "C7_VinylGrey": ("#BC8854", 0.46, 0.00),      # Saddle-Camel Tan Luxury Cushions!
            "C7_VinylDark": ("#162840", 0.50, 0.00),      # Deep Navy Contrast Bolster
            "C7_SunroofCanvas": ("#DDD6C9", 0.85, 0.00),  # Sand-Linen Woven Sunroof Canvas
            "C7_DashDark": ("#141D28", 0.34, 0.10),
            "C7_BlackTrim": ("#0F1620", 0.24, 0.28),
            "C7_Stainless": ("#E2E7EE", 0.13, 0.96),
            "C7_PodGrey": ("#28303A", 0.34, 0.55),
            "C7_PropBronze": ("#D0B070", 0.15, 0.94),
        },
        "glass_tint": "#0D2438",
        "glass_alpha": 0.46,
    },
    {
        "id": "stealth_graphite",
        "label": "Cruiser Boat 7C — Stealth Anthracite & Crimson",
        "deck_style": "seadek_grey",
        "colors": {
            "C7_HullTopsides": ("#232830", 0.18, 0.32),   # Metallic Stealth Anthracite Hull!
            "C7_HullWhite": ("#D5DCE4", 0.16, 0.08),      # Cool Titanium-Silver Superstructure
            "C7_HullAccent": ("#B81D24", 0.20, 0.15),     # Aggressive Crimson-Red Louvers & Flybridge Spear!
            "C7_BootStripe": ("#C81D26", 0.20, 0.15),     # Crimson Sport Boot Stripe!
            "C7_AntiFoul": ("#0C0E12", 0.70, 0.00),
            "C7_DeckWhite": ("#313842", 0.84, 0.00),      # Charcoal Tactical Diamond Non-Skid
            "C7_Teak": ("#454D58", 0.64, 0.00),           # Brushed Storm-Grey EVA SeaDek Planks!
            "C7_WalnutFloor": ("#282B30", 0.32, 0.00),    # Smoked Charcoal Oak Salon Floor
            "C7_WalnutCab": ("#1C1F24", 0.24, 0.10),
            "C7_Marble": ("#2D3138", 0.18, 0.05),         # Nero Marquina Dark Marble Countertops!
            "C7_VinylWhite": ("#262C35", 0.46, 0.00),     # Carbon Sport Leather Seating
            "C7_VinylGrey": ("#4B5360", 0.48, 0.00),      # Storm-Grey Sunpads
            "C7_VinylDark": ("#B81D24", 0.46, 0.00),      # Crimson Accent Backrest!
            "C7_SunroofCanvas": ("#262B33", 0.86, 0.00),  # Blackout Woven Sunroof Canvas
            "C7_DashDark": ("#0C0E12", 0.34, 0.10),
            "C7_BlackTrim": ("#0B0D10", 0.22, 0.35),
            "C7_Stainless": ("#B8C2CE", 0.16, 0.92),
            "C7_PodGrey": ("#1B1E24", 0.32, 0.60),
            "C7_PropBronze": ("#BFA064", 0.16, 0.94),
        },
        "glass_tint": "#070B10",
        "glass_alpha": 0.60,
    },
    {
        "id": "monaco_champagne",
        "label": "Cruiser Boat 7C — Monaco Champagne-Bronze",
        "deck_style": "teak",
        "colors": {
            "C7_HullTopsides": ("#9E8B73", 0.17, 0.38),   # Metallic Champagne-Bronze Hull Topsides!
            "C7_HullWhite": ("#F8F6F2", 0.14, 0.00),      # Warm Alabaster Pearl Superstructure
            "C7_HullAccent": ("#2B231B", 0.22, 0.25),     # Espresso-Bronze Intake Louvers
            "C7_BootStripe": ("#34281E", 0.22, 0.20),     # Deep Espresso Boot Stripe
            "C7_AntiFoul": ("#1C1917", 0.68, 0.00),
            "C7_DeckWhite": ("#EFECE6", 0.74, 0.00),
            "C7_Teak": ("#A47B4E", 0.50, 0.00),           # Rich Honey-Amber Teak
            "C7_WalnutFloor": ("#523B28", 0.32, 0.00),
            "C7_WalnutCab": ("#3D2A1B", 0.22, 0.00),
            "C7_Marble": ("#F3EFE6", 0.16, 0.00),         # Travertine Cream Marble
            "C7_VinylWhite": ("#F5EFE6", 0.44, 0.00),     # Cream Cashmere Leather
            "C7_VinylGrey": ("#C7BA9E", 0.48, 0.00),      # Warm Champagne-Taupe Sunpads
            "C7_VinylDark": ("#3B2D22", 0.50, 0.00),      # Espresso Contrast Backrest
            "C7_SunroofCanvas": ("#DFD8CB", 0.85, 0.00),  # Warm Linen Canvas
            "C7_DashDark": ("#1D1916", 0.34, 0.10),
            "C7_BlackTrim": ("#191614", 0.25, 0.28),
            "C7_Stainless": ("#E4E2DC", 0.14, 0.95),
            "C7_PodGrey": ("#312E2B", 0.34, 0.55),
            "C7_PropBronze": ("#D4B474", 0.15, 0.94),
        },
        "glass_tint": "#1A1816",
        "glass_alpha": 0.50,
    },
]


# ---------------------------------------------------------------------------
# 1. Procedural Cycles Marine Shaders (Blender 5.2+/5.3 Safe via `vflib.bake`)
# ---------------------------------------------------------------------------
def build_procedural_material(
    mat_name: str,
    hex_col: str,
    rough: float,
    metal: float,
    *,
    deck_style: str = "teak",
) -> bpy.types.Material:
    mat = mats.pbr(mat_name, hex_col, roughness=rough, metallic=metal)
    nt = mat.node_tree
    b = mats.bsdf(mat)
    base_lin = mats.linear(hex_col)

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1150, 0)

    if mat_name == "C7_Teak":
        # 105 mm luxury superyacht fore-aft Burmese teak planks + 4.5 mm recessed black thiokol caulk seams + stretched fiber grain!
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        sep.location = (-920, 200)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(sep, "Vector"))

        div = nt.nodes.new("ShaderNodeMath")
        div.operation = "DIVIDE"
        div.inputs[1].default_value = 0.105
        div.location = (-740, 220)
        nt.links.new(sep.outputs["X"], div.inputs[0])

        frac = nt.nodes.new("ShaderNodeMath")
        frac.operation = "FRACT"
        frac.location = (-580, 220)
        nt.links.new(div.outputs[0], frac.inputs[0])

        sub = nt.nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[1].default_value = 0.5
        sub.location = (-420, 220)
        nt.links.new(frac.outputs[0], sub.inputs[0])

        absm = nt.nodes.new("ShaderNodeMath")
        absm.operation = "ABSOLUTE"
        absm.location = (-260, 220)
        nt.links.new(sub.outputs[0], absm.inputs[0])

        seam_ramp = nt.nodes.new("ShaderNodeMapRange")
        seam_ramp.clamp = True
        seam_ramp.inputs["From Min"].default_value = 0.448
        seam_ramp.inputs["From Max"].default_value = 0.476
        seam_ramp.inputs["To Min"].default_value = 1.0  # plank body
        seam_ramp.inputs["To Max"].default_value = 0.0  # recessed black caulk groove
        seam_ramp.location = (-80, 220)
        nt.links.new(absm.outputs[0], seam_ramp.inputs["Value"])

        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (26.0, 2.8, 12.0)
        mp.location = (-920, -120)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(mp, "Vector"))

        noise = nt.nodes.new("ShaderNodeTexNoise")
        mats.set_in(noise, "Scale", 8.0)
        mats.set_in(noise, "Detail", 6.0)
        mats.set_in(noise, "Roughness", 0.65)
        noise.location = (-680, -120)
        nt.links.new(mats.sock(mp, "Vector", output=True), mats.sock(noise, "Vector"))

        caulk_col = (0.008, 0.007, 0.006, 1.0) if deck_style == "teak" else (0.015, 0.017, 0.020, 1.0)
        grain_col = bake.mix_rgba(
            nt,
            mats.sock(noise, "Fac", output=True),
            tuple(c * 0.78 for c in base_lin) + (1.0,),
            tuple(min(1.0, c * 1.22) for c in base_lin) + (1.0,),
        )
        final_col = bake.mix_rgba(nt, seam_ramp.outputs["Result"], caulk_col, grain_col)
        nt.links.new(final_col, mats.sock(b, "Base Color"))

        r_map = nt.nodes.new("ShaderNodeMapRange")
        r_map.inputs["To Min"].default_value = 0.88
        r_map.inputs["To Max"].default_value = rough
        nt.links.new(seam_ramp.outputs["Result"], r_map.inputs["Value"])
        nt.links.new(r_map.outputs["Result"], mats.sock(b, "Roughness"))

        h_add = nt.nodes.new("ShaderNodeMath")
        h_add.operation = "MULTIPLY_ADD"
        h_add.inputs[1].default_value = 0.14
        nt.links.new(mats.sock(noise, "Fac", output=True), h_add.inputs[0])
        nt.links.new(seam_ramp.outputs["Result"], h_add.inputs[2])

        bump = nt.nodes.new("ShaderNodeBump")
        mats.set_in(bump, "Strength", 0.65)
        mats.set_in(bump, "Distance", 0.0024)
        nt.links.new(h_add.outputs[0], mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))

    elif mat_name in ("C7_WalnutFloor", "C7_WalnutCab"):
        # Luxury European walnut planks (`95 mm` on sole) & glossy walnut wood grain
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (14.0, 2.2, 8.0)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(mp, "Vector"))
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "X"
        mats.set_in(wave, "Scale", 5.5)
        mats.set_in(wave, "Distortion", 6.5)
        mats.set_in(wave, "Detail", 5.0)
        nt.links.new(mats.sock(mp, "Vector", output=True), mats.sock(wave, "Vector"))
        w_col = bake.mix_rgba(
            nt,
            mats.sock(wave, "Fac", output=True),
            tuple(c * 0.68 for c in base_lin) + (1.0,),
            tuple(min(1.0, c * 1.24) for c in base_lin) + (1.0,),
        )
        nt.links.new(w_col, mats.sock(b, "Base Color"))
        bump = nt.nodes.new("ShaderNodeBump")
        mats.set_in(bump, "Strength", 0.22)
        mats.set_in(bump, "Distance", 0.0008)
        nt.links.new(mats.sock(wave, "Fac", output=True), mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))

    elif mat_name == "C7_Marble":
        # Veined Carrara / Nero Marquina Galley Marble!
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "DIAGONAL"
        mats.set_in(wave, "Scale", 2.8)
        mats.set_in(wave, "Distortion", 11.0)
        mats.set_in(wave, "Detail", 6.0)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(wave, "Vector"))

        vein_mr = nt.nodes.new("ShaderNodeMapRange")
        vein_mr.clamp = True
        vein_mr.inputs["From Min"].default_value = 0.72
        vein_mr.inputs["From Max"].default_value = 0.96
        vein_mr.inputs["To Min"].default_value = 0.0
        vein_mr.inputs["To Max"].default_value = 1.0
        nt.links.new(mats.sock(wave, "Fac", output=True), vein_mr.inputs["Value"])

        is_dark = (base_lin[0] + base_lin[1] + base_lin[2]) / 3.0 < 0.15
        vein_col = (0.72, 0.72, 0.70, 1.0) if is_dark else (0.48, 0.50, 0.52, 1.0)
        m_col = bake.mix_rgba(nt, vein_mr.outputs["Result"], base_lin + (1.0,), vein_col)
        nt.links.new(m_col, mats.sock(b, "Base Color"))
        mats.add_bump_noise(mat, scale=35.0, strength=0.04, distance=0.0003, roughness_variation=0.03)

    elif mat_name == "C7_DeckWhite":
        # 45-degree molded diamond marine non-skid (`Voronoi MANHATTAN`)!
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(45.0))
        mp.inputs["Scale"].default_value = (95.0, 95.0, 95.0)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(mp, "Vector"))

        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.feature = "F1"
        vor.distance = "MANHATTAN"
        mats.set_in(vor, "Randomness", 0.06)
        mats.set_in(vor, "Scale", 1.0)
        nt.links.new(mats.sock(mp, "Vector", output=True), mats.sock(vor, "Vector"))

        ns_col = bake.mix_rgba(
            nt,
            mats.sock(vor, "Distance", output=True),
            tuple(min(1.0, c * 1.06) for c in base_lin) + (1.0,),
            tuple(c * 0.88 for c in base_lin) + (1.0,),
        )
        nt.links.new(ns_col, mats.sock(b, "Base Color"))

        r_mr = nt.nodes.new("ShaderNodeMapRange")
        r_mr.inputs["To Min"].default_value = max(0.55, rough - 0.10)
        r_mr.inputs["To Max"].default_value = min(0.96, rough + 0.08)
        nt.links.new(mats.sock(vor, "Distance", output=True), r_mr.inputs["Value"])
        nt.links.new(r_mr.outputs["Result"], mats.sock(b, "Roughness"))

        bump = nt.nodes.new("ShaderNodeBump")
        bump.invert = True
        mats.set_in(bump, "Strength", 0.45)
        mats.set_in(bump, "Distance", 0.0016)
        nt.links.new(mats.sock(vor, "Distance", output=True), mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))

    elif mat_name == "C7_SunroofCanvas":
        # Woven Sunbrella retractable sunroof fabric!
        w1 = nt.nodes.new("ShaderNodeTexWave")
        w1.wave_type = "BANDS"
        w1.bands_direction = "X"
        mats.set_in(w1, "Scale", 110.0)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(w1, "Vector"))
        w2 = nt.nodes.new("ShaderNodeTexWave")
        w2.wave_type = "BANDS"
        w2.bands_direction = "Y"
        mats.set_in(w2, "Scale", 110.0)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(w2, "Vector"))
        add_w = nt.nodes.new("ShaderNodeMath")
        add_w.operation = "MULTIPLY"
        nt.links.new(mats.sock(w1, "Fac", output=True), add_w.inputs[0])
        nt.links.new(mats.sock(w2, "Fac", output=True), add_w.inputs[1])
        c_col = bake.mix_rgba(
            nt,
            add_w.outputs[0],
            tuple(c * 0.90 for c in base_lin) + (1.0,),
            tuple(min(1.0, c * 1.08) for c in base_lin) + (1.0,),
        )
        nt.links.new(c_col, mats.sock(b, "Base Color"))
        bump = nt.nodes.new("ShaderNodeBump")
        mats.set_in(bump, "Strength", 0.28)
        mats.set_in(bump, "Distance", 0.0010)
        nt.links.new(add_w.outputs[0], mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))

    elif mat_name in ("C7_VinylWhite", "C7_VinylGrey", "C7_VinylDark"):
        mats.add_bump_noise(mat, scale=320.0, strength=0.24, distance=0.0011, kind="voronoi", roughness_variation=0.06)

    elif mat_name == "C7_ScreenGlow":
        # Garmin Glass-Bridge Bathymetric Sonar & Chartplotter MFD UI!
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "RINGS"
        mats.set_in(wave, "Scale", 16.0)
        mats.set_in(wave, "Distortion", 4.5)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(wave, "Vector"))
        s_col = bake.mix_rgba(
            nt,
            mats.sock(wave, "Fac", output=True),
            (0.005, 0.035, 0.090, 1.0),
            (0.045, 0.580, 0.760, 1.0),
        )
        nt.links.new(s_col, mats.sock(b, "Base Color"))
        mats.set_in(b, "Roughness", 0.30)

    elif metal >= 0.5:
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (16.0, 120.0, 120.0)
        nt.links.new(mats.sock(tc, "Object", output=True), mats.sock(mp, "Vector"))
        ns = nt.nodes.new("ShaderNodeTexNoise")
        mats.set_in(ns, "Scale", 6.0)
        mats.set_in(ns, "Detail", 5.0)
        nt.links.new(mats.sock(mp, "Vector", output=True), mats.sock(ns, "Vector"))
        r_mr = nt.nodes.new("ShaderNodeMapRange")
        r_mr.inputs["To Min"].default_value = max(0.06, rough - 0.05)
        r_mr.inputs["To Max"].default_value = min(0.58, rough + 0.06)
        nt.links.new(mats.sock(ns, "Fac", output=True), r_mr.inputs["Value"])
        nt.links.new(r_mr.outputs["Result"], mats.sock(b, "Roughness"))
        bump = nt.nodes.new("ShaderNodeBump")
        mats.set_in(bump, "Strength", 0.10)
        mats.set_in(bump, "Distance", 0.0005)
        nt.links.new(mats.sock(ns, "Fac", output=True), mats.sock(bump, "Height"))
        nt.links.new(mats.sock(bump, "Normal", output=True), mats.sock(b, "Normal"))

    else:
        mats.add_bump_noise(mat, scale=65.0, strength=0.05, distance=0.0003, kind="noise", roughness_variation=0.03)

    return mat


def apply_variant_materials(variant: dict) -> dict[str, bpy.types.Material]:
    vid = variant["id"]
    built: dict[str, bpy.types.Material] = {}
    for mat_name, (hex_c, r_val, m_val) in variant["colors"].items():
        built[mat_name] = build_procedural_material(
            mat_name, hex_c, r_val, m_val, deck_style=variant["deck_style"]
        )
    built["C7_ScreenGlow"] = build_procedural_material("C7_ScreenGlow", "#0E3F5E", 0.22, 0.0)

    # Preserve all 5 architectural glass materials per variant (so hull windows stay pitch-obsidian & windshield stays crystal clear!)
    built["C7_HullGlass"] = mats.pbr(
        f"M_CruiserBoat7c_{vid}_HullGlass", "#020407", roughness=0.18, metallic=0.0, coat=0.0, specular=0.05, ior=1.08, alpha=1.0
    )
    built["C7_Glass"] = mats.pbr(
        f"M_CruiserBoat7c_{vid}_Glass",
        variant["glass_tint"],
        roughness=0.02,
        metallic=0.0,
        coat=0.0,
        specular=0.42,
        ior=1.01,
        alpha=variant["glass_alpha"],
        role="glass",
        roblox_material="Glass",
    )
    built["C7_SideGlass"] = mats.pbr(
        f"M_CruiserBoat7c_{vid}_SideGlass", "#071018", roughness=0.02, metallic=0.0, coat=0.0, specular=0.32, ior=1.02, alpha=0.84, role="glass"
    )
    built["C7_VenturiGlass"] = mats.pbr(
        f"M_CruiserBoat7c_{vid}_VenturiGlass", "#060C12", roughness=0.03, metallic=0.0, coat=0.0, specular=0.28, ior=1.02, alpha=0.86, role="glass"
    )
    built["C7_SkylightGlass"] = mats.pbr(
        f"M_CruiserBoat7c_{vid}_SkylightGlass", "#253240", roughness=0.08, metallic=0.0, coat=0.0, specular=0.35, ior=1.04, alpha=0.92, role="glass"
    )

    built["C7_NavRed"] = mats.pbr("C7_NavRed", "#FF2424", roughness=0.12, emission="#FF2424", emission_strength=4.0, role="neon")
    built["C7_NavGreen"] = mats.pbr("C7_NavGreen", "#1EE65A", roughness=0.12, emission="#1EE65A", emission_strength=4.0, role="neon")
    built["C7_LightWhite"] = mats.pbr("C7_LightWhite", "#FFFDF4", roughness=0.10, emission="#FFFDF4", emission_strength=3.2, role="neon")
    built["C7_UnderwaterBlue"] = mats.pbr("C7_UnderwaterBlue", "#14B8FF", roughness=0.10, emission="#14B8FF", emission_strength=4.2, role="neon")
    return built


def remap_source_materials(src_col: bpy.types.Collection, v_mats: dict[str, bpy.types.Material]) -> None:
    """Assign variant procedural materials onto source meshes; split Hull_Main topsides into C7_HullTopsides!"""
    for ob in core.objects_in(src_col, types=("MESH",)):
        for i, slot in enumerate(ob.material_slots):
            if slot.material is None:
                continue
            mname = slot.material.name
            # Strip Blender .001 suffixes or previous variant prefixes
            base_key = None
            for k in v_mats:
                if mname == k or mname.startswith(k + ".") or mname.endswith("_" + k.replace("C7_", "")):
                    base_key = k
                    break
            if base_key is None:
                continue
            if ob.name in ("Hull_Main", "Hull_WindowMullions") and base_key in ("C7_HullWhite", "C7_HullTopsides"):
                ob.data.materials[i] = v_mats["C7_HullTopsides"]
            else:
                ob.data.materials[i] = v_mats[base_key]


# ---------------------------------------------------------------------------
# 2. Collapse into 14 Game-Ready Parts & Pack Shared Non-Overlapping 2K UV Atlas
# ---------------------------------------------------------------------------
def build_joined_lod0_parts(
    src_col: bpy.types.Collection,
    dest_col_name: str,
) -> tuple[bpy.types.Collection, dict[str, bpy.types.Object]]:
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
        while len(joined.data.uv_layers) > 1:
            joined.data.uv_layers.remove(joined.data.uv_layers[-1])
        if not joined.data.uv_layers:
            joined.data.uv_layers.new(name="UVMap")
        else:
            joined.data.uv_layers[0].name = "UVMap"
        joined.data.uv_layers.active_index = 0
        part_objs[pname] = joined

    # Pack all 12 opaque parts onto ONE shared non-overlapping [0..1]^2 UV atlas with prioritized hero texel density!
    # Priority weighting gives Hull/Deck/Superstructure/InteriorSalon/Flybridge 4x more texel area (razor-sharp teak & marble!)
    # while uniform chrome/bronze CAD hardware (cleats/props/steering/throttle) packs compactly in 12% of the sheet!
    opaque = [part_objs[k] for k in OPAQUE_PARTS if k in part_objs]
    core.ensure_object_mode()
    for ob in opaque:
        bm_s = bmesh.new()
        bm_s.from_mesh(ob.data)
        border_edges = [e for e in bm_s.edges if len({f.material_index for f in e.link_faces}) > 1]
        if border_edges:
            bmesh.ops.split_edges(bm_s, edges=border_edges)
        bm_s.to_mesh(ob.data)
        bm_s.free()

    # Smart-project each part in real-world meter scale, then weight relative island sizes before fitting into [0..1]^2!
    uv_weights = {
        "Deck": 1.65,
        "Hull": 1.25,
        "Superstructure": 1.20,
        "InteriorSalon": 1.45,
        "Flybridge": 1.35,
        "HullAccent": 1.00,
        "Electronics": 0.60,
        "Propulsion": 0.55,
        "RailsHardware": 0.35,
        "Props": 0.32,
        "Steering": 0.28,
        "Throttle": 0.28,
    }
    for ob in opaque:
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.002, scale_to_bounds=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        ob.select_set(False)
        w = uv_weights.get(ob.get("sc_part", ""), 1.0)
        uv_layer = ob.data.uv_layers.active
        if uv_layer and abs(w - 1.0) > 1e-4:
            for d in uv_layer.data:
                d.uv.x *= w
                d.uv.y *= w

    # Jointly pack all 12 weighted parts strictly inside [0..1]^2 (`scale=True` scales uniformly to fit [0..1] while preserving relative weights!)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in opaque:
        o.select_set(True)
    bpy.context.view_layer.objects.active = opaque[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.0022)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in opaque:
        o.select_set(False)

    # Hard assertion: verify 100% of UVs stay strictly inside [0, 1] (zero wrapping / OOB!)
    for ob in opaque:
        uv_layer = ob.data.uv_layers.active
        us = [d.uv.x for d in uv_layer.data]
        vs = [d.uv.y for d in uv_layer.data]
        if min(us) < -1e-4 or max(us) > 1.0001 or min(vs) < -1e-4 or max(vs) > 1.0001:
            raise RuntimeError(
                f"UV out of [0,1] on {ob.name}: u=[{min(us):.4f},{max(us):.4f}] v=[{min(vs):.4f},{max(vs):.4f}]"
            )

    # Re-weld 3D vertices back to 100% watertight while preserving the isolated per-loop UVs & locked seams!
    for ob in opaque:
        bm_w = bmesh.new()
        bm_w.from_mesh(ob.data)
        bmesh.ops.remove_doubles(bm_w, verts=bm_w.verts[:], dist=1e-6)
        bm_w.to_mesh(ob.data)
        bm_w.free()
        ob.data.update()

    return dest_col, part_objs


# ---------------------------------------------------------------------------
# 3. True 2048x2048 Cycles GPU (OPTIX) PBR Texture Baker
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
        tn.label = "__VF_BAKE_TARGET__"
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


def bake_variant_pbr_maps(
    part_objs: dict[str, bpy.types.Object],
    variant_id: str,
    out_dir: str,
    *,
    cached_ao: np.ndarray | None = None,
    res: int = BAKE_RES,
) -> tuple[bpy.types.Material, dict[str, str], np.ndarray]:
    sc = bpy.context.scene
    backend = bake.enable_cycles_gpu(sc)
    core.log(f"[bake:{variant_id}] Cycles GPU-only backend={backend}, resolution={res}x{res}")

    opaque_list = [part_objs[k] for k in OPAQUE_PARTS if k in part_objs]
    tmp_col = core.fresh_collection("__VF_BakeTmp")
    dups = [gameready.bake_object(o, f"__bake_{i}", tmp_col) for i, o in enumerate(opaque_list)]
    proxy = gameready.join(dups, "__VF_BakeProxy")
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
        # 1. Physical Cycles Raytraced AO (32 samples — cached across identical yacht geometry!)
        if cached_ao is None:
            img_ao_raw = _make_bake_image("__raw_ao", res, "Non-Color")
            t_nodes = _attach_bake_targets(proxy, img_ao_raw)
            sc.cycles.samples = 32
            bpy.ops.object.bake(type="AO")
            ao_arr = _read_float_img(img_ao_raw)[..., 0].copy()
            _remove_bake_targets(t_nodes)
            bpy.data.images.remove(img_ao_raw)
            bake.cooldown(0.8)
        else:
            ao_arr = cached_ao

        # 2. OpenGL Tangent-Space Normal Map (16 samples, +Y Green)
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
        bake.cooldown(0.6)

        # 3. Roughness Map (4 samples)
        img_r_raw = _make_bake_image("__raw_r", res, "Non-Color")
        t_nodes = _attach_bake_targets(proxy, img_r_raw)
        sc.cycles.samples = 4
        bpy.ops.object.bake(type="ROUGHNESS")
        rough_arr = _read_float_img(img_r_raw)[..., 0].copy()
        _remove_bake_targets(t_nodes)
        bpy.data.images.remove(img_r_raw)

        # 4. Base Color (Emission override, 2 samples -> linear float!)
        img_bc_raw = _make_bake_image("__raw_bc", res, "Non-Color")
        undo_bc = _route_socket_to_emission(used_mats, "Base Color")
        t_nodes = _attach_bake_targets(proxy, img_bc_raw)
        sc.cycles.samples = 2
        bpy.ops.object.bake(type="EMIT")
        bc_lin = _read_float_img(img_bc_raw)[..., :3].copy()
        _remove_bake_targets(t_nodes)
        _restore_emission(undo_bc)
        bpy.data.images.remove(img_bc_raw)

        # 5. Metalness (Emission override, 1 sample)
        img_m_raw = _make_bake_image("__raw_m", res, "Non-Color")
        undo_m = _route_socket_to_emission(used_mats, "Metallic")
        t_nodes = _attach_bake_targets(proxy, img_m_raw)
        sc.cycles.samples = 1
        bpy.ops.object.bake(type="EMIT")
        metal_arr = _read_float_img(img_m_raw)[..., 0].copy()
        _remove_bake_targets(t_nodes)
        _restore_emission(undo_m)
        bpy.data.images.remove(img_m_raw)
        bake.cooldown(0.6)

    finally:
        for o, h_state in prev_hide:
            o.hide_render = h_state
        core.clear_collection(tmp_col)
        bpy.data.collections.remove(tmp_col)

    # Composite subtle physical Cycles AO (26% depth so bright pure-white yacht gelcoat stays crisp & radiant!)
    ao_clamped = np.clip(ao_arr, 0.0, 1.0)
    ao_factor = (0.74 + 0.26 * ao_clamped)[..., None]
    bc_shaded_lin = np.clip(bc_lin * ao_factor, 0.0, 1.0)
    color_srgb_rgba = np.ones((res, res, 4), dtype=np.float32)
    color_srgb_rgba[..., :3] = bake.lin_arr_to_srgb(bc_shaded_lin)

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

    prefix = f"T_CruiserBoat7c_{variant_id}"
    paths = {
        "Color": os.path.join(out_dir, f"{prefix}_Color.png"),
        "Normal": os.path.join(out_dir, f"{prefix}_Normal.png"),
        "Roughness": os.path.join(out_dir, f"{prefix}_Roughness.png"),
        "Metalness": os.path.join(out_dir, f"{prefix}_Metalness.png"),
        "AO": os.path.join(out_dir, f"{prefix}_AO.png"),
        "ORM": os.path.join(out_dir, f"{prefix}_ORM.png"),
    }
    img_c = bake.save_png_8bit(color_srgb_rgba, paths["Color"], "sRGB")
    img_n = bake.save_png_8bit(norm_rgba, paths["Normal"], "Non-Color")
    img_r = bake.save_png_8bit(rough_rgba, paths["Roughness"], "Non-Color")
    img_m = bake.save_png_8bit(metal_rgba, paths["Metalness"], "Non-Color")
    bake.save_png_8bit(ao_rgba, paths["AO"], "Non-Color")
    bake.save_png_8bit(orm_rgba, paths["ORM"], "Non-Color")

    # Wire single baked game-ready Principled BSDF material exclusively to baked 2048x2048 PNGs!
    baked_mat, bsdf_node = mats._new_node_material(f"M_CruiserBoat7c_{variant_id}_Baked")
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
# 4. Seam-Locked 4-Tier LOD Chain Generator (`LOD0` -> `LOD1` -> `LOD2` -> `LOD3`)
# ---------------------------------------------------------------------------
LOD_SPECS = [
    # (lod_level, base_ratio, hull_angle_deg, cull_parts, screen_size)
    (1, 0.48, 2.0, set(), 0.50),
    (2, 0.24, 3.4, {"Throttle"}, 0.25),
    (3, 0.11, 5.2, {"Steering", "Throttle", "InteriorSalon"}, 0.10),
]


def build_lod_chain(lod0_parts: dict[str, bpy.types.Object], base_prefix: str = "CruiserBoat7c") -> dict[str, dict]:
    lod_summary: dict[str, dict] = {
        "LOD0": {
            "tris": sum(gameready.triangle_count(o, False) for o in lod0_parts.values()),
            "parts": len(lod0_parts),
            "screen_size": 1.0,
            "glb": "lods/cruiser_boat_7c_LOD0.glb",
        }
    }

    for lvl, r_def, hull_ang, culled, scr_sz in LOD_SPECS:
        col_name = f"{base_prefix}_LOD{lvl}"
        l_col = core.fresh_collection(col_name)
        lvl_objs: list[bpy.types.Object] = []

        for pname, src in lod0_parts.items():
            if pname in culled:
                continue
            cp = src.copy()
            cp.data = src.data.copy()
            cp.name = f"{pname}_LOD{lvl}"
            cp.data.name = cp.name
            l_col.objects.link(cp)
            cp["sc_part"] = pname
            cp["sc_role"] = src.get("sc_role", "solid")

            dec = cp.modifiers.new("VF_LOD_Decimate", "DECIMATE")
            if pname == "Hull":
                dec.decimate_type = "DISSOLVE"
                dec.angle_limit = math.radians(hull_ang)
                dec.delimit = {"UV", "SEAM", "SHARP", "MATERIAL"}
                dec.use_dissolve_boundaries = False
            else:
                dec.decimate_type = "COLLAPSE"
                dec.ratio = {1: 0.78, 2: 0.56, 3: 0.36}[lvl] if pname in ("HullAccent", "Glass") else r_def
                dec.delimit = {"UV", "SEAM", "SHARP"}
                dec.use_collapse_triangulate = True

            with bpy.context.temp_override(
                object=cp,
                active_object=cp,
                selected_objects=[cp],
                selected_editable_objects=[cp],
            ):
                bpy.ops.object.modifier_apply(modifier=dec.name)

            if pname in ("Hull", "HullAccent"):
                bm_t = bmesh.new()
                bm_t.from_mesh(cp.data)
                if pname == "Hull":
                    bmesh.ops.triangulate(bm_t, faces=bm_t.faces[:])
                else:
                    # Slight outboard offset prevents simplified louver chords from dipping into simplified Hull!
                    mw = cp.matrix_world
                    dx_out = {1: 0.004, 2: 0.008, 3: 0.014}[lvl]
                    for v in bm_t.verts:
                        wco = mw @ v.co
                        if abs(wco.x) > 0.20:
                            v.co.x += math.copysign(dx_out, wco.x)
                bm_t.to_mesh(cp.data)
                bm_t.free()
                cp.data.update()
            lvl_objs.append(cp)

        os.makedirs(LODS_ROOT, exist_ok=True)
        glb_lod = os.path.join(LODS_ROOT, f"cruiser_boat_7c_LOD{lvl}.glb")
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
            "glb": f"lods/cruiser_boat_7c_LOD{lvl}.glb",
        }
        core.log(f"[LOD{lvl}] {lod_tris:,} tris across {len(lvl_objs)} parts -> {glb_lod}")

    return lod_summary


# ---------------------------------------------------------------------------
# 5. Export Variants (GLB + Roblox FBX + Manifest + Studio Luau)
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

    # Metric Textured GLB (embeds baked 2048x2048 PBR maps!)
    glb_path = os.path.join(out_dir, f"cruiser_boat_7c_{variant['id']}.glb")
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

    # Roblox FBX + Manifest + Studio Setup Luau
    collide_parts = {"Hull", "Deck", "Superstructure", "Flybridge", "InteriorSalon"}
    accent_srgb = mats.parse_color(variant["colors"]["C7_HullAccent"][0])
    glass_srgb = mats.parse_color(variant["glass_tint"])

    parts_spec = []
    for pname, pob in part_objs.items():
        role = pob.get("sc_role", "solid")
        spec = dict(
            name=pname,
            objects=[pob],
            role="solid" if pname in OPAQUE_PARTS and pname != "HullAccent" else role,
            collide=pname in collide_parts,
            render_fidelity="Precise" if pname in ("Hull", "Superstructure", "Glass") else "Automatic",
        )
        if pname == "HullAccent":
            spec["role"] = "paint"
            spec["material"] = "SmoothPlastic"
            spec["color"] = accent_srgb
        elif pname == "Glass":
            spec["role"] = "glass"
            spec["transparency"] = round(1.0 - variant["glass_alpha"], 2)
            spec["color"] = glass_srgb
        parts_spec.append(spec)

    lo, hi = core.world_bbox(all_v_objs)
    hinges = [
        dict(name="Steering", socket="HingeSteering", part0="@primary", part1="Steering", actuator="Servo", lower=-180, upper=180, speed=8),
        dict(name="Throttle", socket="HingeThrottle", part0="@primary", part1="Throttle", actuator="Servo", lower=-45, upper=45, speed=6),
        dict(name="Props", socket="HingeProps", part0="Propulsion", part1="Props", actuator="Motor", torque=1e6),
    ]
    asset_tag = "CruiserBoat7c" if variant["id"] == "reference_pearl" else f"CruiserBoat7c_{variant['id']}"
    export.export_roblox(
        asset_tag,
        out_dir,
        parts=parts_spec,
        source_collection=src_col,
        primary=dict(name="Boat", center=(lo + hi) * 0.5, size=hi - lo),
        hinges=hinges,
        attributes={"BoatType": "FlybridgeMotorYacht", "Variant": variant["id"], "LengthMeters": 18.3, "MaxSpeed": 34},
        tags=["Boat", "Yacht", "Flybridge"],
        reference="Hull",
        prebaked_material=baked_mat,
        prebaked_textures=rel_tex,
        extra_manifest=extra_manifest,
    )


# ---------------------------------------------------------------------------
# 6. Showroom Verification Renders (Heroes, Baked Macro Close-Up, 4-Yacht Lineup & 2x2 LOD Sheet)
# ---------------------------------------------------------------------------
def _compose_labeled_lod_grid(lod_tiles: list[tuple[str, str]], out_path: str) -> None:
    """Compose a razor-sharp 2x2 LOD0–LOD3 comparison sheet with header labels using PIL (fallback numpy)."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        w, h = 960, 600
        hdr = 54
        canvas = Image.new("RGB", (w * 2 + 8, h * 2 + hdr + 8), (20, 24, 30))
        draw = ImageDraw.Draw(canvas)
        try:
            font_lg = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 24)
            font_sm = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 18)
        except OSError:
            font_lg = ImageFont.load_default()
            font_sm = ImageFont.load_default()

        draw.text((22, 13), "CRUISER BOAT 7C  |  4-TIER SEAM-LOCKED LOD COMPARISON (Cycles OPTIX 2K Baked PBR)", fill=(238, 242, 248), font=font_lg)
        slots = [(0, hdr), (w + 8, hdr), (0, hdr + h + 8), (w + 8, hdr + h + 8)]
        for (lbl, tp), (ox, oy) in zip(lod_tiles, slots):
            im = Image.open(tp).convert("RGB").resize((w, h), Image.LANCZOS)
            canvas.paste(im, (ox, oy))
            draw.rectangle((ox + 14, oy + 14, ox + 360, oy + 48), fill=(18, 22, 28))
            draw.text((ox + 26, oy + 20), lbl, fill=(130, 232, 185), font=font_sm)
        tmp_out = os.path.join(tempfile.gettempdir(), f"__vf_lod_sheet_{os.getpid()}.png")
        canvas.save(tmp_out)
        cb._safe_copy(tmp_out, out_path)
        os.remove(tmp_out)
    except Exception:
        # Pure numpy fallback if PIL is unavailable inside Blender Python
        arrs = []
        for _lbl, tp in lod_tiles:
            im = bpy.data.images.load(tp)
            px = np.zeros(960 * 600 * 4, dtype=np.float32)
            im.pixels.foreach_get(px)
            bpy.data.images.remove(im)
            arrs.append(px.reshape((600, 960, 4)))
        grid = np.ones((1200, 1920, 4), dtype=np.float32)
        grid[600:1200, 0:960] = arrs[0]
        grid[600:1200, 960:1920] = arrs[1]
        grid[0:600, 0:960] = arrs[2]
        grid[0:600, 960:1920] = arrs[3]
        grid[598:602, :, :3] = 0.12
        grid[:, 958:962, :3] = 0.12
        bake.save_png_8bit(grid, out_path, "sRGB")


def render_variants_and_lods(
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

    saved_shots: dict[str, str] = {}

    for _lbl, lc in lod_cols:
        lc.hide_render = True
        lc.hide_viewport = True

    # 1. Per-variant hero 3/4 shots + Baked Macro Close-Ups on Reference Pearl!
    for vid, vcol in variant_cols.items():
        for other_id, other_col in variant_cols.items():
            other_col.hide_render = other_id != vid
            other_col.hide_viewport = other_id != vid

        v_meshes = core.objects_in(vcol, types=("MESH",))
        studio_col = render.setup_studio(v_meshes, backdrop="product")
        cam_d = bpy.data.cameras.new("C7_VarCam")
        cam = bpy.data.objects.new("C7_VarCam", cam_d)
        studio_col.objects.link(cam)
        sc.camera = cam
        try:
            sc.render.resolution_x = 1600
            sc.render.resolution_y = 1000
            # Magazine-cover 18.3 m yacht hero 3/4 framing (~78% frame fill, zero clipping!)
            render.frame_camera(cam, v_meshes, direction=(0.95, 1.05, 0.32), lens=52.0, margin=0.72, aspect=1600 / 1000)
            p_hero = os.path.join(out_dir, f"variant_{vid}.png")
            bake.render_still_safe(sc, p_hero)
            saved_shots[f"variant_{vid}"] = p_hero

            if vid == "reference_pearl":
                # Macro Close-Up 1: Aft Burmese Teak Swim Platform, Transom Stairs, Lounge Leather, Baked AO & Normal Bump!
                cam.location = Vector((3.25, -10.65, 3.20))
                cam.data.lens = 40.0
                cam.rotation_euler = (Vector((0.0, -5.85, 1.80)) - cam.location).to_track_quat("-Z", "Y").to_euler()
                p_macro = os.path.join(out_dir, "baked_closeup.png")
                bake.render_still_safe(sc, p_macro)
                saved_shots["baked_closeup"] = p_macro

                # Macro Close-Up 2: Foredeck Diamond Non-Skid, Split Loungers, Skylights, Panoramic Windshield & Flybridge!
                cam.location = Vector((3.20, 8.95, 4.65))
                cam.data.lens = 38.0
                cam.rotation_euler = (Vector((0.0, 2.20, 2.85)) - cam.location).to_track_quat("-Z", "Y").to_euler()
                p_fore = os.path.join(out_dir, "baked_foredeck_closeup.png")
                bake.render_still_safe(sc, p_fore)
                saved_shots["baked_foredeck_closeup"] = p_fore
        finally:
            core.clear_collection(studio_col)
            bpy.data.collections.remove(studio_col)

    # 2. All 4 Superyacht Variants Side-by-Side Echelon Showroom Lineup!
    offsets_x = {
        "reference_pearl": -9.00,
        "mediterranean_navy": -3.00,
        "stealth_graphite": 3.00,
        "monaco_champagne": 9.00,
    }
    offsets_y = {
        "reference_pearl": 4.50,
        "mediterranean_navy": 1.50,
        "stealth_graphite": -1.50,
        "monaco_champagne": -4.50,
    }
    all_lineup_meshes: list[bpy.types.Object] = []
    for vid, vcol in variant_cols.items():
        vcol.hide_render = False
        vcol.hide_viewport = False
        dx, dy = offsets_x[vid], offsets_y[vid]
        for o in vcol.objects:
            o.location.x += dx
            o.location.y += dy
            if o.type == "MESH":
                all_lineup_meshes.append(o)
    bpy.context.view_layer.update()

    studio_line = render.setup_studio(all_lineup_meshes, backdrop="product")
    cam_d = bpy.data.cameras.new("C7_LineupCam")
    cam = bpy.data.objects.new("C7_LineupCam", cam_d)
    studio_line.objects.link(cam)
    sc.camera = cam
    try:
        sc.render.resolution_x = 2000
        sc.render.resolution_y = 1125
        render.frame_camera(cam, all_lineup_meshes, direction=(0.86, 0.94, 0.28), lens=48.0, margin=0.64, aspect=2000 / 1125)
        p_lineup = os.path.join(out_dir, "variants_lineup.png")
        bake.render_still_safe(sc, p_lineup)
        saved_shots["variants_lineup"] = p_lineup
    finally:
        core.clear_collection(studio_line)
        bpy.data.collections.remove(studio_line)

    # Park Reference Pearl at X=0 and the other 3 neatly alongside (+7.2, +14.4, +21.6 m, Y=0) for live Blender inspection!
    final_x = {
        "reference_pearl": 0.0,
        "mediterranean_navy": 7.20,
        "stealth_graphite": 14.40,
        "monaco_champagne": 21.60,
    }
    for vid, vcol in variant_cols.items():
        sx = final_x[vid] - offsets_x[vid]
        sy = -offsets_y[vid]
        for o in vcol.objects:
            o.location.x += sx
            o.location.y += sy
    bpy.context.view_layer.update()

    # 3. 4-Panel Seam-Locked LOD Comparison Sheet (`LOD0`, `LOD1`, `LOD2`, `LOD3`)!
    for vcol in variant_cols.values():
        vcol.hide_render = True
    lod_tile_paths: list[tuple[str, str]] = []
    for idx_l, (lbl, lcol) in enumerate(lod_cols):
        for _l2, lc2 in lod_cols:
            lc2.hide_render = lc2 != lcol
        l_meshes = core.objects_in(lcol, types=("MESH",))
        st_l = render.setup_studio(l_meshes, backdrop="product")
        cd = bpy.data.cameras.new("C7_LODCam")
        cm = bpy.data.objects.new("C7_LODCam", cd)
        st_l.objects.link(cm)
        sc.camera = cm
        try:
            sc.render.resolution_x = 960
            sc.render.resolution_y = 600
            sc.cycles.samples = 40
            render.frame_camera(cm, l_meshes, direction=(0.95, 1.05, 0.32), lens=52.0, margin=0.72, aspect=960 / 600)
            tp = os.path.join(tempfile.gettempdir(), f"__vf_c7_lod_{idx_l}.png")
            bake.render_still_safe(sc, tp, cooldown_sec=0.4)
            lod_tile_paths.append((lbl, tp))
        finally:
            core.clear_collection(st_l)
            bpy.data.collections.remove(st_l)

    if len(lod_tile_paths) == 4:
        p_lod_sheet = os.path.join(out_dir, "lod_comparison_sheet.png")
        _compose_labeled_lod_grid(lod_tile_paths, p_lod_sheet)
        saved_shots["lod_sheet"] = p_lod_sheet
    for _lbl, tp in lod_tile_paths:
        try:
            os.remove(tp)
        except OSError:
            pass

    for vcol in variant_cols.values():
        vcol.hide_render = False
        vcol.hide_viewport = False
    for idx_l, (_lbl, lcol) in enumerate(lod_cols):
        if idx_l > 0:
            lcol.hide_render = True
            lcol.hide_viewport = True

    return saved_shots


def main() -> int:
    # 1. Build clean 1:1 parametric source yacht (0 shell breaches, 0 Errors, 0 Warnings!)
    src_col, _raw_meshes = cb.build_all()

    variant_cols: dict[str, bpy.types.Collection] = {}
    variant_manifests: dict[str, dict] = {}
    cached_ao: np.ndarray | None = None
    flagship_parts: dict[str, bpy.types.Object] = {}
    lod_summary: dict[str, dict] = {}

    for var in VARIANTS:
        vid = var["id"]
        v_mats = apply_variant_materials(var)
        remap_source_materials(src_col, v_mats)

        col_name = f"Variant_{vid}"
        v_col, part_objs = build_joined_lod0_parts(src_col, col_name)
        tex_dir = os.path.join(TEXTURES_ROOT, vid)
        baked_mat, tex_paths, ao_out = bake_variant_pbr_maps(
            part_objs, vid, tex_dir, cached_ao=cached_ao, res=BAKE_RES
        )
        if cached_ao is None:
            cached_ao = ao_out

        # Assign single 2048x2048 baked PBR material onto all 12 opaque MeshParts (Glass & Lights retain specialized slots!)
        for pname in OPAQUE_PARTS:
            if pname in part_objs:
                pob = part_objs[pname]
                pob.data.materials.clear()
                pob.data.materials.append(baked_mat)
                pob.data.polygons.foreach_set("material_index", [0] * len(pob.data.polygons))
                pob.data.update()

        if vid == "reference_pearl":
            flagship_parts = part_objs
            lod_summary = build_lod_chain(flagship_parts, base_prefix="CruiserBoat7c")

        var_out = os.path.join(VARIANTS_ROOT, vid)
        extra_meta = {
            "variant": vid,
            "variantLabel": var["label"],
            "bakeResolution": BAKE_RES,
            "lods": lod_summary,
            "availableVariants": [v["id"] for v in VARIANTS],
        }
        export_variant_bundle(var, src_col, part_objs, baked_mat, tex_paths, var_out, extra_manifest=extra_meta)

        if vid == "reference_pearl":
            export_variant_bundle(var, src_col, part_objs, baked_mat, tex_paths, EXPORT_DIR, extra_manifest=extra_meta)
            os.makedirs(LODS_ROOT, exist_ok=True)
            cb._safe_copy(os.path.join(var_out, f"cruiser_boat_7c_{vid}.glb"), os.path.join(THIS_DIR, "cruiser_boat_7c.glb"))
            cb._safe_copy(os.path.join(var_out, f"cruiser_boat_7c_{vid}.glb"), os.path.join(LODS_ROOT, "cruiser_boat_7c_LOD0.glb"))

        variant_cols[vid] = v_col
        variant_manifests[vid] = {
            "label": var["label"],
            "dir": f"variants/{vid}",
            "glb": f"variants/{vid}/cruiser_boat_7c_{vid}.glb",
            "textures": {k: f"textures/{vid}/{os.path.basename(v)}" for k, v in tex_paths.items()},
        }

    src_col.hide_viewport = True
    src_col.hide_render = True

    lod_cols = [
        (f"LOD0  ({lod_summary['LOD0']['tris']:,} tris · 100%)", variant_cols["reference_pearl"]),
        (f"LOD1  ({lod_summary['LOD1']['tris']:,} tris · {100.0 * lod_summary['LOD1']['tris'] / lod_summary['LOD0']['tris']:.0f}%)", bpy.data.collections["CruiserBoat7c_LOD1"]),
        (f"LOD2  ({lod_summary['LOD2']['tris']:,} tris · {100.0 * lod_summary['LOD2']['tris'] / lod_summary['LOD0']['tris']:.0f}%)", bpy.data.collections["CruiserBoat7c_LOD2"]),
        (f"LOD3  ({lod_summary['LOD3']['tris']:,} tris · {100.0 * lod_summary['LOD3']['tris'] / lod_summary['LOD0']['tris']:.0f}%)", bpy.data.collections["CruiserBoat7c_LOD3"]),
    ]
    shots = render_variants_and_lods(variant_cols, lod_cols, RENDERS_DIR)

    # Frame all 4 Baked Showroom Variants nicely for live desktop Blender inspection
    visible_meshes = [o for vc in variant_cols.values() for o in core.objects_in(vc, types=("MESH",))]
    render.frame_viewport(visible_meshes)
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == "VIEW_3D":
                for sp in area.spaces:
                    if sp.type == "VIEW_3D":
                        sp.shading.type = "MATERIAL"
                        sp.overlay.show_extras = False

    showroom_blend = os.path.join(THIS_DIR, "cruiser_boat_7c_variants_lods.blend")
    bpy.ops.wm.save_as_mainfile(filepath=showroom_blend)
    core.log("saved master baked variants + LODs blend ->", showroom_blend)

    # Sync final master deliverables to Desktop Design Model Output
    os.makedirs(DESIGN_OUTPUT_DIR, exist_ok=True)
    cb._safe_copy(showroom_blend, os.path.join(DESIGN_OUTPUT_DIR, "cruiser_boat_7c_variants_lods.blend"))
    cb._safe_copy(showroom_blend, os.path.join(DESIGN_OUTPUT_DIR, "cruiser_boat_7c.blend"))
    cb._safe_copy(os.path.join(THIS_DIR, "cruiser_boat_7c.glb"), os.path.join(DESIGN_OUTPUT_DIR, "cruiser_boat_7c.glb"))
    for v in VARIANTS:
        vid = v["id"]
        cb._safe_copy(
            os.path.join(VARIANTS_ROOT, vid, f"cruiser_boat_7c_{vid}.glb"),
            os.path.join(DESIGN_OUTPUT_DIR, f"cruiser_boat_7c_{vid}.glb"),
        )
    if "variants_lineup" in shots:
        cb._safe_copy(shots["variants_lineup"], os.path.join(DESIGN_OUTPUT_DIR, "blender-render-check.png"))
    for _k, spath in shots.items():
        cb._safe_copy(spath, os.path.join(DESIGN_OUTPUT_DIR, f"cruiser_boat_7c_{os.path.basename(spath)}"))

    summary_json = os.path.join(THIS_DIR, "variants_and_lods_report.json")
    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump({"ok": True, "bake_res": BAKE_RES, "lods": lod_summary, "variants": variant_manifests}, fh, indent=2)
    core.log("DONE! Report written to", summary_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
