"""Procedural mesh builders: lofts, sweeps, tubes, lathes, rounded prisms and primitives.

All builders return a linked mesh object with mesh-level materials. Coordinates are meters.
Profiles for sweeps are 2D (x = side, y = up) relative to the path frame.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import core


def _v3(p):
    if isinstance(p, Vector) and len(p) == 3:
        return p.copy()
    return Vector((p[0], p[1], p[2] if len(p) > 2 else 0.0))


def xform(points, matrix):
    return [matrix @ _v3(p) for p in points]


# ---------------------------------------------------------------------------
# Shading & cleanup
# ---------------------------------------------------------------------------
def shade(ob, sharp_angle=35.0):
    """Smooth shading with sharp edges above `sharp_angle` degrees (None = fully smooth)."""
    me = ob.data
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if sharp_angle is not None:
        try:
            me.set_sharp_from_angle(angle=math.radians(sharp_angle))
        except AttributeError:  # Blender < 4.1
            me.use_auto_smooth = True
            me.auto_smooth_angle = math.radians(sharp_angle)
    me.update()
    return ob


def shade_flat(ob):
    me = ob.data
    me.polygons.foreach_set("use_smooth", [False] * len(me.polygons))
    me.update()
    return ob


def cleanup(ob, merge=1e-5, recalc=False):
    """Weld coincident verts, remove degenerate geometry and loose verts."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=max(merge or 0.0, 1e-7))
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return ob


def _finish(ob, col, mats, smooth, sharp_angle, parent, merge, recalc, flip):
    core.link(ob, col, parent)
    if mats is not None:
        for m in (mats if isinstance(mats, (list, tuple)) else [mats]):
            ob.data.materials.append(m)
    cleanup(ob, merge, recalc)
    if flip:
        ob.data.flip_normals()
    if smooth:
        shade(ob, sharp_angle)
    else:
        shade_flat(ob)
    return ob


def mesh_object(name, verts, faces, col, mats=None, mat_indices=None, smooth=True, sharp_angle=35.0,
                parent=None, merge=1e-5, recalc=False, flip=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(_v3(v)) for v in verts], [], [tuple(f) for f in faces])
    if mat_indices is not None:
        me.polygons.foreach_set("material_index", list(mat_indices))
    me.update()
    ob = bpy.data.objects.new(name, me)
    return _finish(ob, col, mats, smooth, sharp_angle, parent, merge, recalc, flip)


