r"""Cruiser Boat 7C — 18.30 m (60-ft) Luxury Flybridge Motor Yacht Builder (v4 1:1 Precision Sculpt).

Calibrated 1:1 against `references/ref_side_image.png`, `ref_front_image.png`, `ref_top_image.png`,
and `ref_hero_image.png`:
  - Real-world metric scale: LOA = 18.30 m (-9.15 .. +9.15 m along +Y), Beam = 4.88 m (+/-2.44 m along X)
  - Grounded at exact Z = 0.0000 m on twin Volvo Penta IPS pod skegs (static waterline Z = 1.04 m)
  - Exact horizontal waterline (Z = 1.085 m) & metallic silver boot-stripe (Z = 1.185 m) hull edge loops
  - Sleek tapered rounded-V bow chine + convex upper hull knuckle + subtle bow stem V-drop (`ref_front_image.png`)
  - Seamless sculpted 28 cm white hydraulic swim platform + gracefully curved transom cheek & double aft louvers
  - Deep jet-obsidian 6-pane (3x2) midship master hull windows + twin forward stateroom hull windows (rich black at all angles!)
  - Open wide trapezoidal 2-pane main windshield + thin angled A-pillars + diagonal pantograph wipers + low foredeck cushions
  - Sleek low-profile tapered white flybridge brow (~36 cm) + wide flat-fronted curved dark venturi windscreen
  - Iconic AFT-SWEPT boomerang white flybridge arch legs + forward-cantilevered pure-white aerodynamic gull-wing hardtop
    with recessed flush canvas sunroof (invisible from side/front, crisp from top!), compact Garmin radar, low domes & slender whips
  - Full visible luxury walnut/marble main-deck salon interior (`ref_hero_image.png`) & flybridge helm/lounge (`ref_top_image.png`)
  - 14 game-ready `sc_part` groups (every part < 20,000 tris), 0 BVH breaches, 0 Errors, 0 Warnings.
"""
from __future__ import annotations

import math
import os
import shutil
import sys
import time
from collections import defaultdict

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
BLENDER_ENGINE = os.path.join(REPO_ROOT, "engine", "blender")
CAD_DIR = os.path.join(THIS_DIR, "cad")
RENDERS_DIR = os.path.join(THIS_DIR, "renders")

if BLENDER_ENGINE not in sys.path:
    sys.path.insert(0, BLENDER_ENGINE)

from vflib import core, gameready, geo, integrity, mats, refs  # noqa: E402

COLL_NAME = "CruiserBoat7c"

# ---------------------------------------------------------------------------
# True 60-ft (18.30 m) Luxury Flybridge Motor Yacht Naval Dimensions (1:1 Ref Locked!)
# ---------------------------------------------------------------------------
Y_PLAT_AFT = -9.150       # Aft edge of full-width hydraulic swim platform
Y_TRANSOM = -7.650        # Transom waterline base (curves smoothly forward-and-up to sheer!)
Y_BOW = 9.150             # Extreme bow stem nose tip (LOA = 18.300 m!)
HULL_LEN = Y_BOW - Y_TRANSOM

MAX_HALF_BEAM = 2.440     # 4.88 m (16' 0") beam
TRANSOM_HALF_BEAM = 2.120 # 4.24 m transom width
Z_KEEL_AFT = 0.420        # Planing V-hull keel baseline (IPS pod skegs grounded at Z = 0.000 m!)
Z_WATERLINE = 1.040       # Static waterline
Z_ANTIFOUL_TOP = 1.085    # Exact horizontal top of dark navy antifouling bottom
Z_BOOT_TOP = 1.185        # Exact horizontal top of crisp 10 cm silver-slate boot stripe
Z_PLAT_TOP = 1.255        # Sleek sculpted 24 cm white hydraulic teak swim platform (`ref_side_image.png`!)
Z_COCKPIT_SOLE = 1.720    # Aft teak cockpit sole
Z_SALON_SOLE = 1.880      # Walnut hardwood main-deck salon sole
Z_SHEER_BOW = 2.820       # Crisp yacht sheer at bow shoulders (drops cleanly at stem nose!)
Z_SALON_ROOF_MAX = 3.740  # Crown of sweeping coupe salon arch
Z_FB_FLOOR = 3.740        # Cantilevered flybridge deck sole
Z_FB_COAMING = 4.060      # Sleek low 32 cm tapered white flybridge brow (`ref_front_image.png` 1:1!)
Z_FB_VENTURI = 4.400      # Ultra-sleek low aft-raked dark smoked venturi windscreen (`ref_side_image.png` 1:1!)
Z_HARDTOP_BOT = 5.440     # Arched gull-wing hardtop soffit (`ref_front_image.png` & `ref_side_image.png`!)
Z_HARDTOP_TOP = 5.740     # Pure sculpted white aerodynamic hardtop crown (sunroof recessed cleanly inside!)


def smoothstep(a: float, b: float, x: float) -> float:
    if abs(b - a) < 1e-9:
        return 0.0 if x < a else 1.0
    u = max(0.0, min(1.0, (x - a) / (b - a)))
    return u * u * (3.0 - 2.0 * u)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _safe_copy(src: str, dst: str, retries: int = 6) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    for attempt in range(retries):
        try:
            shutil.copy2(src, dst)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(0.35)


# ---------------------------------------------------------------------------
# Naval Architecture Hull Surface Equations (t in [0.0 .. 1.0], 0=transom, 1=bow)
# ---------------------------------------------------------------------------
def hull_y_base(t: float) -> float:
    return Y_TRANSOM + HULL_LEN * t


def hull_half_beam(t: float) -> float:
    """Luxury 60-ft yacht planform (`ref_top_image.png` & `ref_front_image.png`: proud convex bow flare!)."""
    if t <= 0.44:
        u = t / 0.44
        return TRANSOM_HALF_BEAM + (MAX_HALF_BEAM - TRANSOM_HALF_BEAM) * (math.sin(u * math.pi * 0.5) ** 0.85)
    u = (t - 0.44) / 0.56
    fullness = max(0.0, 1.0 - (u ** 2.02)) ** 0.68
    return max(0.015, (MAX_HALF_BEAM - 0.015) * fullness + 0.015)


def hull_keel_z(t: float) -> float:
    if t <= 0.58:
        return Z_KEEL_AFT
    u = (t - 0.58) / 0.42
    return Z_KEEL_AFT + 0.60 * (u ** 2.65)


def hull_sheer_z(t: float) -> float:
    """1:1 Cruiser Boat 7C sheerline: curved stern quarter -> level mid -> gentle bow rise + crisp V-stem dip!"""
    if t < 0.16:
        u = t / 0.16
        return lerp(2.06, 2.52, math.sin(u * math.pi * 0.5) ** 0.74)
    base = lerp(2.52, Z_SHEER_BOW, smoothstep(0.16, 0.88, t) ** 1.08)
    nose_dip = -0.105 * (smoothstep(0.82, 1.0, t) ** 1.55)
    return base + nose_dip


def hull_chine_point(t: float) -> tuple[float, float, float]:
    """Return (chine_inner_x, chine_z, spray_flat_w) — sleek tucked chine matching `ref_front_image.png`!"""
    sheer_b = hull_half_beam(t)
    kz = hull_keel_z(t)
    sz = hull_sheer_z(t)
    fb = smoothstep(0.32, 0.96, t)
    # Tucked lower chine (`0.78 -> 0.28`) eliminates square bottom corners in `FRONT (ORTHO)`!
    c_in = max(0.008, sheer_b * (0.78 - 0.50 * fb))
    deadrise_deg = 19.0 + 5.5 * min(1.0, t / 0.50) + 30.0 * (smoothstep(0.44, 0.98, t) ** 1.45)
    cz_aft = kz + c_in * math.tan(math.radians(deadrise_deg))
    bow_lift = Z_KEEL_AFT + 0.58 + 0.08 * t + 0.56 * (smoothstep(0.52, 1.0, t) ** 1.40)
    m_hi = max(cz_aft, bow_lift)
    cz_smooth = m_hi + 0.045 * math.log(math.exp((cz_aft - m_hi) / 0.045) + math.exp((bow_lift - m_hi) / 0.045))
    cz = min(sz - 0.52, cz_smooth)
    flat_w = max(0.006, 0.072 * (1.0 - 0.82 * fb) * (1.0 - 0.90 * (t ** 3)))
    return c_in, cz, flat_w


def _raw_hull_outer_x(t: float, z: float) -> float:
    """Smooth convex-flared yacht hull cross-section matching `ref_front_image.png`."""
    kz = hull_keel_z(t)
    sz = hull_sheer_z(t)
    sheer_b = hull_half_beam(t)
    c_in, cz, flat_w = hull_chine_point(t)
    fb = smoothstep(0.28, 0.95, t)
    x_sp = min(sheer_b - 0.014 * (1.0 - t ** 3), c_in + flat_w)
    z_sp = cz + 0.012

    if z <= kz + 1e-6:
        return 0.0
    if z <= cz:
        u = max(0.0, min(1.0, (z - kz) / max(cz - kz, 1e-4)))
        return c_in * (u ** 0.94)
    if z <= z_sp:
        u = (z - cz) / max(z_sp - cz, 1e-4)
        return lerp(c_in, x_sp, u)
    v = max(0.0, min(1.0, (z - z_sp) / max(sz - z_sp, 1e-4)))
    aft_prof = v ** 1.04
    fwd_prof = v ** 1.38
    prof = (1.0 - fb) * aft_prof + fb * fwd_prof
    knuckle = 0.072 * math.sin(math.pi * (v ** 1.50)) * (0.38 + 0.62 * fb) * (1.0 - t ** 4.5)
    return max(x_sp + 0.002 * v, x_sp + (sheer_b - x_sp) * prof + knuckle)


def hull_outer_profile(t: float) -> list[tuple[float, float]]:
    """15-point half-section WITH EXACT HORIZONTAL WATERLINE & SILVER BOOT-STRIPE LOOPS!"""
    kz = hull_keel_z(t)
    sz = hull_sheer_z(t)
    z_af = max(kz + 0.035, Z_ANTIFOUL_TOP)
    z_bt = max(z_af + 0.065, Z_BOOT_TOP)

    pts: list[tuple[float, float]] = []
    for i in range(5):
        u = i / 4.0
        z = lerp(kz, z_af, u)
        pts.append((0.0 if i == 0 else _raw_hull_outer_x(t, z), z))
    pts.append((_raw_hull_outer_x(t, z_bt), z_bt))
    for j in range(1, 10):
        v = j / 9.0
        z = lerp(z_bt, sz, v)
        pts.append((_raw_hull_outer_x(t, z), z))
    return pts


def hull_y_at_z(t: float, z: float) -> float:
    """Longitudinal Y including gracefully curved stern transom (`ref_side_image.png`) & bold raked clipper bow!"""
    base = hull_y_base(t)
    kz = hull_keel_z(t)
    sz = hull_sheer_z(t)
    frac = max(0.0, min(1.0, (z - kz) / max(sz - kz, 0.15)))
    # Bold sleek clipper bow overhang (`1.44 m` rake matching `ref_side_image.png`!)
    bow_rake = 1.44 * (t ** 2.75) * (frac - 1.0)
    # Continuous curved forward-sloping stern transom flowing cleanly from waterline up to cockpit sheer!
    transom_rake = 1.62 * ((1.0 - t) ** 7.8) * (frac ** 1.20)
    return base + bow_rake + transom_rake


def hull_outer_x_at_z(t: float, z: float) -> float:
    pts = hull_outer_profile(t)
    if z <= pts[0][1]:
        return pts[0][0]
    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
        if z <= z1:
            u = (z - z0) / max(z1 - z0, 1e-6)
            return x0 + (x1 - x0) * u
    return pts[-1][0]


def exact_t_at_yz(y: float, z: float) -> float:
    if y <= hull_y_at_z(0.0, z):
        return 0.0
    if y >= hull_y_at_z(1.0, z):
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        if hull_y_at_z(mid, z) < y:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def outer_x_at_yz(y: float, z: float) -> float:
    return hull_outer_x_at_z(exact_t_at_yz(y, z), z)


def foredeck_crown_z(y: float) -> float:
    t = exact_t_at_yz(y, 2.76)
    return hull_sheer_z(t) + 0.055 * (1.0 - t ** 2.0)


def salon_roof_z(y: float) -> float:
    """Iconic continuous sweeping coupe crescent dome arch (`ref_side_image.png`!) from Y=-4.95 to Y=+3.45."""
    if y <= -0.30:
        u = max(0.0, min(1.0, (-0.30 - y) / 4.65))
        return Z_SALON_ROOF_MAX - 1.36 * (u ** 1.72)
    u = max(0.0, min(1.0, (y - (-0.30)) / 3.80))
    return Z_SALON_ROOF_MAX - 1.06 * (u ** 1.56)


def salon_half_width(y: float, z: float) -> float:
    """Sleek tapered trapezoidal cabin (`ref_front_image.png`: 3.55 m windshield base -> 2.86 m header)."""
    t = exact_t_at_yz(y, 2.55)
    sheer_x = hull_half_beam(t)
    base_w = min(2.02, max(1.24, sheer_x - 0.30))
    tumble = max(0.0, (z - 2.40) / 1.38)
    w = base_w * (1.0 - 0.22 * tumble)
    if y > 0.6:
        uf = min(1.0, (y - 0.6) / 3.0)
        w *= 1.0 - 0.12 * (uf ** 1.45)
    return max(0.92, w)


