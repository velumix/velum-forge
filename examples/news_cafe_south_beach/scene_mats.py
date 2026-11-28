r"""Blender 5.2+ PBR Material Library for News Cafe South Beach (800 Ocean Dr & Surroundings).

Every shader follows Velum Forge Blender 5.2+ guardrails:
  - Uses `vflib.bake.mix_rgba()` (explicit RGBA socket indices `0, 6, 7 -> 2`)
  - Uses `ShaderNodeTexVoronoi.distance` (never deprecated `.metric`)
  - Tags image textures strictly `sRGB` (albedo/graphics) vs `Non-Color` (data/bump)
"""
from __future__ import annotations

import os
import sys

import bpy

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_BLENDER = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "engine", "blender"))
if ENGINE_BLENDER not in sys.path:
    sys.path.insert(0, ENGINE_BLENDER)

from vflib import bake, mats  # noqa: E402

TEX_SRC = os.path.join(THIS_DIR, "textures_src")


def _hex_lin(h: str) -> tuple[float, float, float, float]:
    return (*mats.linear(h), 1.0)


def _load_img(filename: str, colorspace: str = "sRGB") -> bpy.types.Image:
    path = os.path.join(TEX_SRC, filename)
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = colorspace
    return img


def _new_mat(name: str):
    return mats._new_node_material(name)


