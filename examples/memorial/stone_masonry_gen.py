"""Physically Simulated Rock-Faced Quarry Masonry Texture Generator for the Arlington Lockerbie Cairn.

Models REAL hand-pitched Scottish Corsehill sandstone (`crop_plaque_stone.png`) via 3D intersecting
cleavage planes + conchoidal pitching-chisel spall scoops (smooth_min of strongly tilted, organically
warped 3D planes — creating BIG broad 30-55 deg angular cleaved facets, bold dark downward-facing
rock slopes, chunky irregular pitched margins, crisp narrow mortar joints, and gritty sandstone grain):
  - ZERO tiny Voronoi cobblestones
  - ZERO smooth clay blobs
  - ZERO hairline scratches or mechanical picture-frame bevels!

Channel contract for `*_detail_srgb.png` (loaded as sRGB -> feeds ONLY Base Color -> 0 QA warnings!):
  - R: Per-block mineral hue/value + sedimentary bedding + coarse/fine quartz sandstone grain
  - G: Physical hemispherical sky-horizon AO + bold top-lit facet shading + subtle ridge highlight
  - B: Razor-thin straight recessed mortar joint mask (`0.0` = mortar, `1.0` = stone)
"""
from __future__ import annotations

import math
import os
import numpy as np
from PIL import Image

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TEX_SRC_DIR = os.path.join(THIS_DIR, "textures_src")


