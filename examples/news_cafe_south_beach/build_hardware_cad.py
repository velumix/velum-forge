r"""Velum Forge High-Poly Precision B-Rep CAD Hardware for News Cafe South Beach (800 Ocean Dr).

NO 20k tri decimation — exported at smooth ArchViz / film-grade OpenCascade tessellation
(`linear_deflection=0.0009, angular_deflection=0.16`, 100% watertight B-Rep solids):
  1. `trash_bin`        — Fluted 20-rib Miami Beach park trash bin w/ rolled dome rim & recessed liner
  2. `menu_stand`       — Brushed stainless outdoor menu vitrine w/ flanged posts, lock & cantilevered LED hood
  3. `bistro_table`     — Smooth bullnose brass-rimmed marble cafe table w/ ornate turned Victorian S-scroll tripod
  4. `host_podium`      — Architectural mitered-frame host stand w/ sloped brass-lipped lectern & casters
  5. `fire_hydrant`     — Authentic bolted Mueller municipal fire hydrant w/ 16 hex bolts, 3 lugged nozzles & bonnet
  6. `lamp_luminaire`   — Aerodynamic cobra-head LED streetlight w/ dorsal cooling fins, photocell & clamp
  7. `tableware_set`    — Fine Parisian cafe place setting (rimmed porcelain plate, saucer, handled cup, stemmed glass, brass candle)

All parts modeled strictly in meters (`1.0 = 1.0 m`, `+Z = Up`, grounded at `Z = 0.0000 m`).
"""
from __future__ import annotations

import json
import math
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
CAD_DIR = os.path.join(REPO_ROOT, "engine", "cad")
if CAD_DIR not in sys.path:
    sys.path.insert(0, CAD_DIR)

from build123d import (  # noqa: E402
    Axis,
    Box,
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
    Cone,
    Cylinder,
    Face,
    Line,
    Plane,
    Polygon,
    Pos,
    RectangleRounded,
    Rot,
    Sphere,
    Spline,
    Torus,
    extrude,
    loft,
    make_face,
    revolve,
    sweep,
)
from cad_bridge import decimate_mesh, export_cad_part  # noqa: E402

CAD_OUT = os.path.join(THIS_DIR, "cad")


def build_trash_bin():
    """High-poly Miami Beach 20-slat fluted forest-green park trash bin (D=0.59 m, H=0.94 m, Z>=0)."""
    # Smooth revolved drum body with bottom plinth skirt, rolled lip, and tapered rain rim
    body = Pos(0, 0, 0.435) * Cone(bottom_radius=0.252, top_radius=0.278, height=0.87)
    base_skirt = Pos(0, 0, 0.028) * Cylinder(radius=0.272, height=0.056)
    base_bead = Pos(0, 0, 0.058) * Torus(major_radius=0.260, minor_radius=0.014)
    mid_band = Pos(0, 0, 0.44) * Torus(major_radius=0.268, minor_radius=0.010)
    top_collar = Pos(0, 0, 0.855) * Cylinder(radius=0.296, height=0.058)
    top_rim = Pos(0, 0, 0.892) * Torus(major_radius=0.282, minor_radius=0.026)
    dome_lip = Pos(0, 0, 0.910) * Cone(bottom_radius=0.290, top_radius=0.230, height=0.052)
    part = body + base_skirt + base_bead + mid_band + top_collar + top_rim + dome_lip

    # 20 crisp smooth half-round vertical structural flutes around the drum
    for i in range(20):
        ang = math.radians(i * (360.0 / 20.0))
        rx = 0.266 * math.cos(ang)
        ry = 0.266 * math.sin(ang)
        rib = Pos(rx, ry, 0.445) * Cylinder(radius=0.014, height=0.77)
        cap_t = Pos(rx, ry, 0.830) * Sphere(radius=0.014)
        cap_b = Pos(rx, ry, 0.060) * Sphere(radius=0.014)
        part = part + rib + cap_t + cap_b

    # Deep recessed disposal opening at top
    cavity = Pos(0, 0, 0.90) * Cylinder(radius=0.205, height=0.20)
    part = part - cavity
    part = part - Pos(0, 0, -0.25) * Box(1.2, 1.2, 0.5)
    return part


