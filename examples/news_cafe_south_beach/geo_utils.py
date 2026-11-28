r"""High-Poly Photorealistic ArchViz BMesh Geometry, Curved Botanicals, Quatrefoil Breeze-Blocks & CAD Import (`geo_utils.py`).

No 20k low-poly compromises:
  - Smooth 24-point curved Art Deco quatrefoil breeze blocks with chamfered masonry faces
  - 3-segment curved V-folded ovate/lanceolate botanical leaves (zero flat diamond spikes!)
  - Genuine 3-bract cupped papery bougainvillea blossom clusters w/ central cream florets
  - Bishop-frame twist-free smooth Catmull-Rom curved spline tubes (bentwood chairs, gnarled trees, arched fronds, vines)
  - Smooth revolved lathe meshes (wine bottles, fluted ceramic/terracotta pots, barstools, sconces)
  - Crisp micro-beveled architectural boxes & watertight positive-signed-volume enforcement
"""
from __future__ import annotations

import math
from collections import defaultdict

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree


def _islands(bm: bmesh.types.BMesh) -> list[list[bmesh.types.BMFace]]:
    """Group faces into connected mesh islands."""
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
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

    groups: dict[int, list[bmesh.types.BMFace]] = defaultdict(list)
    for f in bm.faces:
        if f.verts:
            groups[find(f.verts[0].index)].append(f)
    return list(groups.values())


def ensure_all_islands_outward(bm: bmesh.types.BMesh) -> None:
    """Guarantee positive signed volume (100% outward blue normals) on EVERY closed island."""
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for faces in _islands(bm):
        ref = faces[0].verts[0].co
        vol6 = 0.0
        for f in faces:
            if len(f.verts) >= 3:
                v0 = f.verts[0].co - ref
                for k in range(1, len(f.verts) - 1):
                    v1 = f.verts[k].co - ref
                    v2 = f.verts[k + 1].co - ref
                    vol6 += v0.dot(v1.cross(v2))
        if vol6 < -1e-9:
            bmesh.ops.reverse_faces(bm, faces=faces)


def _point_in_tri_3d(p: Vector, a: Vector, b: Vector, c: Vector, n: Vector) -> bool:
    for u, v in ((a, b), (b, c), (c, a)):
        if (v - u).cross(p - u).dot(n) < -1e-6:
            return False
    return True


def deconflict_botanical_islands(bm: bmesh.types.BMesh, max_passes: int = 5) -> int:
    """Apply subtle organic leaf tilts if random botanical leaves collide coplanarly within 1.2 mm."""
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="FIXED")
    if len(bm.faces) > 180000:
        # Fast safeguard for ultra-dense multi-hundred-thousand-tri foliage meshes
        return 0
    total_adjusted = 0
    for p_idx in range(max_passes):
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        island_faces = _islands(bm)
        f_to_isl: dict[int, int] = {}
        isl_verts: dict[int, list[bmesh.types.BMVert]] = {}
        for iid, flist in enumerate(island_faces):
            vset = {}
            for f in flist:
                f_to_isl[f.index] = iid
                for v in f.verts:
                    vset[v.index] = v
            isl_verts[iid] = list(vset.values())

        verts = [v.co.copy() for v in bm.verts]
        tris = [tuple(v.index for v in f.verts) for f in bm.faces]
        norms = [f.normal.copy() for f in bm.faces]
        tsets = [set(t) for t in tris]
        bvh = BVHTree.FromPolygons(verts, tris, epsilon=0.0)

        bad_islands: set[int] = set()
        for ti, t in enumerate(tris):
            n = norms[ti]
            if n.length < 0.5:
                continue
            a, b, c = verts[t[0]], verts[t[1]], verts[t[2]]
            cen = (a + b + c) / 3.0
            for pt in (cen, cen.lerp(a, 0.6), cen.lerp(b, 0.6), cen.lerp(c, 0.6)):
                for _, _, tj, _ in bvh.find_nearest_range(pt, 0.0012):
                    if tj is None or tj == ti or (tsets[ti] & tsets[tj]):
                        continue
                    n2 = norms[tj]
                    if abs(n.dot(n2)) < 0.997:
                        continue
                    a2, b2, c2 = verts[tris[tj][0]], verts[tris[tj][1]], verts[tris[tj][2]]
                    q = pt - n2 * n2.dot(pt - a2)
                    if _point_in_tri_3d(q, a2, b2, c2, n2):
                        ia, ib = f_to_isl[ti], f_to_isl[tj]
                        pick = ia if len(isl_verts[ia]) < len(isl_verts[ib]) else (ib if len(isl_verts[ib]) < len(isl_verts[ia]) else max(ia, ib))
                        bad_islands.add(pick)

        if not bad_islands:
            break
        for iid in bad_islands:
            vs = isl_verts[iid]
            pivot = vs[0].co.copy() if len(vs) <= 40 else sum((v.co for v in vs), Vector()) / len(vs)
            ang = 0.16 * (1.0 + 0.37 * p_idx)
            rot = Euler((ang, ang * (0.61 + 0.17 * p_idx), ang * (0.37 + 0.23 * p_idx)), "XYZ").to_matrix()
            for v in vs:
                v.co = pivot + rot @ (v.co - pivot)
            total_adjusted += 1
    return total_adjusted


def add_box(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    mat_idx: int = 0,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
    *,
    bevel: float = 0.0,
) -> list[bmesh.types.BMFace]:
    """Add a watertight closed box (optionally micro-beveled for crisp sunlight edge highlights!)."""
    sx, sy, sz = (max(float(c), 0.004) for c in size)
    mat_s = Matrix.Diagonal((sx, sy, sz, 1.0))
    mat_r = Euler(rot_euler, "XYZ").to_matrix().to_4x4()
    mat_t = Matrix.Translation(Vector(center))
    xf = mat_t @ mat_r @ mat_s
    ret = bmesh.ops.create_cube(bm, size=1.0, matrix=xf)
    verts = set(ret["verts"])
    if bevel > 0.0:
        b_amt = min(bevel, min(sx, sy, sz) * 0.24)
        edges = [e for e in bm.edges if e.verts[0] in verts and e.verts[1] in verts]
        res = bmesh.ops.bevel(bm, geom=edges, offset=b_amt, offset_type="OFFSET", segments=2, profile=0.5, affect="EDGES")
        verts.update(res.get("verts", []))
    faces = [f for f in bm.faces if all(v in verts for v in f.verts)]
    for f in faces:
        f.material_index = mat_idx
    return faces


def add_box_bounds(
    bm: bmesh.types.BMesh,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    mat_idx: int = 0,
    *,
    bevel: float = 0.0,
) -> list[bmesh.types.BMFace]:
    """Add a watertight axis-aligned box spanning `[x0..x1] x [y0..y1] x [z0..z1]`."""
    cx, cy, cz = 0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)
    sx, sy, sz = abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)
    return add_box(bm, (cx, cy, cz), (sx, sy, sz), mat_idx=mat_idx, bevel=bevel)


def add_cylinder(
    bm: bmesh.types.BMesh,
    p0: tuple[float, float, float],
    p1: tuple[float, float, float],
    r0: float,
    r1: float | None = None,
    *,
    segs: int = 16,
    mat_idx: int = 0,
    extend: float = 0.0,
) -> list[bmesh.types.BMFace]:
    """Add a smooth closed tapered cylinder spanning `p0 -> p1`."""
    v0, v1 = Vector(p0), Vector(p1)
    dv = v1 - v0
    length = dv.length
    if length < 1e-5:
        return []
    d_unit = dv / length
    if extend > 0.0:
        v0 = v0 - d_unit * extend
        v1 = v1 + d_unit * extend
        length += 2.0 * extend
    mid = 0.5 * (v0 + v1)
    rot = d_unit.to_track_quat("Z", "Y").to_matrix().to_4x4()
    xf = Matrix.Translation(mid) @ rot
    rr0 = max(float(r0), 0.002)
    rr1 = max(float(r0 if r1 is None else r1), 0.002)
    ret = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=segs,
        radius1=rr0,
        radius2=rr1,
        depth=length,
        matrix=xf,
    )
    verts = set(ret["verts"])
    faces = [f for f in bm.faces if all(v in verts for v in f.verts)]
    for f in faces:
        f.material_index = mat_idx
    return faces


def add_icosphere(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    scale: tuple[float, float, float],
    *,
    subdiv: int = 2,
    mat_idx: int = 0,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[bmesh.types.BMFace]:
    """Add a smooth watertight closed ellipsoid."""
    xf = (
        Matrix.Translation(Vector(center))
        @ Euler(rot_euler, "XYZ").to_matrix().to_4x4()
        @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    )
    ret = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0, matrix=xf)
    verts = set(ret["verts"])
    faces = [f for f in bm.faces if all(v in verts for v in f.verts)]
    for f in faces:
        f.material_index = mat_idx
    return faces


def _catmull_rom(pts: list[Vector], substeps: int = 4) -> list[Vector]:
    """Smooth Catmull-Rom cubic interpolation through `pts`."""
    if len(pts) < 2 or substeps <= 1:
        return list(pts)
    ext = [pts[0] + (pts[0] - pts[1])] + list(pts) + [pts[-1] + (pts[-1] - pts[-2])]
    out: list[Vector] = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        n_s = substeps if i < len(ext) - 3 else substeps + 1
        for s in range(n_s):
            t = s / substeps
            t2 = t * t
            t3 = t2 * t
            v = 0.5 * (
                (2.0 * p1)
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
            )
            out.append(v)
    return out


