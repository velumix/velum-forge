r"""High-Poly ArchViz Architectural Builders for News Cafe (800 Ocean Dr), 804 Ocean Dr & 820 Ocean Dr.

High-Poly Photorealistic Upgrades (No 20k Cap):
  - Smooth 24-segment curved Art Deco quatrefoil breeze blocks w/ beveled front/back masonry chamfers
  - Micro-beveled Art Deco eyebrows, drip moldings, pilasters, recessed brass LED downlights & slatted HVAC units
  - Tilted 3D glass jalousie louvers, beveled water-shedding aluminum sills, balcony woven armchairs, accordion bi-fold cafe doors
  - Smoothly curved semicircular scalloped awning valances + 3D continuous white stitched piping + side end-curtains + catenary sag
  - Curved tufted channel-back burgundy leather banquettes, lathe-turned 3D wine/spirits bottles & brass swivel barstools
  - 804 Ocean Dr: overlapping curved Spanish Mission barrel + valley terracotta tiles, beveled pediments & hexagonal wrought-iron lanterns
  - 820 Ocean Dr: true 20-seg semicircular royal-blue Art Deco arch, curved blue window hoods & rounded-top pickets!
"""
from __future__ import annotations

import math
import bmesh
import bpy
from mathutils import Vector

import geo_utils as gu

Z_ROAD = 0.22
Z_SW = 0.37

NC_X_NORTH = -5.30
NC_X_SOUTH = 9.30
NC_Y_WEST = -15.50
NC_Y_EAST_WALL = 4.00
NC_Y_BALC = 5.55

Z_F1 = Z_SW
Z_FLOOR_INT = Z_F1 + 0.042
Z_F2_BOT = Z_SW + 3.68
Z_F2_TOP = Z_F2_BOT + 0.26
Z_F3_BOT = Z_F2_TOP + 2.68
Z_F3_TOP = Z_F3_BOT + 0.26
Z_RF_BOT = Z_F3_TOP + 2.68
Z_RF_TOP = Z_RF_BOT + 0.26
Z_PARAPET_TOP = Z_RF_TOP + 1.16

# Exact structural awning pole & patio column XY positions (exported to build_street_and_nature.py for ZERO collisions!)
PATIO_COLUMN_XY: list[tuple[float, float]] = [
    (-4.95, NC_Y_BALC - 0.22),
    (-0.60, NC_Y_BALC - 0.22),
    (3.90, NC_Y_BALC - 0.22),
    (9.02, NC_Y_BALC - 0.22),
]
AWNING_POLE_XY: list[tuple[float, float]] = [
    # Awning 1: x=-5.45..+1.70, proj y=5.55..7.68 -> poles at y=7.51
    (-5.02, NC_Y_BALC + 1.96), (-1.88, NC_Y_BALC + 1.96), (1.27, NC_Y_BALC + 1.96),
    # Awning 2: x=+2.35..+9.55, proj y=5.55..7.68 -> poles at y=7.51
    (2.78, NC_Y_BALC + 1.96), (5.95, NC_Y_BALC + 1.96), (9.12, NC_Y_BALC + 1.96),
]


def _add_window_assembly(
    bm_win: bmesh.types.BMesh,
    wall_point: tuple[float, float, float],
    width: float,
    height: float,
    *,
    face_axis: str = "+Y",
    panes_x: int = 2,
    jalousie_slats: int = 7,
    mat_glass: int = 0,
    mat_frame: int = 1,
    mat_slat: int | None = None,
    frame_t: float = 0.058,
    reveal_depth: float = 0.13,
) -> None:
    """High-poly architectural jalousie window w/ beveled frames, stepped aluminum sill & tilted 3D louver blades."""
    wx, wy, wz = wall_point
    slat_m = mat_frame if mat_slat is None else mat_slat
    emb = 0.018
    full_d = reveal_depth + emb

    if face_axis == "+Y":
        y_glass = wy + 0.028
        y_frame = wy + 0.5 * (reveal_depth - emb)
        gu.add_box(bm_win, (wx, y_glass, wz), (width - frame_t * 0.6, 0.028, height - frame_t * 0.6), mat_glass)
        # Beveled header, stepped water-shedding sill & jambs
        gu.add_box(bm_win, (wx, y_frame + 0.004, wz + height * 0.5 - frame_t * 0.5), (width + 0.02, full_d, frame_t), mat_frame, bevel=0.005)
        gu.add_box(bm_win, (wx, y_frame + 0.014, wz - height * 0.5 + frame_t * 0.48), (width + 0.07, full_d + 0.032, frame_t * 1.18), mat_frame, bevel=0.006)
        gu.add_box(bm_win, (wx - width * 0.5 + frame_t * 0.5, y_frame, wz), (frame_t, full_d - 0.008, height - 2 * frame_t + 0.024), mat_frame, bevel=0.005)
        gu.add_box(bm_win, (wx + width * 0.5 - frame_t * 0.5, y_frame, wz), (frame_t, full_d - 0.008, height - 2 * frame_t + 0.024), mat_frame, bevel=0.005)
        for p in range(1, panes_x):
            mx = wx - width * 0.5 + width * (p / panes_x)
            gu.add_box(bm_win, (mx, y_glass + 0.044, wz), (frame_t * 0.72, 0.044, height - frame_t * 0.9), mat_frame, bevel=0.004)
        # Genuine tilted 3D Miami Beach jalousie louver slats catching sunlight!
        for s in range(1, jalousie_slats):
            sz = wz - height * 0.5 + height * (s / jalousie_slats)
            gu.add_box(bm_win, (wx, y_glass + 0.054, sz), (width - frame_t * 1.1, 0.026, 0.012), slat_m, rot_euler=(math.radians(18.0), 0.0, 0.0))

    elif face_axis in ("+X", "-X"):
        sgn = 1.0 if face_axis == "+X" else -1.0
        x_glass = wx + sgn * 0.028
        x_frame = wx + sgn * 0.5 * (reveal_depth - emb)
        gu.add_box(bm_win, (x_glass, wy, wz), (0.028, width - frame_t * 0.6, height - frame_t * 0.6), mat_glass)
        gu.add_box(bm_win, (x_frame + sgn * 0.004, wy, wz + height * 0.5 - frame_t * 0.5), (full_d, width + 0.02, frame_t), mat_frame, bevel=0.005)
        gu.add_box(bm_win, (x_frame + sgn * 0.014, wy, wz - height * 0.5 + frame_t * 0.48), (full_d + 0.032, width + 0.07, frame_t * 1.18), mat_frame, bevel=0.006)
        gu.add_box(bm_win, (x_frame, wy - width * 0.5 + frame_t * 0.5, wz), (full_d - 0.008, frame_t, height - 2 * frame_t + 0.024), mat_frame, bevel=0.005)
        gu.add_box(bm_win, (x_frame, wy + width * 0.5 - frame_t * 0.5, wz), (full_d - 0.008, frame_t, height - 2 * frame_t + 0.024), mat_frame, bevel=0.005)
        for p in range(1, panes_x):
            my = wy - width * 0.5 + width * (p / panes_x)
            gu.add_box(bm_win, (x_glass + sgn * 0.044, my, wz), (0.044, frame_t * 0.72, height - frame_t * 0.9), mat_frame, bevel=0.004)
        for s in range(1, jalousie_slats):
            sz = wz - height * 0.5 + height * (s / jalousie_slats)
            gu.add_box(bm_win, (x_glass + sgn * 0.054, wy, sz), (0.026, width - frame_t * 1.1, 0.012), slat_m, rot_euler=(0.0, math.radians(-18.0 * sgn), 0.0))