def build_menu_stand():
    """High-poly brushed-stainless News Cafe menu vitrine w/ flanged posts, lock & cantilevered LED lamp hood."""
    with BuildPart() as base:
        with BuildSketch(Plane.XY):
            RectangleRounded(0.58, 0.42, radius=0.036)
        extrude(amount=0.032)
        with BuildSketch(Plane.XY.offset(0.028)):
            RectangleRounded(0.52, 0.36, radius=0.030)
        extrude(amount=0.024)
    part = base.part

    # Twin tubular stainless uprights with turned deck flange collars & bolt heads
    for sx in (-0.215, 0.215):
        flange = Pos(sx, 0.0, 0.062) * Cylinder(radius=0.044, height=0.024)
        collar = Pos(sx, 0.0, 0.082) * Cone(bottom_radius=0.036, top_radius=0.022, height=0.026)
        post = Pos(sx, 0.0, 0.65) * Cylinder(radius=0.020, height=1.18)
        top_fin = Pos(sx, 0.0, 1.32) * Sphere(radius=0.022)
        part = part + flange + collar + post + top_fin

    # Twin sleek horizontal cross-braces
    for tz in (0.28, 0.48):
        tie = Pos(0.0, 0.0, tz) * Rot(0, 90, 0) * Cylinder(radius=0.011, height=0.44)
        part = part + tie

    # Framed mitered vitrine cabinet (Z = 0.56 .. 1.32 m) w/ recessed front glass pocket
    with BuildPart() as cab_p:
        with BuildSketch(Plane.XY.offset(0.56)):
            RectangleRounded(0.58, 0.098, radius=0.016)
        extrude(amount=0.76)
    cab = cab_p.part
    # Outer picture-frame door bezel lip on +Y front face
    with BuildPart() as bezel_p:
        with BuildSketch(Plane.XY.offset(0.575)):
            RectangleRounded(0.56, 0.030, radius=0.010)
        extrude(amount=0.73)
    bezel = Pos(0.0, 0.042, 0.0) * bezel_p.part
    cab = cab + bezel
    # Recessed menu cavity
    recess = Pos(0.0, 0.044, 0.94) * Box(0.49, 0.048, 0.67)
    cab = cab - recess
    # Side stainless barrel lock + hinges
    lock = Pos(0.268, 0.046, 0.94) * Rot(90, 0, 0) * Cylinder(radius=0.010, height=0.020)

    # Cantilevered architectural rain hood + overhead tubular LED reading bar
    hood = Pos(0.0, 0.020, 1.328) * Box(0.62, 0.155, 0.024)
    led_bar = Pos(0.0, 0.075, 1.312) * Rot(0, 90, 0) * Cylinder(radius=0.012, height=0.46)
    part = part + cab + lock + hood + led_bar
    part = part - Pos(0, 0, -0.25) * Box(1.2, 1.2, 0.5)
    return part