def flybridge_half_width(y: float) -> float:
    """Sleek flybridge deck & coaming half-width (`ref_front_image.png`: ~2.68 m front, ~3.00 m midships)."""
    if y <= -1.2:
        u = max(0.0, min(1.0, (-1.2 - y) / 4.55))
        return 1.50 - 0.14 * (u ** 1.55)
    u = max(0.0, min(1.0, (y - (-1.2)) / 2.25))
    return max(0.36, 1.50 * (1.0 - 0.30 * (u ** 1.85)))


# ---------------------------------------------------------------------------
# Clean Watertight BMesh & Scene Helpers (0 Errors, 0 Warnings Guarantee!)
# ---------------------------------------------------------------------------
def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        d = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(d)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def _unwrap_clean(ob: bpy.types.Object) -> None:
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.012, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.008)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)


def _fix_island_volumes(bm: bmesh.types.BMesh) -> None:
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    if not bm.faces:
        return
    parent = list(range(len(bm.verts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in bm.edges:
        a, b = find(e.verts[0].index), find(e.verts[1].index)
        if a != b:
            parent[a] = b

    isl = [find(i) for i in range(len(bm.verts))]
    closed = defaultdict(lambda: True)
    for e in bm.edges:
        if len(e.link_faces) != 2:
            closed[isl[e.verts[0].index]] = False

    vol = defaultdict(float)
    ref: dict[int, Vector] = {}
    faces_by_isl: dict[int, list[bmesh.types.BMFace]] = defaultdict(list)
    for v in bm.verts:
        ref.setdefault(isl[v.index], v.co.copy())
    for f in bm.faces:
        g = isl[f.verts[0].index]
        faces_by_isl[g].append(f)
        if not closed[g] or len(f.verts) < 3:
            continue
        o = ref[g]
        v0 = f.verts[0].co - o
        for k in range(1, len(f.verts) - 1):
            vol[g] += v0.dot((f.verts[k].co - o).cross(f.verts[k + 1].co - o)) / 6.0

    to_flip = [f for g, fs in faces_by_isl.items() if closed[g] and vol[g] < -1e-9 for f in fs]
    if to_flip:
        bmesh.ops.reverse_faces(bm, faces=to_flip)


def finalize_bmesh(
    name: str,
    bm: bmesh.types.BMesh,
    col: bpy.types.Collection,
    materials: bpy.types.Material | list[bpy.types.Material],
    *,
    part: str,
    role: str = "solid",
    sharp_angle: float = 36.0,
) -> bpy.types.Object:
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=2.0e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=3.0e-4)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=3.0e-4)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    _fix_island_volumes(bm)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()

    if len(me.polygons) == 0:
        raise RuntimeError(f"finalize_bmesh({name}): produced 0 polygons!")

    mat_list = materials if isinstance(materials, (list, tuple)) else [materials]
    for m in mat_list:
        me.materials.append(m)

    if len(me.materials) > 1:
        idx = [0] * len(me.polygons)
        me.polygons.foreach_get("material_index", idx)
        used = sorted(set(idx))
        if len(used) < len(me.materials):
            remap = {old_i: new_i for new_i, old_i in enumerate(used)}
            kept = [me.materials[i] for i in used]
            me.materials.clear()
            for m in kept:
                me.materials.append(m)
            me.polygons.foreach_set("material_index", [remap[i] for i in idx])

    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    geo.shade(ob, sharp_angle)
    ob["sc_part"] = part
    ob["sc_role"] = role
    _unwrap_clean(ob)
    return ob


def make_closed_loft(
    rings: list[list[Vector]],
    *,
    mat_fn=None,
    cap_start_mat: int = 0,
    cap_end_mat: int = 0,
) -> bmesh.types.BMesh:
    bm = bmesh.new()
    n_r = len(rings)
    n_c = len(rings[0])
    bm_r = [[bm.verts.new(p) for p in r] for r in rings]

    c0 = sum(rings[0], Vector()) / n_c
    c1 = sum(rings[-1], Vector()) / n_c
    v0 = bm.verts.new(c0)
    v1 = bm.verts.new(c1)

    for j in range(n_c):
        jn = (j + 1) % n_c
        f = bm.faces.new((v0, bm_r[0][jn], bm_r[0][j]))
        f.material_index = cap_start_mat

    for i in range(n_r - 1):
        for j in range(n_c):
            jn = (j + 1) % n_c
            f = bm.faces.new((bm_r[i][j], bm_r[i][jn], bm_r[i + 1][jn], bm_r[i + 1][j]))
            f.material_index = mat_fn(i, j) if mat_fn else 0

    for j in range(n_c):
        jn = (j + 1) % n_c
        f = bm.faces.new((bm_r[-1][j], bm_r[-1][jn], v1))
        f.material_index = cap_end_mat

    return bm


def make_box_bm(
    size: tuple[float, float, float],
    center: tuple[float, float, float],
    *,
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bevel: float = 0.0,
    segments: int = 2,
    mat_idx: int = 0,
) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    if bevel > 0.0:
        bmesh.ops.bevel(
            bm,
            geom=bm.edges[:],
            offset=min(bevel, min(size) * 0.40),
            segments=segments,
            affect="EDGES",
            clamp_overlap=True,
        )
    rot_m = Euler(tuple(math.radians(a) for a in rot_deg), "XYZ").to_matrix().to_4x4()
    xf = Matrix.Translation(Vector(center)) @ rot_m
    bmesh.ops.transform(bm, matrix=xf, verts=bm.verts[:])
    for f in bm.faces:
        f.material_index = mat_idx
    return bm


def make_cylinder_bm(
    r1: float,
    r2: float,
    depth: float,
    center: tuple[float, float, float],
    *,
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    seg: int = 20,
    mat_idx: int = 0,
) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=seg, radius1=r1, radius2=r2, depth=depth)
    rot_m = Euler(tuple(math.radians(a) for a in rot_deg), "XYZ").to_matrix().to_4x4()
    xf = Matrix.Translation(Vector(center)) @ rot_m
    bmesh.ops.transform(bm, matrix=xf, verts=bm.verts[:])
    for f in bm.faces:
        f.material_index = mat_idx
    return bm


def make_tube_bm(points: list[Vector], radius: float, seg: int = 10, mat_idx: int = 0) -> bmesh.types.BMesh:
    frames = geo.path_frames(points, up=(0, 0, 1), closed=False)
    prof = geo.circle2d(radius, seg)
    rings = [[p + b * x + n * y for (x, y) in prof] for (p, _t, n, b) in frames]
    return make_closed_loft(rings, mat_fn=lambda _i, _j: mat_idx, cap_start_mat=mat_idx, cap_end_mat=mat_idx)


def append_bm(dst: bmesh.types.BMesh, src: bmesh.types.BMesh) -> None:
    vmap = {v: dst.verts.new(v.co) for v in src.verts}
    for f in src.faces:
        try:
            nf = dst.faces.new([vmap[v] for v in f.verts])
            nf.material_index = f.material_index
        except ValueError:
            pass
    src.free()


def make_rrect_extrude_bm(
    w: float,
    l: float,
    r: float,
    z0: float,
    z1: float,
    center_xy: tuple[float, float] = (0.0, 0.0),
    *,
    taper_top: float = 1.0,
    seg: int = 4,
    mat_idx: int = 0,
) -> bmesh.types.BMesh:
    poly = geo.rrect2d(w, l, r, seg=seg)
    cx, cy = center_xy
    r0 = [Vector((cx + x, cy + y, z0)) for x, y in poly]
    r1 = [Vector((cx + x * taper_top, cy + y * taper_top, z1)) for x, y in poly]
    return make_closed_loft([r0, r1], mat_fn=lambda _i, _j: mat_idx, cap_start_mat=mat_idx, cap_end_mat=mat_idx)


def import_cad_glb(
    glb_name: str,
    name: str,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    part: str,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: float | tuple[float, float, float] = 1.0,
    role: str = "solid",
) -> bpy.types.Object:
    glb_path = os.path.join(CAD_DIR, glb_name)
    if not os.path.isfile(glb_path):
        raise FileNotFoundError(f"Missing CAD GLB: {glb_path}. Run build_hardware_cad.py first.")

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    imported = [o for o in bpy.data.objects if o not in before]
    mesh_obs = [o for o in imported if o.type == "MESH"]
    non_mesh = [o for o in imported if o.type != "MESH"]

    bm = bmesh.new()
    bpy.context.view_layer.update()
    for mo in mesh_obs:
        tbm = bmesh.new()
        tbm.from_mesh(mo.data)
        tbm.transform(mo.matrix_world)
        append_bm(bm, tbm)
        d = mo.data
        bpy.data.objects.remove(mo, do_unlink=True)
        core._free_data(d)
    for eo in non_mesh:
        bpy.data.objects.remove(eo, do_unlink=True)

    sc_v = (scale, scale, scale) if isinstance(scale, (int, float)) else scale
    xf = (
        Matrix.Translation(Vector(location))
        @ Euler(tuple(math.radians(a) for a in rot_deg), "XYZ").to_matrix().to_4x4()
        @ Matrix.Diagonal((sc_v[0], sc_v[1], sc_v[2], 1.0))
    )
    bmesh.ops.transform(bm, matrix=xf, verts=bm.verts[:])
    for f in bm.faces:
        f.material_index = 0
    return finalize_bmesh(name, bm, col, mat, part=part, role=role, sharp_angle=35.0)


# ---------------------------------------------------------------------------
# Material Palette (Reference-Calibrated to Cruiser Boat 7C!)
# ---------------------------------------------------------------------------
def build_materials() -> dict[str, bpy.types.Material]:
    return {
        "C7_HullWhite": mats.pbr("C7_HullWhite", "#F4F6F9", roughness=0.14, metallic=0.0, coat=0.85, roblox_material="SmoothPlastic"),
        "C7_HullAccent": mats.pbr("C7_HullAccent", "#15191F", roughness=0.22, metallic=0.10, coat=0.45, role="paint", roblox_material="SmoothPlastic"),
        "C7_BootStripe": mats.pbr("C7_BootStripe", "#9AA4B0", roughness=0.26, metallic=0.35, coat=0.45),
        "C7_AntiFoul": mats.pbr("C7_AntiFoul", "#141C26", roughness=0.68, metallic=0.0),
        "C7_DeckWhite": mats.pbr("C7_DeckWhite", "#EBF0F4", roughness=0.72, metallic=0.0),
        "C7_Teak": mats.pbr("C7_Teak", "#9C734B", roughness=0.52, metallic=0.0),
        "C7_WalnutFloor": mats.pbr("C7_WalnutFloor", "#4A3929", roughness=0.34, metallic=0.0, coat=0.35),
        "C7_WalnutCab": mats.pbr("C7_WalnutCab", "#3B2A1C", roughness=0.24, metallic=0.0, coat=0.55),
        "C7_Marble": mats.pbr("C7_Marble", "#EBEDE9", roughness=0.18, metallic=0.0, coat=0.65),
        "C7_VinylWhite": mats.pbr("C7_VinylWhite", "#EFF1EE", roughness=0.44, metallic=0.0),
        "C7_VinylGrey": mats.pbr("C7_VinylGrey", "#B2B8C0", roughness=0.48, metallic=0.0),
        "C7_VinylDark": mats.pbr("C7_VinylDark", "#2A3038", roughness=0.52, metallic=0.0),
        "C7_SunroofCanvas": mats.pbr("C7_SunroofCanvas", "#D6D9DC", roughness=0.84, metallic=0.0),
        "C7_DashDark": mats.pbr("C7_DashDark", "#181C22", roughness=0.36, metallic=0.08),
        "C7_BlackTrim": mats.pbr("C7_BlackTrim", "#111419", roughness=0.26, metallic=0.25),
        "C7_Stainless": mats.pbr("C7_Stainless", "#DFE5EC", roughness=0.14, metallic=0.95, roblox_material="Metal"),
        "C7_PodGrey": mats.pbr("C7_PodGrey", "#2D333B", roughness=0.34, metallic=0.55),
        "C7_PropBronze": mats.pbr("C7_PropBronze", "#C9A86A", roughness=0.16, metallic=0.94, roblox_material="Metal"),
        "C7_ScreenGlow": mats.pbr("C7_ScreenGlow", "#0E3F5E", roughness=0.22, metallic=0.0, emission="#1788B8", emission_strength=0.45),
        # Deep Pitch-Obsidian Hull Stateroom Windows (ultra-low Fresnel grazing reflection -> stays JET BLACK in FRONT & SIDE views!)
        "C7_HullGlass": mats.pbr(
            "C7_HullGlass",
            "#020407",
            roughness=0.18,
            metallic=0.0,
            coat=0.0,
            specular=0.05,
            ior=1.08,
            alpha=1.0,
            role="solid",
            roblox_material="SmoothPlastic",
        ),
        # Crystal-clear dark smoked marine windshield (`ior=1.01` -> zero internal caustic fireflies over MFD screens!)
        "C7_Glass": mats.pbr(
            "C7_Glass",
            "#122230",
            roughness=0.02,
            metallic=0.0,
            coat=0.0,
            specular=0.42,
            ior=1.01,
            alpha=0.48,
            role="glass",
            roblox_material="Glass",
        ),
        # Rich dark architectural smoked salon side glazing (`ref_side_image.png`: sleek glossy dark coupe glass, zero speckle!)
        "C7_SideGlass": mats.pbr(
            "C7_SideGlass",
            "#071018",
            roughness=0.02,
            metallic=0.0,
            coat=0.0,
            specular=0.32,
            ior=1.02,
            alpha=0.84,
            role="glass",
            roblox_material="Glass",
        ),
        # Rich dark smoked flybridge venturi glazing (`ref_front_image.png`!)
        "C7_VenturiGlass": mats.pbr(
            "C7_VenturiGlass",
            "#060C12",
            roughness=0.03,
            metallic=0.0,
            coat=0.0,
            specular=0.28,
            ior=1.02,
            alpha=0.86,
            role="glass",
            roblox_material="Glass",
        ),
        # Sleek smoked slate-grey foredeck skylight glass (`ref_top_image.png` 1:1!)
        "C7_SkylightGlass": mats.pbr(
            "C7_SkylightGlass",
            "#253240",
            roughness=0.08,
            metallic=0.0,
            coat=0.0,
            specular=0.35,
            ior=1.04,
            alpha=0.92,
            role="glass",
            roblox_material="Glass",
        ),
        "C7_NavRed": mats.pbr("C7_NavRed", "#FF2424", roughness=0.12, emission="#FF2424", emission_strength=4.0, role="neon", roblox_material="Neon"),
        "C7_NavGreen": mats.pbr("C7_NavGreen", "#1EE65A", roughness=0.12, emission="#1EE65A", emission_strength=4.0, role="neon", roblox_material="Neon"),
        "C7_LightWhite": mats.pbr("C7_LightWhite", "#FFFDF4", roughness=0.10, emission="#FFFDF4", emission_strength=3.2, role="neon", roblox_material="Neon"),
        "C7_UnderwaterBlue": mats.pbr("C7_UnderwaterBlue", "#14B8FF", roughness=0.10, emission="#14B8FF", emission_strength=4.2, role="neon", roblox_material="Neon"),
    }