def _tileable_fbm(
    h: int,
    w: int,
    seed: int,
    octaves: list[tuple[int, int, float]],
    tile_x: bool = True,
) -> np.ndarray:
    """Fast deterministic multi-octave fractal noise in [0, 1] using PIL + NumPy."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), dtype=np.float32)
    tot = 0.0
    for gh, gw, amp in octaves:
        raw = rng.random((gh, gw), dtype=np.float32)
        if tile_x and gw >= 4:
            pad_raw = np.concatenate([raw[:, -2:], raw, raw[:, :2]], axis=1)
            im = Image.fromarray((pad_raw * 255.0).astype(np.uint8), mode="L")
            pw = int(round(w * (gw + 4) / gw))
            arr = np.asarray(im.resize((pw, h), Image.Resampling.BICUBIC), dtype=np.float32) / 255.0
            pad_px = int(round(w * 2 / gw))
            layer = arr[:, pad_px : pad_px + w]
            if layer.shape[1] != w:
                layer = np.asarray(
                    Image.fromarray((layer * 255.0).astype(np.uint8), mode="L").resize((w, h), Image.Resampling.BILINEAR),
                    dtype=np.float32,
                ) / 255.0
        else:
            im = Image.fromarray((raw * 255.0).astype(np.uint8), mode="L")
            layer = np.asarray(im.resize((w, h), Image.Resampling.BICUBIC), dtype=np.float32) / 255.0
        acc += layer * amp
        tot += amp
    return np.clip(acc / max(tot, 1e-6), 0.0, 1.0)


def _lin_to_srgb_u8(x: np.ndarray) -> np.ndarray:
    """Encode true linear [0, 1] signal as sRGB uint8 so Blender sRGB->Linear decode recovers exact linear values!"""
    x = np.clip(x, 0.0, 1.0).astype(np.float32)
    srgb = np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.maximum(x, 1e-7), 1.0 / 2.4) - 0.055)
    return np.clip(np.round(srgb * 255.0), 0, 255).astype(np.uint8)


def _srgb_u8_to_lin(u8: np.ndarray) -> np.ndarray:
    x = u8.astype(np.float32) / 255.0
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4)).astype(np.float32)


def _save_detail_srgb(path: str, g_lin: np.ndarray, cavity_lin: np.ndarray, mortar_lin: np.ndarray) -> None:
    rgb = np.stack([_lin_to_srgb_u8(g_lin), _lin_to_srgb_u8(cavity_lin), _lin_to_srgb_u8(mortar_lin)], axis=-1)
    Image.fromarray(rgb, mode="RGB").save(path, format="PNG")


def _smoothstep(edge0, edge1, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / np.maximum(edge1 - edge0, 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _smin(a: np.ndarray, b: np.ndarray, k: float = 0.035) -> np.ndarray:
    """Polynomial smooth-minimum (crisp angular quarry fracture ridge where two stone planes intersect!)."""
    h = np.clip(0.5 + 0.5 * (b - a) / max(k, 1e-5), 0.0, 1.0)
    return b * (1.0 - h) + a * h - k * h * (1.0 - h)


def _smax(a: np.ndarray, b: np.ndarray, k: float = 0.035) -> np.ndarray:
    return -_smin(-a, -b, k)


def _sculpt_single_rock_block(
    bh: int,
    bw: int,
    seed: int,
    *,
    num_bosses: int = 3,
    num_spalls: int = 5,
    granite_mode: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sculpt ONE chunky, hand-pitched rock-faced stone block `(bh, bw)` via 3D intersecting cleavage planes!

    Each block consists of 2-3 bold irregular protruding rock ridges carved by 4-6 BIG angular
    pitching-chisel fracture planes (creating broad upward sky-lit slopes & bold dark downward faces
    spanning 20-45% of block width/height — matching `crop_plaque_stone.png` 1:1!).
    """
    rng = np.random.default_rng(seed)

    # Local block coordinates: u in [0, 1] (width ~2.05 m), v in [0, 1] (height ~1.06 m; v=1 is TOP!)
    yy, xx = np.mgrid[0:bh, 0:bw].astype(np.float32)
    u = xx / max(bw - 1.0, 1.0)
    v = 1.0 - yy / max(bh - 1.0, 1.0)

    # 1. Multi-scale rock fracture warp + coarse rough sandstone texture + fine crystalline sand grit
    # Macro fracture warp gives organic crooked hand-chiseled ridges (NOT straight CAD wedges!)
    warp_u = _tileable_fbm(bh, bw, seed + 11, [(3, 5, 0.52), (7, 12, 0.30), (15, 26, 0.18)], tile_x=False) - 0.5
    warp_v = _tileable_fbm(bh, bw, seed + 23, [(3, 5, 0.52), (7, 12, 0.30), (15, 26, 0.18)], tile_x=False) - 0.5

    # Rough split-stone surface texture (craggy sandstone micro-spall grain, NOT medium Voronoi pebbles!)
    rough_rock = _tileable_fbm(bh, bw, seed + 41, [(8, 14, 0.35), (18, 32, 0.35), (38, 68, 0.30)], tile_x=False)
    ridged_rock = 1.0 - np.abs(2.0 * rough_rock - 1.0)  # crisp craggy mineral fracture micro-facets!

    # Horizontal sedimentary sandstone bedding layers
    bed_n = _tileable_fbm(bh, bw, seed + 59, [(10, 4, 0.45), (26, 9, 0.35), (56, 18, 0.20)], tile_x=False)

    # Authentic gritty fine quartz sand grain (abrasive dry sandstone feel!)
    fine_raw = rng.normal(0.0, 1.0, size=(bh, bw)).astype(np.float32)
    fine_im = Image.fromarray(np.clip((fine_raw * 0.28 + 0.5) * 255.0, 0, 255).astype(np.uint8), mode="L")
    fine_2 = np.asarray(
        fine_im.resize((max(4, bw // 2), max(4, bh // 2)), Image.Resampling.BILINEAR).resize((bw, bh), Image.Resampling.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    fine_sand = 0.60 * fine_2 + 0.40 * np.clip(fine_raw * 0.20 + 0.5, 0.0, 1.0)

    # Warped block coordinates for organic jagged rock-plane intersections!
    uw = u + 0.14 * warp_u + 0.030 * (rough_rock - 0.5)
    vw = v + 0.22 * warp_v + 0.038 * (rough_rock - 0.5)

    # 2. BUILD MASSIVE CHUNKY FACETED ROCK BOSSES (`smax` of `num_bosses` bold pyramidal/wedged ridges!)
    # Every block gets 3-4 chunky protruding rock knuckles/ledges with steep 40-65 deg cleaved faces!
    h_rock = np.full((bh, bw), 0.05, dtype=np.float32)
    for b_i in range(num_bosses):
        cu = (b_i + 0.14 + 0.72 * rng.random()) / num_bosses
        cv = rng.uniform(0.28, 0.76)  # bold main horizontal rock ridge across upper/mid/lower thirds
        peak_h = rng.uniform(0.84, 1.12)

        # Steep architectural pitched-rock slopes (creates BIG fat upward bright & downward dark facets!)
        slope_up = rng.uniform(0.90, 1.85)    # broad sky-facing cleaved upper rock plane
        slope_dn = rng.uniform(1.85, 3.40)    # bold steep downward-facing cleaved rock undercut!
        slope_l = rng.uniform(0.80, 1.65)
        slope_r = rng.uniform(0.80, 1.65)
        skew = rng.uniform(-0.42, 0.42)

        du = uw - cu
        dv = (vw - cv) + skew * du

        # Crisp `smin` intersection of 4 strongly tilted cleavage planes -> ONE bold angular rock boss!
        p_top = peak_h - slope_up * np.maximum(dv, 0.0)
        p_bot = peak_h - slope_dn * np.maximum(-dv, 0.0)
        p_left = peak_h - slope_l * np.maximum(-du, 0.0)
        p_right = peak_h - slope_r * np.maximum(du, 0.0)

        ridge_chunk = _smin(_smin(p_top, p_bot, k=0.035), _smin(p_left, p_right, k=0.045), k=0.045)
        h_rock = _smax(h_rock, ridge_chunk, k=0.040)

    # 3. CARVE 2-3 LOCALIZED DEEP ANGULAR CONCHOIDAL QUARRY-CHISEL SCOOPS (`smin` with strong localized cup!)
    # Localized basin (`1.9..3.6 * r^2`) knocks out crisp 25-45% angular pockets WITHOUT flattening the peaks!
    for _ in range(num_spalls):
        su = rng.uniform(0.10, 0.90)
        sv = rng.uniform(0.14, 0.86)
        ang = rng.choice([
            rng.uniform(-0.40, 0.40),
            rng.uniform(math.pi - 0.45, math.pi + 0.45),
            rng.uniform(0.55, 1.35),
            rng.uniform(-1.35, -0.55),
        ])
        gx = math.sin(ang) * rng.uniform(0.75, 1.55)
        gy = math.cos(ang) * rng.uniform(1.30, 2.50)
        s_depth = rng.uniform(0.24, 0.56)
        du = uw - su
        dv = vw - sv
        basin = rng.uniform(1.9, 3.6) * (du * du * 0.85 + dv * dv * 1.65)
        spall_plane = s_depth + gx * du + gy * dv + basin
        h_rock = _smin(h_rock, spall_plane, k=0.028)

    # Normalize raw quarry cleavage cleanly into [0.08, 0.88] leaving headroom so micro-rock NEVER clips flat!
    p03 = float(np.percentile(h_rock, 3))
    p99 = float(np.percentile(h_rock, 99))
    h_rock = 0.08 + 0.80 * np.clip((h_rock - p03) / max(p99 - p03, 0.12), 0.0, 1.0)

    # Layer coarse fractured sandstone micro-crags + sedimentary bedding + abrasive sand grit (ZERO flat clipping!)
    h_rock = h_rock + 0.095 * (ridged_rock - 0.50) + 0.048 * (bed_n - 0.50) + 0.030 * (fine_sand - 0.50)
    # Soft per-block protrusion variation inside [0.06, 0.98] without hard-clipping peaks!
    lo_r, hi_r = float(h_rock.min()), float(h_rock.max())
    blk_max = rng.uniform(0.84, 0.98)
    h_rock = 0.06 + (blk_max - 0.06) * (h_rock - lo_r) / max(hi_r - lo_r, 1e-4)

    # 5. CRISP NARROW STRAIGHT MORTAR JOINTS + RAGGED CHISELED BLOCK PERIMETER
    m_u = 0.0080 if not granite_mode else 0.0055
    m_v = 0.0145 if not granite_mode else 0.0000
    du_e = np.minimum(u, 1.0 - u)
    dv_e = np.minimum(v, 1.0 - v)

    stone_u = _smoothstep(m_u * 0.65, m_u * 1.35, du_e)
    stone_v = _smoothstep(m_v * 0.65, m_v * 1.35, dv_e) if m_v > 0 else np.ones_like(u)
    mortar_mask = stone_u * stone_v

    # Chunky irregular hand-chiseled drop into the mortar groove:
    # Gentler top roll (`chip_v_top`) prevents artificial bright laser lines along top block edge;
    # steeper crisp bottom overhang (`chip_v_bot`) casts natural shadow into mortar joint below!
    chip_u = 0.026 + 0.042 * np.clip(0.5 + warp_u + 0.40 * (rough_rock - 0.5), 0.0, 1.0)
    chip_v_bot = 0.036 + 0.045 * np.clip(0.5 + warp_v + 0.40 * (rough_rock - 0.5), 0.0, 1.0)
    chip_v_top = 0.075 + 0.065 * np.clip(0.5 - warp_v + 0.35 * (rough_rock - 0.5), 0.0, 1.0)
    edge_u = _smoothstep(m_u * 0.85, m_u + chip_u, du_e)
    if m_v > 0:
        edge_v_bot = _smoothstep(m_v * 0.85, m_v + chip_v_bot, v)
        edge_v_top = _smoothstep(m_v * 0.85, m_v + chip_v_top, 1.0 - v)
        edge_v = edge_v_bot * edge_v_top
    else:
        edge_v = np.ones_like(u)
    pitch_env = np.power(edge_u * edge_v, 0.64)

    # Subtle hand-laid edge variation so mortar edges feel organic rather than CAD-stamped
    m_wob = 0.0025 * (rough_rock - 0.5)
    stone_u_org = _smoothstep(m_u * 0.60, m_u * 1.40, du_e + m_wob)
    stone_v_org = _smoothstep(m_v * 0.60, m_v * 1.40, dv_e + m_wob) if m_v > 0 else np.ones_like(u)
    mortar_mask = stone_u_org * stone_v_org

    h_block = mortar_mask * (0.10 + 0.90 * pitch_env * h_rock)

    # 6. Per-block natural mineral color variation + sedimentary strata + coarse/fine sandstone mineral flecks (R)
    blk_tone = rng.uniform(0.32, 0.72)
    # Occasional subtle dark iron-oxide flecks & pale quartz specks matching real Corsehill sandstone
    mineral_speck = np.where(fine_raw > 1.85, 0.14, np.where(fine_raw < -1.95, -0.18, 0.0))
    grain = np.clip(
        blk_tone
        + 0.18 * (bed_n - 0.5)
        + 0.14 * (rough_rock - 0.5)
        + 0.12 * (fine_sand - 0.5)
        + mineral_speck,
        0.0,
        1.0,
    )
    return h_block.astype(np.float32), mortar_mask.astype(np.float32), grain.astype(np.float32)


def _compute_physical_cavity_and_sky_ao(
    height: np.ndarray,
    mortar_mask: np.ndarray,
    height_scale_m: float = 0.155,
    pixel_w_m: float = 0.0074,
    pixel_h_m: float = 0.0073,
    tile_x: bool = True,
) -> np.ndarray:
    """Compute true horizon-raymarched sky occlusion + bold top-lit facet normal shading!

    Upward-facing cleaved rock planes glow warmly under diffuse sky light; broad steep downward-facing
    cleaved slopes & overhangs drop into BIG chunky dark shadows — matching `crop_plaque_stone.png`!
    """
    h_m = height * height_scale_m

    if tile_x:
        gx = (np.roll(h_m, -1, axis=1) - np.roll(h_m, 1, axis=1)) / (2.0 * pixel_w_m)
    else:
        gx = np.gradient(h_m, pixel_w_m, axis=1)
    # Surface X = H(u, Z) -> outward normal N = (+1, -dH/du, -dH/dZ).
    # Since image row y increases DOWNWARD (Z = -y), -dH/dZ = +dH/dy = +(h[y+1] - h[y-1]) / (2 * dy)!
    # Check: ABOVE a protruding peak (sky-facing slope), h[y+1] > h[y-1] -> nz_up > 0 (BRIGHT!).
    #        BELOW a protruding peak (underside overhang), h[y+1] < h[y-1] -> nz_up < 0 (DARK SHADOW!).
    dh_dy = (np.pad(h_m[1:, :], ((0, 1), (0, 0)), mode="edge") - np.pad(h_m[:-1, :], ((1, 0), (0, 0)), mode="edge")) / (
        2.0 * pixel_h_m
    )

    inv_len = 1.0 / np.sqrt(gx * gx + dh_dy * dh_dy + 1.0)
    nz_up = dh_dy * inv_len   # +1 = sky-facing bright rock plane, -1 = dark downward overhang!
    nx_lat = -gx * inv_len
    nout = inv_len

    # Vectorized hemispherical sky horizon raymarch (5 upward sky directions x 9 distances!)
    h_rows, w_cols = h_m.shape
    rays = [
        (0, -1, 0.36),    # zenith (+Z)
        (-1, -2, 0.22),   # up-left
        (1, -2, 0.22),    # up-right
        (-2, -1, 0.10),   # grazing left
        (2, -1, 0.10),    # grazing right
    ]
    step_dists = (1, 2, 4, 7, 11, 17, 25, 36, 50)
    sky_vis = np.zeros_like(h_m)

    for dx_r, dy_r, weight in rays:
        max_slope = np.zeros_like(h_m)
        step_m = math.hypot(dx_r * pixel_w_m, dy_r * pixel_h_m)
        for s in step_dists:
            ox = dx_r * s
            oy = dy_r * s
            h_s = np.roll(h_m, -ox, axis=1)
            if not tile_x:
                if ox < 0:
                    h_s[:, :-ox] = h_m[:, :1]
                elif ox > 0:
                    h_s[:, -ox:] = h_m[:, -1:]
            k = -oy
            if k < h_rows:
                shifted = np.empty_like(h_s)
                shifted[:k, :] = h_s[:1, :]
                shifted[k:, :] = h_s[:-k, :]
            else:
                shifted = np.broadcast_to(h_s[:1, :], h_s.shape)
            slope = (shifted - h_m) / (s * step_m + 1e-6)
            max_slope = np.maximum(max_slope, slope)
        horizon_sin = max_slope / np.sqrt(max_slope * max_slope + 1.0)
        sky_vis += weight * (1.0 - np.clip(horizon_sin, 0.0, 0.94))

    # Bold hemispherical sky-cavity AO + subtle ridge highlight (clean for Cycles normal shading!)
    # NOTE: Cycles computes full directional diffuse light from `height` Normal map, so `cavity` here
    # carries true hemispherical sky horizon occlusion + deep overhang shadow + gentle ridge pop!
    facet_ao = np.clip(0.62 + 0.34 * nz_up + 0.08 * nout, 0.16, 1.06)

    h_blur = np.asarray(
        Image.fromarray((np.clip(height, 0, 1) * 255.0).astype(np.uint8), mode="L")
        .resize((w_cols // 6, h_rows // 6), Image.Resampling.BILINEAR)
        .resize((w_cols, h_rows), Image.Resampling.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    ridge_pop = np.clip((height - h_blur) * 0.85, -0.18, 0.15)

    shading = np.power(np.clip(sky_vis, 0.04, 1.0), 1.32) * (0.38 + 0.62 * facet_ao) + 0.14 * ridge_pop
    # Keep mortar warm shadowed grey-brown (0.48 floor instead of jet-black 0.34)
    shading = shading * (0.48 + 0.52 * mortar_mask)
    return np.clip(shading, 0.06, 1.0).astype(np.float32)


def generate_shaft_masonry_maps(
    out_height: str,
    out_detail_srgb: str,
    *,
    width: int = 4096,
    height: int = 2048,
    num_courses: int = 14,
    blocks_per_course: int = 14,
) -> tuple[str, str]:
    """Generate seamless `4096x2048` 14-course x 14-block running-bond rock-faced Corsehill sandstone maps."""
    h_map = np.zeros((height, width), dtype=np.float32)
    m_map = np.ones((height, width), dtype=np.float32)
    g_map = np.full((height, width), 0.5, dtype=np.float32)

    y_edges = [int(round(height * (1.0 - c / num_courses))) for c in range(num_courses + 1)]
    x_edges = [int(round(width * b / blocks_per_course)) for b in range(blocks_per_course + 1)]
    half_shift_px = int(round(0.5 * width / blocks_per_course))

    for c_idx in range(num_courses):
        y1 = y_edges[c_idx]
        y0 = y_edges[c_idx + 1]
        bh = y1 - y0
        course_h = np.zeros((bh, width), dtype=np.float32)
        course_m = np.ones((bh, width), dtype=np.float32)
        course_g = np.full((bh, width), 0.5, dtype=np.float32)

        for b_idx in range(blocks_per_course):
            x0 = x_edges[b_idx]
            x1 = x_edges[b_idx + 1]
            bw = x1 - x0
            seed = 10300 + c_idx * 97 + b_idx * 31
            n_boss = 3 + ((c_idx * 3 + b_idx * 7) % 2)   # 3-4 chunky bold rock bosses per block!
            n_spall = 2 + ((c_idx * 5 + b_idx * 3) % 2)  # 2-3 deep localized conchoidal quarry scoops!
            bh_blk, bm_blk, bg_blk = _sculpt_single_rock_block(
                bh, bw, seed, num_bosses=n_boss, num_spalls=n_spall, granite_mode=False
            )
            course_h[:, x0:x1] = bh_blk
            course_m[:, x0:x1] = bm_blk
            course_g[:, x0:x1] = bg_blk

        if c_idx % 2 == 1:
            course_h = np.roll(course_h, half_shift_px, axis=1)
            course_m = np.roll(course_m, half_shift_px, axis=1)
            course_g = np.roll(course_g, half_shift_px, axis=1)

        h_map[y0:y1, :] = course_h
        m_map[y0:y1, :] = course_m
        g_map[y0:y1, :] = course_g

    px_w_m = (2.0 * math.pi * 4.81) / width
    px_h_m = 14.88 / height
    cavity = _compute_physical_cavity_and_sky_ao(h_map, m_map, height_scale_m=0.22, pixel_w_m=px_w_m, pixel_h_m=px_h_m)

    os.makedirs(os.path.dirname(os.path.abspath(out_height)), exist_ok=True)
    Image.fromarray(np.clip(h_map * 255.0, 0, 255).astype(np.uint8), mode="L").save(out_height, format="PNG")
    _save_detail_srgb(out_detail_srgb, g_map, cavity, m_map)
    return out_height, out_detail_srgb


def generate_coping_maps(
    out_height: str,
    out_detail_srgb: str,
    *,
    width: int = 4096,
    height: int = 512,
    num_stones: int = 18,
) -> tuple[str, str]:
    """Generate `4096x512` 18-stone rock-faced coping fascia (`v in [0, 0.68]`) + dressed stone top (`v in [0.68, 1]`)."""
    h_map = np.zeros((height, width), dtype=np.float32)
    m_map = np.ones((height, width), dtype=np.float32)
    g_map = np.full((height, width), 0.5, dtype=np.float32)

    split_row = int(round(height * 0.32))
    fh = height - split_row
    th = split_row
    x_edges = [int(round(width * b / num_stones)) for b in range(num_stones + 1)]

    top_grain = _tileable_fbm(th, width, 20991, [(6, 36, 0.40), (18, 108, 0.35), (44, 264, 0.25)], tile_x=True)

    for b_idx in range(num_stones):
        x0 = x_edges[b_idx]
        x1 = x_edges[b_idx + 1]
        bw = x1 - x0
        seed = 20400 + b_idx * 47
        bh_blk, bm_blk, bg_blk = _sculpt_single_rock_block(
            fh, bw, seed, num_bosses=3, num_spalls=3, granite_mode=False
        )
        h_map[split_row:, x0:x1] = bh_blk
        m_map[split_row:, x0:x1] = bm_blk
        g_map[split_row:, x0:x1] = bg_blk

        rng = np.random.default_rng(seed + 7)
        xx = np.linspace(0.0, 1.0, bw, dtype=np.float32)[None, :]
        du = np.minimum(xx, 1.0 - xx)
        j_mask = _smoothstep(0.008, 0.018, du)
        top_h = (0.48 + 0.06 * top_grain[:, x0:x1]) * (0.65 + 0.35 * j_mask)
        h_map[:split_row, x0:x1] = top_h
        m_map[:split_row, x0:x1] = 0.25 + 0.75 * j_mask
        g_map[:split_row, x0:x1] = np.clip(rng.uniform(0.42, 0.62) + 0.16 * (top_grain[:, x0:x1] - 0.5), 0.0, 1.0)

    px_w_m = (2.0 * math.pi * 4.66) / width
    px_h_m = 0.94 / fh
    cavity = _compute_physical_cavity_and_sky_ao(h_map, m_map, height_scale_m=0.21, pixel_w_m=px_w_m, pixel_h_m=px_h_m)
    cavity[:split_row, :] = np.clip(0.76 + 0.18 * (top_grain - 0.5) - 0.26 * (1.0 - m_map[:split_row, :]), 0.38, 0.96)

    Image.fromarray(np.clip(h_map * 255.0, 0, 255).astype(np.uint8), mode="L").save(out_height, format="PNG")
    _save_detail_srgb(out_detail_srgb, g_map, cavity, m_map)
    return out_height, out_detail_srgb


def generate_curb_maps(
    out_height: str,
    out_detail_srgb: str,
    *,
    width: int = 4096,
    height: int = 512,
    num_wedges: int = 6,
) -> tuple[str, str]:
    """Generate `4096x512` 6-wedge rough-split granite curb wall (`v in [0, 0.76]`) + hammered top (`v in [0.76, 1]`)."""
    h_map = np.zeros((height, width), dtype=np.float32)
    m_map = np.ones((height, width), dtype=np.float32)
    g_map = np.full((height, width), 0.5, dtype=np.float32)

    split_row = int(round(height * 0.24))
    fh = height - split_row
    th = split_row
    x_edges = [int(round(width * b / num_wedges)) for b in range(num_wedges + 1)]

    top_grain = _tileable_fbm(th, width, 30991, [(6, 24, 0.42), (18, 72, 0.35), (48, 192, 0.23)], tile_x=True)

    for b_idx in range(num_wedges):
        x0 = x_edges[b_idx]
        x1 = x_edges[b_idx + 1]
        bw = x1 - x0
        seed = 30700 + b_idx * 53
        # Each 9.5 m wide granite curb block has 16 crisp rough-split granite quarry bosses (~0.6 m wide!)
        # + 18 angular conchoidal rock spalls + crystalline feldspar/quartz granite salt-and-pepper speckle!
        bh_blk, bm_blk, bg_blk = _sculpt_single_rock_block(
            fh, bw, seed, num_bosses=16, num_spalls=18, granite_mode=True
        )
        rng_g = np.random.default_rng(seed + 19)
        granite_speck = rng_g.normal(0.0, 0.11, size=(fh, bw)).astype(np.float32)
        h_map[split_row:, x0:x1] = bh_blk
        m_map[split_row:, x0:x1] = bm_blk
        g_map[split_row:, x0:x1] = np.clip(bg_blk + granite_speck, 0.0, 1.0)

        xx = np.linspace(0.0, 1.0, bw, dtype=np.float32)[None, :]
        du = np.minimum(xx, 1.0 - xx)
        j_mask = _smoothstep(0.004, 0.010, du)
        h_map[:split_row, x0:x1] = (0.50 + 0.05 * top_grain[:, x0:x1]) * (0.60 + 0.40 * j_mask)
        m_map[:split_row, x0:x1] = 0.20 + 0.80 * j_mask
        g_map[:split_row, x0:x1] = np.clip(0.60 + 0.22 * (top_grain[:, x0:x1] - 0.5), 0.0, 1.0)

    px_w_m = (2.0 * math.pi * 9.15) / width
    px_h_m = 1.42 / fh
    cavity = _compute_physical_cavity_and_sky_ao(h_map, m_map, height_scale_m=0.22, pixel_w_m=px_w_m, pixel_h_m=px_h_m)
    cavity[:split_row, :] = np.clip(0.80 + 0.14 * (top_grain - 0.5) - 0.30 * (1.0 - m_map[:split_row, :]), 0.40, 0.96)

    Image.fromarray(np.clip(h_map * 255.0, 0, 255).astype(np.uint8), mode="L").save(out_height, format="PNG")
    _save_detail_srgb(out_detail_srgb, g_map, cavity, m_map)
    return out_height, out_detail_srgb


def generate_cap_top_maps(
    out_height: str,
    out_detail_srgb: str,
    *,
    size: int = 2048,
    num_stones: int = 18,
    r_max_m: float = 4.75,
    r_inner_ring_m: float = 2.15,
) -> tuple[str, str]:
    """Generate `2048x2048` TRUE PLANAR (X, Y) top-down weathered Scottish sandstone crown maps!

    Zero polar stretching & zero center-pole pinch:
      - Outer ring (`R = 2.15 .. 4.66 m`): exact 18 radial coping stone slabs aligned 1:1 with the
        18 vertical fascia joints (`theta = 2*pi*k/18`), each with unique subtle stone tone, dressed
        bush-hammered sandstone relief, natural chisel tool grain, and rainwater weathering!
      - Concentric recessed mortar ring at `R = 2.15 m` framing a solid circular central Corsehill
        sandstone capstone medallion (`R = 0 .. 2.15 m`) with realistic coarse sandstone micro-relief!
    """
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    # Standard UV: u = x/(size-1) -> nx in [-1, 1] (+X right), v = 1 - y/(size-1) -> ny in [-1, 1] (+Y top)
    nx = (xx / (size - 1.0)) * 2.0 - 1.0
    ny = 1.0 - (yy / (size - 1.0)) * 2.0
    r_m = np.sqrt(nx * nx + ny * ny) * r_max_m
    theta = np.mod(np.arctan2(ny, nx), 2.0 * math.pi)

    # Multi-scale isotropic planar weathered sandstone grain & chisel relief (ZERO radial stretch!)
    macro_n = _tileable_fbm(size, size, 41001, [(8, 8, 0.42), (18, 18, 0.34), (40, 40, 0.24)], tile_x=False)
    med_n = _tileable_fbm(size, size, 41017, [(24, 24, 0.36), (56, 56, 0.34), (128, 128, 0.30)], tile_x=False)
    ridged_n = 1.0 - np.abs(2.0 * med_n - 1.0)
    rng = np.random.default_rng(41033)
    fine_raw = rng.normal(0.0, 1.0, size=(size, size)).astype(np.float32)
    fine_im = Image.fromarray(np.clip((fine_raw * 0.26 + 0.5) * 255.0, 0, 255).astype(np.uint8), mode="L")
    fine_2 = np.asarray(
        fine_im.resize((size // 2, size // 2), Image.Resampling.BILINEAR).resize((size, size), Image.Resampling.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    fine_sand = 0.58 * fine_2 + 0.42 * np.clip(fine_raw * 0.18 + 0.5, 0.0, 1.0)

    # Per-slab subtle stone hue/value & height variation across the 18 outer slabs + central capstone
    stone_idx = np.floor(theta / (2.0 * math.pi / num_stones)).astype(np.int32) % num_stones
    slab_tones = rng.uniform(0.36, 0.68, size=num_stones).astype(np.float32)
    slab_heights = rng.uniform(0.70, 0.88, size=num_stones).astype(np.float32)
    is_center = r_m < r_inner_ring_m

    base_tone = np.where(is_center, 0.52, slab_tones[stone_idx])
    base_h = np.where(is_center, 0.82, slab_heights[stone_idx])

    # Crisp constant-physical-width mortar joints (measured in REAL METERS -> zero pinching!)
    # 1. Concentric circular mortar ring at R = 2.15 m (`width = 3.2 cm`)
    wob_r = 0.012 * (med_n - 0.5)
    ring_dist_m = np.abs(r_m - (r_inner_ring_m + wob_r))
    m_ring = _smoothstep(0.014, 0.030, ring_dist_m)
    bevel_ring = _smoothstep(0.024, 0.095, ring_dist_m)

    # 2. Exact 18 radial mortar joints ONLY outside R = 2.15 m (`constant physical width = 3.0 cm`!)
    step_ang = (2.0 * math.pi) / num_stones
    ang_mod = np.mod(theta + 0.5 * step_ang, step_ang) - 0.5 * step_ang
    arc_dist_m = np.abs(ang_mod) * np.maximum(r_m, 0.5) + 0.008 * (med_n - 0.5)
    outer_blend = _smoothstep(r_inner_ring_m - 0.01, r_inner_ring_m + 0.02, r_m)
    m_rad_raw = _smoothstep(0.013, 0.028, arc_dist_m)
    m_rad = 1.0 - outer_blend * (1.0 - m_rad_raw)
    bevel_rad_raw = _smoothstep(0.022, 0.090, arc_dist_m)
    bevel_rad = 1.0 - outer_blend * (1.0 - bevel_rad_raw)

    mortar_mask = np.minimum(m_ring, m_rad)
    edge_bevel = np.minimum(bevel_ring, bevel_rad)

    # Authentic bush-hammered / hand-tooled weathered sandstone top relief (crisp tactile stone, NOT smooth clay!)
    # Subtle outer weathered pitch lip near R > 4.25 m
    outer_pitch = _smoothstep(4.64, 4.30, r_m)
    h_surf = (
        base_h
        + 0.14 * (macro_n - 0.5)
        + 0.10 * (ridged_n - 0.5)
        + 0.045 * (fine_sand - 0.5)
    )
    h_surf = np.clip(h_surf * (0.86 + 0.14 * outer_pitch), 0.15, 0.96)
    h_map = mortar_mask * (0.14 + 0.86 * (0.35 + 0.65 * edge_bevel) * h_surf)

    # Natural outdoor rainwater staining & subtle radial moss/weathering in outer bevel & mortar joints
    rain_stain = _tileable_fbm(size, size, 41077, [(5, 5, 0.50), (14, 14, 0.30), (32, 32, 0.20)], tile_x=False)
    mineral_speck = np.where(fine_raw > 1.85, 0.14, np.where(fine_raw < -1.95, -0.18, 0.0))
    g_map = np.clip(
        base_tone
        + 0.20 * (macro_n - 0.5)
        + 0.14 * (med_n - 0.5)
        + 0.12 * (fine_sand - 0.5)
        - 0.14 * _smoothstep(0.55, 0.92, rain_stain)
        + mineral_speck,
        0.0,
        1.0,
    )

    # Physical local crevice AO (darkens mortar channels, chamfer bevels, and micro-pits cleanly!)
    h_blur = np.asarray(
        Image.fromarray((np.clip(h_map, 0, 1) * 255.0).astype(np.uint8), mode="L")
        .resize((size // 8, size // 8), Image.Resampling.BILINEAR)
        .resize((size, size), Image.Resampling.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    cavity = np.clip(
        (0.76 + 0.22 * (h_map - h_blur) * 2.2 - 0.14 * (1.0 - edge_bevel) - 0.10 * _smoothstep(0.60, 0.95, rain_stain))
        * (0.42 + 0.58 * mortar_mask),
        0.10,
        0.98,
    )

    os.makedirs(os.path.dirname(os.path.abspath(out_height)), exist_ok=True)
    Image.fromarray(np.clip(h_map * 255.0, 0, 255).astype(np.uint8), mode="L").save(out_height, format="PNG")
    _save_detail_srgb(out_detail_srgb, g_map, cavity, mortar_mask)
    return out_height, out_detail_srgb


def generate_curb_bottom_maps(
    out_height: str,
    out_detail_srgb: str,
    *,
    size: int = 2048,
    num_wedges: int = 6,
    r_max_m: float = 9.30,
    r_footing_in_m: float = 7.45,
) -> tuple[str, str]:
    """Generate `2048x2048` TRUE PLANAR (X, Y) underside granite footing & foundation slab maps!

    Zero radial stretching & zero wood-grain streaks:
      - Outer ring (`R = 7.45 .. 9.25 m`): exact 6 cut granite curb footing slabs aligned 1:1 with the
        6 vertical granite curb joints (`-30, +30, +90, +150, -150, -90 deg`).
      - Inner circular core (`R = 0 .. 7.45 m`): clean isotropic rough-cast architectural concrete/stone
        monument foundation slab with natural aggregate grain & subtle weathering!
    """
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    nx = (xx / (size - 1.0)) * 2.0 - 1.0
    ny = 1.0 - (yy / (size - 1.0)) * 2.0
    r_m = np.sqrt(nx * nx + ny * ny) * r_max_m
    theta = np.mod(np.arctan2(ny, nx) - math.radians(-30.0), 2.0 * math.pi)

    macro_n = _tileable_fbm(size, size, 52001, [(8, 8, 0.45), (20, 20, 0.35), (48, 48, 0.20)], tile_x=False)
    med_n = _tileable_fbm(size, size, 52019, [(30, 30, 0.38), (72, 72, 0.34), (160, 160, 0.28)], tile_x=False)
    rng = np.random.default_rng(52037)
    fine_raw = rng.normal(0.0, 1.0, size=(size, size)).astype(np.float32)
    fine_im = Image.fromarray(np.clip((fine_raw * 0.28 + 0.5) * 255.0, 0, 255).astype(np.uint8), mode="L")
    fine_2 = np.asarray(
        fine_im.resize((size // 2, size // 2), Image.Resampling.BILINEAR).resize((size, size), Image.Resampling.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    fine_grain = 0.55 * fine_2 + 0.45 * np.clip(fine_raw * 0.20 + 0.5, 0.0, 1.0)

    # Exact 6 outer granite footing wedges + solid rough-cast foundation core
    wedge_idx = np.floor(theta / (2.0 * math.pi / num_wedges)).astype(np.int32) % num_wedges
    wedge_tones = rng.uniform(0.38, 0.56, size=num_wedges).astype(np.float32)
    is_core = r_m < r_footing_in_m

    # Constant physical width joints (`4 cm`) ONLY on the outer footing ring + inner foundation seam
    ring_dist_m = np.abs(r_m - (r_footing_in_m + 0.02 * (med_n - 0.5)))
    m_ring = _smoothstep(0.020, 0.045, ring_dist_m)
    step_ang = (2.0 * math.pi) / num_wedges
    ang_mod = np.mod(theta + 0.5 * step_ang, step_ang) - 0.5 * step_ang
    arc_dist_m = np.abs(ang_mod) * np.maximum(r_m, 1.0) + 0.015 * (med_n - 0.5)
    outer_m = _smoothstep(r_footing_in_m - 0.02, r_footing_in_m + 0.03, r_m)
    m_rad = 1.0 - outer_m * (1.0 - _smoothstep(0.018, 0.042, arc_dist_m))
    mortar_mask = np.minimum(m_ring, m_rad)

    # Clean isotropic rough-sawn granite / poured concrete relief
    h_surf = np.clip(
        np.where(is_core, 0.56, 0.66)
        + 0.16 * (macro_n - 0.5)
        + 0.12 * (med_n - 0.5)
        + 0.07 * (fine_grain - 0.5),
        0.15,
        0.92,
    )
    h_map = mortar_mask * (0.18 + 0.82 * h_surf)

    base_tone = np.where(is_core, 0.44, wedge_tones[wedge_idx])
    g_map = np.clip(
        base_tone
        + 0.22 * (macro_n - 0.5)
        + 0.16 * (med_n - 0.5)
        + 0.14 * (fine_grain - 0.5),
        0.0,
        1.0,
    )
    cavity = np.clip((0.78 + 0.16 * (med_n - 0.5)) * (0.45 + 0.55 * mortar_mask), 0.15, 0.96)

    os.makedirs(os.path.dirname(os.path.abspath(out_height)), exist_ok=True)
    Image.fromarray(np.clip(h_map * 255.0, 0, 255).astype(np.uint8), mode="L").save(out_height, format="PNG")
    _save_detail_srgb(out_detail_srgb, g_map, cavity, mortar_mask)
    return out_height, out_detail_srgb


def ensure_stone_textures(force: bool = False) -> dict[str, str]:
    os.makedirs(TEX_SRC_DIR, exist_ok=True)
    paths = {
        "shaft_h": os.path.join(TEX_SRC_DIR, "shaft_stone_height.png"),
        "shaft_d": os.path.join(TEX_SRC_DIR, "shaft_stone_detail_srgb.png"),
        "coping_h": os.path.join(TEX_SRC_DIR, "coping_stone_height.png"),
        "coping_d": os.path.join(TEX_SRC_DIR, "coping_stone_detail_srgb.png"),
        "curb_h": os.path.join(TEX_SRC_DIR, "curb_stone_height.png"),
        "curb_d": os.path.join(TEX_SRC_DIR, "curb_stone_detail_srgb.png"),
        "cap_top_h": os.path.join(TEX_SRC_DIR, "cap_top_height.png"),
        "cap_top_d": os.path.join(TEX_SRC_DIR, "cap_top_detail_srgb.png"),
        "curb_bot_h": os.path.join(TEX_SRC_DIR, "curb_bottom_height.png"),
        "curb_bot_d": os.path.join(TEX_SRC_DIR, "curb_bottom_detail_srgb.png"),
    }
    if force or not (os.path.isfile(paths["shaft_h"]) and os.path.isfile(paths["shaft_d"])):
        print("[stone-gen] Synthesizing 4096x2048 14x14 rock-faced Corsehill sandstone maps...")
        generate_shaft_masonry_maps(paths["shaft_h"], paths["shaft_d"])
    if force or not (os.path.isfile(paths["coping_h"]) and os.path.isfile(paths["coping_d"])):
        print("[stone-gen] Synthesizing 4096x512 18-stone rock-faced coping cap maps...")
        generate_coping_maps(paths["coping_h"], paths["coping_d"])
    if force or not (os.path.isfile(paths["curb_h"]) and os.path.isfile(paths["curb_d"])):
        print("[stone-gen] Synthesizing 4096x512 6-wedge rough-split granite curb maps...")
        generate_curb_maps(paths["curb_h"], paths["curb_d"])
    if force or not (os.path.isfile(paths["cap_top_h"]) and os.path.isfile(paths["cap_top_d"])):
        print("[stone-gen] Synthesizing 2048x2048 planar sandstone coping crown top maps...")
        generate_cap_top_maps(paths["cap_top_h"], paths["cap_top_d"])
    if force or not (os.path.isfile(paths["curb_bot_h"]) and os.path.isfile(paths["curb_bot_d"])):
        print("[stone-gen] Synthesizing 2048x2048 planar granite footing & concrete underside maps...")
        generate_curb_bottom_maps(paths["curb_bot_h"], paths["curb_bot_d"])
    return paths


def save_debug_comparison(out_path: str) -> None:
    """Save side-by-side comparison simulating overcast sky-dome Cycles lighting from height normal + AO."""
    h_im = np.asarray(Image.open(os.path.join(TEX_SRC_DIR, "shaft_stone_height.png")), dtype=np.float32) / 255.0
    d_im = _srgb_u8_to_lin(np.asarray(Image.open(os.path.join(TEX_SRC_DIR, "shaft_stone_detail_srgb.png"))))
    y0, y1 = int(d_im.shape[0] * 0.22), int(d_im.shape[0] * 0.72)
    x0, x1 = int(d_im.shape[1] * 0.12), int(d_im.shape[1] * 0.48)
    hh = h_im[y0:y1, x0:x1] * 0.20
    g = d_im[y0:y1, x0:x1, 0]
    ao = d_im[y0:y1, x0:x1, 1]
    m = d_im[y0:y1, x0:x1, 2]

    # Exact outward normal shading under overcast Arlington outdoor sky dome (matches Cycles render!)
    # N = (+1, -dH/du, +dH/dy) normalized -> nz_up > 0 on upward sky-facing slopes!
    px_m = 0.00735
    gx = np.gradient(hh, px_m, axis=1)
    dh_dy = np.gradient(hh, px_m, axis=0)
    inv_l = 1.0 / np.sqrt(gx * gx + dh_dy * dh_dy + 1.0)
    nx, nz_up, nout = -gx * inv_l, dh_dy * inv_l, inv_l
    # Overcast outdoor hemisphere irradiance: bright zenith sky + frontal sky + darker ground bounce!
    sky_lit = np.clip(0.64 + 0.44 * nz_up + 0.14 * nout + 0.08 * nx, 0.16, 1.18)

    c_dark = np.array([148, 86, 62], dtype=np.float32)
    c_light = np.array([218, 148, 114], dtype=np.float32)
    c_mortar = np.array([86, 62, 50], dtype=np.float32)

    stone_rgb = c_dark[None, None, :] + g[:, :, None] * (c_light - c_dark)[None, None, :]
    base_rgb = c_mortar[None, None, :] * (1.0 - m[:, :, None]) + stone_rgb * m[:, :, None]
    final_rgb = base_rgb * (0.28 + 0.82 * ao[:, :, None]) * sky_lit[:, :, None]
    synth = Image.fromarray(np.clip(final_rgb, 0, 255).astype(np.uint8), mode="RGB")

    ref_crop_path = os.path.join(THIS_DIR, "references", "crop_plaque_stone.png")
    if os.path.isfile(ref_crop_path):
        ref = Image.open(ref_crop_path).convert("RGB")
        target_h = 680
        rw = int(round(ref.width * target_h / ref.height))
        sw = int(round(synth.width * target_h / synth.height))
        ref_r = ref.resize((rw, target_h), Image.Resampling.LANCZOS)
        syn_r = synth.resize((sw, target_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (rw + sw + 16, target_h), (24, 24, 24))
        canvas.paste(ref_r, (0, 0))
        canvas.paste(syn_r, (rw + 16, 0))
        canvas.save(out_path, format="PNG")
    else:
        synth.save(out_path, format="PNG")
    print(f"[stone-gen] Saved comparison -> {out_path}")


if __name__ == "__main__":
    ensure_stone_textures(force=True)
    save_debug_comparison(os.path.join(THIS_DIR, "renders", "stone_vs_ref.png"))
    print("[stone-gen] Done.")
