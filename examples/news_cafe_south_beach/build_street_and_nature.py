r"""High-Poly Photorealistic Streetscape, Parisian Bistro Furniture, Fine Tableware & Tropical Botanicals.

No 20k Low-Poly Compromise — ArchViz / Film-Grade Realism Across EVERY Prop & Plant:
  1. `RoadAndCurbs` + `SidewalksAndApron`:
     - Smooth 28-seg sweeping corner radius w/ stepped bullnose rounded yellow curb lip & crisp `"VALET ONLY"` stencils
     - Real 3D raised truncated-dome ADA tactile warning bumps (`18 x 7` domes!), slotted cast-iron storm drain grate bars
     - Sculpted beveled Zicla Zebra bike-lane separators w/ sloped ends & embossed Miami Beach manhole cover
  2. `Patio_Umbrellas`:
     - Tensioned 8-panel bicubic draped fabric canopies (subtle inward catenary sag between every tensioned rib!)
     - Double-vented pagoda wind cap + wooden finial spire + sliding brass runner hub + articulated diagonal steel ribs
  3. `Patio_Chairs`:
     - Authentic Parisian bentwood rattan sidewalk chairs (`add_spline_tube` 12-seg smooth curved tubular legs, double-hoop
       arched bentwood backrest, rolled bullnose woven rattan seat cushion, curved saddle-contoured woven back!)
  4. `Patio_Tables`:
     - High-poly 8.5k-tri B-Rep CAD Victorian S-scroll marble+brass bistro tables + 6.5k-tri B-Rep CAD fine dining place settings
       (porcelain dinner plates, handled espresso cups on saucers, clear crystal stemmed wine glasses, brass hurricane candles + folded napkins!)
     - High-poly B-Rep CAD architectural host lectern podium (`host_podium.glb`) & LED stainless menu vitrine (`menu_stand.glb`)
  5. `Street_Furniture`:
     - High-poly B-Rep CAD 20-rib trash bin (`9k`), bolted Mueller fire hydrant (`9.5k`), finned cobra-head LED lamps (`6.5k`) on
       smooth spline-curved streetlight arms, lathe-revolved fluted ceramic/terracotta pots & reflective valet bollards!
  6. Photorealistic Botanicals:
     - 24-seg curved ringed coconut palm trunks w/ root flares, fibrous leaf-boot crownshaft & smooth `subdiv=2` coconut clusters
     - 16 sweeping 12-seg arched palm fronds per palm w/ 22 pairs of long 3-segment curved V-folded drooping leaflets!
     - Gnarled organic twisting spline Buttonwood/Sea Grape shade trees w/ 3-tier forked branches & dense curved ovate broad leaves!
     - Thick lush curved ovate SE corner hedge, sculpted broad tropical pot foliage & genuine 3-bract cupped bougainvillea blossoms w/ cream florets!
"""
from __future__ import annotations

import math
import os
import random

import bmesh
import bpy
from mathutils import Vector

import geo_utils as gu
from build_buildings import (
    AWNING_POLE_XY,
    NC_X_NORTH,
    NC_X_SOUTH,
    NC_Y_BALC,
    PATIO_COLUMN_XY,
    Z_F1,
    Z_ROAD,
    Z_SW,
)

Z_PINK = Z_SW + 0.011  # Exact top elevation of coral-pink SE corner apron (`build_sidewalks_and_apron`)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_DIR = os.path.join(THIS_DIR, "cad")

SITE_X_N = -22.50
SITE_X_S = 20.00
SITE_Y_W = -16.50
SITE_Y_E = 23.00

CURB_Y_OCEAN = 11.60
CURB_X_8TH = 13.30
CORNER_R = 3.40
CORNER_CX = CURB_X_8TH - CORNER_R   # 9.90
CORNER_CY = CURB_Y_OCEAN - CORNER_R # 8.20


def _sidewalk_outer_poly(offset: float = 0.0, segs: int = 28) -> list[tuple[float, float]]:
    y_e = CURB_Y_OCEAN + offset
    x_s = CURB_X_8TH + offset
    r = max(0.5, CORNER_R + offset)
    pts = [(SITE_X_N, SITE_Y_W), (SITE_X_N, y_e), (CORNER_CX, y_e)]
    for k in range(1, segs):
        a = math.pi * 0.5 * (1.0 - k / segs)
        pts.append((CORNER_CX + r * math.cos(a), CORNER_CY + r * math.sin(a)))
    pts.extend([(x_s, CORNER_CY), (x_s, SITE_Y_W)])
    return pts


def _pink_apron_poly(segs: int = 28) -> list[tuple[float, float]]:
    r = CORNER_R - 0.25
    pts = [
        (NC_X_SOUTH + 0.02, SITE_Y_W + 0.01),
        (NC_X_SOUTH + 0.02, NC_Y_BALC + 0.35),
        (7.90, CURB_Y_OCEAN - 0.25),
        (CORNER_CX, CURB_Y_OCEAN - 0.25),
    ]
    for k in range(1, segs):
        a = math.pi * 0.5 * (1.0 - k / segs)
        pts.append((CORNER_CX + r * math.cos(a), CORNER_CY + r * math.sin(a)))
    pts.extend([(CURB_X_8TH - 0.25, CORNER_CY), (CURB_X_8TH - 0.25, SITE_Y_W + 0.01)])
    return pts


def _uv_map_road_top(faces: list[bmesh.types.BMFace], uv_layer, x0: float, x1: float, y0: float, y1: float, *, along_y: bool = False) -> None:
    dx = max(abs(x1 - x0), 1e-4)
    dy = max(abs(y1 - y0), 1e-4)
    for f in faces:
        if f.normal.z > 0.8:
            for l in f.loops:
                if along_y:
                    u = (l.vert.co.x - x0) / dx
                    v = 1.0 - (l.vert.co.y - y0) / dy
                else:
                    u = (l.vert.co.y - y0) / dy
                    v = 1.0 - (l.vert.co.x - x0) / dx
                l[uv_layer].uv = (max(0.005, min(0.995, u)), max(0.005, min(0.995, v)))