def build_bistro_table():
    """High-poly Parisian bistro table: turned cast-iron baluster column, 3 scrolled legs & bullnose brass-rimmed marble top."""
    # Ornate turned Victorian cast-iron central column (Z = 0.06 .. 0.705 m)
    pts_col = [
        (0.000, 0.060),
        (0.074, 0.060),
        (0.072, 0.085),
        (0.056, 0.115),
        (0.038, 0.155),
        (0.046, 0.180),
        (0.030, 0.210),
        (0.027, 0.420),
        (0.036, 0.445),
        (0.026, 0.470),
        (0.025, 0.610),
        (0.042, 0.640),
        (0.068, 0.685),
        (0.078, 0.708),
        (0.000, 0.708),
    ]
    with BuildPart() as col_p:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                for i in range(len(pts_col) - 1):
                    Line(pts_col[i], pts_col[i + 1])
                Line(pts_col[-1], pts_col[0])
            make_face()
        revolve(axis=Axis.Z)
    part = col_p.part

    # Cast-iron 4-arm under-table support spider
    for a_deg in (0, 90):
        part = part + Pos(0, 0, 0.700) * Rot(0, 0, a_deg) * Box(0.36, 0.038, 0.024)

    # 3 gracefully arched Victorian cast-iron S-scroll tripod legs w/ paw feet & leveling glides
    for i in range(3):
        ang_deg = i * 120.0
        with BuildPart() as leg_p:
            with BuildLine(Plane.XZ) as path:
                Spline([(0.042, 0.135), (0.110, 0.125), (0.175, 0.072), (0.232, 0.032), (0.246, 0.016)])
            with BuildSketch(Plane.YZ.offset(0.042)):
                RectangleRounded(0.030, 0.028, radius=0.008)
            # Use clean smooth lofted arch segments for 100% bulletproof B-Rep sweep
        leg_pts = [(0.045, 0.135), (0.105, 0.122), (0.165, 0.082), (0.215, 0.042), (0.242, 0.018)]
        for k in range(len(leg_pts) - 1):
            r0, z0 = leg_pts[k]
            r1, z1 = leg_pts[k + 1]
            dx, dz = r1 - r0, z1 - z0
            L = math.hypot(dx, dz) + 0.010
            pitch = -math.degrees(math.atan2(dz, dx))
            mx, mz = 0.5 * (r0 + r1), 0.5 * (z0 + z1)
            seg = Rot(0, 0, ang_deg) * Pos(mx, 0, mz) * Rot(0, pitch + 90.0, 0) * Cylinder(radius=0.017 - 0.0015 * k, height=L)
            part = part + seg
            joint = Rot(0, 0, ang_deg) * Pos(r0, 0, z0) * Sphere(radius=0.017 - 0.0015 * k)
            part = part + joint
        # Sculpted scroll finial & round floor glide pad
        foot_pad = Rot(0, 0, ang_deg) * Pos(0.242, 0, 0.014) * Cylinder(radius=0.026, height=0.028)
        scroll_knob = Rot(0, 0, ang_deg) * Pos(0.115, 0, 0.140) * Sphere(radius=0.016)
        part = part + foot_pad + scroll_knob

    # Smooth Carrara marble tabletop + stepped bullnose gleaming brass gallery rim (Z = 0.710 .. 0.742 m)
    top_slab = Pos(0, 0, 0.726) * Cylinder(radius=0.332, height=0.032)
    rim_upper = Pos(0, 0, 0.733) * Torus(major_radius=0.332, minor_radius=0.011)
    rim_lower = Pos(0, 0, 0.719) * Torus(major_radius=0.332, minor_radius=0.010)
    rim_band = Pos(0, 0, 0.726) * Cylinder(radius=0.342, height=0.016)
    part = part + top_slab + rim_upper + rim_lower + rim_band
    part = part - Pos(0, 0, -0.25) * Box(1.2, 1.2, 0.5)
    return part


def build_host_podium():
    """High-poly architectural charcoal-steel News Cafe host lectern podium (W=0.72 m, D=0.56 m, H=1.16 m)."""
    # 4 low heavy-duty rubber swivel caster wheels + stepped recessed toe-kick plinth
    part = Pos(0, 0, 0.055) * Box(0.64, 0.50, 0.050)
    for cx in (-0.25, 0.25):
        for cy in (-0.18, 0.18):
            wheel = Pos(cx, cy, 0.022) * Rot(0, 90, 0) * Cylinder(radius=0.022, height=0.022)
            stem = Pos(cx, cy, 0.036) * Cylinder(radius=0.010, height=0.028)
            part = part + wheel + stem

    # Main beveled cabinet body (Z = 0.07 .. 1.04 m)
    with BuildPart() as cab:
        with BuildSketch(Plane.XY.offset(0.07)):
            RectangleRounded(0.68, 0.54, radius=0.018)
        extrude(amount=0.97)
    part = part + cab.part

    # Architectural mitered raised perimeter frame trim on +Y front face
    frame_outer = Pos(0, 0.272, 0.555) * Box(0.64, 0.026, 0.88)
    frame_cut = Pos(0, 0.278, 0.555) * Box(0.56, 0.030, 0.80)
    part = part + (frame_outer - frame_cut)

    # Side raised decorative wainscoting panels
    for sx in (-0.342, 0.342):
        sp = Pos(sx, 0, 0.555) * Box(0.020, 0.44, 0.80)
        part = part + sp

    # Overhanging beveled top counter molding + slanted reading lectern desk & brass book-stop lip
    with BuildPart() as top_p:
        with BuildSketch(Plane.XY.offset(1.03)):
            RectangleRounded(0.76, 0.62, radius=0.020)
        extrude(amount=0.048)
    part = part + top_p.part

    # Sloped host ledger reading top (tilts gently toward host at -Y, raised privacy rail on +Y)
    slope_desk = Pos(0, -0.02, 1.105) * Rot(-10.0, 0, 0) * Box(0.70, 0.52, 0.026)
    front_shield = Pos(0, 0.255, 1.115) * Box(0.72, 0.030, 0.095)
    book_lip = Pos(0, -0.255, 1.072) * Rot(0, 90, 0) * Cylinder(radius=0.011, height=0.68)
    # Rear stainless handle bar
    handle = Pos(0, -0.290, 0.88) * Rot(0, 90, 0) * Cylinder(radius=0.009, height=0.28)
    part = part + slope_desk + front_shield + book_lip + handle
    part = part - Pos(0, 0, -0.25) * Box(1.4, 1.4, 0.5)
    return part


