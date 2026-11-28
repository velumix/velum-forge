r"""Build precision B-Rep CAD marine hardware for the Sunrunner 24 offshore boat (v2 Realism Overhaul).

Generates 5 watertight, meter-scale `.step` + `.glb` assets under `assets/models/sunrunner_24/cad/`:
  1. deck_cleat        (220 mm Herreshoff/pull-up sculpted 316 stainless cleat, Z >= 0)
  2. steering_wheel    (370 mm 5-spoke dished destroyer wheel + Edson power knob, axis = Y)
  3. throttle_binnacle (Ergonomic Yamaha/Mercury single-lever binnacle + trim switch, Z >= 0)
  4. outboard_prop     (380 mm / 15" 3-blade progressively-pitched skewed offshore prop, axis = Y)
  5. rocket_launcher   (1.20 m T-Top aft 5-tube tulip-flared stainless rod holder bar)

Usage:
    .\tools\cad\.venv\Scripts\python.exe assets\models\sunrunner_24\build_hardware_cad.py
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
    Compound,
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
    fillet,
    loft,
)
from cad_bridge import decimate_mesh, export_cad_part, inspect_mesh_file  # noqa: E402

CAD_OUT = os.path.join(THIS_DIR, "cad")


def build_deck_cleat():
    """220 mm sculpted low-profile marine stainless cleat, grounded at Z = 0."""
    base_len, base_wid, base_h = 0.128, 0.052, 0.009
    horn_len, horn_z = 0.224, 0.052

    with BuildPart() as cleat:
        # Rounded oval base plate
        with BuildSketch(Plane.XY):
            RectangleRounded(base_len, base_wid, radius=base_wid * 0.46)
        extrude(amount=base_h)
        top_e = cleat.edges().filter_by(lambda e: abs(e.center().Z - base_h) < 1e-4)
        if top_e:
            chamfer(top_e, length=0.0022)

    part = cleat.part

    # Two angled, sculpted elliptical support legs
    for sign in (-1.0, 1.0):
        with BuildPart() as leg:
            with BuildSketch(Plane.XY.offset(0.004)):
                with Locations((sign * 0.030, 0.0)):
                    Ellipse(0.015, 0.010)
            with BuildSketch(Plane.XY.offset(horn_z - 0.004)):
                with Locations((sign * 0.038, 0.0)):
                    Ellipse(0.013, 0.009)
            loft()
        part = part + leg.part

    # Sculpted swept top horn bar (lofted from center saddle out to tapered tips)
    xs = [-0.112, -0.072, -0.036, 0.0, 0.036, 0.072, 0.112]
    widths = [0.009, 0.017, 0.024, 0.022, 0.024, 0.017, 0.009]
    heights = [0.009, 0.015, 0.019, 0.017, 0.019, 0.015, 0.009]
    z_centers = [horn_z + 0.004, horn_z + 0.002, horn_z, horn_z - 0.001, horn_z, horn_z + 0.002, horn_z + 0.004]

    with BuildPart() as horn:
        for x_pos, wy, hz, zc in zip(xs, widths, heights, z_centers):
            p = Plane(origin=(x_pos, 0.0, zc), x_dir=(0.0, 1.0, 0.0), z_dir=(1.0, 0.0, 0.0))
            with BuildSketch(p):
                Ellipse(wy * 0.5, hz * 0.5)
        loft()
    part = part + horn.part

    # Rounded tip balls at horn ends so tips are smooth & rope-safe
    for sign in (-1.0, 1.0):
        part = part + Pos(sign * 0.112, 0.0, horn_z + 0.004) * Sphere(radius=0.0052)

    # 2 countersunk heavy stud recesses between/outside legs
    for sx in (-0.048, 0.048):
        for sy in (-0.014, 0.014):
            part = part - Pos(sx, sy, base_h - 0.0015) * Cylinder(radius=0.0046, height=0.005)

    # Guarantee flat ground plane Z >= 0
    part = part - Pos(0.0, 0.0, -0.025) * Box(0.5, 0.5, 0.05)
    return part


def build_steering_wheel():
    """370 mm 5-spoke dished stainless offshore destroyer wheel + Edson power knob (shaft axis = +Y)."""
    rim_major_r = 0.176
    rim_minor_r = 0.0135
    dish_y = -0.052  # dished aft toward helmsman (-Y)

    # Single revolved/unioned hub assembly with generous overlap (zero internal coplanar faces!)
    collar = Pos(0.0, 0.022, 0.0) * Rot(90, 0, 0) * Cone(bottom_radius=0.036, top_radius=0.028, height=0.038)
    hub = Pos(0.0, -0.004, 0.0) * Rot(90, 0, 0) * Cylinder(radius=0.034, height=0.042)
    cap_dome = Pos(0.0, -0.022, 0.0) * Sphere(radius=0.028)
    rim = Pos(0.0, dish_y, 0.0) * Rot(90, 0, 0) * Torus(major_radius=rim_major_r, minor_radius=rim_minor_r)

    wheel = collar + hub + cap_dome + rim

    # 5 tapered round stainless destroyer spokes penetrating 6 mm into hub & rim (100% single solid!)
    for i in range(5):
        ang = math.radians(90.0 + i * 72.0)
        dx, dz = math.cos(ang), math.sin(ang)
        r0, r1 = 0.018, rim_major_r + 0.006
        y0, y1 = -0.006, dish_y
        vec = ((r1 - r0) * dx, y1 - y0, (r1 - r0) * dz)
        spoke_len = math.sqrt(sum(c * c for c in vec))
        z_unit = tuple(c / spoke_len for c in vec)
        x_dir = (-dz, 0.0, dx)
        p0 = (r0 * dx, y0, r0 * dz)
        plane = Plane(origin=p0, x_dir=x_dir, z_dir=z_unit)
        with BuildPart() as sp:
            with BuildSketch(plane):
                Circle(0.0095)
            with BuildSketch(plane.offset(spoke_len)):
                Circle(0.0072)
            loft()
        wheel = wheel + sp.part

    # Ergonomic Edson-style maneuvering power knob at 54 deg (single unioned solid!)
    knob_ang = math.radians(54.0)
    kx = rim_major_r * math.cos(knob_ang)
    kz = rim_major_r * math.sin(knob_ang)
    knob_strap = Pos(kx, dish_y, kz) * Rot(90, 0, 0) * Cylinder(radius=0.0185, height=0.028)
    knob_neck = Pos(kx, dish_y - 0.018, kz) * Rot(90, 0, 0) * Cone(bottom_radius=0.015, top_radius=0.010, height=0.028)
    knob_body = Pos(kx, dish_y - 0.036, kz) * Rot(90, 0, 0) * Cone(bottom_radius=0.023, top_radius=0.012, height=0.028)
    knob_crown = Pos(kx, dish_y - 0.046, kz) * Sphere(radius=0.021)
    knob = knob_strap + knob_neck + knob_body + knob_crown

    return wheel + knob


def build_throttle_binnacle():
    """Top-mount single-lever marine binnacle control (stalk on port side, ergonomic T-grip extending +X over body)."""
    # 1. Separate clean BuildParts for base flange & domed mechanism housing (avoids multi-loft pending_face bugs!)
    with BuildPart() as flange:
        with BuildSketch(Plane.XY):
            RectangleRounded(0.098, 0.182, radius=0.030)
        with BuildSketch(Plane.XY.offset(0.022)):
            RectangleRounded(0.088, 0.164, radius=0.026)
        loft()

    with BuildPart() as dome:
        with BuildSketch(Plane.XY.offset(0.014)):
            with Locations((0.006, -0.004)):
                RectangleRounded(0.060, 0.120, radius=0.024)
        with BuildSketch(Plane.XY.offset(0.072)):
            with Locations((0.006, -0.008)):
                RectangleRounded(0.048, 0.084, radius=0.020)
        loft()

    part = flange.part + dome.part

    # 2. Drum pivot turret on port (-X) side of housing
    drum = Pos(-0.018, -0.006, 0.052) * Rot(0, 90, 0) * Cylinder(radius=0.029, height=0.048)
    drum_cap = Pos(-0.040, -0.006, 0.052) * Rot(0, 90, 0) * Cone(bottom_radius=0.020, top_radius=0.027, height=0.016)
    part = part + drum + drum_cap

    # 3. Slightly forward-tilted (+10 deg) chrome stalk rising cleanly on port side (-X = -0.036)
    tilt_rad = math.radians(10.0)
    arm_len = 0.128
    arm_origin = (-0.036, -0.006, 0.052)
    arm_plane = Plane(
        origin=arm_origin,
        x_dir=(1.0, 0.0, 0.0),
        z_dir=(0.0, math.sin(tilt_rad), math.cos(tilt_rad)),
    )
    with BuildPart() as stalk:
        with BuildSketch(arm_plane):
            RectangleRounded(0.013, 0.028, radius=0.005)
        with BuildSketch(arm_plane.offset(arm_len + 0.004)):
            RectangleRounded(0.011, 0.020, radius=0.004)
        loft()
    part = part + stalk.part

    # 4. Ergonomic horizontal T-grip extending INWARD (+X) right over the binnacle housing!
    gy = -0.006 + arm_len * math.sin(tilt_rad)
    gz = 0.052 + arm_len * math.cos(tilt_rad)
    grip = Pos(0.004, gy, gz) * Rot(0, 90, 0) * Cylinder(radius=0.016, height=0.098)
    trim_rocker = Pos(-0.040, gy + 0.008, gz) * Box(0.014, 0.015, 0.020)
    part = part + grip + trim_rocker

    return part - Pos(0.0, 0.0, -0.025) * Box(0.5, 0.5, 0.05)


def build_outboard_prop():
    """408 mm (16") 3-blade wide-ear Saltwater Series II offshore stainless propeller (axis = Y).

    Large, unmistakable 3-blade silhouette with progressive pitch, aft rake, and wide rounded blades.
    """
    # Through-hub exhaust barrel along Y: front = +0.095, aft = -0.105
    hub_front = Pos(0.0, 0.032, 0.0) * Rot(90, 0, 0) * Cone(bottom_radius=0.054, top_radius=0.062, height=0.126)
    hub_mid = Pos(0.0, -0.055, 0.0) * Rot(90, 0, 0) * Cylinder(radius=0.053, height=0.058)
    # Flared exhaust diffuser lip at aft (-Y) end
    diffuser = Pos(0.0, -0.092, 0.0) * Rot(90, 0, 0) * Cone(bottom_radius=0.062, top_radius=0.053, height=0.024)
    # Recessed bore at aft end so exhaust hub looks authentic & hollow-rimmed (closed watertight inside!)
    exhaust_cavity = Pos(0.0, -0.088, 0.0) * Rot(90, 0, 0) * Cylinder(radius=0.043, height=0.045)
    shaft_nut = Pos(0.0, -0.068, 0.0) * Rot(90, 0, 0) * Cone(bottom_radius=0.016, top_radius=0.026, height=0.052)

    hub_solid = (hub_front + hub_mid + diffuser) - exhaust_cavity + shaft_nut

    # Radial stations: (r_span, pitch_deg, chord_m, thick_m, skew_tangential_m, aft_rake_m)
    # Full 204 mm radius (408 mm / 16.1" diameter) wide-ear offshore 3-blade geometry!
    stations = [
        (0.042, 34.0, 0.102, 0.0145, 0.000, 0.008),
        (0.074, 30.0, 0.142, 0.0115, -0.010, -0.004),
        (0.110, 26.0, 0.172, 0.0092, -0.026, -0.016),
        (0.146, 22.5, 0.176, 0.0076, -0.046, -0.028),
        (0.176, 19.8, 0.148, 0.0062, -0.064, -0.038),
        (0.194, 18.2, 0.102, 0.0050, -0.075, -0.044),
        (0.204, 17.2, 0.054, 0.0038, -0.082, -0.048),
    ]

    for b_idx in range(3):
        ang = math.radians(b_idx * 120.0)
        rx0, rz0 = math.cos(ang), math.sin(ang)
        tx0, tz0 = -math.sin(ang), math.cos(ang)
        root_plane = Plane(origin=(0.0, 0.0, 0.0), x_dir=(tx0, 0.0, tz0), z_dir=(rx0, 0.0, rz0))
        faces = []
        for r, pitch_deg, chord, thick, skew_t, rake_y in stations:
            with BuildSketch(root_plane.offset(r)) as sk:
                with Locations((skew_t, rake_y)):
                    with Locations(Rot(0, 0, pitch_deg)):
                        RectangleRounded(chord, thick, radius=thick * 0.46)
            faces.append(sk.sketch.face())
        blade_solid = loft(faces)
        hub_solid = hub_solid + blade_solid

    return hub_solid


def build_rocket_launcher():
    """1.22 m wide T-Top aft 5-tube tulip-flared offshore rod holder bar."""
    bar_w = 1.220
    tube_r = 0.025
    tube_len = 0.245

    # Curved/straight main heavy crossbar along X
    main_bar = Rot(0, 90, 0) * Cylinder(radius=0.019, height=bar_w)
    end_l = Pos(-bar_w * 0.5, 0.0, 0.0) * Sphere(radius=0.019)
    end_r = Pos(bar_w * 0.5, 0.0, 0.0) * Sphere(radius=0.019)
    launcher = main_bar + end_l + end_r

    # Twin heavy mounting stanchions + 4-bolt oval mounting pads (embed cleanly into T-top canopy)
    for sx in (-0.44, 0.44):
        stanchion = Pos(sx, 0.015, -0.030) * Rot(-18, 0, 0) * Cylinder(radius=0.015, height=0.068)
        pad = Pos(sx, 0.026, -0.060) * Box(0.068, 0.088, 0.014)
        launcher = launcher + stanchion + pad

    # 5 tulip-flared offshore rod holder tubes tilted 22 deg aft (-Y)
    tube_xs = [-0.52, -0.26, 0.0, 0.26, 0.52]
    tilt = math.radians(22.0)
    tube_dir = (0.0, -math.sin(tilt), math.cos(tilt))

    parts = [launcher]
    for tx in tube_xs:
        p = Plane(origin=(tx, -0.010, -0.022), x_dir=(1.0, 0.0, 0.0), z_dir=tube_dir)
        with BuildPart(p) as holder:
            # Main outer barrel
            Cylinder(radius=tube_r, height=tube_len - 0.024, align=(Align.CENTER, Align.CENTER, Align.MIN))
            # Flared tulip bell mouth at top
            with Locations((0.0, 0.0, tube_len - 0.026)):
                Cone(
                    bottom_radius=tube_r,
                    top_radius=tube_r + 0.007,
                    height=0.028,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                )
            # Rolled upper lip torus
            with Locations((0.0, 0.0, tube_len + 0.001)):
                Torus(major_radius=tube_r + 0.004, minor_radius=0.0035)
            # Welded fin gusset connecting barrel forward (+Y in world = -local Y) to crossbar
            with Locations((0.0, 0.018, 0.045)):
                Box(0.008, 0.028, 0.065)
            # Hollow bore upper 72% (closed watertight bottom with gimbal cross-bar look)
            with Locations((0.0, 0.0, tube_len + 0.010)):
                Cylinder(
                    radius=tube_r - 0.0055,
                    height=tube_len * 0.74,
                    align=(Align.CENTER, Align.CENTER, Align.MAX),
                    mode=Mode.SUBTRACT,
                )
        parts.append(holder.part)

    return Compound(children=parts)


SPECS = [
    ("deck_cleat", build_deck_cleat, 1100, (0.86, 0.89, 0.92, 1.0), 0.94, 0.16),
    ("steering_wheel", build_steering_wheel, 2800, (0.86, 0.89, 0.92, 1.0), 0.94, 0.16),
    ("throttle_binnacle", build_throttle_binnacle, 1600, (0.83, 0.86, 0.90, 1.0), 0.92, 0.18),
    ("outboard_prop", build_outboard_prop, 2800, (0.88, 0.90, 0.93, 1.0), 0.96, 0.13),
    ("rocket_launcher", build_rocket_launcher, 3000, (0.86, 0.89, 0.92, 1.0), 0.94, 0.16),
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
            linear_deflection=0.0015,
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