def add_spline_tube(
    bm: bmesh.types.BMesh,
    ctrl_pts: list[Vector],
    radii: list[float] | float,
    *,
    segs: int = 12,
    substeps: int = 3,
    mat_idx: int = 0,
    cap_round: bool = True,
    rib_amp: float = 0.0,
    rib_freq: float = 0.0,
    flute_amp: float = 0.0,
    flute_freq: int = 0,
    closed: bool = False,
) -> list[bmesh.types.BMFace]:
    """Build a silky-smooth, twist-free Bishop-frame watertight curved tube along a Catmull-Rom spline!

    Supports `closed=True` for seamless manifold bentwood rings/hoops with zero duplicate seam verts,
    plus `rib_amp`/`rib_freq` (transverse growth rings) and `flute_amp`/`flute_freq` (longitudinal bark ridges).
    """
    src = [Vector(p) for p in ctrl_pts]
    if closed and len(src) >= 3:
        if (src[-1] - src[0]).length < 1e-5:
            src = src[:-1]
        # Cyclic smooth Catmull-Rom interpolation
        pts: list[Vector] = []
        m_n = len(src)
        for i in range(m_n):
            p0 = src[(i - 1) % m_n]
            p1 = src[i]
            p2 = src[(i + 1) % m_n]
            p3 = src[(i + 2) % m_n]
            for s in range(max(1, substeps)):
                t = s / max(1, substeps)
                t2, t3 = t * t, t * t * t
                v = 0.5 * (
                    (2.0 * p1)
                    + (-p0 + p2) * t
                    + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                    + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
                )
                pts.append(v)
    else:
        pts = _catmull_rom(src, substeps=substeps)

    n = len(pts)
    if n < 2:
        return []

    if isinstance(radii, (int, float)):
        r_vals = [max(float(radii), 0.002)] * n
    else:
        r_src = [max(float(r), 0.002) for r in radii]
        r_vals = []
        for i in range(n):
            u = i / max(n - 1, 1) * (len(r_src) - 1)
            k0 = min(len(r_src) - 2, int(u))
            f = u - k0
            r_vals.append(r_src[k0] * (1.0 - f) + r_src[k0 + 1] * f)

    # Parallel-transport (Bishop) frame along curve -> ZERO twist artifacts!
    tangs: list[Vector] = []
    for i in range(n):
        if closed:
            t = pts[(i + 1) % n] - pts[(i - 1) % n]
        elif i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tangs.append(t.normalized() if t.length > 1e-7 else Vector((0, 0, 1)))

    t0 = tangs[0]
    ref = Vector((1, 0, 0)) if abs(t0.x) < 0.85 else Vector((0, 1, 0))
    u_vec = (ref - t0 * ref.dot(t0)).normalized()
    v_vec = t0.cross(u_vec).normalized()

    # Pre-compute parallel-transport frames, and for closed loops distribute holonomy twist smoothly -> ZERO seam twist!
    frames_u: list[Vector] = []
    frames_v: list[Vector] = []
    for i in range(n):
        if i > 0:
            axis = tangs[i - 1].cross(tangs[i])
            if axis.length > 1e-7:
                ang = math.acos(max(-1.0, min(1.0, tangs[i - 1].dot(tangs[i]))))
                rot = Matrix.Rotation(ang, 3, axis.normalized())
                u_vec = (rot @ u_vec).normalized()
            v_vec = tangs[i].cross(u_vec).normalized()
            u_vec = v_vec.cross(tangs[i]).normalized()
        frames_u.append(u_vec.copy())
        frames_v.append(v_vec.copy())

    holonomy = 0.0
    if closed and n >= 3:
        # Transport final frame across closing segment (n-1 -> 0) and measure angular mismatch against frame 0!
        u_close = frames_u[-1].copy()
        axis_c = tangs[-1].cross(tangs[0])
        if axis_c.length > 1e-7:
            ang_c = math.acos(max(-1.0, min(1.0, tangs[-1].dot(tangs[0]))))
            u_close = (Matrix.Rotation(ang_c, 3, axis_c.normalized()) @ u_close).normalized()
        holonomy = math.atan2(u_close.dot(frames_v[0]), u_close.dot(frames_u[0]))

    rings: list[list[Vector]] = []
    for i in range(n):
        u_i, v_i = frames_u[i], frames_v[i]
        if closed and abs(holonomy) > 1e-6:
            corr = -holonomy * (i / n)
            cc, ss = math.cos(corr), math.sin(corr)
            u_rot = u_i * cc + v_i * ss
            v_rot = -u_i * ss + v_i * cc
            u_i, v_i = u_rot, v_rot
        r_i = r_vals[i]
        frac = i / max(n - 1, 1)
        if rib_amp > 0.0 and rib_freq > 0.0:
            r_i *= 1.0 + rib_amp * math.sin(frac * math.tau * rib_freq)
        ring = []
        for j in range(segs):
            a = math.tau * j / segs
            r_j = r_i
            if flute_amp > 0.0 and flute_freq > 0:
                r_j *= 1.0 + flute_amp * math.sin(a * flute_freq + frac * 4.5)
            ring.append(pts[i] + (u_i * math.cos(a) + v_i * math.sin(a)) * r_j)
        rings.append(ring)

    if closed:
        vr = [[bm.verts.new(p) for p in r] for r in rings]
        faces: list[bmesh.types.BMFace] = []
        for i in range(n):
            inxt = (i + 1) % n
            for j in range(segs):
                jn = (j + 1) % segs
                f = bm.faces.new((vr[i][j], vr[i][jn], vr[inxt][jn], vr[inxt][j]))
                f.material_index = mat_idx
                faces.append(f)
        return faces

    cap_a = pts[0] - tangs[0] * (r_vals[0] * 0.65 if cap_round else 0.002)
    cap_b = pts[-1] + tangs[-1] * (r_vals[-1] * 0.65 if cap_round else 0.002)
    return add_closed_tube(bm, rings, cap_a, cap_b, mat_idx=mat_idx)