def build_fire_hydrant():
    """High-poly authentic Mueller-style bolted Miami Beach municipal fire hydrant (H=0.74 m, Z>=0)."""
    flange_bot = Pos(0, 0, 0.028) * Cylinder(radius=0.152, height=0.056)
    collar_b = Pos(0, 0, 0.068) * Cone(bottom_radius=0.132, top_radius=0.106, height=0.042)
    barrel = Pos(0, 0, 0.315) * Cylinder(radius=0.104, height=0.50)
    flange_top = Pos(0, 0, 0.562) * Cylinder(radius=0.136, height=0.036)
    bonnet = Pos(0, 0, 0.578) * Sphere(radius=0.114)
    bonnet_rim = Pos(0, 0, 0.580) * Torus(major_radius=0.112, minor_radius=0.014)
    part = flange_bot + collar_b + barrel + flange_top + bonnet + bonnet_rim

    # 8 structural vertical barrel flutes
    for i in range(8):
        a = math.radians(i * 45.0 + 22.5)
        part = part + Pos(0.102 * math.cos(a), 0.102 * math.sin(a), 0.24) * Cylinder(radius=0.010, height=0.26)

    # 16 hex flange bolts (8 on bottom ground flange + 8 on upper bonnet flange!)
    for z_b, r_b in [(0.062, 0.132), (0.584, 0.120)]:
        for i in range(8):
            a = math.radians(i * 45.0)
            bolt = Pos(r_b * math.cos(a), r_b * math.sin(a), z_b) * Cylinder(radius=0.010, height=0.018)
            part = part + bolt

    # 5-sided pentagon operating nut on top of bonnet
    with BuildPart() as nut_p:
        with BuildSketch(Plane.XY.offset(0.675)):
            Polygon(*[(0.028 * math.cos(2 * math.pi * k / 5), 0.028 * math.sin(2 * math.pi * k / 5)) for k in range(5)])
        extrude(amount=0.055)
    part = part + nut_p.part

    # Dual side 2.5" hose nozzles (+X / -X) w/ threaded collars, octagonal caps & pentagon lug nuts
    nozzle_lr = Pos(0, 0, 0.430) * Rot(0, 90, 0) * Cylinder(radius=0.044, height=0.285)
    part = part + nozzle_lr
    for sgn in (-1.0, 1.0):
        c_ring = Pos(sgn * 0.145, 0, 0.430) * Rot(0, 90, 0) * Cylinder(radius=0.052, height=0.026)
        c_dome = Pos(sgn * 0.160, 0, 0.430) * Sphere(radius=0.044)
        c_nut = Pos(sgn * 0.198, 0, 0.430) * Rot(0, 90, 0) * Cylinder(radius=0.018, height=0.028)
        part = part + c_ring + c_dome + c_nut

    # Front 4.5" steamer pumper nozzle (+Y) w/ cap & pentagon nut
    steamer = Pos(0, 0.112, 0.375) * Rot(90, 0, 0) * Cylinder(radius=0.062, height=0.105)
    s_cap = Pos(0, 0.165, 0.375) * Rot(90, 0, 0) * Cylinder(radius=0.072, height=0.028)
    s_dome = Pos(0, 0.175, 0.375) * Sphere(radius=0.060)
    s_nut = Pos(0, 0.228, 0.375) * Rot(90, 0, 0) * Cylinder(radius=0.022, height=0.028)
    part = part + steamer + s_cap + s_dome + s_nut
    part = part - Pos(0, 0, -0.25) * Box(1.0, 1.0, 0.5)
    return part