def build_news_cafe_shell(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    """Build high-poly `NewsCafe_Shell` w/ beveled Art Deco eyebrows, recessed LED brass bezels & detailed rooftop HVAC."""
    bm = bmesh.new()
    mat_list = [m["stucco_cream"], m["stucco_white"], m["roof_membrane"], m["column_green"], m["interior_floor"], m["warm_lamp"], m["brass_warm"], m["cast_iron"]]

    # 1. Ground Floor Main Solid Rear Mass & Side/Front Piers (EXACT flush base at Z_F1 -> ZERO buried overhangs!)
    gu.add_box_bounds(bm, NC_X_NORTH + 0.006, NC_X_SOUTH - 0.006, NC_Y_WEST + 0.006, -4.15, Z_F1, Z_F2_BOT + 0.02, 0)
    gu.add_box_bounds(bm, NC_X_NORTH + 0.012, NC_X_NORTH + 0.42, -4.15, NC_Y_EAST_WALL - 0.012, Z_F1, Z_F2_BOT + 0.02, 0)
    gu.add_box_bounds(bm, NC_X_SOUTH - 0.38, NC_X_SOUTH - 0.006, -4.15, NC_Y_EAST_WALL - 0.012, Z_F1, Z_F1 + 0.90, 0)
    gu.add_box_bounds(bm, NC_X_SOUTH - 0.38, NC_X_SOUTH - 0.006, -4.15, NC_Y_EAST_WALL - 0.012, Z_F1 + 2.88, Z_F2_BOT + 0.02, 0)
    for y0, y1 in [(3.55, 3.98), (-0.85, -0.30), (-2.95, -2.50), (-4.15, -3.75)]:
        gu.add_box_bounds(bm, NC_X_SOUTH - 0.37, NC_X_SOUTH - 0.014, y0, y1, Z_F1 + 0.88, Z_F1 + 2.90, 0)
    gu.add_box_bounds(bm, NC_X_NORTH + 0.018, NC_X_SOUTH - 0.018, NC_Y_EAST_WALL - 0.34, NC_Y_EAST_WALL - 0.006, Z_F1 + 2.94, Z_F2_BOT + 0.02, 0)
    for x0, x1 in [(-5.26, -4.55), (-0.95, -0.25), (3.55, 4.25), (8.60, 9.26)]:
        gu.add_box_bounds(bm, x0, x1, NC_Y_EAST_WALL - 0.33, NC_Y_EAST_WALL - 0.014, Z_F1, Z_F1 + 2.96, 0, bevel=0.010)

    # Interior terrazzo cafe floor slab resting cleanly on Z_F1 (top surface = exact Z_FLOOR_INT = Z_F1 + 0.042!)
    gu.add_box_bounds(bm, NC_X_NORTH + 0.42, NC_X_SOUTH - 0.38, -4.15, NC_Y_BALC - 0.04, Z_F1, Z_FLOOR_INT, 4)

    # Chamfered dark-green structural corner columns w/ molded base plinths & capitals (EXACT flush on Z_F1!)
    for cx, cy in PATIO_COLUMN_XY:
        gu.add_box_bounds(bm, cx - 0.15, cx + 0.15, cy - 0.15, cy + 0.15, Z_F1, Z_F1 + 0.30, 3, bevel=0.010)
        gu.add_box_bounds(bm, cx - 0.12, cx + 0.12, cy - 0.12, cy + 0.12, Z_F1 + 0.28, Z_F2_BOT - 0.12, 3, bevel=0.012)
        gu.add_box_bounds(bm, cx - 0.15, cx + 0.15, cy - 0.15, cy + 0.15, Z_F2_BOT - 0.14, Z_F2_BOT, 3, bevel=0.010)

    # Corner low stepped stucco curb wall & crisp beveled white concrete base plinth along 8th St (flush on Z_F1!)
    gu.add_box_bounds(bm, NC_X_SOUTH - 0.34, NC_X_SOUTH + 0.02, NC_Y_EAST_WALL - 0.04, NC_Y_BALC + 0.02, Z_F1, Z_F1 + 0.56, 0, bevel=0.010)
    gu.add_box_bounds(bm, NC_X_SOUTH - 0.012, NC_X_SOUTH + 0.055, NC_Y_WEST + 0.02, NC_Y_EAST_WALL - 0.02, Z_F1, Z_F1 + 0.72, 1, bevel=0.008)

    # 2. Floors 2 & 3 Main Solid Building Mass
    gu.add_box_bounds(bm, NC_X_NORTH, NC_X_SOUTH, NC_Y_WEST, NC_Y_EAST_WALL, Z_F2_BOT + 0.03, Z_RF_TOP - 0.03, 0)

    # 3. Crisp Beveled White Art Deco Vertical Pilasters along 8th Street (exact Photo 5 rhythm!)
    for py in (-11.45, -6.10, -3.65, -1.25, 3.55):
        gu.add_box_bounds(bm, NC_X_SOUTH - 0.016, NC_X_SOUTH + 0.026, py - 0.56, py + 0.56, Z_F2_TOP - 0.02, Z_RF_BOT + 0.02, 1, bevel=0.006)

    # 4. Cantilevered Beveled White Art Deco Floor Slabs, Drip Moldings & Recessed Brass LED Downlights!
    for z_bot, z_top in [(Z_F2_BOT, Z_F2_TOP), (Z_F3_BOT, Z_F3_TOP), (Z_RF_BOT, Z_RF_TOP)]:
        gu.add_box_bounds(bm, NC_X_NORTH - 0.34, NC_X_SOUTH + 0.44, NC_Y_WEST - 0.25, NC_Y_BALC + 0.04, z_bot, z_top, 1, bevel=0.014)
        gu.add_box_bounds(bm, NC_X_NORTH - 0.28, NC_X_SOUTH + 0.38, NC_Y_WEST - 0.20, NC_Y_BALC - 0.04, z_bot - 0.06, z_bot + 0.025, 1, bevel=0.008)
        for lx in (-2.8, 2.0, 6.8):
            gu.add_cylinder(bm, (lx, NC_Y_EAST_WALL + 0.78, z_bot + 0.02), (lx, NC_Y_EAST_WALL + 0.78, z_bot - 0.022), 0.105, 0.098, segs=18, mat_idx=6)
            gu.add_cylinder(bm, (lx, NC_Y_EAST_WALL + 0.78, z_bot + 0.01), (lx, NC_Y_EAST_WALL + 0.78, z_bot - 0.028), 0.078, 0.078, segs=18, mat_idx=5)

    # 5. Roof Membrane Deck & Solid Beveled White Parapet Walls
    gu.add_box_bounds(bm, NC_X_NORTH + 0.22, NC_X_SOUTH - 0.12, NC_Y_WEST + 0.22, NC_Y_BALC - 0.22, Z_RF_TOP - 0.02, Z_RF_TOP + 0.06, 2)
    gu.add_box_bounds(bm, NC_X_NORTH - 0.29, NC_X_SOUTH + 0.39, NC_Y_WEST - 0.21, NC_Y_WEST + 0.18, Z_RF_TOP - 0.02, Z_PARAPET_TOP - 0.24, 1, bevel=0.012)
    gu.add_box_bounds(bm, NC_X_NORTH - 0.28, NC_X_NORTH + 0.16, NC_Y_WEST + 0.12, NC_Y_EAST_WALL + 0.02, Z_RF_TOP - 0.025, Z_PARAPET_TOP - 0.16, 1, bevel=0.012)

    z_p_top = Z_RF_TOP + 0.86
    vent_ranges = [(-13.2, -11.9), (-9.2, -7.9), (-5.2, -3.9), (-1.2, 0.1)]
    gu.add_box_bounds(bm, NC_X_SOUTH + 0.03, NC_X_SOUTH + 0.42, NC_Y_WEST + 0.14, NC_Y_EAST_WALL + 0.02, Z_RF_TOP - 0.025, Z_RF_TOP + 0.24, 1)
    gu.add_box_bounds(bm, NC_X_SOUTH + 0.01, NC_X_SOUTH + 0.45, NC_Y_WEST + 0.14, NC_Y_EAST_WALL + 0.04, z_p_top - 0.16, z_p_top, 1, bevel=0.012)
    y_cursor = NC_Y_WEST + 0.16
    for v0, v1 in vent_ranges:
        gu.add_box_bounds(bm, NC_X_SOUTH + 0.04, NC_X_SOUTH + 0.41, y_cursor, v0, Z_RF_TOP + 0.20, z_p_top - 0.12, 1)
        y_cursor = v1
    gu.add_box_bounds(bm, NC_X_SOUTH + 0.04, NC_X_SOUTH + 0.41, y_cursor, NC_Y_EAST_WALL + 0.01, Z_RF_TOP + 0.20, z_p_top - 0.12, 1)

    # 6. Streamline Moderne Rooftop Stair Penthouse & Detailed Louvered HVAC Units w/ Fan Grilles!
    gu.add_box_bounds(bm, -4.40, 3.80, -14.20, -6.20, Z_RF_TOP - 0.012, Z_RF_TOP + 2.35, 1, bevel=0.020)
    gu.add_box_bounds(bm, -4.65, 4.05, -14.45, -5.95, Z_RF_TOP + 2.24, Z_RF_TOP + 2.48, 1, bevel=0.018)
    for hx, hy in [(5.8, -9.5), (5.8, -11.8)]:
        gu.add_box(bm, (hx, hy, Z_RF_TOP + 0.46), (1.35, 1.10, 0.90), 2, bevel=0.016)
        gu.add_cylinder(bm, (hx, hy, Z_RF_TOP + 0.89), (hx, hy, Z_RF_TOP + 0.96), 0.42, 0.42, segs=24, mat_idx=7)
        for gr in range(5):
            gu.add_box(bm, (hx, hy - 0.34 + gr * 0.17, Z_RF_TOP + 0.965), (0.80, 0.018, 0.014), 1)

    return gu.finalize_part(bm, "NewsCafe_Shell", col, mat_list, smooth_angle_deg=38.0)


def build_news_cafe_breeze_blocks(col: bpy.types.Collection, m: dict) -> list[bpy.types.Object]:
    """Build 4 high-poly 24-seg curved Art Deco quatrefoil breeze-block balustrades bonded via recessed mortar ribs."""
    mat_list = [m["breeze_block"], m["stucco_white"]]
    objs: list[bpy.types.Object] = []

    blk_w = 0.320
    blk_h = 0.265
    blk_d = 0.115
    mortar_d = blk_d - 0.032
    rows = 4

    def _build_balcony_tier(name: str, z_base: float, include_south_vents: bool = False) -> bpy.types.Object:
        bm = bmesh.new()
        x_start = NC_X_NORTH - 0.30
        x_end = NC_X_SOUTH + 0.40
        y_front = NC_Y_BALC - 0.04
        bx_s = x_start + 0.16
        bx_e = x_end - 0.16
        n_front = int(round((bx_e - bx_s) / blk_w))
        actual_w = (bx_e - bx_s) / n_front

        for r in range(rows):
            cz = z_base + (r + 0.5) * blk_h
            for i in range(n_front):
                cx = bx_s + (i + 0.5) * actual_w
                gu.add_breeze_block(bm, (cx, y_front, cz), actual_w - 0.008, blk_h - 0.008, blk_d, normal_axis="+Y", mat_idx=0)
        for r in range(rows + 1):
            mz = z_base + r * blk_h
            gu.add_box_bounds(bm, x_start + 0.06, x_end - 0.06, y_front - mortar_d * 0.5, y_front + mortar_d * 0.5, mz - 0.014, mz + 0.014, 1)

        y_ret_start = NC_Y_EAST_WALL + 0.03
        y_ret_end = y_front - 0.12
        n_ret = 4
        ret_w = (y_ret_end - y_ret_start) / n_ret
        for side_x in (x_start + blk_d * 0.5 + 0.01, x_end - blk_d * 0.5 - 0.01):
            for r in range(rows):
                cz = z_base + (r + 0.5) * blk_h
                for j in range(n_ret):
                    cy = y_ret_start + (j + 0.5) * ret_w
                    gu.add_breeze_block(bm, (side_x, cy, cz), ret_w - 0.008, blk_h - 0.008, blk_d, normal_axis="+X", mat_idx=0)
            for r in range(rows + 1):
                mz = z_base + r * blk_h
                gu.add_box_bounds(bm, side_x - mortar_d * 0.5, side_x + mortar_d * 0.5, y_ret_start - 0.042, y_front - 0.01, mz - 0.011, mz + 0.011, 1)

        top_z = z_base + rows * blk_h
        gu.add_box_bounds(bm, x_start - 0.02, x_end + 0.02, y_front - 0.088, y_front + 0.088, top_z - 0.012, top_z + 0.075, 1, bevel=0.010)
        gu.add_box_bounds(bm, x_start - 0.02, x_end + 0.02, y_front - 0.082, y_front + 0.082, z_base - 0.035, z_base + 0.016, 1)
        for sx0, sx1 in [(x_start - 0.015, x_start + 0.155), (x_end - 0.155, x_end + 0.015)]:
            gu.add_box_bounds(bm, sx0, sx1, y_ret_start - 0.068, y_front - 0.08, top_z - 0.008, top_z + 0.070, 1, bevel=0.008)
            gu.add_box_bounds(bm, sx0, sx1, y_ret_start - 0.068, y_front - 0.08, z_base - 0.030, z_base + 0.018, 1)

        for cx in (x_start + 0.075, x_end - 0.075):
            gu.add_box(bm, (cx, y_front, z_base + rows * blk_h * 0.5), (0.148, blk_d + 0.032, rows * blk_h + 0.06), 1, bevel=0.008)

        if include_south_vents:
            vent_ranges = [(-13.2, -11.9), (-9.2, -7.9), (-5.2, -3.9), (-1.2, 0.1)]
            for v0, v1 in vent_ranges:
                n_v = 4
                vw = (v1 - v0) / n_v
                for r in range(2):
                    cz = Z_RF_TOP + 0.24 + (r + 0.5) * 0.23
                    for j in range(n_v):
                        cy = v0 + (j + 0.5) * vw
                        gu.add_breeze_block(bm, (NC_X_SOUTH + 0.22, cy, cz), vw - 0.008, 0.216, 0.12, normal_axis="+X", mat_idx=0)
                for rz in (Z_RF_TOP + 0.24, Z_RF_TOP + 0.47, Z_RF_TOP + 0.70):
                    gu.add_box_bounds(bm, NC_X_SOUTH + 0.18, NC_X_SOUTH + 0.26, v0 - 0.06, v1 + 0.06, rz - 0.014, rz + 0.014, 1)

        return gu.finalize_part(bm, name, col, mat_list, smooth_angle_deg=32.0)

    objs.append(_build_balcony_tier("NewsCafe_Breeze_L2", Z_F2_TOP))
    objs.append(_build_balcony_tier("NewsCafe_Breeze_L3", Z_F3_TOP))
    objs.append(_build_balcony_tier("NewsCafe_Breeze_Roof", Z_RF_TOP, include_south_vents=True))

    bm_pw = bmesh.new()
    pw_y = 7.45
    pw_x0, pw_x1 = -4.55, 0.30
    n_pw = 15
    pww = (pw_x1 - pw_x0) / n_pw
    gu.add_box_bounds(bm_pw, pw_x0 - 0.10, pw_x1 + 0.10, pw_y - 0.08, pw_y + 0.08, Z_F1, Z_F1 + 0.11, 1, bevel=0.008)
    for r in range(4):
        cz = Z_F1 + 0.11 + (r + 0.5) * 0.255
        for i in range(n_pw):
            cx = pw_x0 + (i + 0.5) * pww
            gu.add_breeze_block(bm_pw, (cx, pw_y, cz), pww - 0.008, 0.246, blk_d, normal_axis="+Y", mat_idx=0)
    for r in range(5):
        mz = Z_F1 + 0.11 + r * 0.255
        gu.add_box_bounds(bm_pw, pw_x0 - 0.08, pw_x1 + 0.08, pw_y - mortar_d * 0.5, pw_y + mortar_d * 0.5, mz - 0.014, mz + 0.014, 1)
    gu.add_box_bounds(bm_pw, pw_x0 - 0.12, pw_x1 + 0.12, pw_y - 0.095, pw_y + 0.095, Z_F1 + 1.12, Z_F1 + 1.20, 1, bevel=0.010)
    for ex in (pw_x0 - 0.08, pw_x1 + 0.08):
        gu.add_box_bounds(bm_pw, ex - 0.075, ex + 0.075, pw_y - (blk_d * 0.5 + 0.018), pw_y + (blk_d * 0.5 + 0.018), Z_F1, Z_F1 + 1.22, 1, bevel=0.008)
    objs.append(gu.finalize_part(bm_pw, "NewsCafe_Breeze_Patio", col, mat_list, smooth_angle_deg=32.0))
    return objs


def build_news_cafe_windows(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    """Build high-poly `NewsCafe_Windows`: tilted jalousie windows, corrugated roll-up door, accordion portals & balcony armchairs."""
    bm = bmesh.new()
    mat_list = [
        m["window_glass"], m["aluminum_frame"], m["cafe_mullion"], m["shutter_white"],
        m["boxwood_balcony"], m["column_green"], m["window_jalousie_dark"], m["rattan_cream"],
    ]

    for z_fl in (Z_F2_TOP, Z_F3_TOP):
        zc = z_fl + 1.48
        _add_window_assembly(bm, (-2.65, NC_Y_EAST_WALL, zc), 2.75, 1.68, face_axis="+Y", panes_x=2, jalousie_slats=7, mat_glass=0, mat_frame=1)
        _add_window_assembly(bm, (2.05, NC_Y_EAST_WALL, zc), 2.70, 1.68, face_axis="+Y", panes_x=2, jalousie_slats=7, mat_glass=0, mat_frame=1)
        _add_window_assembly(bm, (4.35, NC_Y_EAST_WALL, z_fl + 1.18), 0.92, 2.24, face_axis="+Y", panes_x=1, jalousie_slats=5, mat_glass=6, mat_frame=1)
        _add_window_assembly(bm, (6.95, NC_Y_EAST_WALL, zc), 2.35, 1.68, face_axis="+Y", panes_x=2, jalousie_slats=7, mat_glass=0, mat_frame=1)

        # Framed boxwood privacy dividers resting EXACTLY FLUSH on balcony deck `z_fl`!
        for div_x in (-0.30, 5.15):
            gu.add_box_bounds(bm, div_x - 0.078, div_x + 0.078, NC_Y_EAST_WALL + 0.002, NC_Y_BALC - 0.145, z_fl + 0.002, z_fl + 2.345, 4)
            gu.add_box_bounds(bm, div_x - 0.095, div_x + 0.095, NC_Y_BALC - 0.16, NC_Y_BALC - 0.10, z_fl, z_fl + 2.37, 5, bevel=0.008)

        # Fully Connected Curved Tubular Hotel Balcony Lounge Armchairs resting EXACTLY FLUSH on `z_fl`!
        for ch_x in (-2.40, 2.20):
            y_b, y_f = NC_Y_EAST_WALL + 0.44, NC_Y_EAST_WALL + 0.98
            # Twin side tubular frames (front leg -> armrest -> rear leg, flush at z_fl!)
            for ldx in (-0.28, 0.28):
                gu.add_spline_tube(
                    bm,
                    [
                        Vector((ch_x + ldx, y_f, z_fl)),
                        Vector((ch_x + ldx, y_f, z_fl + 0.56)),
                        Vector((ch_x + ldx, y_b, z_fl + 0.58)),
                        Vector((ch_x + ldx, y_b, z_fl)),
                    ],
                    0.016, segs=12, substeps=3, mat_idx=5, cap_round=False,
                )
                # Horizontal side seat support rails tucked cleanly inside the 16mm legs (zero coincident cylinder caps!)
                gu.add_cylinder(bm, (ch_x + ldx, y_b + 0.004, z_fl + 0.34), (ch_x + ldx, y_f - 0.004, z_fl + 0.34), 0.013, 0.013, segs=10, mat_idx=5)
                # Rear angled backrest support stanchions rising cleanly from rear armrest bend to top rail!
                gu.add_cylinder(bm, (ch_x + ldx, y_b, z_fl + 0.565), (ch_x + ldx, y_b - 0.06, z_fl + 0.88), 0.013, 0.013, segs=10, mat_idx=5)
            # Cross-rails linking left & right frames cleanly (slightly inset inside side tube centers -> zero welded cap T-junctions!)
            gu.add_cylinder(bm, (ch_x - 0.274, y_f, z_fl + 0.34), (ch_x + 0.274, y_f, z_fl + 0.34), 0.012, 0.012, segs=10, mat_idx=5)
            gu.add_cylinder(bm, (ch_x - 0.274, y_b, z_fl + 0.34), (ch_x + 0.274, y_b, z_fl + 0.34), 0.012, 0.012, segs=10, mat_idx=5)
            gu.add_cylinder(bm, (ch_x - 0.274, y_b - 0.06, z_fl + 0.88), (ch_x + 0.274, y_b - 0.06, z_fl + 0.88), 0.012, 0.012, segs=10, mat_idx=5)
            # Plump beveled seat & reclined backrest cushions resting solidly ON the tubular frame!
            gu.add_box(bm, (ch_x, 0.5 * (y_b + y_f), z_fl + 0.405), (0.54, 0.54, 0.115), 7, bevel=0.032)
            gu.add_box(bm, (ch_x, y_b + 0.02, z_fl + 0.67), (0.53, 0.115, 0.46), 7, rot_euler=(math.radians(-10.0), 0.0, 0.0), bevel=0.032)

    south_specs = [
        (1.65, 2.75, 3, 7), (-1.25, 0.96, 1, 6), (-3.65, 0.96, 1, 6), (-6.10, 0.96, 1, 6),
        (-8.60, 2.70, 3, 7), (-11.45, 0.96, 1, 6), (-13.85, 1.75, 2, 6),
    ]
    for z_fl in (Z_F2_TOP, Z_F3_TOP):
        zc = z_fl + 1.46
        for wy, ww, px, sl in south_specs:
            _add_window_assembly(bm, (NC_X_SOUTH, wy, zc), ww, 1.48, face_axis="+X", panes_x=px, jalousie_slats=sl, mat_glass=0, mat_frame=1)

    for z_fl in (Z_F2_TOP, Z_F3_TOP):
        zc = z_fl + 1.46
        for wy, ww, px in [(1.5, 2.55, 3), (-2.2, 2.45, 3), (-6.2, 2.45, 3), (-10.5, 2.45, 3)]:
            _add_window_assembly(bm, (NC_X_NORTH, wy, zc), ww, 1.44, face_axis="-X", panes_x=px, jalousie_slats=6, mat_glass=0, mat_frame=1)

    # Ground Floor 8th Street Cream-Framed Multi-Pane Cafe Windows
    _add_window_assembly(bm, (NC_X_SOUTH - 0.14, 1.62, Z_F1 + 1.89), 3.72, 1.94, face_axis="+X", panes_x=4, jalousie_slats=3, mat_glass=6, mat_frame=2, frame_t=0.072)
    _add_window_assembly(bm, (NC_X_SOUTH - 0.14, -1.68, Z_F1 + 1.89), 1.56, 1.94, face_axis="+X", panes_x=2, jalousie_slats=3, mat_glass=6, mat_frame=2, frame_t=0.072)
    _add_window_assembly(bm, (NC_X_SOUTH - 0.14, -3.35, Z_F1 + 1.89), 0.76, 1.94, face_axis="+X", panes_x=1, jalousie_slats=3, mat_glass=6, mat_frame=2, frame_t=0.072)
    _add_window_assembly(bm, (NC_X_SOUTH, -9.15, Z_F1 + 1.89), 2.95, 1.94, face_axis="+X", panes_x=3, jalousie_slats=3, mat_glass=0, mat_frame=2, frame_t=0.072)

    # 'the hotel @ 800' White Corrugated Roll-Up Security Door (28 smooth rounded slats + hood box + side guide rails, flush at Z_F1!)
    hx, hy = NC_X_SOUTH + 0.032, -5.65
    gu.add_box(bm, (hx - 0.015, hy, Z_F1 + 1.36), (0.07, 1.50, 2.72), 3)
    for s in range(28):
        sz = Z_F1 + 0.08 + s * 0.092
        gu.add_cylinder(bm, (hx + 0.025, hy - 0.70, sz), (hx + 0.025, hy + 0.70, sz), 0.024, 0.024, segs=10, mat_idx=3)
    gu.add_box(bm, (hx + 0.04, hy - 0.78, Z_F1 + 1.375), (0.16, 0.10, 2.73), 2, bevel=0.008)
    gu.add_box(bm, (hx + 0.04, hy + 0.78, Z_F1 + 1.375), (0.16, 0.10, 2.73), 2, bevel=0.008)
    gu.add_box(bm, (hx + 0.055, hy, Z_F1 + 2.74), (0.20, 1.72, 0.22), 2, bevel=0.012)

    # Ground Floor East Open Accordion Bi-Fold Cafe Doors folded cleanly against piers!
    for px0, px1 in [(-4.52, -0.98), (-0.22, 3.52), (4.28, 8.58)]:
        pc, pw = 0.5 * (px0 + px1), px1 - px0
        gu.add_box(bm, (pc, NC_Y_EAST_WALL - 0.14, Z_F1 + 2.88), (pw + 0.12, 0.14, 0.10), 2, bevel=0.006)
        gu.add_box(bm, (px0 + 0.05, NC_Y_EAST_WALL - 0.14, Z_F1 + 1.44), (0.20, 0.11, 2.86), 2, bevel=0.006)
        gu.add_box(bm, (px1 - 0.05, NC_Y_EAST_WALL - 0.14, Z_F1 + 1.44), (0.20, 0.11, 2.86), 2, bevel=0.006)
        # Folded open bi-fold door leaves angled neatly inside the reveal
        for leaf_x, ang_y in [(px0 + 0.22, 0.35), (px1 - 0.22, -0.35)]:
            gu.add_box(bm, (leaf_x, NC_Y_EAST_WALL - 0.28, Z_F1 + 1.44), (0.05, 0.42, 2.78), 2, rot_euler=(0.0, 0.0, ang_y), bevel=0.004)
            gu.add_box(bm, (leaf_x, NC_Y_EAST_WALL - 0.28, Z_F1 + 1.62), (0.022, 0.32, 1.65), 6, rot_euler=(0.0, 0.0, ang_y))

    return gu.finalize_part(bm, "NewsCafe_Windows", col, mat_list, smooth_angle_deg=36.0)


def _add_scalloped_awning(
    bm: bmesh.types.BMesh,
    uv_layer,
    *,
    p_start: Vector,
    span_vec: Vector,
    proj_vec: Vector,
    z_top: float,
    z_eave: float,
    valance_h: float,
    mat_canvas: int,
    mat_frame: int,
    mat_piping: int,
    add_poles: bool = True,
    z_ground: float = Z_F1,
    thickness: float = 0.026,
) -> None:
    """High-poly realistic canvas awning: subtle catenary sag roof, silky semicircular scallops, 3D piping & side curtains!"""
    s_len = span_vec.length
    s_dir = span_vec.normalized()
    p_len = proj_vec.length
    p_dir = proj_vec.normalized()
    up = Vector((0, 0, 1))
    slope_v = (p_dir * p_len + Vector((0, 0, z_eave - z_top))).normalized()
    slope_n = s_dir.cross(slope_v).normalized()
    if slope_n.z < 0:
        slope_n = -slope_n

    # 1. Subdivided sloped canvas roof panel with natural subtle tension sag between rafters (8 x 4 grid)
    nx_r, ny_r = 8, 4
    t_off = slope_n * (thickness * 0.5)
    grid_t: list[list] = []
    grid_b: list[list] = []
    for ix in range(nx_r + 1):
        u = ix / nx_r
        row_t, row_b = [], []
        for iy in range(ny_r + 1):
            v = iy / ny_r
            sag = -0.026 * math.sin(math.pi * v) * (0.4 + 0.6 * abs(math.sin(math.pi * u * 3.0)))
            pt = p_start + span_vec * u + proj_vec * v + Vector((0, 0, z_top * (1.0 - v) + z_eave * v + sag))
            row_t.append(bm.verts.new(pt + t_off))
            row_b.append(bm.verts.new(pt - t_off))
        grid_t.append(row_t)
        grid_b.append(row_b)

    for ix in range(nx_r):
        for iy in range(ny_r):
            u0, u1 = 0.02 + 0.96 * (ix / nx_r), 0.02 + 0.96 * ((ix + 1) / nx_r)
            v0, v1 = 0.98 - 0.60 * (iy / ny_r), 0.98 - 0.60 * ((iy + 1) / ny_r)
            ft = bm.faces.new((grid_t[ix][iy], grid_t[ix + 1][iy], grid_t[ix + 1][iy + 1], grid_t[ix][iy + 1]))
            fb = bm.faces.new((grid_b[ix][iy + 1], grid_b[ix + 1][iy + 1], grid_b[ix + 1][iy], grid_b[ix][iy]))
            ft.material_index = mat_canvas
            fb.material_index = mat_canvas
            for l, uv in zip(ft.loops, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]):
                l[uv_layer].uv = uv
            for l in fb.loops:
                l[uv_layer].uv = (0.10, 0.72)
    # Close perimeter rims of roof canvas cleanly
    rim_fs = []
    for ix in range(nx_r):
        rim_fs.append(bm.faces.new((grid_b[ix][0], grid_b[ix + 1][0], grid_t[ix + 1][0], grid_t[ix][0])))
        rim_fs.append(bm.faces.new((grid_t[ix][ny_r], grid_t[ix + 1][ny_r], grid_b[ix + 1][ny_r], grid_b[ix][ny_r])))
    for iy in range(ny_r):
        rim_fs.append(bm.faces.new((grid_t[0][iy], grid_t[0][iy + 1], grid_b[0][iy + 1], grid_b[0][iy])))
        rim_fs.append(bm.faces.new((grid_b[nx_r][iy], grid_b[nx_r][iy + 1], grid_t[nx_r][iy + 1], grid_t[nx_r][iy])))
    for rf in rim_fs:
        rf.material_index = mat_canvas
        for l in rf.loops:
            l[uv_layer].uv = (0.10, 0.72)

    # 2. Silky-smooth curved semicircular scalloped valance (`6` curve subdivisions per scallop lobe -> zero sawtooth!)
    scr_right = (-p_dir).cross(up).normalized()
    c2 = p_start + span_vec + proj_vec + Vector((0, 0, z_eave))
    c3 = p_start + proj_vec + Vector((0, 0, z_eave))
    v_left_top, v_right_top = (c2, c3) if s_dir.dot(scr_right) < 0 else (c3, c2)

    n_lobes = max(6, int(round(s_len / 0.24)))
    sub_per_lobe = 6
    n_pts = n_lobes * sub_per_lobe + 1
    n_off = p_dir * (thickness * 0.5)
    top_f, top_b, bot_f, bot_b = [], [], [], []
    pipe_pts: list[Vector] = []
    for k in range(n_pts):
        u_t = k / (n_pts - 1)
        pt_top = v_left_top.lerp(v_right_top, u_t)
        lobe_ph = (u_t * n_lobes) % 1.0
        # Smooth semicircular rounded scallop arch dip (4.2 cm deep!)
        dip = 0.042 * math.sqrt(max(0.0, 1.0 - (2.0 * lobe_ph - 1.0) ** 2))
        pt_bot = pt_top - Vector((0, 0, valance_h + dip))
        pipe_pts.append(pt_bot + p_dir * (thickness * 0.35))
        top_f.append(bm.verts.new(pt_top + n_off))
        top_b.append(bm.verts.new(pt_top - n_off))
        bot_f.append(bm.verts.new(pt_bot + n_off))
        bot_b.append(bm.verts.new(pt_bot - n_off))

    val_other: list[bmesh.types.BMFace] = []
    for k in range(n_pts - 1):
        u0 = 0.02 + 0.96 * (k / (n_pts - 1))
        u1 = 0.02 + 0.96 * ((k + 1) / (n_pts - 1))
        ff = bm.faces.new((bot_f[k], bot_f[k + 1], top_f[k + 1], top_f[k]))
        fb = bm.faces.new((top_b[k], top_b[k + 1], bot_b[k + 1], bot_b[k]))
        ft = bm.faces.new((top_f[k], top_f[k + 1], top_b[k + 1], top_b[k]))
        fbot = bm.faces.new((bot_b[k], bot_b[k + 1], bot_f[k + 1], bot_f[k]))
        ff.material_index = mat_canvas
        for l, uv in zip(ff.loops, [(u0, 0.01), (u1, 0.01), (u1, 0.36), (u0, 0.36)]):
            l[uv_layer].uv = uv
        for fo in (fb, ft, fbot):
            fo.material_index = mat_canvas
            val_other.append(fo)
    for fc in (
        bm.faces.new((bot_b[0], bot_f[0], top_f[0], top_b[0])),
        bm.faces.new((bot_f[-1], bot_b[-1], top_b[-1], top_f[-1])),
    ):
        fc.material_index = mat_canvas
        val_other.append(fc)
    for f_o in val_other:
        for l in f_o.loops:
            l[uv_layer].uv = (0.10, 0.72)

    # 3D stitched white fabric piping tube tracing every curved scallop along the lower hem!
    if mat_canvas == 0:
        f_pipe = gu.add_spline_tube(bm, pipe_pts, 0.008, segs=6, substeps=1, mat_idx=mat_piping)
        for fp in f_pipe:
            for l in fp.loops:
                l[uv_layer].uv = (0.10, 0.72)

    # 3. Realistic triangular canvas side end-flaps closing awning ends (matching Photos 1, 2, 5!)
    for end_u in (0.01, 0.99):
        p_base_end = p_start + span_vec * end_u
        a0 = p_base_end + Vector((0, 0, z_top - 0.01))
        a1 = p_base_end + proj_vec + Vector((0, 0, z_eave - 0.01))
        a2 = p_base_end + Vector((0, 0, z_eave - 0.01))
        e_off = s_dir * (0.010 if end_u < 0.5 else -0.010)
        ef = [bm.verts.new(p + e_off) for p in (a0, a1, a2)]
        eb = [bm.verts.new(p - e_off) for p in (a0, a1, a2)]
        for f_end in (
            bm.faces.new((ef[0], ef[1], ef[2])),
            bm.faces.new((eb[2], eb[1], eb[0])),
            bm.faces.new((eb[0], eb[1], ef[1], ef[0])),
            bm.faces.new((eb[1], eb[2], ef[2], ef[1])),
            bm.faces.new((eb[2], eb[0], ef[0], ef[2])),
        ):
            f_end.material_index = mat_canvas
            for l in f_end.loops:
                l[uv_layer].uv = (0.10, 0.72)

    # 4. Solid Wall Mounting Ledger Bar (flush on building facade -> ZERO sinking!) + Flush Flanged Support Poles!
    ledger_c = p_start + span_vec * 0.5 + Vector((0, 0, z_top - 0.01))
    if abs(p_dir.y) > 0.5:
        gu.add_box(bm, (ledger_c.x, ledger_c.y + p_dir.y * 0.025, ledger_c.z), (s_len + 0.04, 0.05, 0.07), mat_frame)
    else:
        gu.add_box(bm, (ledger_c.x + p_dir.x * 0.025, ledger_c.y, ledger_c.z), (0.05, s_len + 0.04, 0.07), mat_frame)

    if add_poles:
        n_poles = 2 if s_len < 4.0 else 3
        for idx in range(n_poles):
            t = 0.06 if idx == 0 else (0.94 if idx == n_poles - 1 else idx / (n_poles - 1))
            top_pt = p_start + span_vec * t + proj_vec * 0.92 + Vector((0, 0, z_eave))
            # Exact flush circular bolted steel base plate on sidewalk Z = z_ground + 0.0000!
            gu.add_cylinder(bm, (top_pt.x, top_pt.y, z_ground), (top_pt.x, top_pt.y, z_ground + 0.018), 0.064, 0.060, segs=18, mat_idx=mat_frame)
            gu.add_cylinder(bm, (top_pt.x, top_pt.y, z_ground + 0.016), (top_pt.x, top_pt.y, z_ground + 0.052), 0.044, 0.030, segs=16, mat_idx=mat_frame)
            gu.add_cylinder(bm, (top_pt.x, top_pt.y, z_ground + 0.045), top_pt, 0.024, 0.024, segs=16, mat_idx=mat_frame)
    for t in (0.04, 0.35, 0.65, 0.96):
        pa = p_start + span_vec * t + p_dir * 0.02 + Vector((0, 0, z_top - 0.02))
        pb = p_start + span_vec * t + proj_vec * 0.96 + Vector((0, 0, z_eave - 0.02))
        gu.add_cylinder(bm, pa, pb, 0.020, 0.020, segs=12, mat_idx=mat_frame)


def build_news_cafe_awnings(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    mat_list = [m["awning_news_cafe"], m["awning_green_plain"], m["awning_hotel_800"], m["column_green"], m["stucco_white"]]

    # East Ocean Dr hero awnings mounted flush on NC_Y_BALC (projection = 2.13 m -> front poles at exact AWNING_POLE_XY!)
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((-5.45, NC_Y_BALC, 0.0)), span_vec=Vector((7.15, 0.0, 0.0)), proj_vec=Vector((0.0, 2.13, 0.0)),
        z_top=Z_F1 + 3.60, z_eave=Z_F1 + 2.94, valance_h=0.36, mat_canvas=0, mat_frame=3, mat_piping=4, add_poles=True,
    )
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((2.35, NC_Y_BALC, 0.0)), span_vec=Vector((7.20, 0.0, 0.0)), proj_vec=Vector((0.0, 2.13, 0.0)),
        z_top=Z_F1 + 3.60, z_eave=Z_F1 + 2.94, valance_h=0.36, mat_canvas=0, mat_frame=3, mat_piping=4, add_poles=True,
    )
    # 8th St & North wall awnings mounted cleanly flush on facade exterior (`NC_X_SOUTH` / `NC_X_NORTH`)
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((NC_X_SOUTH, -0.35, 0.0)), span_vec=Vector((0.0, 4.00, 0.0)), proj_vec=Vector((1.30, 0.0, 0.0)),
        z_top=Z_F1 + 3.44, z_eave=Z_F1 + 2.74, valance_h=0.34, mat_canvas=0, mat_frame=3, mat_piping=4, add_poles=False,
    )
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((NC_X_SOUTH, -2.60, 0.0)), span_vec=Vector((0.0, 1.82, 0.0)), proj_vec=Vector((1.20, 0.0, 0.0)),
        z_top=Z_F1 + 3.40, z_eave=Z_F1 + 2.76, valance_h=0.30, mat_canvas=1, mat_frame=3, mat_piping=4, add_poles=False,
    )
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((NC_X_SOUTH, -3.85, 0.0)), span_vec=Vector((0.0, 1.00, 0.0)), proj_vec=Vector((1.20, 0.0, 0.0)),
        z_top=Z_F1 + 3.40, z_eave=Z_F1 + 2.76, valance_h=0.30, mat_canvas=1, mat_frame=3, mat_piping=4, add_poles=False,
    )
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((NC_X_SOUTH, -6.75, 0.0)), span_vec=Vector((0.0, 2.20, 0.0)), proj_vec=Vector((1.34, 0.0, 0.0)),
        z_top=Z_F1 + 3.42, z_eave=Z_F1 + 2.74, valance_h=0.34, mat_canvas=2, mat_frame=3, mat_piping=4, add_poles=False,
    )
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((NC_X_SOUTH, -10.90, 0.0)), span_vec=Vector((0.0, 3.45, 0.0)), proj_vec=Vector((1.26, 0.0, 0.0)),
        z_top=Z_F1 + 3.42, z_eave=Z_F1 + 2.76, valance_h=0.32, mat_canvas=1, mat_frame=3, mat_piping=4, add_poles=False,
    )
    _add_scalloped_awning(
        bm, uv_layer,
        p_start=Vector((NC_X_NORTH, -1.50, 0.0)), span_vec=Vector((0.0, 4.80, 0.0)), proj_vec=Vector((-1.02, 0.0, 0.0)),
        z_top=Z_F1 + 3.30, z_eave=Z_F1 + 2.66, valance_h=0.28, mat_canvas=1, mat_frame=3, mat_piping=4, add_poles=False,
    )

    return gu.finalize_part(bm, "NewsCafe_Awnings", col, mat_list, smooth_angle_deg=42.0, preserve_existing_uv=True)