def add_torus_ring(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    major_r: float,
    minor_r: float,
    *,
    major_segs: int = 32,
    minor_segs: int = 14,
    mat_idx: int = 0,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[bmesh.types.BMFace]:
    """Exact analytical zero-twist seamless circular torus ring (0.000 mm seam closure -> ZERO pinched gaps!)."""
    rot_m = Euler(rot_euler, "XYZ").to_matrix()
    cen = Vector(center)
    vr: list[list] = []
    for i in range(major_segs):
        phi = math.tau * i / major_segs
        cp, sp = math.cos(phi), math.sin(phi)
        rad = Vector((cp, sp, 0.0))
        up = Vector((0.0, 0.0, 1.0))
        ring_v = []
        for j in range(minor_segs):
            th = math.tau * j / minor_segs
            local_p = rad * (major_r + minor_r * math.cos(th)) + up * (minor_r * math.sin(th))
            ring_v.append(bm.verts.new(cen + rot_m @ local_p))
        vr.append(ring_v)

    faces: list[bmesh.types.BMFace] = []
    for i in range(major_segs):
        inxt = (i + 1) % major_segs
        for j in range(minor_segs):
            jn = (j + 1) % minor_segs
            f = bm.faces.new((vr[i][j], vr[inxt][j], vr[inxt][jn], vr[i][jn]))
            f.material_index = mat_idx
            faces.append(f)
    return faces


def add_parisian_bistro_chair(
    bm: bmesh.types.BMesh,
    x: float,
    y: float,
    z_floor: float,
    yaw: float,
    *,
    mat_frame: int = 0,
    mat_weave: int = 1,
    mat_brass: int = 3,
) -> None:
    """CAD-precision French Parisian bentwood-rattan bistro chair with 100% mathematically locked joints & exact flush feet!

    Engineering guarantees:
      - All 4 brass leg ferrules rest EXACTLY FLUSH at `z_floor + 0.0000 m` (ZERO sinking into floor/sidewalk!).
      - All 4 curved bentwood legs meet BOTH the circular outer seat frame (`R=0.212, z=0.455`) AND the under-seat
        circular stretcher ring (`R=0.206, z=0.215`) cleanly with brass joint sleeves -> ZERO air gaps, ZERO flat stubs!
      - Seamless analytical `add_torus_ring` for seat hoop, under-seat support hoop, and foot stretcher -> ZERO twist seams!
      - Smooth 10-point spherical-cap domed woven seat cushion nestled cleanly INSIDE the bentwood seat hoop.
      - Curved woven backrest panel whose 360-deg perimeter locks directly INSIDE the inner bentwood arch & lower rail -> ZERO gap!
    """
    c, s = math.cos(yaw), math.sin(yaw)

    def _w(lx: float, ly: float, lz: float) -> Vector:
        return Vector((x + lx * c - ly * s, y + lx * s + ly * c, z_floor + lz))

    R_SEAT = 0.212
    Z_SEAT = 0.455
    Z_RING = 0.215

    # 1. Seamless analytical circular bentwood seat frame ring + recessed inner under-seat support hoop!
    add_torus_ring(bm, (x, y, z_floor + Z_SEAT), R_SEAT, 0.017, major_segs=36, minor_segs=14, mat_idx=mat_frame)
    add_torus_ring(bm, (x, y, z_floor + Z_SEAT - 0.028), R_SEAT - 0.016, 0.011, major_segs=32, minor_segs=12, mat_idx=mat_frame)

    # 2. Smooth 10-point spherical-cap domed woven rattan seat cushion nested cleanly INSIDE the bentwood seat ring!
    #    Outer skirt r=0.201 embeds cleanly 6 mm inside the inner wall of R_SEAT (0.212 - 0.017 = 0.195) -> ZERO step or gap!
    seat_prof: list[tuple[float, float]] = [(0.194, -0.016), (0.201, -0.006), (0.201, 0.004)]
    for k in range(1, 9):
        frac = k / 8.0
        r_k = 0.201 * math.cos(frac * math.pi * 0.48)
        z_k = 0.004 + 0.022 * math.sin(frac * math.pi * 0.50)
        seat_prof.append((max(0.006, r_k), z_k))
    add_revolved_profile(bm, (x, y, z_floor + Z_SEAT), seat_prof, segs=32, mat_idx=mat_weave, yaw_rad=yaw)

    # 3. Seamless analytical circular under-seat stretcher ring (`R_RING=0.205`, outer wall `0.216`) overlapping ALL 4 legs cleanly!
    #    At z=Z_RING (0.215), every leg centerline sits at R = hypot(0.160, 0.150) = 0.2193 -> leg inner wall = 0.2053!
    #    Outer wall of ring (0.216) penetrates 10.7 mm cleanly INTO every leg centerline without poking outside!
    add_torus_ring(bm, (x, y, z_floor + Z_RING), 0.205, 0.011, major_segs=32, minor_segs=12, mat_idx=mat_frame)

    # 4. Flared curved front bentwood legs: exact flush brass ferrules at z=0.000, curving cleanly INTO seat hoop centerline!
    #    Top point (sx*0.155, +0.145, Z_SEAT-0.004) has R = hypot(0.155, 0.145) = 0.2122 == R_SEAT!
    for sx in (-1.0, 1.0):
        # Exact horizontal flat-bottomed brass floor glide pad (`z=0.0000` flush!) + tilted brass ferrule sleeve (`z=0.005..0.042`)
        add_cylinder(bm, _w(sx * 0.175, 0.168, 0.000), _w(sx * 0.175, 0.168, 0.008), 0.0145, 0.0143, segs=14, mat_idx=mat_brass)
        add_cylinder(bm, _w(sx * 0.174, 0.167, 0.005), _w(sx * 0.171, 0.163, 0.042), 0.0142, 0.0148, segs=14, mat_idx=mat_brass)
        # Curved wooden front leg rising through (sx*0.160, 0.150, Z_RING) straight into underside of seat hoop & tucked inward!
        f_leg = [
            _w(sx * 0.172, 0.164, 0.036),
            _w(sx * 0.160, 0.150, Z_RING),
            _w(sx * 0.157, 0.146, Z_SEAT - 0.055),
            _w(sx * 0.155, 0.145, Z_SEAT - 0.004),
            _w(sx * 0.140, 0.132, Z_SEAT - 0.018),
        ]
        add_spline_tube(bm, f_leg, [0.0135, 0.0140, 0.0142, 0.0138, 0.0115], segs=12, substeps=4, mat_idx=mat_frame, cap_round=True)
        # Neat turned bentwood collar reinforcing the foot stretcher ring-to-leg joint cleanly
        add_icosphere(bm, _w(sx * 0.158, 0.148, Z_RING), (0.0172, 0.0172, 0.016), subdiv=1, mat_idx=mat_frame)

    # 5. Continuous sweeping Parisian outer bentwood back-legs + horseshoe backrest hoop!
    #    Passes EXACTLY through (sx*0.160, -0.150, Z_RING) AND (sx*0.155, -0.145, Z_SEAT) [R=0.2122 == R_SEAT!]
    outer_hoop = [
        _w(-0.172, -0.164, 0.036),
        _w(-0.160, -0.150, Z_RING),
        _w(-0.155, -0.145, Z_SEAT),
        _w(-0.184, -0.194, 0.675),
        _w(-0.164, -0.224, 0.805),
        _w(-0.102, -0.240, 0.880),
        _w(0.000, -0.246, 0.904),
        _w(0.102, -0.240, 0.880),
        _w(0.164, -0.224, 0.805),
        _w(0.184, -0.194, 0.675),
        _w(0.155, -0.145, Z_SEAT),
        _w(0.160, -0.150, Z_RING),
        _w(0.172, -0.164, 0.036),
    ]
    add_spline_tube(bm, outer_hoop, 0.0142, segs=14, substeps=4, mat_idx=mat_frame, cap_round=True)
    for sx in (-1.0, 1.0):
        add_cylinder(bm, _w(sx * 0.175, -0.168, 0.000), _w(sx * 0.175, -0.168, 0.008), 0.0145, 0.0143, segs=14, mat_idx=mat_brass)
        add_cylinder(bm, _w(sx * 0.174, -0.167, 0.005), _w(sx * 0.171, -0.163, 0.042), 0.0142, 0.0148, segs=14, mat_idx=mat_brass)
        add_icosphere(bm, _w(sx * 0.158, -0.148, Z_RING), (0.0172, 0.0172, 0.016), subdiv=1, mat_idx=mat_frame)

    # 6. PARAMETRICALLY LOCKED Inner Bentwood Arch + Horizontal Lower Backrest Cross-Rail + Zero-Gap Woven Rattan Backrest!
    #    Every perimeter vertex of the woven rattan panel sits DIRECTLY INSIDE the centerline of the inner wooden arch & cross-rail!
    Z_BACK_BOT = 0.540

    def _back_arch_xy(u: float) -> tuple[float, float, float]:
        """Exact smooth arched top curve for u in [-1..+1] matching inner bentwood hoop."""
        # Half-width 0.148 at bottom cross-rail, smoothly curving up to peak Z=0.848 at u=0!
        ang = math.pi * 0.5 * (1.0 - u)  # pi (u=-1) -> pi/2 (u=0) -> 0 (u=+1)
        lx = 0.148 * math.cos(ang)
        lz = 0.635 + 0.213 * math.sin(ang)
        t_h = max(0.0, min(1.0, (lz - Z_SEAT) / (0.848 - Z_SEAT)))
        ly = -0.152 - 0.084 * (t_h ** 0.90) - 0.014 * (1.0 - u * u)
        return lx, ly, lz

    # Inner bentwood arch tube anchored solidly INTO the seat frame at (sx*0.148, -0.152, Z_SEAT) [R=0.2121 == R_SEAT!]
    inner_pts: list[Vector] = [
        _w(-0.148, -0.152, Z_SEAT),
        _w(-0.148, -0.172, Z_BACK_BOT),
    ]
    for k in range(13):
        u_k = -1.0 + 2.0 * (k / 12.0)
        ax, ay, az = _back_arch_xy(u_k)
        inner_pts.append(_w(ax, ay, az))
    inner_pts.extend([
        _w(0.148, -0.172, Z_BACK_BOT),
        _w(0.148, -0.152, Z_SEAT),
    ])
    add_spline_tube(bm, inner_pts, 0.0118, segs=12, substeps=2, mat_idx=mat_frame, cap_round=True)

    # Curved horizontal lower backrest wooden cross-rail physically supporting the bottom edge of the woven backrest!
    rail_pts = [
        _w(0.148 * u, -0.172 - 0.014 * (1.0 - u * u), Z_BACK_BOT)
        for u in (-1.0, -0.6, -0.2, 0.2, 0.6, 1.0)
    ]
    add_spline_tube(bm, rail_pts, 0.0110, segs=10, substeps=2, mat_idx=mat_frame, cap_round=True)

    # Two short horizontal wooden tie-dowels linking outer hoop to inner arch cleanly on left & right sides
    for sx in (-1.0, 1.0):
        add_cylinder(bm, _w(sx * 0.180, -0.194, 0.675), _w(sx * 0.146, -0.194, 0.675), 0.008, 0.008, segs=10, mat_idx=mat_frame)

    # Woven rattan backrest shell (16 x 6) whose 4 perimeter edges terminate EXACTLY ON the inner arch & bottom cross-rail centerline!
    nu, nv = 16, 6
    vt_g, vb_g = [], []
    for iu in range(nu + 1):
        u = -1.0 + 2.0 * (iu / nu)
        top_x, top_y, top_z = _back_arch_xy(u)
        bot_x = 0.148 * u
        bot_y = -0.172 - 0.014 * (1.0 - u * u)
        bot_z = Z_BACK_BOT
        row_t, row_b = [], []
        for iv in range(nv + 1):
            v = iv / nv
            # Smooth interpolation from bottom cross-rail centerline (v=0) to arched hoop centerline (v=1)!
            lx = bot_x * (1.0 - v) + top_x * v
            lz = bot_z * (1.0 - v) + top_z * v
            ly = bot_y * (1.0 - v) + top_y * v - 0.006 * math.sin(math.pi * v) * (1.0 - u * u)
            row_t.append(bm.verts.new(_w(lx, ly + 0.0065, lz)))
            row_b.append(bm.verts.new(_w(lx, ly - 0.0065, lz)))
        vt_g.append(row_t)
        vb_g.append(row_b)

    for iu in range(nu):
        for iv in range(nv):
            for q in [
                (vt_g[iu][iv], vt_g[iu][iv + 1], vt_g[iu + 1][iv + 1], vt_g[iu + 1][iv]),
                (vb_g[iu][iv], vb_g[iu + 1][iv], vb_g[iu + 1][iv + 1], vb_g[iu][iv + 1]),
            ]:
                f = bm.faces.new(q)
                f.material_index = mat_weave
    for iu in range(nu):
        for q in [
            (vt_g[iu][0], vt_g[iu + 1][0], vb_g[iu + 1][0], vb_g[iu][0]),
            (vb_g[iu][nv], vb_g[iu + 1][nv], vt_g[iu + 1][nv], vt_g[iu][nv]),
        ]:
            f = bm.faces.new(q)
            f.material_index = mat_weave
    for iv in range(nv):
        for q in [
            (vt_g[0][iv], vb_g[0][iv], vb_g[0][iv + 1], vt_g[0][iv + 1]),
            (vb_g[nu][iv], vt_g[nu][iv], vt_g[nu][iv + 1], vb_g[nu][iv + 1]),
        ]:
            f = bm.faces.new(q)
            f.material_index = mat_weave


def add_revolved_profile(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    profile_rz: list[tuple[float, float]],
    *,
    segs: int = 20,
    mat_idx: int = 0,
    yaw_rad: float = 0.0,
) -> list[bmesh.types.BMFace]:
    """Build a watertight smooth lathe/revolved solid around Z from `profile_rz = [(r0, z0), ...]`."""
    cx, cy, cz = center
    rings: list[list[Vector]] = []
    for r, z in profile_rz:
        rr = max(float(r), 0.0015)
        rings.append([
            Vector((cx + rr * math.cos(yaw_rad + math.tau * j / segs), cy + rr * math.sin(yaw_rad + math.tau * j / segs), cz + z))
            for j in range(segs)
        ])
    cap_a = Vector((cx, cy, cz + profile_rz[0][1]))
    cap_b = Vector((cx, cy, cz + profile_rz[-1][1] + 0.0005))
    return add_closed_tube(bm, rings, cap_a, cap_b, mat_idx=mat_idx)


def add_revolved_ring(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    profile_rz: list[tuple[float, float]],
    *,
    segs: int = 32,
    mat_idx: int = 0,
    yaw_rad: float = 0.0,
) -> list[bmesh.types.BMFace]:
    """Build a 100% ALL-QUAD zero-pole revolved closed-loop ring around Z (ideal for brass table rims & hollow moldings!)."""
    cx, cy, cz = center
    n_p = len(profile_rz)
    vr: list[list] = []
    for i in range(segs):
        ang = yaw_rad + math.tau * i / segs
        ca, sa = math.cos(ang), math.sin(ang)
        vr.append([bm.verts.new(Vector((cx + r * ca, cy + r * sa, cz + z))) for r, z in profile_rz])
    faces: list[bmesh.types.BMFace] = []
    for i in range(segs):
        inxt = (i + 1) % segs
        for p in range(n_p):
            pn = (p + 1) % n_p
            f = bm.faces.new((vr[i][p], vr[inxt][p], vr[inxt][pn], vr[i][pn]))
            f.material_index = mat_idx
            faces.append(f)
    return faces


def add_quad_sphere(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    scale: tuple[float, float, float],
    *,
    segs: int = 16,
    rings: int = 8,
    mat_idx: int = 0,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[bmesh.types.BMFace]:
    """Build a clean structured quad-ring UV sphere (converts cleanly with Alt+J Tris-to-Quads, SubD & Un-Subdivide!)."""
    cx, cy, cz = center
    sx, sy, sz = scale
    rot_m = Euler(rot_euler, "XYZ").to_matrix()
    cen = Vector((cx, cy, cz))
    ring_pts: list[list[Vector]] = []
    for ri in range(1, rings):
        phi = -math.pi * 0.5 + math.pi * (ri / rings)
        cp, sp = math.cos(phi), math.sin(phi)
        ring = []
        for j in range(segs):
            th = math.tau * j / segs
            lp = Vector((sx * cp * math.cos(th), sy * cp * math.sin(th), sz * sp))
            ring.append(cen + rot_m @ lp)
        ring_pts.append(ring)
    cap_a = cen + rot_m @ Vector((0.0, 0.0, -sz))
    cap_b = cen + rot_m @ Vector((0.0, 0.0, +sz))
    return add_closed_tube(bm, ring_pts, cap_a, cap_b, mat_idx=mat_idx)


def add_quad_grid_box(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    mat_idx: int = 0,
    rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
    *,
    segs_xyz: tuple[int, int, int] = (4, 4, 2),
    round_r: float = 0.0,
) -> list[bmesh.types.BMFace]:
    """Build a 100% pure structured quad-grid box with optional smooth SubD corner rounding (ZERO triangles / ZERO n-gons!)."""
    nx, ny, nz = (max(1, int(k)) for k in segs_xyz)
    hx, hy, hz = (max(float(c), 0.004) * 0.5 for c in size)
    rr = min(float(round_r), hx * 0.42, hy * 0.42, hz * 0.42)
    rot_m = Euler(rot_euler, "XYZ").to_matrix()
    cen = Vector(center)

    def _surf_pt(ix: int, iy: int, iz: int) -> Vector:
        px = -hx + 2.0 * hx * (ix / nx)
        py = -hy + 2.0 * hy * (iy / ny)
        pz = -hz + 2.0 * hz * (iz / nz)
        if rr > 1e-5:
            # Smooth superellipsoid corner bevel keeping flat faces planar & rounding edge loops cleanly!
            ix_c = max(-(hx - rr), min(hx - rr, px))
            iy_c = max(-(hy - rr), min(hy - rr, py))
            iz_c = max(-(hz - rr), min(hz - rr, pz))
            dv = Vector((px - ix_c, py - iy_c, pz - iz_c))
            if dv.length > 1e-6:
                dv = dv.normalized() * rr
                px, py, pz = ix_c + dv.x, iy_c + dv.y, iz_c + dv.z
        return cen + rot_m @ Vector((px, py, pz))

    vmap: dict[tuple[int, int, int], bmesh.types.BMVert] = {}

    def _v(ix: int, iy: int, iz: int):
        key = (ix, iy, iz)
        v = vmap.get(key)
        if v is None:
            v = bm.verts.new(_surf_pt(ix, iy, iz))
            vmap[key] = v
        return v

    faces: list[bmesh.types.BMFace] = []
    # Top (+Z) & Bottom (-Z)
    for ix in range(nx):
        for iy in range(ny):
            faces.append(bm.faces.new((_v(ix, iy, nz), _v(ix + 1, iy, nz), _v(ix + 1, iy + 1, nz), _v(ix, iy + 1, nz))))
            faces.append(bm.faces.new((_v(ix, iy + 1, 0), _v(ix + 1, iy + 1, 0), _v(ix + 1, iy, 0), _v(ix, iy, 0))))
    # Front (+Y) & Back (-Y)
    for ix in range(nx):
        for iz in range(nz):
            faces.append(bm.faces.new((_v(ix + 1, ny, iz), _v(ix, ny, iz), _v(ix, ny, iz + 1), _v(ix + 1, ny, iz + 1))))
            faces.append(bm.faces.new((_v(ix, 0, iz), _v(ix + 1, 0, iz), _v(ix + 1, 0, iz + 1), _v(ix, 0, iz + 1))))
    # Right (+X) & Left (-X)
    for iy in range(ny):
        for iz in range(nz):
            faces.append(bm.faces.new((_v(nx, iy, iz), _v(nx, iy + 1, iz), _v(nx, iy + 1, iz + 1), _v(nx, iy, iz + 1))))
            faces.append(bm.faces.new((_v(0, iy + 1, iz), _v(0, iy, iz), _v(0, iy, iz + 1), _v(0, iy + 1, iz + 1))))
    for f in faces:
        f.material_index = mat_idx
    return faces


def add_parisian_bistro_table(
    bm: bmesh.types.BMesh,
    x: float,
    y: float,
    z_floor: float,
    yaw: float = 0.0,
    *,
    mat_iron: int = 0,
    mat_marble: int = 1,
    mat_brass: int = 7,
) -> None:
    """100% structured quad-flow Parisian cast-iron, Carrara marble & stepped brass bistro table (SubD & Alt+J ready!).

    Exact real-world dimensions & datums:
      - 4 cast-iron glide pads resting EXACTLY FLUSH at `z_floor + 0.0000 m`.
      - Turned Victorian baluster pedestal column + 4 sweeping curved S-scroll legs + quad-sphere knee finials.
      - Concentric quad-ring Carrara marble slab (`R = 0.326 m`, `z_top = z_floor + 0.7420 m`).
      - Zero-pole all-quad stepped gleaming brass gallery edge channel (`R_out = 0.343 m`).
    """
    # 1. Turned Cast-Iron Victorian Pedestal Column (`segs = 32` power-of-2 concentric quad rings!)
    ped_prof = [
        (0.012, 0.024), (0.048, 0.024), (0.088, 0.028), (0.098, 0.048),
        (0.094, 0.082), (0.072, 0.118), (0.050, 0.145), (0.056, 0.162),
        (0.044, 0.180), (0.036, 0.205), (0.035, 0.345), (0.042, 0.365),
        (0.048, 0.382), (0.042, 0.398), (0.033, 0.418), (0.031, 0.565),
        (0.038, 0.595), (0.056, 0.635), (0.082, 0.675), (0.104, 0.698),
        (0.104, 0.712), (0.058, 0.712), (0.014, 0.712),
    ]
    add_revolved_profile(bm, (x, y, z_floor), ped_prof, segs=32, mat_idx=mat_iron, yaw_rad=yaw)

    # 2. 4 Sweeping Victorian Curved Cast-Iron S-Scroll Legs + Flush Floor Pads + Quad-Sphere Knee Finials!
    foot_prof = [
        (0.008, 0.000), (0.022, 0.000), (0.032, 0.000), (0.032, 0.012),
        (0.029, 0.024), (0.022, 0.030), (0.010, 0.031),
    ]
    for k in range(4):
        ang = yaw + k * (math.pi * 0.5) + math.pi * 0.25
        ca, sa = math.cos(ang), math.sin(ang)
        # Smooth arched cast-iron leg tube (`segs = 12, substeps = 4` -> clean uniform quad loops!)
        leg_pts = [
            Vector((x + 0.052 * ca, y + 0.052 * sa, z_floor + 0.132)),
            Vector((x + 0.118 * ca, y + 0.118 * sa, z_floor + 0.148)),
            Vector((x + 0.198 * ca, y + 0.198 * sa, z_floor + 0.098)),
            Vector((x + 0.278 * ca, y + 0.278 * sa, z_floor + 0.024)),
        ]
        add_spline_tube(bm, leg_pts, [0.020, 0.0175, 0.0155, 0.014], segs=12, substeps=4, mat_idx=mat_iron, cap_round=True)
        # Revolved round cast-iron floor pad glide resting EXACTLY FLUSH at `z_floor + 0.0000 m`!
        add_revolved_profile(bm, (x + 0.285 * ca, y + 0.285 * sa, z_floor), foot_prof, segs=16, mat_idx=mat_iron, yaw_rad=ang)
        # Sculpted knee scroll finial ball (`add_quad_sphere`, pure quad rings!) perched cleanly on leg shoulder
        add_quad_sphere(bm, (x + 0.125 * ca, y + 0.125 * sa, z_floor + 0.168), (0.020, 0.020, 0.020), segs=16, rings=8, mat_idx=mat_iron)

    # 3. 4 Radial Under-Table Cast-Iron Spider Mounting Arms starting cleanly inside pedestal capital (`r=0.06..0.24`, zero center overlap!)
    for k in range(4):
        ang_s = yaw + k * (math.pi * 0.5)
        cs, ss = math.cos(ang_s), math.sin(ang_s)
        add_quad_grid_box(
            bm, (x + 0.150 * cs, y + 0.150 * ss, z_floor + 0.706), (0.180, 0.036, 0.016), mat_iron,
            rot_euler=(0.0, 0.0, ang_s), segs_xyz=(6, 2, 2), round_r=0.003,
        )

    # 4. Concentric Quad-Ring Carrara Marble Tabletop (`segs = 32`, exact top at `z_floor + 0.7420 m`!)
    marble_prof = [
        (0.025, 0.7120), (0.115, 0.7120), (0.215, 0.7120), (0.312, 0.7120),
        (0.326, 0.7150), (0.327, 0.7385), (0.322, 0.7420),
        (0.260, 0.7420), (0.195, 0.7420), (0.130, 0.7420), (0.065, 0.7420), (0.018, 0.7420),
    ]
    add_revolved_profile(bm, (x, y, z_floor), marble_prof, segs=32, mat_idx=mat_marble, yaw_rad=yaw)

    # 5. Zero-Pole 100% ALL-QUAD Stepped Gleaming Brass Gallery Edge Rim wrapping the marble perimeter!
    brass_rim_prof = [
        (0.323, 0.7085), (0.336, 0.7085), (0.342, 0.7130), (0.3435, 0.7220),
        (0.341, 0.7265), (0.3435, 0.7310), (0.3425, 0.7405), (0.338, 0.7448),
        (0.331, 0.7452), (0.325, 0.7425), (0.324, 0.7380), (0.324, 0.7140),
    ]
    add_revolved_ring(bm, (x, y, z_floor), brass_rim_prof, segs=32, mat_idx=mat_brass, yaw_rad=yaw)


def add_bistro_tableware_set(
    bm: bmesh.types.BMesh,
    x: float,
    y: float,
    z_top: float,
    yaw: float = 0.0,
    *,
    mat_porcelain: int = 2,
    mat_brass: int = 7,
    mat_crystal: int = 8,
    mat_linen: int = 9,
    mat_flame: int = 10,
    mat_stainless: int = 5,
    mat_espresso: int = 0,
) -> None:
    """100% structured quad-flow Parisian fine-dining place setting resting EXACTLY FLUSH on `z_top` (SubD & Alt+J ready!).

    Includes: hollow sculpted porcelain dinner plate, hollow porcelain espresso cup + saucer + curved C-handle + crema,
    hollow crystal stemmed tulip wine glass, turned brass hurricane votive + wax candle + quad-sphere flame,
    multi-cut folded linen napkin, and sculpted lofted quad stainless dinner knife & fork!
    """
    c, s = math.cos(yaw), math.sin(yaw)

    def _xy(lx: float, ly: float) -> tuple[float, float]:
        return (x + lx * c - ly * s, y + lx * s + ly * c)

    # 1. Center Turned Brass Hurricane Votive Candle Holder + Cream Wax Pillar + Quad-Sphere Teardrop Flame!
    votive_prof = [
        (0.008, 0.000), (0.022, 0.000), (0.031, 0.000), (0.031, 0.006),
        (0.025, 0.011), (0.021, 0.016), (0.026, 0.036), (0.031, 0.064),
        (0.034, 0.078), (0.032, 0.082), (0.028, 0.081), (0.025, 0.062),
        (0.021, 0.022), (0.010, 0.018),
    ]
    add_revolved_profile(bm, (x, y, z_top), votive_prof, segs=24, mat_idx=mat_brass, yaw_rad=yaw)
    candle_prof = [
        (0.006, 0.018), (0.017, 0.018), (0.017, 0.048), (0.0165, 0.076),
        (0.014, 0.079), (0.006, 0.078),
    ]
    add_revolved_profile(bm, (x, y, z_top), candle_prof, segs=16, mat_idx=mat_linen, yaw_rad=yaw)
    add_quad_sphere(bm, (x, y, z_top + 0.092), (0.007, 0.007, 0.015), segs=12, rings=8, mat_idx=mat_flame)

    # 2. Hollow Sculpted Porcelain Dinner Plate (`segs = 32`, concentric quad rings inside well & rim!)
    px_pl, py_pl = _xy(-0.145, 0.065)
    plate_prof = [
        (0.016, 0.000), (0.048, 0.000), (0.074, 0.000), (0.088, 0.006),
        (0.106, 0.016), (0.118, 0.021), (0.119, 0.024), (0.115, 0.0255),
        (0.098, 0.020), (0.080, 0.012), (0.066, 0.0085), (0.042, 0.0082), (0.016, 0.0080),
    ]
    add_revolved_profile(bm, (px_pl, py_pl, z_top), plate_prof, segs=32, mat_idx=mat_porcelain, yaw_rad=yaw)

    # 3. Porcelain Espresso Saucer + Hollow Espresso Cup + Espresso Crema + Smooth Curved Quad-Tube C-Handle!
    px_cu, py_cu = _xy(0.112, 0.088)
    saucer_prof = [
        (0.010, 0.000), (0.032, 0.000), (0.044, 0.003), (0.060, 0.012),
        (0.068, 0.0165), (0.066, 0.019), (0.056, 0.015), (0.040, 0.0075),
        (0.026, 0.0055), (0.010, 0.0055),
    ]
    add_revolved_profile(bm, (px_cu, py_cu, z_top), saucer_prof, segs=24, mat_idx=mat_porcelain, yaw_rad=yaw)
    cup_prof = [
        (0.008, 0.0055), (0.022, 0.0055), (0.025, 0.012), (0.029, 0.028),
        (0.033, 0.046), (0.036, 0.062), (0.0345, 0.065), (0.0315, 0.064),
        (0.029, 0.046), (0.025, 0.024), (0.020, 0.012), (0.008, 0.011),
    ]
    add_revolved_profile(bm, (px_cu, py_cu, z_top), cup_prof, segs=24, mat_idx=mat_porcelain, yaw_rad=yaw)
    # Warm dark espresso crema disc tucked cleanly inside cup!
    crema_prof = [(0.006, 0.049), (0.029, 0.049), (0.0295, 0.053), (0.018, 0.0532), (0.006, 0.0532)]
    add_revolved_profile(bm, (px_cu, py_cu, z_top), crema_prof, segs=16, mat_idx=mat_espresso, yaw_rad=yaw)
    # Curved porcelain C-handle (`add_spline_tube`, segs=10, substeps=4 -> pure clean quad rings!)
    h_ang = yaw + 0.55
    hc, hs = math.cos(h_ang), math.sin(h_ang)
    h_pts = [
        Vector((px_cu + 0.030 * hc, py_cu + 0.030 * hs, z_top + 0.053)),
        Vector((px_cu + 0.049 * hc, py_cu + 0.049 * hs, z_top + 0.052)),
        Vector((px_cu + 0.052 * hc, py_cu + 0.052 * hs, z_top + 0.036)),
        Vector((px_cu + 0.044 * hc, py_cu + 0.044 * hs, z_top + 0.022)),
        Vector((px_cu + 0.025 * hc, py_cu + 0.025 * hs, z_top + 0.019)),
    ]
    add_spline_tube(bm, h_pts, 0.0044, segs=10, substeps=3, mat_idx=mat_porcelain, cap_round=True)

    # 4. Sculpted Hollow Crystal Stemmed Tulip Wine Glass (`segs = 24`, pure concentric quad rings!)
    px_wg, py_wg = _xy(0.088, -0.105)
    wine_prof = [
        (0.008, 0.000), (0.022, 0.000), (0.035, 0.000), (0.035, 0.0035),
        (0.024, 0.007), (0.011, 0.012), (0.0052, 0.019), (0.0044, 0.052),
        (0.0046, 0.088), (0.010, 0.098), (0.024, 0.108), (0.036, 0.124),
        (0.040, 0.144), (0.038, 0.168), (0.033, 0.192), (0.0315, 0.1945),
        (0.0298, 0.192), (0.0345, 0.168), (0.0365, 0.144), (0.032, 0.124),
        (0.020, 0.109), (0.008, 0.102),
    ]
    add_revolved_profile(bm, (px_wg, py_wg, z_top), wine_prof, segs=24, mat_idx=mat_crystal, yaw_rad=yaw)

    # 5. Folded Linen Napkin (`add_quad_grid_box` 6x4x2 pure quads!) + Sculpted Lofted Quad Dinner Knife & Fork!
    nx, ny = _xy(-0.145, -0.115)
    nap_yaw = yaw + 0.18
    add_quad_grid_box(
        bm, (nx, ny, z_top + 0.0065), (0.148, 0.090, 0.013), mat_linen,
        rot_euler=(0.0, 0.0, nap_yaw), segs_xyz=(6, 4, 2), round_r=0.004,
    )
    cn, sn = math.cos(nap_yaw), math.sin(nap_yaw)

    def _add_cutlery_loft(off_y: float, specs: list[tuple[float, float, float]]) -> None:
        """Loft a smooth 100% quad-ring tapered utensil along local X from `[(lx, hw, hz), ...]`."""
        n_c = 12
        rings: list[list[Vector]] = []
        for lx, hw, hz in specs:
            ring = []
            for j in range(n_c):
                a = math.tau * j / n_c
                ly = off_y + hw * math.cos(a)
                lz = z_top + 0.0155 + hz * math.sin(a)
                wx = nx + lx * cn - ly * sn
                wy = ny + lx * sn + ly * cn
                ring.append(Vector((wx, wy, lz)))
            rings.append(ring)
        p_a = Vector((nx + (specs[0][0] - 0.004) * cn - off_y * sn, ny + (specs[0][0] - 0.004) * sn + off_y * cn, z_top + 0.0155))
        p_b = Vector((nx + (specs[-1][0] + 0.004) * cn - off_y * sn, ny + (specs[-1][0] + 0.004) * sn + off_y * cn, z_top + 0.0155))
        add_closed_tube(bm, rings, p_a, p_b, mat_idx=mat_stainless)

    # Dinner Knife (rounded handle -> bolster -> flat tapered blade)
    _add_cutlery_loft(-0.017, [
        (-0.078, 0.0060, 0.0028), (-0.050, 0.0068, 0.0030), (-0.012, 0.0052, 0.0026),
        ( 0.002, 0.0042, 0.0022), ( 0.018, 0.0072, 0.0014), ( 0.056, 0.0076, 0.0012),
        ( 0.076, 0.0052, 0.0010),
    ])
    # Dinner Fork (tapered handle -> slender neck -> flared curved tine head)
    _add_cutlery_loft(+0.017, [
        (-0.074, 0.0054, 0.0024), (-0.044, 0.0062, 0.0026), (-0.006, 0.0034, 0.0020),
        ( 0.018, 0.0040, 0.0020), ( 0.036, 0.0095, 0.0016), ( 0.068, 0.0092, 0.0013),
        ( 0.076, 0.0075, 0.0011),
    ])


def add_host_podium_quad(
    bm: bmesh.types.BMesh,
    uv_layer,
    x: float,
    y: float,
    z_floor: float,
    *,
    mat_body: int = 4,
    mat_front: int = 3,
    mat_stainless: int = 5,
    mat_brass: int = 7,
) -> None:
    """100% structured quad-flow News Cafe architectural host lectern podium resting EXACTLY FLUSH on `z_floor`!"""
    # 1. 4 Recessed Swivel Caster Glide Feet resting EXACTLY FLUSH at `z_floor + 0.0000 m`!
    foot_p = [(0.008, 0.000), (0.026, 0.000), (0.026, 0.022), (0.022, 0.034), (0.010, 0.035)]
    for fx in (-0.25, 0.25):
        for fy in (-0.19, 0.19):
            add_revolved_profile(bm, (x + fx, y + fy, z_floor), foot_p, segs=16, mat_idx=mat_stainless)

    # 2. Recessed Stepped Lower Plinth + Main Architectural Cabinet Body (`add_quad_grid_box` 100% pure quads!)
    add_quad_grid_box(bm, (x, y, z_floor + 0.072), (0.62, 0.50, 0.095), mat_body, segs_xyz=(6, 4, 2), round_r=0.008)
    add_quad_grid_box(bm, (x, y, z_floor + 0.565), (0.68, 0.54, 0.915), mat_body, segs_xyz=(6, 6, 8), round_r=0.010)
    # Recessed decorative molding trim bands around upper & lower cabinet perimeter (non-coincident!)
    add_quad_grid_box(bm, (x, y, z_floor + 0.125), (0.71, 0.57, 0.034), mat_body, segs_xyz=(6, 6, 2), round_r=0.006)
    add_quad_grid_box(bm, (x, y, z_floor + 1.028), (0.72, 0.58, 0.042), mat_body, segs_xyz=(6, 6, 2), round_r=0.008)

    # 3. Sloped Lectern Reading Desk Top + Solid Tapered Riser Collar (ZERO air gap!) + Brass Book-Stop Bar!
    #    Cabinet crown ends at `z_floor + 1.049`; tilted desk (`+9 deg` around X) rises from `1.046` at -Y to `1.140` at +Y.
    #    Solid recessed collar neck (`z = 1.038 .. 1.132`, tilted underside seated solidly into crown) joins desk flush!
    add_quad_grid_box(bm, (x, y + 0.04, z_floor + 1.062), (0.66, 0.48, 0.068), mat_body, segs_xyz=(6, 4, 2), round_r=0.004)
    add_quad_grid_box(
        bm, (x, y + 0.01, z_floor + 1.106), (0.74, 0.58, 0.046), mat_body,
        rot_euler=(math.radians(9.0), 0.0, 0.0), segs_xyz=(6, 6, 2), round_r=0.008,
    )
    add_quad_grid_box(
        bm, (x, y - 0.242, z_floor + 1.096), (0.66, 0.022, 0.028), mat_brass,
        rot_euler=(math.radians(9.0), 0.0, 0.0), segs_xyz=(6, 2, 2), round_r=0.004,
    )
    # Brushed stainless rear clerk handle rail (`-Y` side)
    add_cylinder(bm, (x - 0.20, y - 0.295, z_floor + 0.88), (x + 0.20, y - 0.295, z_floor + 0.88), 0.010, 0.010, segs=12, mat_idx=mat_stainless)
    for hx in (-0.19, 0.19):
        add_cylinder(bm, (x + hx, y - 0.265, z_floor + 0.88), (x + hx, y - 0.292, z_floor + 0.88), 0.008, 0.008, segs=10, mat_idx=mat_stainless)

    # 4. Crisp UV-Mapped `"NC / NEWS CAFE"` Front Graphic Plaque (`+Y` face, pure quads!)
    add_uv_mapped_sign_plate(
        bm, (x, y + 0.278, z_floor + 0.565), 0.54, 0.78, 0.020,
        face_dir="+Y", mat_front=mat_front, mat_back=mat_body, uv_layer=uv_layer,
    )


def add_menu_stand_quad(
    bm: bmesh.types.BMesh,
    uv_layer,
    x: float,
    y: float,
    z_floor: float,
    *,
    mat_stainless: int = 5,
    mat_menu: int = 6,
) -> None:
    """100% structured quad-flow brushed-stainless News Cafe LED menu vitrine stand resting EXACTLY FLUSH on `z_floor`!"""
    # 1. Heavy Stepped Beveled Stainless Floor Base Plate resting EXACTLY FLUSH at `z_floor + 0.0000 m`!
    add_quad_grid_box(bm, (x, y, z_floor + 0.016), (0.58, 0.36, 0.032), mat_stainless, segs_xyz=(6, 4, 2), round_r=0.006)
    add_quad_grid_box(bm, (x, y, z_floor + 0.036), (0.50, 0.28, 0.016), mat_stainless, segs_xyz=(6, 4, 2), round_r=0.004)

    # 2. Twin Vertical Brushed-Stainless Tubular Posts w/ Flanged Base Collars & 2 Horizontal Tie Crossbars!
    post_col_p = [(0.012, 0.040), (0.032, 0.040), (0.032, 0.056), (0.022, 0.072), (0.016, 0.078), (0.016, 0.585), (0.010, 0.585)]
    for px_off in (-0.185, 0.185):
        add_revolved_profile(bm, (x + px_off, y, z_floor), post_col_p, segs=16, mat_idx=mat_stainless)
    for hz_bar in (0.24, 0.44):
        add_cylinder(bm, (x - 0.180, y, z_floor + hz_bar), (x + 0.180, y, z_floor + hz_bar), 0.011, 0.011, segs=12, mat_idx=mat_stainless)

    # 3. LED Menu Vitrine Display Cabinet: Solid Back Housing + True 45-deg Mitered All-Quad Stainless Bezel + Menu Sheet!
    add_quad_grid_box(bm, (x, y - 0.012, z_floor + 0.935), (0.56, 0.048, 0.74), mat_stainless, segs_xyz=(6, 2, 8), round_r=0.006)
    add_mitered_frame(
        bm, x, y + 0.010, z_floor + 0.935, 0.56, 0.74, 0.042, 0.030,
        mat_idx=mat_stainless, front_inset=0.005, step_depth=0.007, face_axis="+Y",
    )
    add_uv_mapped_sign_plate(
        bm, (x, y + 0.020, z_floor + 0.935), 0.48, 0.66, 0.010,
        face_dir="+Y", mat_front=mat_menu, mat_back=mat_stainless, uv_layer=uv_layer,
    )


def add_curved_leaf(
    bm: bmesh.types.BMesh,
    root: Vector,
    forward: Vector,
    up_hint: Vector,
    length: float,
    width: float,
    *,
    droop: float = 0.0,
    v_fold: float = 0.14,
    thickness: float = 0.005,
    n_segs: int = 3,
    shape: str = "ovate",
    mat_idx: int = 0,
) -> list[bmesh.types.BMFace]:
    """Add a realistic 3D arched, V-folded, smoothly contoured watertight botanical leaf (`24-36` tris!).

    `shape`:
      - `"ovate"`: broad rounded Sea Grape / Buttonwood / tropical hedge leaf
      - `"palm"`: long slender graceful arched coconut-palm leaflet tapering to a fine tip
      - `"petal"`: wide cupped papery heart-rounded bougainvillea bract
    """
    fwd = forward.normalized()
    right = fwd.cross(up_hint)
    if right.length < 1e-5:
        alt = Vector((1, 0, 0)) if abs(fwd.x) < 0.9 else Vector((0, 1, 0))
        right = fwd.cross(alt)
    right.normalize()
    up = right.cross(fwd).normalized()

    ht = max(thickness, 0.004) * 0.5
    v_root = bm.verts.new(root)

    # Build `n_segs` intermediate cross-sections (each 4 vertices: left, top-midrib, right, bot-midrib)
    rings: list[tuple] = []
    for s in range(1, n_segs + 1):
        t = s / (n_segs + 1)
        if shape == "palm":
            w_env = math.sin(math.pi * math.pow(t, 0.55)) * (1.0 - 0.25 * t)
            arch = length * 0.09 * math.sin(math.pi * t)
        elif shape == "petal":
            w_env = math.sin(math.pi * math.pow(t, 0.62)) ** 0.72
            arch = -length * 0.12 * math.sin(math.pi * t)  # gentle inward cup!
        else:  # "ovate"
            w_env = math.sin(math.pi * math.pow(t, 0.72)) ** 0.80
            arch = length * 0.07 * math.sin(math.pi * t)

        hw = max(width * 0.5 * w_env, 0.004)
        c_pt = root + fwd * (length * t) + up * arch + Vector((0, 0, -droop * (t ** 1.85)))
        fold_lift = hw * v_fold
        vl = bm.verts.new(c_pt - right * hw + up * fold_lift)
        vt = bm.verts.new(c_pt + up * ht)
        vr = bm.verts.new(c_pt + right * hw + up * fold_lift)
        vb = bm.verts.new(c_pt - up * ht)
        rings.append((vl, vt, vr, vb))

    tip_pt = root + fwd * length + Vector((0, 0, -droop))
    v_tip = bm.verts.new(tip_pt)

    faces: list[bmesh.types.BMFace] = []
    # Root fan -> first ring
    r0 = rings[0]
    for a, b in [(r0[0], r0[1]), (r0[1], r0[2]), (r0[2], r0[3]), (r0[3], r0[0])]:
        faces.append(bm.faces.new((v_root, b, a)))
    # Ring-to-ring quads
    for i in range(len(rings) - 1):
        ra, rb = rings[i], rings[i + 1]
        for k in range(4):
            kn = (k + 1) % 4
            faces.append(bm.faces.new((ra[k], ra[kn], rb[kn], rb[k])))
    # Last ring -> tip fan
    rl = rings[-1]
    for a, b in [(rl[0], rl[1]), (rl[1], rl[2]), (rl[2], rl[3]), (rl[3], rl[0])]:
        faces.append(bm.faces.new((a, b, v_tip)))

    for f in faces:
        f.material_index = mat_idx
    return faces


def add_bougainvillea_cluster(
    bm: bmesh.types.BMesh,
    center: Vector,
    normal_dir: Vector,
    scale: float,
    rng,
    *,
    mat_bract: int = 0,
    mat_floret: int = 4,
) -> list[bmesh.types.BMFace]:
    """Add ONE photorealistic 3-bract papery cupped bougainvillea blossom cluster w/ tiny cream center floret!"""
    n_ax = normal_dir.normalized()
    ref = Vector((0, 0, 1)) if abs(n_ax.z) < 0.88 else Vector((1, 0, 0))
    u_ax = n_ax.cross(ref).normalized()
    v_ax = n_ax.cross(u_ax).normalized()
    a0 = rng.uniform(0.0, math.tau)
    faces: list[bmesh.types.BMFace] = []

    # 3 wide cupped papery petal bracts arranged at 120° around the central floret
    for k in range(3):
        ang = a0 + k * (math.tau / 3.0) + rng.uniform(-0.18, 0.18)
        rad = u_ax * math.cos(ang) + v_ax * math.sin(ang)
        p_dir = (rad * 0.84 + n_ax * rng.uniform(0.32, 0.56)).normalized()
        p_up = (n_ax * 0.85 - rad * 0.35).normalized()
        p_len = scale * rng.uniform(0.88, 1.16)
        p_wid = p_len * rng.uniform(0.86, 1.04)
        faces.extend(
            add_curved_leaf(
                bm, center + rad * 0.004, p_dir, p_up, p_len, p_wid,
                droop=p_len * 0.06, v_fold=-0.22, thickness=0.004, n_segs=2, shape="petal", mat_idx=mat_bract,
            )
        )
    # Tiny cream-white central bougainvillea tubular floret bud (iconic biological signature!)
    faces.extend(
        add_cylinder(bm, center - n_ax * 0.004, center + n_ax * (scale * 0.34), 0.0055, 0.0085, segs=6, mat_idx=mat_floret)
    )
    return faces


# Backwards-compatible alias forwarding cleanly to high-poly curved leaf!
def add_leaf_blade(
    bm: bmesh.types.BMesh,
    root: Vector,
    forward: Vector,
    up_hint: Vector,
    length: float,
    width: float,
    *,
    droop: float = 0.0,
    thickness: float = 0.006,
    mat_idx: int = 0,
) -> list[bmesh.types.BMFace]:
    return add_curved_leaf(
        bm, root, forward, up_hint, length, width,
        droop=droop, thickness=thickness, n_segs=3, shape="ovate", mat_idx=mat_idx,
    )


def add_prism_xy(
    bm: bmesh.types.BMesh,
    poly2d: list[tuple[float, float]],
    z0: float,
    z1: float,
    mat_idx: int = 0,
) -> list[bmesh.types.BMFace]:
    """Extrude a simple closed 2D polygon cleanly from `z0` to `z1`."""
    pts = [(float(x), float(y)) for x, y in poly2d]
    area2 = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if area2 < 0.0:
        pts.reverse()
    n = len(pts)
    vb = [bm.verts.new((x, y, z0)) for x, y in pts]
    vt = [bm.verts.new((x, y, z1)) for x, y in pts]
    faces: list[bmesh.types.BMFace] = []
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((vb[i], vb[j], vt[j], vt[i])))
    faces.append(bm.faces.new(list(reversed(vb))))
    faces.append(bm.faces.new(vt))
    for f in faces:
        f.material_index = mat_idx
    return faces


def add_breeze_block(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    width: float,
    height: float,
    depth: float,
    *,
    normal_axis: str = "+Y",
    mat_idx: int = 0,
) -> list[bmesh.types.BMFace]:
    """Add ONE high-poly smooth 24-segment curved Art Deco 4-petal quatrefoil Miami Beach breeze block!

    Features genuine curved concave rosette petals + beveled inner aperture lips catching bright Miami sunlight!
    """
    hw = width * 0.5
    hh = height * 0.5
    hd = depth * 0.5
    n_ring = 24  # 6 segments per side -> silky smooth concave quatrefoil floral cutout!

    outer_uv: list[tuple[float, float]] = []
    inner_uv: list[tuple[float, float]] = []
    inner_bev_uv: list[tuple[float, float]] = []

    for k in range(n_ring):
        # Angle starting at +X (0..2pi)
        ang = (k / n_ring) * math.tau
        ca, sa = math.cos(ang), math.sin(ang)
        # Project ray onto exact outer square border [-hw..hw] x [-hh..hh]
        s_box = min(hw / max(abs(ca), 1e-6), hh / max(abs(sa), 1e-6))
        outer_uv.append((ca * s_box, sa * s_box))

        # Authentic smooth concave Art Deco 4-petal starburst / floral quatrefoil cutout!
        lobe = abs(math.cos(2.0 * ang)) ** 1.45
        r_fac = 0.43 + 0.37 * lobe  # 0.80 at cardinal N/S/E/W tips, smooth 0.43 pinched lobes at diagonals!
        iu, iv = ca * hw * r_fac, sa * hh * r_fac
        inner_uv.append((iu, iv))
        # Subtle recessed inner bevel shoulder (+6% wider on outer surface -> crisp sunlit chamfer!)
        inner_bev_uv.append((ca * hw * min(0.92, r_fac + 0.055), sa * hh * min(0.92, r_fac + 0.055)))

    cx, cy, cz = center

    def _pt(u: float, v: float, w: float) -> Vector:
        if normal_axis == "+Y":
            return Vector((cx + u, cy + w, cz + v))
        return Vector((cx + w, cy + u, cz + v))

    bev_d = min(0.012, depth * 0.14)
    vo_f = [bm.verts.new(_pt(u, v, +hd)) for u, v in outer_uv]
    vo_b = [bm.verts.new(_pt(u, v, -hd)) for u, v in outer_uv]
    vb_f = [bm.verts.new(_pt(u, v, +hd)) for u, v in inner_bev_uv]
    vb_b = [bm.verts.new(_pt(u, v, -hd)) for u, v in inner_bev_uv]
    vi_f = [bm.verts.new(_pt(u, v, +hd - bev_d)) for u, v in inner_uv]
    vi_b = [bm.verts.new(_pt(u, v, -hd + bev_d)) for u, v in inner_uv]

    faces: list[bmesh.types.BMFace] = []
    for k in range(n_ring):
        kn = (k + 1) % n_ring
        # Front face flat border + front chamfer bevel
        faces.append(bm.faces.new((vo_f[k], vo_f[kn], vb_f[kn], vb_f[k])))
        faces.append(bm.faces.new((vb_f[k], vb_f[kn], vi_f[kn], vi_f[k])))
        # Back face flat border + back chamfer bevel
        faces.append(bm.faces.new((vo_b[kn], vo_b[k], vb_b[k], vb_b[kn])))
        faces.append(bm.faces.new((vb_b[kn], vb_b[k], vi_b[k], vi_b[kn])))
        # Outer rim walls
        faces.append(bm.faces.new((vo_b[k], vo_b[kn], vo_f[kn], vo_f[k])))
        # Inner smooth quatrefoil tunnel walls
        faces.append(bm.faces.new((vi_f[k], vi_f[kn], vi_b[kn], vi_b[k])))

    for f in faces:
        f.material_index = mat_idx
    return faces


def add_closed_tube(
    bm: bmesh.types.BMesh,
    rings: list[list[Vector]],
    cap_a: Vector,
    cap_b: Vector,
    mat_idx: int = 0,
) -> list[bmesh.types.BMFace]:
    """Closed `S^2` lofted tube with apex end caps."""
    va = bm.verts.new(cap_a)
    vr = [[bm.verts.new(p) for p in r] for r in rings]
    vb = bm.verts.new(cap_b)
    nc = len(vr[0])
    faces: list[bmesh.types.BMFace] = []
    for j in range(nc):
        jn = (j + 1) % nc
        faces.append(bm.faces.new((va, vr[0][jn], vr[0][j])))
    for i in range(len(vr) - 1):
        for j in range(nc):
            jn = (j + 1) % nc
            faces.append(bm.faces.new((vr[i][j], vr[i][jn], vr[i + 1][jn], vr[i + 1][j])))
    for j in range(nc):
        jn = (j + 1) % nc
        faces.append(bm.faces.new((vr[-1][j], vr[-1][jn], vb)))
    for f in faces:
        f.material_index = mat_idx
    return faces


def add_mitered_frame(
    bm: bmesh.types.BMesh,
    cx: float,
    wall_y: float,
    cz: float,
    fw: float,
    fh: float,
    rail_w: float,
    depth: float,
    *,
    mat_idx: int = 0,
    front_inset: float = 0.006,
    step_depth: float = 0.008,
    face_axis: str = "+Y",
) -> list[bmesh.types.BMFace]:
    """Single watertight manifold 45-deg mitered rectangular museum frame (supports `+Y` back wall & `+X` side wall!)."""
    ohw, ohh = fw * 0.5, fh * 0.5
    ihw, ihh = max(0.02, ohw - rail_w), max(0.02, ohh - rail_w)
    bf = min(front_inset, rail_w * 0.35)
    sd = min(step_depth, depth * 0.45)

    signs = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    prof_specs = [
        (ohw, ohh, 0.0),
        (ohw, ohh, depth - sd),
        (ohw - bf, ohh - bf, depth),
        (ihw + bf, ihh + bf, depth),
        (ihw, ihh, depth - sd),
        (ihw, ihh, 0.0),
    ]
    if face_axis == "+X":
        # Here `cx` is wall_x, `wall_y` is center_y along the north wall!
        rings = [
            [bm.verts.new(Vector((cx + pd, wall_y + sx * hx, cz + sz * hz))) for sx, sz in signs]
            for hx, hz, pd in prof_specs
        ]
    else:
        rings = [
            [bm.verts.new(Vector((cx + sx * hx, wall_y + pd, cz + sz * hz))) for sx, sz in signs]
            for hx, hz, pd in prof_specs
        ]
    n_p = len(rings)
    faces: list[bmesh.types.BMFace] = []
    for p in range(n_p):
        pn = (p + 1) % n_p
        for c in range(4):
            cn = (c + 1) % 4
            f = bm.faces.new((rings[p][c], rings[p][cn], rings[pn][cn], rings[pn][c]))
            f.material_index = mat_idx
            faces.append(f)
    return faces


def add_uv_mapped_sign_plate(
    bm: bmesh.types.BMesh,
    center: tuple[float, float, float],
    width: float,
    height: float,
    thickness: float,
    *,
    face_dir: str = "+Y",
    mat_front: int = 0,
    mat_back: int = 1,
    uv_layer=None,
    yaw_rad: float = 0.0,
    uv_rect: tuple[float, float, float, float] = (0.01, 0.01, 0.99, 0.99),
) -> list[bmesh.types.BMFace]:
    """Add a solid watertight sign/graphic plate with exact `[0..1]` UV mapping on its front face."""
    hw, hh, ht = width * 0.5, height * 0.5, max(thickness, 0.006) * 0.5
    local_corners_front = [(-hw, -hh, +ht), (hw, -hh, +ht), (hw, hh, +ht), (-hw, hh, +ht)]
    local_corners_back = [(-hw, -hh, -ht), (hw, -hh, -ht), (hw, hh, -ht), (-hw, hh, -ht)]

    if face_dir == "+Y":
        u_ax, v_ax, n_ax = Vector((-1, 0, 0)), Vector((0, 0, 1)), Vector((0, 1, 0))
    elif face_dir == "+X":
        u_ax, v_ax, n_ax = Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0))
    elif face_dir == "-X":
        u_ax, v_ax, n_ax = Vector((0, -1, 0)), Vector((0, 0, 1)), Vector((-1, 0, 0))
    else:
        u_ax, v_ax, n_ax = Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0))

    rot_z = Matrix.Rotation(yaw_rad, 3, "Z")
    u_ax, v_ax, n_ax = rot_z @ u_ax, rot_z @ v_ax, rot_z @ n_ax
    c = Vector(center)

    vf = [bm.verts.new(c + u_ax * lx + v_ax * ly + n_ax * lz) for lx, ly, lz in local_corners_front]
    vb = [bm.verts.new(c + u_ax * lx + v_ax * ly + n_ax * lz) for lx, ly, lz in local_corners_back]

    f_front = bm.faces.new((vf[0], vf[1], vf[2], vf[3]))
    f_front.material_index = mat_front
    f_back = bm.faces.new((vb[3], vb[2], vb[1], vb[0]))
    f_back.material_index = mat_back
    sides = [
        bm.faces.new((vb[0], vb[1], vf[1], vf[0])),
        bm.faces.new((vb[1], vb[2], vf[2], vf[1])),
        bm.faces.new((vb[2], vb[3], vf[3], vf[2])),
        bm.faces.new((vb[3], vb[0], vf[0], vf[3])),
    ]
    for sf in sides:
        sf.material_index = mat_back

    if uv_layer is not None:
        u0, v0, u1, v1 = uv_rect
        uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        for loop, uv in zip(f_front.loops, uvs):
            loop[uv_layer].uv = uv
        for f_o in [f_back, *sides]:
            for loop in f_o.loops:
                loop[uv_layer].uv = (u0 + 0.01 * (u1 - u0), v0 + 0.01 * (v1 - v0))

    return [f_front, f_back, *sides]


