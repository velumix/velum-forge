r"""Photorealistic South Beach Sunlit Street-View Angle Renderer & Side-by-Side Comparison Composer.

Renders 7 Cycles GPU (OPTIX, power-safe via `vflib.bake`) cameras matching EVERY ONE of the 5
uploaded Google Street View photos + an Aerial Hero 3/4 + a Macro Patio/Breeze-Block Close-up,
then composes `renders/streetview_comparison.png` pairing real Google Street View photos next to
our 3D renders for strict honest visual critique!
"""
from __future__ import annotations

import math
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
RENDERS_DIR = os.path.join(THIS_DIR, "renders")

if "--compose-only" not in sys.argv:
    import bpy
    from mathutils import Vector

    ENGINE_BLENDER = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "engine", "blender"))
    for _p in (THIS_DIR, ENGINE_BLENDER):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    from vflib import bake, core, mats  # noqa: E402
    import build_news_cafe_south_beach as builder  # noqa: E402


def setup_miami_sun_sky(sc: bpy.types.Scene) -> bpy.types.Collection:
    """Create bright realistic Miami Beach midday tropical sky (Nishita sun + azure sky) matching Street View lighting!"""
    st_col = core.fresh_collection("VF_MiamiSun_Studio")
    world = bpy.data.worlds.get("VF_MiamiSky") or bpy.data.worlds.new("VF_MiamiSky")
    try:
        world.use_nodes = True
    except (AttributeError, TypeError):
        pass
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "NISHITA"
        sky.sun_disc = True
        sky.sun_size = math.radians(1.2)
        sky.sun_intensity = 0.85
        sky.sun_elevation = math.radians(56.0)
        # Sun coming from South-East (+X, +Y) illuminating East Ocean Dr & South 8th St facades crisply!
        sky.sun_rotation = math.radians(132.0)
        sky.air_density = 1.05
        if hasattr(sky, "aerosol_density"):
            sky.aerosol_density = 0.75
        elif hasattr(sky, "dust_density"):
            sky.dust_density = 0.75
        sky.ozone_density = 1.6
    except Exception:
        pass
    bg.inputs["Strength"].default_value = 0.34

    # Soft coastal Miami horizon mist below Z=0 so diorama Street View shots have bright atmospheric haze (not black void!)
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geom.outputs["Incoming"], sep.inputs["Vector"])
    # Incoming points FROM camera TO sky, so Z < 0 is sky above horizon? Wait: Incoming points toward camera (down = +Z)!
    # MapRange Z from -0.02..+0.08 -> 0..1 (lower hemisphere blends smoothly into warm sunlit pale coastal haze!)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.inputs["From Min"].default_value = -0.02
    mr.inputs["From Max"].default_value = 0.05
    mr.inputs["To Min"].default_value = 0.0
    mr.inputs["To Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])

    sky_col = bake.mix_rgba(nt, mr.outputs["Result"], sky.outputs["Color"], (0.78, 0.86, 0.94, 1.0))

    # Realistic soft Miami Beach coastal cumulus clouds in the upper azure sky dome!
    tc_w = nt.nodes.new("ShaderNodeTexCoord")
    sep_gen = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc_w.outputs["Generated"], sep_gen.inputs["Vector"])
    mp_c = nt.nodes.new("ShaderNodeMapping")
    mp_c.inputs["Scale"].default_value = (1.5, 1.5, 4.8)
    nt.links.new(tc_w.outputs["Generated"], mp_c.inputs["Vector"])
    cld_n = nt.nodes.new("ShaderNodeTexNoise")
    cld_n.inputs["Scale"].default_value = 3.2
    cld_n.inputs["Detail"].default_value = 8.0
    cld_n.inputs["Roughness"].default_value = 0.62
    nt.links.new(mp_c.outputs["Vector"], cld_n.inputs["Vector"])
    mr_c = nt.nodes.new("ShaderNodeMapRange")
    mr_c.clamp = True
    mr_c.inputs["From Min"].default_value = 0.50
    mr_c.inputs["From Max"].default_value = 0.72
    mr_c.inputs["To Min"].default_value = 0.0
    mr_c.inputs["To Max"].default_value = 0.85
    nt.links.new(cld_n.outputs["Fac"], mr_c.inputs["Value"])
    # Fade clouds smoothly above horizon (Generated Z > 0 = upper sky hemisphere!)
    mr_elev = nt.nodes.new("ShaderNodeMapRange")
    mr_elev.clamp = True
    mr_elev.inputs["From Min"].default_value = 0.05
    mr_elev.inputs["From Max"].default_value = 0.28
    mr_elev.inputs["To Min"].default_value = 0.0
    mr_elev.inputs["To Max"].default_value = 1.0
    nt.links.new(sep_gen.outputs["Z"], mr_elev.inputs["Value"])
    cld_mask = nt.nodes.new("ShaderNodeMath")
    cld_mask.operation = "MULTIPLY"
    nt.links.new(mr_c.outputs["Result"], cld_mask.inputs[0])
    nt.links.new(mr_elev.outputs["Result"], cld_mask.inputs[1])

    sky_with_clouds = bake.mix_rgba(nt, cld_mask.outputs[0], sky_col, (1.65, 1.68, 1.74, 1.0))
    nt.links.new(sky_with_clouds, bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    sc.world = world

    # Crisp subtle warm bounce fill light from bright sand/concrete street so under-awning patio reads clearly!
    ld = bpy.data.lights.new("VF_MiamiSunFill", "SUN")
    ld.energy = 1.8
    ld.angle = math.radians(1.6)
    ld.color = (1.0, 0.97, 0.92)
    sun_ob = bpy.data.objects.new("VF_MiamiSunFill", ld)
    st_col.objects.link(sun_ob)
    sun_ob.location = (18.0, 22.0, 26.0)
    sun_ob.rotation_euler = (Vector((0.0, 2.0, 2.0)) - sun_ob.location).to_track_quat("-Z", "Y").to_euler()

    # Also add warm interior dining room practical fill lights so sv12/sv13/sv15/sv16 show sculpted couches, 3D frames & bar clearly!
    for ilx, ily, ilz, ieng in [
        (-2.2, -0.5, 3.35, 300.0),
        (-2.2, -2.5, 2.85, 220.0),
        ( 2.65, -1.8, 3.35, 320.0),
        ( 5.25, -1.8, 3.35, 340.0),
        ( 7.65, -1.8, 3.35, 300.0),
        ( 4.50,  1.6, 3.35, 280.0),
    ]:
        pl = bpy.data.lights.new(f"VF_IntFill_{ilx}_{ily}", "POINT")
        pl.energy = ieng
        pl.color = (1.0, 0.92, 0.80)
        pl.shadow_soft_size = 0.45
        pob = bpy.data.objects.new(pl.name, pl)
        pob.location = (ilx, ily, ilz)
        try:
            pob.visible_glossy = False
        except AttributeError:
            pass
        st_col.objects.link(pob)

    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        try:
            sc.view_settings.view_transform = "AgX"
        except TypeError:
            pass
    sc.view_settings.exposure = -0.15
    return st_col


# Exact cameras matched to the 5 uploaded Street View screenshots + Aerial + 4 Macro Prop Close-Ups!
STREETVIEW_CAMS = [
    # (filename, cam_loc, target_loc, lens_mm)
    ("sv1_se_corner.png",       (17.2, 17.0, 2.45),  (2.2,  3.5, 4.6),  20.0),  # Photo 1: SE corner Ocean Dr & 8th St
    ("sv2_front_ocean_dr.png",  ( 2.0, 20.8, 2.45),  (1.5,  4.0, 5.2),  21.0),  # Photo 2: Straight-on East Ocean Dr front (full roof to curb!)
    ("sv3_ne_34_block.png",     (-12.2, 18.8, 2.65), (-4.0, 4.0, 4.5),  22.0),  # Photo 3: NE 3/4 News Cafe + 804 Ocean Dr
    ("sv4_streetscape.png",     (-24.8, 17.8, 2.55), (-6.5, 5.5, 3.6),  20.0),  # Photo 4: Wide Ocean Dr streetscape (shows 820 blue arch + 804 + 800!)
    ("sv5_south_8th_st.png",    (19.6, -2.5, 2.45),  (9.2, -2.5, 5.5),  18.5),  # Photo 5: South 8th St elevation (shows rooftop vents!)
    ("sv6_aerial_hero.png",     (27.5, 30.0, 20.0),  (-1.0, 3.5, 3.5),  34.0),  # Aerial 3/4 bird's-eye establishing shot
    ("sv7_patio_closeup.png",   ( 4.2, 13.0, 2.15),  ( 2.2, 5.4, 2.7),  30.0),  # Patio, awnings, bougainvillea, quatrefoil breeze blocks
    ("sv8_macro_bistro.png",    ( 4.95, 10.85, 1.58),( 3.45, 9.00, 0.82), 40.0), # Macro: Parisian bentwood rattan chairs, marble/brass CAD table, tableware, cutlery, candle, podium & menu stand
    ("sv9_macro_804_820.png",   (-10.5, 13.2, 2.50), (-12.5, 4.2, 2.90), 32.0), # Macro: 804 gnarled fluted trees, Spanish barrel tiles, lanterns, French door & 820 royal blue arch
    ("sv10_macro_street.png",   (14.8, 10.6, 1.45),  (11.4, 6.9, 0.85),  36.0), # Macro: 20-rib CAD trash bin, glazed ceramic pots, palm trunks, ADA tactile domes, curb & 8th St
    ("sv11_macro_hydrant.png",  (14.6, -2.55, 1.15), (12.1, -1.65, 0.72), 46.0), # Macro: 9.5k bolted Mueller fire hydrant, 8th St curb & sidewalk
    ("sv12_interior_wide.png",  ( 0.35,  2.75, 1.75), ( 5.20, -2.50, 1.65), 22.0), # Interior: sculpted Art Deco banquettes, mid-room divider, tables, chairs & gallery wall
    ("sv13_interior_bar.png",   ( 1.35,  1.25, 1.50), (-2.30, -1.80, 1.35), 26.0), # Interior Bar: paneled mahogany bar, espresso machine, draft taps, mirror, bottles & barstools
    ("sv14_chair_joints.png",   ( 4.42, 10.68, 1.18), ( 3.76,  9.84, 0.80), 58.0), # Ultra-macro: Parisian chair joints (flush ferrules, foot ring, seat hoop, domed cushion, backrest lock!)
    ("sv15_banquette_art.png",  ( 4.80, -0.85, 1.70), ( 5.25, -4.12, 1.74), 24.0), # Ultra-macro: sculpted oxblood leather banquettes + 8 REAL 3D framed paintings + brass picture lights!
    ("sv16_bar_joints.png",     (-0.85,  0.55, 0.92), (-2.15, -0.78, 0.68), 46.0), # Ultra-macro: bar footrail cast T-collar brackets (zero poke-through!) + 4-spoke torus barstool ring!
]


def compose_streetview_comparison() -> str:
    """Pair all 5 real Google Street View photos directly alongside our 5 Cycles OPTIX renders + 2x2 Macro Prop Showcase!"""
    from PIL import Image, ImageDraw, ImageFont

    pairs = [
        ("Photo 1: SE Corner (Ocean Dr & 8th St)", "ref_hero_se_corner.jpg", "sv1_se_corner.png"),
        ("Photo 2: East Ocean Dr Front Facade", "ref_front_ocean_dr.jpg", "sv2_front_ocean_dr.png"),
        ("Photo 3: NE 3/4 Block (800 & 804 Ocean Dr)", "ref_ne_34_block.jpg", "sv3_ne_34_block.png"),
        ("Photo 4: Ocean Dr Streetscape (820 -> 800)", "ref_ocean_dr_streetscape.jpg", "sv4_streetscape.png"),
        ("Photo 5: South 8th St Elevation (the hotel @ 800)", "ref_side_8th_st.jpg", "sv5_south_8th_st.png"),
    ]
    cw, ch, pad, hdr = 960, 480, 14, 42
    sheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + hdr) * len(pairs) + pad * (len(pairs) + 1)), (18, 20, 24))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 22)
    except OSError:
        font = ImageFont.load_default()

    ref_dir = os.path.join(THIS_DIR, "references")
    for idx, (title, ref_f, ren_f) in enumerate(pairs):
        y0 = pad + idx * (ch + hdr + pad)
        draw.text((pad, y0 + 8), f"REAL GOOGLE STREET VIEW  —  {title}", fill=(226, 232, 240), font=font)
        draw.text((pad * 2 + cw, y0 + 8), f"VELUM FORGE 3D MODEL (CYCLES OPTIX)", fill=(116, 236, 182), font=font)
        for col_i, path in enumerate([os.path.join(ref_dir, ref_f), os.path.join(RENDERS_DIR, ren_f)]):
            if os.path.isfile(path):
                im = Image.open(path).convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
                sheet.paste(im, (pad + col_i * (cw + pad), y0 + hdr))

    out_path = os.path.join(RENDERS_DIR, "streetview_comparison.png")
    sheet.save(out_path)

    # Also compose 3x2 High-Poly ArchViz & Macro Prop Showcase Sheet!
    macros = [
        ("Aerial 3/4 Hero Establishing View (800-820 Ocean Dr & Lummus Park)", "sv6_aerial_hero.png"),
        ("Patio Facade, Quatrefoil Breeze Blocks, Awnings & Bougainvillea", "sv7_patio_closeup.png"),
        ("Macro: Parisian Bentwood Chairs, CAD Marble/Brass Table, Tableware & Podium", "sv8_macro_bistro.png"),
        ("Macro: 804 Fissured Hardwood Trees, Spanish Barrel Tiles & Lanterns", "sv9_macro_804_820.png"),
        ("Macro: 20-Rib Trash Bin, Ceramic Urns, Terraced Palms & ADA Tactile Domes", "sv10_macro_street.png"),
        ("Macro: 9.5k Bolted Mueller Fire Hydrant & 8th St Coral Sidewalk", "sv11_macro_hydrant.png"),
    ]
    msheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + hdr) * 3 + pad * 4), (18, 20, 24))
    mdraw = ImageDraw.Draw(msheet)
    for idx, (title, fn) in enumerate(macros):
        r_i, c_i = divmod(idx, 2)
        x0 = pad + c_i * (cw + pad)
        y0 = pad + r_i * (ch + hdr + pad)
        mdraw.text((x0, y0 + 8), title, fill=(116, 236, 182), font=font)
        p = os.path.join(RENDERS_DIR, fn)
        if os.path.isfile(p):
            im = Image.open(p).convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
            msheet.paste(im, (x0, y0 + hdr))
    msheet.save(os.path.join(RENDERS_DIR, "prop_showcase_sheet.png"))

    # Compose dedicated 3x2 Interior & Joint Connection Audit Sheet (`interior_and_joints_sheet.png`)!
    joints = [
        ("Interior Wide: Art Deco Banquettes, Mid-Room Partition & 3D Gallery Wall", "sv12_interior_wide.png"),
        ("Interior Bar: Mahogany/Marble Bar, Espresso Machine, Mirror & Swivel Barstools", "sv13_interior_bar.png"),
        ("Ultra-Macro: Sculpted Oxblood Banquettes + 8 REAL 3D Framed Paintings & Lights", "sv15_banquette_art.png"),
        ("Ultra-Macro: Brass Bar Footrail Cast T-Collars + 4-Spoke Torus Barstool Ring", "sv16_bar_joints.png"),
        ("Ultra-Macro: Parisian Bistro Chair Joints (Ferrules, Ring, Seat, Backrest Lock)", "sv14_chair_joints.png"),
        ("Patio Bistro Ensemble: Flush CAD Marble/Brass Tables, Chairs, Podium & Menu", "sv8_macro_bistro.png"),
    ]
    jsheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + hdr) * 3 + pad * 4), (18, 20, 24))
    jdraw = ImageDraw.Draw(jsheet)
    for idx, (title, fn) in enumerate(joints):
        r_i, c_i = divmod(idx, 2)
        x0 = pad + c_i * (cw + pad)
        y0 = pad + r_i * (ch + hdr + pad)
        jdraw.text((x0, y0 + 8), title, fill=(116, 236, 182), font=font)
        p = os.path.join(RENDERS_DIR, fn)
        if os.path.isfile(p):
            im = Image.open(p).convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
            jsheet.paste(im, (x0, y0 + hdr))
    jsheet.save(os.path.join(RENDERS_DIR, "interior_and_joints_sheet.png"))
    return out_path