def _add_framed_painting(
    bm: bmesh.types.BMesh,
    uv_layer,
    cx: float,
    wall_y: float,
    cz: float,
    fw: float,
    fh: float,
    tile_col: int,
    tile_row: int,
    *,
    mat_wood: int,
    mat_brass: int,
    mat_matboard: int,
    mat_art: int,
    face_axis: str = "+Y",
) -> None:
    """REAL 3D Modeled Museum Gallery Frame: true 45-deg mitered beveled mahogany frame + brass fillet + 3D recessed mat board + canvas!"""
    rf = 0.046   # outer wood molding width
    df = 0.038   # outer frame projection flush from wall
    rb = 0.012   # gilded brass inner fillet width
    rm = 0.055   # recessed museum mat board border width
    hw, hh = fw * 0.5, fh * 0.5
    mw = fw - 2.0 * (rf + rb) + 0.004
    mh = fh - 2.0 * (rf + rb) + 0.004
    aw = max(0.12, mw - 2.0 * rm + 0.008)
    ah = max(0.12, mh - 2.0 * rm + 0.008)
    u0 = tile_col * 0.25 + 0.006
    u1 = (tile_col + 1) * 0.25 - 0.006
    v0 = (1 - tile_row) * 0.50 + 0.006
    v1 = (2 - tile_row) * 0.50 - 0.006

    if face_axis == "+X":
        # Here `cx` = wall_x, `wall_y` = cy along the north wall!
        gu.add_box_bounds(bm, cx + 0.001, cx + 0.010, wall_y - hw + 0.012, wall_y + hw - 0.012, cz - hh + 0.012, cz + hh - 0.012, mat_wood)
        gu.add_mitered_frame(bm, cx, wall_y, cz, fw, fh, rf, df, mat_idx=mat_wood, front_inset=0.007, step_depth=0.009, face_axis="+X")
        gu.add_mitered_frame(bm, cx + 0.011, wall_y, cz, fw - 2.0 * rf + 0.004, fh - 2.0 * rf + 0.004, rb + 0.002, 0.019, mat_idx=mat_brass, front_inset=0.002, step_depth=0.004, face_axis="+X")
        gu.add_mitered_frame(bm, cx + 0.011, wall_y, cz, mw, mh, rm + 0.002, 0.011, mat_idx=mat_matboard, front_inset=0.002, step_depth=0.003, face_axis="+X")
        gu.add_uv_mapped_sign_plate(
            bm, (cx + 0.013, wall_y, cz), aw, ah, 0.006,
            face_dir="+X", mat_front=mat_art, mat_back=mat_wood, uv_layer=uv_layer, uv_rect=(u0, v0, u1, v1),
        )
    else:
        gu.add_box_bounds(bm, cx - hw + 0.012, cx + hw - 0.012, wall_y + 0.001, wall_y + 0.010, cz - hh + 0.012, cz + hh - 0.012, mat_wood)
        gu.add_mitered_frame(bm, cx, wall_y, cz, fw, fh, rf, df, mat_idx=mat_wood, front_inset=0.007, step_depth=0.009, face_axis="+Y")
        gu.add_mitered_frame(bm, cx, wall_y + 0.011, cz, fw - 2.0 * rf + 0.004, fh - 2.0 * rf + 0.004, rb + 0.002, 0.019, mat_idx=mat_brass, front_inset=0.002, step_depth=0.004, face_axis="+Y")
        gu.add_mitered_frame(bm, cx, wall_y + 0.011, cz, mw, mh, rm + 0.002, 0.011, mat_idx=mat_matboard, front_inset=0.002, step_depth=0.003, face_axis="+Y")
        gu.add_uv_mapped_sign_plate(
            bm, (cx, wall_y + 0.013, cz), aw, ah, 0.006,
            face_dir="+Y", mat_front=mat_art, mat_back=mat_wood, uv_layer=uv_layer, uv_rect=(u0, v0, u1, v1),
        )