def obj_from_bmesh(name, bm, col, mats=None, smooth=True, sharp_angle=35.0, parent=None, merge=1e-5,
                   recalc=False, flip=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    return _finish(ob, col, mats, smooth, sharp_angle, parent, merge, recalc, flip)


# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------
def add_bevel(ob, width, segments=2, angle=30.0, profile=0.5, clamp=True, harden=False):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    m.profile = profile
    m.use_clamp_overlap = clamp
    m.harden_normals = harden
    return m


def add_weighted_normal(ob, weight=50, keep_sharp=True):
    m = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.weight = weight
    m.keep_sharp = keep_sharp
    m.mode = "FACE_AREA"
    return m


def add_solidify(ob, thickness, offset=-1.0, even=True, rim=True):
    m = ob.modifiers.new("Solidify", "SOLIDIFY")
    m.thickness = thickness
    m.offset = offset
    m.use_even_offset = even
    m.use_rim = rim
    return m


def add_subsurf(ob, levels=1):
    m = ob.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    return m


def add_mirror(ob, x=True, y=False, z=False, merge=1e-4, clip=True):
    m = ob.modifiers.new("Mirror", "MIRROR")
    m.use_axis = (x, y, z)
    m.use_mirror_merge = merge > 0
    m.merge_threshold = merge
    m.use_clip = clip
    return m


def finish_hard_surface(ob, bevel=0.004, segments=2, angle=30.0):
    """The standard game-ready look: small angle bevel + weighted normals."""
    if bevel:
        add_bevel(ob, bevel, segments, angle)
    add_weighted_normal(ob)
    return ob


# ---------------------------------------------------------------------------
# 2D profiles
# ---------------------------------------------------------------------------
def circle2d(r, seg=16, start=0.0):
    return [(r * math.cos(start + 2 * math.pi * i / seg), r * math.sin(start + 2 * math.pi * i / seg))
            for i in range(seg)]


def ellipse2d(rx, ry, seg=16):
    return [(rx * math.cos(2 * math.pi * i / seg), ry * math.sin(2 * math.pi * i / seg)) for i in range(seg)]


def rrect2d(w, h, r, seg=3):
    """Rounded rectangle centred on the origin (counter-clockwise)."""
    r = min(r, w / 2 - 1e-5, h / 2 - 1e-5)
    hw, hh = w / 2 - r, h / 2 - r
    pts = []
    for cx, cy, a0 in ((hw, hh, 0.0), (-hw, hh, 90.0), (-hw, -hh, 180.0), (hw, -hh, 270.0)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90.0 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def fillet_poly(points, radius, seg=4):
    """Round every corner of a closed 2D polygon. `radius` may be a scalar or per-corner list."""
    pts = [Vector((p[0], p[1])) for p in points]
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        r = radius[i] if isinstance(radius, (list, tuple)) else radius
        d1, d2 = (p0 - p1), (p2 - p1)
        if r <= 0 or d1.length < 1e-9 or d2.length < 1e-9:
            out.append(p1)
            continue
        d1n, d2n = d1.normalized(), d2.normalized()
        ang = d1n.angle(d2n)
        if ang < 1e-3 or abs(ang - math.pi) < 1e-3:
            out.append(p1)
            continue
        dist = min(r / math.tan(ang / 2), d1.length * 0.49, d2.length * 0.49)
        r_eff = dist * math.tan(ang / 2)
        a, b = p1 + d1n * dist, p1 + d2n * dist
        center = p1 + (d1n + d2n).normalized() * (r_eff / math.sin(ang / 2))
        va, vb = a - center, b - center
        a0 = math.atan2(va.y, va.x)
        delta = math.atan2(vb.y, vb.x) - a0
        while delta > math.pi:
            delta -= 2 * math.pi
        while delta < -math.pi:
            delta += 2 * math.pi
        for k in range(seg + 1):
            t = a0 + delta * k / seg
            out.append(center + r_eff * Vector((math.cos(t), math.sin(t))))
    return [(p.x, p.y) for p in out]


def catmull_rom(points, samples=6, closed=False):
    """Smooth a polyline through its control points (uniform Catmull-Rom)."""
    P = [_v3(p) for p in points]
    n = len(P)
    if n < 3:
        return P
    out = []
    seg_count = n if closed else n - 1
    for i in range(seg_count):
        p0 = P[(i - 1) % n] if closed else P[max(i - 1, 0)]
        p1 = P[i % n]
        p2 = P[(i + 1) % n] if closed else P[min(i + 1, n - 1)]
        p3 = P[(i + 2) % n] if closed else P[min(i + 2, n - 1)]
        for k in range(samples):
            t = k / samples
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return out


# ---------------------------------------------------------------------------
# Lofts & sweeps
# ---------------------------------------------------------------------------
def loft(name, rings, col, mats=None, closed=False, cap_start=False, cap_end=False, mat_fn=None,
         cap_mat=(0, 0), smooth=True, sharp_angle=35.0, flip=False, parent=None, merge=1e-5, recalc=None):
    """Skin a list of equally sized point rings. mat_fn(ring_index, segment_index) -> slot index."""
    n = len(rings[0])
    if any(len(r) != n for r in rings):
        raise ValueError(f"loft {name}: rings must share a point count")
    verts = [_v3(p) for r in rings for p in r]
    faces, mis = [], []
    segs = n if closed else n - 1
    for i in range(len(rings) - 1):
        for j in range(segs):
            j2 = (j + 1) % n
            faces.append((i * n + j, i * n + j2, (i + 1) * n + j2, (i + 1) * n + j))
            mis.append(mat_fn(i, j) if mat_fn else 0)
    if cap_start:
        faces.append(tuple(reversed(range(n))))
        mis.append(cap_mat[0])
    if cap_end:
        base = (len(rings) - 1) * n
        faces.append(tuple(range(base, base + n)))
        mis.append(cap_mat[1])
    if recalc is None:
        recalc = closed and cap_start and cap_end
    return mesh_object(name, verts, faces, col, mats, mis, smooth, sharp_angle, parent, merge, recalc, flip)


def path_frames(path, up=(0, 0, 1), closed=False):
    """Parallel-transport frames (point, tangent, normal, binormal) along a polyline."""
    pts = [_v3(p) for p in path]
    n = len(pts)
    tans = []
    for i in range(n):
        if closed:
            a, b = pts[i - 1], pts[(i + 1) % n]
        else:
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        t = b - a
        tans.append(t.normalized() if t.length > 1e-12 else Vector((0, 1, 0)))
    up = Vector(up)
    nrm = up - tans[0] * up.dot(tans[0])
    if nrm.length < 1e-6:
        alt = Vector((1, 0, 0)) if abs(tans[0].x) < 0.9 else Vector((0, 1, 0))
        nrm = alt - tans[0] * alt.dot(tans[0])
    nrm.normalize()
    frames = []
    for i in range(n):
        if i > 0:
            nrm = tans[i - 1].rotation_difference(tans[i]) @ nrm
            nrm = (nrm - tans[i] * nrm.dot(tans[i])).normalized()
        frames.append((pts[i], tans[i], nrm, tans[i].cross(nrm)))
    return frames


def sweep(name, path, profile, col, mats=None, closed_profile=True, closed_path=False, cap=True, scale=None,
          up=(0, 0, 1), smooth=True, sharp_angle=None, parent=None, flip=False, mat_fn=None):
    """Sweep a 2D profile (x = side, y = up) along a 3D polyline. `scale(t)` tapers it."""
    frames = path_frames(path, up, closed_path)
    rings = []
    last = len(frames) - 1
    for i, (p, _t, n, b) in enumerate(frames):
        s = scale(i / last if last else 0.0) if scale else 1.0
        sx, sy = (s if isinstance(s, (int, float)) else s[0]), (s if isinstance(s, (int, float)) else s[1])
        rings.append([p + b * (x * sx) + n * (y * sy) for (x, y) in profile])
    if closed_path:
        rings.append([v.copy() for v in rings[0]])
    end_caps = cap and closed_profile and not closed_path
    return loft(name, rings, col, mats, closed=closed_profile, cap_start=end_caps, cap_end=end_caps,
                mat_fn=mat_fn, smooth=smooth, sharp_angle=sharp_angle, flip=flip, parent=parent,
                recalc=closed_profile)


def tube(name, points, radius, col, mats=None, seg=12, smooth_samples=0, cap=True, closed=False,
         up=(0, 0, 1), parent=None):
    path = catmull_rom(points, smooth_samples, closed) if smooth_samples else [_v3(p) for p in points]
    if closed and smooth_samples:
        pass  # catmull_rom(closed=True) already wraps without duplicating the first point
    return sweep(name, path, circle2d(radius, seg), col, mats, True, closed, cap, None, up, True, None, parent)


def lathe(name, profile, col, mats=None, seg=32, center=(0, 0, 0), axis=(0, 0, 1), cap_start=False,
          cap_end=False, sharp_angle=40.0, parent=None):
    """Revolve a (radius, height) profile around `axis` through `center`."""
    m = core.axis_matrix(center, axis)
    rings = []
    for r, h in profile:
        rings.append([m @ Vector((r * math.cos(2 * math.pi * k / seg), r * math.sin(2 * math.pi * k / seg), h))
                      for k in range(seg)])
    return loft(name, rings, col, mats, closed=True, cap_start=cap_start, cap_end=cap_end,
                sharp_angle=sharp_angle, parent=parent, recalc=True)


def prism(name, poly2d, z0, z1, col, mats=None, matrix=None, sharp_angle=35.0, parent=None, taper=None):
    """Extrude a closed 2D polygon (XY) from z0 to z1. `taper` scales the top ring about its centroid."""
    m = matrix or Matrix.Identity(4)
    cx = sum(p[0] for p in poly2d) / len(poly2d)
    cy = sum(p[1] for p in poly2d) / len(poly2d)
    s = taper if taper is not None else 1.0
    bot = [m @ Vector((x, y, z0)) for x, y in poly2d]
    top = [m @ Vector((cx + (x - cx) * s, cy + (y - cy) * s, z1)) for x, y in poly2d]
    return loft(name, [bot, top], col, mats, closed=True, cap_start=True, cap_end=True,
                sharp_angle=sharp_angle, parent=parent, recalc=True)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def _place(ob, location, rotation):
    ob.location = location
    ob.rotation_euler = rotation
    return ob


def box(name, size, col, mats=None, location=(0, 0, 0), rotation=(0, 0, 0), bevel=0.0, segments=3,
        parent=None, weighted=True, bevel_angle=30.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    ob = obj_from_bmesh(name, bm, col, mats, True, 35.0, parent, recalc=True)
    _place(ob, location, rotation)
    if bevel:
        add_bevel(ob, bevel, segments, bevel_angle)
    if weighted:
        add_weighted_normal(ob)
    return ob


def cylinder(name, radius, depth, col, mats=None, location=(0, 0, 0), rotation=(0, 0, 0), seg=24,
             radius2=None, cap=True, bevel=0.0, segments=2, parent=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=radius,
                          radius2=radius if radius2 is None else radius2, depth=depth)
    ob = obj_from_bmesh(name, bm, col, mats, True, 40.0, parent, recalc=True)
    _place(ob, location, rotation)
    if bevel:
        add_bevel(ob, bevel, segments, 40.0)
        add_weighted_normal(ob)
    return ob


def sphere(name, radius, col, mats=None, location=(0, 0, 0), scale=(1, 1, 1), seg=24, rings=12, parent=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=radius)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
    ob = obj_from_bmesh(name, bm, col, mats, True, None, parent, recalc=True)
    ob.location = location
    return ob


def torus(name, major, minor, col, mats=None, center=(0, 0, 0), axis=(0, 0, 1), seg=48, rseg=12, parent=None):
    m = core.axis_matrix(center, axis)
    path = [m @ Vector((major * math.cos(2 * math.pi * k / seg), major * math.sin(2 * math.pi * k / seg), 0))
            for k in range(seg)]
    return sweep(name, path, circle2d(minor, rseg), col, mats, True, True, False, None,
                 m.to_3x3() @ Vector((0, 0, 1)), True, None, parent)


# Re-export structured quad-flow & environment primitives from vflib.quadflow
from .quadflow import (  # noqa: E402, F401
    add_bougainvillea_cluster,
    add_box,
    add_box_bounds,
    add_breeze_block,
    add_closed_tube,
    add_curved_leaf,
    add_cylinder,
    add_mitered_frame,
    add_quad_grid_box,
    add_quad_sphere,
    add_revolved_profile,
    add_revolved_ring,
    add_spline_tube,
    add_torus_ring,
    add_uv_mapped_sign_plate,
    deconflict_botanical_islands,
    ensure_all_islands_outward,
    finalize_mesh_data,
    finalize_part,
    ground_objects_safe,
    import_cad_to_bmesh,
    spawn_instance,
    sub_collection,
)