def _stucco_mat(
    name: str,
    col_a: str,
    col_b: str,
    *,
    rough: float = 0.72,
    bump_scale: float = 28.0,
    bump_str: float = 0.14,
    bump_dist: float = 0.004,
    spec_ior: float = 0.28,
) -> bpy.types.Material:
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")

    n_macro = nt.nodes.new("ShaderNodeTexNoise")
    n_macro.inputs["Scale"].default_value = 0.45
    n_macro.inputs["Detail"].default_value = 5.0
    n_macro.inputs["Roughness"].default_value = 0.62
    nt.links.new(tc.outputs["Object"], n_macro.inputs["Vector"])

    n_fine = nt.nodes.new("ShaderNodeTexNoise")
    n_fine.inputs["Scale"].default_value = bump_scale
    n_fine.inputs["Detail"].default_value = 8.0
    n_fine.inputs["Roughness"].default_value = 0.68
    nt.links.new(tc.outputs["Object"], n_fine.inputs["Vector"])

    col = bake.mix_rgba(nt, n_macro.outputs["Fac"], _hex_lin(col_a), _hex_lin(col_b))
    nt.links.new(col, bsdf.inputs["Base Color"])
    mats.set_in(bsdf, ("Specular IOR Level", "Specular"), spec_ior)

    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = max(0.15, rough - 0.10)
    mr.inputs["To Max"].default_value = min(0.96, rough + 0.10)
    nt.links.new(n_macro.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_str
    bump.inputs["Distance"].default_value = bump_dist
    nt.links.new(n_fine.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mat["sc_srgb"] = list(mats.parse_color(col_a))
    mat["sc_roughness"] = rough
    mat["sc_metallic"] = 0.0
    mat["sc_role"] = "solid"
    return mat


def _paver_concrete_mat(
    name: str,
    col_light: str,
    col_dark: str,
    col_joint: str,
    *,
    grid_x: float = 1.25,
    grid_y: float = 1.25,
    rough: float = 0.78,
) -> bpy.types.Material:
    """Scored Miami Beach concrete sidewalk with expansion joints + subtle tropical grit."""
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")

    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Scale"].default_value = 1.0 / max(grid_x, 0.2)
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = grid_y / max(grid_x, 0.2)
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Mortar Smooth"].default_value = 0.25
    brick.inputs["Color1"].default_value = _hex_lin(col_light)
    brick.inputs["Color2"].default_value = _hex_lin(col_dark)
    brick.inputs["Mortar"].default_value = _hex_lin(col_joint)
    nt.links.new(tc.outputs["Object"], brick.inputs["Vector"])

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 48.0
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Roughness"].default_value = 0.65
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

    # Macro coastal concrete mottling & per-slab subtle weathering variation
    stain = nt.nodes.new("ShaderNodeTexNoise")
    stain.inputs["Scale"].default_value = 0.55
    stain.inputs["Detail"].default_value = 5.0
    stain.inputs["Roughness"].default_value = 0.58
    nt.links.new(tc.outputs["Object"], stain.inputs["Vector"])

    grit = nt.nodes.new("ShaderNodeTexNoise")
    grit.inputs["Scale"].default_value = 115.0
    grit.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], grit.inputs["Vector"])

    col_weath = bake.mix_rgba(nt, stain.outputs["Fac"], brick.outputs["Color"], _hex_lin(col_dark))
    # Subtle fine aggregate speckle over weathered slabs
    col_speck = bake.mix_rgba(nt, grit.outputs["Fac"], col_weath, _hex_lin(col_light))
    col_mix = bake.mix_rgba(nt, 0.22, col_weath, col_speck)
    # Keep expansion joints crisp by mixing mortar back in using brick Fac
    col_final = bake.mix_rgba(nt, brick.outputs["Fac"], col_mix, _hex_lin(col_joint))
    nt.links.new(col_final, bsdf.inputs["Base Color"])

    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = rough - 0.12
    mr.inputs["To Max"].default_value = min(0.96, rough + 0.14)
    nt.links.new(noise.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])

    # Combine crisp expansion-joint grooves + sandy coastal concrete grain into Bump
    math_b = nt.nodes.new("ShaderNodeMath")
    math_b.operation = "MULTIPLY_ADD"
    nt.links.new(brick.outputs["Fac"], math_b.inputs[0])
    math_b.inputs[1].default_value = -1.15
    nt.links.new(noise.outputs["Fac"], math_b.inputs[2])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.34
    bump.inputs["Distance"].default_value = 0.008
    nt.links.new(math_b.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mat["sc_srgb"] = list(mats.parse_color(col_light))
    mat["sc_roughness"] = rough
    mat["sc_metallic"] = 0.0
    mat["sc_role"] = "solid"
    return mat


def _image_mat(
    name: str,
    filename: str,
    *,
    rough: float = 0.55,
    metallic: float = 0.0,
    bump_scale: float = 40.0,
    bump_str: float = 0.06,
    emission_strength: float = 0.0,
    spec_ior: float = 0.35,
) -> bpy.types.Material:
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    uv_node = nt.nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = "GraphicUV"
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = _load_img(filename, "sRGB")
    tex.extension = "CLIP" if "sign_" in filename or "menu_" in filename or "podium" in filename else "REPEAT"
    nt.links.new(uv_node.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    mats.set_in(bsdf, ("Specular IOR Level", "Specular"), spec_ior)
    if emission_strength > 0.0:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if bump_str > 0.0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = bump_scale
        n.inputs["Detail"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        b = nt.nodes.new("ShaderNodeBump")
        b.inputs["Strength"].default_value = bump_str
        b.inputs["Distance"].default_value = 0.002
        nt.links.new(n.outputs["Fac"], b.inputs["Height"])
        nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])

    mat["sc_srgb"] = [0.5, 0.5, 0.5]
    mat["sc_roughness"] = rough
    mat["sc_metallic"] = metallic
    mat["sc_role"] = "solid"
    return mat


def _foliage_mat(
    name: str,
    col_a: str,
    col_b: str,
    *,
    rough: float = 0.44,
    subsurf: float = 0.15,
    scale: float = 12.0,
    bump_str: float = 0.22,
) -> bpy.types.Material:
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "F1"
    vor.distance = "EUCLIDEAN"
    vor.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])

    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale * 0.45
    n.inputs["Detail"].default_value = 5.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])

    col = bake.mix_rgba(nt, n.outputs["Fac"], _hex_lin(col_a), _hex_lin(col_b))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    mats.set_in(bsdf, ("Subsurface Weight", "Subsurface"), subsurf)
    mats.set_in(bsdf, ("Coat Weight", "Clearcoat"), 0.26)
    mats.set_in(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.22)

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_str
    bump.inputs["Distance"].default_value = 0.008
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mat["sc_srgb"] = list(mats.parse_color(col_a))
    mat["sc_roughness"] = rough
    mat["sc_metallic"] = 0.0
    mat["sc_role"] = "solid"
    return mat