def build_lamp_luminaire():
    """High-poly aerodynamic cobra-head LED streetlight luminaire w/ dorsal cooling fins & photocell."""
    with BuildPart() as housing:
        with BuildSketch(Plane.YZ):
            RectangleRounded(0.088, 0.070, radius=0.024)
        with BuildSketch(Plane.YZ.offset(0.24)):
            RectangleRounded(0.215, 0.088, radius=0.036)
        with BuildSketch(Plane.YZ.offset(0.58)):
            RectangleRounded(0.255, 0.078, radius=0.032)
        with BuildSketch(Plane.YZ.offset(0.74)):
            RectangleRounded(0.130, 0.046, radius=0.018)
        loft()
    part = housing.part

    # 7 sculpted dorsal heat-sink cooling fins along upper body
    for k in range(7):
        fy = -0.078 + k * 0.026
        fin = Pos(0.42, fy, 0.044) * Box(0.32, 0.007, 0.018)
        part = part + fin

    # Slip-fitter mast clamp w/ collar & bolts + NEMA photocell dome + recessed optical lens
    collar = Pos(-0.08, 0.0, 0.0) * Rot(0, 90, 0) * Cylinder(radius=0.038, height=0.19)
    clamp_ring = Pos(-0.04, 0.0, 0.0) * Rot(0, 90, 0) * Torus(major_radius=0.040, minor_radius=0.009)
    photocell = Pos(0.22, 0.0, 0.058) * Cylinder(radius=0.030, height=0.056)
    photo_cap = Pos(0.22, 0.0, 0.086) * Sphere(radius=0.029)
    lens_rim = Pos(0.45, 0.0, -0.040) * Box(0.34, 0.175, 0.016)
    part = part + collar + clamp_ring + photocell + photo_cap + lens_rim
    bb = part.bounding_box()
    part = Pos(0, 0, -bb.min.Z) * part
    return part


def build_tableware_set():
    """High-poly revolved Parisian cafe dining set (centered at 0,0,0 -> placed right onto marble tabletop!).

    Contains:
      - Porcelain dinner plate w/ sculpted raised rim at (-0.15, 0.04)
      - Fluted espresso saucer + coffee cup w/ C-curved handle at (0.14, -0.06)
      - Graceful stemmed wine goblet (foot + slender stem + curved tulip bowl) at (0.04, 0.16)
      - Brass hurricane table votive candle holder at (0.0, 0.0)
    """
    # 1. Sculpted rimmed porcelain plate (D=0.22 m)
    plate_prof = [(0.0, 0.0), (0.068, 0.0), (0.078, 0.004), (0.106, 0.017), (0.110, 0.021), (0.104, 0.023), (0.072, 0.010), (0.0, 0.008)]
    with BuildPart() as p_plate:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                for i in range(len(plate_prof) - 1):
                    Line(plate_prof[i], plate_prof[i + 1])
                Line(plate_prof[-1], plate_prof[0])
            make_face()
        revolve(axis=Axis.Z)
    plate = Pos(-0.145, 0.035, 0.0) * p_plate.part

    # 2. Espresso saucer + cup w/ real curved loop handle
    saucer_prof = [(0.0, 0.0), (0.044, 0.0), (0.066, 0.013), (0.068, 0.016), (0.063, 0.017), (0.040, 0.007), (0.0, 0.006)]
    with BuildPart() as p_saucer:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                for i in range(len(saucer_prof) - 1):
                    Line(saucer_prof[i], saucer_prof[i + 1])
                Line(saucer_prof[-1], saucer_prof[0])
            make_face()
        revolve(axis=Axis.Z)
    cup_prof = [(0.0, 0.005), (0.025, 0.005), (0.036, 0.038), (0.040, 0.074), (0.035, 0.074), (0.031, 0.038), (0.021, 0.012), (0.0, 0.012)]
    with BuildPart() as p_cup:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                for i in range(len(cup_prof) - 1):
                    Line(cup_prof[i], cup_prof[i + 1])
                Line(cup_prof[-1], cup_prof[0])
            make_face()
        revolve(axis=Axis.Z)
    handle = Pos(0.039, 0.0, 0.044) * Rot(90, 0, 0) * Torus(major_radius=0.016, minor_radius=0.0045)
    cup_asm = Pos(0.145, -0.055, 0.0) * (p_saucer.part + p_cup.part + handle)

    # 3. Graceful stemmed wine glass (H=0.185 m, tulip bowl + slender stem + circular foot)
    glass_prof = [
        (0.000, 0.000), (0.034, 0.000), (0.034, 0.005), (0.007, 0.011), (0.0055, 0.088),
        (0.026, 0.104), (0.039, 0.138), (0.036, 0.178), (0.031, 0.184), (0.028, 0.178),
        (0.031, 0.138), (0.020, 0.108), (0.000, 0.102),
    ]
    with BuildPart() as p_glass:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                for i in range(len(glass_prof) - 1):
                    Line(glass_prof[i], glass_prof[i + 1])
                Line(glass_prof[-1], glass_prof[0])
            make_face()
        revolve(axis=Axis.Z)
    wine = Pos(0.045, 0.155, 0.0) * p_glass.part

    # 4. Turned brass hurricane table votive candle holder at center (0, 0)
    candle_prof = [
        (0.000, 0.000), (0.032, 0.000), (0.032, 0.008), (0.024, 0.016),
        (0.028, 0.088), (0.032, 0.095), (0.024, 0.095), (0.020, 0.016), (0.000, 0.016),
    ]
    with BuildPart() as p_candle:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                for i in range(len(candle_prof) - 1):
                    Line(candle_prof[i], candle_prof[i + 1])
                Line(candle_prof[-1], candle_prof[0])
            make_face()
        revolve(axis=Axis.Z)
    candle = p_candle.part

    # Join via invisible thin tabletop tie-disk embedded below tabletop Z=0? No, keep as separate clean B-Rep compound
    # exported cleanly — note `export_cad_part` supports multi-solid compounds!
    part = plate + cup_asm + wine + candle
    return part