def _add_brass_picture_light(
    bm: bmesh.types.BMesh,
    cx: float,
    wall_y: float,
    cz: float,
    mat_brass: int,
    mat_lamp: int,
    *,
    face_axis: str = "+Y",
) -> None:
    """REAL 3D Brass Gooseneck Picture Light mounted flush on wall above gallery frames (supports `+Y` & `+X`!)."""
    if face_axis == "+X":
        gu.add_cylinder(bm, (cx, wall_y, cz), (cx + 0.024, wall_y, cz), 0.048, 0.042, segs=18, mat_idx=mat_brass)
        neck = [
            Vector((cx + 0.018, wall_y, cz)),
            Vector((cx + 0.14, wall_y, cz + 0.055)),
            Vector((cx + 0.23, wall_y, cz + 0.035)),
            Vector((cx + 0.25, wall_y, cz - 0.005)),
        ]
        gu.add_spline_tube(bm, neck, 0.009, segs=10, substeps=3, mat_idx=mat_brass, cap_round=True)
        gu.add_cylinder(bm, (cx + 0.25, wall_y - 0.22, cz - 0.018), (cx + 0.25, wall_y + 0.22, cz - 0.018), 0.022, 0.022, segs=16, mat_idx=mat_brass)
        gu.add_box(bm, (cx + 0.246, wall_y, cz - 0.036), (0.020, 0.38, 0.010), mat_lamp)
    else:
        gu.add_cylinder(bm, (cx, wall_y, cz), (cx, wall_y + 0.024, cz), 0.048, 0.042, segs=18, mat_idx=mat_brass)
        neck = [
            Vector((cx, wall_y + 0.018, cz)),
            Vector((cx, wall_y + 0.14, cz + 0.055)),
            Vector((cx, wall_y + 0.23, cz + 0.035)),
            Vector((cx, wall_y + 0.25, cz - 0.005)),
        ]
        gu.add_spline_tube(bm, neck, 0.009, segs=10, substeps=3, mat_idx=mat_brass, cap_round=True)
        gu.add_cylinder(bm, (cx - 0.22, wall_y + 0.25, cz - 0.018), (cx + 0.22, wall_y + 0.25, cz - 0.018), 0.022, 0.022, segs=16, mat_idx=mat_brass)
        gu.add_box(bm, (cx, wall_y + 0.246, cz - 0.036), (0.38, 0.020, 0.010), mat_lamp)