# ---------------------------------------------------------------------------
# 1. Primary Sculpted Watertight Yacht Hull (`Hull`)
# ---------------------------------------------------------------------------
def build_hull(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    objs: list[bpy.types.Object] = []

    n_st = 76
    ts = [i / (n_st - 1) for i in range(n_st)]
    hull_mats = [
        M["C7_HullWhite"],
        M["C7_AntiFoul"],
        M["C7_BootStripe"],
        M["C7_DeckWhite"],
        M["C7_Teak"],
        M["C7_WalnutFloor"],
    ]

    rings: list[list[Vector]] = []
    for t in ts:
        prof = hull_outer_profile(t)
        sheer_x, sheer_z = prof[-1]
        y_sheer = hull_y_at_z(t, sheer_z)

        w_fore = smoothstep(3.15, 3.85, y_sheer)
        w_salon = smoothstep(-3.95, -3.50, y_sheer) * (1.0 - w_fore)
        w_cockpit = 1.0 - smoothstep(-3.95, -3.50, y_sheer)

        well_z = Z_COCKPIT_SOLE * w_cockpit + Z_SALON_SOLE * w_salon
        fore_crown_z = sheer_z + 0.055 * (1.0 - t ** 2.0)

        side_deck_z = lerp(Z_COCKPIT_SOLE + 0.14, sheer_z - 0.14, smoothstep(-5.8, 3.2, y_sheer))
        cap_w = max(0.006, min(0.19, sheer_x * 0.24))
        x_cap = max(0.008, sheer_x - cap_w)
        x_walk_in = max(0.006, x_cap - min(0.36, x_cap * 0.26))
        x_well = max(0.004, x_walk_in - 0.05)

        stbd_top = [
            (x_cap, sheer_z),
            (x_cap - 0.015 * (1.0 - t ** 2), lerp(side_deck_z, sheer_z - 0.015, w_fore)),
            (x_walk_in, lerp(side_deck_z + 0.02, fore_crown_z - 0.018, w_fore)),
            (x_well, lerp(well_z + 0.02, fore_crown_z - 0.008, w_fore)),
            (x_well * 0.50, lerp(well_z, fore_crown_z - 0.002, w_fore)),
            (0.0, lerp(well_z, fore_crown_z, w_fore)),
        ]

        ring_xz: list[tuple[float, float]] = []
        for x, z in prof:
            ring_xz.append((x, z))
        for x, z in stbd_top:
            ring_xz.append((x, z))
        for x, z in reversed(stbd_top[:-1]):
            ring_xz.append((-x, z))
        for x, z in reversed(prof[1:]):
            ring_xz.append((-x, z))

        rings.append([Vector((x, hull_y_at_z(t, z), z)) for (x, z) in ring_xz])

    n_ring = len(rings[0])

    def hull_mat_fn(i: int, j: int) -> int:
        if j <= 3 or j >= 36:
            return 1
        if j == 4 or j == 35:
            return 2
        if j <= 14 or j >= 25:
            return 0
        p0, p1 = rings[i][j], rings[i][(j + 1) % n_ring]
        p2, p3 = rings[i + 1][(j + 1) % n_ring], rings[i + 1][j]
        cen = (p0 + p1 + p2 + p3) * 0.25
        if cen.y > 3.45:
            return 3
        if j in (18, 19, 20, 21):
            return 4 if cen.y < -3.70 else 5
        return 3

    bm_hull = make_closed_loft(rings, mat_fn=hull_mat_fn, cap_start_mat=0, cap_end_mat=0)
    objs.append(finalize_bmesh("Hull_Main", bm_hull, col, hull_mats, part="Hull", sharp_angle=34.0))

    # Sleek Tapered Sculpted 24 cm Pure-White Hydraulic Swim Platform + Sweeping Transom Cheek Wings (`ref_side` & `ref_top` 1:1!)
    bm_plat = bmesh.new()
    plat_rings = []
    for k in range(10):
        u = k / 9.0
        y = lerp(Y_PLAT_AFT, -7.15, u)
        # Gracefully rounded trapezoidal planform matching `ref_top_image.png`!
        hw = lerp(1.84, 2.09, smoothstep(0.0, 0.85, u))
        if u < 0.14:
            hw *= 0.88 + 0.12 * math.sqrt(max(0.0, u / 0.14))
        z0, z1 = 1.015, Z_PLAT_TOP
        plat_rings.append([
            Vector((-hw + 0.04, y, z0)),
            Vector((hw - 0.04, y, z0)),
            Vector((hw, y, z0 + 0.04)),
            Vector((hw, y, z1 - 0.03)),
            Vector((hw - 0.03, y, z1)),
            Vector((-hw + 0.03, y, z1)),
            Vector((-hw, y, z1 - 0.03)),
            Vector((-hw, y, z0 + 0.04)),
        ])
    append_bm(bm_plat, make_closed_loft(plat_rings, mat_fn=lambda _i, _j: 0, cap_start_mat=0, cap_end_mat=0))

    # Boarding steps tucked cleanly INSIDE the curved transom cheek wings (60 mm clear of cheek inner wall -> 0 B2B!)
    for side in (-1.0, 1.0):
        for yc, zb, zt, wx, dy in (
            (-7.56, 1.180, 1.410, 0.56, 0.40),
            (-7.18, 1.335, 1.570, 0.52, 0.40),
            (-6.80, 1.495, 1.730, 0.48, 0.42),
        ):
            append_bm(bm_plat, make_box_bm((wx, dy, zt - zb), (side * 1.48, yc, 0.5 * (zb + zt)), bevel=0.014, mat_idx=0))

        # Sculpted Sweeping S-Curve Aft Transom Side Cheek Coaming Wings blending seamlessly INTO sheer (`ref_side_image.png`!)
        # Outer wall `<= 1.97 m` stays strictly inboard of swim platform edge `2.09 m` -> 0 coplanar faces (`0 Warnings`!)
        cheek_rings = []
        z_sheer_join = hull_sheer_z(exact_t_at_yz(-6.05, 2.38)) - 0.035
        for k in range(14):
            u = k / 13.0
            y = lerp(-7.76, -6.05, u)
            z_top = lerp(Z_PLAT_TOP + 0.015, z_sheer_join, smoothstep(0.0, 1.0, u) ** 0.78)
            z_bot = lerp(1.06, 1.72, u ** 1.2)
            t_y = exact_t_at_yz(max(y, -7.45), z_top)
            x_out = min(1.97, hull_half_beam(t_y) - 0.065)
            x_in = x_out - 0.16
            cheek_rings.append([
                Vector((side * x_in, y, z_bot)),
                Vector((side * x_out, y, z_bot)),
                Vector((side * x_out, y, z_top)),
                Vector((side * x_in, y, z_top)),
            ])
        append_bm(bm_plat, make_closed_loft(cheek_rings, mat_fn=lambda _i, _j: 0, cap_start_mat=0, cap_end_mat=0))

    objs.append(
        finalize_bmesh(
            "Hull_SwimPlatform",
            bm_plat,
            col,
            M["C7_HullWhite"],
            part="Hull",
            sharp_angle=34.0,
        )
    )

    # Sleek stainless-insert rubrail hugging the sheerline + bold dark swim platform outer bumper rim
    bm_rr = bmesh.new()
    for side in (-1.0, 1.0):
        rr_pts: list[Vector] = []
        for k in range(44):
            t = k / 43.0
            sx = hull_half_beam(t)
            sz = hull_sheer_z(t)
            sy = hull_y_at_z(t, sz)
            rr_pts.append(Vector((side * max(0.015, sx - 0.008), sy, sz - 0.034)))
        append_bm(bm_rr, make_tube_bm(rr_pts, radius=0.024, seg=10, mat_idx=0))
    # Swim platform outer perimeter bumper trim (`ref_side_image.png`: crisp horizontal dark edge!)
    pr_pts = [
        Vector((-2.07, -7.42, Z_PLAT_TOP - 0.045)),
        Vector((-1.94, -8.35, Z_PLAT_TOP - 0.045)),
        Vector((-1.78, Y_PLAT_AFT + 0.04, Z_PLAT_TOP - 0.045)),
        Vector((0.0, Y_PLAT_AFT - 0.008, Z_PLAT_TOP - 0.045)),
        Vector((1.78, Y_PLAT_AFT + 0.04, Z_PLAT_TOP - 0.045)),
        Vector((1.94, -8.35, Z_PLAT_TOP - 0.045)),
        Vector((2.07, -7.42, Z_PLAT_TOP - 0.045)),
    ]
    append_bm(bm_rr, make_tube_bm(pr_pts, radius=0.028, seg=8, mat_idx=0))
    objs.append(finalize_bmesh("Hull_Rubrail", bm_rr, col, M["C7_BlackTrim"], part="Hull", sharp_angle=45.0))

    # Ultra-Sleek White 6-Pane (3x2) Structural Mullions (`+0.018` center, `r=0.014` -> 4 mm clear of Hull_Main, 0 B2B!)
    bm_mull = bmesh.new()
    for side in (-1.0, 1.0):
        h_pts = []
        for k in range(7):
            u = k / 6.0
            y = lerp(-3.16, 0.72, u)
            z = lerp(1.70, 1.77, u)
            h_pts.append(Vector((side * (outer_x_at_yz(y, z) + 0.018), y, z)))
        append_bm(bm_mull, make_tube_bm(h_pts, radius=0.014, seg=8, mat_idx=0))
        for ym in (-2.26, -0.04):
            v_pts = [
                Vector((side * (outer_x_at_yz(ym, z) + 0.018), ym, z))
                for z in (1.42, 1.60, 1.78, 1.98, 2.18)
            ]
            append_bm(bm_mull, make_tube_bm(v_pts, radius=0.014, seg=8, mat_idx=0))
    objs.append(finalize_bmesh("Hull_WindowMullions", bm_mull, col, M["C7_HullWhite"], part="Hull", sharp_angle=35.0))

    # Bold Pitch-Obsidian Vertical Shield Bow Anchor Hawse Pocket (`ref_front_image.png` 1:1!)
    bm_ap = bmesh.new()
    y_ap = hull_y_at_z(0.992, 2.18)
    append_bm(bm_ap, make_box_bm((0.36, 0.56, 0.48), (0.0, y_ap - 0.20, 2.18), rot_deg=(16.0, 0.0, 0.0), bevel=0.055, mat_idx=0))
    objs.append(finalize_bmesh("Hull_AnchorPocket", bm_ap, col, M["C7_HullGlass"], part="Hull", sharp_angle=35.0))

    # 6x Crisp Flat Mounting Plinth Backing Plates for CAD Cleats (0 gunwale z-fighting!)
    bm_pads = bmesh.new()
    for _lbl, yc, z_est in (("Stern", -5.45, 2.48), ("Midship", -1.10, 2.58), ("Bow", 6.95, 2.74)):
        t = exact_t_at_yz(yc, z_est)
        sx = hull_half_beam(t) - 0.105
        sz = hull_sheer_z(t)
        for side in (-1.0, 1.0):
            append_bm(bm_pads, make_box_bm((0.10, 0.24, 0.055), (side * sx, yc, sz - 0.008), bevel=0.010, mat_idx=0))
    objs.append(finalize_bmesh("Hull_CleatPads", bm_pads, col, M["C7_HullWhite"], part="Hull", sharp_angle=35.0))

    return objs


# ---------------------------------------------------------------------------
# 2. Recolorable Yacht Accent & Curved Aft Engine Intake Louvers (`HullAccent`)
# ---------------------------------------------------------------------------
def build_hull_accents(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    bm = bmesh.new()
    # 1) Iconic Curved Aft Scythe Double-Blade Intake Louver (`ref_side_image.png`!)
    for side in (-1.0, 1.0):
        for z_off, y_end in ((0.0, -2.20), (-0.088, -2.65)):
            rings = []
            for k in range(20):
                u = k / 19.0
                y = lerp(-6.50, y_end, u)
                t_y = exact_t_at_yz(y, 2.25)
                z_base = hull_sheer_z(t_y) - 0.24 + z_off
                h_half = lerp(0.032, 0.009, u ** 1.4)
                x_out = outer_x_at_yz(y, z_base)
                xi = side * (x_out - 0.042)
                xo = side * (x_out + 0.026)
                rings.append([
                    Vector((xi, y, z_base - h_half)),
                    Vector((xo, y, z_base - h_half * 0.85)),
                    Vector((xo, y, z_base + h_half * 0.85)),
                    Vector((xi, y, z_base + h_half)),
                ])
            append_bm(bm, make_closed_loft(rings, mat_fn=lambda _i, _j: 0))

    # 2) Signature Flybridge Side Parallelogram Accent Spear (`ref_side_image.png`!)
    for side in (-1.0, 1.0):
        rings = []
        for k in range(14):
            u = k / 13.0
            y = lerp(-3.05, -0.75, u)
            z0 = lerp(3.81, 3.84, u)
            z1 = lerp(4.04, 4.07, u)
            pinch = min(1.0, u / 0.14, (1.0 - u) / 0.16)
            zc = 0.5 * (z0 + z1)
            hh = max(0.018, 0.5 * (z1 - z0) * pinch)
            fw = flybridge_half_width(y)
            xi = side * (fw - 0.048)
            xo = side * (fw + 0.026)
            rings.append([
                Vector((xi, y, zc - hh)),
                Vector((xo, y, zc - hh * 0.85)),
                Vector((xo, y, zc + hh * 0.85)),
                Vector((xi, y, zc + hh)),
            ])
        append_bm(bm, make_closed_loft(rings, mat_fn=lambda _i, _j: 0))

    return [finalize_bmesh("HullAccent_Spears", bm, col, M["C7_HullAccent"], part="HullAccent", role="paint", sharp_angle=35.0)]


# ---------------------------------------------------------------------------
# 3. Teak Decking, Recessed Low-Profile Foredeck Sunpads & Aft Cockpit Lounge (`Deck`)
# ---------------------------------------------------------------------------
def build_deck_and_cockpit(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    d_mats = [M["C7_Teak"], M["C7_VinylGrey"], M["C7_VinylWhite"], M["C7_VinylDark"], M["C7_HullWhite"], M["C7_Stainless"]]
    bm = bmesh.new()

    # 1) Tapered Swim Platform Burmese Teak Deck Inlay with crisp white yacht perimeter border (`ref_top_image.png`!)
    # Stops at Y = -7.82 (60 mm aft of Step 0 at -7.76 -> GUARANTEED 0 ZF / 0 B2B with boarding steps!)
    teak_plat_rings = []
    for k in range(8):
        u = k / 7.0
        y = lerp(Y_PLAT_AFT + 0.22, -7.82, u)
        hw = lerp(1.56, 1.72, smoothstep(0.0, 0.9, u))
        if u < 0.14:
            hw *= 0.90 + 0.10 * math.sqrt(max(0.0, u / 0.14))
        teak_plat_rings.append([
            Vector((-hw, y, Z_PLAT_TOP - 0.035)),
            Vector((hw, y, Z_PLAT_TOP - 0.035)),
            Vector((hw, y, Z_PLAT_TOP + 0.024)),
            Vector((-hw, y, Z_PLAT_TOP + 0.024)),
        ])
    append_bm(bm, make_closed_loft(teak_plat_rings, mat_fn=lambda _i, _j: 0, cap_start_mat=0, cap_end_mat=0))
    # Boarding step teak treads cleanly shortened & aligned with steps (`xc = ±1.48`, 40 mm clear of next step riser -> 0 B2B!)
    for side in (-1.0, 1.0):
        for sy, sz, tw in ((-7.56, 1.410, 0.46), (-7.18, 1.570, 0.42), (-6.80, 1.730, 0.38)):
            append_bm(bm, make_box_bm((tw, 0.25, 0.056), (side * 1.48, sy - 0.03, sz + 0.002), bevel=0.008, mat_idx=0))

    # 2) Aft Transom Cockpit Sunpad / L-Lounge Bench + Dark Charcoal Backrest (all staggered >= 20 mm -> 0 B2B!)
    append_bm(bm, make_box_bm((2.60, 1.02, 0.52), (0.0, -5.80, 1.925), bevel=0.036, mat_idx=4))
    append_bm(bm, make_box_bm((2.68, 0.92, 0.19), (0.0, -5.62, 2.230), bevel=0.042, mat_idx=2))
    append_bm(bm, make_box_bm((2.44, 0.32, 0.50), (0.0, -6.12, 2.330), rot_deg=(-16.0, 0.0, 0.0), bevel=0.055, mat_idx=3))
    append_bm(bm, make_box_bm((0.68, 1.46, 0.49), (1.36, -4.78, 1.930), bevel=0.035, mat_idx=4))
    append_bm(bm, make_box_bm((0.72, 1.50, 0.18), (1.36, -4.78, 2.220), bevel=0.040, mat_idx=2))

    # Glossy Teak Cockpit Dining Table on Twin Chrome Pedestals
    append_bm(bm, make_rrect_extrude_bm(1.36, 0.76, 0.09, 2.42, 2.49, center_xy=(0.15, -4.82), seg=4, mat_idx=0))
    for px in (-0.28, 0.58):
        append_bm(bm, make_cylinder_bm(0.048, 0.048, 0.80, (px, -4.82, 2.06), seg=16, mat_idx=5))
        append_bm(bm, make_cylinder_bm(0.115, 0.105, 0.075, (px, -4.82, 1.705), seg=18, mat_idx=5))

    # 3) Sleek Low-Profile Foredeck Split Grey Sunpad Loungers + Low Teak Trays (`ref_front_image.png` & `ref_top_image.png`!)
    # Cleanly separated in X from center skylights (`+/-0.32`) and from side trays (`+/-1.26`) -> ZERO coplanar faces!
    for side in (-1.0, 1.0):
        z_f = foredeck_crown_z(6.28)
        append_bm(bm, make_box_bm((0.68, 1.92, 0.18), (side * 0.78, 6.28, z_f - 0.015), rot_deg=(-1.4, side * 2.5, 0.0), bevel=0.042, mat_idx=1))
        append_bm(bm, make_box_bm((0.58, 0.34, 0.18), (side * 0.78, 5.44, z_f + 0.055), rot_deg=(24.0, 0.0, 0.0), bevel=0.040, mat_idx=1))
        t_tray = exact_t_at_yz(5.05, 2.75)
        z_tray = hull_sheer_z(t_tray)
        append_bm(bm, make_box_bm((0.20, 0.54, 0.16), (side * 1.24, 5.05, z_tray - 0.032), bevel=0.018, mat_idx=0))

    z_b = foredeck_crown_z(4.38)
    append_bm(bm, make_box_bm((2.42, 0.64, 0.20), (0.0, 4.38, z_b - 0.010), bevel=0.042, mat_idx=1))
    append_bm(bm, make_box_bm((2.32, 0.22, 0.22), (0.0, 4.04, z_b + 0.085), rot_deg=(-16.0, 0.0, 0.0), bevel=0.042, mat_idx=1))

    # Molded Curved Teak Side-Deck Walk-Around Inlay Planks strictly inboard of outer hull wall (ZERO side-hull hairline!)
    for side in (-1.0, 1.0):
        for y0, y1, has_sill in ((-5.45, -3.76, False), (-3.42, 1.55, True)):
            walk_rings = []
            for k in range(10):
                u = k / 9.0
                y = lerp(y0, y1, u)
                t = exact_t_at_yz(y, 2.45)
                z_w = lerp(Z_COCKPIT_SOLE + 0.15, hull_sheer_z(t) - 0.14, smoothstep(-5.8, 3.2, y))
                if has_sill:
                    x_out = min(hull_half_beam(t) - 0.26, outer_x_at_yz(y, z_w) - 0.25)
                    x_in = max(x_out - 0.13, salon_half_width(y, z_w) + 0.075)
                else:
                    # Aft cockpit walkway: keep 38 cm strictly inboard of curved transom hull wall -> ZERO hairline!
                    x_out = min(hull_half_beam(t) - 0.38, outer_x_at_yz(y, z_w) - 0.38)
                    x_in = x_out - 0.16
                walk_rings.append([
                    Vector((side * x_in, y, z_w - 0.042)),
                    Vector((side * x_out, y, z_w - 0.042)),
                    Vector((side * x_out, y, z_w + 0.024)),
                    Vector((side * x_in, y, z_w + 0.024)),
                ])
            append_bm(bm, make_closed_loft(walk_rings, mat_fn=lambda _i, _j: 0, cap_start_mat=0, cap_end_mat=0))

    return [finalize_bmesh("Deck_TeakAndCushions", bm, col, d_mats, part="Deck", sharp_angle=36.0)]


# ---------------------------------------------------------------------------
# 4. Sweeping Coupe Salon Arch, Low Flybridge Brow, AFT-SWEPT Boomerang Arch & Pure-White Gull-Wing Hardtop (`Superstructure`)
# ---------------------------------------------------------------------------
def build_superstructure(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    s_mats = [M["C7_HullWhite"], M["C7_BlackTrim"], M["C7_SunroofCanvas"], M["C7_DeckWhite"], M["C7_DashDark"]]
    bm = bmesh.new()

    # 1) Sweeping Crescent Salon Roofline Arch Beams (`ref_side_image.png` & `ref_front_image.png`!)
    for side in (-1.0, 1.0):
        arch_rings = []
        for k in range(32):
            u = k / 31.0
            y = lerp(-4.95, 3.46, u)
            zr = salon_roof_z(y)
            w_out = salon_half_width(y, zr)
            beam_h = lerp(0.17, 0.11, abs(2.0 * u - 1.0))
            beam_w = lerp(0.15, 0.10, smoothstep(0.50, 1.0, u))
            xo = side * (w_out + 0.015)
            xi = side * (w_out - beam_w)
            arch_rings.append([
                Vector((xi, y, zr - beam_h)),
                Vector((xo, y, zr - beam_h * 0.70)),
                Vector((xo, y, zr + 0.025)),
                Vector((xi, y, zr + 0.045)),
            ])
        append_bm(bm, make_closed_loft(arch_rings, mat_fn=lambda _i, _j: 0))

        # Lower salon window sill rail seated into hull walk-around deck (clamped strictly inside bow flare -> 0 poke-through on colored hulls!)
        sill_rings = []
        for k in range(22):
            u = k / 21.0
            y = lerp(-4.85, 3.40, u)
            z_top = lerp(2.36, 2.66, smoothstep(-4.85, 3.40, y))
            z_bot = lerp(Z_SALON_SOLE - 0.12, 2.48, smoothstep(0.40, 3.40, y))
            w_out = salon_half_width(y, z_top) + 0.032
            w_bot_out = min(w_out, outer_x_at_yz(y, z_bot) - 0.22)
            w_in = min(w_out, w_bot_out) - 0.14
            sill_rings.append([
                Vector((side * w_in, y, z_bot)),
                Vector((side * w_bot_out, y, z_bot)),
                Vector((side * w_out, y, z_top)),
                Vector((side * w_in, y, z_top)),
            ])
        append_bm(bm, make_closed_loft(sill_rings, mat_fn=lambda _i, _j: 0))

        # SIGNATURE PARTIAL WHITE AERODYNAMIC "WAVE-FIN" CLIP (`ref_side_image.png` 1:1!)
        fin_rings = []
        for k in range(10):
            u = k / 9.0
            y_aft = lerp(-1.82, -1.30, u ** 0.82)
            y_fwd = lerp(-0.30, -1.06, u ** 1.12)
            z_c = lerp(2.36, 3.04, u)
            w_c = salon_half_width(0.5 * (y_aft + y_fwd), z_c)
            xo = side * (w_c + 0.052)
            xi = side * (w_c - 0.130)
            fin_rings.append([
                Vector((xi, y_aft, z_c)),
                Vector((xo, y_aft, z_c)),
                Vector((xo, y_fwd, z_c)),
                Vector((xi, y_fwd, z_c)),
            ])
        append_bm(bm, make_closed_loft(fin_rings, mat_fn=lambda _i, _j: 0))

        # Slender dark angled mullion continuing from wave-fin tip up to the salon roof arch
        append_bm(
            bm,
            make_tube_bm(
                [
                    Vector((side * (salon_half_width(-1.22, 2.95) - 0.02), -1.22, 2.95)),
                    Vector((side * (salon_half_width(-1.82, salon_roof_z(-1.82)) - 0.02), -1.82, salon_roof_z(-1.82) - 0.01)),
                ],
                radius=0.032,
                seg=8,
                mat_idx=1,
            ),
        )

        # Slender dark vertical mid-salon slider mullion (`ref_side_image.png` & `ref_hero_image.png`!)
        y_m = 0.55
        z_mt = salon_roof_z(y_m) - 0.01
        w_m = salon_half_width(y_m, 3.05)
        append_bm(
            bm,
            make_box_bm(
                (0.080, 0.068, z_mt - 2.44),
                (side * (w_m - 0.025), y_m, 0.5 * (z_mt + 2.44)),
                rot_deg=(-6.0, 0.0, 0.0),
                bevel=0.012,
                mat_idx=1,
            ),
        )

    # 2) Crisp Razor-Thin Windshield Center Mullion + Low Flush Cowl & Header (`ref_front_image.png` 1:1!)
    ws_pts = [Vector((0.0, lerp(3.46, 1.48, u), lerp(2.64, 3.68, u))) for u in (0.0, 0.33, 0.67, 1.0)]
    append_bm(bm, make_tube_bm(ws_pts, radius=0.036, seg=10, mat_idx=0))
    brow_lo_pts = [
        Vector((x, 3.48 - 0.14 * ((x / 1.80) ** 2), 2.66 - 0.04 * ((x / 1.80) ** 2)))
        for x in (-1.80, -1.20, -0.60, 0.0, 0.60, 1.20, 1.80)
    ]
    append_bm(bm, make_tube_bm(brow_lo_pts, radius=0.038, seg=10, mat_idx=0))
    brow_hi_pts = [
        Vector((x, 1.50 - 0.11 * ((x / 1.46) ** 2), 3.68 - 0.03 * ((x / 1.46) ** 2)))
        for x in (-1.46, -0.97, -0.49, 0.0, 0.49, 0.97, 1.46)
    ]
    append_bm(bm, make_tube_bm(brow_hi_pts, radius=0.056, seg=10, mat_idx=0))

    # 3) Main Salon Roof & Gracefully Tapered Aerodynamic Boat-Tail Flybridge Nacelle (`ref_side_image.png` 1:1!)
    fb_rings = []
    for k in range(30):
        u = k / 29.0
        y = lerp(-5.72, 1.44, u)
        fw = flybridge_half_width(min(y, 1.05))
        aft_u = max(0.0, (-3.15 - y) / 2.57)
        # Smooth upward sweeping boat-tail underside (`3.54 -> 3.96` at stern tip!) matching `ref_side_image.png`!
        z_bot = 3.54 + 0.36 * (aft_u ** 1.35)
        z_top = Z_FB_FLOOR + 0.18 * (max(0.0, (-5.10 - y) / 0.62) ** 1.8)
        if z_bot > z_top - 0.08:
            z_bot = z_top - 0.08
        fb_rings.append([
            Vector((-fw * 0.84, y, z_bot)),
            Vector((0.0, y, z_bot - 0.025)),
            Vector((fw * 0.84, y, z_bot)),
            Vector((fw, y, lerp(z_bot, z_top, 0.62))),
            Vector((fw, y, z_top)),
            Vector((0.0, y, z_top + 0.010)),
            Vector((-fw, y, z_top)),
            Vector((-fw, y, lerp(z_bot, z_top, 0.62))),
        ])
    append_bm(bm, make_closed_loft(fb_rings, mat_fn=lambda _i, j: 3 if j in (4, 5) else 0))

    # 4) Sleek Low Tapered 32 cm White Flybridge U-Perimeter Brow (`ref_front_image.png` 1:1!)
    u_coam_rings = []
    path_u: list[tuple[float, float, float, float, float]] = []
    for k in range(16):
        s = k / 15.0
        y = lerp(-5.58, 0.45, s)
        fw = flybridge_half_width(y)
        zt = lerp(4.02, Z_FB_COAMING + 0.01, smoothstep(-5.0, 0.3, y))
        path_u.append((-fw, y, -1.0, 0.0, zt))
    for k in range(1, 12):
        ang = math.radians(lerp(-82.0, 82.0, k / 12.0))
        x = 1.38 * math.sin(ang)
        y = 0.48 + 0.56 * math.cos(ang)
        zt = Z_FB_COAMING + 0.018 * math.cos(ang)
        path_u.append((x, y, math.sin(ang), math.cos(ang), zt))
    for k in range(16):
        s = k / 15.0
        y = lerp(0.45, -5.58, s)
        fw = flybridge_half_width(y)
        zt = lerp(Z_FB_COAMING + 0.01, 4.02, smoothstep(0.3, -5.0, y))
        path_u.append((fw, y, 1.0, 0.0, zt))

    for xo, yo, nx, ny, zt in path_u:
        xi, yi = xo - nx * 0.16, yo - ny * 0.16
        xo_t, yo_t = xo - nx * 0.075, yo - ny * 0.075
        u_coam_rings.append([
            Vector((xi, yi, Z_FB_FLOOR - 0.035)),
            Vector((xo + nx * 0.015, yo + ny * 0.015, Z_FB_FLOOR - 0.035)),
            Vector((xo_t, yo_t, zt)),
            Vector((xi, yi, zt)),
        ])
    append_bm(bm, make_closed_loft(u_coam_rings, mat_fn=lambda _i, _j: 0))

    # Aft flybridge low transom coaming bar (staggered bottom Z_FB_FLOOR - 0.055 -> 0 B2B!)
    append_bm(bm, make_box_bm((2.58, 0.16, 0.30), (0.0, -5.56, Z_FB_FLOOR + 0.135), bevel=0.032, mat_idx=0))

    # Crisp Black Anodized Flybridge Venturi Windscreen Frame & 4 Vertical Mullions (`ref_side` & `ref_front` 1:1!)
    # Smooth continuous aft-raked upper brow with zero side-wing kink!
    vent_top_pts = []
    vent_bot_pts = []
    for k in range(25):
        u = k / 24.0
        if u < 0.25:
            s = u / 0.25
            y = lerp(-1.65, 0.54, s)
            x = -flybridge_half_width(y) + 0.10
            z_t = lerp(4.06, Z_FB_VENTURI, smoothstep(0.0, 1.0, s))
            z_b = lerp(4.02, Z_FB_COAMING + 0.01, smoothstep(0.0, 1.0, s))
            dy_rake = -0.02 * s
        elif u <= 0.75:
            ang = math.radians(lerp(-84.0, 84.0, (u - 0.25) / 0.50))
            x = 1.34 * math.sin(ang)
            y = 0.54 + 0.42 * math.cos(ang)
            z_t = Z_FB_VENTURI + 0.015 * math.cos(ang)
            z_b = Z_FB_COAMING + 0.015 * math.cos(ang)
            dy_rake = -0.02 - 0.15 * math.cos(ang)
        else:
            s = (u - 0.75) / 0.25
            y = lerp(0.54, -1.65, s)
            x = flybridge_half_width(y) - 0.10
            z_t = lerp(Z_FB_VENTURI, 4.06, smoothstep(0.0, 1.0, s))
            z_b = lerp(Z_FB_COAMING + 0.01, 4.02, smoothstep(0.0, 1.0, s))
            dy_rake = -0.02 * (1.0 - s)
        vent_top_pts.append(Vector((x, y + dy_rake, z_t)))
        vent_bot_pts.append(Vector((x, y, z_b)))
    append_bm(bm, make_tube_bm(vent_top_pts, radius=0.022, seg=8, mat_idx=1))
    append_bm(bm, make_tube_bm(vent_bot_pts, radius=0.020, seg=8, mat_idx=1))

    for ang_deg in (-68.0, -24.0, 24.0, 68.0):
        ang = math.radians(ang_deg)
        mx = 1.34 * math.sin(ang)
        my = 0.54 + 0.42 * math.cos(ang)
        append_bm(
            bm,
            make_box_bm((0.028, 0.044, 0.36), (mx, my - 0.01 - 0.075 * math.cos(ang), 4.22), rot_deg=(-22.0, 0.0, -ang_deg), bevel=0.007, mat_idx=1),
        )

    # 5) ICONIC AFT-SWEPT BOOMERANG WHITE FLYBRIDGE ARCH WINGS (`ref_side_image.png` & `ref_front_image.png` 1:1!)
    for side in (-1.0, 1.0):
        wing_rings = []
        for k in range(14):
            u = k / 13.0
            y_c = lerp(-2.15, -4.32, u ** 0.90)
            z_c = lerp(3.92, Z_HARDTOP_BOT + 0.12, u)
            x_out = side * lerp(1.36, 1.20, u ** 1.1)
            x_in = side * lerp(1.16, 1.02, u ** 1.1)
            chord = lerp(1.22, 0.84, math.sin(math.pi * 0.65 * u)) + 0.48 * (u ** 2.6)
            wing_rings.append([
                Vector((x_in, y_c - chord * 0.5, z_c)),
                Vector((x_out, y_c - chord * 0.5, z_c)),
                Vector((x_out, y_c + chord * 0.5, z_c)),
                Vector((x_in, y_c + chord * 0.5, z_c)),
            ])
        append_bm(bm, make_closed_loft(wing_rings, mat_fn=lambda _i, _j: 0))

        # Slender dark aft corner support stanchion leaning gently forward (`ref_side_image.png`!)
        append_bm(
            bm,
            make_tube_bm(
                [Vector((side * 1.28, -5.36, 3.92)), Vector((side * 1.18, -5.18, Z_HARDTOP_BOT + 0.10))],
                radius=0.022,
                seg=10,
                mat_idx=1,
            ),
        )
        # Ultra-sleek angled dark front venturi-to-hardtop tie strut seated solidly inside hardtop soffit (`ref_front_image.png`!)
        append_bm(
            bm,
            make_tube_bm(
                [Vector((side * 1.24, -1.45, 4.10)), Vector((side * 1.08, -1.28, Z_HARDTOP_BOT + 0.12))],
                radius=0.017,
                seg=10,
                mat_idx=1,
            ),
        )

    # 6) Pure-White Sculpted Aerodynamic Forward-Cantilevered Whale-Brow Hardtop Canopy (`ref_side`, `ref_front` & `ref_top` 1:1!)
    # Ends cleanly at Y = -0.35 so TOP view clearly reveals the open forward flybridge lounge & teak walk borders (`ref_top_image.png`!)
    ht_rings = []
    for k in range(26):
        u = k / 25.0
        y = lerp(-5.45, -0.35, u)
        if u > 0.64:
            uf = (u - 0.64) / 0.36
            hw = 1.32 * math.sqrt(max(0.10, 1.0 - 0.78 * (uf ** 2)))
        elif u < 0.14:
            ua = (0.14 - u) / 0.14
            hw = 1.32 * (1.0 - 0.12 * (ua ** 2))
        else:
            hw = 1.32
        arch_z = 0.085
        # Sculpted chunky rounded white fiberglass visor brow (fuller aerodynamic front nose -> 1:1 with `ref_side_image.png`!)
        nose_droop = -0.040 * (max(0.0, (u - 0.72) / 0.28) ** 2.0)
        z_tip = Z_HARDTOP_BOT + 0.04 * (u ** 1.3) + nose_droop
        z_bot_c = z_tip + arch_z
        taper_nose = math.sqrt(max(0.42, 1.0 - max(0.0, (u - 0.70) / 0.30) ** 2.0))
        taper_tail = math.sqrt(max(0.68, 1.0 - max(0.0, (0.12 - u) / 0.12) ** 2.0))
        thick_c = lerp(0.16, 0.25, math.sin(math.pi * (0.20 + 0.68 * u))) * taper_nose * taper_tail
        thick_e = lerp(0.12, 0.20, math.sin(math.pi * (0.20 + 0.68 * u))) * taper_nose * taper_tail
        z_top_c = z_bot_c + thick_c
        z_top_edge = z_tip + thick_e
        ht_rings.append([
            Vector((-hw * 0.84, y, z_tip)),
            Vector((0.0, y, z_bot_c)),
            Vector((hw * 0.84, y, z_tip)),
            Vector((hw, y, 0.5 * (z_tip + z_top_edge))),
            Vector((hw * 0.84, y, z_top_edge)),
            Vector((0.0, y, z_top_c)),
            Vector((-hw * 0.84, y, z_top_edge)),
            Vector((-hw, y, 0.5 * (z_tip + z_top_edge))),
        ])
    def ht_mat_fn(i: int, j: int) -> int:
        if j in (0, 1):
            return 4  # sleek dark soffit underside (`ref_front_image.png`!)
        y_mid = 0.5 * (ht_rings[i][5].y + ht_rings[i + 1][5].y)
        if j in (4, 5) and (-3.95 <= y_mid <= -1.45):
            return 2  # flush light-grey retractable canvas sunroof (`ref_top_image.png`!)
        return 0  # pure brilliant sculpted white hardtop gelcoat!

    append_bm(bm, make_closed_loft(ht_rings, mat_fn=ht_mat_fn, cap_start_mat=0, cap_end_mat=0))

    return [finalize_bmesh("Superstructure_ArchHardtop", bm, col, s_mats, part="Superstructure", sharp_angle=35.0)]


# ---------------------------------------------------------------------------
# 5. Visible Luxury Main-Deck Salon Interior (`InteriorSalon` — from `ref_hero_image.png`!)
# ---------------------------------------------------------------------------
def build_interior_salon(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    i_mats = [
        M["C7_WalnutCab"],
        M["C7_Marble"],
        M["C7_VinylWhite"],
        M["C7_Stainless"],
        M["C7_DashDark"],
        M["C7_ScreenGlow"],
    ]
    bm = bmesh.new()
    # Every base strictly penetrates 40..60 mm below Z_SALON_SOLE (`1.880`) at unique non-coplanar Z heights!
    zb = Z_SALON_SOLE - 0.050  # 1.830 m

    # 1) Port Aft L-Shaped Galley (Marble countertop bottom = cabinet top - 30 mm -> 0 B2B!)
    append_bm(bm, make_box_bm((0.88, 1.80, 0.88), (-1.20, -2.55, zb + 0.440), bevel=0.014, mat_idx=0))
    append_bm(bm, make_box_bm((0.96, 1.88, 0.085), (-1.18, -2.55, zb + 0.895), bevel=0.012, mat_idx=1))
    # Peninsula return (penetrates 60 mm into main galley, top 27 mm below main marble, faucet bottom 40 mm below main cabinet top -> 0 B2B!)
    append_bm(bm, make_box_bm((0.60, 0.54, 0.80), (-0.52, -1.90, zb + 0.425), bevel=0.014, mat_idx=0))
    append_bm(bm, make_box_bm((0.66, 0.60, 0.085), (-0.52, -1.90, zb + 0.865), bevel=0.012, mat_idx=1))
    append_bm(bm, make_cylinder_bm(0.018, 0.015, 0.30, (-0.78, -1.90, zb + 0.990), seg=10, mat_idx=3))

    # 2) Starboard Aft Galley / Credenza + Twin Brushed Stainless Fridge Drawers
    append_bm(bm, make_box_bm((0.84, 1.50, 0.88), (1.22, -2.68, zb + 0.440), bevel=0.014, mat_idx=0))
    append_bm(bm, make_box_bm((0.92, 1.58, 0.085), (1.20, -2.68, zb + 0.895), bevel=0.012, mat_idx=1))
    for dz in (0.30, 0.64):
        append_bm(bm, make_box_bm((0.06, 0.62, 0.25), (0.795, -2.28, zb + dz), bevel=0.008, mat_idx=3))

    # 3) Starboard Modern White Leather Lounge Sofa (backrest 1.82 m -> 20 mm inside seat 1.86 m AND 10 mm into armrest -> 0 ZF / 0 B2B!)
    append_bm(bm, make_box_bm((0.84, 1.86, 0.44), (1.14, -0.70, zb + 0.220), bevel=0.036, mat_idx=2))
    append_bm(bm, make_box_bm((0.24, 1.82, 0.54), (1.44, -0.70, zb + 0.560), rot_deg=(0.0, 10.0, 0.0), bevel=0.040, mat_idx=2))
    append_bm(bm, make_box_bm((0.76, 0.24, 0.50), (1.14, -1.72, zb + 0.305), bevel=0.034, mat_idx=2))

    # 4) Port Elevated Dinette Sofa + Glossy Walnut Pedestal Table
    append_bm(bm, make_box_bm((0.80, 1.88, 0.45), (-1.16, -0.15, zb + 0.225), bevel=0.036, mat_idx=2))
    append_bm(bm, make_box_bm((0.22, 1.80, 0.52), (-1.46, -0.15, zb + 0.565), rot_deg=(0.0, -10.0, 0.0), bevel=0.040, mat_idx=2))
    append_bm(bm, make_rrect_extrude_bm(0.68, 1.12, 0.06, zb + 0.72, zb + 0.79, center_xy=(-0.54, -0.12), seg=3, mat_idx=0))
    append_bm(bm, make_box_bm((0.20, 0.26, 0.78), (-0.54, -0.12, zb + 0.390), bevel=0.02, mat_idx=0))

    # 5) Forward Starboard Lower Helm Station Console + Dual Glowing Garmin MFDs
    append_bm(bm, make_box_bm((1.34, 0.88, 0.90), (0.68, 2.15, zb + 0.450), bevel=0.042, mat_idx=0))
    append_bm(bm, make_box_bm((1.20, 0.50, 0.28), (0.68, 2.08, zb + 0.865), rot_deg=(24.0, 0.0, 0.0), bevel=0.030, mat_idx=4))
    for mx in (0.42, 0.92):
        append_bm(bm, make_box_bm((0.38, 0.08, 0.23), (mx, 1.88, zb + 0.945), rot_deg=(-64.0, 0.0, 0.0), bevel=0.008, mat_idx=5))

    # 6) Twin White Sculpted Captain's Helm Chairs on Chrome Pedestals (armrests embed 14 cm INTO backrest -> 0 floating, 0 ZF!)
    for cx in (0.38, 1.00):
        append_bm(bm, make_cylinder_bm(0.14, 0.12, 0.085, (cx, 1.25, zb + 0.042), seg=16, mat_idx=3))
        append_bm(bm, make_cylinder_bm(0.055, 0.055, 0.64, (cx, 1.25, zb + 0.360), seg=14, mat_idx=3))
        append_bm(bm, make_box_bm((0.52, 0.48, 0.16), (cx, 1.30, zb + 0.660), bevel=0.034, mat_idx=2))
        append_bm(bm, make_box_bm((0.46, 0.16, 0.68), (cx, 1.04, zb + 0.990), rot_deg=(-10.0, 0.0, 0.0), bevel=0.040, mat_idx=2))
        for ax in (-0.23, 0.23):
            append_bm(bm, make_box_bm((0.075, 0.36, 0.095), (cx + ax, 1.16, zb + 0.805), bevel=0.018, mat_idx=2))

    # 7) Overhead Glossy Walnut Valance Cabinets tucked neatly INBOARD (`X = +/-1.18`, `Z = 3.38..3.68` -> never peeks out side windows!)
    for side in (-1.0, 1.0):
        append_bm(bm, make_box_bm((0.30, 2.70, 0.28), (side * 1.16, -2.05, 3.52), bevel=0.020, mat_idx=0))

    return [finalize_bmesh("InteriorSalon_Furnishings", bm, col, i_mats, part="InteriorSalon", sharp_angle=35.0)]


# ---------------------------------------------------------------------------
# 6. Upper Flybridge Helm, Seating, Wetbar & Lounge (`Flybridge` — from `ref_top_image.png`!)
# ---------------------------------------------------------------------------
def build_flybridge_interior(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    f_mats = [
        M["C7_HullWhite"],
        M["C7_VinylWhite"],
        M["C7_VinylGrey"],
        M["C7_Teak"],
        M["C7_DashDark"],
        M["C7_ScreenGlow"],
        M["C7_Stainless"],
    ]
    bm = bmesh.new()
    # Distinct bottom Z per furniture zone -> GUARANTEED ZERO coplanar floor overlaps!
    zf = Z_FB_FLOOR  # 3.740 m

    # 1) Flybridge Teak Walk-Aisle Strips (inboard of sofa plinths & wetbar -> ZERO floor z-fighting!)
    for side in (-1.0, 1.0):
        append_bm(bm, make_box_bm((0.20, 3.60, 0.046), (side * 0.44, -2.55, zf + 0.008), bevel=0.008, mat_idx=3))

    # 2) Forward Curved Flybridge Helm Console + Dual Garmin MFDs (dash hood embedded 55 mm into console -> 0 B2B!)
    append_bm(bm, make_box_bm((1.30, 0.72, 0.72), (0.0, 0.42, zf + 0.305), bevel=0.045, mat_idx=0))
    append_bm(bm, make_box_bm((1.10, 0.40, 0.24), (0.0, 0.36, zf + 0.610), rot_deg=(24.0, 0.0, 0.0), bevel=0.028, mat_idx=4))
    for mx in (-0.25, 0.25):
        append_bm(bm, make_box_bm((0.35, 0.08, 0.21), (mx, 0.17, zf + 0.680), rot_deg=(-64.0, 0.0, 0.0), bevel=0.008, mat_idx=5))

    # 3) Twin Flybridge Bolster Captain Chairs
    for cx in (-0.34, 0.34):
        append_bm(bm, make_cylinder_bm(0.13, 0.11, 0.080, (cx, -0.40, zf + 0.000), seg=16, mat_idx=6))
        append_bm(bm, make_cylinder_bm(0.05, 0.05, 0.58, (cx, -0.40, zf + 0.280), seg=14, mat_idx=6))
        append_bm(bm, make_box_bm((0.48, 0.46, 0.16), (cx, -0.37, zf + 0.560), bevel=0.034, mat_idx=1))
        append_bm(bm, make_box_bm((0.44, 0.15, 0.52), (cx, -0.56, zf + 0.830), rot_deg=(-10.0, 0.0, 0.0), bevel=0.038, mat_idx=1))

    # 4) Starboard U-Shaped Flybridge Lounge Sofa + Glossy Teak Dinette Table (`ref_top_image.png`!)
    # Strictly staggered X/Y/Z between plinth, cushion & backrest -> 0 ZF / 0 B2B!
    append_bm(bm, make_box_bm((0.60, 2.52, 0.44), (0.96, -2.75, zf + 0.175), bevel=0.028, mat_idx=0))
    append_bm(bm, make_box_bm((0.68, 2.60, 0.18), (0.96, -2.75, zf + 0.440), bevel=0.038, mat_idx=2))
    append_bm(bm, make_box_bm((0.18, 2.48, 0.36), (1.15, -2.75, zf + 0.640), bevel=0.036, mat_idx=2))

    append_bm(bm, make_box_bm((1.94, 0.72, 0.42), (-0.06, -4.64, zf + 0.180), bevel=0.028, mat_idx=0))
    append_bm(bm, make_box_bm((2.02, 0.78, 0.18), (-0.06, -4.64, zf + 0.430), bevel=0.038, mat_idx=2))
    append_bm(bm, make_box_bm((1.88, 0.20, 0.35), (-0.06, -4.92, zf + 0.625), bevel=0.038, mat_idx=2))

    append_bm(bm, make_rrect_extrude_bm(0.80, 1.24, 0.08, zf + 0.66, zf + 0.73, center_xy=(0.04, -2.85), seg=4, mat_idx=3))
    append_bm(bm, make_cylinder_bm(0.055, 0.055, 0.76, (0.04, -2.85, zf + 0.340), seg=16, mat_idx=6))

    # 5) Port Flybridge Wetbar / Grill Cabinet (bottom at `zf - 0.048`, clear of teak & coaming!)
    append_bm(bm, make_box_bm((0.50, 1.36, 0.80), (-0.98, -2.45, zf + 0.352), bevel=0.028, mat_idx=0))
    append_bm(bm, make_box_bm((0.44, 0.54, 0.16), (-0.98, -2.45, zf + 0.785), bevel=0.015, mat_idx=6))

    return [finalize_bmesh("Flybridge_Outfitting", bm, col, f_mats, part="Flybridge", sharp_angle=35.0)]


# ---------------------------------------------------------------------------
# 7. All Dark-Tinted Marine Glazing (`Glass` — Pitch-Obsidian Hull Glass + Clear Smoked Windshield + Dark Venturi!)
# ---------------------------------------------------------------------------
def build_glass(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    # 0 = C7_Glass (clear windshield & aft door), 1 = C7_HullGlass (jet-black hull windows),
    # 2 = C7_VenturiGlass (smoked venturi), 3 = C7_SideGlass (sleek dark coupe side glass), 4 = C7_SkylightGlass
    g_mats = [M["C7_Glass"], M["C7_HullGlass"], M["C7_VenturiGlass"], M["C7_SideGlass"], M["C7_SkylightGlass"]]
    bm = bmesh.new()

    # 1) Iconic 6-Pane Trapezoidal Midship Master Hull Window (`ref_side_image.png` 1:1, sleek +11 mm flush!)
    for side in (-1.0, 1.0):
        rings = []
        n_y = 9
        for k in range(14):
            u = k / 13.0
            z = lerp(1.44, 2.15, u)
            y_aft = lerp(-2.72, -3.45, u)
            y_fwd = lerp(0.05, 1.02, u)
            ys = [lerp(y_aft, y_fwd, m / (n_y - 1)) for m in range(n_y)]
            outer_pts = [Vector((side * (outer_x_at_yz(yy, z) + 0.011), yy, z)) for yy in ys]
            inner_pts = [Vector((side * (outer_x_at_yz(yy, z) - 0.055), yy, z)) for yy in reversed(ys)]
            rings.append(outer_pts + inner_pts)
        append_bm(bm, make_closed_loft(rings, mat_fn=lambda _i, _j: 1, cap_start_mat=1, cap_end_mat=1))

    # 2) Forward VIP & Bow Stateroom Pitch-Obsidian Hull Windows (`ref_side_image.png` & `ref_front_image.png` 1:1!)
    fwd_windows = [
        (1.82, 4.18, 1.84, 2.30),  # Mid-forward VIP stateroom window (crisp 46 cm tall!)
        (4.65, 6.82, 1.90, 2.37),  # Forward bow stateroom window (`ref_front_image.png` 1:1!)
    ]
    for side in (-1.0, 1.0):
        for y0, y1, z0, z1 in fwd_windows:
            rings = []
            for k in range(14):
                u = k / 13.0
                y = lerp(y0, y1, u)
                zb = z0 + 0.03 * u
                zt = z1 + 0.03 * u
                xb = outer_x_at_yz(y, zb)
                xt = outer_x_at_yz(y, zt)
                rings.append([
                    Vector((side * (xb - 0.055), y, zb)),
                    Vector((side * (xb + 0.011), y, zb)),
                    Vector((side * (xt + 0.011), y, zt)),
                    Vector((side * (xt - 0.055), y, zt)),
                ])
            append_bm(bm, make_closed_loft(rings, mat_fn=lambda _i, _j: 1, cap_start_mat=1, cap_end_mat=1))

    # 3) Wide Open 2-Pane Raked Panoramic Main Salon Windshield (`ref_front_image.png` & `ref_top_image.png` 1:1!)
    ws_rings = []
    for k in range(17):
        u = k / 16.0
        ang_x = lerp(-1.0, 1.0, u)
        x_b = 1.76 * ang_x
        y_b = 3.46 - 0.14 * (ang_x ** 2)
        z_b = 2.66 - 0.04 * (ang_x ** 2)
        x_t = 1.44 * ang_x
        y_t = 1.50 - 0.11 * (ang_x ** 2)
        z_t = 3.68 - 0.03 * (ang_x ** 2)
        ws_rings.append([
            Vector((x_b, y_b + 0.014, z_b - 0.012)),
            Vector((x_b, y_b - 0.020, z_b + 0.012)),
            Vector((x_t, y_t - 0.020, z_t + 0.012)),
            Vector((x_t, y_t + 0.014, z_t - 0.012)),
        ])
    append_bm(bm, make_closed_loft(ws_rings, mat_fn=lambda _i, _j: 0, cap_start_mat=0, cap_end_mat=0))

    # 4) Continuous Sweeping Panoramic Side Salon Windows (deeply seated 90 mm inside sill & centered -> 0 B2B!)
    for side in (-1.0, 1.0):
        sw_rings = []
        for k in range(26):
            u = k / 25.0
            y = lerp(-4.52, 3.16, u)
            z_bot = lerp(2.26, 2.56, u)
            z_top = salon_roof_z(y) - 0.06
            if z_top - z_bot < 0.08:
                z_top = z_bot + 0.08
            wb = salon_half_width(y, z_bot) - 0.048
            wt = salon_half_width(y, z_top) - 0.048
            sw_rings.append([
                Vector((side * (wb - 0.028), y, z_bot)),
                Vector((side * (wb + 0.008), y, z_bot)),
                Vector((side * (wt + 0.008), y, z_top)),
                Vector((side * (wt - 0.028), y, z_top)),
            ])
        append_bm(bm, make_closed_loft(sw_rings, mat_fn=lambda _i, _j: 3, cap_start_mat=3, cap_end_mat=3))

    # 5) Aft Sliding Salon Glass Bulkhead Doors (width 2.54 m tucked strictly inside flybridge roof & salon arch!)
    append_bm(bm, make_box_bm((2.54, 0.038, 1.88), (0.0, -3.72, 2.66), bevel=0.006, mat_idx=0))

    # 6) Sleek Low Aft-Raked Dark Smoked Flybridge Venturi Windscreen (`ref_side` & `ref_front` 1:1!)
    v_rings = []
    for k in range(25):
        u = k / 24.0
        if u < 0.25:
            s = u / 0.25
            y = lerp(-1.62, 0.54, s)
            x = -flybridge_half_width(y) + 0.10
            z_top = lerp(4.06, Z_FB_VENTURI, smoothstep(0.0, 1.0, s))
            nx, ny = -1.0, 0.0
            dy_rake = -0.02 * s
        elif u <= 0.75:
            ang = math.radians(lerp(-84.0, 84.0, (u - 0.25) / 0.50))
            x = 1.34 * math.sin(ang)
            y = 0.54 + 0.42 * math.cos(ang)
            z_top = Z_FB_VENTURI + 0.015 * math.cos(ang)
            nx, ny = math.sin(ang), math.cos(ang)
            dy_rake = -0.02 - 0.15 * math.cos(ang)
        else:
            s = (u - 0.75) / 0.25
            y = lerp(0.54, -1.62, s)
            x = flybridge_half_width(y) - 0.10
            z_top = lerp(Z_FB_VENTURI, 4.06, smoothstep(0.0, 1.0, s))
            nx, ny = 1.0, 0.0
            dy_rake = -0.02 * (1.0 - s)
        z_bot = Z_FB_COAMING - 0.08
        x_b, y_b = x, y
        x_t, y_t = x, y + dy_rake
        v_rings.append([
            Vector((x_b - nx * 0.014, y_b - ny * 0.014, z_bot)),
            Vector((x_b + nx * 0.014, y_b + ny * 0.014, z_bot)),
            Vector((x_t + nx * 0.014, y_t + ny * 0.014, z_top)),
            Vector((x_t - nx * 0.014, y_t - ny * 0.014, z_top)),
        ])
    append_bm(bm, make_closed_loft(v_rings, mat_fn=lambda _i, _j: 2, cap_start_mat=2, cap_end_mat=2))

    # 7) Twin Parallel Smoked Slate-Grey Foredeck Skylight Hatches (`ref_top_image.png` 1:1!)
    for sx in (-0.175, 0.175):
        z_sky = foredeck_crown_z(6.58)
        append_bm(bm, make_box_bm((0.28, 1.34, 0.090), (sx, 6.58, z_sky - 0.005), rot_deg=(-1.4, 0.0, 0.0), bevel=0.014, mat_idx=4))

    return [finalize_bmesh("Glass_Glazing", bm, col, g_mats, part="Glass", role="glass", sharp_angle=38.0)]


# ---------------------------------------------------------------------------
# 8. 316 Stainless Railings, Wipers, CAD Mooring Cleats & Bow Anchor (`RailsHardware`)
# ---------------------------------------------------------------------------
def build_rails_and_hardware(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    objs: list[bpy.types.Object] = []
    r_mats = [M["C7_Stainless"], M["C7_BlackTrim"]]
    bm = bmesh.new()

    # 1) Sleek Low-Profile Open-Front 316 Stainless Bow Pulpit Railings (`ref_front_image.png` 1:1!)
    for side in (-1.0, 1.0):
        top_pts: list[Vector] = []
        mid_pts: list[Vector] = []
        n_rp = 24
        for k in range(n_rp):
            u = k / (n_rp - 1)
            t = lerp(0.24, 0.990, u)
            sx = hull_half_beam(t)
            sz = hull_sheer_z(t)
            sy = hull_y_at_z(t, sz)
            rx = max(0.30, sx - 0.10)
            rh = lerp(0.14, 0.46, smoothstep(0.0, 0.35, u))
            top_pts.append(Vector((side * rx, sy, sz + rh)))
            mid_pts.append(Vector((side * rx, sy, sz + rh * 0.48)))

        aft_base = Vector((top_pts[0].x, top_pts[0].y, top_pts[0].z - 0.24))
        top_pts.insert(0, aft_base)
        fwd_tip = top_pts[-1]
        fwd_base = Vector((fwd_tip.x, fwd_tip.y - 0.08, hull_sheer_z(0.985) - 0.06))
        top_pts.append(fwd_base)
        append_bm(bm, make_tube_bm(top_pts, radius=0.015, seg=8, mat_idx=0))
        append_bm(bm, make_tube_bm(mid_pts[4:], radius=0.009, seg=8, mat_idx=0))

        for idx in (3, 6, 9, 12, 15, 18, 21, 23):
            p_top = top_pts[idx]
            t_s = exact_t_at_yz(p_top.y, p_top.z - 0.4)
            z_base = hull_sheer_z(t_s) - 0.05
            append_bm(bm, make_tube_bm([Vector((p_top.x, p_top.y, z_base)), p_top], radius=0.011, seg=8, mat_idx=0))

    # 2) Flybridge Aft Perimeter Stainless Safety Rail (`ref_side_image.png`!)
    fb_rail = [
        Vector((-1.26, -3.55, 3.92)),
        Vector((-1.26, -3.55, 4.46)),
        Vector((-1.26, -5.52, 4.46)),
        Vector((0.0, -5.54, 4.46)),
        Vector((1.26, -5.52, 4.46)),
        Vector((1.26, -3.55, 4.46)),
        Vector((1.26, -3.55, 3.92)),
    ]
    append_bm(bm, make_tube_bm(fb_rail, radius=0.017, seg=8, mat_idx=0))
    for sx, sy in ((-1.26, -4.55), (-1.26, -5.52), (-0.58, -5.53), (0.58, -5.53), (1.26, -5.52), (1.26, -4.55)):
        append_bm(bm, make_tube_bm([Vector((sx, sy, 3.88)), Vector((sx, sy, 4.46))], radius=0.012, seg=8, mat_idx=0))

    # 3) Aft Swim Platform Stainless Safety Staple Rails seated squarely inside tapered platform (`ref_top_image.png`!)
    for side in (-1.0, 1.0):
        st_pts = [
            Vector((side * 1.06, -8.78, 1.14)),
            Vector((side * 1.06, -8.78, 1.92)),
            Vector((side * 1.60, -8.78, 1.92)),
            Vector((side * 1.60, -8.78, 1.14)),
        ]
        append_bm(bm, make_tube_bm(st_pts, radius=0.018, seg=8, mat_idx=0))

    # 4) Prominent Crisp Black Pantograph Windshield Wipers (`ref_front_image.png` & `ref_top_image.png` 1:1!)
    for side in (-1.0, 1.0):
        px = side * 0.88
        append_bm(bm, make_cylinder_bm(0.024, 0.020, 0.08, (px, 3.38, 2.70), rot_deg=(58.0, 0.0, 0.0), seg=10, mat_idx=1))
        arm = [
            Vector((px, 3.41, 2.71)),
            Vector((px - side * 0.16, 2.54, 3.15)),
            Vector((px - side * 0.66, 2.66, 3.09)),
        ]
        append_bm(bm, make_tube_bm(arm, radius=0.015, seg=8, mat_idx=1))

    # 5) Gleaming Chrome Bow Searchlight Pod mounted on Bow Stem Cap (`ref_front_image.png`!)
    y_nose = hull_y_at_z(0.985, Z_SHEER_BOW)
    z_nose = hull_sheer_z(0.985)
    append_bm(bm, make_cylinder_bm(0.058, 0.048, 0.14, (0.0, y_nose - 0.18, z_nose + 0.02), seg=16, mat_idx=0))
    append_bm(bm, make_cylinder_bm(0.074, 0.064, 0.17, (0.0, y_nose - 0.14, z_nose + 0.10), rot_deg=(90.0, 0.0, 0.0), seg=16, mat_idx=0))

    objs.append(finalize_bmesh("RailsHardware_Stainless", bm, col, r_mats, part="RailsHardware", sharp_angle=35.0))

    # 6) 6x Precision CAD 320 mm Stainless Mooring Cleats seated 5 mm INTO the flat backing pads!
    for label, yc, z_est in (("Stern", -5.45, 2.48), ("Midship", -1.10, 2.58), ("Bow", 6.95, 2.74)):
        t = exact_t_at_yz(yc, z_est)
        sx = hull_half_beam(t) - 0.105
        sz = hull_sheer_z(t) + 0.0145
        for side, tag in ((-1.0, "Port"), (1.0, "Stbd")):
            objs.append(
                import_cad_glb(
                    "deck_cleat.glb",
                    f"CAD_Cleat_{label}_{tag}",
                    col,
                    M["C7_Stainless"],
                    part="RailsHardware",
                    location=(side * sx, yc, sz),
                    rot_deg=(0.0, 0.0, 90.0),
                    scale=1.0,
                )
            )

    # 7) Precision CAD Polished Stainless Bow Plow Anchor (`bow_anchor.glb`, scale=1.00 nested cleanly in dark shield pocket!)
    y_anc = hull_y_at_z(0.992, 2.18)
    objs.append(
        import_cad_glb(
            "bow_anchor.glb",
            "CAD_BowAnchor",
            col,
            M["C7_Stainless"],
            part="RailsHardware",
            location=(0.0, y_anc + 0.04, 2.16),
            rot_deg=(12.0, 0.0, 0.0),
            scale=1.00,
        )
    )

    return objs


# ---------------------------------------------------------------------------
# 9. Compact Hardtop Electronics: CAD Garmin Radar, Low-Profile Domes & Slender VHF Whips (`Electronics`)
# ---------------------------------------------------------------------------
def build_electronics(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    objs: list[bpy.types.Object] = []
    e_mats = [M["C7_HullWhite"], M["C7_Stainless"]]
    bm = bmesh.new()
    z_roof = Z_HARDTOP_TOP + 0.01

    # Compact aerodynamic white radar mast deeply seated in curved hardtop crown (`ref_front` & `ref_side` 1:1!)
    append_bm(bm, make_rrect_extrude_bm(0.30, 0.42, 0.08, z_roof - 0.18, z_roof + 0.12, center_xy=(0.0, -4.55), taper_top=0.82, seg=4, mat_idx=0))

    # Twin Low-Profile Small White KVH Satcom Domes flanking radar (`ref_front_image.png`!)
    for side in (-1.0, 1.0):
        append_bm(bm, make_cylinder_bm(0.092, 0.082, 0.18, (side * 0.48, -4.64, z_roof - 0.06), seg=16, mat_idx=0))
        d_bm = bmesh.new()
        bmesh.ops.create_uvsphere(d_bm, u_segments=20, v_segments=12, radius=0.112)
        for v in d_bm.verts:
            v.co = Vector((v.co.x + side * 0.48, v.co.y - 4.64, v.co.z * 0.88 + z_roof + 0.09))
        for f in d_bm.faces:
            f.material_index = 0
        append_bm(bm, d_bm)

    # Twin Crisp Ultra-Slender Gently Aft-Raked White VHF/AIS Whip Antennas deeply seated INTO hardtop & base (0 floating!)
    for side in (-1.0, 1.0):
        append_bm(bm, make_cylinder_bm(0.026, 0.018, 0.26, (side * 0.88, -4.92, z_roof - 0.10), seg=12, mat_idx=1))
        whip_pts = [
            Vector((side * 0.88, -4.92, z_roof - 0.12)),
            Vector((side * 0.88, -4.96, z_roof + 0.50)),
            Vector((side * 0.88, -5.03, z_roof + 1.58)),
        ]
        append_bm(bm, make_tube_bm(whip_pts, radius=0.0085, seg=10, mat_idx=0))

    # Compact Aft Anchor Light Mast Pole deeply seated into hardtop crown
    append_bm(bm, make_cylinder_bm(0.012, 0.010, 0.48, (0.0, -4.88, z_roof + 0.16), seg=10, mat_idx=1))

    objs.append(finalize_bmesh("Electronics_DomesAntennas", bm, col, e_mats, part="Electronics", sharp_angle=35.0))

    # Precision CAD Garmin Open-Array Radar Scanner (`radar_scanner.glb`, scaled 0.82 -> exact 1:1 `ref_front` size!)
    objs.append(
        import_cad_glb(
            "radar_scanner.glb",
            "CAD_GarminRadar",
            col,
            M["C7_HullWhite"],
            part="Electronics",
            location=(0.0, -4.55, z_roof + 0.10),
            rot_deg=(0.0, 0.0, 0.0),
            scale=0.82,
        )
    )

    return objs


# ---------------------------------------------------------------------------
# 10. Navigation, Masthead & Underwater Stern LEDs (`Lights`)
# ---------------------------------------------------------------------------
def build_lights(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    l_mats = [M["C7_NavRed"], M["C7_NavGreen"], M["C7_LightWhite"], M["C7_UnderwaterBlue"]]
    bm = bmesh.new()

    append_bm(bm, make_box_bm((0.08, 0.18, 0.05), (-1.68, 1.05, 3.30), bevel=0.012, mat_idx=0))
    append_bm(bm, make_box_bm((0.08, 0.18, 0.05), (1.68, 1.05, 3.30), bevel=0.012, mat_idx=1))
    append_bm(bm, make_cylinder_bm(0.022, 0.022, 0.054, (0.0, -4.88, Z_HARDTOP_TOP + 0.41), seg=12, mat_idx=2))

    y_nose = hull_y_at_z(0.985, Z_SHEER_BOW)
    z_nose = hull_sheer_z(0.985)
    append_bm(bm, make_cylinder_bm(0.058, 0.058, 0.04, (0.0, y_nose - 0.05, z_nose + 0.10), rot_deg=(90.0, 0.0, 0.0), seg=14, mat_idx=2))

    y_tr_led = hull_y_at_z(0.0, 0.84)
    for sx in (-1.10, 1.10):
        append_bm(bm, make_cylinder_bm(0.078, 0.078, 0.16, (sx, y_tr_led + 0.05, 0.84), rot_deg=(90.0, 0.0, 0.0), seg=14, mat_idx=3))

    return [finalize_bmesh("Lights_Navigation", bm, col, l_mats, part="Lights", role="neon", sharp_angle=35.0)]


# ---------------------------------------------------------------------------
# 11. Twin Volvo Penta IPS Pod Drives (`Propulsion`) & CAD 4-Blade Props (`Props`)
# ---------------------------------------------------------------------------
def build_propulsion(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    objs: list[bpy.types.Object] = []
    bm = bmesh.new()

    pod_y = -5.45
    pod_z = 0.280
    for side in (-1.0, 1.0):
        px = side * 1.10
        strut_rings = []
        for k in range(6):
            u = k / 5.0
            z = lerp(pod_z, 0.96, u)
            rx = lerp(0.095, 0.145, u)
            ry = lerp(0.32, 0.42, u)
            strut_rings.append([
                Vector((px + rx * math.sin(a), pod_y + ry * math.cos(a), z))
                for a in (2.0 * math.pi * j / 16.0 for j in range(16))
            ])
        append_bm(bm, make_closed_loft(strut_rings))

        torp_rings = []
        for ty, tr in ((-6.12, 0.035), (-5.96, 0.115), (-5.50, 0.140), (-5.02, 0.125), (-4.72, 0.085), (-4.62, 0.055)):
            torp_rings.append([
                Vector((px + tr * math.cos(a), ty, pod_z + tr * math.sin(a)))
                for a in (2.0 * math.pi * j / 16.0 for j in range(16))
            ])
        append_bm(bm, make_closed_loft(torp_rings))

        skeg_rings = []
        for k in range(5):
            u = k / 4.0
            z = lerp(0.000, pod_z + 0.02, u)
            y_aft = lerp(-5.90, -5.98, u)
            y_fwd = lerp(-5.58, -5.32, u)
            w_h = lerp(0.018, 0.042, u)
            skeg_rings.append([
                Vector((px - w_h, y_aft, z)),
                Vector((px + w_h, y_aft, z)),
                Vector((px + w_h, y_fwd, z)),
                Vector((px - w_h, y_fwd, z)),
            ])
        append_bm(bm, make_closed_loft(skeg_rings))

    objs.append(finalize_bmesh("Propulsion_TwinIPS", bm, col, M["C7_PodGrey"], part="Propulsion", sharp_angle=35.0))

    for side, tag in ((-1.0, "Port"), (1.0, "Stbd")):
        objs.append(
            import_cad_glb(
                "pod_propeller.glb",
                f"CAD_IPS_Prop_{tag}",
                col,
                M["C7_PropBronze"],
                part="Props",
                location=(side * 1.10, -4.64, pod_z),
                rot_deg=(0.0, 0.0, 180.0),
                scale=1.0,
            )
        )

    return objs


# ---------------------------------------------------------------------------
# 12. Articulated CAD Steering Wheels (`Steering`) & Twin-Lever Throttles (`Throttle`)
# ---------------------------------------------------------------------------
def build_helm_controls(col: bpy.types.Collection, M: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    objs: list[bpy.types.Object] = []

    # Lower helm console top is at `Z = 2.730`; throttle binnacle embedded cleanly 12 mm into console (`2.718` -> 0 ZF!)
    objs.append(
        import_cad_glb(
            "steering_wheel.glb",
            "CAD_Steering_Lower",
            col,
            M["C7_Stainless"],
            part="Steering",
            location=(0.44, 1.72, Z_SALON_SOLE + 0.80),
            rot_deg=(24.0, 0.0, 0.0),
            scale=1.0,
        )
    )
    objs.append(
        import_cad_glb(
            "throttle_binnacle.glb",
            "CAD_Throttle_Lower",
            col,
            M["C7_Stainless"],
            part="Throttle",
            location=(0.86, 1.84, Z_SALON_SOLE + 0.838),
            rot_deg=(0.0, 0.0, 0.0),
            scale=1.0,
        )
    )

    # Flybridge helm console top is at `Z = Z_FB_FLOOR + 0.665`; wheel shifted aft 30 mm so collar clears dash bevel (0 B2B!)
    objs.append(
        import_cad_glb(
            "steering_wheel.glb",
            "CAD_Steering_Flybridge",
            col,
            M["C7_Stainless"],
            part="Steering",
            location=(-0.18, 0.03, Z_FB_FLOOR + 0.56),
            rot_deg=(24.0, 0.0, 0.0),
            scale=1.0,
        )
    )
    objs.append(
        import_cad_glb(
            "throttle_binnacle.glb",
            "CAD_Throttle_Flybridge",
            col,
            M["C7_Stainless"],
            part="Throttle",
            location=(0.24, 0.18, Z_FB_FLOOR + 0.648),
            rot_deg=(0.0, 0.0, 0.0),
            scale=1.0,
        )
    )

    return objs


# ---------------------------------------------------------------------------
# 13. Roblox Functional Sockets & Seats
# ---------------------------------------------------------------------------
def build_sockets_and_seats(col: bpy.types.Collection) -> None:
    core.seat("HelmLower", col, (0.38, 1.25, Z_SALON_SOLE + 0.65), yaw_deg=0.0, driver=True)
    core.seat("CompanionLower", col, (1.00, 1.25, Z_SALON_SOLE + 0.65), yaw_deg=0.0, driver=False)
    core.seat("HelmFlybridge", col, (-0.34, -0.40, Z_FB_FLOOR + 0.56), yaw_deg=0.0, driver=False)
    core.seat("FlybridgeLounge", col, (0.92, -2.75, Z_FB_FLOOR + 0.45), yaw_deg=90.0, driver=False)
    core.seat("BowLounge", col, (0.0, 4.38, 2.86), yaw_deg=0.0, driver=False)

    core.socket("BoatCenter", col, (0.0, -0.30, Z_WATERLINE))
    core.socket("HingeSteering", col, (0.44, 1.72, Z_SALON_SOLE + 0.80), parent_part="Hull")
    core.socket("HingeThrottle", col, (0.86, 1.84, Z_SALON_SOLE + 0.838), parent_part="Hull")
    core.socket("HingeProps", col, (0.0, -4.64, 0.28), parent_part="Propulsion")
    core.socket("WakePort", col, (-1.95, Y_PLAT_AFT, Z_WATERLINE), parent_part="Hull")
    core.socket("WakeStbd", col, (1.95, Y_PLAT_AFT, Z_WATERLINE), parent_part="Hull")
    core.socket("BowMooring", col, (0.0, Y_BOW - 0.15, Z_SHEER_BOW), parent_part="Hull")


# ---------------------------------------------------------------------------
# 14. Hard Gate 3: BVH Shell-Integrity & Connectivity Verification
# ---------------------------------------------------------------------------
def verify_yacht_integrity(meshes: list[bpy.types.Object]) -> None:
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    breaches: list[str] = []
    for ob in meshes:
        if ob.get("sc_part") != "InteriorSalon":
            continue
        bm = bmesh.new()
        bm.from_object(ob, dg)
        bm.transform(ob.matrix_world)
        for v in bm.verts:
            if v.co.z < Z_SHEER_BOW:
                x_lim = outer_x_at_yz(v.co.y, v.co.z) - 0.15
                if abs(v.co.x) > x_lim:
                    breaches.append(f"{ob.name} vert {tuple(round(c, 3) for c in v.co)} exceeds hull inner x={x_lim:.3f}")
                    break
        bm.free()

    bvhs: list[tuple[str, BVHTree]] = []
    for ob in meshes:
        bm = bmesh.new()
        bm.from_object(ob, dg)
        bm.transform(ob.matrix_world)
        bvhs.append((ob.name, BVHTree.FromBMesh(bm)))
        bm.free()

    n = len(bvhs)
    visited = {0}
    queue = [0]
    while queue:
        cur = queue.pop(0)
        for nxt in range(n):
            if nxt not in visited and bvhs[cur][1].overlap(bvhs[nxt][1]):
                visited.add(nxt)
                queue.append(nxt)

    floating = [bvhs[i][0] for i in range(n) if i not in visited]
    if breaches or floating:
        msg = []
        if breaches:
            msg.append("Shell breaches: " + "; ".join(breaches))
        if floating:
            msg.append("Floating unconnected meshes: " + ", ".join(floating))
        raise RuntimeError("Gate 3 BVH Integrity FAILED -> " + " | ".join(msg))
    core.log(f"[Gate 3 OK] 0 shell breaches, {len(visited)}/{n} meshes form a single BVH-connected assembly!")


# ---------------------------------------------------------------------------
# Master Assembly Entry Point
# ---------------------------------------------------------------------------
def build_all(
    collection_name: str = COLL_NAME,
    clear_scene: bool = True,
    mat_override: dict[str, bpy.types.Material] | None = None,
) -> tuple[bpy.types.Collection, list[bpy.types.Object]]:
    if clear_scene:
        clear_scene_and_setup_units()
    col = core.fresh_collection(collection_name)

    M = build_materials()
    if mat_override:
        M.update(mat_override)

    meshes: list[bpy.types.Object] = []
    meshes.extend(build_hull(col, M))
    meshes.extend(build_hull_accents(col, M))
    meshes.extend(build_deck_and_cockpit(col, M))
    meshes.extend(build_superstructure(col, M))
    meshes.extend(build_interior_salon(col, M))
    meshes.extend(build_flybridge_interior(col, M))
    meshes.extend(build_glass(col, M))
    meshes.extend(build_rails_and_hardware(col, M))
    meshes.extend(build_electronics(col, M))
    meshes.extend(build_lights(col, M))
    meshes.extend(build_propulsion(col, M))
    meshes.extend(build_helm_controls(col, M))
    build_sockets_and_seats(col)

    lo, hi = core.world_bbox(meshes)
    if abs(lo.z) > 1e-6:
        shift = Matrix.Translation((0.0, 0.0, -lo.z))
        for ob in meshes:
            ob.data.transform(shift)
            ob.data.update()
        for ob in col.objects:
            if ob.type == "EMPTY":
                ob.location.z -= lo.z
        bpy.context.view_layer.update()

    verify_yacht_integrity(meshes)
    refs.load_reference_planes(THIS_DIR)

    part_budget = gameready.budget(meshes, evaluated=False)
    for pname, tcnt in part_budget.items():
        if tcnt > gameready.ROBLOX_MAX_TRIS_PER_MESH:
            raise RuntimeError(f"sc_part '{pname}' has {tcnt} tris > Roblox 20,000 limit!")
    core.log(
        f"Cruiser Boat 7C built: {sum(part_budget.values()):,} tris across {len(part_budget)} parts | "
        f"size={(hi - lo).x:.2f} x {(hi - lo).y:.2f} x {(hi - lo).z:.2f} m"
    )
    gameready.validate(meshes, verbose=False)
    return col, meshes


def main() -> int:
    _col, meshes = build_all()
    blend_path = os.path.join(THIS_DIR, "cruiser_boat_7c.blend")
    glb_path = os.path.join(THIS_DIR, "cruiser_boat_7c.glb")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.export_scene.gltf(filepath=glb_path, use_selection=True, export_format="GLB", export_apply=True)
    for o in meshes:
        o.select_set(False)
    return 0


if __name__ == "__main__":
    main()