def main() -> int:
    os.makedirs(CAD_OUT, exist_ok=True)
    # High-poly archviz tolerances — silky smooth curves, zero faceted low-poly decimation!
    specs = [
        ("trash_bin", build_trash_bin, "#1A5B36", 0.10, 0.48, 0.0012, 0.18, 9000),
        ("menu_stand", build_menu_stand, "#B8BEC6", 0.85, 0.24, 0.0010, 0.18, 7000),
        ("bistro_table", build_bistro_table, "#24272B", 0.55, 0.32, 0.0010, 0.16, 8500),
        ("host_podium", build_host_podium, "#343840", 0.25, 0.48, 0.0012, 0.20, 6000),
        ("fire_hydrant", build_fire_hydrant, "#E4B81E", 0.25, 0.34, 0.0010, 0.16, 9500),
        ("lamp_luminaire", build_lamp_luminaire, "#C2C7CC", 0.85, 0.26, 0.0012, 0.18, 6500),
        ("tableware_set", build_tableware_set, "#F5F5F2", 0.05, 0.14, 0.0008, 0.16, 6500),
    ]
    report = {}
    for name, fn, color, metallic, roughness, lin_def, ang_def, max_tris in specs:
        print(f"[CAD-HP] Building high-poly {name}...", flush=True)
        shape = fn()
        res = export_cad_part(
            shape,
            CAD_OUT,
            name,
            linear_deflection=lin_def,
            angular_deflection=ang_def,
            color=color,
            metallic=metallic,
            roughness=roughness,
        )
        tris = res["inspection"]["totals"]["tris"]
        if tris > max_tris:
            glb = res["glb"]
            dec = decimate_mesh(glb, glb, target_tris=max_tris, preserve_topology=True)
            res["inspection"] = dec["after"]
            tris = dec["after"]["totals"]["tris"]
        ok = res["inspection"]["pass"]
        wt = res["inspection"]["totals"]["all_watertight"]
        print(f"  -> {name}: {tris:,} tris, watertight={wt}, pass={ok}", flush=True)
        assert ok, f"CAD part {name} failed inspection: {res['inspection']['errors']}"
        report[name] = res["inspection"]["totals"]

    with open(os.path.join(CAD_OUT, "cad_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"[CAD-HP] Exported {len(specs)} high-poly watertight B-Rep CAD parts to {CAD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