def _add_luxury_banquette(
    bm: bmesh.types.BMesh,
    cx: float,
    y_back: float,
    z_floor: float,
    width: float,
    *,
    mat_wood: int,
    mat_leather: int,
    mat_brass: int,
) -> None:
    """Sculpted realistic Art Deco restaurant leather banquette (ZERO boxy bricks! Flush on `z_floor`!).

    Features:
      - Recessed mahogany heel toe-kick plinth resting FLUSH at `z_floor`
      - Smooth 14-point lofted ergonomic waterfall plush seat cushion w/ rolled front knee lip & stitched leather welt piping
      - 9 reclined (10-deg) sculpted S-curved half-round vertical channel-tufted leather bolsters curving into plush headrest crest
      - Curved carved mahogany & brass side wing end-cheeks enclosing left & right ends solidly from floor to crest!
    """
    hw = width * 0.5
    depth = 0.78
    cheek_w = 0.058
    inner_hw = hw - cheek_w

    # 1. Recessed mahogany toe-kick plinth (flush on `z_floor`, recessed 9 cm back from front seat edge for real diner legroom!)
    gu.add_box_bounds(bm, cx - inner_hw - 0.004, cx + inner_hw + 0.004, y_back + 0.005, y_back + depth - 0.11, z_floor, z_floor + 0.148, mat_wood, bevel=0.006)
    # Solid upholstered leather lower base apron sitting solidly on plinth (`z = 0.14 .. 0.34`)
    gu.add_box_bounds(bm, cx - inner_hw - 0.003, cx + inner_hw + 0.003, y_back + 0.022, y_back + depth - 0.04, z_floor + 0.142, z_floor + 0.346, mat_leather, bevel=0.014)
    # Finished mahogany rear backing panel flush along `y_back`
    gu.add_box_bounds(bm, cx - hw + 0.004, cx + hw - 0.004, y_back, y_back + 0.045, z_floor + 0.002, z_floor + 1.06, mat_wood, bevel=0.008)

    # 2. Sculpted 14-point Ergonomic Waterfall Plush Seat Cushion (smooth curved loft along X -> ZERO brick corners!)
    #    Cross-section in (local_y from y_back, local_z from z_floor), smooth crowned dome + generous rounded front knee roll!
    seat_yz = [
        (0.06, 0.340), (0.68, 0.340), (0.745, 0.352), (0.778, 0.382),
        (0.786, 0.422), (0.774, 0.458), (0.735, 0.482), (0.640, 0.494),
        (0.460, 0.498), (0.280, 0.488), (0.140, 0.474), (0.060, 0.465),
    ]
    n_xseg = 12
    seat_rings: list[list[Vector]] = []
    for ix in range(n_xseg + 1):
        u = -1.0 + 2.0 * (ix / n_xseg)
        px = cx + u * inner_hw
        # Gentle pillowed soft-edge crown drop near the two side cheeks so cushion looks genuinely plush!
        edge_pill = -0.012 * (u ** 6)
        ring = [Vector((px, y_back + ly, z_floor + lz + (edge_pill if lz > 0.40 else 0.0))) for ly, lz in seat_yz]
        seat_rings.append(ring)
    cap_l = Vector((cx - inner_hw - 0.004, y_back + 0.42, z_floor + 0.42))
    cap_r = Vector((cx + inner_hw + 0.004, y_back + 0.42, z_floor + 0.42))
    gu.add_closed_tube(bm, seat_rings, cap_l, cap_r, mat_idx=mat_leather)

    # Stitched leather piping welt tubes tracing upper & lower front waterfall roll cleanly!
    gu.add_cylinder(bm, (cx - inner_hw, y_back + 0.748, z_floor + 0.476), (cx + inner_hw, y_back + 0.748, z_floor + 0.476), 0.009, 0.009, segs=10, mat_idx=mat_leather)
    gu.add_cylinder(bm, (cx - inner_hw, y_back + 0.748, z_floor + 0.348), (cx + inner_hw, y_back + 0.748, z_floor + 0.348), 0.009, 0.009, segs=10, mat_idx=mat_leather)

    # 3. 9 Reclined (10-deg) Sculpted S-Curved Channel-Tufted Plump Vertical Leather Bolsters!
    n_flutes = 9
    flute_w = (2.0 * inner_hw) / n_flutes
    flute_rx = flute_w * 0.515  # subtle 1.5% tight nest -> crisp deep tufted channel creases with ZERO gaps!
    for k in range(n_flutes):
        fx = (cx - inner_hw) + (k + 0.5) * flute_w
        # Smooth reclined S-lumbar spine from seat tuck (z=0.45) swelling gently out for lumbar support up into curved crest (z=1.07)!
        n_v = 10
        f_rings: list[list[Vector]] = []
        for iv in range(n_v + 1):
            t = iv / n_v
            lz = 0.445 + 0.635 * t
            # Reclined spine leans smoothly backward (y_front = 0.25 at lumbar -> 0.14 at headrest crest!)
            y_base = 0.042 + 0.008 * (1.0 - t)
            lumbar_swell = 0.036 * math.sin(math.pi * (t ** 0.75))
            recline_shift = 0.135 * (1.0 - t)
            depth_t = 0.088 + lumbar_swell + 0.035 * math.sin(math.pi * t)
            y_mid = y_base + recline_shift * 0.55 + depth_t * 0.5
            ry_t = max(0.032, depth_t * 0.62)
            # Rounded half-pillowed cross-section (14 segs around each channel bolster!)
            ring = []
            for j in range(14):
                ang = math.tau * j / 14
                px = fx + flute_rx * math.cos(ang)
                py = y_back + y_mid + ry_t * math.sin(ang)
                ring.append(Vector((px, max(y_back + 0.032, py), z_floor + lz)))
            f_rings.append(ring)
        gu.add_closed_tube(
            bm, f_rings,
            Vector((fx, y_back + 0.14, z_floor + 0.435)),
            Vector((fx, y_back + 0.095, z_floor + 1.095)),
            mat_idx=mat_leather,
        )

    # Continuous plush rolled top headrest bolster crowning all 9 fluted bolsters cleanly!
    gu.add_cylinder(bm, (cx - inner_hw, y_back + 0.092, z_floor + 1.075), (cx + inner_hw, y_back + 0.092, z_floor + 1.075), 0.056, 0.056, segs=18, mat_idx=mat_leather)

    # 4. Sculpted Curved-Profile Mahogany & Brass End-Cheeks enclosing both ends cleanly from floor to crest!
    for sgn in (-1.0, 1.0):
        ex0 = cx + sgn * inner_hw - (cheek_w if sgn < 0 else 0.0)
        ex1 = ex0 + cheek_w
        # Lower curved seat wing + taller tapered backrest cheek (clean beveled Art Deco silhouette, zero coincident corners!)
        gu.add_box_bounds(bm, ex0, ex1, y_back + 0.003, y_back + depth + 0.01, z_floor, z_floor + 0.54, mat_wood, bevel=0.012)
        gu.add_box_bounds(bm, ex0 + 0.002, ex1 - 0.002, y_back + 0.005, y_back + 0.30, z_floor + 0.48, z_floor + 1.12, mat_wood, bevel=0.014)
        # Curved brass armrest cap bead & vertical brass Art Deco inlay strip on the outer cheek face!
        ax = ex1 + 0.002 if sgn > 0 else ex0 - 0.002
        gu.add_cylinder(bm, (0.5 * (ex0 + ex1), y_back + 0.28, z_floor + 0.545), (0.5 * (ex0 + ex1), y_back + depth - 0.01, z_floor + 0.545), 0.016, 0.016, segs=12, mat_idx=mat_brass)
        gu.add_box_bounds(bm, min(ax, ax - sgn * 0.008), max(ax, ax - sgn * 0.008), y_back + 0.14, y_back + 0.175, z_floor + 0.08, z_floor + 1.04, mat_brass)


def _add_swivel_barstool(
    bm: bmesh.types.BMesh,
    x: float,
    y: float,
    z_floor: float,
    *,
    mat_brass: int,
    mat_leather: int,
) -> None:
    """Sculpted brass & oxblood leather swivel barstool w/ ZERO-TWIST connected 4-spoke footrest ring & curved backrest!"""
    # 1. Turned brass trumpet pedestal base resting EXACTLY FLUSH on `z_floor`!
    stool_base_prof = [
        (0.215, 0.000), (0.215, 0.014), (0.190, 0.028), (0.130, 0.056),
        (0.054, 0.095), (0.038, 0.125), (0.033, 0.695), (0.058, 0.710), (0.095, 0.722),
    ]
    gu.add_revolved_profile(bm, (x, y, z_floor), stool_base_prof, segs=24, mat_idx=mat_brass)

    # 2. SEAMLESS ZERO-TWIST ANALYTICAL TORUS FOOTREST RING (`r=0.175`) PHYSICALLY CONNECTED BY 4 RADIAL SPOKES!
    z_ring = z_floor + 0.255
    gu.add_torus_ring(bm, (x, y, z_ring), 0.175, 0.0115, major_segs=32, minor_segs=14, mat_idx=mat_brass)
    # Central turned brass collar hub + 4 radial spokes starting inside hub collar (r=0.024 -> ZERO shared center weld!)
    gu.add_cylinder(bm, (x, y, z_ring - 0.022), (x, y, z_ring + 0.022), 0.044, 0.044, segs=18, mat_idx=mat_brass)
    for k in range(4):
        ang = k * (math.pi * 0.5) + math.pi * 0.25
        p_in = (x + 0.024 * math.cos(ang), y + 0.024 * math.sin(ang), z_ring)
        p_out = (x + 0.174 * math.cos(ang), y + 0.174 * math.sin(ang), z_ring)
        gu.add_cylinder(bm, p_in, p_out, 0.009, 0.0085, segs=10, mat_idx=mat_brass)

    # 3. Smoothly Domed Plush Oxblood Leather Seat Cushion w/ Brass Perimeter Trim Collar!
    seat_prof = [
        (0.165, 0.000), (0.194, 0.012), (0.204, 0.036), (0.202, 0.068),
        (0.184, 0.095), (0.145, 0.108), (0.085, 0.114), (0.015, 0.116),
    ]
    gu.add_revolved_profile(bm, (x, y, z_floor + 0.715), seat_prof, segs=28, mat_idx=mat_leather)
    gu.add_torus_ring(bm, (x, y, z_floor + 0.728), 0.194, 0.008, major_segs=28, minor_segs=10, mat_idx=mat_brass)

    # 4. Curved Low Upholstered Backrest (+Y side) w/ Twin Brass Arms Bolted Flush into Brass Rear Mounting Flanges (ZERO gap!)
    #    At sx=+-0.115 along kidney curve r=0.215: ang = asin(0.115/0.215)=0.564, y_rear = 0.215*cos(0.564)+0.026 = 0.208!
    for sx in (-0.115, 0.115):
        arm = [
            Vector((x + sx * 0.72, y + 0.075, z_floor + 0.716)),
            Vector((x + sx, y + 0.190, z_floor + 0.732)),
            Vector((x + sx, y + 0.214, z_floor + 0.840)),
            Vector((x + sx, y + 0.204, z_floor + 0.955)),
        ]
        gu.add_spline_tube(bm, arm, 0.0095, segs=10, substeps=3, mat_idx=mat_brass, cap_round=True)
        # Beveled brass backrest mounting bracket bolting arm flush onto the rear surface of the curved kidney cushion!
        ang_b = math.asin(sx / 0.215)
        gu.add_box(
            bm, (x + sx, y + 0.203, z_floor + 0.955), (0.044, 0.018, 0.068), mat_brass,
            rot_euler=(0.0, 0.0, -ang_b), bevel=0.004,
        )
    # Curved kidney-shaped padded leather lumbar backrest bar
    b_rings: list[list[Vector]] = []
    for k in range(13):
        u = -1.0 + 2.0 * (k / 12.0)
        ang = u * 0.88
        bx = x + 0.215 * math.sin(ang)
        by = y + 0.215 * math.cos(ang)
        rad = Vector((math.sin(ang), math.cos(ang), 0.0))
        ring = []
        for j in range(12):
            th = math.tau * j / 12
            ring.append(Vector((bx, by, z_floor + 0.955)) + rad * (0.028 * math.cos(th)) + Vector((0, 0, 0.072 * math.sin(th))))
        b_rings.append(ring)
    gu.add_closed_tube(
        bm, b_rings,
        Vector((x - 0.180, y + 0.132, z_floor + 0.955)),
        Vector((x + 0.180, y + 0.132, z_floor + 0.955)),
        mat_idx=mat_leather,
    )


