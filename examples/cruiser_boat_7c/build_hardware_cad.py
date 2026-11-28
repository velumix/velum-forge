r"""Build precision OpenCascade B-Rep CAD marine hardware for Cruiser Boat 7C (18.3 m / 60-ft Flybridge Yacht).

Generates 6 watertight, meter-scale `.step` + `.glb` sub-assemblies under `examples/cruiser_boat_7c/cad/`:
  1. deck_cleat        (320 mm heavy-duty 316 stainless yacht mooring cleat, Z >= 0)
  2. steering_wheel    (400 mm 5-spoke dished stainless helm wheel + Edson power knob, axis = +Y)
  3. throttle_binnacle (Twin-lever Volvo IPS yacht electronic binnacle control, Z >= 0)
  4. pod_propeller     (540 mm 4-blade skewed Nibral/stainless IPS pod propeller, axis = +Y)
  5. radar_scanner     (1.26 m Garmin-style open-array radar pedestal + swept horizontal array bar, Z >= 0)
  6. bow_anchor        (Sculpted 316 stainless yacht plow anchor for recessed bow stem pocket)

Usage:
    .\.venv\Scripts\python.exe examples\cruiser_boat_7c\build_hardware_cad.py
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
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Circle,
    Cone,
    Cylinder,
    Ellipse,
    Locations,
    Mode,
    Plane,
    Pos,
    RectangleRounded,
    Rot,
    Sphere,
    Torus,
    chamfer,
    extrude,
    loft,
)
from cad_bridge import decimate_mesh, export_cad_part, inspect_mesh_file  # noqa: E402

CAD_OUT = os.path.join(THIS_DIR, "cad")


def build_deck_cleat():
    """320 mm heavy-duty sculpted 316 stainless yacht mooring cleat, grounded at Z = 0."""
    base_len, base_wid, base_h = 0.185, 0.072, 0.013
    horn_z = 0.074

    with BuildPart() as cleat:
        with BuildSketch(Plane.XY):
            RectangleRounded(base_len, base_wid, radius=base_wid * 0.45)
        extrude(amount=base_h)
        top_e = cleat.edges().filter_by(lambda e: abs(e.center().Z - base_h) < 1e-4)
        if top_e:
            chamfer(top_e, length=0.0028)

    part = cleat.part

    for sign in (-1.0, 1.0):
        with BuildPart() as leg:
            with BuildSketch(Plane.XY.offset(0.006)):
                with Locations((sign * 0.044, 0.0)):
                    Ellipse(0.021, 0.014)
            with BuildSketch(Plane.XY.offset(horn_z - 0.006)):
                with Locations((sign * 0.056, 0.0)):
                    Ellipse(0.018, 0.012)
            loft()
        part = part + leg.part

    xs = [-0.160, -0.105, -0.052, 0.0, 0.052, 0.105, 0.160]
    widths = [0.014, 0.025, 0.034, 0.030, 0.034, 0.025, 0.014]
    heights = [0.014, 0.022, 0.027, 0.024, 0.027, 0.022, 0.014]
    z_centers = [horn_z + 0.006, horn_z + 0.003, horn_z, horn_z - 0.002, horn_z, horn_z + 0.003, horn_z + 0.006]

    with BuildPart() as horn:
        for x_pos, wy, hz, zc in zip(xs, widths, heights, z_centers):
            p = Plane(origin=(x_pos, 0.0, zc), x_dir=(0.0, 1.0, 0.0), z_dir=(1.0, 0.0, 0.0))
            with BuildSketch(p):
                Ellipse(wy * 0.5, hz * 0.5)
        loft()
    part = part + horn.part

    for sign in (-1.0, 1.0):
        part = part + Pos(sign * 0.160, 0.0, horn_z + 0.006) * Sphere(radius=0.0075)

    for sx in (-0.072, 0.072):
        for sy in (-0.019, 0.019):
            part = part - Pos(sx, sy, base_h - 0.002) * Cylinder(radius=0.0055, height=0.007)

    return part - Pos(0.0, 0.0, -0.03) * Box(0.6, 0.6, 0.06)


def build_steering_wheel():
    """400 mm 5-spoke dished stainless luxury yacht helm wheel + maneuvering knob (axis = +Y)."""
    rim_major_r = 0.190
    rim_minor_r = 0.0145
    dish_y = -0.058

    collar = Pos(0.0, 0.024, 0.0) * Rot(90, 0, 0) * Cone(bottom_radius=0.042, top_radius=0.032, height=0.042)
    hub = Pos(0.0, -0.005, 0.0) * Rot(90, 0, 0) * Cylinder(radius=0.038, height=0.046)
    cap_dome = Pos(0.0, -0.025, 0.0) * Sphere(radius=0.031)
    rim = Pos(0.0, dish_y, 0.0) * Rot(90, 0, 0) * Torus(major_radius=rim_major_r, minor_radius=rim_minor_r)
    wheel = collar + hub + cap_dome + rim

    for i in range(5):
        ang = math.radians(90.0 + i * 72.0)
        dx, dz = math.cos(ang), math.sin(ang)
        r0, r1 = 0.020, rim_major_r + 0.006
        y0, y1 = -0.007, dish_y
        vec = ((r1 - r0) * dx, y1 - y0, (r1 - r0) * dz)
        spoke_len = math.sqrt(sum(c * c for c in vec))
        z_unit = tuple(c / spoke_len for c in vec)
        x_dir = (-dz, 0.0, dx)
        plane = Plane(origin=(r0 * dx, y0, r0 * dz), x_dir=x_dir, z_dir=z_unit)
        with BuildPart() as sp:
            with BuildSketch(plane):
                Circle(0.0105)
            with BuildSketch(plane.offset(spoke_len)):
                Circle(0.0080)
            loft()
        wheel = wheel + sp.part

    knob_ang = math.radians(52.0)
    kx = rim_major_r * math.cos(knob_ang)
    kz = rim_major_r * math.sin(knob_ang)
    knob = (
        Pos(kx, dish_y, kz) * Rot(90, 0, 0) * Cylinder(radius=0.0195, height=0.030)
        + Pos(kx, dish_y - 0.019, kz) * Rot(90, 0, 0) * Cone(bottom_radius=0.016, top_radius=0.011, height=0.030)
        + Pos(kx, dish_y - 0.038, kz) * Rot(90, 0, 0) * Cone(bottom_radius=0.024, top_radius=0.013, height=0.030)
        + Pos(kx, dish_y - 0.049, kz) * Sphere(radius=0.022)
    )
    return wheel + knob


def build_throttle_binnacle():
    """Twin-lever Volvo IPS electronic yacht throttle control binnacle, grounded at Z = 0."""
    with BuildPart() as flange:
        with BuildSketch(Plane.XY):
            RectangleRounded(0.176, 0.215, radius=0.034)
        with BuildSketch(Plane.XY.offset(0.024)):
            RectangleRounded(0.162, 0.198, radius=0.030)
        loft()

    with BuildPart() as dome:
        with BuildSketch(Plane.XY.offset(0.014)):
            RectangleRounded(0.126, 0.150, radius=0.028)
        with BuildSketch(Plane.XY.offset(0.078)):
            RectangleRounded(0.104, 0.110, radius=0.024)
        loft()

    part = flange.part + dome.part

    # Twin port & starboard electronic shift/throttle levers (cleanly separated across X = 0!)
    tilt_rad = math.radians(12.0)
    arm_len = 0.145
    gy = -0.004 + arm_len * math.sin(tilt_rad)
    gz = 0.056 + arm_len * math.cos(tilt_rad)
    for sx in (-0.052, 0.052):
        # Drum penetrates deeply into dome (from +/-0.022 to +/-0.068)
        drum = Pos(sx * 0.85, -0.004, 0.056) * Rot(0, 90, 0) * Cylinder(radius=0.030, height=0.048)
        part = part + drum
        arm_plane = Plane(
            origin=(sx, -0.004, 0.048),
            x_dir=(1.0, 0.0, 0.0),
            z_dir=(0.0, math.sin(tilt_rad), math.cos(tilt_rad)),
        )
        with BuildPart() as stalk:
            with BuildSketch(arm_plane):
                RectangleRounded(0.016, 0.030, radius=0.005)
            with BuildSketch(arm_plane.offset(arm_len + 0.012)):
                RectangleRounded(0.013, 0.022, radius=0.004)
            loft()
        # Separate port/stbd ergonomic horizontal grips (gap of 36 mm between inner tips!)
        grip = Pos(sx, gy, gz) * Rot(0, 90, 0) * Cylinder(radius=0.017, height=0.052)
        cap_in = Pos(sx - 0.026, gy, gz) * Sphere(radius=0.017)
        cap_out = Pos(sx + 0.026, gy, gz) * Sphere(radius=0.017)
        part = part + stalk.part + grip + cap_in + cap_out

    return part


def build_pod_propeller():
    """540 mm 4-blade skewed Nibral/stainless Volvo IPS pod propeller (axis = +Y)."""
    hub_front = Pos(0.0, 0.044, 0.0) * Rot(90, 0, 0) * Cone(bottom_radius=0.068, top_radius=0.082, height=0.150)
    hub_aft = Pos(0.0, -0.068, 0.0) * Rot(90, 0, 0) * Cone(bottom_radius=0.038, top_radius=0.068, height=0.085)
    nose_cone = Pos(0.0, -0.118, 0.0) * Sphere(radius=0.038)
    hub_solid = hub_front + hub_aft + nose_cone

    # Radial stations: (r_span, pitch_deg, chord_m, thick_m, skew_t, rake_y)
    stations = [
        (0.056, 36.0, 0.125, 0.0185, 0.000, 0.008),
        (0.100, 32.0, 0.178, 0.0145, -0.012, -0.004),
        (0.150, 27.5, 0.212, 0.0115, -0.030, -0.016),
        (0.198, 24.0, 0.214, 0.0095, -0.052, -0.028),
        (0.238, 21.0, 0.175, 0.0078, -0.072, -0.038),
        (0.262, 19.2, 0.115, 0.0064, -0.085, -0.044),
        (0.272, 18.0, 0.058, 0.0052, -0.092, -0.048),
    ]

    for b_idx in range(4):
        ang = math.radians(b_idx * 90.0)
        rx0, rz0 = math.cos(ang), math.sin(ang)
        tx0, tz0 = -math.sin(ang), math.cos(ang)
        root_plane = Plane(origin=(0.0, 0.0, 0.0), x_dir=(tx0, 0.0, tz0), z_dir=(rx0, 0.0, rz0))
        faces = []
        for r, pitch_deg, chord, thick, skew_t, rake_y in stations:
            with BuildSketch(root_plane.offset(r)) as sk:
                with Locations((skew_t, rake_y)):
                    with Locations(Rot(0, 0, pitch_deg)):
                        RectangleRounded(chord, thick, radius=thick * 0.45)
            faces.append(sk.sketch.face())
        hub_solid = hub_solid + loft(faces)

    return hub_solid


def build_radar_scanner():
    """1.26 m Garmin-style open-array yacht radar pedestal + wide horizontal scanner array bar, Z >= 0."""
    # Tapered aerodynamic mounting pedestal
    with BuildPart() as ped:
        with BuildSketch(Plane.XY):
            RectangleRounded(0.380, 0.480, radius=0.075)
        with BuildSketch(Plane.XY.offset(0.055)):
            RectangleRounded(0.350, 0.440, radius=0.070)
        with BuildSketch(Plane.XY.offset(0.240)):
            RectangleRounded(0.290, 0.360, radius=0.060)
        with BuildSketch(Plane.XY.offset(0.290)):
            RectangleRounded(0.230, 0.280, radius=0.050)
        loft()

    part = ped.part

    # Rotating drive neck collar
    neck = Pos(0.0, 0.0, 0.310) * Cylinder(radius=0.082, height=0.080)
    part = part + neck

    # Wide 1.26 m swept open-array waveguide bar (cross-section along X!)
    xs = [-0.630, -0.580, -0.320, 0.0, 0.320, 0.580, 0.630]
    depths = [0.072, 0.105, 0.132, 0.148, 0.132, 0.105, 0.072]
    heights = [0.068, 0.095, 0.112, 0.122, 0.112, 0.095, 0.068]
    with BuildPart() as bar:
        for x_pos, dy, hz in zip(xs, depths, heights):
            p = Plane(origin=(x_pos, 0.0, 0.385), x_dir=(0.0, 1.0, 0.0), z_dir=(1.0, 0.0, 0.0))
            with BuildSketch(p):
                RectangleRounded(dy, hz, radius=min(dy, hz) * 0.38)
        loft()

    part = part + bar.part
    return part - Pos(0.0, 0.0, -0.04) * Box(1.8, 1.0, 0.08)


def build_bow_anchor():
    """Sculpted 316 stainless Delta/Ultra yacht plow anchor for the recessed bow stem pocket (shank along -Y/+Z)."""
    # Main curved plow fluke body (pointing downward/forward at bow stem!)
    fluke_stations = [
        # (z_offset, y_offset, width_x, thick_y)
        (-0.38, 0.08, 0.055, 0.032),
        (-0.24, 0.04, 0.240, 0.048),
        (-0.08, 0.00, 0.380, 0.052),
        (0.08, -0.06, 0.420, 0.048),
        (0.20, -0.14, 0.280, 0.040),
    ]
    with BuildPart() as fluke:
        for zc, yc, wx, ty in fluke_stations:
            with BuildSketch(Plane.XY.offset(zc)):
                with Locations((0.0, yc)):
                    RectangleRounded(wx, ty, radius=min(wx, ty) * 0.40)
        loft()

    # Heavy curved stainless shank sweeping inward (-Y) and upward (+Z) into the bow roller pocket
    shank_pts = [
        (0.0, 0.02, -0.12, 0.042, 0.085),
        (0.0, -0.12, 0.05, 0.040, 0.082),
        (0.0, -0.28, 0.16, 0.038, 0.076),
        (0.0, -0.46, 0.22, 0.036, 0.068),
    ]
    with BuildPart() as shank:
        for xc, yc, zc, wx, hz in shank_pts:
            p = Plane(origin=(xc, yc, zc), x_dir=(1.0, 0.0, 0.0), z_dir=(0.0, -1.0, 0.45))
            with BuildSketch(p):
                RectangleRounded(wx, hz, radius=0.012)
        loft()

    # Fluke stabilizer roll-bar arch visible at the bow pocket face
    roll_left = Pos(-0.14, 0.01, -0.02) * Rot(22, -18, 0) * Cylinder(radius=0.018, height=0.32)
    roll_right = Pos(0.14, 0.01, -0.02) * Rot(22, 18, 0) * Cylinder(radius=0.018, height=0.32)
    ballast_tip = Pos(0.0, 0.075, -0.37) * Sphere(radius=0.034)
    return fluke.part + shank.part + roll_left + roll_right + ballast_tip


SPECS = [
    ("deck_cleat", build_deck_cleat, 1100, (0.86, 0.89, 0.92, 1.0), 0.94, 0.16),
    ("steering_wheel", build_steering_wheel, 2400, (0.86, 0.89, 0.92, 1.0), 0.94, 0.16),
    ("throttle_binnacle", build_throttle_binnacle, 1800, (0.83, 0.86, 0.90, 1.0), 0.92, 0.18),
    ("pod_propeller", build_pod_propeller, 2800, (0.85, 0.78, 0.62, 1.0), 0.94, 0.16),
    ("radar_scanner", build_radar_scanner, 2200, (0.95, 0.96, 0.98, 1.0), 0.05, 0.18),
    ("bow_anchor", build_bow_anchor, 1800, (0.88, 0.91, 0.94, 1.0), 0.96, 0.12),
]


def main() -> int:
    os.makedirs(CAD_OUT, exist_ok=True)
    summary = []
    all_ok = True

    for name, fn, max_tris, color, metal, rough in SPECS:
        part = fn()
        res = export_cad_part(
            part,
            CAD_OUT,
            name,
            linear_deflection=0.0018,
            angular_deflection=0.35,
            color=color,
            metallic=metal,
            roughness=rough,
        )
        glb_path = res["glb"]
        tris = res["inspection"]["totals"]["tris"]
        if tris > max_tris:
            dec = decimate_mesh(glb_path, glb_path, target_tris=max_tris, preserve_topology=True)
            res["inspection"] = dec["after"]
            res["decimated_from"] = tris

        ins = inspect_mesh_file(glb_path)
        if not ins["pass"] or not ins["totals"]["all_watertight"]:
            all_ok = False
        summary.append(
            {
                "name": name,
                "tris": ins["totals"]["tris"],
                "watertight": ins["totals"]["all_watertight"],
                "size_m": ins["totals"]["size_m"],
                "pass": ins["pass"],
                "glb": glb_path,
            }
        )

    print(json.dumps({"ok": all_ok, "parts": summary}, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
