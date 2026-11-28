"""Structured quad-flow geometry, linked instancing, botanical de-confliction & safe grounding."""
from __future__ import annotations

import math
import os
import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from . import core


# ---------------------------------------------------------------------------
# Outliner hierarchy & linked instancing
# ---------------------------------------------------------------------------

def sub_collection(name, parent=None):
    """Return or create child collection `name` linked under `parent` (or active scene)."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    target_parent = parent if parent is not None else bpy.context.scene.collection
    if col.name not in target_parent.children:
        target_parent.children.link(col)
    return col


def spawn_instance(name, mesh_data, col, *, loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0),
                   scale=(1.0, 1.0, 1.0), asset_set=None, instanced=True):
    """Create a linked Object referencing `mesh_data` with transform & `vf_asset_set` metadata."""
    ob = bpy.data.objects.new(name, mesh_data)
    ob.location = Vector(loc)
    ob.rotation_euler = Vector(rot)
    ob.scale = Vector(scale)
    if instanced:
        ob["vf_instanced"] = True
    if asset_set:
        ob["vf_asset_set"] = str(asset_set)
    col.objects.link(ob)
    return ob


# ---------------------------------------------------------------------------
# Signed-volume orientation, UV clamp-before-nudge & clean triangulation
# ---------------------------------------------------------------------------

def _island_signed_volume(verts_list, faces_list):
    if not faces_list:
        return 0.0
    ref = faces_list[0].verts[0].co
    vol = 0.0
    for f in faces_list:
        vs = f.verts
        if len(vs) < 3:
            continue
        v0 = vs[0].co - ref
        for k in range(1, len(vs) - 1):
            v1 = vs[k].co - ref
            v2 = vs[k + 1].co - ref
            vol += v0.dot(v1.cross(v2))
    return vol / 6.0


def ensure_all_islands_outward(bm):
    """Orient each disconnected closed component outward using exact 3D signed volume."""
    bm.faces.ensure_lookup_table()
    if not bm.faces:
        return
    visited = set()
    for f in bm.faces:
        if f.index in visited:
            continue
        stack = [f]
        comp = []
        visited.add(f.index)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in visited:
                        visited.add(nf.index)
                        stack.append(nf)
        has_boundary = any(len(e.link_faces) < 2 for cf in comp for e in cf.edges)
        if has_boundary:
            continue
        vol = _island_signed_volume(bm.verts, comp)
        if vol < -1e-11:
            bmesh.ops.reverse_faces(bm, faces=comp)
    bm.normal_update()


def _clamp_then_nudge_uvs(bm, margin=0.001):
    """Clamp all UVs to `[margin, 1-margin]` FIRST, then nudge degenerate 2D triangles cleanly."""
    lo, hi = float(margin), 1.0 - float(margin)
    for uv_layer in bm.loops.layers.uv:
        for f in bm.faces:
            for lp in f.loops:
                uv = lp[uv_layer].uv
                uv.x = min(hi, max(lo, uv.x))
                uv.y = min(hi, max(lo, uv.y))
        for f in bm.faces:
            if len(f.loops) < 3:
                continue
            u0 = f.loops[0][uv_layer].uv
            u1 = f.loops[1][uv_layer].uv
            u2 = f.loops[2][uv_layer].uv
            area2 = (u1.x - u0.x) * (u2.y - u0.y) - (u1.y - u0.y) * (u2.x - u0.x)
            if abs(area2) < 1e-9:
                dx = -0.0005 if u0.x > 0.5 else 0.0005
                if abs(u1.x - u0.x) + abs(u1.y - u0.y) < 1e-6:
                    u1.x = min(hi, max(lo, u0.x + dx))
                    u1.y = u0.y
                vx, vy = u1.x - u0.x, u1.y - u0.y
                vlen = max(1e-8, math.hypot(vx, vy))
                px, py = -vy / vlen, vx / vlen
                step = 0.0005
                cx_u, cy_u = 0.5 * (u0.x + u1.x), 0.5 * (u0.y + u1.y)
                cand_x = min(hi, max(lo, cx_u + px * step))
                cand_y = min(hi, max(lo, cy_u + py * step))
                if abs((u1.x - u0.x) * (cand_y - u0.y) - (u1.y - u0.y) * (cand_x - u0.x)) < 1e-9:
                    cand_x = min(hi, max(lo, cx_u - px * step))
                    cand_y = min(hi, max(lo, cy_u - py * step))
                u2.x, u2.y = cand_x, cand_y


def finalize_mesh_data(bm, name, mats=None, *, smooth=True, sharp_angle=35.0, auto_uv=True,
                       triangulate=True, weld_tol=0.0):
    """Convert `bm` into a standalone `bpy.types.Mesh` with outward normals, clean UVs & `FIXED` tris."""
    if weld_tol > 0.0:
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=weld_tol)
    for v in list(bm.verts):
        if not v.link_faces:
            bm.verts.remove(v)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    ensure_all_islands_outward(bm)
    if triangulate and any(len(f.verts) > 3 for f in bm.faces):
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="FIXED", ngon_method="BEAUTY")
    has_existing_uv = len(bm.loops.layers.uv) > 0
    if has_existing_uv:
        _clamp_then_nudge_uvs(bm)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()

    if mats:
        for m in mats:
            if m is not None:
                mesh.materials.append(m)

    if smooth:
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        if sharp_angle is not None:
            try:
                mesh.set_sharp_from_angle(angle=math.radians(sharp_angle))
            except AttributeError:
                pass
    else:
        mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))

    if auto_uv and len(mesh.polygons) > 0:
        uv_layer = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
        mesh.uv_layers.active = uv_layer
        tmp_ob = bpy.data.objects.new(f"__vf_uv_{name}", mesh)
        bpy.context.scene.collection.objects.link(tmp_ob)
        try:
            core.ensure_object_mode()
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            tmp_ob.select_set(True)
            bpy.context.view_layer.objects.active = tmp_ob
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=math.radians(60.0), island_margin=0.015, scale_to_bounds=False)
            bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=0.012)
            bpy.ops.object.mode_set(mode="OBJECT")
            tmp_ob.select_set(False)
        finally:
            bpy.data.objects.remove(tmp_ob, do_unlink=True)
        bm_uv = bmesh.new()
        bm_uv.from_mesh(mesh)
        _clamp_then_nudge_uvs(bm_uv)
        bm_uv.to_mesh(mesh)
        bm_uv.free()
    mesh.update()
    return mesh


def finalize_part(bm, name, col, mats=None, *, smooth=True, sharp_angle=35.0, auto_uv=True,
                  triangulate=True, weld_tol=0.0, asset_set=None):
    """Finalize `bm` into an Object linked into `col` at origin with `vf_asset_set` tag."""
    mesh = finalize_mesh_data(
        bm, name, mats=mats, smooth=smooth, sharp_angle=sharp_angle,
        auto_uv=auto_uv, triangulate=triangulate, weld_tol=weld_tol,
    )
    ob = bpy.data.objects.new(name, mesh)
    if asset_set:
        ob["vf_asset_set"] = str(asset_set)
    col.objects.link(ob)
    return ob


# ---------------------------------------------------------------------------
# Structured quad-flow BMesh primitives
# ---------------------------------------------------------------------------

def _apply_uv_rect_to_faces(bm, faces, uv_name="UVMap"):
    uv_layer = bm.loops.layers.uv.get(uv_name) or bm.loops.layers.uv.new(uv_name)
    for f in faces:
        n = f.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for lp in f.loops:
            co = lp.vert.co
            if az >= ax and az >= ay:
                u, v = co.x, co.y
            elif ax >= ay and ax >= az:
                u, v = co.y, co.z
            else:
                u, v = co.x, co.z
            lp[uv_layer].uv = (
                max(0.001, min(0.999, (u * 0.4) % 0.998 + 0.001)),
                max(0.001, min(0.999, (v * 0.4) % 0.998 + 0.001)),
            )


def add_box(bm, center, size, mat_idx=0, rot_euler=None, *, bevel=0.0, bevel_segments=2):
    """Append an axis-aligned (or rotated) quad box centered at `center` (optionally micro-beveled)."""
    sx, sy, sz = (max(float(c), 1e-4) for c in size)
    mat_s = Matrix.Diagonal((sx, sy, sz, 1.0))
    mat_r = Euler(rot_euler, "XYZ").to_matrix().to_4x4() if rot_euler is not None else Matrix.Identity(4)
    mat_t = Matrix.Translation(Vector(center))
    xf = mat_t @ mat_r @ mat_s
    ret = bmesh.ops.create_cube(bm, size=1.0, matrix=xf)
    verts = set(ret["verts"])
    if bevel > 0.0:
        b_amt = min(float(bevel), min(sx, sy, sz) * 0.24)
        if b_amt > 1e-6:
            edges = [e for e in bm.edges if e.verts[0] in verts and e.verts[1] in verts]
            res = bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=b_amt,
                offset_type="OFFSET",
                segments=max(1, int(bevel_segments)),
                profile=0.5,
                affect="EDGES",
            )
            verts.update(res.get("verts", []))
    faces = [f for f in bm.faces if all(v in verts for v in f.verts)]
    for f in faces:
        f.material_index = mat_idx
    _apply_uv_rect_to_faces(bm, faces)
    return list(verts)


def add_box_bounds(bm, xmin, xmax, ymin, ymax, zmin, zmax, mat_idx=0, *, bevel=0.0, bevel_segments=2):
    """Append an axis-aligned box spanning explicit min/max bounds (optionally micro-beveled)."""
    cx = 0.5 * (xmin + xmax)
    cy = 0.5 * (ymin + ymax)
    cz = 0.5 * (zmin + zmax)
    return add_box(
        bm,
        (cx, cy, cz),
        (abs(xmax - xmin), abs(ymax - ymin), abs(zmax - zmin)),
        mat_idx=mat_idx,
        bevel=bevel,
        bevel_segments=bevel_segments,
    )


def add_quad_grid_box(bm, center, size, segs=(4, 4, 2), radius=0.0, mat_idx=0, rot_euler=None):
    """Build a subdivided all-quad box (ideal for beveled upholstery, seats, cushions, panels)."""
    sx, sy, sz = size
    nx, ny, nz = max(1, int(segs[0])), max(1, int(segs[1])), max(1, int(segs[2]))
    # Sample surface grid per axis with smooth corner beveling if radius > 0
    b2 = bmesh.new()
    bmesh.ops.create_cube(b2, size=1.0)
    for v in b2.verts:
        v.co.x *= sx
        v.co.y *= sy
        v.co.z *= sz
    cuts = max(nx, ny, nz) - 1
    if cuts > 0:
        bmesh.ops.subdivide_edges(b2, edges=list(b2.edges), cuts=cuts, use_grid_fill=True)
    if radius > 0.0:
        hx, hy, hz = 0.5 * sx, 0.5 * sy, 0.5 * sz
        r = min(radius, hx * 0.45, hy * 0.45, hz * 0.45)
        ix, iy, iz = max(1e-5, hx - r), max(1e-5, hy - r), max(1e-5, hz - r)
        for v in b2.verts:
            cx_v = max(-ix, min(ix, v.co.x))
            cy_v = max(-iy, min(iy, v.co.y))
            cz_v = max(-iz, min(iz, v.co.z))
            dv = Vector((v.co.x - cx_v, v.co.y - cy_v, v.co.z - cz_v))
            if dv.length > 1e-6:
                dv = dv.normalized() * r
                v.co = Vector((cx_v, cy_v, cz_v)) + dv
    m_rot = Euler(rot_euler, "XYZ").to_matrix() if rot_euler else Matrix.Identity(3)
    cvec = Vector(center)
    vmap = {}
    created_faces = []
    for v in b2.verts:
        nv = bm.verts.new((m_rot @ v.co) + cvec)
        vmap[v.index] = nv
    for f in b2.faces:
        nf = bm.faces.new([vmap[v.index] for v in f.verts])
        nf.material_index = mat_idx
        created_faces.append(nf)
    b2.free()
    _apply_uv_rect_to_faces(bm, created_faces)
    return list(vmap.values())


def add_cylinder(bm, p0, p1, r0, r1=None, segs=24, mat_idx=0, cap=True):
    """Append a tapered cylinder/frustum between `p0` and `p1`."""
    if r1 is None:
        r1 = r0
    a = Vector(p0)
    b = Vector(p1)
    axis = b - a
    if axis.length < 1e-7:
        return []
    zdir = axis.normalized()
    ref = Vector((1, 0, 0)) if abs(zdir.z) > 0.92 else Vector((0, 0, 1))
    xdir = ref.cross(zdir).normalized()
    ydir = zdir.cross(xdir).normalized()

    ring0, ring1 = [], []
    for k in range(segs):
        ang = 2.0 * math.pi * k / segs
        ca, sa = math.cos(ang), math.sin(ang)
        dir_r = xdir * ca + ydir * sa
        ring0.append(bm.verts.new(a + dir_r * r0))
        ring1.append(bm.verts.new(b + dir_r * r1))

    created = []
    for k in range(segs):
        kn = (k + 1) % segs
        created.append(bm.faces.new([ring0[k], ring0[kn], ring1[kn], ring1[k]]))
    if cap:
        if r0 > 1e-6:
            created.append(bm.faces.new(list(reversed(ring0))))
        if r1 > 1e-6:
            created.append(bm.faces.new(ring1))
    for f in created:
        f.material_index = mat_idx
    _apply_uv_rect_to_faces(bm, created)
    return ring0 + ring1


def add_closed_tube(bm, pts, r, segs=16, mat_idx=0):
    """Closed circumferential loop tube using parallel-transport framing (zero twist)."""
    return add_spline_tube(bm, pts, r, segs=segs, mat_idx=mat_idx, closed=True)


def add_torus_ring(bm, center, major_r, minor_r, major_segs=36, minor_segs=14,
                   axis=(0, 0, 1), mat_idx=0):
    """Zero-twist analytical torus ring aligned to `axis`."""
    zdir = Vector(axis).normalized()
    ref = Vector((1, 0, 0)) if abs(zdir.z) > 0.92 else Vector((0, 0, 1))
    xdir = ref.cross(zdir).normalized()
    ydir = zdir.cross(xdir).normalized()
    c = Vector(center)
    rings = []
    for i in range(major_segs):
        theta = 2.0 * math.pi * i / major_segs
        radial = xdir * math.cos(theta) + ydir * math.sin(theta)
        rc = c + radial * major_r
        ring = []
        for j in range(minor_segs):
            phi = 2.0 * math.pi * j / minor_segs
            pt = rc + (radial * math.cos(phi) + zdir * math.sin(phi)) * minor_r
            ring.append(bm.verts.new(pt))
        rings.append(ring)
    created = []
    for i in range(major_segs):
        inext = (i + 1) % major_segs
        for j in range(minor_segs):
            jnext = (j + 1) % minor_segs
            f = bm.faces.new([rings[i][j], rings[inext][j], rings[inext][jnext], rings[i][jnext]])
            f.material_index = mat_idx
            created.append(f)
    _apply_uv_rect_to_faces(bm, created)
    return [v for rg in rings for v in rg]


def _catmull_rom_spline(pvecs, rlist, substeps, closed=False):
    """Interpolate control points & radii using smooth cubic Catmull-Rom splines."""
    sub = max(1, int(substeps))
    if sub <= 1 or len(pvecs) < 2:
        return list(pvecs), list(rlist)
    if closed and len(pvecs) >= 3:
        pts_src = list(pvecs)
        r_src = list(rlist)
        if (pts_src[-1] - pts_src[0]).length < 1e-5:
            pts_src = pts_src[:-1]
            r_src = r_src[:-1]
        m = len(pts_src)
        if m >= 3:
            out_p, out_r = [], []
            for i in range(m):
                p0, p1, p2, p3 = pts_src[(i - 1) % m], pts_src[i], pts_src[(i + 1) % m], pts_src[(i + 2) % m]
                r1, r2 = r_src[i], r_src[(i + 1) % m]
                for s in range(sub):
                    t = s / sub
                    t2 = t * t
                    t3 = t2 * t
                    v = 0.5 * (
                        (2.0 * p1)
                        + (-p0 + p2) * t
                        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
                    )
                    out_p.append(v)
                    out_r.append(r1 + (r2 - r1) * t)
            return out_p, out_r

    ext_p = [pvecs[0] + (pvecs[0] - pvecs[1])] + list(pvecs) + [pvecs[-1] + (pvecs[-1] - pvecs[-2])]
    ext_r = [rlist[0]] + list(rlist) + [rlist[-1]]
    out_p, out_r = [], []
    for i in range(1, len(ext_p) - 2):
        p0, p1, p2, p3 = ext_p[i - 1], ext_p[i], ext_p[i + 1], ext_p[i + 2]
        r1, r2 = ext_r[i], ext_r[i + 1]
        n_s = sub if i < len(ext_p) - 3 else sub + 1
        for s in range(n_s):
            t = s / sub
            t2 = t * t
            t3 = t2 * t
            v = 0.5 * (
                (2.0 * p1)
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
            )
            out_p.append(v)
            out_r.append(r1 + (r2 - r1) * t)
    return out_p, out_r


def add_spline_tube(bm, pts, radii, segs=16, mat_idx=0, closed=False, cap_ends=True, *, substeps=1):
    """Sweep a circular profile along `pts` using a parallel-transport Bishop frame (with optional Catmull-Rom smoothing)."""
    pvecs = [Vector(p) for p in pts]
    if len(pvecs) < 2:
        return []
    if isinstance(radii, (int, float)):
        rlist = [float(radii)] * len(pvecs)
    else:
        rlist = [float(r) for r in radii]
    if substeps > 1:
        pvecs, rlist = _catmull_rom_spline(pvecs, rlist, substeps, closed=closed)
    n_pts = len(pvecs)
    if n_pts < 2:
        return []

    tangents = []
    for i in range(n_pts):
        if closed:
            t = pvecs[(i + 1) % n_pts] - pvecs[(i - 1) % n_pts]
        elif i == 0:
            t = pvecs[1] - pvecs[0]
        elif i == n_pts - 1:
            t = pvecs[-1] - pvecs[-2]
        else:
            t = pvecs[i + 1] - pvecs[i - 1]
        tangents.append(t.normalized() if t.length > 1e-8 else Vector((0, 0, 1)))

    t0 = tangents[0]
    ref = Vector((1, 0, 0)) if abs(t0.z) > 0.9 else Vector((0, 0, 1))
    nrm = ref.cross(t0).normalized()
    binrm = t0.cross(nrm).normalized()

    rings = []
    for i in range(n_pts):
        if i > 0:
            rot = tangents[i - 1].rotation_difference(tangents[i])
            nrm = (rot @ nrm).normalized()
            binrm = tangents[i].cross(nrm).normalized()
        rad = rlist[i]
        ring = []
        for k in range(segs):
            ang = 2.0 * math.pi * k / segs
            offset = (nrm * math.cos(ang) + binrm * math.sin(ang)) * rad
            ring.append(bm.verts.new(pvecs[i] + offset))
        rings.append(ring)

    created = []
    limit = n_pts if closed else n_pts - 1
    for i in range(limit):
        inext = (i + 1) % n_pts
        for k in range(segs):
            kn = (k + 1) % segs
            f = bm.faces.new([rings[i][k], rings[inext][k], rings[inext][kn], rings[i][kn]])
            f.material_index = mat_idx
            created.append(f)

    if not closed and cap_ends:
        if rlist[0] > 1e-6:
            f0 = bm.faces.new(list(reversed(rings[0])))
            f0.material_index = mat_idx
            created.append(f0)
        if rlist[-1] > 1e-6:
            f1 = bm.faces.new(rings[-1])
            f1.material_index = mat_idx
            created.append(f1)
    _apply_uv_rect_to_faces(bm, created)
    return [v for rg in rings for v in rg]


def add_revolved_profile(bm, profile_rz, segs=32, center=(0, 0, 0), axis=(0, 0, 1),
                         mat_idx=0, cap_poles=True):
    """Lathe a list of `(r, z)` points around `axis` with clean quad edge rings."""
    zdir = Vector(axis).normalized()
    ref = Vector((1, 0, 0)) if abs(zdir.z) > 0.92 else Vector((0, 0, 1))
    xdir = ref.cross(zdir).normalized()
    ydir = zdir.cross(xdir).normalized()
    c = Vector(center)

    rings = []
    for r, z in profile_rz:
        if r < 1e-6:
            rings.append([bm.verts.new(c + zdir * z)])
        else:
            rg = []
            for k in range(segs):
                ang = 2.0 * math.pi * k / segs
                rg.append(bm.verts.new(c + (xdir * math.cos(ang) + ydir * math.sin(ang)) * r + zdir * z))
            rings.append(rg)

    created = []
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        if len(r0) == 1 and len(r1) == segs:
            pole = r0[0]
            for k in range(segs):
                kn = (k + 1) % segs
                f = bm.faces.new([pole, r1[k], r1[kn]])
                f.material_index = mat_idx
                created.append(f)
        elif len(r0) == segs and len(r1) == 1:
            pole = r1[0]
            for k in range(segs):
                kn = (k + 1) % segs
                f = bm.faces.new([r0[k], pole, r0[kn]])
                f.material_index = mat_idx
                created.append(f)
        elif len(r0) == segs and len(r1) == segs:
            for k in range(segs):
                kn = (k + 1) % segs
                f = bm.faces.new([r0[k], r0[kn], r1[kn], r1[k]])
                f.material_index = mat_idx
                created.append(f)

    if cap_poles and len(rings[0]) == segs and profile_rz[0][0] > 1e-6:
        fb = bm.faces.new(list(reversed(rings[0])))
        fb.material_index = mat_idx
        created.append(fb)
    if cap_poles and len(rings[-1]) == segs and profile_rz[-1][0] > 1e-6:
        ft = bm.faces.new(rings[-1])
        ft.material_index = mat_idx
        created.append(ft)
    _apply_uv_rect_to_faces(bm, created)
    return [v for rg in rings for v in rg]


def add_revolved_ring(bm, center, r_inner, r_outer, height, segs=32, bevel=0.0, mat_idx=0, cap_rings=3):
    """Build a revolved disc (with concentric quad cap loops when `r_inner == 0`) or hollow collar."""
    hz = 0.5 * height
    b = min(bevel, max(0.0, 0.25 * height), max(0.0, 0.25 * (r_outer - r_inner)))
    if r_inner <= 1e-5:
        r_cap = (r_outer - b) if b > 1e-5 else r_outer
        n_rings = max(1, int(cap_rings))
        fracs = [0.28, 0.58, 0.84] if n_rings == 3 else [(k + 1) / (n_rings + 1) for k in range(n_rings)]
        bot_pts = [(0.0, -hz)] + [(r_cap * f, -hz) for f in fracs] + [(r_cap, -hz)]
        top_pts = [(r_cap, hz)] + [(r_cap * f, hz) for f in reversed(fracs)] + [(0.0, hz)]
        if b > 1e-5:
            mid_pts = [(r_outer, -hz + b), (r_outer, hz - b)]
        else:
            mid_pts = []
        prof = bot_pts + mid_pts + top_pts
        return add_revolved_profile(bm, prof, segs=segs, center=center, mat_idx=mat_idx, cap_poles=False)
    if b > 1e-5:
        prof = [
            (r_inner, -hz + b),
            (r_inner + b, -hz),
            (r_outer - b, -hz),
            (r_outer, -hz + b),
            (r_outer, hz - b),
            (r_outer - b, hz),
            (r_inner + b, hz),
            (r_inner, hz - b),
            (r_inner, -hz + b),
        ]
    else:
        prof = [
            (r_inner, -hz),
            (r_outer, -hz),
            (r_outer, hz),
            (r_inner, hz),
            (r_inner, -hz),
        ]
    return add_revolved_profile(bm, prof, segs=segs, center=center, mat_idx=mat_idx, cap_poles=False)


def add_quad_sphere(bm, center, radius=0.5, segs=24, rings=12, scale=(1, 1, 1), mat_idx=0):
    """Build a UV/quad-ring sphere (never icosphere) centered at `center`."""
    if isinstance(radius, (int, float)):
        rx = ry = rz = float(radius)
    else:
        rx, ry, rz = float(radius[0]), float(radius[1]), float(radius[2])
    rx *= scale[0]
    ry *= scale[1]
    rz *= scale[2]
    prof = [(0.0, -rz)]
    for i in range(1, rings):
        phi = -0.5 * math.pi + math.pi * i / rings
        r = math.cos(phi)
        z = math.sin(phi) * rz
        prof.append((r, z))
    prof.append((0.0, rz))

    c = Vector(center)
    v_rings = []
    for r, z in prof:
        if r < 1e-6:
            v_rings.append([bm.verts.new(c + Vector((0, 0, z)))])
        else:
            rg = []
            for k in range(segs):
                ang = 2.0 * math.pi * k / segs
                rg.append(bm.verts.new(c + Vector((r * math.cos(ang) * rx, r * math.sin(ang) * ry, z))))
            v_rings.append(rg)
    created = []
    for i in range(len(v_rings) - 1):
        r0, r1 = v_rings[i], v_rings[i + 1]
        if len(r0) == 1:
            for k in range(segs):
                created.append(bm.faces.new([r0[0], r1[(k + 1) % segs], r1[k]]))
        elif len(r1) == 1:
            for k in range(segs):
                created.append(bm.faces.new([r0[k], r0[(k + 1) % segs], r1[0]]))
        else:
            for k in range(segs):
                kn = (k + 1) % segs
                created.append(bm.faces.new([r0[k], r0[kn], r1[kn], r1[k]]))
    for f in created:
        f.material_index = mat_idx
    _apply_uv_rect_to_faces(bm, created)
    return [v for rg in v_rings for v in rg]


def add_mitered_frame(bm, center, width, height, bar_w=0.055, bar_d=0.038,
                      facing_axis="+Y", mat_idx=0):
    """Build a single-manifold 45-deg mitered picture/mirror frame centered on `center`."""
    hw, hh = 0.5 * width, 0.5 * height
    iw, ih = max(0.02, hw - bar_w), max(0.02, hh - bar_w)
    hd = 0.5 * bar_d
    # Local XY frame facing +Z, rotated afterward to match facing_axis
    outer_f = [(-hw, -hh, hd), (hw, -hh, hd), (hw, hh, hd), (-hw, hh, hd)]
    outer_b = [(-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd)]
    inner_f = [(-iw, -ih, hd), (iw, -ih, hd), (iw, ih, hd), (-iw, ih, hd)]
    inner_b = [(-iw, -ih, -hd), (iw, -ih, -hd), (iw, ih, -hd), (-iw, ih, -hd)]

    axis_map = {
        "+Y": Matrix.Rotation(-0.5 * math.pi, 3, "X"),
        "-Y": Matrix.Rotation(0.5 * math.pi, 3, "X"),
        "+X": Matrix.Rotation(0.5 * math.pi, 3, "Y"),
        "-X": Matrix.Rotation(-0.5 * math.pi, 3, "Y"),
        "+Z": Matrix.Identity(3),
    }
    rot = axis_map.get(facing_axis, Matrix.Rotation(-0.5 * math.pi, 3, "X"))
    c = Vector(center)

    def _mk(pts):
        return [bm.verts.new((rot @ Vector(p)) + c) for p in pts]

    vo_f, vo_b, vi_f, vi_b = _mk(outer_f), _mk(outer_b), _mk(inner_f), _mk(inner_b)
    created = []
    for k in range(4):
        kn = (k + 1) % 4
        created.append(bm.faces.new([vo_f[k], vo_f[kn], vi_f[kn], vi_f[k]]))
        created.append(bm.faces.new([vi_b[k], vi_b[kn], vo_b[kn], vo_b[k]]))
        created.append(bm.faces.new([vo_b[k], vo_b[kn], vo_f[kn], vo_f[k]]))
        created.append(bm.faces.new([vi_f[k], vi_f[kn], vi_b[kn], vi_b[k]]))
    for f in created:
        f.material_index = mat_idx
    _apply_uv_rect_to_faces(bm, created)
    return vo_f + vo_b + vi_f + vi_b


def add_uv_mapped_sign_plate(bm, center, width, height, thickness=0.015, facing_axis="+Y",
                             mat_front=0, mat_back=0, uv_rect=(0.0, 0.0, 1.0, 1.0),
                             graphic_uv_name="GraphicUV"):
    """Build a crisp Dual-UV plate with `(u0,v0,u1,v1)` mapped cleanly onto `GraphicUV`."""
    hw, hh, hd = 0.5 * width, 0.5 * height, 0.5 * thickness
    axis_map = {
        "+Y": Matrix.Rotation(-0.5 * math.pi, 3, "X"),
        "-Y": Matrix.Rotation(0.5 * math.pi, 3, "X"),
        "+X": Matrix.Rotation(0.5 * math.pi, 3, "Y"),
        "-X": Matrix.Rotation(-0.5 * math.pi, 3, "Y"),
        "+Z": Matrix.Identity(3),
    }
    rot = axis_map.get(facing_axis, Matrix.Rotation(-0.5 * math.pi, 3, "X"))
    c = Vector(center)
    f_pts = [(-hw, -hh, hd), (hw, -hh, hd), (hw, hh, hd), (-hw, hh, hd)]
    b_pts = [(-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd)]
    vf = [bm.verts.new((rot @ Vector(p)) + c) for p in f_pts]
    vb = [bm.verts.new((rot @ Vector(p)) + c) for p in b_pts]

    front = bm.faces.new(vf)
    front.material_index = mat_front
    back = bm.faces.new(list(reversed(vb)))
    back.material_index = mat_back
    sides = []
    for k in range(4):
        kn = (k + 1) % 4
        sf = bm.faces.new([vb[k], vb[kn], vf[kn], vf[k]])
        sf.material_index = mat_back
        sides.append(sf)

    uv_layer = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    guv_layer = bm.loops.layers.uv.get(graphic_uv_name) or bm.loops.layers.uv.new(graphic_uv_name)
    u0, v0, u1, v1 = uv_rect
    corners = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    for lp, (u, v) in zip(front.loops, corners):
        lp[uv_layer].uv = (u, v)
        lp[guv_layer].uv = (u, v)
    _apply_uv_rect_to_faces(bm, [back] + sides, "UVMap")
    return vf + vb


# ---------------------------------------------------------------------------
# Realistic 3D botanicals & architectural breeze blocks
# ---------------------------------------------------------------------------

def add_curved_leaf(bm, origin, direction, up_hint=(0, 0, 1), length=0.45, width=0.08,
                    droop=0.14, segs=6, mat_idx=0, thickness=0.0025):
    """Build a curved, slightly folded 3D botanical leaflet/frond blade with `>= 1.6 mm` thickness."""
    o = Vector(origin)
    fwd = Vector(direction).normalized()
    uh = Vector(up_hint).normalized()
    side = fwd.cross(uh)
    if side.length < 1e-6:
        side = fwd.cross(Vector((1, 0, 0)))
    side.normalize()
    up = side.cross(fwd).normalized()

    half_t = max(0.0009, 0.5 * thickness)
    top_rows, bot_rows = [], []
    for i in range(segs + 1):
        t = i / segs
        w = width * math.sin(math.pi * max(0.03, min(0.97, t * 0.92 + 0.04)))
        bend = droop * (t ** 1.8)
        spine = o + fwd * (length * t) - up * bend
        pts_c = [spine - side * w + up * (w * 0.14), spine, spine + side * w + up * (w * 0.14)]
        top_rows.append([bm.verts.new(p + up * half_t) for p in pts_c])
        bot_rows.append([bm.verts.new(p - up * half_t) for p in pts_c])

    created = []
    for i in range(segs):
        for c in range(2):
            created.append(bm.faces.new([top_rows[i][c], top_rows[i][c + 1], top_rows[i + 1][c + 1], top_rows[i + 1][c]]))
            created.append(bm.faces.new([bot_rows[i][c + 1], bot_rows[i][c], bot_rows[i + 1][c], bot_rows[i + 1][c + 1]]))
        created.append(bm.faces.new([top_rows[i][0], top_rows[i + 1][0], bot_rows[i + 1][0], bot_rows[i][0]]))
        created.append(bm.faces.new([bot_rows[i][2], bot_rows[i + 1][2], top_rows[i + 1][2], top_rows[i][2]]))
    for c in range(2):
        created.append(bm.faces.new([top_rows[0][c + 1], top_rows[0][c], bot_rows[0][c], bot_rows[0][c + 1]]))
        created.append(bm.faces.new([top_rows[-1][c], top_rows[-1][c + 1], bot_rows[-1][c + 1], bot_rows[-1][c]]))
    for f in created:
        f.material_index = mat_idx
    _apply_uv_rect_to_faces(bm, created)
    return [v for row in (top_rows + bot_rows) for v in row]


def add_bougainvillea_cluster(bm, center, radius=0.055, bract_mat_idx=0, stamen_mat_idx=0,
                              rot_euler=(0, 0, 0)):
    """Build a 3-bract papery bougainvillea cluster with tiny central stamen."""
    m = Euler(rot_euler, "XYZ").to_matrix()
    c = Vector(center)
    for k in range(3):
        ang = 2.0 * math.pi * k / 3.0
        local_dir = Vector((math.cos(ang), math.sin(ang), 0.35)).normalized()
        world_dir = (m @ local_dir).normalized()
        world_up = (m @ Vector((0, 0, 1))).normalized()
        stem_off = (m @ Vector((math.cos(ang) * radius * 0.22, math.sin(ang) * radius * 0.22, k * 0.003)))
        add_curved_leaf(
            bm, c + stem_off, world_dir, up_hint=world_up, length=radius * 1.05,
            width=radius * 0.62, droop=radius * 0.12, segs=3, mat_idx=bract_mat_idx, thickness=0.002,
        )
    add_quad_sphere(bm, c + (m @ Vector((0, 0, radius * 0.28))), radius=radius * 0.14,
                    segs=8, rings=4, mat_idx=stamen_mat_idx)


def add_breeze_block(bm, center, size=0.295, depth=0.10, facing_axis="+Y", mat_idx=0,
                     *, height=None, style="diamond", n_ring=24):
    """Build a manifold Art-Deco pierced concrete breeze block (`style='quatrefoil'` or `'diamond'`)."""
    axis_map = {
        "+Y": Matrix.Rotation(-0.5 * math.pi, 3, "X"),
        "-Y": Matrix.Rotation(0.5 * math.pi, 3, "X"),
        "+X": Matrix.Rotation(0.5 * math.pi, 3, "Y"),
        "-X": Matrix.Rotation(-0.5 * math.pi, 3, "Y"),
        "+Z": Matrix.Identity(3),
    }
    rot = axis_map.get(facing_axis, Matrix.Rotation(-0.5 * math.pi, 3, "X"))
    c = Vector(center)
    blk_w = float(size)
    blk_h = float(size if height is None else height)

    if str(style).lower() == "quatrefoil":
        hw = 0.5 * blk_w
        hh = 0.5 * blk_h
        hd = 0.5 * depth
        n_r = max(12, int(n_ring))
        outer_uv, inner_uv, inner_bev_uv = [], [], []
        for k in range(n_r):
            ang = (k / n_r) * math.tau
            ca, sa = math.cos(ang), math.sin(ang)
            s_box = min(hw / max(abs(ca), 1e-6), hh / max(abs(sa), 1e-6))
            outer_uv.append((ca * s_box, sa * s_box))
            lobe = abs(math.cos(2.0 * ang)) ** 1.45
            r_fac = 0.43 + 0.37 * lobe
            inner_uv.append((ca * hw * r_fac, sa * hh * r_fac))
            inner_bev_uv.append((ca * hw * min(0.92, r_fac + 0.055), sa * hh * min(0.92, r_fac + 0.055)))

        def _pt(u, v, w):
            return (rot @ Vector((u, v, w))) + c

        bev_d = min(0.012, depth * 0.14)
        vo_f = [bm.verts.new(_pt(u, v, +hd)) for u, v in outer_uv]
        vo_b = [bm.verts.new(_pt(u, v, -hd)) for u, v in outer_uv]
        vb_f = [bm.verts.new(_pt(u, v, +hd)) for u, v in inner_bev_uv]
        vb_b = [bm.verts.new(_pt(u, v, -hd)) for u, v in inner_bev_uv]
        vi_f = [bm.verts.new(_pt(u, v, +hd - bev_d)) for u, v in inner_uv]
        vi_b = [bm.verts.new(_pt(u, v, -hd + bev_d)) for u, v in inner_uv]

        faces = []
        for k in range(n_r):
            kn = (k + 1) % n_r
            faces.append(bm.faces.new((vo_f[k], vo_f[kn], vb_f[kn], vb_f[k])))
            faces.append(bm.faces.new((vb_f[k], vb_f[kn], vi_f[kn], vi_f[k])))
            faces.append(bm.faces.new((vo_b[kn], vo_b[k], vb_b[k], vb_b[kn])))
            faces.append(bm.faces.new((vb_b[kn], vb_b[k], vi_b[k], vi_b[kn])))
            faces.append(bm.faces.new((vo_b[k], vo_b[kn], vo_f[kn], vo_f[k])))
            faces.append(bm.faces.new((vi_f[k], vi_f[kn], vi_b[kn], vi_b[k])))
        for f in faces:
            f.material_index = mat_idx
        _apply_uv_rect_to_faces(bm, faces)
        return vo_f + vo_b + vb_f + vb_b + vi_f + vi_b

    hs = 0.5 * blk_w
    wall = max(0.022, blk_w * 0.13)
    in_r = hs - wall

    def _local_box(lx, ly, sx, sy, sz):
        bverts = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        for v in bverts:
            p = Vector((v.co.x * sx + lx, v.co.y * sy + ly, v.co.z * sz))
            v.co = (rot @ p) + c
        for v in bverts:
            for f in v.link_faces:
                f.material_index = mat_idx

    _local_box(0.0, hs - 0.5 * wall, blk_w, wall, depth)
    _local_box(0.0, -hs + 0.5 * wall, blk_w, wall, depth)
    _local_box(-hs + 0.5 * wall, 0.0, wall, blk_w - 2.0 * wall, depth)
    _local_box(hs - 0.5 * wall, 0.0, wall, blk_w - 2.0 * wall, depth)
    diag = in_r * 1.414
    for angle in (0.25 * math.pi, -0.25 * math.pi):
        m_d = rot @ Matrix.Rotation(angle, 3, "Z")
        bverts = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        for v in bverts:
            p = Vector((v.co.x * (diag * 1.32), v.co.y * (wall * 0.72), v.co.z * (depth * 0.85)))
            v.co = (m_d @ p) + c
        for v in bverts:
            for f in v.link_faces:
                f.material_index = mat_idx


# ---------------------------------------------------------------------------
# CAD bridge import, botanical de-confliction & instance-safe grounding
# ---------------------------------------------------------------------------

def import_cad_to_bmesh(glb_path, name, col, mats=None, asset_set=None):
    """Import a `cad_bridge.py` 1:1m GLB cleanly with outward signed volume & `FIXED` tris."""
    if not os.path.exists(glb_path):
        raise FileNotFoundError(f"CAD GLB not found: {glb_path}")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    imported = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bm = bmesh.new()
    for o in imported:
        me = o.data
        bm.from_mesh(me)
        bpy.data.objects.remove(o, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    return finalize_part(bm, name, col, mats=mats, smooth=True, auto_uv=True,
                         triangulate=True, asset_set=asset_set)


def deconflict_botanical_islands(bm, min_gap=0.008, iterations=4, max_step=0.015):
    """Separate overlapping leaf/petal islands via bounded non-oscillating impulse shifts."""
    bm.faces.ensure_lookup_table()
    if not bm.faces:
        return 0
    visited = set()
    islands = []
    for f in bm.faces:
        if f.index in visited:
            continue
        stack = [f]
        visited.add(f.index)
        iverts = set()
        while stack:
            cur = stack.pop()
            for v in cur.verts:
                iverts.add(v)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in visited:
                        visited.add(nf.index)
                        stack.append(nf)
        if iverts:
            islands.append(list(iverts))

    n = len(islands)
    if n < 2:
        return 0

    def _stats(vs):
        mn = Vector((min(v.co.x for v in vs), min(v.co.y for v in vs), min(v.co.z for v in vs)))
        mx = Vector((max(v.co.x for v in vs), max(v.co.y for v in vs), max(v.co.z for v in vs)))
        ctr = 0.5 * (mn + mx)
        rad = 0.5 * (mx - mn).length
        return ctr, rad

    resolved = 0
    for _ in range(iterations):
        boxes = [_stats(vs) for vs in islands]
        shifts = [Vector((0.0, 0.0, 0.0)) for _ in range(n)]
        moved = False
        for i in range(n):
            ci, ri = boxes[i]
            for j in range(i + 1, n):
                cj, rj = boxes[j]
                delta = ci - cj
                dist = delta.length
                need = 0.45 * (ri + rj) + min_gap
                if dist < need:
                    direction = delta.normalized() if dist > 1e-6 else Vector((0.0, 0.0, 1.0))
                    push = min(max_step, 0.35 * (need - dist))
                    shifts[i] += direction * push
                    shifts[j] -= direction * push
                    moved = True
                    resolved += 1
        if not moved:
            break
        for vs, sh in zip(islands, shifts):
            if sh.length > 1e-6:
                if sh.length > max_step:
                    sh = sh.normalized() * max_step
                for v in vs:
                    v.co += sh
    bm.normal_update()
    return resolved


def ground_objects_safe(objs, target_z=0.0):
    """Shift `objs` so global `min_z == target_z` WITHOUT multi-shifting shared `ob.data`."""
    meshes = [o for o in objs if o is not None and o.type == "MESH" and o.data is not None]
    if not meshes:
        return 0.0
    bpy.context.view_layer.update()
    min_z = min(
        (o.matrix_world @ v.co).z
        for o in meshes
        for v in o.data.vertices
    )
    dz = float(target_z) - min_z
    if abs(dz) < 1e-6:
        return 0.0

    seen_mesh_ptrs = set()
    for o in meshes:
        if o.get("vf_instanced") or o.data.users > 1 or o.location.length > 1e-5:
            o.location.z += dz
        else:
            ptr = o.data.as_pointer()
            if ptr not in seen_mesh_ptrs:
                seen_mesh_ptrs.add(ptr)
                for v in o.data.vertices:
                    v.co.z += dz
                o.data.update()
    bpy.context.view_layer.update()
    return dz