def _palm_bark_mat(name: str) -> bpy.types.Material:
    """Crisp terraced sun-weathered Miami Beach coconut palm bark w/ sawtooth leaf scars & vertical fibrous cracks!"""
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")

    # Sharp terraced horizontal leaf-scar rings (SAW profile -> crisp shadowed ledges, NOT blurry zebra stripes!)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.wave_profile = "SAW"
    wave.inputs["Scale"].default_value = 5.4
    wave.inputs["Distortion"].default_value = 2.8
    wave.inputs["Detail"].default_value = 6.0
    wave.inputs["Detail Scale"].default_value = 2.2
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])

    # Fine vertical fibrous bark cracks stretched vertically along Z
    mp_f = nt.nodes.new("ShaderNodeMapping")
    mp_f.inputs["Scale"].default_value = (14.0, 14.0, 2.2)
    nt.links.new(tc.outputs["Object"], mp_f.inputs["Vector"])
    fibers = nt.nodes.new("ShaderNodeTexNoise")
    fibers.inputs["Scale"].default_value = 4.5
    fibers.inputs["Detail"].default_value = 10.0
    fibers.inputs["Roughness"].default_value = 0.72
    nt.links.new(mp_f.outputs["Vector"], fibers.inputs["Vector"])

    # Subtle coastal grey-tan lichen weathering blotches
    lichen = nt.nodes.new("ShaderNodeTexNoise")
    lichen.inputs["Scale"].default_value = 2.2
    lichen.inputs["Detail"].default_value = 5.0
    nt.links.new(tc.outputs["Object"], lichen.inputs["Vector"])

    # Sharpen ring dark crevice band
    mr_ring = nt.nodes.new("ShaderNodeMapRange")
    mr_ring.clamp = True
    mr_ring.inputs["From Min"].default_value = 0.15
    mr_ring.inputs["From Max"].default_value = 0.75
    nt.links.new(wave.outputs["Fac"], mr_ring.inputs["Value"])

    col = bake.mix_rgba(nt, mr_ring.outputs["Result"], _hex_lin("#5B5248"), _hex_lin("#9A9083"))
    col2 = bake.mix_rgba(nt, fibers.outputs["Fac"], col, _hex_lin("#463E36"))
    col3 = bake.mix_rgba(nt, lichen.outputs["Fac"], col2, _hex_lin("#ABA398"))
    col_fin = bake.mix_rgba(nt, 0.32, col2, col3)
    nt.links.new(col_fin, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.90
    mats.set_in(bsdf, ("Specular IOR Level", "Specular"), 0.16)

    # Combine horizontal leaf-scar terraces + vertical fiber cracks into strong physical bump
    h_mix = nt.nodes.new("ShaderNodeMath")
    h_mix.operation = "MULTIPLY_ADD"
    nt.links.new(mr_ring.outputs["Result"], h_mix.inputs[0])
    h_mix.inputs[1].default_value = 0.65
    nt.links.new(fibers.outputs["Fac"], h_mix.inputs[2])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.68
    bump.inputs["Distance"].default_value = 0.020
    nt.links.new(h_mix.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mat["sc_srgb"] = list(mats.parse_color("#7E756B"))
    mat["sc_roughness"] = 0.90
    mat["sc_metallic"] = 0.0
    mat["sc_role"] = "solid"
    return mat


def _tree_bark_mat(name: str) -> bpy.types.Material:
    """Deeply fissured tropical Buttonwood / Sea Grape hardwood bark w/ vertical cracks, bark plates & coastal lichen!"""
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")

    # Gently stretched organic bark fissures (natural on BOTH vertical trunks and angled spreading boughs!)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (5.8, 5.8, 2.2)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 3.0
    nt.links.new(mp.outputs["Vector"], vor.inputs["Vector"])

    n_cr = nt.nodes.new("ShaderNodeTexNoise")
    n_cr.inputs["Scale"].default_value = 5.5
    n_cr.inputs["Detail"].default_value = 10.0
    n_cr.inputs["Roughness"].default_value = 0.72
    nt.links.new(mp.outputs["Vector"], n_cr.inputs["Vector"])

    lichen = nt.nodes.new("ShaderNodeTexNoise")
    lichen.inputs["Scale"].default_value = 3.5
    lichen.inputs["Detail"].default_value = 5.0
    nt.links.new(tc.outputs["Object"], lichen.inputs["Vector"])

    mr_cr = nt.nodes.new("ShaderNodeMapRange")
    mr_cr.clamp = True
    mr_cr.inputs["From Min"].default_value = 0.02
    mr_cr.inputs["From Max"].default_value = 0.28
    nt.links.new(vor.outputs["Distance"], mr_cr.inputs["Value"])

    col_base = bake.mix_rgba(nt, mr_cr.outputs["Result"], _hex_lin("#2D2721"), _hex_lin("#6A6055"))
    col_var = bake.mix_rgba(nt, n_cr.outputs["Fac"], col_base, _hex_lin("#4F473E"))
    col_lich = bake.mix_rgba(nt, lichen.outputs["Fac"], col_var, _hex_lin("#857E72"))
    col_fin = bake.mix_rgba(nt, 0.35, col_var, col_lich)
    nt.links.new(col_fin, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    mats.set_in(bsdf, ("Specular IOR Level", "Specular"), 0.14)

    h_bark = nt.nodes.new("ShaderNodeMath")
    h_bark.operation = "MULTIPLY_ADD"
    nt.links.new(mr_cr.outputs["Result"], h_bark.inputs[0])
    h_bark.inputs[1].default_value = 0.75
    nt.links.new(n_cr.outputs["Fac"], h_bark.inputs[2])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.80
    bump.inputs["Distance"].default_value = 0.026
    nt.links.new(h_bark.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mat["sc_srgb"] = list(mats.parse_color("#595046"))
    mat["sc_roughness"] = 0.92
    mat["sc_metallic"] = 0.0
    mat["sc_role"] = "solid"
    return mat


def _rattan_weave_mat(name: str, hex_a: str, hex_b: str, rough: float = 0.56) -> bpy.types.Material:
    """Authentic millimeter-scale 3D tri-planar French Parisian woven cane/rattan basketweave (crisp on seats AND vertical backs!)."""
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")

    # 3D diagonal woven reed coordinates -> works cleanly on horizontal seats AND curved vertical chair backs!
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0.62, 0.45, 0.785)
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    wx = nt.nodes.new("ShaderNodeTexWave")
    wx.wave_type = "BANDS"
    wx.bands_direction = "DIAGONAL"
    wx.wave_profile = "SIN"
    wx.inputs["Scale"].default_value = 115.0
    wx.inputs["Distortion"].default_value = 0.25
    nt.links.new(mp.outputs["Vector"], wx.inputs["Vector"])

    mp2 = nt.nodes.new("ShaderNodeMapping")
    mp2.inputs["Rotation"].default_value = (-0.62, 0.45, -0.785)
    nt.links.new(tc.outputs["Object"], mp2.inputs["Vector"])

    wy = nt.nodes.new("ShaderNodeTexWave")
    wy.wave_type = "BANDS"
    wy.bands_direction = "DIAGONAL"
    wy.wave_profile = "SIN"
    wy.inputs["Scale"].default_value = 115.0
    wy.inputs["Distortion"].default_value = 0.25
    nt.links.new(mp2.outputs["Vector"], wy.inputs["Vector"])

    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 135.0
    nt.links.new(tc.outputs["Object"], chk.inputs["Vector"])

    weave_mix = nt.nodes.new("ShaderNodeMix")
    weave_mix.data_type = "FLOAT"
    nt.links.new(chk.outputs["Fac"], weave_mix.inputs["Factor"])
    nt.links.new(wx.outputs["Fac"], weave_mix.inputs[2])
    nt.links.new(wy.outputs["Fac"], weave_mix.inputs[3])

    col = bake.mix_rgba(nt, weave_mix.outputs[0], _hex_lin(hex_a), _hex_lin(hex_b))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.24

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.38
    bump.inputs["Distance"].default_value = 0.003
    nt.links.new(weave_mix.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    mat["sc_srgb"] = list(mats.parse_color(hex_a))
    mat["sc_roughness"] = rough
    mat["sc_metallic"] = 0.0
    mat["sc_role"] = "solid"
    return mat


def _terracotta_tile_mat(name: str) -> bpy.types.Material:
    """Spanish barrel terracotta clay tiles for 804 Ocean Dr entrance roof canopy (Photo 3)."""
    mat, bsdf = _new_mat(name)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 5.5
    n.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    col = bake.mix_rgba(nt, n.outputs["Fac"], _hex_lin("#BD6540"), _hex_lin("#8F4224"))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.68
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.005
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mat["sc_srgb"] = list(mats.parse_color("#B05A37"))
    mat["sc_roughness"] = 0.68
    mat["sc_metallic"] = 0.0
    mat["sc_role"] = "solid"
    return mat


def build_material_library(palette_override: dict | None = None) -> dict[str, bpy.types.Material]:
    """Create the complete News Cafe South Beach architectural, signage, streetscape & botanical material dict."""
    ov = palette_override or {}
    m: dict[str, bpy.types.Material] = {}

    # 1. News Cafe (800 Ocean Dr) Stucco, Eyebrows & Breeze Blocks
    m["stucco_cream"] = _stucco_mat(
        "NC_Stucco_Cream",
        ov.get("stucco_cream_a", "#EAE5D3"),
        ov.get("stucco_cream_b", "#DDD7C3"),
        rough=0.70,
        bump_scale=32.0,
        bump_str=0.12,
    )
    m["stucco_white"] = _stucco_mat(
        "NC_Stucco_White",
        ov.get("stucco_white_a", "#F7F6F1"),
        ov.get("stucco_white_b", "#EBE9E0"),
        rough=0.62,
        bump_scale=34.0,
        bump_str=0.10,
    )
    m["breeze_block"] = _stucco_mat(
        "NC_BreezeBlock_White",
        ov.get("breeze_a", "#F4F3EE"),
        ov.get("breeze_b", "#E4E2DA"),
        rough=0.68,
        bump_scale=44.0,
        bump_str=0.18,
    )
    m["roof_membrane"] = _stucco_mat("NC_Roof_Membrane", "#D5D2C8", "#B9B6AC", rough=0.86, bump_scale=18.0, bump_str=0.16)

    # 2. Windows, Jalousie Louvers & Interior Glazing
    m["window_glass"] = mats.pbr(
        "NC_Window_Glass",
        color=ov.get("glass_col", "#0E1C24"),
        roughness=0.05,
        metallic=0.22,
        coat=1.0,
        coat_roughness=0.02,
        specular=0.95,
    )
    m["window_jalousie_dark"] = mats.pbr(
        "NC_Window_Jalousie",
        color="#13222A",
        roughness=0.03,
        metallic=0.20,
        coat=1.0,
        coat_roughness=0.01,
    )
    m["cafe_glass"] = mats.pbr(
        "NC_Cafe_Glass",
        color="#121D22",
        roughness=0.05,
        metallic=0.10,
        coat=0.85,
        transmission=0.68,
        alpha=0.38,
        ior=1.50,
    )
    m["aluminum_frame"] = mats.pbr("NC_Aluminum_Frame", color="#CFD5D3", roughness=0.28, metallic=0.78)
    m["cafe_mullion"] = mats.pbr("NC_Cafe_Mullion", color="#E6E1D3", roughness=0.36, metallic=0.15)
    m["shutter_white"] = _stucco_mat("NC_Hotel_Shutter", "#EAECEB", "#CFD3D2", rough=0.44, bump_scale=60.0, bump_str=0.16)
    m["column_green"] = mats.pbr("NC_Column_Green", color=ov.get("column_green", "#0D3D2B"), roughness=0.38, metallic=0.25)

    # 3. Awnings & Umbrellas (low-specular velvety cloth -> deep saturated Miami forest-emerald without sky washout!)
    m["awning_news_cafe"] = _image_mat("NC_Awning_NewsCafe", "awning_news_cafe.png", rough=0.88, bump_scale=85.0, bump_str=0.08, spec_ior=0.06)
    if "awning_tint" in ov:
        # Variant livery recolor: preserve crisp white "News Cafe" script & white trim while shifting canvas hue!
        nt_a = m["awning_news_cafe"].node_tree
        tex_a = next(n for n in nt_a.nodes if n.type == "TEX_IMAGE")
        bsdf_a = next(n for n in nt_a.nodes if n.type == "BSDF_PRINCIPLED")
        sep_a = nt_a.nodes.new("ShaderNodeSeparateColor")
        nt_a.links.new(tex_a.outputs["Color"], sep_a.inputs["Color"])
        mr_a = nt_a.nodes.new("ShaderNodeMapRange")
        mr_a.clamp = True
        mr_a.inputs["From Min"].default_value = 0.08
        mr_a.inputs["From Max"].default_value = 0.45
        nt_a.links.new(sep_a.outputs["Red"], mr_a.inputs["Value"])
        recol = bake.mix_rgba(nt_a, mr_a.outputs["Result"], _hex_lin(ov["awning_tint"]), (0.96, 0.97, 0.95, 1.0))
        nt_a.links.new(recol, bsdf_a.inputs["Base Color"])
    m["awning_green_plain"] = _stucco_mat(
        "NC_Awning_Green_Plain",
        ov.get("awning_green_a", "#022A1A"),
        ov.get("awning_green_b", "#011C11"),
        rough=0.88,
        bump_scale=90.0,
        bump_str=0.10,
        spec_ior=0.06,
    )
    m["awning_hotel_800"] = _image_mat("NC_Awning_Hotel800", "awning_hotel_800.png", rough=0.84, bump_scale=85.0, bump_str=0.08, spec_ior=0.08)
    m["umbrella_green"] = _stucco_mat(
        "NC_Umbrella_Green",
        ov.get("umbrella_green_a", "#033623"),
        ov.get("umbrella_green_b", "#022417"),
        rough=0.86,
        bump_scale=75.0,
        bump_str=0.08,
        spec_ior=0.06,
    )
    m["umbrella_sage"] = _stucco_mat("NC_Umbrella_Sage", "#768D7F", "#60776A", rough=0.84, bump_scale=75.0, bump_str=0.08, spec_ior=0.08)

    # 4. News Cafe Ground Interior (3D Gallery Art, Sculpted Oxblood Leather Banquettes, Mahogany Millwork & Back-Bar Mirror)
    m["interior_wall"] = _image_mat("NC_Interior_Backdrop", "interior_news_cafe.png", rough=0.65, bump_str=0.04, emission_strength=0.22, spec_ior=0.18)
    m["gallery_art"] = _image_mat("NC_Gallery_Art", "gallery_art_atlas.png", rough=0.38, bump_str=0.03, emission_strength=0.0, spec_ior=0.22)
    m["museum_mat"] = _stucco_mat("NC_Museum_Mat", "#F2EEE4", "#E6E0D2", rough=0.78, bump_scale=95.0, bump_str=0.04, spec_ior=0.12)
    m["plaster_interior"] = _stucco_mat("NC_Plaster_Interior", "#DDD2BD", "#CEC1A8", rough=0.66, bump_scale=24.0, bump_str=0.09, spec_ior=0.18)
    m["antique_mirror"] = mats.pbr("NC_Antique_Mirror", color="#9C8F7C", roughness=0.06, metallic=0.92, coat=1.0)
    m["interior_floor"] = _paver_concrete_mat("NC_Interior_Terrazzo", "#D9D2C2", "#C7BEAC", "#8F8574", grid_x=0.6, grid_y=0.6, rough=0.28)
    m["mahogany_wood"] = _stucco_mat("NC_Mahogany_Wood", "#3A1C10", "#241008", rough=0.32, bump_scale=44.0, bump_str=0.08, spec_ior=0.24)
    m["banquette_red"] = _stucco_mat("NC_Banquette_Red", "#631219", "#420B10", rough=0.34, bump_scale=95.0, bump_str=0.12, spec_ior=0.28)
    m["bottle_amber"] = mats.pbr("NC_Bottle_Amber", color="#8A440E", roughness=0.08, metallic=0.10, coat=1.0)
    m["bottle_emerald"] = mats.pbr("NC_Bottle_Emerald", color="#0B4A24", roughness=0.08, metallic=0.10, coat=1.0)
    m["crystal_glass"] = mats.pbr(
        "NC_Crystal_Glass",
        color="#F0F6FA",
        roughness=0.025,
        metallic=0.04,
        coat=1.0,
        coat_roughness=0.01,
        transmission=0.90,
        ior=1.52,
        specular=0.98,
    )
    m["linen_napkin"] = _stucco_mat("NC_Linen_Napkin", "#EFECE4", "#DFDBD0", rough=0.84, bump_scale=110.0, bump_str=0.12, spec_ior=0.08)
    m["brass_warm"] = mats.pbr("NC_Brass_Warm", color="#D4A64A", roughness=0.22, metallic=0.94)
    m["warm_lamp"] = mats.pbr("NC_Warm_Lamp", color="#FFF1D0", roughness=0.12, emission="#FFCC78", emission_strength=8.5)
    m["candle_flame"] = mats.pbr("NC_Candle_Flame", color="#FFE6A3", roughness=0.05, emission="#FFBB44", emission_strength=14.0)

    # 5. Patio Bistro Furniture & Props
    m["marble_top"] = _stucco_mat("NC_Marble_Top", "#F2F0EC", "#D4D2CE", rough=0.16, bump_scale=6.0, bump_str=0.03)
    m["cast_iron"] = mats.pbr("NC_Cast_Iron", color="#22252A", roughness=0.38, metallic=0.78)
    m["rattan_weave"] = _rattan_weave_mat("NC_Rattan_Weave", "#9E764B", "#624326", rough=0.58)
    m["rattan_cream"] = _rattan_weave_mat("NC_Rattan_Cream", "#E4DCCD", "#B8AC96", rough=0.54)
    m["chair_frame"] = mats.pbr("NC_Chair_Frame", color="#4D3624", roughness=0.40, metallic=0.08)
    m["stainless_steel"] = mats.pbr("NC_Stainless_Steel", color="#C6CBD0", roughness=0.24, metallic=0.90)
    m["galvanized_steel"] = mats.pbr("NC_Galvanized_Steel", color="#A8AEB4", roughness=0.36, metallic=0.82)
    m["host_podium_front"] = _image_mat("NC_HostPodium_Front", "host_podium_front.png", rough=0.58, bump_str=0.06)
    m["host_podium_body"] = _stucco_mat("NC_HostPodium_Body", "#3D4148", "#2E3136", rough=0.56, bump_scale=35.0, bump_str=0.10)
    m["menu_board"] = _image_mat("NC_MenuBoard_Sheet", "menu_board_sheet.png", rough=0.28, bump_str=0.02, emission_strength=0.18)
    m["ceramic_white"] = mats.pbr("NC_Ceramic_White", color="#F5F5F2", roughness=0.14, coat=0.6)
    m["terracotta_pot"] = _terracotta_tile_mat("NC_Terracotta_Pot")
    m["glazed_green_pot"] = mats.pbr("NC_Glazed_Green_Pot", color="#4C8638", roughness=0.22, coat=0.7)
    m["cedar_planter"] = _stucco_mat("NC_Cedar_Planter", "#A67C52", "#805C3A", rough=0.74, bump_scale=30.0, bump_str=0.20)

    # 6. Adjacent Buildings: 804 Ocean Dr (Olive-Green & Tan) & 820 Ocean Dr (White & Royal Blue)
    m["olive_804"] = _stucco_mat("NC_804_Olive", "#73864E", "#5F703E", rough=0.72, bump_scale=30.0, bump_str=0.14)
    m["tan_804"] = _stucco_mat("NC_804_Tan", "#C79C73", "#B2865E", rough=0.70, bump_scale=30.0, bump_str=0.14)
    m["spanish_tile"] = _terracotta_tile_mat("NC_Spanish_Tile")
    m["sign_804"] = _image_mat("NC_Sign_804", "sign_804_menu.png", rough=0.45, bump_str=0.03)
    m["blue_820"] = mats.pbr("NC_820_RoyalBlue", color="#1A65C2", roughness=0.38, metallic=0.08)
    m["blue_awning_820"] = _stucco_mat("NC_820_BlueAwning", "#1758B0", "#104590", rough=0.76, bump_scale=80.0, bump_str=0.10)

    # 7. Roads, Sidewalks, Curbs, Bike Lanes & Street Furniture
    m["asphalt_ocean"] = _image_mat("NC_Road_OceanDr", "road_ocean_dr.png", rough=0.86, bump_scale=65.0, bump_str=0.18)
    m["asphalt_plain"] = _image_mat("NC_Road_Asphalt", "road_asphalt_plain.png", rough=0.86, bump_scale=65.0, bump_str=0.18)
    m["road_paint_white"] = _stucco_mat("NC_Road_PaintWhite", "#EAECE8", "#D6D9D4", rough=0.72, bump_scale=45.0, bump_str=0.10)
    m["bike_lane"] = _image_mat("NC_Road_BikeLane", "road_bike_lane.png", rough=0.80, bump_scale=55.0, bump_str=0.14)
    m["sidewalk_concrete"] = _paver_concrete_mat("NC_Sidewalk_Concrete", "#D7D4CB", "#C6C2B8", "#8A877F", grid_x=1.45, grid_y=1.45, rough=0.78)
    m["sidewalk_pink"] = _paver_concrete_mat("NC_Sidewalk_Pink", "#CE928B", "#BD7E77", "#8B5E58", grid_x=1.35, grid_y=1.35, rough=0.80)
    m["ada_pad"] = _stucco_mat("NC_ADA_Tactile", "#D4B67B", "#BE9F65", rough=0.76, bump_scale=110.0, bump_str=0.38)
    m["curb_yellow"] = _stucco_mat("NC_Curb_Yellow", "#DFAC22", "#C49118", rough=0.74, bump_scale=36.0, bump_str=0.16)
    m["curb_valet"] = _image_mat("NC_Curb_Valet", "curb_valet_only.png", rough=0.76, bump_scale=36.0, bump_str=0.14)
    m["curb_concrete"] = _stucco_mat("NC_Curb_Concrete", "#CCC9C0", "#B5B1A7", rough=0.80, bump_scale=36.0, bump_str=0.16)
    m["plinth_slate"] = mats.pbr("NC_Plinth_Slate", color="#2B3038", roughness=0.78, metallic=0.05)
    m["trash_bin_green"] = _stucco_mat("NC_TrashBin_Green", "#1D6B3C", "#165730", rough=0.46, bump_scale=95.0, bump_str=0.06, spec_ior=0.38)
    m["hydrant_yellow"] = _stucco_mat("NC_Hydrant_Yellow", "#E8BA1E", "#CDA114", rough=0.34, bump_scale=75.0, bump_str=0.09, spec_ior=0.45)
    m["bollard_orange"] = mats.pbr("NC_Bollard_Orange", color="#E25A26", roughness=0.42, metallic=0.05)
    m["zebra_rubber"] = mats.pbr("NC_Zebra_Rubber", color="#24272B", roughness=0.72, metallic=0.05)
    m["zebra_white"] = mats.pbr("NC_Zebra_White", color="#EAECE9", roughness=0.45, metallic=0.05)
    m["iron_grate"] = mats.pbr("NC_Iron_Grate", color="#3A3C3F", roughness=0.58, metallic=0.75)

    # 8. Street & Building Signage
    m["sign_one_way"] = _image_mat("NC_Sign_OneWay", "sign_one_way.png", rough=0.30, metallic=0.20, bump_str=0.0)
    m["sign_stop_ped"] = _image_mat("NC_Sign_StopPed", "sign_stop_ped.png", rough=0.30, metallic=0.20, bump_str=0.0)
    m["sign_no_parking"] = _image_mat("NC_Sign_NoParking", "sign_no_parking.png", rough=0.30, metallic=0.20, bump_str=0.0)
    m["sign_ocean_dr"] = _image_mat("NC_Sign_OceanDr", "sign_street_ocean.png", rough=0.30, metallic=0.20, bump_str=0.0)
    m["sign_8th_st"] = _image_mat("NC_Sign_8thSt", "sign_street_8th.png", rough=0.30, metallic=0.20, bump_str=0.0)
    m["sign_ada"] = _image_mat("NC_Sign_ADA", "sign_ada_blue.png", rough=0.32, metallic=0.15, bump_str=0.0)
    m["sign_fdc"] = _image_mat("NC_Sign_FDC", "sign_fdc_red.png", rough=0.32, metallic=0.15, bump_str=0.0)

    # 9. Tropical Botanicals (Multi-tone Palms, Deep Rich Buttonwood Leaves, Lush Hedges, Magenta Bougainvillea)
    m["palm_bark"] = _palm_bark_mat("NC_Palm_Bark")
    m["tree_bark"] = _tree_bark_mat("NC_Tree_Bark")
    m["palm_frond"] = _foliage_mat("NC_Palm_Frond", "#35601B", "#5B8328", rough=0.42, subsurf=0.22, scale=18.0, bump_str=0.14)
    m["palm_frond_sun"] = _foliage_mat("NC_Palm_Frond_Sun", "#4D7922", "#759D32", rough=0.38, subsurf=0.26, scale=18.0, bump_str=0.14)
    m["coconut_green"] = _stucco_mat("NC_Coconut_Green", "#5A8028", "#43631C", rough=0.36, bump_scale=28.0, bump_str=0.10)
    m["hedge_dark"] = _foliage_mat("NC_Hedge_Dark", "#123C14", "#22581C", rough=0.48, subsurf=0.10, scale=26.0, bump_str=0.28)
    m["hedge_mid"] = _foliage_mat("NC_Hedge_Mid", "#1F541B", "#377424", rough=0.44, subsurf=0.14, scale=24.0, bump_str=0.26)
    m["boxwood_balcony"] = _foliage_mat("NC_Boxwood_Balcony", "#0E2E14", "#1B4820", rough=0.52, subsurf=0.06, scale=32.0, bump_str=0.34)
    m["tree_canopy"] = _foliage_mat("NC_Tree_Canopy", "#1F4F14", "#3B7220", rough=0.44, subsurf=0.16, scale=18.0, bump_str=0.24)
    m["tree_canopy_lit"] = _foliage_mat("NC_Tree_Canopy_Lit", "#366D1B", "#5C912B", rough=0.40, subsurf=0.20, scale=18.0, bump_str=0.22)
    m["lime_shrub"] = _foliage_mat("NC_Lime_Shrub", "#548C1E", "#77AE2F", rough=0.42, subsurf=0.18, scale=22.0, bump_str=0.24)
    m["soil_mulch"] = _stucco_mat("NC_Soil_Mulch", "#3E2E23", "#261C15", rough=0.92, bump_scale=42.0, bump_str=0.34)
    m["park_grass"] = _foliage_mat("NC_Park_Grass", "#4B782E", "#69943E", rough=0.78, subsurf=0.05, scale=28.0, bump_str=0.22)
    m["bougainvillea_pink"] = _foliage_mat("NC_Bougainvillea_Pink", "#C40D5E", "#E62E7D", rough=0.46, subsurf=0.28, scale=28.0, bump_str=0.18)
    m["bougainvillea_deep"] = _foliage_mat("NC_Bougainvillea_Deep", "#880842", "#B8145C", rough=0.50, subsurf=0.20, scale=28.0, bump_str=0.18)
    m["bougainvillea_floret"] = _stucco_mat("NC_Bougainvillea_Floret", "#F9F4DF", "#E8DFC0", rough=0.55, bump_scale=40.0, bump_str=0.08, spec_ior=0.12)
    m["palm_crown_fiber"] = _stucco_mat("NC_Palm_CrownFiber", "#5A4430", "#3D2D1E", rough=0.92, bump_scale=60.0, bump_str=0.38, spec_ior=0.12)

    return m