def build_news_cafe_interior(
    col: bpy.types.Collection,
    m: dict,
    *,
    chair_mesh: bpy.types.Mesh | None = None,
) -> list[bpy.types.Object]:
    """Build modular, individually selectable, dedicated-2K-UV `NewsCafe_Interior` asset sets!

    Organized cleanly under `NewsCafe_Interior` sub-collections:
      - `Interior_Architecture` (mahogany wainscoting, plaster walls, crown, ceiling beams & carved mid-room partition -> `int_arch` 2K)
      - `Interior_Bar_Counter` (front paneled mahogany/marble bar, zero-poke brass footrail, credenza, antique mirror & shelves -> `int_bar` 2K)
      - `Interior_Bar_Equipment` (`Bar_Espresso_Machine`, `Bar_Espresso_Grinder`, `Bar_Draft_Tap_Tower`, `Bar_Bottles_Glassware` -> `int_bar_props` 2K)
      - `Interior_Gallery` (`Gallery_Painting_01..10` -> `int_gallery_art` 2K; `Picture_Light_01..06` -> `int_lighting` 2K)
      - `Interior_Banquettes` (`Interior_Banquette_01..06`, shared 2K `Mesh_ArtDeco_Banquette` -> `int_banquette` 2K)
      - `Interior_Barstools` (`Interior_Barstool_01..05`, shared 2K `Mesh_Swivel_Barstool` -> `int_barstool` 2K)
      - `Interior_Dining` (`Interior_Table_01..06` -> `int_dining_table` 2K; `Interior_Chair_01..12` reusing 2K `Mesh_Parisian_Chair_Honey`!)
      - `Interior_Lighting` (`Interior_Pendant_01..10`, shared 2K `Mesh_Brass_Pendant_Light` -> `int_lighting` 2K)
    """
    col_int = gu.sub_collection(col, "NewsCafe_Interior")
    col_eq = gu.sub_collection(col_int, "Interior_Bar_Equipment")
    col_gal = gu.sub_collection(col_int, "Interior_Gallery")
    col_banq = gu.sub_collection(col_int, "Interior_Banquettes")
    col_stools = gu.sub_collection(col_int, "Interior_Barstools")
    col_din = gu.sub_collection(col_int, "Interior_Dining")
    col_lit = gu.sub_collection(col_int, "Interior_Lighting")

    zf = Z_FLOOR_INT
    y_wall = -4.148   # Exact flush interior face of NewsCafe_Shell back wall (-4.150)!
    x_nwall = -4.878  # Exact flush interior face of NewsCafe_Shell north wall (-4.880)!
    out_objs: list[bpy.types.Object] = []

    # 1. `Interior_Architecture` (dedicated 2K `int_arch`): Wall Millwork, Plaster, Ceiling Beams & Carved Mid-Room Partition!
    bm_arch = bmesh.new()
    gu.add_box_bounds(bm_arch, -4.87, 8.91, y_wall, y_wall + 0.022, zf, zf + 1.06, 0)
    gu.add_box_bounds(bm_arch, -4.866, 8.906, y_wall + 0.003, y_wall + 0.044, zf, zf + 0.145, 0, bevel=0.006)
    gu.add_box_bounds(bm_arch, -4.866, 8.906, y_wall + 0.003, y_wall + 0.052, zf + 1.03, zf + 1.09, 0, bevel=0.008)
    gu.add_box_bounds(bm_arch, -4.868, 8.908, y_wall + 0.001, y_wall + 0.018, zf + 1.075, Z_F2_BOT - 0.002, 1)
    gu.add_box_bounds(bm_arch, -4.864, 8.904, y_wall + 0.004, y_wall + 0.095, Z_F2_BOT - 0.11, Z_F2_BOT, 0, bevel=0.010)
    for px in [1.65 + k * 0.72 for k in range(10)]:
        gu.add_box_bounds(bm_arch, px - 0.28, px + 0.28, y_wall + 0.016, y_wall + 0.036, zf + 0.22, zf + 0.94, 0, bevel=0.006)

    gu.add_box_bounds(bm_arch, x_nwall, x_nwall + 0.022, -4.136, 3.65, zf, zf + 1.06, 0)
    gu.add_box_bounds(bm_arch, x_nwall + 0.003, x_nwall + 0.044, -4.132, 3.646, zf, zf + 0.145, 0, bevel=0.006)
    gu.add_box_bounds(bm_arch, x_nwall + 0.003, x_nwall + 0.052, -4.132, 3.646, zf + 1.03, zf + 1.09, 0, bevel=0.008)
    gu.add_box_bounds(bm_arch, x_nwall + 0.001, x_nwall + 0.018, -4.134, 3.648, zf + 1.075, Z_F2_BOT - 0.002, 1)
    gu.add_box_bounds(bm_arch, x_nwall + 0.004, x_nwall + 0.095, -4.130, 3.644, Z_F2_BOT - 0.11, Z_F2_BOT, 0, bevel=0.010)
    for py in [-3.40 + k * 0.78 for k in range(9)]:
        gu.add_box_bounds(bm_arch, x_nwall + 0.016, x_nwall + 0.036, py - 0.30, py + 0.30, zf + 0.22, zf + 0.94, 0, bevel=0.006)

    for bx_c in (-0.60, 3.90):
        gu.add_box_bounds(bm_arch, bx_c - 0.13, bx_c + 0.13, -4.14, 3.66, Z_F2_BOT - 0.16, Z_F2_BOT, 0, bevel=0.008)

    # Carved Mahogany & Brass-Railed Mid-Room Booth Partition Wall (`x = 1.45 .. 8.85`, flush on zf!)
    gu.add_box_bounds(bm_arch, 1.45, 8.85, -0.14, 0.02, zf, zf + 1.18, 0, bevel=0.010)
    gu.add_box_bounds(bm_arch, 1.42, 8.88, -0.17, 0.05, zf + 1.17, zf + 1.24, 0, bevel=0.010)
    gu.add_cylinder(bm_arch, (1.46, -0.06, zf + 1.38), (8.84, -0.06, zf + 1.38), 0.014, 0.014, segs=14, mat_idx=2)
    for dpx in (1.56, 3.90, 6.40, 8.74):
        gu.add_cylinder(bm_arch, (dpx, -0.06, zf + 1.24), (dpx, -0.06, zf + 1.38), 0.011, 0.011, segs=12, mat_idx=2)
        gu.add_quad_sphere(bm_arch, (dpx, -0.06, zf + 1.38), (0.018, 0.018, 0.018), segs=12, rings=6, mat_idx=2)

    out_objs.append(
        gu.finalize_part(
            bm_arch, "Interior_Architecture", col_int,
            [m["mahogany_wood"], m["plaster_interior"], m["brass_warm"]],
            smooth_angle_deg=42.0, asset_set="int_arch",
        )
    )

    # 2. `Interior_Gallery`: 10 INDIVIDUAL Selectable 3D Framed Paintings (`int_gallery_art` 2K) + 6 Instanced Brass Picture Lights!
    y_art_wall = y_wall + 0.018
    x_art_nwall = x_nwall + 0.018
    mat_paint = [m["gallery_art"], m["mahogany_wood"], m["brass_warm"], m["museum_mat"]]

    back_gallery = [
        (2.35, zf + 2.48, 0.92, 0.76, 0, 0),
        (4.15, zf + 2.46, 0.96, 0.74, 1, 0),
        (5.95, zf + 2.48, 0.88, 0.80, 2, 0),
        (7.75, zf + 2.46, 0.94, 0.74, 3, 0),
        (2.40, zf + 1.56, 0.98, 0.66, 0, 1),
        (4.15, zf + 1.58, 0.88, 0.68, 1, 1),
        (5.95, zf + 1.56, 0.92, 0.66, 2, 1),
        (7.70, zf + 1.58, 0.94, 0.68, 3, 1),
    ]
    for p_i, (gcx, gcz, gfw, gfh, tc_i, tr_i) in enumerate(back_gallery, start=1):
        bm_p = bmesh.new()
        uv_p = bm_p.loops.layers.uv.new("UVMap")
        _add_framed_painting(bm_p, uv_p, 0.0, 0.0, 0.0, gfw, gfh, tc_i, tr_i, mat_wood=1, mat_brass=2, mat_matboard=3, mat_art=0, face_axis="+Y")
        out_objs.append(
            gu.finalize_part(
                bm_p, f"Gallery_Painting_{p_i:02d}", col_gal, mat_paint,
                smooth_angle_deg=40.0, preserve_existing_uv=True, location=(gcx, y_art_wall, gcz), yaw_rad=0.0, asset_set="int_gallery_art",
            )
        )
    for n_i, (gcy, gcz, gfw, gfh, tc_i, tr_i) in enumerate([(-1.90, zf + 2.15, 1.02, 0.80, 2, 0), (-0.15, zf + 2.15, 1.06, 0.80, 1, 1)], start=9):
        bm_p = bmesh.new()
        uv_p = bm_p.loops.layers.uv.new("UVMap")
        _add_framed_painting(bm_p, uv_p, 0.0, 0.0, 0.0, gfw, gfh, tc_i, tr_i, mat_wood=1, mat_brass=2, mat_matboard=3, mat_art=0, face_axis="+Y")
        out_objs.append(
            gu.finalize_part(
                bm_p, f"Gallery_Painting_{n_i:02d}", col_gal, mat_paint,
                smooth_angle_deg=40.0, preserve_existing_uv=True, location=(x_art_nwall, gcy, gcz), yaw_rad=-math.pi * 0.5, asset_set="int_gallery_art",
            )
        )

    # Shared Hero Mesh for all 6 Brass Gooseneck Picture Lights (`int_lighting` 2K)!
    bm_pl = bmesh.new()
    _add_brass_picture_light(bm_pl, 0.0, 0.0, 0.0, mat_brass=0, mat_lamp=1, face_axis="+Y")
    me_pic_light = gu.finalize_mesh_data(bm_pl, "Mesh_Brass_Picture_Light", col_gal, [m["brass_warm"], m["warm_lamp"]], smooth_angle_deg=42.0)
    pl_idx = 0
    for lx_pl in (2.35, 4.15, 5.95, 7.75):
        pl_idx += 1
        out_objs.append(gu.spawn_instance(f"Picture_Light_{pl_idx:02d}", me_pic_light, col_gal, (lx_pl, y_art_wall, zf + 3.04), 0.0, asset_set="int_lighting"))
    for gcy in (-1.90, -0.15):
        pl_idx += 1
        out_objs.append(gu.spawn_instance(f"Picture_Light_{pl_idx:02d}", me_pic_light, col_gal, (x_art_nwall, gcy, zf + 2.74), -math.pi * 0.5, asset_set="int_lighting"))

    # 3. `Interior_Bar_Counter` (dedicated 2K `int_bar`): Credenza, Antique Mirror, Shelves, Front Bar & Zero-Poke Brass Footrail!
    bm_bar = bmesh.new()
    gu.add_box_bounds(bm_bar, -4.55, 1.05, y_wall + 0.024, -3.56, zf, zf + 0.942, 0, bevel=0.010)
    gu.add_box_bounds(bm_bar, -4.59, 1.09, y_wall + 0.022, -3.52, zf + 0.940, zf + 0.992, 2, bevel=0.010)
    for dk in range(6):
        dx_c = -4.08 + dk * 0.92
        gu.add_box_bounds(bm_bar, dx_c - 0.39, dx_c + 0.39, -3.565, -3.538, zf + 0.14, zf + 0.86, 0, bevel=0.006)
        gu.add_quad_sphere(bm_bar, (dx_c + 0.28, -3.525, zf + 0.52), (0.016, 0.016, 0.016), segs=12, rings=6, mat_idx=1)

    gu.add_box_bounds(bm_bar, -4.55, 1.05, y_wall + 0.020, y_wall + 0.036, zf + 0.994, zf + 2.98, 3)
    gu.add_box_bounds(bm_bar, -4.58, 1.08, y_wall + 0.022, y_wall + 0.085, zf + 2.92, zf + 3.04, 0, bevel=0.010)
    for pil_x in (-4.52, -2.68, -0.82, 1.02):
        gu.add_box_bounds(bm_bar, pil_x - 0.065, pil_x + 0.065, y_wall + 0.024, y_wall + 0.082, zf + 0.996, zf + 2.935, 0, bevel=0.008)

    for sz in (zf + 1.48, zf + 1.96, zf + 2.44):
        gu.add_box_bounds(bm_bar, -4.44, 0.94, y_wall + 0.036, -3.72, sz - 0.034, sz, 0, bevel=0.005)
        y_rail = -3.755
        z_rail = sz + 0.042
        gu.add_cylinder(bm_bar, (-4.38, y_rail, z_rail), (0.88, y_rail, z_rail), 0.007, 0.007, segs=12, mat_idx=1)
        for st_x in (-4.38, -2.68, -0.82, 0.88):
            gu.add_cylinder(bm_bar, (st_x, y_rail, sz), (st_x, y_rail, z_rail), 0.0055, 0.0055, segs=10, mat_idx=1)
            gu.add_quad_sphere(bm_bar, (st_x, y_rail, z_rail), (0.0115, 0.0115, 0.0115), segs=10, rings=6, mat_idx=1)

    gu.add_box_bounds(bm_bar, -4.18, 0.88, -1.74, -1.06, zf, zf + 0.12, 0)
    gu.add_box_bounds(bm_bar, -4.25, 0.95, -1.78, -1.00, zf + 0.11, zf + 1.04, 0, bevel=0.010)
    for pk in range(5):
        px_b = -3.72 + pk * 1.04
        gu.add_box_bounds(bm_bar, px_b - 0.42, px_b + 0.42, -1.00, -0.975, zf + 0.22, zf + 0.92, 0, bevel=0.008)
    gu.add_box_bounds(bm_bar, -4.32, 1.02, -1.84, -0.88, zf + 1.04, zf + 1.105, 2, bevel=0.016)

    y_fr, z_fr = -0.78, zf + 0.21
    gu.add_cylinder(bm_bar, (-4.18, y_fr, z_fr), (0.88, y_fr, z_fr), 0.022, 0.022, segs=22, mat_idx=1)
    gu.add_quad_sphere(bm_bar, (-4.18, y_fr, z_fr), (0.025, 0.025, 0.025), segs=14, rings=8, mat_idx=1)
    gu.add_quad_sphere(bm_bar, (0.88, y_fr, z_fr), (0.025, 0.025, 0.025), segs=14, rings=8, mat_idx=1)
    for br_x in (-3.92, -2.38, -0.84, 0.68):
        gu.add_cylinder(bm_bar, (br_x - 0.026, y_fr, z_fr), (br_x + 0.026, y_fr, z_fr), 0.028, 0.028, segs=18, mat_idx=1)
        gu.add_cylinder(bm_bar, (br_x, -1.005, z_fr), (br_x, y_fr - 0.004, z_fr), 0.014, 0.014, segs=14, mat_idx=1)
        gu.add_cylinder(bm_bar, (br_x, -1.002, z_fr), (br_x, -0.960, z_fr), 0.036, 0.030, segs=16, mat_idx=1)
        gu.add_cylinder(bm_bar, (br_x, y_fr, zf + 0.014), (br_x, y_fr, z_fr - 0.004), 0.0135, 0.0135, segs=14, mat_idx=1)
        gu.add_cylinder(bm_bar, (br_x, y_fr, zf), (br_x, y_fr, zf + 0.018), 0.038, 0.032, segs=16, mat_idx=1)

    out_objs.append(
        gu.finalize_part(
            bm_bar, "Interior_Bar_Counter", col_int,
            [m["mahogany_wood"], m["brass_warm"], m["marble_top"], m["antique_mirror"]],
            smooth_angle_deg=42.0, asset_set="int_bar",
        )
    )

    # 4. `Interior_Bar_Equipment` (dedicated 2K `int_bar_props`): 4 Distinct Selectable Objects (Espresso, Grinder, Taps, Bottles)!
    z_bar_top = zf + 1.105

    # 4a. Commercial 2-Group Espresso Machine pivoted at (-3.20, -1.45, z_bar_top)
    bm_esp = bmesh.new()
    gu.add_box_bounds(bm_esp, -0.40, 0.40, -0.25, 0.25, 0.000, 0.052, 0, bevel=0.008)
    gu.add_box_bounds(bm_esp, -0.36, 0.36, -0.11, 0.23, 0.048, 0.440, 0, bevel=0.018)
    gu.add_box_bounds(bm_esp, -0.37, 0.37, 0.220, 0.245, 0.360, 0.430, 1, bevel=0.006)
    gu.add_box_bounds(bm_esp, -0.18, 0.18, 0.225, 0.250, 0.160, 0.280, 1, bevel=0.005)
    gu.add_cylinder(bm_esp, (-0.335, 0.21, 0.485), (0.335, 0.21, 0.485), 0.0055, 0.0055, segs=10, mat_idx=1)
    gu.add_cylinder(bm_esp, (-0.335, -0.09, 0.485), (0.335, -0.09, 0.485), 0.0055, 0.0055, segs=10, mat_idx=1)
    for rpx in (-0.34, 0.34):
        gu.add_cylinder(bm_esp, (rpx, -0.085, 0.485), (rpx, 0.205, 0.485), 0.0055, 0.0055, segs=10, mat_idx=1)
        for rpy in (-0.09, 0.21):
            gu.add_cylinder(bm_esp, (rpx, rpy, 0.435), (rpx, rpy, 0.480), 0.007, 0.007, segs=10, mat_idx=1)
            gu.add_quad_sphere(bm_esp, (rpx, rpy, 0.485), (0.0105, 0.0105, 0.0105), segs=10, rings=6, mat_idx=1)
    for cx_cup in (-0.20, 0.00, 0.20):
        for cy_cup in (0.01, 0.13):
            gu.add_cylinder(bm_esp, (cx_cup, cy_cup, 0.440), (cx_cup, cy_cup, 0.450), 0.044, 0.048, segs=14, mat_idx=3)
            gu.add_cylinder(bm_esp, (cx_cup, cy_cup, 0.450), (cx_cup, cy_cup, 0.505), 0.026, 0.032, segs=14, mat_idx=3)
    for gx in (-0.16, 0.16):
        gu.add_cylinder(bm_esp, (gx, -0.16, 0.24), (gx, -0.16, 0.37), 0.046, 0.050, segs=16, mat_idx=0)
        gu.add_cylinder(bm_esp, (gx, -0.16, 0.25), (gx, -0.31, 0.22), 0.011, 0.014, segs=10, mat_idx=2)
    out_objs.append(
        gu.finalize_part(
            bm_esp, "Bar_Espresso_Machine", col_eq,
            [m["stainless_steel"], m["brass_warm"], m["mahogany_wood"], m["ceramic_white"]],
            smooth_angle_deg=42.0, location=(-3.20, -1.45, z_bar_top), asset_set="int_bar_props",
        )
    )

    # 4b. Artisan Conical-Burr Espresso Grinder pivoted at (-2.52, -1.42, z_bar_top)
    bm_gr = bmesh.new()
    gu.add_revolved_profile(bm_gr, (0.0, 0.0, 0.0), [(0.010, 0.0), (0.088, 0.0), (0.086, 0.028), (0.064, 0.055), (0.068, 0.245), (0.045, 0.265)], segs=24, mat_idx=0)
    gu.add_revolved_profile(bm_gr, (0.0, 0.0, 0.262), [(0.042, 0.0), (0.095, 0.145), (0.098, 0.175), (0.090, 0.180)], segs=24, mat_idx=2)
    gu.add_cylinder(bm_gr, (0.0, 0.0, 0.438), (0.0, 0.0, 0.455), 0.099, 0.092, segs=24, mat_idx=1)
    out_objs.append(
        gu.finalize_part(
            bm_gr, "Bar_Espresso_Grinder", col_eq,
            [m["stainless_steel"], m["brass_warm"], m["crystal_glass"]],
            smooth_angle_deg=42.0, location=(-2.52, -1.42, z_bar_top), asset_set="int_bar_props",
        )
    )

    # 4c. Twin Brass Draft Tap Tower pivoted at (-0.60, -1.36, z_bar_top)
    bm_tap = bmesh.new()
    gu.add_cylinder(bm_tap, (0.0, 0.0, 0.0), (0.0, 0.0, 0.36), 0.044, 0.038, segs=20, mat_idx=0)
    gu.add_cylinder(bm_tap, (-0.14, 0.0, 0.36), (0.14, 0.0, 0.36), 0.034, 0.034, segs=18, mat_idx=0)
    for tx_t in (-0.08, 0.08):
        gu.add_cylinder(bm_tap, (tx_t, 0.0, 0.36), (tx_t, -0.12, 0.33), 0.010, 0.008, segs=12, mat_idx=0)
        gu.add_cylinder(bm_tap, (tx_t, -0.09, 0.36), (tx_t, -0.10, 0.50), 0.008, 0.014, segs=12, mat_idx=1)
    out_objs.append(
        gu.finalize_part(
            bm_tap, "Bar_Draft_Tap_Tower", col_eq,
            [m["brass_warm"], m["mahogany_wood"]],
            smooth_angle_deg=42.0, location=(-0.60, -1.36, z_bar_top), asset_set="int_bar_props",
        )
    )

    # 4d. Back-Bar Spirits Bottles & Crystal Glassware Set
    bm_bot = bmesh.new()
    bordeaux_prof = [(0.008, 0.000), (0.035, 0.000), (0.037, 0.015), (0.037, 0.175), (0.031, 0.215), (0.015, 0.240), (0.013, 0.305), (0.015, 0.315), (0.012, 0.320)]
    decanter_prof = [(0.010, 0.000), (0.044, 0.000), (0.048, 0.025), (0.052, 0.095), (0.046, 0.145), (0.018, 0.175), (0.016, 0.215), (0.022, 0.228), (0.016, 0.242)]
    tumbler_prof = [(0.006, 0.000), (0.028, 0.000), (0.034, 0.082), (0.031, 0.082), (0.025, 0.010), (0.006, 0.010)]
    for s_idx, sz in enumerate((zf + 1.48, zf + 1.96, zf + 2.44)):
        for bi in range(18):
            bx = -4.24 + bi * 0.295
            if abs(bx + 2.68) < 0.12 or abs(bx + 0.82) < 0.12:
                continue
            if s_idx == 0 and bi % 4 == 3:
                gu.add_revolved_profile(bm_bot, (bx, -3.89, sz), tumbler_prof, segs=16, mat_idx=2)
                gu.add_revolved_profile(bm_bot, (bx + 0.08, -3.89, sz), tumbler_prof, segs=16, mat_idx=2)
            else:
                prof = decanter_prof if (bi + s_idx) % 3 == 0 else bordeaux_prof
                sc_h = 0.88 + 0.18 * ((bi * 5 + s_idx) % 3) / 2.0
                bm_idx = 0 if (bi + s_idx) % 3 == 0 else (1 if (bi + s_idx) % 3 == 1 else 2)
                gu.add_revolved_profile(bm_bot, (bx, -3.91, sz), [(r, z * sc_h) for r, z in prof], segs=16, mat_idx=bm_idx)
    out_objs.append(
        gu.finalize_part(
            bm_bot, "Bar_Bottles_Glassware", col_eq,
            [m["bottle_amber"], m["bottle_emerald"], m["crystal_glass"]],
            smooth_angle_deg=42.0, asset_set="int_bar_props",
        )
    )

    # 5. `Interior_Barstools`: 5 Instanced Swivel Brass & Leather Barstools (shared 2K `Mesh_Swivel_Barstool` -> 5x sharper!)
    bm_bs = bmesh.new()
    _add_swivel_barstool(bm_bs, 0.0, 0.0, 0.0, mat_brass=0, mat_leather=1)
    me_barstool = gu.finalize_mesh_data(bm_bs, "Mesh_Swivel_Barstool", col_stools, [m["brass_warm"], m["banquette_red"]], smooth_angle_deg=44.0)
    for b_i, bs_x in enumerate((-3.65, -2.60, -1.55, -0.50, 0.55), start=1):
        out_objs.append(gu.spawn_instance(f"Interior_Barstool_{b_i:02d}", me_barstool, col_stools, (bs_x, -0.28, zf), 0.0, asset_set="int_barstool"))

    # 6. `Interior_Banquettes`: 6 Instanced Luxury Art Deco Leather Banquettes (shared 2K `Mesh_ArtDeco_Banquette` -> 6x sharper!)
    bm_bq = bmesh.new()
    _add_luxury_banquette(bm_bq, 0.0, 0.0, 0.0, width=1.96, mat_wood=0, mat_leather=1, mat_brass=2)
    me_banq = gu.finalize_mesh_data(bm_bq, "Mesh_ArtDeco_Banquette", col_banq, [m["mahogany_wood"], m["banquette_red"], m["brass_warm"]], smooth_angle_deg=44.0)

    # 7. `Interior_Dining`: 6 Instanced Quad-Flow Indoor Dining Tables (shared 2K) + 12 Instanced Honey Parisian Chairs!
    bm_it = bmesh.new()
    table_ped_prof = [
        (0.020, 0.000), (0.120, 0.000), (0.245, 0.000), (0.245, 0.018), (0.215, 0.036), (0.140, 0.068),
        (0.058, 0.115), (0.044, 0.675), (0.088, 0.706), (0.020, 0.706),
    ]
    int_votive_prof = [
        (0.008, 0.000), (0.026, 0.000), (0.029, 0.035), (0.031, 0.072),
        (0.028, 0.074), (0.024, 0.068), (0.020, 0.016), (0.008, 0.016),
    ]
    int_plate_prof = [
        (0.014, 0.000), (0.045, 0.000), (0.072, 0.000), (0.095, 0.012),
        (0.110, 0.019), (0.108, 0.022), (0.090, 0.015), (0.064, 0.0075), (0.014, 0.0075),
    ]
    gu.add_revolved_profile(bm_it, (0.0, 0.0, 0.0), table_ped_prof, segs=24, mat_idx=0)
    gu.add_quad_grid_box(bm_it, (0.0, 0.0, 0.722), (1.36, 0.76, 0.040), 1, segs_xyz=(8, 6, 2), round_r=0.010)
    gu.add_quad_grid_box(bm_it, (0.0, 0.0, 0.720), (1.385, 0.785, 0.022), 2, segs_xyz=(8, 6, 2), round_r=0.005)
    gu.add_revolved_profile(bm_it, (0.0, 0.0, 0.742), int_votive_prof, segs=24, mat_idx=2)
    gu.add_quad_sphere(bm_it, (0.0, 0.0, 0.742 + 0.082), (0.008, 0.008, 0.016), segs=12, rings=8, mat_idx=3)
    for sdx in (-0.34, 0.34):
        gu.add_revolved_profile(bm_it, (sdx, -0.18, 0.742), int_plate_prof, segs=24, mat_idx=4)
        gu.add_revolved_profile(bm_it, (sdx, +0.18, 0.742), int_plate_prof, segs=24, mat_idx=4)
        gu.add_quad_grid_box(bm_it, (sdx + 0.15, -0.18, 0.742 + 0.0065), (0.078, 0.138, 0.013), 5, segs_xyz=(4, 6, 2), round_r=0.003)
    me_int_table = gu.finalize_mesh_data(
        bm_it, "Mesh_Interior_Dining_Table", col_din,
        [m["mahogany_wood"], m["marble_top"], m["brass_warm"], m["warm_lamp"], m["ceramic_white"], m["linen_napkin"]],
        smooth_angle_deg=42.0,
    )

    if chair_mesh is None:
        bm_ic = bmesh.new()
        gu.add_parisian_bistro_chair(bm_ic, 0.0, 0.0, 0.0, 0.0, mat_frame=0, mat_weave=1, mat_brass=2)
        chair_mesh = gu.finalize_mesh_data(bm_ic, "Mesh_Parisian_Chair_Honey", col_din, [m["chair_frame"], m["rattan_weave"], m["brass_warm"]], smooth_angle_deg=44.0)

    bq_i, ic_i = 0, 0
    for row_y_back in (y_wall + 0.038, 0.020):
        for bx in (2.65, 5.15, 7.65):
            bq_i += 1
            ty = row_y_back + 1.16
            out_objs.append(gu.spawn_instance(f"Interior_Banquette_{bq_i:02d}", me_banq, col_banq, (bx, row_y_back, zf), 0.0, asset_set="int_banquette"))
            out_objs.append(gu.spawn_instance(f"Interior_Table_{bq_i:02d}", me_int_table, col_din, (bx, ty, zf), 0.0, asset_set="int_dining_table"))
            for sdx in (-0.34, 0.34):
                ic_i += 1
                out_objs.append(gu.spawn_instance(f"Interior_Chair_{ic_i:02d}", chair_mesh, col_din, (bx + sdx, ty + 0.58, zf), math.pi, asset_set="chair_honey"))

    # 8. `Interior_Lighting`: 10 Instanced Brass & Opal Glass Dome Pendant Lights (shared 2K `Mesh_Brass_Pendant_Light`!)
    bm_pd = bmesh.new()
    shade_prof = [(0.042, 0.18), (0.062, 0.14), (0.145, 0.08), (0.195, 0.01), (0.184, 0.0)]
    gu.add_cylinder(bm_pd, (0.0, 0.0, -0.032), (0.0, 0.0, 0.0), 0.056, 0.068, segs=18, mat_idx=0)
    gu.add_cylinder(bm_pd, (0.0, 0.0, -0.500), (0.0, 0.0, -0.025), 0.011, 0.011, segs=12, mat_idx=0)
    gu.add_revolved_profile(bm_pd, (0.0, 0.0, -0.660), shade_prof, segs=24, mat_idx=0)
    gu.add_quad_sphere(bm_pd, (0.0, 0.0, -0.670), (0.082, 0.082, 0.092), segs=16, rings=10, mat_idx=1)
    me_pendant = gu.finalize_mesh_data(bm_pd, "Mesh_Brass_Pendant_Light", col_lit, [m["brass_warm"], m["warm_lamp"]], smooth_angle_deg=42.0)

    pd_i = 0
    for px in (-3.2, -0.8, 2.65, 5.15, 7.65):
        for py in (-1.35, 1.85):
            pd_i += 1
            out_objs.append(gu.spawn_instance(f"Interior_Pendant_{pd_i:02d}", me_pendant, col_lit, (px, py, Z_F2_BOT), 0.0, asset_set="int_lighting"))

    return out_objs