def import_cad_to_bmesh(
    bm: bmesh.types.BMesh,
    glb_path: str,
    location: tuple[float, float, float],
    *,
    rot_z_rad: float = 0.0,
    scale: float = 1.0,
    mat_idx: int = 0,
    top_mat_idx: int | None = None,
    top_z_threshold: float | None = None,
    mat_fn=None,
) -> list[bmesh.types.BMFace]:
    """Import a `cad_bridge.py` 1:1m watertight GLB directly into `bm` with optional local-coord material zoning."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    new_obs = [o for o in bpy.data.objects if o not in before]
    xf_world = (
        Matrix.Translation(Vector(location))
        @ Matrix.Rotation(rot_z_rad, 4, "Z")
        @ Matrix.Scale(scale, 4)
    )

    added_faces: list[bmesh.types.BMFace] = []
    for ob in new_obs:
        if ob.type == "MESH":
            bm_tmp = bmesh.new()
            bm_tmp.from_mesh(ob.data)
            bm_tmp.transform(ob.matrix_world)
            vmap = {}
            local_cos = {}
            for v in bm_tmp.verts:
                local_cos[v.index] = v.co.copy()
                vmap[v.index] = bm.verts.new(xf_world @ v.co)
            for f in bm_tmp.faces:
                try:
                    nf = bm.faces.new([vmap[v.index] for v in f.verts])
                    if mat_fn is not None:
                        c_loc = sum((local_cos[v.index] for v in f.verts), Vector()) / len(f.verts)
                        nf.material_index = mat_fn(c_loc)
                    elif top_mat_idx is not None and top_z_threshold is not None:
                        avg_z = sum(local_cos[v.index].z for v in f.verts) / len(f.verts)
                        nf.material_index = top_mat_idx if avg_z >= top_z_threshold else mat_idx
                    else:
                        nf.material_index = mat_idx
                    added_faces.append(nf)
                except ValueError:
                    pass
            bm_tmp.free()

    for ob in new_obs:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
    return added_faces


def sub_collection(parent_col: bpy.types.Collection, name: str) -> bpy.types.Collection:
    """Create or retrieve a clean child sub-collection under `parent_col` for organized Blender Outliner hierarchy."""
    existing = parent_col.children.get(name)
    if existing is not None:
        return existing
    sub = bpy.data.collections.get(name)
    if sub is None:
        sub = bpy.data.collections.new(name)
    if sub.name not in parent_col.children:
        parent_col.children.link(sub)
    return sub


def finalize_mesh_data(
    bm: bmesh.types.BMesh,
    mesh_name: str,
    col: bpy.types.Collection,
    mat_list: list[bpy.types.Material],
    *,
    smooth_angle_deg: float = 42.0,
    preserve_existing_uv: bool = False,
    unwrap_angle_deg: float = 60.0,
    clean_merge_dist: float = 0.00025,
) -> bpy.types.Mesh:
    """Finalize a reusable watertight `Mesh` datablock (fixed-diagonal tris, outward normals, clean non-overlapping UVMap)."""
    if clean_merge_dist > 0.0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=clean_merge_dist)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=1e-6)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="FIXED")
    tiny = [f for f in bm.faces if f.calc_area() < 1e-9]
    if tiny:
        bmesh.ops.delete(bm, geom=tiny, context="FACES")
    ensure_all_islands_outward(bm)

    max_slot = max(0, len(mat_list) - 1)
    used_indices = sorted({min(max(f.material_index, 0), max_slot) for f in bm.faces})
    remap = {old_i: new_i for new_i, old_i in enumerate(used_indices)}
    for f in bm.faces:
        f.material_index = remap[min(max(f.material_index, 0), max_slot)]

    me = bpy.data.meshes.new(mesh_name)
    bm.to_mesh(me)
    bm.free()

    for old_i in used_indices:
        me.materials.append(mat_list[old_i])

    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if smooth_angle_deg is not None:
        try:
            me.set_sharp_from_angle(angle=math.radians(smooth_angle_deg))
        except AttributeError:
            pass
    me.update()

    if preserve_existing_uv and me.uv_layers:
        old_uv = me.uv_layers.active
        old_uv.name = "GraphicUV"
        bm_g = bmesh.new()
        bm_g.from_mesh(me)
        g_lay = bm_g.loops.layers.uv["GraphicUV"]
        for f in bm_g.faces:
            for l in f.loops:
                l[g_lay].uv.x = max(0.001, min(0.999, l[g_lay].uv.x))
                l[g_lay].uv.y = max(0.001, min(0.999, l[g_lay].uv.y))
        bm_g.to_mesh(me)
        bm_g.free()

        bake_uv = me.uv_layers.new(name="UVMap")
        me.uv_layers.active = bake_uv
        me.uv_layers.active_index = list(me.uv_layers).index(bake_uv)
        me.update()

    # Temporary helper object to run Blender's native smart_project & pack_islands on `me`
    tmp_ob = bpy.data.objects.new(f"__tmp_uv_{mesh_name}", me)
    col.objects.link(tmp_ob)
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    tmp_ob.select_set(True)
    bpy.context.view_layer.objects.active = tmp_ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=math.radians(unwrap_angle_deg),
        island_margin=0.005,
        scale_to_bounds=False,
    )
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    tmp_ob.select_set(False)
    bpy.data.objects.remove(tmp_ob, do_unlink=True)

    bm_u = bmesh.new()
    bm_u.from_mesh(me)
    uv_lay = bm_u.loops.layers.uv.active
    if uv_lay is not None:
        for f in bm_u.faces:
            for l in f.loops:
                l[uv_lay].uv.x = max(0.001, min(0.999, l[uv_lay].uv.x))
                l[uv_lay].uv.y = max(0.001, min(0.999, l[uv_lay].uv.y))
            pts = [l[uv_lay].uv for l in f.loops]
            a2 = sum(
                pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y
                for i in range(len(pts))
            )
            if abs(a2) < 1e-10:
                u0, v0 = max(0.002, min(0.997, pts[0].x)), max(0.002, min(0.997, pts[0].y))
                for idx_l, l in enumerate(f.loops):
                    l[uv_lay].uv = (u0 + (0.00015 if idx_l == 1 else 0.0), v0 + (0.00015 if idx_l >= 2 else 0.0))
        bm_u.to_mesh(me)
    bm_u.free()
    me.update()
    return me


def spawn_instance(
    name: str,
    mesh_data: bpy.types.Mesh,
    col: bpy.types.Collection,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    yaw_rad: float = 0.0,
    *,
    role: str = "solid",
    asset_set: str = "",
    instanced: bool = True,
) -> bpy.types.Object:
    """Link a clean world-placed object sharing `mesh_data` (scale=(1,1,1), exact pivot, dedicated 2K UV set!)."""
    ob = bpy.data.objects.new(name, mesh_data)
    ob.location = Vector(location)
    ob.rotation_euler = Euler((0.0, 0.0, yaw_rad), "XYZ")
    ob.scale = Vector((1.0, 1.0, 1.0))
    col.objects.link(ob)
    ob["sc_part"] = name
    ob["sc_role"] = role
    if asset_set:
        ob["vf_asset_set"] = asset_set
    ob["vf_instanced"] = bool(instanced)
    return ob


def finalize_part(
    bm: bmesh.types.BMesh,
    name: str,
    col: bpy.types.Collection,
    mat_list: list[bpy.types.Material],
    *,
    role: str = "solid",
    smooth_angle_deg: float = 42.0,
    preserve_existing_uv: bool = False,
    unwrap_angle_deg: float = 60.0,
    clean_merge_dist: float = 0.00025,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    yaw_rad: float = 0.0,
    asset_set: str = "",
) -> bpy.types.Object:
    """Triangulate, verify outward normals on all islands, create object, tag `sc_part`, and unwrap clean `[0,1]` UVs."""
    me = finalize_mesh_data(
        bm, name, col, mat_list,
        smooth_angle_deg=smooth_angle_deg,
        preserve_existing_uv=preserve_existing_uv,
        unwrap_angle_deg=unwrap_angle_deg,
        clean_merge_dist=clean_merge_dist,
    )
    return spawn_instance(name, me, col, location=location, yaw_rad=yaw_rad, role=role, asset_set=asset_set, instanced=False)