def main() -> int:
    os.makedirs(RENDERS_DIR, exist_ok=True)
    builder.build_all(clear_scene=True)

    sc = bpy.context.scene
    bake.enable_cycles_gpu(sc)
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 640
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"

    st_col = setup_miami_sun_sky(sc)
    cd = bpy.data.cameras.new("VF_SVCam")
    cam = bpy.data.objects.new("VF_SVCam", cd)
    st_col.objects.link(cam)
    sc.camera = cam

    for fname, loc, tgt, lens in STREETVIEW_CAMS:
        cam.location = Vector(loc)
        cam.data.lens = lens
        cam.data.clip_start = 0.1
        cam.data.clip_end = 250.0
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        out_p = os.path.join(RENDERS_DIR, fname)
        bake.render_still_safe(sc, out_p, cooldown_sec=0.5)
        core.log(f"[SV-QA] Rendered {out_p}")

    core.clear_collection(st_col)
    bpy.data.collections.remove(st_col)
    try:
        comp_p = compose_streetview_comparison()
        core.log(f"[SV-QA] Composed side-by-side comparison sheet: {comp_p}")
    except ImportError:
        core.log("[SV-QA] Pillow not in Blender Python; run with .venv --compose-only to build comparison sheet.")
    return 0


if __name__ == "__main__":
    if "--compose-only" in sys.argv:
        p = compose_streetview_comparison()
        print(f"[SV-QA] Composed side-by-side comparison sheet: {p}")
        raise SystemExit(0)
    raise SystemExit(main())