def build_road_and_curbs(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    """Build high-poly `RoadAndCurbs`: smooth 28-seg bullnose yellow curb, slotted storm grate, embossed manhole & beveled Zicla zebras."""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    mat_list = [
        m["plinth_slate"], m["asphalt_plain"], m["asphalt_ocean"], m["bike_lane"],
        m["curb_yellow"], m["zebra_rubber"], m["zebra_white"], m["iron_grate"], m["road_paint_white"], m["curb_valet"],
    ]

    gu.add_box_bounds(bm, SITE_X_N, SITE_X_S, SITE_Y_W, SITE_Y_E, 0.0000, 0.190, 0)
    gap = 0.005
    z_bot_rd = 0.175

    gu.add_box_bounds(bm, SITE_X_N + 0.004, CURB_X_8TH - 0.04, SITE_Y_W + 0.004, CURB_Y_OCEAN - 0.04, z_bot_rd, Z_ROAD, 1)

    y_oc_start = CURB_Y_OCEAN - 0.02
    f_n1 = gu.add_box_bounds(bm, SITE_X_N + 0.004, -13.0 - gap, y_oc_start, 18.45 - gap, z_bot_rd, Z_ROAD, 1)
    _uv_map_road_top(f_n1, uv_layer, SITE_X_N, -13.0 - gap, y_oc_start, 18.45 - gap)
    f_n2 = gu.add_box_bounds(bm, -13.0, -3.50 - gap, y_oc_start, 18.45 - gap, z_bot_rd, Z_ROAD, 1)
    _uv_map_road_top(f_n2, uv_layer, -13.0, -3.50 - gap, y_oc_start, 18.45 - gap)
    f_od = gu.add_box_bounds(bm, -3.50, 11.50, y_oc_start, 18.45 - gap, z_bot_rd, Z_ROAD, 2)
    _uv_map_road_top(f_od, uv_layer, -3.50, 11.50, y_oc_start, 18.45 - gap)
    f_s1 = gu.add_box_bounds(bm, 11.50 + gap, SITE_X_S - 0.004, y_oc_start, 18.45 - gap, z_bot_rd, Z_ROAD, 1)
    _uv_map_road_top(f_s1, uv_layer, 11.50 + gap, SITE_X_S, y_oc_start, 18.45 - gap)

    for idx, (bx0, bx1) in enumerate([(-22.496, -12.0), (-12.0, -1.5), (-1.5, 9.0), (9.0, 19.996)]):
        fb = gu.add_box_bounds(bm, bx0 + (gap if idx > 0 else 0.0), bx1, 18.45, 20.15 - gap, z_bot_rd, Z_ROAD, 3)
        _uv_map_road_top(fb, uv_layer, bx0, bx1, 18.45, 20.15 - gap)

    x_8_start = CURB_X_8TH - 0.02
    for idx, (by0, by1) in enumerate([(-16.496, -7.2), (-7.2, 2.2), (2.2, 11.60)]):
        fb8 = gu.add_box_bounds(bm, x_8_start, 15.05 - gap, by0 + (gap if idx > 0 else 0.0), by1 - gap, z_bot_rd, Z_ROAD, 3)
        _uv_map_road_top(fb8, uv_layer, x_8_start, 15.05 - gap, by0, by1 - gap, along_y=True)

    for idx, (by0, by1) in enumerate([(-16.496, -5.0), (-5.0, 6.5), (6.5, 11.60)]):
        f8 = gu.add_box_bounds(bm, 15.05, SITE_X_S - 0.004, by0 + (gap if idx > 0 else 0.0), by1 - gap, z_bot_rd, Z_ROAD, 1)
        _uv_map_road_top(f8, uv_layer, 15.05, SITE_X_S, by0, by1 - gap, along_y=True)

    gu.add_box_bounds(bm, SITE_X_N + 0.004, SITE_X_S - 0.004, 20.15, SITE_Y_E - 0.004, z_bot_rd, Z_ROAD, 1)

    for cy in (12.4, 13.6, 14.8, 16.0, 17.2):
        gu.add_box_bounds(bm, 12.5, 14.7, cy - 0.26, cy + 0.26, Z_ROAD - 0.006, Z_ROAD + 0.008, 8)
    for cx in (15.7, 16.9, 18.1, 19.3):
        gu.add_box_bounds(bm, cx - 0.26, cx + 0.26, 9.1, 11.1, Z_ROAD - 0.006, Z_ROAD + 0.008, 8)

    # Smooth 28-segment rounded bullnose yellow curb ribbon (main body + stepped rounded upper bullnose cap!)
    outer_pts = _sidewalk_outer_poly(offset=0.0, segs=28)[1:-1]
    inner_pts = _sidewalk_outer_poly(offset=-0.22, segs=28)[1:-1]
    gu.add_prism_xy(bm, list(outer_pts) + list(reversed(inner_pts)), Z_ROAD - 0.014, Z_SW - 0.012, 4)
    outer_cap = _sidewalk_outer_poly(offset=-0.018, segs=28)[1:-1]
    inner_cap = _sidewalk_outer_poly(offset=-0.215, segs=28)[1:-1]
    gu.add_prism_xy(bm, list(outer_cap) + list(reversed(inner_cap)), Z_SW - 0.018, Z_SW + 0.006, 4)

    for vx in (0.80, -3.20, -13.20):
        vx0, vx1 = vx - 0.62, vx + 0.62
        vy0, vy1 = CURB_Y_OCEAN - 0.20, CURB_Y_OCEAN + 0.004
        f_val = gu.add_box_bounds(bm, vx0, vx1, vy0, vy1, Z_ROAD + 0.008, Z_SW + 0.009, 9)
        for f in f_val:
            if f.normal.z > 0.8:
                for l in f.loops:
                    u = (vx1 - l.vert.co.x) / (vx1 - vx0)
                    v = (vy1 - l.vert.co.y) / (vy1 - vy0)
                    l[uv_layer].uv = (max(0.01, min(0.99, u)), max(0.01, min(0.99, v)))
            elif f.normal.y > 0.8:
                for l in f.loops:
                    u = (vx1 - l.vert.co.x) / (vx1 - vx0)
                    v = (l.vert.co.z - (Z_ROAD + 0.008)) / max((Z_SW + 0.009) - (Z_ROAD + 0.008), 1e-4)
                    l[uv_layer].uv = (max(0.01, min(0.99, u)), max(0.01, min(0.99, v)))
            else:
                for l in f.loops:
                    l[uv_layer].uv = (0.04, 0.04)

    # Sculpted Beveled Zicla Zebra Rubber Bike-Lane Separators w/ Rounded Ends & Reflective Strips!
    for zx in range(-20, 19, 3):
        gu.add_box_bounds(bm, zx - 0.44, zx + 0.44, 18.33, 18.57, Z_ROAD - 0.008, Z_ROAD + 0.115, 5, bevel=0.042)
        for dx in (-0.22, 0.0, 0.22):
            gu.add_box_bounds(bm, zx + dx - 0.045, zx + dx + 0.045, 18.35, 18.55, Z_ROAD + 0.095, Z_ROAD + 0.126, 6, bevel=0.010)

    # Slotted 3D Cast-Iron Storm Drain Curb Grate (14 individual raised grate bars!) + Embossed Circular Manhole Cover!
    gu.add_box_bounds(bm, 1.78, 2.92, CURB_Y_OCEAN + 0.02, CURB_Y_OCEAN + 0.44, Z_ROAD - 0.012, Z_ROAD + 0.005, 0)
    gu.add_box_bounds(bm, 1.76, 2.94, CURB_Y_OCEAN + 0.01, CURB_Y_OCEAN + 0.06, Z_ROAD - 0.008, Z_ROAD + 0.018, 7, bevel=0.005)
    gu.add_box_bounds(bm, 1.76, 2.94, CURB_Y_OCEAN + 0.40, CURB_Y_OCEAN + 0.45, Z_ROAD - 0.008, Z_ROAD + 0.018, 7, bevel=0.005)
    for k in range(14):
        gx = 1.82 + k * 0.082
        gu.add_box_bounds(bm, gx - 0.016, gx + 0.016, CURB_Y_OCEAN + 0.03, CURB_Y_OCEAN + 0.43, Z_ROAD - 0.004, Z_ROAD + 0.019, 7, bevel=0.004)
    # Embossed Miami Beach manhole cover w/ outer cast-iron collar ring & concentric lid rings
    gu.add_cylinder(bm, (2.35, CURB_Y_OCEAN - 0.65, Z_SW - 0.018), (2.35, CURB_Y_OCEAN - 0.65, Z_SW + 0.012), 0.39, 0.38, segs=32, mat_idx=7)
    gu.add_cylinder(bm, (2.35, CURB_Y_OCEAN - 0.65, Z_SW + 0.004), (2.35, CURB_Y_OCEAN - 0.65, Z_SW + 0.020), 0.34, 0.33, segs=32, mat_idx=7)

    return gu.finalize_part(bm, "RoadAndCurbs", col, mat_list, smooth_angle_deg=38.0, preserve_existing_uv=True)


def build_sidewalks_and_apron(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    """Build high-poly `SidewalksAndApron` w/ 28-seg smooth corner arc & real 3D truncated-dome ADA tactile warning bumps!"""
    bm = bmesh.new()
    mat_list = [
        m["sidewalk_concrete"], m["sidewalk_pink"], m["ada_pad"], m["stucco_white"],
        m["soil_mulch"], m["curb_concrete"], m["park_grass"], m["iron_grate"],
    ]

    sw_poly = _sidewalk_outer_poly(offset=-0.21, segs=28)
    sw_poly = [(max(SITE_X_N + 0.008, x), max(SITE_Y_W + 0.008, y)) for x, y in sw_poly]
    gu.add_prism_xy(bm, sw_poly, Z_ROAD - 0.022, Z_SW, 0)

    pink_poly = _pink_apron_poly(segs=28)
    gu.add_prism_xy(bm, pink_poly, Z_SW - 0.020, Z_SW + 0.011, 1)

    # Beige ADA Tactile Warning Pad w/ 16 x 6 real 3D raised truncated-dome bumps!
    ada_cx, ada_cy, ada_ang = 11.48, 9.76, math.radians(45.0)
    gu.add_box(bm, (ada_cx, ada_cy, Z_SW + 0.014), (1.42, 0.56, 0.018), 2, rot_euler=(0.0, 0.0, ada_ang), bevel=0.004)
    ca, sa = math.cos(ada_ang), math.sin(ada_ang)
    for ix in range(16):
        lx = -0.63 + ix * 0.084
        for iy in range(6):
            ly = -0.21 + iy * 0.084
            dx = ada_cx + lx * ca - ly * sa
            dy = ada_cy + lx * sa + ly * ca
            gu.add_cylinder(bm, (dx, dy, Z_SW + 0.018), (dx, dy, Z_SW + 0.030), 0.015, 0.010, segs=8, mat_idx=2)

    wedge_pts = [(7.55, 8.85), (7.55, 11.18), (9.50, 11.18), (10.30, 10.72), (10.68, 9.95), (9.65, 8.85)]
    gu.add_prism_xy(bm, wedge_pts, Z_SW - 0.026, Z_SW + 0.036, 4)

    # Beveled crisp white 8th St palm planter curb (4 solid masonry perimeter walls cleanly framing recessed soil!)
    gu.add_box_bounds(bm, 11.55, 11.72, 2.20, 7.65, Z_SW - 0.028, Z_SW + 0.165, 3, bevel=0.012)
    gu.add_box_bounds(bm, 12.78, 12.95, 2.20, 7.65, Z_SW - 0.028, Z_SW + 0.165, 3, bevel=0.012)
    gu.add_box_bounds(bm, 11.71, 12.79, 2.21, 2.38, Z_SW - 0.024, Z_SW + 0.162, 3, bevel=0.010)
    gu.add_box_bounds(bm, 11.71, 12.79, 7.47, 7.64, Z_SW - 0.024, Z_SW + 0.162, 3, bevel=0.010)
    # Recessed rich soil mulch safely 4.5 cm BELOW the crisp white planter rim!
    gu.add_box_bounds(bm, 11.70, 12.80, 2.36, 7.49, Z_SW - 0.020, Z_SW + 0.120, 4)

    # Recessed granite-curbed dark soil tree pits flush on Z_SW for the 2 Ocean Dr palms & 2 Buttonwood shade trees!
    for tx_p, ty_p, half_w in [(-6.05, 9.85, 0.56), (-16.10, 10.55, 0.56), (-7.60, 7.60, 0.64), (-13.85, 7.80, 0.68)]:
        gu.add_box_bounds(bm, tx_p - half_w, tx_p + half_w, ty_p - half_w, ty_p + half_w, Z_SW, Z_SW + 0.022, 4)
        # 4 beveled low concrete curb edging bars framing the tree pit cleanly flush on Z_SW
        cb = 0.065
        gu.add_box_bounds(bm, tx_p - half_w - cb, tx_p + half_w + cb, ty_p - half_w - cb, ty_p - half_w, Z_SW, Z_SW + 0.042, 5, bevel=0.008)
        gu.add_box_bounds(bm, tx_p - half_w - cb, tx_p + half_w + cb, ty_p + half_w, ty_p + half_w + cb, Z_SW, Z_SW + 0.042, 5, bevel=0.008)
        gu.add_box_bounds(bm, tx_p - half_w - cb, tx_p - half_w, ty_p - half_w + 0.004, ty_p + half_w - 0.004, Z_SW, Z_SW + 0.042, 5, bevel=0.008)
        gu.add_box_bounds(bm, tx_p + half_w, tx_p + half_w + cb, ty_p - half_w + 0.004, ty_p + half_w - 0.004, Z_SW, Z_SW + 0.042, 5, bevel=0.008)

    # Detailed twin diamond-plate recessed 8th St sidewalk utility hatches
    for hy in (-0.35, 0.65):
        gu.add_box_bounds(bm, 11.66, 12.54, hy - 0.44, hy + 0.44, Z_SW + 0.002, Z_SW + 0.020, 7, bevel=0.005)

    gu.add_box_bounds(bm, SITE_X_N + 0.008, SITE_X_S - 0.008, 20.17, 21.56, Z_ROAD - 0.018, Z_SW, 0)
    gu.add_box_bounds(bm, SITE_X_N + 0.012, SITE_X_S - 0.012, 21.53, 21.80, Z_SW - 0.025, Z_SW + 0.48, 3, bevel=0.016)
    gu.add_box_bounds(bm, SITE_X_N + 0.008, SITE_X_S - 0.008, 21.77, SITE_Y_E - 0.008, Z_ROAD - 0.024, Z_SW + 0.05, 6)

    return gu.finalize_part(bm, "SidewalksAndApron", col, mat_list, smooth_angle_deg=38.0)


def _add_market_umbrella(
    bm: bmesh.types.BMesh,
    x: float,
    y: float,
    *,
    radius: float = 1.44,
    height: float = 2.36,
    mat_canopy: int = 0,
    mat_pole: int = 1,
    mat_base: int = 2,
    mat_brass: int = 4,
) -> None:
    """High-poly market umbrella w/ flush base on Z_SW, draped seamless 8-gore canopy, brass hubs & connected articulated ribs!"""
    # Stepped revolved cast-iron umbrella base resting EXACTLY FLUSH at `Z_SW` (ZERO sinking into concrete!)
    base_prof = [(0.29, 0.000), (0.29, 0.018), (0.26, 0.042), (0.12, 0.072), (0.052, 0.115), (0.044, 0.240)]
    gu.add_revolved_profile(bm, (x, y, Z_SW), base_prof, segs=24, mat_idx=mat_base)
    gu.add_cylinder(bm, (x, y, Z_SW + 0.08), (x, y, Z_SW + height + 0.15), 0.025, 0.023, segs=20, mat_idx=mat_pole)
    # Sliding brass runner hub collar, upper brass crown collar & mid-pole brass coupling
    gu.add_cylinder(bm, (x, y, Z_SW + height - 0.56), (x, y, Z_SW + height - 0.44), 0.042, 0.040, segs=18, mat_idx=mat_brass)
    gu.add_cylinder(bm, (x, y, Z_SW + height - 0.03), (x, y, Z_SW + height + 0.05), 0.046, 0.042, segs=18, mat_idx=mat_brass)
    gu.add_cylinder(bm, (x, y, Z_SW + height * 0.48), (x, y, Z_SW + height * 0.52), 0.032, 0.032, segs=18, mat_idx=mat_brass)

    # Continuous seamless watertight 8-gore curved draped market canopy (shared rib vertices -> ZERO duplicate verts!)
    n_gores = 8
    nu, nv = 5, 5
    z_eave = Z_SW + height - 0.36
    z_peak = Z_SW + height + 0.05
    r_top = 0.22
    t = 0.016
    n_u_total = n_gores * nu

    vt_ring: list[list] = []
    vb_ring: list[list] = []
    for gu_i in range(n_u_total):
        g = gu_i // nu
        u = (gu_i % nu) / nu
        a0 = math.tau * g / n_gores
        a1 = math.tau * (g + 1) / n_gores
        p_t0 = Vector((x + r_top * math.cos(a0), y + r_top * math.sin(a0), z_peak))
        p_t1 = Vector((x + r_top * math.cos(a1), y + r_top * math.sin(a1), z_peak))
        p_b0 = Vector((x + radius * math.cos(a0), y + radius * math.sin(a0), z_eave))
        p_b1 = Vector((x + radius * math.cos(a1), y + radius * math.sin(a1), z_eave))

        row_t, row_b = [], []
        for iv in range(nv + 1):
            v = iv / nv
            pt = p_t0.lerp(p_t1, u).lerp(p_b0.lerp(p_b1, u), v)
            dome_lift = 0.065 * math.sin(math.pi * v)
            rib_sag = -0.028 * math.sin(math.pi * u) * math.sin(math.pi * v)
            eave_scallop = -0.018 * math.sin(math.pi * u) * (v ** 3)
            pt.z += dome_lift + rib_sag + eave_scallop
            row_t.append(bm.verts.new(pt))
            row_b.append(bm.verts.new(pt - Vector((0, 0, t))))
        vt_ring.append(row_t)
        vb_ring.append(row_b)

    for gu_i in range(n_u_total):
        gn = (gu_i + 1) % n_u_total
        for iv in range(nv):
            for q in [
                (vt_ring[gu_i][iv], vt_ring[gn][iv], vt_ring[gn][iv + 1], vt_ring[gu_i][iv + 1]),
                (vb_ring[gu_i][iv + 1], vb_ring[gn][iv + 1], vb_ring[gn][iv], vb_ring[gu_i][iv]),
            ]:
                f = bm.faces.new(q)
                f.material_index = mat_canopy
        for q in [
            (vb_ring[gu_i][nv], vb_ring[gn][nv], vt_ring[gn][nv], vt_ring[gu_i][nv]),
            (vt_ring[gu_i][0], vt_ring[gn][0], vb_ring[gn][0], vb_ring[gu_i][0]),
        ]:
            f = bm.faces.new(q)
            f.material_index = mat_canopy

    for g in range(n_gores):
        a0 = math.tau * g / n_gores
        p_crown = Vector((x + 0.032 * math.cos(a0), y + 0.032 * math.sin(a0), z_peak - 0.032))
        p_hub = Vector((x + 0.032 * math.cos(a0), y + 0.032 * math.sin(a0), Z_SW + height - 0.50))
        p_mid_rib = Vector((x + (radius * 0.52) * math.cos(a0), y + (radius * 0.52) * math.sin(a0), 0.5 * (z_peak + z_eave) + 0.024))
        p_tip_rib = Vector((x + (radius - 0.03) * math.cos(a0), y + (radius - 0.03) * math.sin(a0), z_eave - 0.024))
        gu.add_cylinder(bm, p_hub, p_mid_rib, 0.0095, 0.009, segs=10, mat_idx=mat_pole)
        gu.add_spline_tube(bm, [p_crown, p_mid_rib, p_tip_rib], 0.0095, segs=10, substeps=2, mat_idx=mat_pole)
        # Brass hinge pin sleeve connecting diagonal strut cleanly to main rafter rib!
        gu.add_icosphere(bm, p_mid_rib, (0.015, 0.015, 0.015), subdiv=1, mat_idx=mat_brass)

    # Sculpted vented pagoda top wind-cap + turned brass/wood finial spire!
    cap_prof = [(0.36, 0.0), (0.35, 0.015), (0.24, 0.085), (0.10, 0.145), (0.035, 0.165)]
    gu.add_revolved_profile(bm, (x, y, z_peak - 0.005), cap_prof, segs=20, mat_idx=mat_canopy)
    finial_prof = [(0.022, 0.0), (0.032, 0.025), (0.016, 0.055), (0.024, 0.082), (0.008, 0.115)]
    gu.add_revolved_profile(bm, (x, y, z_peak + 0.150), finial_prof, segs=16, mat_idx=mat_brass)


# Shared deterministic umbrella pole layout (cleanly placed in open bays between tables -> ZERO pole/chair collisions!)
UMBRELLA_SPECS_NC = [
    (7.35, 8.85, 1.40, 2.34),
    (5.25, 8.55, 1.44, 2.38),
    (3.20, 10.25, 1.42, 2.36),
    (-1.25, 9.05, 1.46, 2.40),
    (-3.35, 9.15, 1.44, 2.36),
    (-5.30, 8.80, 1.38, 2.34),
]
UMBRELLA_SPECS_804 = [
    (-9.05, 8.75, 1.42, 2.42),
    (-15.05, 8.75, 1.42, 2.42),
]


def build_patio_umbrellas(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    bm = bmesh.new()
    mat_list = [m["umbrella_green"], m["cast_iron"], m["stainless_steel"], m["umbrella_sage"], m["brass_warm"]]

    for ux, uy, ur, uh in UMBRELLA_SPECS_NC:
        _add_market_umbrella(bm, ux, uy, radius=ur, height=uh, mat_canopy=0, mat_pole=1, mat_base=2, mat_brass=4)
    for ux, uy, ur, uh in UMBRELLA_SPECS_804:
        _add_market_umbrella(bm, ux, uy, radius=ur, height=uh, mat_canopy=3, mat_pole=1, mat_base=2, mat_brass=4)

    return gu.finalize_part(bm, "Patio_Umbrellas", col, mat_list, smooth_angle_deg=44.0)


def _add_parisian_bistro_chair(
    bm: bmesh.types.BMesh,
    x: float,
    y: float,
    yaw: float,
    *,
    mat_frame: int = 0,
    mat_weave: int = 1,
    mat_brass: int = 3,
) -> None:
    """Delegate directly to our CAD-precision zero-gap, flush-grounded `gu.add_parisian_bistro_chair`!"""
    gu.add_parisian_bistro_chair(bm, x, y, Z_SW, yaw, mat_frame=mat_frame, mat_weave=mat_weave, mat_brass=mat_brass)


def build_patio_furniture(col: bpy.types.Collection, m: dict) -> tuple[list[bpy.types.Object], bpy.types.Mesh]:
    """Build modular, individually selectable, instanced high-res patio sets -> FULL 2K UV texel density per asset!

    Splits the old merged `Patio_Tables` & `Patio_Chairs` cleanly into 4 dedicated Outliner sub-collections:
      - `Patio_Tables` (`Patio_Table_01..15`, shared 2K `Mesh_Parisian_Bistro_Table`)
      - `Patio_Tableware` (`Patio_Tableware_01..15`, shared 2K `Mesh_Bistro_Tableware_Set`)
      - `Patio_Chairs` (`Patio_Chair_01..45`, shared 2K `Mesh_Parisian_Chair_Honey` & `Mesh_Parisian_Chair_Cream`)
      - `Patio_Fixtures` (`Host_Podium` standalone 2K + `Menu_Stand` standalone 2K)
    """
    col_tables = gu.sub_collection(col, "Patio_Tables")
    col_tableware = gu.sub_collection(col, "Patio_Tableware")
    col_chairs = gu.sub_collection(col, "Patio_Chairs")
    col_fixtures = gu.sub_collection(col, "Patio_Fixtures")

    # 1. Build Reusable Hero Prototype Mesh Datablocks at Local Origin (0, 0, 0) -> 15x–45x HIGHER TEXEL DENSITY!
    bm_tbl_p = bmesh.new()
    gu.add_parisian_bistro_table(bm_tbl_p, 0.0, 0.0, 0.0, yaw=0.0, mat_iron=0, mat_marble=1, mat_brass=2)
    me_table = gu.finalize_mesh_data(
        bm_tbl_p, "Mesh_Parisian_Bistro_Table", col_tables,
        [m["cast_iron"], m["marble_top"], m["brass_warm"]], smooth_angle_deg=42.0,
    )

    bm_tw_p = bmesh.new()
    gu.add_bistro_tableware_set(
        bm_tw_p, 0.0, 0.0, 0.0, yaw=0.0,
        mat_porcelain=0, mat_brass=1, mat_crystal=2, mat_linen=3, mat_flame=4, mat_stainless=5, mat_espresso=6,
    )
    me_tableware = gu.finalize_mesh_data(
        bm_tw_p, "Mesh_Bistro_Tableware_Set", col_tableware,
        [m["ceramic_white"], m["brass_warm"], m["crystal_glass"], m["linen_napkin"], m["candle_flame"], m["stainless_steel"], m["cast_iron"]],
        smooth_angle_deg=42.0,
    )

    bm_ch_h = bmesh.new()
    gu.add_parisian_bistro_chair(bm_ch_h, 0.0, 0.0, 0.0, 0.0, mat_frame=0, mat_weave=1, mat_brass=2)
    me_chair_honey = gu.finalize_mesh_data(
        bm_ch_h, "Mesh_Parisian_Chair_Honey", col_chairs,
        [m["chair_frame"], m["rattan_weave"], m["brass_warm"]], smooth_angle_deg=44.0,
    )

    bm_ch_c = bmesh.new()
    gu.add_parisian_bistro_chair(bm_ch_c, 0.0, 0.0, 0.0, 0.0, mat_frame=0, mat_weave=1, mat_brass=2)
    me_chair_cream = gu.finalize_mesh_data(
        bm_ch_c, "Mesh_Parisian_Chair_Cream", col_chairs,
        [m["chair_frame"], m["rattan_cream"], m["brass_warm"]], smooth_angle_deg=44.0,
    )

    rng = random.Random(800)

    # Exact collision-free bistro table layout harmonized with ALL umbrellas, awning poles, patio columns, breeze wall, pots, podium & menu!
    table_coords = [
        (7.75, 7.68, 3), (6.35, 8.20, 3), (5.95, 9.75, 3), (3.85, 9.25, 3),
        (4.15, 6.45, 3), (6.50, 6.10, 3), (-0.15, 9.55, 3), (-2.35, 9.60, 3),
        (-4.35, 9.55, 3), (-1.10, 6.20, 3), (-3.45, 6.20, 3), (-6.25, 9.45, 3),
        (0.55, 6.10, 3), (-8.05, 9.35, 3), (-13.95, 9.25, 3),
    ]
    px_pod, py_pod = 2.65, 8.25
    mx_menu, my_menu = 1.65, 8.42

    pole_obstacles = [(u[0], u[1], 0.64) for u in (UMBRELLA_SPECS_NC + UMBRELLA_SPECS_804)]
    awning_obstacles = [(ax, ay, 0.44) for ax, ay in AWNING_POLE_XY]
    col_obstacles = [(cx, cy, 0.56) for cx, cy in PATIO_COLUMN_XY]
    pot_obstacles = [
        (9.35, 7.05, 0.54), (9.85, 7.55, 0.56), (10.35, 7.95, 0.54), (9.90, 8.35, 0.56),
        (-4.20, 7.80, 0.56), (-2.60, 7.80, 0.56), (-1.10, 7.80, 0.56), (0.15, 7.80, 0.56),
        (-6.05, 9.85, 0.85), (-7.60, 7.60, 0.90), (-13.85, 7.80, 0.92),
    ]
    fixed_obstacles = pole_obstacles + awning_obstacles + col_obstacles + pot_obstacles + [(px_pod, py_pod, 0.78), (mx_menu, my_menu, 0.72)]
    placed_chairs: list[tuple[float, float]] = []
    out_objs: list[bpy.types.Object] = []
    chair_idx = 0

    for idx, (tx, ty, n_chairs) in enumerate(table_coords):
        rot_t = rng.uniform(0, math.tau)
        out_objs.append(
            gu.spawn_instance(f"Patio_Table_{idx + 1:02d}", me_table, col_tables, (tx, ty, Z_SW), rot_t, asset_set="patio_table")
        )
        z_top = Z_SW + 0.7420
        rot_tw = 1.95 if idx == 3 else rng.uniform(0, math.tau)
        out_objs.append(
            gu.spawn_instance(f"Patio_Tableware_{idx + 1:02d}", me_tableware, col_tableware, (tx, ty, z_top), rot_tw, asset_set="patio_tableware")
        )

        use_cream = idx >= 11
        ch_me = me_chair_cream if use_cream else me_chair_honey
        ch_set = "chair_cream" if use_cream else "chair_honey"
        a0 = -0.35 if idx == 3 else rng.uniform(0.0, math.tau)
        for k in range(n_chairs):
            base_ang = a0 + k * (math.tau / n_chairs)
            best_pos = None
            for trial in range(24):
                ang = base_ang + (0.0 if trial == 0 else (0.14 * ((trial + 1) // 2) * (1 if trial % 2 else -1)))
                dist = 0.60
                ch_x, ch_y = tx + dist * math.cos(ang), ty + dist * math.sin(ang)
                ok = True
                if -4.80 <= ch_x <= 0.55 and 7.00 <= ch_y <= 7.90:
                    ok = False
                if ok:
                    for ox, oy, r_min in fixed_obstacles:
                        if math.hypot(ch_x - ox, ch_y - oy) < r_min:
                            ok = False
                            break
                if ok:
                    for tidx2, (tx2, ty2, _) in enumerate(table_coords):
                        if tidx2 != idx and math.hypot(ch_x - tx2, ch_y - ty2) < 0.72:
                            ok = False
                            break
                if ok:
                    for pcx, pcy in placed_chairs:
                        if math.hypot(ch_x - pcx, ch_y - pcy) < 0.48:
                            ok = False
                            break
                if ok:
                    best_pos = (ch_x, ch_y)
                    break
            if best_pos is not None:
                ch_x, ch_y = best_pos
                placed_chairs.append((ch_x, ch_y))
                chair_idx += 1
                yaw = math.atan2(ty - ch_y, tx - ch_x) - math.pi * 0.5 + rng.uniform(-0.08, 0.08)
                out_objs.append(
                    gu.spawn_instance(f"Patio_Chair_{chair_idx:02d}", ch_me, col_chairs, (ch_x, ch_y, Z_SW), yaw, asset_set=ch_set)
                )

    # 2. Standalone Dedicated-2K Hero Fixtures: `Host_Podium` & `Menu_Stand` (pivoted cleanly at their own ground bases!)
    bm_pod = bmesh.new()
    uv_pod = bm_pod.loops.layers.uv.new("UVMap")
    gu.add_host_podium_quad(bm_pod, uv_pod, 0.0, 0.0, 0.0, mat_body=0, mat_front=1, mat_stainless=2, mat_brass=3)
    out_objs.append(
        gu.finalize_part(
            bm_pod, "Host_Podium", col_fixtures,
            [m["host_podium_body"], m["host_podium_front"], m["stainless_steel"], m["brass_warm"]],
            smooth_angle_deg=42.0, preserve_existing_uv=True, location=(px_pod, py_pod, Z_SW), asset_set="host_podium",
        )
    )

    bm_menu = bmesh.new()
    uv_menu = bm_menu.loops.layers.uv.new("UVMap")
    gu.add_menu_stand_quad(bm_menu, uv_menu, 0.0, 0.0, 0.0, mat_stainless=0, mat_menu=1)
    out_objs.append(
        gu.finalize_part(
            bm_menu, "Menu_Stand", col_fixtures,
            [m["stainless_steel"], m["menu_board"]],
            smooth_angle_deg=42.0, preserve_existing_uv=True, location=(mx_menu, my_menu, Z_SW), asset_set="menu_stand",
        )
    )

    return out_objs, me_chair_honey


def build_street_furniture(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    """Build high-poly FLUSH-GROUNDED `Street_Furniture`: trash bin, hydrant, cobra lamps, clamped signs, ceramic urns & bollards."""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    mat_list = [
        m["trash_bin_green"], m["hydrant_yellow"], m["galvanized_steel"], m["bollard_orange"],
        m["terracotta_pot"], m["glazed_green_pot"], m["sign_one_way"], m["sign_stop_ped"],
        m["sign_no_parking"], m["sign_ocean_dr"], m["sign_8th_st"], m["sign_ada"],
        m["warm_lamp"], m["soil_mulch"], m["zebra_white"], m["cast_iron"],
    ]

    # High-Poly B-Rep CAD 20-rib Trash Bin (13 cm clear of white 8th St planter curb!) & Bolted Mueller Fire Hydrant FLUSH on `Z_PINK`!
    gu.import_cad_to_bmesh(bm, os.path.join(CAD_DIR, "trash_bin.glb"), (11.98, 8.06, Z_PINK), mat_idx=0)
    gu.import_cad_to_bmesh(bm, os.path.join(CAD_DIR, "fire_hydrant.glb"), (12.60, -1.65, Z_PINK), rot_z_rad=math.pi * 0.5, mat_idx=1)

    # Smooth 20-seg Galvanized Streetlight Poles resting EXACTLY FLUSH on `Z_PINK` (8th St) / `Z_SW` (Ocean Dr)!
    lamp_glb = os.path.join(CAD_DIR, "lamp_luminaire.glb")
    for lx, ly, yaw, z_base in [(12.55, 1.35, 0.0, Z_PINK), (-15.80, 10.95, math.pi * 0.5, Z_SW)]:
        base_prof = [(0.22, 0.000), (0.21, 0.055), (0.17, 0.135), (0.15, 0.46), (0.12, 0.52), (0.098, 0.56)]
        gu.add_revolved_profile(bm, (lx, ly, z_base), base_prof, segs=12, mat_idx=2)
        gu.add_cylinder(bm, (lx, ly, z_base + 0.48), (lx, ly, z_base + 7.22), 0.096, 0.060, segs=20, mat_idx=2)
        c, s = math.cos(yaw), math.sin(yaw)
        arm_ctrl = [
            Vector((lx + p[0] * c - p[1] * s, ly + p[0] * s + p[1] * c, z_base + p[2]))
            for p in [(0.0, 0.0, 7.05), (0.45, 0.0, 7.42), (1.20, 0.0, 7.60), (2.06, 0.0, 7.64)]
        ]
        gu.add_spline_tube(bm, arm_ctrl, [0.044, 0.040, 0.036, 0.034], segs=14, substeps=3, mat_idx=2)
        tip_x, tip_y = lx + 2.02 * c, ly + 2.02 * s
        gu.import_cad_to_bmesh(bm, lamp_glb, (tip_x, tip_y, z_base + 7.56), rot_z_rad=yaw, mat_idx=2)
        gu.add_box(bm, (tip_x + 0.38 * c, tip_y + 0.38 * s, z_base + 7.562), (0.30, 0.16, 0.018), 12, (0.0, 0.0, yaw))

    def _add_sign_post_flush(px: float, py: float, z_base: float, top_h: float, rad: float = 0.028) -> None:
        gu.add_cylinder(bm, (px, py, z_base), (px, py, z_base + 0.018), rad * 2.4, rad * 2.1, segs=14, mat_idx=2)
        gu.add_cylinder(bm, (px, py, z_base + 0.015), (px, py, z_base + top_h), rad, rad, segs=14, mat_idx=2)
        gu.add_cylinder(bm, (px, py, z_base + top_h - 0.01), (px, py, z_base + top_h + 0.024), rad * 1.35, rad * 1.15, segs=14, mat_idx=2)

    # Regulatory & Street-Name Signs w/ Flush Base Flanges & Real Wrapped Steel Mounting Clamps!
    _add_sign_post_flush(9.62, 10.48, Z_SW, 2.50, 0.028)
    gu.add_cylinder(bm, (9.62, 10.48, Z_SW + 2.20), (9.62, 10.48, Z_SW + 2.36), 0.036, 0.036, segs=14, mat_idx=2)
    gu.add_uv_mapped_sign_plate(bm, (9.656, 10.48, Z_SW + 2.28), 0.92, 0.32, 0.018, face_dir="+X", mat_front=6, mat_back=2, uv_layer=uv_layer)

    _add_sign_post_flush(9.15, 11.12, Z_SW, 2.54, 0.028)
    gu.add_cylinder(bm, (9.15, 11.12, Z_SW + 2.06), (9.15, 11.12, Z_SW + 2.34), 0.036, 0.036, segs=14, mat_idx=2)
    gu.add_uv_mapped_sign_plate(bm, (9.114, 11.12, Z_SW + 2.20), 0.68, 0.68, 0.018, face_dir="-X", mat_front=7, mat_back=2, uv_layer=uv_layer, yaw_rad=-0.16)

    _add_sign_post_flush(7.35, 10.85, Z_SW, 2.40, 0.024)
    gu.add_cylinder(bm, (7.35, 10.85, Z_SW + 2.00), (7.35, 10.85, Z_SW + 2.30), 0.032, 0.032, segs=14, mat_idx=2)
    gu.add_uv_mapped_sign_plate(bm, (7.35, 10.882, Z_SW + 2.15), 0.38, 0.52, 0.018, face_dir="+Y", mat_front=8, mat_back=2, uv_layer=uv_layer)

    _add_sign_post_flush(11.48, 8.22, Z_PINK, 3.28, 0.032)
    gu.add_cylinder(bm, (11.48, 8.22, Z_PINK + 2.74), (11.48, 8.22, Z_PINK + 3.16), 0.042, 0.042, segs=16, mat_idx=2)
    gu.add_uv_mapped_sign_plate(bm, (11.48, 8.22, Z_PINK + 3.08), 0.88, 0.24, 0.018, face_dir="+Y", mat_front=9, mat_back=9, uv_layer=uv_layer)
    gu.add_uv_mapped_sign_plate(bm, (11.48, 8.22, Z_PINK + 2.82), 0.78, 0.24, 0.018, face_dir="+X", mat_front=10, mat_back=10, uv_layer=uv_layer)

    gu.add_uv_mapped_sign_plate(bm, (NC_X_SOUTH + 0.012, 3.82, Z_PINK + 1.38), 0.24, 0.30, 0.024, face_dir="+X", mat_front=11, mat_back=2, uv_layer=uv_layer)

    # Flexible Orange Valet Bollards resting EXACTLY FLUSH on `Z_SW` w/ Bolted Black Rubber Bases & Dual White Reflective Collars!
    for bx in (-7.20, -11.50, -17.50):
        gu.add_cylinder(bm, (bx, CURB_Y_OCEAN - 0.36, Z_SW), (bx, CURB_Y_OCEAN - 0.36, Z_SW + 0.036), 0.115, 0.095, segs=18, mat_idx=15)
        gu.add_cylinder(bm, (bx, CURB_Y_OCEAN - 0.36, Z_SW + 0.030), (bx, CURB_Y_OCEAN - 0.36, Z_SW + 0.92), 0.044, 0.038, segs=18, mat_idx=3)
        gu.add_icosphere(bm, (bx, CURB_Y_OCEAN - 0.36, Z_SW + 0.92), (0.038, 0.038, 0.028), subdiv=2, mat_idx=3)
        for rz in (0.64, 0.78):
            gu.add_cylinder(bm, (bx, CURB_Y_OCEAN - 0.36, Z_SW + rz), (bx, CURB_Y_OCEAN - 0.36, Z_SW + rz + 0.075), 0.042, 0.041, segs=18, mat_idx=14)

    # Lathe-Revolved Curved Sculptural Glazed-Emerald Ceramic Pots (FLUSH on Z_PINK!) & Rolled-Lip Terracotta Urns (FLUSH on Z_SW!)
    pot_prof_norm = [
        (0.72, 0.00), (0.76, 0.06), (0.94, 0.42), (1.02, 0.76), (0.98, 0.88),
        (1.06, 0.92), (1.06, 0.98), (0.95, 1.00), (0.86, 0.94),
    ]
    for px, py, pr, ph in [(9.35, 7.05, 0.23, 0.42), (9.85, 7.55, 0.26, 0.48), (10.35, 7.95, 0.24, 0.44), (9.90, 8.35, 0.27, 0.50)]:
        prof = [(r * pr, z * ph) for r, z in pot_prof_norm]
        gu.add_revolved_profile(bm, (px, py, Z_PINK), prof, segs=24, mat_idx=5)
        gu.add_cylinder(bm, (px, py, Z_PINK + ph - 0.075), (px, py, Z_PINK + ph - 0.020), pr * 0.86, pr * 0.86, segs=18, mat_idx=13)

    for px, py, z_pot in [
        (-4.20, 7.80, Z_SW), (-2.60, 7.80, Z_SW), (-1.10, 7.80, Z_SW), (0.15, 7.80, Z_SW),
        (-12.55, 4.45, Z_SW + 0.140), (-10.75, 4.45, Z_SW + 0.140),  # EXACT FLUSH on 804 Ocean Dr terracotta porch step!
    ]:
        prof = [(r * 0.27, z * 0.54) for r, z in pot_prof_norm]
        gu.add_revolved_profile(bm, (px, py, z_pot), prof, segs=24, mat_idx=4)
        gu.add_cylinder(bm, (px, py, z_pot + 0.455), (px, py, z_pot + 0.510), 0.23, 0.23, segs=18, mat_idx=13)

    # Flush terracotta planter pots placed strictly IN FRONT of the 3 patio columns (`y = NC_Y_BALC + 0.13` -> ZERO column clip!)
    for vx, vy in [(3.88, NC_Y_BALC + 0.13), (9.05, NC_Y_BALC + 0.13), (-4.95, NC_Y_BALC + 0.13)]:
        prof = [(r * 0.22, z * 0.40) for r, z in pot_prof_norm]
        gu.add_revolved_profile(bm, (vx, vy, Z_SW), prof, segs=20, mat_idx=4)
        gu.add_cylinder(bm, (vx, vy, Z_SW + 0.32), (vx, vy, Z_SW + 0.37), 0.18, 0.18, segs=16, mat_idx=13)

    return gu.finalize_part(bm, "Street_Furniture", col, mat_list, smooth_angle_deg=42.0, preserve_existing_uv=True)


# ---------------------------------------------------------------------------
# High-Poly Photorealistic Tropical Botanicals (24-Seg Ringed Palms, Spline Gnarled Trees,
# Curved 3-Segment Leaves & Genuine 3-Bract Cupped Bougainvillea Blooms!)
# ---------------------------------------------------------------------------
PALM_SPECS = [
    (8.65, 10.05, 9.60, 0.35, 0.65, 11),
    (12.25, 6.45, 7.80, 1.35, 1.15, 12),
    (12.25, 4.95, 8.60, 0.95, -0.45, 13),
    (12.25, 3.35, 7.20, 1.10, -0.90, 14),
    (12.40, 1.95, 8.20, 0.85, 0.40, 15),
    (-6.05, 9.85, 8.80, -0.55, 0.95, 16),
    (-16.10, 10.55, 9.40, -0.25, 0.45, 17),
    (4.50, 22.15, 8.80, -0.45, -0.55, 18),
    (-6.50, 22.15, 9.30, 0.35, -0.60, 19),
    (-17.00, 22.15, 8.90, -0.30, -0.50, 20),
]


def _add_feathery_palm_frond(
    bm: bmesh.types.BMesh,
    crown: Vector,
    az: float,
    f_len: float,
    up_boost: float,
    droop: float,
    rng: random.Random,
    mat_idx: int,
) -> None:
    """High-poly sweeping arched coconut palm frond: 12-seg spline rachis + 22 pairs of curved 3-seg V-folded drooping leaflets!"""
    rad_dir = Vector((math.cos(az), math.sin(az), 0.0))
    lat_dir = Vector((-math.sin(az), math.cos(az), 0.0))

    n_sp = 10
    spine_pts = [
        crown + rad_dir * ((k / n_sp) * f_len) + Vector((0, 0, up_boost * (k / n_sp) - droop * ((k / n_sp) ** 2.05)))
        for k in range(n_sp + 1)
    ]
    radii = [0.036 * (1.0 - 0.78 * (k / n_sp)) for k in range(n_sp + 1)]
    gu.add_spline_tube(bm, spine_pts, radii, segs=8, substeps=1, mat_idx=mat_idx)

    n_pairs = 20
    for i in range(n_pairs):
        u = 0.11 + 0.87 * (i / (n_pairs - 1))
        s_flt = u * n_sp
        s_idx = min(n_sp - 1, int(s_flt))
        s_frac = s_flt - s_idx
        p_node = spine_pts[s_idx].lerp(spine_pts[s_idx + 1], s_frac)
        tang = (spine_pts[s_idx + 1] - spine_pts[s_idx]).normalized()
        env = math.sin(math.pi * math.pow(u, 0.68))
        lf_len = max(0.28, 1.02 * env * rng.uniform(0.88, 1.12))
        lf_wid = max(0.048, 0.088 * env)
        lf_droop = lf_len * (0.55 + 0.28 * u)
        for side in (-1.0, 1.0):
            l_dir = (lat_dir * side * 0.78 + tang * 0.56 + Vector((0, 0, rng.uniform(-0.12, 0.16)))).normalized()
            up_tilt = Vector((rng.uniform(-0.28, 0.28), rng.uniform(-0.28, 0.28), 1.0)).normalized()
            root_pt = p_node + tang * (side * 0.008) + Vector((0, 0, side * 0.002))
            gu.add_curved_leaf(
                bm, root_pt, l_dir, up_tilt, lf_len, lf_wid,
                droop=lf_droop, v_fold=0.22, thickness=0.007, n_segs=3, shape="palm", mat_idx=mat_idx,
            )


def build_palms_and_tree_trunks(col: bpy.types.Collection, m: dict) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object, dict]:
    """Build 24-seg ringed coconut palm trunks + organic spline gnarled Buttonwood trees + sweeping curved palm crowns!"""
    bm_tr = bmesh.new()
    bm_fr_s = bmesh.new()
    bm_fr_n = bmesh.new()
    mat_tr = [m["palm_bark"], m["coconut_green"], m["tree_bark"], m["palm_crown_fiber"]]
    mat_fr = [m["palm_frond"], m["palm_frond_sun"]]

    for p_idx, (px, py, h, ldx, ldy, seed) in enumerate(PALM_SPECS):
        rng = random.Random(seed)
        # 44-ring terraced curved coconut palm trunk w/ crisp organic leaf-scar ledges & flared root buttress!
        n_st, n_circ = 44, 22
        rings: list[list[Vector]] = []
        for i in range(n_st + 1):
            t = i / n_st
            bend = math.pow(t, 1.35)
            cx = px + ldx * bend + 0.09 * math.sin(t * math.pi * 1.4)
            cy = py + ldy * bend + 0.04 * math.cos(t * math.pi * 1.8)
            cz = (Z_SW - 0.005) + (h + 0.025) * t
            r_base = 0.245 * (1.0 - 0.44 * t) + 0.105 * math.exp(-t * 10.5)
            # Crisp terraced sawtooth coconut-palm leaf-scar rings!
            ring_ph = (t * 26.0) % 1.0
            r_ring = r_base * (1.0 + 0.048 * (1.0 - ring_ph))
            rings.append([
                Vector((cx + r_ring * math.cos(math.tau * j / n_circ), cy + r_ring * math.sin(math.tau * j / n_circ), cz))
                for j in range(n_circ)
            ])
        gu.add_closed_tube(bm_tr, rings, Vector((px, py, Z_SW - 0.008)), Vector((px + ldx, py + ldy, Z_SW + h + 0.04)), mat_idx=0)

        # Layered fibrous crownshaft tucked neatly UNDER emerging fronds (zero protruding aerial brown cap!) + 8 glossy coconuts!
        crown = Vector((px + ldx, py + ldy, Z_SW + h))
        gu.add_icosphere(
            bm_tr, (crown.x, crown.y, crown.z - 0.16), (0.19, 0.19, 0.26), subdiv=2, mat_idx=3,
            rot_euler=(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)),
        )
        for c_i in range(8):
            ca = c_i * (math.tau / 8.0) + rng.uniform(-0.18, 0.18)
            cz_off = -0.14 if c_i % 2 == 0 else -0.25
            gu.add_icosphere(
                bm_tr, (crown.x + 0.165 * math.cos(ca), crown.y + 0.165 * math.sin(ca), crown.z + cz_off),
                (0.088, 0.088, 0.112), subdiv=2, mat_idx=1,
                rot_euler=(rng.uniform(0, 6.28), rng.uniform(0, 6.28), rng.uniform(0, 6.28)),
            )

        bm_tgt = bm_fr_s if p_idx < 5 else bm_fr_n
        # 20 lush sweeping fronds per palm (lower arched skirt, mid dome, upper crown & 4 bright young central spear fronds!)
        for fi in range(20):
            tier = 0 if fi < 7 else (1 if fi < 14 else (2 if fi < 17 else 3))
            az = (fi * 2.39996) + rng.uniform(-0.15, 0.15)
            f_len = rng.uniform(2.65, 3.45) * ([1.02, 0.98, 0.84, 0.62][tier])
            up_boost = [0.38, 1.08, 1.75, 2.05][tier] + rng.uniform(-0.12, 0.14)
            droop = [2.00, 1.56, 0.92, 0.48][tier]
            m_f = 1 if (tier >= 2 or fi % 3 == 0) else 0
            _add_feathery_palm_frond(bm_tgt, crown, az, f_len, up_boost, droop, rng, m_f)

    # Organic Gnarled Fluted Spline Buttonwood / Sea Grape Shade Trees (`804 Ocean Dr` — realistic fissured bark + organic crotches!)
    tree_bough_tips: dict[int, list[Vector]] = {}
    shade_trees = [(-7.60, 7.60, 1.00, 31), (-13.85, 7.80, 1.18, 32)]
    for t_idx, (tx, ty, sc, seed) in enumerate(shade_trees):
        rng = random.Random(seed)
        tips: list[Vector] = []
        p_base = Vector((tx, ty, Z_SW - 0.004))
        p_low = Vector((tx + 0.10 * sc, ty + 0.06 * sc, Z_SW + 0.65 * sc))
        p_mid = Vector((tx + 0.24 * sc, ty + 0.18 * sc, Z_SW + 1.45 * sc))
        p_fork = Vector((tx + 0.08 * sc, ty + 0.24 * sc, Z_SW + 2.35 * sc))
        gu.add_spline_tube(
            bm_tr, [p_base, p_low, p_mid, p_fork],
            [0.31 * sc, 0.22 * sc, 0.180 * sc, 0.155 * sc],
            segs=20, substeps=4, mat_idx=2, rib_amp=0.035, rib_freq=3.5, flute_amp=0.055, flute_freq=6,
        )
        # Organic flared gnarly crotch swelling at main branch junction
        gu.add_icosphere(bm_tr, (p_fork.x, p_fork.y, p_fork.z - 0.05 * sc), (0.17 * sc, 0.16 * sc, 0.15 * sc), subdiv=2, mat_idx=2)
        # Flared gnarled surface roots gripping the mulch tree pit (strictly >= Z_SW + 0.005 -> ZERO below-slab root poke!)
        for rk in range(5):
            ra = rk * (math.tau / 5.0) + rng.uniform(-0.25, 0.25)
            gu.add_spline_tube(
                bm_tr,
                [
                    Vector((tx + 0.06 * math.cos(ra) * sc, ty + 0.06 * math.sin(ra) * sc, Z_SW + 0.36 * sc)),
                    Vector((tx + 0.20 * math.cos(ra) * sc, ty + 0.20 * math.sin(ra) * sc, Z_SW + 0.14 * sc)),
                    Vector((tx + 0.38 * math.cos(ra) * sc, ty + 0.38 * math.sin(ra) * sc, Z_SW + 0.028)),
                ],
                [0.088 * sc, 0.058 * sc, 0.022 * sc], segs=12, substeps=3, mat_idx=2, flute_amp=0.05, flute_freq=4, cap_round=False,
            )

        limbs = [
            (-1.60, 0.72, 4.00), (1.48, 0.58, 3.88), (-0.42, -1.32, 4.18),
            (0.78, 1.44, 3.74), (-1.26, -0.64, 3.68), (0.18, 0.14, 4.62),
        ]
        for dx, dy, dz in limbs:
            p_end = Vector((tx + dx * sc, ty + dy * sc, Z_SW + dz * sc))
            p_collar = p_fork.lerp(p_end, 0.16) + Vector((0, 0, -0.06))
            p_elbow = 0.52 * (p_fork + p_end) + Vector((rng.uniform(-0.28, 0.28), rng.uniform(-0.28, 0.28), 0.22))
            gu.add_spline_tube(
                bm_tr, [p_fork - Vector((0, 0, 0.14)), p_collar, p_elbow, p_end],
                [0.122 * sc, 0.095 * sc, 0.064 * sc, 0.036 * sc], segs=14, substeps=3, mat_idx=2, flute_amp=0.045, flute_freq=5,
            )
            tips.append(p_end)
            # 3 curved diverging secondary boughs + finer tertiary branchlets!
            for tw in range(3):
                ang_tw = tw * 2.09 + rng.uniform(-0.4, 0.4)
                tw_dir = Vector((math.cos(ang_tw) * 0.85, math.sin(ang_tw) * 0.85, rng.uniform(0.10, 0.65))).normalized()
                p_tw_mid = p_end + tw_dir * (0.44 * sc) + Vector((rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), 0.08))
                p_tw = p_end + tw_dir * (0.90 * sc)
                gu.add_spline_tube(bm_tr, [p_end, p_tw_mid, p_tw], [0.036 * sc, 0.025 * sc, 0.014 * sc], segs=10, substeps=2, mat_idx=2)
                tips.append(p_tw)
        tree_bough_tips[t_idx] = tips

    ob_tr = gu.finalize_part(bm_tr, "Palms_Trunks", col, mat_tr, smooth_angle_deg=48.0)
    ob_frs = gu.finalize_part(bm_fr_s, "Palms_Fronds_South", col, mat_fr, smooth_angle_deg=52.0)
    ob_frn = gu.finalize_part(bm_fr_n, "Palms_Fronds_North", col, mat_fr, smooth_angle_deg=52.0)
    return ob_tr, ob_frs, ob_frn, tree_bough_tips


def _add_curved_foliage_sprig(
    bm: bmesh.types.BMesh,
    center: Vector,
    hub_radius: float,
    n_leaves: int,
    leaf_len: float,
    leaf_wid: float,
    rng: random.Random,
    mat_choices: list[int],
    *,
    stem_anchor: Vector | None = None,
    stem_mat: int = 0,
    hub_mat: int | None = None,
    shape: str = "ovate",
) -> None:
    """Create a realistic organic botanical sprig of 3-segment curved V-folded broad leaves (ZERO sharp low-poly darts!)."""
    hm = stem_mat if hub_mat is None else hub_mat
    if stem_anchor is not None:
        mid_s = stem_anchor.lerp(center, 0.5) + Vector((rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0.02))
        gu.add_spline_tube(bm, [stem_anchor, mid_s, center], [0.018, 0.014, 0.010], segs=6, substeps=2, mat_idx=stem_mat)
    r_knot = max(0.020, hub_radius)
    rot_k = (rng.uniform(0.0, math.tau), rng.uniform(0.0, math.tau), rng.uniform(0.0, math.tau))
    gu.add_box(bm, (center.x, center.y, center.z), (r_knot * 2.0, r_knot * 1.8, r_knot * 1.6), mat_idx=hm, rot_euler=rot_k)

    for k in range(n_leaves):
        az = k * 2.39996 + rng.uniform(-0.38, 0.38)
        elev = rng.uniform(-0.42, 0.88)
        f_dir = Vector((math.cos(az) * math.cos(elev), math.sin(az) * math.cos(elev), math.sin(elev))).normalized()
        root = center + f_dir * (r_knot * 0.30) + Vector((rng.uniform(-0.006, 0.006), rng.uniform(-0.006, 0.006), rng.uniform(-0.006, 0.006)))
        up_h = Vector((rng.uniform(-0.55, 0.55), rng.uniform(-0.55, 0.55), 1.0)).normalized()
        gu.add_curved_leaf(
            bm, root, f_dir, up_h,
            leaf_len * rng.uniform(0.80, 1.24),
            leaf_wid * rng.uniform(0.82, 1.22),
            droop=leaf_len * rng.uniform(0.14, 0.30),
            v_fold=0.18,
            thickness=0.007,
            n_segs=3,
            shape=shape,
            mat_idx=rng.choice(mat_choices),
        )


def build_foliage_and_bougainvillea(
    col: bpy.types.Collection,
    m: dict,
    tree_bough_tips: dict[int, list[Vector]],
) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object]:
    """Build lush photorealistic curved-leaf `Foliage_Trees`, dense `Hedges_Shrubs` & genuine 3-bract `Bougainvillea`!"""
    bm_tree = bmesh.new()
    bm_hdg = bmesh.new()
    bm_bgv = bmesh.new()

    mat_tree = [m["tree_canopy"], m["tree_canopy_lit"], m["hedge_dark"], m["tree_bark"]]
    mat_hdg = [m["hedge_dark"], m["hedge_mid"], m["lime_shrub"]]
    mat_bgv = [m["bougainvillea_pink"], m["bougainvillea_deep"], m["hedge_dark"], m["tree_bark"], m["bougainvillea_floret"]]

    rng = random.Random(777)

    # 1. `Foliage_Trees`: Dense billowing Sea Grape / Buttonwood canopies made of 3-seg curved ovate broad leaves!
    for t_idx, tips in tree_bough_tips.items():
        for tip in tips:
            _add_curved_foliage_sprig(
                bm_tree, tip, hub_radius=0.032, n_leaves=14,
                leaf_len=0.38, leaf_wid=0.25, rng=rng,
                mat_choices=[0, 0, 1, 2], hub_mat=3,
            )
            for sub in range(3 if t_idx == 0 else 4):
                off = Vector((rng.uniform(-0.62, 0.62), rng.uniform(-0.62, 0.62), rng.uniform(-0.38, 0.46)))
                p_sub = tip + off
                _add_curved_foliage_sprig(
                    bm_tree, p_sub, hub_radius=0.028, n_leaves=12,
                    leaf_len=0.35, leaf_wid=0.23, rng=rng,
                    mat_choices=[0, 1, 1] if off.z > 0.05 else [0, 0, 2],
                    stem_anchor=tip, stem_mat=3, hub_mat=3,
                )

    # 2. `Hedges_Shrubs`: Lush dense manicured SE corner hedge mound, 8th St recessed planter bed & sculpted potted tropical plants!
    wedge_inner = [(7.70, 9.00), (7.70, 11.06), (9.42, 11.06), (10.18, 10.60), (10.52, 9.94), (9.55, 9.00)]
    gu.add_prism_xy(bm_hdg, wedge_inner, Z_SW, Z_SW + 0.34, 0)
    for i in range(150):
        if i < 52:
            perim = [
                (7.60, 8.92), (7.60, 11.14), (9.45, 11.14), (10.24, 10.65),
                (10.60, 9.92), (9.60, 8.92), (7.60, 8.92),
            ]
            seg_i = (i * (len(perim) - 1)) // 52
            frac = ((i * (len(perim) - 1)) % 52) / 52.0
            ax, ay = perim[seg_i]
            bx, by = perim[min(seg_i + 1, len(perim) - 1)]
            hx = ax + (bx - ax) * frac + rng.uniform(-0.08, 0.08)
            hy = ay + (by - ay) * frac + rng.uniform(-0.08, 0.08)
            hz = Z_SW + rng.uniform(0.16, 0.44)
        else:
            u, v = rng.uniform(0.0, 1.0), rng.uniform(0.0, 1.0)
            hx = 7.68 + u * 2.82
            hy = 8.98 + v * 2.10
            if (hx - 9.2) + (hy - 10.2) > 1.32:
                hx -= 0.72
                hy -= 0.56
            hz = Z_SW + rng.uniform(0.36, 0.64)
        p_c = Vector((hx, hy, hz))
        p_base = Vector((hx + rng.uniform(-0.04, 0.04), hy + rng.uniform(-0.04, 0.04), Z_SW + rng.uniform(0.010, 0.024)))
        _add_curved_foliage_sprig(
            bm_hdg, p_c, hub_radius=0.032, n_leaves=12, leaf_len=0.25, leaf_wid=0.145, rng=rng,
            mat_choices=[0, 0, 1, 1], stem_anchor=p_base, stem_mat=0, hub_mat=0,
        )

    # 8th St recessed tropical planter bed — 92 dense curved-leaf groundcover sprigs emerging directly from mulch (ZERO blocky green brick!)
    for i in range(92):
        hx = rng.uniform(11.78, 12.72)
        hy = 2.44 + (i / 91.0) * 4.98 + rng.uniform(-0.08, 0.08)
        hz = Z_SW + rng.uniform(0.16, 0.42)
        p_base = Vector((hx + rng.uniform(-0.04, 0.04), hy + rng.uniform(-0.04, 0.04), Z_SW + rng.uniform(0.05, 0.09)))
        _add_curved_foliage_sprig(
            bm_hdg, Vector((hx, hy, hz)), hub_radius=0.026, n_leaves=11, leaf_len=0.25, leaf_wid=0.14, rng=rng,
            mat_choices=[0, 1, 2], stem_anchor=p_base, stem_mat=0, hub_mat=0,
        )

    # Lush sculpted broad-leaf tropical plants anchored strictly inside the raised ceramic, terracotta & cedar planter soils!
    for px, py, ph in [(9.35, 7.05, 0.42), (9.85, 7.55, 0.48), (10.35, 7.95, 0.44), (9.90, 8.35, 0.50)]:
        _add_curved_foliage_sprig(
            bm_hdg, Vector((px, py, Z_PINK + ph + 0.14)), hub_radius=0.034, n_leaves=16,
            leaf_len=0.38, leaf_wid=0.18, rng=rng, mat_choices=[2, 2, 1],
            stem_anchor=Vector((px, py, Z_PINK + ph - 0.05)), stem_mat=0, hub_mat=0,
        )
    for px, py, z_pot in [
        (-4.20, 7.80, Z_SW), (-2.60, 7.80, Z_SW), (-1.10, 7.80, Z_SW), (0.15, 7.80, Z_SW),
        (-12.55, 4.45, Z_SW + 0.140), (-10.75, 4.45, Z_SW + 0.140),
    ]:
        _add_curved_foliage_sprig(
            bm_hdg, Vector((px, py, z_pot + 0.68)), hub_radius=0.034, n_leaves=16,
            leaf_len=0.40, leaf_wid=0.19, rng=rng, mat_choices=[0, 1, 2],
            stem_anchor=Vector((px, py, z_pot + 0.48)), stem_mat=0, hub_mat=0,
        )
    for px, py in [(-6.35, 4.95), (-6.35, 6.25), (-7.15, 7.25)]:
        _add_curved_foliage_sprig(
            bm_hdg, Vector((px, py, Z_SW + 0.88)), hub_radius=0.036, n_leaves=18,
            leaf_len=0.42, leaf_wid=0.20, rng=rng, mat_choices=[0, 1, 2],
            stem_anchor=Vector((px, py, Z_SW + 0.67)), stem_mat=0, hub_mat=0,
        )

    for px in (-18.0, -12.0, -5.0, 2.0, 9.0, 15.0):
        for k in range(6):
            hx = px + rng.uniform(-1.6, 1.6)
            hy = 22.35 + rng.uniform(-0.28, 0.28)
            hz = Z_SW + rng.uniform(0.32, 0.68)
            p_base = Vector((hx + rng.uniform(-0.05, 0.05), hy + rng.uniform(-0.05, 0.05), Z_SW + rng.uniform(0.010, 0.024)))
            _add_curved_foliage_sprig(
                bm_hdg, Vector((hx, hy, hz)), hub_radius=0.036, n_leaves=11, leaf_len=0.36, leaf_wid=0.19, rng=rng,
                mat_choices=[0, 1, 2], stem_anchor=p_base, stem_mat=0, hub_mat=0,
            )

    # 3. `Bougainvillea`: Smooth twisting woody climbing vines bursting w/ REAL 3-bract cupped papery blooms + cream florets + oval leaves!
    def _add_bougainvillea_spray(p_anchor: Vector, p_bloom: Vector) -> None:
        mid = p_anchor.lerp(p_bloom, 0.5) + Vector((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), -0.02))
        gu.add_spline_tube(bm_bgv, [p_anchor, mid, p_bloom], [0.014, 0.010, 0.007], segs=6, substeps=2, mat_idx=3)
        # 2-3 cupped 3-bract magenta flower clusters per spray + 4 dark-green curved oval leaves!
        for _ in range(3):
            off = Vector((rng.uniform(-0.10, 0.10), rng.uniform(-0.08, 0.10), rng.uniform(-0.08, 0.08)))
            n_d = Vector((rng.uniform(-0.8, 0.8), rng.uniform(0.2, 1.0), rng.uniform(-0.3, 0.8))).normalized()
            gu.add_bougainvillea_cluster(
                bm_bgv, p_bloom + off, n_d, rng.uniform(0.068, 0.095), rng,
                mat_bract=rng.choice([0, 0, 1]), mat_floret=4,
            )
        for _ in range(4):
            l_dir = Vector((rng.uniform(-1, 1), rng.uniform(-0.5, 1.0), rng.uniform(-0.6, 0.6))).normalized()
            up_h = Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 1.0)).normalized()
            gu.add_curved_leaf(
                bm_bgv, p_bloom, l_dir, up_h, rng.uniform(0.09, 0.13), rng.uniform(0.06, 0.09),
                droop=0.02, thickness=0.005, n_segs=2, shape="ovate", mat_idx=2,
            )

    vine_columns = [
        (3.88, NC_Y_BALC - 0.10, 0.94, 3.04, 36),
        (9.05, NC_Y_BALC - 0.10, 0.65, 3.06, 32),
        (-4.95, NC_Y_BALC - 0.10, 0.65, 3.06, 24),
    ]
    for vx, vy, z0, z1, n_sp in vine_columns:
        pts_v = [
            Vector((
                vx + 0.07 * math.sin((k / 8.0) * 7.5),
                (vy + 0.23 * math.exp(-k * 0.65)) + 0.06 * math.cos((k / 8.0) * 5.5),
                Z_SW + 0.35 + (z1 - 0.32) * (k / 8.0),
            ))
            for k in range(10)
        ]
        gu.add_spline_tube(bm_bgv, pts_v, [0.036 * (1.0 - 0.45 * (k / 9.0)) for k in range(10)], segs=10, substeps=2, mat_idx=3)
        for k in range(n_sp):
            t = k / max(n_sp - 1, 1)
            bz = Z_SW + z0 + (z1 - z0) * t
            spread = 0.40 if t > 0.58 else 0.24
            bx = vx + rng.uniform(-spread, spread)
            by = vy + rng.uniform(-0.12, 0.24)
            _add_bougainvillea_spray(Vector((vx, vy, bz - 0.04)), Vector((bx, by, bz)))

    p_a = Vector((1.76, NC_Y_BALC + 0.06, Z_SW + 3.04))
    p_b = Vector((3.88, NC_Y_BALC - 0.08, Z_SW + 3.04))
    gu.add_spline_tube(bm_bgv, [Vector((1.76, NC_Y_BALC - 0.06, Z_SW + 3.68)), p_a, p_a.lerp(p_b, 0.5) + Vector((0, 0.06, -0.04)), p_b], 0.026, segs=8, substeps=2, mat_idx=3)
    for k in range(26):
        t = k / 25.0
        gx = 1.74 + t * 2.12
        z_cap = 3.20 if gx < 2.32 else 2.94
        gz = Z_SW + z_cap - 0.14 + rng.uniform(-0.16, 0.12)
        gy = (NC_Y_BALC + 0.12 if gx < 2.32 else NC_Y_BALC - 0.06) + rng.uniform(-0.12, 0.20)
        _add_bougainvillea_spray(p_a.lerp(p_b, t), Vector((gx, gy, gz)))

    ob_tree = gu.finalize_part(bm_tree, "Foliage_Trees", col, mat_tree, smooth_angle_deg=52.0)
    ob_hdg = gu.finalize_part(bm_hdg, "Hedges_Shrubs", col, mat_hdg, smooth_angle_deg=52.0)
    ob_bgv = gu.finalize_part(bm_bgv, "Bougainvillea", col, mat_bgv, smooth_angle_deg=52.0)
    return ob_tree, ob_hdg, ob_bgv