def build_neighbor_804(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    """Build high-poly `Neighbor_804`: beveled classical pediments, overlapping Mission S-tiles, paneled French doors & carriage lanterns."""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    mat_list = [
        m["olive_804"], m["tan_804"], m["stucco_white"], m["spanish_tile"],
        m["window_glass"], m["mahogany_wood"], m["sign_804"], m["cedar_planter"], m["warm_lamp"], m["brass_warm"], m["cast_iron"],
    ]

    x_n, x_s = -16.76, -6.50
    x_mid_n, x_mid_s = -12.75, -10.55
    y_w, y_e = -12.00, 4.15
    z_top = Z_F1 + 7.45

    gu.add_box_bounds(bm, x_n, x_mid_n, y_w, y_e, Z_F1, z_top, 0)
    gu.add_box_bounds(bm, x_mid_s, x_s, y_w, y_e, Z_F1, z_top, 0)
    gu.add_box_bounds(bm, x_mid_n - 0.06, x_mid_s + 0.06, y_w + 0.02, y_e - 0.55, Z_F1, z_top - 0.35, 1)

    # Stepped beveled white roof coping cornices
    gu.add_box_bounds(bm, x_n - 0.04, x_mid_n + 0.06, y_w + 0.01, y_e + 0.09, z_top - 0.14, z_top + 0.06, 2, bevel=0.012)
    gu.add_box_bounds(bm, x_mid_s - 0.06, x_s + 0.06, y_w + 0.01, y_e + 0.09, z_top - 0.14, z_top + 0.06, 2, bevel=0.012)
    gu.add_box_bounds(bm, x_mid_n - 0.02, x_mid_s + 0.02, y_w + 0.03, y_e - 0.48, z_top - 0.42, z_top - 0.28, 2, bevel=0.010)

    for wx_c in (-14.78, -8.52):
        # Classical stepped beveled window pediment w/ lower dentil ledge & sloped raking cornice
        gu.add_box(bm, (wx_c, y_e + 0.08, Z_F1 + 6.32), (2.82, 0.22, 0.14), 2, bevel=0.012)
        gu.add_box(bm, (wx_c, y_e + 0.05, Z_F1 + 6.22), (2.68, 0.14, 0.08), 2, bevel=0.008)
        tri = [(-1.32, 0.0), (1.32, 0.0), (0.0, 0.54)]
        va = [bm.verts.new((wx_c + dx, y_e - 0.02, Z_F1 + 6.38 + dz)) for dx, dz in tri]
        vb = [bm.verts.new((wx_c + dx, y_e + 0.15, Z_F1 + 6.38 + dz)) for dx, dz in tri]
        for f in [
            bm.faces.new((va[0], va[2], va[1])),
            bm.faces.new((vb[0], vb[1], vb[2])),
            bm.faces.new((va[0], va[1], vb[1], vb[0])),
            bm.faces.new((va[1], va[2], vb[2], vb[1])),
            bm.faces.new((va[2], va[0], vb[0], vb[2])),
        ]:
            f.material_index = 2
        # Sloped pediment raking cornice molding bars
        for side_s in (-1.0, 1.0):
            gu.add_box(bm, (wx_c + side_s * 0.68, y_e + 0.11, Z_F1 + 6.68), (1.48, 0.22, 0.08), 2, rot_euler=(0.0, math.radians(side_s * 22.0), 0.0), bevel=0.008)

        _add_window_assembly(bm, (wx_c, y_e, Z_F1 + 5.18), 2.35, 1.62, face_axis="+Y", panes_x=2, jalousie_slats=3, mat_glass=4, mat_frame=2, frame_t=0.06)
        _add_window_assembly(bm, (wx_c, y_e, Z_F1 + 1.88), 2.95, 2.08, face_axis="+Y", panes_x=1, jalousie_slats=0, mat_glass=4, mat_frame=5, frame_t=0.075)
        gu.add_uv_mapped_sign_plate(bm, (wx_c, y_e + 0.056, Z_F1 + 1.92), 1.56, 1.42, 0.038, face_dir="+Y", mat_front=6, mat_back=5, uv_layer=uv_layer)

    # Center tan recess: upper windows + rich paneled mahogany French double doors + hexagonal wrought-iron carriage lanterns!
    y_cen = y_e - 0.55
    for cx_w in (-12.05, -11.25):
        _add_window_assembly(bm, (cx_w, y_cen, Z_F1 + 5.20), 0.58, 1.15, face_axis="+Y", panes_x=1, jalousie_slats=2, mat_glass=4, mat_frame=2, frame_t=0.045)

    gu.add_box(bm, (-11.65, y_cen + 0.05, Z_F1 + 1.39), (1.64, 0.15, 2.78), 5, bevel=0.010)
    for dx_p in (-0.36, 0.36):
        # Beveled recessed raised lower door kick panel
        gu.add_box(bm, (-11.65 + dx_p, y_cen + 0.132, Z_F1 + 0.52), (0.50, 0.030, 0.66), 5, bevel=0.012)
        gu.add_box(bm, (-11.65 + dx_p, y_cen + 0.132, Z_F1 + 1.72), (0.52, 0.024, 1.46), 4)
        gu.add_box(bm, (-11.65 + dx_p, y_cen + 0.150, Z_F1 + 1.72), (0.036, 0.022, 1.44), 5, bevel=0.004)
        for gz in (1.28, 1.72, 2.16):
            gu.add_box(bm, (-11.65 + dx_p, y_cen + 0.152, Z_F1 + gz), (0.52, 0.018, 0.032), 5, bevel=0.004)
        hx_pull = -11.65 + (0.06 if dx_p > 0 else -0.06)
        gu.add_cylinder(bm, (hx_pull, y_cen + 0.175, Z_F1 + 1.05), (hx_pull, y_cen + 0.175, Z_F1 + 1.32), 0.014, 0.014, segs=12, mat_idx=9)
        gu.add_cylinder(bm, (hx_pull, y_cen + 0.10, Z_F1 + 1.18), (hx_pull, y_cen + 0.18, Z_F1 + 1.18), 0.012, 0.012, segs=10, mat_idx=9)

    # Twin Hexagonal Spanish Wrought-Iron Wall Carriage Lanterns w/ Curved Scroll Brackets & Pyramidal Caps!
    for sx in (-12.56, -10.74):
        gu.add_box(bm, (sx, y_cen + 0.02, Z_F1 + 2.02), (0.09, 0.04, 0.24), 10, bevel=0.006)
        gu.add_spline_tube(
            bm,
            [Vector((sx, y_cen + 0.03, Z_F1 + 1.94)), Vector((sx, y_cen + 0.14, Z_F1 + 1.98)), Vector((sx, y_cen + 0.20, Z_F1 + 2.18))],
            0.013, segs=8, substeps=3, mat_idx=10,
        )
        gu.add_cylinder(bm, (sx, y_cen + 0.20, Z_F1 + 1.88), (sx, y_cen + 0.20, Z_F1 + 2.15), 0.068, 0.088, segs=6, mat_idx=8)
        gu.add_cylinder(bm, (sx, y_cen + 0.20, Z_F1 + 2.14), (sx, y_cen + 0.20, Z_F1 + 2.26), 0.105, 0.015, segs=6, mat_idx=10)
        gu.add_cylinder(bm, (sx, y_cen + 0.20, Z_F1 + 1.82), (sx, y_cen + 0.20, Z_F1 + 1.89), 0.022, 0.075, segs=6, mat_idx=10)

    # Stepped beveled terracotta entrance porch (EXACT flush on Z_F1!)
    gu.add_box_bounds(bm, -12.68, -10.62, y_cen - 0.015, y_e + 0.72, Z_F1, Z_F1 + 0.14, 3, bevel=0.012)
    gu.add_box_bounds(bm, -12.55, -10.75, y_cen - 0.010, y_e + 0.32, Z_F1 + 0.11, Z_F1 + 0.24, 3, bevel=0.012)

    # Authentic Overlapping Spanish Mission Terracotta Barrel Tiles (3 stepped overlapping rows x 12 barrel ribs!)
    # Sloped mahogany soffit roof backing tilted cleanly DOWN toward +Y (-18 deg!) underneath the barrel tiles!
    gu.add_box(bm, (-11.65, y_e + 0.06, Z_F1 + 3.16), (2.40, 1.30, 0.075), 5, rot_euler=(math.radians(-18.0), 0.0, 0.0), bevel=0.008)
    # Terracotta upper wall-flashing cap beam tucked smoothly at the top ridge against the tan wall
    gu.add_box(bm, (-11.65, y_e - 0.56, Z_F1 + 3.50), (2.44, 0.14, 0.12), 3, bevel=0.014)
    for row_i in range(3):
        ry0 = (y_e - 0.56) + row_i * 0.40
        ry1 = ry0 + 0.44
        rz0 = Z_F1 + 3.46 - row_i * 0.130
        rz1 = rz0 - 0.138
        for k in range(12):
            tx = -12.74 + k * 0.198
            gu.add_cylinder(bm, (tx, ry0, rz0), (tx, ry1, rz1), 0.068, 0.074, segs=14, mat_idx=3)
            # Alternating concave lower valley tiles between cap ridges
            if k < 11:
                gu.add_cylinder(bm, (tx + 0.099, ry0, rz0 - 0.038), (tx + 0.099, ry1, rz1 - 0.038), 0.044, 0.048, segs=10, mat_idx=3)

    # Slatted Cedar Planter Boxes w/ Corner Trim Molding & Top Lip (EXACT flush on Z_F1!)
    for px, py in [(-6.35, 4.95), (-6.35, 6.25), (-7.15, 7.25)]:
        gu.add_box_bounds(bm, px - 0.32, px + 0.32, py - 0.44, py + 0.44, Z_F1, Z_F1 + 0.70, 7, bevel=0.010)
        gu.add_box_bounds(bm, px - 0.36, px + 0.36, py - 0.48, py + 0.48, Z_F1 + 0.68, Z_F1 + 0.745, 7, bevel=0.012)
        for sz_sl in (0.14, 0.30, 0.46, 0.60):
            gu.add_box(bm, (px, py, Z_F1 + sz_sl), (0.67, 0.91, 0.022), 7, bevel=0.004)

    return gu.finalize_part(bm, "Neighbor_804", col, mat_list, smooth_angle_deg=38.0, preserve_existing_uv=True)


def build_neighbor_820(col: bpy.types.Collection, m: dict) -> bpy.types.Object:
    """Build high-poly `Neighbor_820`: TRUE 20-seg semicircular royal-blue Art Deco arch, downward-sloped blue hoods & flush pickets!"""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    mat_list = [m["stucco_white"], m["blue_820"], m["blue_awning_820"], m["window_glass"], m["sign_fdc"], m["cast_iron"], m["warm_lamp"]]

    x_n, x_s = -22.50, -16.82
    y_w, y_e = -12.00, 4.75
    z_top = Z_F1 + 9.20

    gu.add_box_bounds(bm, x_n, x_s, y_w, y_e, Z_F1, z_top, 0)
    gu.add_box_bounds(bm, -19.20, x_s - 0.01, 1.80, y_e - 0.01, z_top - 0.12, z_top + 1.45, 0, bevel=0.015)
    gu.add_box_bounds(bm, -19.35, x_s + 0.025, 1.65, y_e + 0.12, z_top + 1.32, z_top + 1.56, 1, bevel=0.014)

    for bz in (Z_F1 + 3.92, Z_F1 + 7.22, z_top - 0.14):
        gu.add_box_bounds(bm, x_n - 0.04, x_s + 0.028, y_w + 0.02, y_e + 0.10, bz, bz + 0.18, 1, bevel=0.010)

    _add_window_assembly(bm, (-19.65, y_e, Z_F1 + 5.75), 3.20, 1.85, face_axis="+Y", panes_x=3, jalousie_slats=3, mat_glass=3, mat_frame=0, frame_t=0.06)
    # Downward-sloped royal-blue upper & lower awnings (`-22 deg` / `-18 deg` tilting cleanly down toward Ocean Dr!)
    gu.add_box(bm, (-19.65, y_e + 0.50, Z_F1 + 6.92), (3.45, 1.15, 0.10), 2, rot_euler=(math.radians(-22.0), 0.0, 0.0), bevel=0.020)
    # Smooth 24-seg oval royal-blue Art Deco architectural medallion above arch (Photo 4!)
    gu.add_cylinder(bm, (-19.65, y_e, Z_F1 + 4.35), (-19.65, y_e + 0.10, Z_F1 + 4.35), 0.30, 0.28, segs=24, mat_idx=1)

    gu.add_box(bm, (-19.65, y_e + 0.85, Z_F1 + 3.45), (5.55, 1.85, 0.12), 2, rot_euler=(math.radians(-18.0), 0.0, 0.0), bevel=0.018)
    _add_window_assembly(bm, (-19.85, y_e, Z_F1 + 1.80), 3.64, 2.22, face_axis="+Y", panes_x=3, jalousie_slats=3, mat_glass=3, mat_frame=0, frame_t=0.075)

    # ICONIC 20-Segment Curved Royal-Blue Semicircular Art Deco Arch Surround (flush on Z_F1!)
    arch_cx, arch_z_spring, arch_rx, arch_rz = -19.84, Z_F1 + 2.25, 2.02, 0.92
    arch_pts = [
        Vector((arch_cx + arch_rx * math.cos(math.pi * (1.0 - k / 20.0)), y_e + 0.09, arch_z_spring + arch_rz * math.sin(math.pi * (1.0 - k / 20.0))))
        for k in range(21)
    ]
    gu.add_spline_tube(bm, arch_pts, 0.105, segs=12, substeps=1, mat_idx=1)
    gu.add_box_bounds(bm, -17.90, -17.71, y_e, y_e + 0.15, Z_F1, arch_z_spring + 0.04, 1, bevel=0.010)
    gu.add_box_bounds(bm, -21.93, -21.74, y_e, y_e + 0.15, Z_F1, arch_z_spring + 0.04, 1, bevel=0.010)

    # Royal-blue picket fence resting EXACTLY FLUSH on `Z_F1` w/ sculpted rounded-dome picket tips!
    gu.add_box_bounds(bm, -21.85, -17.75, y_e + 0.12, y_e + 0.20, Z_F1 + 0.20, Z_F1 + 0.28, 1, bevel=0.008)
    gu.add_box_bounds(bm, -21.85, -17.75, y_e + 0.12, y_e + 0.20, Z_F1 + 0.86, Z_F1 + 0.94, 1, bevel=0.008)
    for k in range(18):
        px = -21.75 + k * 0.23
        gu.add_box_bounds(bm, px - 0.039, px + 0.039, y_e + 0.138, y_e + 0.192, Z_F1, Z_F1 + 1.09, 1, bevel=0.006)
        gu.add_cylinder(bm, (px, y_e + 0.138, Z_F1 + 1.09), (px, y_e + 0.192, Z_F1 + 1.09), 0.039, 0.039, segs=12, mat_idx=1)

    # Crisp red 'FDC' plaque + black wrought-iron outdoor wall sconce beside it (Photo 4!)
    gu.add_uv_mapped_sign_plate(bm, (-17.28, y_e + 0.012, Z_F1 + 1.98), 0.34, 0.34, 0.036, face_dir="+Y", mat_front=4, mat_back=0, uv_layer=uv_layer)
    gu.add_box(bm, (-17.28, y_e + 0.06, Z_F1 + 2.52), (0.11, 0.14, 0.22), 5, bevel=0.008)
    gu.add_box(bm, (-17.28, y_e + 0.12, Z_F1 + 2.50), (0.07, 0.04, 0.14), 6)

    return gu.finalize_part(bm, "Neighbor_820", col, mat_list, smooth_angle_deg=38.0, preserve_existing_uv=True)
