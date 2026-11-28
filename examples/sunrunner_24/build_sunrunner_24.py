r"""Sunrunner 24 â€” 24 ft (7.32 m) Offshore Center-Console T-Top Boat Builder (v2 Realism Overhaul).

Combines precision B-Rep CAD marine hardware (`cad/*.glb` from `build_hardware_cad.py`)
with sculpted naval-architecture hull, Euro-transom motorwell, rounded glass-bridge helm console,
puffed piped upholstery, mandrel-bent T-Top, and 1:1 300HP V8 offshore outboard in Blender 5.2+.

Axes & Datum (sclib / Roblox BoatService convention):
    1 Blender unit = 1.0 meter
    +Y = Bow (forward)   -> Roblox LookVector (-Z)
    +X = Starboard       -> Roblox RightVector (+X)
    +Z = Up              -> Roblox UpVector (+Y)
    Z = 0.000 m          = Outboard skeg bottom tip (ground_z = 0.0000)
    Z = 0.380 m          = Hull aft keel baseline (aligned with outboard anti-ventilation plate!)
    Z = 0.715 m          = Calm ocean static waterline (BoatCenterAttachment)

Run headless:
    & "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --python-exit-code 1 -P assets\models\sunrunner_24\build_sunrunner_24.py -- --render-views
"""

from __future__ import annotations

import math
import os
import shutil
import sys
from collections import defaultdict

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
TOOLS_BLENDER = os.path.join(REPO_ROOT, "engine", "blender")
CAD_DIR = os.path.join(THIS_DIR, "cad")
EXPORT_DIR = os.path.join(THIS_DIR, "export")
RENDERS_DIR = os.path.join(THIS_DIR, "renders")
DESIGN_OUTPUT_DIR = core.DESIGN_OUTPUT_DIR

if TOOLS_BLENDER not in sys.path:
    sys.path.insert(0, TOOLS_BLENDER)

import sclib  # noqa: E402
from sclib import core, export, gameready, geo, mats, render  # noqa: E402

sclib.reload()

COLL_NAME = "Sunrunner24"

# True 24 ft (7.28 m) Carolina-flare offshore center-console naval dimensions (L/B = 2.64!)
Y_TRANSOM = -3.32
Y_BOW = 3.96
LOA = Y_BOW - Y_TRANSOM          # 7.28 m hull length (~8.55 m LOA w/ pulpit & 300HP V8 outboard)
MAX_HALF_BEAM = 1.380            # 2.76 m (9' 1") muscular offshore sportfisher beam!
TRANSOM_HALF_BEAM = 1.240        # Wide, stable Euro-transom stern
Z_KEEL_AFT = 0.410               # Hull keel baseline (aligned w/ outboard AV plate; skeg tip = 0.000!)
WATERLINE_Z = 0.740              # 0.33 m static hull draft
BOOT_TOP_Z = 0.780               # Crisp 4.0 cm horizontal navy waterline boot stripe
SOLE_Z = 0.885                   # Self-bailing cockpit sole (+14.5 cm above waterline -> wide 2.24 m floor!)
SHEER_STERN = 1.365              # Aft quarter freeboard height
SHEER_BOW = 1.915                # Proud +0.550 m sweeping Carolina bow sheer rise!
MOTORWELL_LIP_Z = 1.055          # 25.4" XL shaft notched Euro-transom height (1.055 - 0.410 = 0.645 m)


def smoothstep(a: float, b: float, x: float) -> float:
    if abs(b - a) < 1e-9:
        return 0.0 if x < a else 1.0
    u = max(0.0, min(1.0, (x - a) / (b - a)))
    return u * u * (3.0 - 2.0 * u)


# ---------------------------------------------------------------------------
# Naval Architecture Hull Equations (t in [0.0 .. 1.0], 0 = transom, 1 = bow)
# ---------------------------------------------------------------------------
def hull_y(t: float) -> float:
    return Y_TRANSOM + LOA * t


def hull_half_beam(t: float) -> float:
    # Pointed Carolina offshore planform: muscular aft/midship tapering into a razor-fine V-bow stem (9 mm half-width + sharp stem crease)!
    if t <= 0.52:
        u = t / 0.52
        return TRANSOM_HALF_BEAM + (MAX_HALF_BEAM - TRANSOM_HALF_BEAM) * (math.sin(u * math.pi * 0.5) ** 0.88)
    u = (t - 0.52) / 0.48
    fullness = max(0.0, 1.0 - (u**1.86)) ** 0.78
    return max(0.009, (MAX_HALF_BEAM - 0.009) * fullness + 0.009)


def hull_keel_z(t: float) -> float:
    if t <= 0.48:
        return Z_KEEL_AFT
    u = (t - 0.48) / 0.52
    # Sweeping offshore forefoot rising gracefully into the raked clipper stem!
    return Z_KEEL_AFT + 0.50 * (u**2.15)


def hull_sheer_z(t: float) -> float:
    # Classic sweeping Carolina S-sheer: low aft fishing cockpit sweeping boldly upward to a proud bow!
    aft_dip = -0.036 * math.sin(math.pi * min(1.0, t / 0.45)) if t < 0.45 else 0.0
    bow_rise = (SHEER_BOW - SHEER_STERN) * (smoothstep(0.12, 1.0, t) ** 1.32)
    return SHEER_STERN + aft_dip + bow_rise


def hull_chine_point(t: float) -> tuple[float, float, float]:
    """Return (chine_inner_x, chine_z, spray_flat_width) at station t."""
    sheer_b = hull_half_beam(t)
    kz = hull_keel_z(t)
    sz = hull_sheer_z(t)
    # Full offshore planing chine aft/midship (t <= 0.44), tucking smoothly forward into a razor V-bow!
    fb = smoothstep(0.42, 0.96, t)
    c_in = max(0.004, sheer_b * (0.89 - 0.58 * fb))
    # True 21-24 deg offshore planing deadrise through helm, twisting smoothly to 57 deg wave-piercing bow entry!
    deadrise_deg = 20.5 + 3.5 * min(1.0, t / 0.52) + 33.0 * (smoothstep(0.46, 0.98, t) ** 1.55)
    dz = c_in * math.tan(math.radians(deadrise_deg))
    cz_aft = max(kz + 0.08 * (1.0 - 0.85 * t) + 0.015, kz + dz)
    bow_chine_lift = Z_KEEL_AFT + 0.37 + 0.06 * t + 0.64 * (smoothstep(0.46, 1.0, t) ** 1.30)
    # Smooth C-infinity log-sum-exp transition between planing chine and sweeping bow chine (zero side-profile kink!)
    m_hi = max(cz_aft, bow_chine_lift)
    cz_smooth = m_hi + 0.032 * math.log(math.exp((cz_aft - m_hi) / 0.032) + math.exp((bow_chine_lift - m_hi) / 0.032))
    cz = min(sz - 0.24, cz_smooth)
    flat_w = max(0.003, 0.072 * (1.0 - 0.82 * fb) * (1.0 - 0.88 * (t**3)))
    return c_in, cz, flat_w


def hull_outer_profile(t: float) -> list[tuple[float, float]]:
    """Smooth 17-point half-section [(x, z), ...] from knife-edge deep-V keel (0) to flared sheer (16)."""
    kz = hull_keel_z(t)
    sz = hull_sheer_z(t)
    sheer_b = hull_half_beam(t)
    c_in, cz, flat_w = hull_chine_point(t)
    fb = smoothstep(0.28, 0.95, t)

    pts: list[tuple[float, float]] = []
    # 0..5: Crisp, slightly CONCAVE wave-slicing deep-V bottom (ZERO barrel belly!)
    n_bot = 5
    for i in range(n_bot + 1):
        u = i / n_bot
        x = c_in * u
        z = kz + (cz - kz) * (u + 0.048 * math.sin(math.pi * u))
        pts.append((x, z))

    # 6: Crisp horizontal reverse-chine spray-knocker ledge
    x_sp = min(sheer_b - 0.012 * (1.0 - t**3), c_in + flat_w)
    z_sp = cz + 0.008
    pts.append((x_sp, z_sp))

    # 7..16: Dense 10-segment concave topside flare -> zero flat facet panels on bow flare!
    n_top = 10
    for j in range(1, n_top + 1):
        v = j / n_top
        aft_prof = v**1.32
        fwd_prof = v**2.70
        prof = (1.0 - fb) * aft_prof + fb * fwd_prof
        x = max(x_sp + 0.0015 * v, x_sp + (sheer_b - x_sp) * prof)
        z = z_sp + (sz - z_sp) * v
        pts.append((x, z))

    # Subtle transom corner rounding across the aft 12 cm
    transom_r_t = 0.12 / LOA
    if t < transom_r_t:
        u = 1.0 - t / transom_r_t
        inset = 0.055 * (1.0 - math.sqrt(max(0.0, 1.0 - u * u)))
        sc = max(0.82, 1.0 - inset / max(sheer_b, 0.2))
        pts = [(x * sc, z) for (x, z) in pts]

    return pts


def hull_outer_x_at_z(t: float, z: float) -> float:
    pts = hull_outer_profile(t)
    if z <= pts[0][1]:
        return pts[0][0]
    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
        if z <= z1:
            u = (z - z0) / max(z1 - z0, 1e-6)
            return x0 + (x1 - x0) * u
    return pts[-1][0]


def hull_y_at_z(t: float, z: float) -> float:
    base = hull_y(t)
    kz = hull_keel_z(t)
    sz = hull_sheer_z(t)
    frac = max(0.0, min(1.0, (z - kz) / max(sz - kz, 0.10)))
    # Bold 37-deg Carolina clipper stem rake (+0.86 m) sweeping forward from forefoot to sheer + 12 deg transom rake
    bow_rake = 0.86 * (t**2.6) * (frac**1.12)
    stern_rake = 0.14 * ((1.0 - t) ** 18.0) * frac
    return base + bow_rake - stern_rake


def _t_for_y(y: float) -> float:
    return max(0.0, min(1.0, (y - Y_TRANSOM) / LOA))


def _exact_t_at_yz(y: float, z: float) -> float:
    """Invert hull_y_at_z(t, z) == y via fast 18-step bisection (accounts for bow & stern rake!)."""
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


def gunwale_inner_half_beam(t: float) -> float:
    sheer = hull_outer_profile(t)[-1][0]
    cap_w = 0.145 * (1.0 - 0.94 * (t**3.6))
    return max(0.004, min(sheer - 0.003, sheer - cap_w))


def _safe_inner_x(y: float, z: float, margin: float = 0.12) -> float:
    t = _exact_t_at_yz(y, z)
    return max(0.020, min(gunwale_inner_half_beam(t) - 0.025, hull_outer_x_at_z(t, z) - margin))


def _clean_poly2d(pts: list[tuple[float, float]], min_dist: float = 1.5e-3) -> list[tuple[float, float]]:
    """Deduplicate near-coincident consecutive points from filleted 2D polygons so lofts/caps stay manifold."""
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_dist:
            out.append((p[0], p[1]))
    if len(out) > 3 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < min_dist:
        out.pop()
    return out


# ---------------------------------------------------------------------------
# Geometry Finalization & Sculpted Marine Helpers
# ---------------------------------------------------------------------------
def _apply_baked_transform(ob: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    mw = ob.matrix_world.copy()
    if mw != Matrix.Identity(4):
        ob.data.transform(mw)
        if mw.determinant() < 0:
            ob.data.flip_normals()
        ob.location = (0.0, 0.0, 0.0)
        ob.rotation_euler = (0.0, 0.0, 0.0)
        ob.scale = (1.0, 1.0, 1.0)
        ob.matrix_world = Matrix.Identity(4)
        bpy.context.view_layer.update()
        ob.data.update()


def _fix_closed_island_volumes(bm: bmesh.types.BMesh) -> None:
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
            v1 = f.verts[k].co - o
            v2 = f.verts[k + 1].co - o
            vol[g] += v0.dot(v1.cross(v2)) / 6.0

    to_flip: list[bmesh.types.BMFace] = []
    for g, fs in faces_by_isl.items():
        if closed[g] and vol[g] < -1e-9:
            to_flip.extend(fs)
    if to_flip:
        bmesh.ops.reverse_faces(bm, faces=to_flip)


def _smart_uv_project(ob: bpy.types.Object) -> None:
    core.ensure_object_mode()
    if not ob.data.polygons:
        return
    if not ob.data.uv_layers:
        ob.data.uv_layers.new(name="UVMap")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.018)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        ob.select_set(False)

    # Fix any edge-on sliver face projected to zero UV area by smart_project
    uv_layer = ob.data.uv_layers.active
    if uv_layer is not None:
        verts = ob.data.vertices
        loops = ob.data.loops
        slot_k = 0
        for poly in ob.data.polygons:
            uvs = [uv_layer.data[li].uv for li in poly.loop_indices]
            def _tri_uv_area(a, b, c) -> float:
                return abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) * 0.5
            has_zero_tri = len(uvs) >= 3 and (
                any(_tri_uv_area(uvs[0], uvs[k], uvs[k + 1]) < 5e-9 for k in range(1, len(uvs) - 1))
                or (len(uvs) == 4 and (_tri_uv_area(uvs[0], uvs[1], uvs[3]) < 5e-9 or _tri_uv_area(uvs[1], uvs[2], uvs[3]) < 5e-9))
            )
            if has_zero_tri:
                m_l = len(poly.loop_indices)
                ox = 0.86 + 0.018 * (slot_k % 7)
                oy = 0.86 + 0.018 * ((slot_k // 7) % 7)
                slot_k += 1
                for idx_l, li in enumerate(poly.loop_indices):
                    ang_u = 2.0 * math.pi * idx_l / m_l
                    uv_layer.data[li].uv = (ox + 0.006 * math.cos(ang_u), oy + 0.006 * math.sin(ang_u))


def finalize_mesh(
    ob: bpy.types.Object,
    *,
    part: str,
    role: str = "solid",
    sharp_angle: float = 36.0,
    merge_dist: float = 1e-5,
    apply_modifiers: bool = True,
) -> bpy.types.Object:
    core.ensure_object_mode()
    if apply_modifiers and ob.modifiers:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        new_me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        old_me = ob.data
        new_me.name = old_me.name
        ob.modifiers.clear()
        ob.data = new_me
        if old_me.users == 0:
            bpy.data.meshes.remove(old_me)

    _apply_baked_transform(ob)

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    if merge_dist > 0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(merge_dist, 5e-5))
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)

    # Always triangulate n-gons LAST (never dissolve edges afterward, which can re-open n-gons/boundaries!)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="EAR_CLIP")

    loose_e = [e for e in bm.edges if not e.link_faces]
    if loose_e:
        bmesh.ops.delete(bm, geom=loose_e, context="EDGES")
    loose_v = [v for v in bm.verts if not v.link_faces]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    _fix_closed_island_volumes(bm)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    # Prune any unused material slots so qa_check never flags unused slots
    if len(ob.data.materials) > 1 and ob.data.polygons:
        used_slots = {p.material_index for p in ob.data.polygons}
        if len(used_slots) < len(ob.data.materials):
            old_mats = [m for m in ob.data.materials]
            kept = [old_mats[i] for i in sorted(used_slots) if i < len(old_mats)]
            remap = {old_i: new_i for new_i, old_i in enumerate(sorted(used_slots))}
            for p in ob.data.polygons:
                p.material_index = remap.get(p.material_index, 0)
            ob.data.materials.clear()
            for km in kept:
                ob.data.materials.append(km)

    geo.shade(ob, sharp_angle=sharp_angle)
    # Mark explicit razor-sharp centerline stem/keel, chine, sheer & transom creases on Hull_DeepV while keeping bow flare glass-smooth!
    if ob.name == "Hull_DeepV" and ob.data.edges:
        verts_co = ob.data.vertices
        sharp_attr = ob.data.attributes.get("sharp_edge")
        if sharp_attr is None:
            sharp_attr = ob.data.attributes.new(name="sharp_edge", type="BOOLEAN", domain="EDGE")
        for ei, ed in enumerate(ob.data.edges):
            v0, v1 = verts_co[ed.vertices[0]].co, verts_co[ed.vertices[1]].co
            if abs(v0.x) < 0.014 and abs(v1.x) < 0.014 and (v0.y > 0.5 or v0.z < WATERLINE_Z + 0.15):
                sharp_attr.data[ei].value = True
            else:
                # Crisp reverse-chine spray-knocker ledge crease along the entire hull!
                ym = 0.5 * (v0.y + v1.y)
                zm = 0.5 * (v0.z + v1.z)
                xm = 0.5 * (abs(v0.x) + abs(v1.x))
                tc = _exact_t_at_yz(ym, zm)
                cin, cz_c, fw_c = hull_chine_point(tc)
                if abs(zm - cz_c) < 0.022 and cin - 0.015 <= xm <= cin + fw_c + 0.018 and abs(v0.y - v1.y) > 0.02:
                    sharp_attr.data[ei].value = True

    # Bake Weighted Normals (keep_sharp=True) so planar walls & filleted radii render with zero blotchy shading!
    if len(ob.data.polygons) >= 4:
        wn = ob.modifiers.new("SC_WeightedNormal", "WEIGHTED_NORMAL")
        wn.keep_sharp = True
        wn.weight = 50
        dg_wn = bpy.context.evaluated_depsgraph_get()
        ev_wn = ob.evaluated_get(dg_wn)
        wn_me = bpy.data.meshes.new_from_object(ev_wn, preserve_all_data_layers=True, depsgraph=dg_wn)
        prev_me = ob.data
        wn_me.name = prev_me.name
        ob.modifiers.clear()
        ob.data = wn_me
        if prev_me.users == 0:
            bpy.data.meshes.remove(prev_me)
    _smart_uv_project(ob)
    core.tag(ob, part=part, role=role)
    return ob


def import_cad_part(
    filename: str,
    name: str,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    location=(0.0, 0.0, 0.0),
    rotation_deg=(0.0, 0.0, 0.0),
    scale=(1.0, 1.0, 1.0),
    part: str,
    role: str = "solid",
) -> bpy.types.Object:
    path = os.path.join(CAD_DIR, filename)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == "MESH"]
    for o in imported:
        if o not in meshes:
            bpy.data.objects.remove(o, do_unlink=True)
    if not meshes:
        raise RuntimeError(f"No mesh found inside CAD file {path}")

    ob = gameready.join(meshes, name) if len(meshes) > 1 else meshes[0]
    ob.name = name
    ob.data.name = name
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    col.objects.link(ob)

    ob.data.materials.clear()
    ob.data.materials.append(mat)
    ob.data.polygons.foreach_set("material_index", [0] * len(ob.data.polygons))
    ob.location = location
    ob.rotation_euler = Euler([math.radians(a) for a in rotation_deg], "XYZ")
    ob.scale = scale
    bpy.context.view_layer.update()
    return finalize_mesh(ob, part=part, role=role, sharp_angle=42.0)


def build_box(
    name: str,
    size: tuple[float, float, float],
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    location=(0.0, 0.0, 0.0),
    rotation_deg=(0.0, 0.0, 0.0),
    bevel: float = 0.008,
    segments: int = 2,
    part: str,
    role: str = "solid",
) -> bpy.types.Object:
    ob = geo.box(
        name,
        size,
        col,
        mat,
        location=location,
        rotation=tuple(math.radians(a) for a in rotation_deg),
        bevel=bevel,
        segments=segments,
        weighted=False,
    )
    return finalize_mesh(ob, part=part, role=role)


def build_prism(
    name: str,
    poly2d: list[tuple[float, float]],
    z0: float,
    z1: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    bevel: float = 0.008,
    taper: float | None = None,
    part: str,
    role: str = "solid",
    sharp_angle: float = 36.0,
) -> bpy.types.Object:
    clean_pts = _clean_poly2d(_ensure_ccw_2d(poly2d))
    ob = geo.prism(name, clean_pts, z0, z1, col, mat, taper=taper)
    if bevel > 0:
        geo.add_bevel(ob, bevel, segments=2, angle=32.0)
    return finalize_mesh(ob, part=part, role=role, sharp_angle=sharp_angle)


def build_hull_clamped_loft(
    name: str,
    poly2d: list[tuple[float, float]],
    z0: float,
    z1: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    margin: float = 0.075,
    bevel: float = 0.008,
    part: str,
    role: str = "solid",
    sharp_angle: float = 36.0,
) -> bpy.types.Object:
    """Loft a 2D planform from z0 to z1 while clamping every slice strictly inside the V-hull shell!"""
    clean_pts = _clean_poly2d(_ensure_ccw_2d(poly2d))
    rings: list[list[Vector]] = []
    for k in range(4):
        z = z0 + (z1 - z0) * (k / 3.0)
        ring: list[Vector] = []
        for px, py in clean_pts:
            t = _exact_t_at_yz(py, z)
            z_use = max(z, hull_keel_z(t) + 0.11)
            max_x = max(0.016, min(gunwale_inner_half_beam(t) - 0.022, hull_outer_x_at_z(t, z_use) - margin))
            cx = math.copysign(min(abs(px), max_x), px) if abs(px) > 1e-6 else 0.0
            ring.append(Vector((cx, py, z_use)))
        rings.append(ring)
    ob = geo.loft(name, rings, col, mat, closed=True, cap_start=True, cap_end=True, smooth=True, sharp_angle=sharp_angle, recalc=True)
    if bevel > 0:
        geo.add_bevel(ob, bevel, segments=2, angle=34.0)
    return finalize_mesh(ob, part=part, role=role, sharp_angle=sharp_angle)


def build_strut(
    name: str,
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    radius: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    seg: int = 16,
    radius2: float | None = None,
    part: str,
    role: str = "solid",
) -> bpy.types.Object:
    v1, v2 = Vector(p1), Vector(p2)
    diff = v2 - v1
    dist = diff.length
    mid = (v1 + v2) * 0.5
    quat = diff.normalized().to_track_quat("Z", "Y")
    ob = geo.cylinder(
        name,
        radius,
        dist,
        col,
        mat,
        location=mid,
        rotation=quat.to_euler("XYZ"),
        seg=seg,
        radius2=radius2,
    )
    return finalize_mesh(ob, part=part, role=role, sharp_angle=42.0)


def build_bent_pipe(
    name: str,
    pts: list[tuple[float, float, float]],
    radius: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    part: str,
    seg: int = 14,
    smooth_samples: int = 6,
    closed: bool = False,
    flange_start: bool = False,
    flange_end: bool = False,
) -> bpy.types.Object:
    """Smooth mandrel-bent marine pipe with optional circular mounting flange pucks (zero cap z-fighting)."""
    use_pts = list(pts)
    if not closed and len(use_pts) >= 2:
        if flange_start:
            p0, p1 = Vector(use_pts[0]), Vector(use_pts[1])
            d0 = (p1 - p0).normalized()
            use_pts[0] = tuple(p0 - d0 * 0.018)
        if flange_end:
            p_last, p_prev = Vector(use_pts[-1]), Vector(use_pts[-2])
            d_end = (p_prev - p_last).normalized()
            use_pts[-1] = tuple(p_last - d_end * 0.018)

    pipe = geo.tube(name, use_pts, radius, col, mat, seg=seg, smooth_samples=smooth_samples, cap=not closed, closed=closed)
    finalize_mesh(pipe, part=part, sharp_angle=45.0)

    if flange_start and len(pts) >= 2:
        p0, p1 = Vector(pts[0]), Vector(pts[1])
        d = (p1 - p0).normalized()
        fl = geo.cylinder(
            f"{name}_FlangeA",
            radius * 1.55,
            0.012,
            col,
            mat,
            location=p0 + d * 0.012,
            rotation=d.to_track_quat("Z", "Y").to_euler("XYZ"),
            seg=16,
            bevel=0.0025,
        )
        finalize_mesh(fl, part=part, sharp_angle=42.0)

    if flange_end and len(pts) >= 2:
        p_last, p_prev = Vector(pts[-1]), Vector(pts[-2])
        d = (p_prev - p_last).normalized()
        fl = geo.cylinder(
            f"{name}_FlangeB",
            radius * 1.55,
            0.012,
            col,
            mat,
            location=p_last + d * 0.012,
            rotation=d.to_track_quat("Z", "Y").to_euler("XYZ"),
            seg=16,
            bevel=0.0025,
        )
        finalize_mesh(fl, part=part, sharp_angle=42.0)

    return pipe


def se_ring_3d(
    cx: float,
    cy: float,
    cz: float,
    rx: float,
    ry_fwd: float,
    ry_aft: float,
    *,
    exp: float = 2.8,
    seg: int = 44,
) -> list[Vector]:
    """Asymmetric superellipse ring in XY at height cz (different fore/aft half-lengths & taper)."""
    pts: list[Vector] = []
    p_inv = 2.0 / exp
    for k in range(seg):
        ang = 2.0 * math.pi * k / seg
        ca, sa = math.cos(ang), math.sin(ang)
        sx = math.copysign(abs(ca) ** p_inv, ca)
        sy = math.copysign(abs(sa) ** p_inv, sa)
        ry = ry_fwd if sy >= 0.0 else ry_aft
        # Subtle automotive rear-quarter taper on aft half
        x_taper = 1.0 - 0.14 * max(0.0, -sy) ** 1.5
        pts.append(Vector((cx + rx * sx * x_taper, cy + ry * sy, cz)))
    return pts


def _ensure_ccw_2d(poly: list[tuple[float, float]]) -> list[tuple[float, float]]:
    area2 = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return poly if area2 >= 0.0 else list(reversed(poly))


def build_puffed_cushion(
    name: str,
    poly2d: list[tuple[float, float]],
    z_bot: float,
    z_top: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    *,
    part: str,
    piping_mat: bpy.types.Material | None = None,
    corner_r: float = 0.045,
    matrix: Matrix | None = None,
) -> bpy.types.Object:
    """Contoured marine upholstery cushion with crowned pillow profile & optional contrasting perimeter welt."""
    pts2d = _clean_poly2d(geo.fillet_poly(_clean_poly2d(_ensure_ccw_2d(poly2d), min_dist=6e-3), corner_r, seg=4), min_dist=6e-3)
    cx = sum(p[0] for p in pts2d) / len(pts2d)
    cy = sum(p[1] for p in pts2d) / len(pts2d)
    h = max(0.03, z_top - z_bot)
    xf = matrix or Matrix.Identity(4)

    def scaled_ring(scale_xy: float, z: float) -> list[Vector]:
        return [xf @ Vector((cx + (px - cx) * scale_xy, cy + (py - cy) * scale_xy, z)) for (px, py) in pts2d]

    rings = [
        scaled_ring(0.93, z_bot),
        scaled_ring(1.00, z_bot + h * 0.22),
        scaled_ring(1.015, z_bot + h * 0.58),
        scaled_ring(0.97, z_bot + h * 0.86),
        scaled_ring(0.86, z_top),
    ]
    cush = geo.loft(
        name,
        rings,
        col,
        mat,
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=52.0,
        recalc=True,
    )
    finalize_mesh(cush, part=part, sharp_angle=52.0)

    if piping_mat is not None:
        # Contrasting welt tube sits right in the upper cushion shoulder (overlaps cushion by ~3 mm -> never floats!)
        welt_pts = [xf @ Vector((cx + (px - cx) * 0.965, cy + (py - cy) * 0.965, z_bot + h * 0.86)) for (px, py) in pts2d]
        welt = geo.tube(f"{name}_Welt", welt_pts, 0.0065, col, piping_mat, seg=10, smooth_samples=0, closed=True)
        finalize_mesh(welt, part=part, sharp_angle=55.0)

    return cush


# ---------------------------------------------------------------------------
# Materials (Rich Marine Gelcoat, Anodized Metals, Teak, Upholstery, V8 Paint)
# ---------------------------------------------------------------------------
def create_materials() -> dict[str, bpy.types.Material]:
    m = {
        "hull_white": mats.pbr("SR_HullWhite", "#F5F7FA", roughness=0.15, coat=0.50),
        "hull_teal": mats.pbr("SR_HullTeal", "#0B556A", roughness=0.35, coat=0.04, specular=0.28, role="paint"),
        "boot_navy": mats.pbr("SR_BootNavy", "#146B85", roughness=0.20, coat=0.45),
        "antifoul": mats.pbr("SR_AntiFoul", "#1E242D", roughness=0.62),
        "nonskid": mats.pbr("SR_NonSkid", "#4C6075", roughness=0.90),
        "teak": mats.pbr("SR_Teak", "#826042", roughness=0.54, roblox_material="WoodPlanks"),
        "console_grey": mats.pbr("SR_ConsoleGrey", "#E8EDF2", roughness=0.24, coat=0.35),
        "dash_dark": mats.pbr("SR_DashDark", "#181D24", roughness=0.38),
        "screen_glow": mats.pbr(
            "SR_ScreenGlow",
            "#0E384D",
            roughness=0.08,
            emission="#26C6DA",
            emission_strength=0.75,
        ),
        "vinyl_white": mats.pbr("SR_VinylOyster", "#E3DACB", roughness=0.48),
        "vinyl_tan": mats.pbr("SR_VinylCamel", "#A8794E", roughness=0.48),
        "vinyl_slate": mats.pbr("SR_VinylSlate", "#232E3D", roughness=0.50),
        "rubber_black": mats.pbr("SR_RubberBlack", "#16191E", roughness=0.78),
        "aluminum": mats.pbr("SR_Aluminum", "#CFD8E2", roughness=0.22, metallic=0.88, roblox_material="Metal"),
        "stainless": mats.pbr("SR_Stainless", "#DCE3EC", roughness=0.15, metallic=0.94, roblox_material="Metal"),
        "prop_steel": mats.pbr("SR_PropStainless", "#BAC4D0", roughness=0.22, metallic=0.88, roblox_material="Metal"),
        "motor_cowl": mats.pbr("SR_MotorCowl", "#1D222A", roughness=0.28, metallic=0.32, coat=0.30),
        "motor_silver": mats.pbr("SR_MotorSilver", "#A5B1BF", roughness=0.22, metallic=0.84, coat=0.35),
        "glass": mats.pbr(
            "SR_WindshieldGlass",
            "#0B2536",
            roughness=0.03,
            coat=0.7,
            specular=0.92,
            transmission=0.0,
            alpha=0.22,
            role="glass",
            roblox_material="Glass",
        ),
        "nav_red": mats.pbr(
            "SR_NavRed",
            "#FF2424",
            roughness=0.15,
            emission="#FF2424",
            emission_strength=3.6,
            role="neon",
        ),
        "nav_green": mats.pbr(
            "SR_NavGreen",
            "#18E05A",
            roughness=0.15,
            emission="#18E05A",
            emission_strength=3.6,
            role="neon",
        ),
        "light_white": mats.pbr(
            "SR_LightWhite",
            "#FFF8EC",
            roughness=0.10,
            emission="#FFF8EC",
            emission_strength=7.5,
            role="neon",
        ),
    }
    # Subtle micro-pebble bump on nonskid & upholstery grain for Cycles close-ups
    mats.add_bump_noise(m["nonskid"], scale=220.0, strength=0.32, distance=0.004, detail=6.0)
    mats.add_bump_noise(m["vinyl_white"], scale=140.0, strength=0.05, distance=0.001, detail=3.0)
    return m


# ---------------------------------------------------------------------------
# 1. Hull, Recessed Motorwell, Horizontal Waterline, Strakes & Topside Paint
# ---------------------------------------------------------------------------
def _interior_liner_section(t: float) -> tuple[float, float, float, float]:
    """Return (x_shoulder, z_shoulder, x_well, z_center) for the molded interior liner at t."""
    sz = hull_sheer_z(t)
    kz = hull_keel_z(t)
    hb_in = gunwale_inner_half_beam(t)

    # Molded motorwell notch at transom (t=0..0.025) -> splashwell tray (t=0.03..0.09)
    # -> splashwell dam (t=0.10..0.125) -> flat cockpit sole (t=0.14..0.72) -> bow deck (t>0.74)
    if t <= 0.025:
        z_cen = MOTORWELL_LIP_Z - 0.015 * smoothstep(0.0, 0.025, t)
        x_well = 0.38
        z_sh = sz - 0.02
        x_sh = max(x_well + 0.08, min(hb_in - 0.02, 0.52))
    elif t <= 0.088:
        z_cen = 0.955
        x_well = 0.40 + 0.08 * smoothstep(0.025, 0.088, t)
        z_sh = sz - 0.06
        x_sh = max(x_well + 0.08, min(hb_in - 0.03, 0.62))
    elif t <= 0.145:
        # Rise over splashwell bulkhead dam then drop cleanly onto cockpit sole
        dam = math.sin(math.pi * smoothstep(0.088, 0.140, t))
        base_z = 0.955 + (SOLE_Z - 0.955) * smoothstep(0.088, 0.145, t)
        z_cen = base_z + 0.24 * dam
        x_well = 0.48 + 0.36 * smoothstep(0.088, 0.145, t)
        z_sh = 0.5 * (sz + z_cen)
        x_sh = hb_in - 0.04
    else:
        # Smooth continuous cockpit sole all the way to t=0.81 -> ZERO twisted quads / blotchy bow liner shading!
        sole_rise = (sz - 0.032 - SOLE_Z) * (smoothstep(0.81, 0.985, t) ** 1.25)
        z_cen = min(sz - 0.032, max(SOLE_Z + sole_rise, kz + 0.19))
        z_sh = max(z_cen + 0.035, sz - 0.28 * (1.0 - 0.80 * smoothstep(0.81, 0.985, t)))
        x_sh = hb_in - 0.03 * (1.0 - t**3)
        x_well = hb_in - 0.06 * (1.0 - 0.75 * t**3)

    # Strictly clamp interior points inside the outer hull skin (and >= 8 mm off centerline so zero stem self-contact!)
    stem_margin = 0.110 * (1.0 - 0.88 * smoothstep(0.88, 1.0, t))
    sh_margin = 0.095 * (1.0 - 0.88 * smoothstep(0.88, 1.0, t))
    max_x_cen = max(0.005, hull_outer_x_at_z(t, z_cen) - stem_margin)
    x_well = max(0.005, min(x_well, max_x_cen))
    max_x_sh = max(0.007, hull_outer_x_at_z(t, z_sh) - sh_margin)
    x_sh = max(x_well + 0.002, min(x_sh, max_x_sh, max(0.007, hb_in - 0.002)))
    return x_sh, z_sh, x_well, z_cen


def build_hull_and_stripe(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build 1-piece 96-station deep-V Carolina-flare Hull with knife-edge bow, horizontal waterline & strakes."""
    # Clean 96-station grid + transom/splashwell detail stations (no sub-2mm stem micro-slices -> zero foldover!)
    raw_ts = {round(i / 96.0, 6) for i in range(97)}
    for extra in (0.004, 0.009, 0.016, 0.025, 0.038, 0.088, 0.108, 0.125, 0.145):
        raw_ts.add(extra)
    ts = sorted(raw_ts)

    rings: list[list[Vector]] = []
    for t in ts:
        outer = hull_outer_profile(t)  # 17 points: 0=keel .. 16=sheer
        sz = outer[-1][1]
        hb_in = gunwale_inner_half_beam(t)
        x_sh, z_sh, x_well, z_cen = _interior_liner_section(t)

        # Starboard outer (0..16)
        stbd_outer = [Vector((x, hull_y_at_z(t, z), z)) for (x, z) in outer]
        # Subdivided 5-point interior liner wall per side â€” strictly monotonic & clamped inside outer flare!
        liner_m = 0.085 * (1.0 - 0.88 * smoothstep(0.88, 1.0, t))
        z_cen = min(sz - 0.048, z_cen)
        z_sh = max(z_cen + 0.022, min(sz - 0.024, z_sh))
        z_u = 0.55 * sz + 0.45 * z_sh
        z_l = 0.50 * z_sh + 0.50 * z_cen

        x_well = max(0.003, min(x_well, hb_in - 0.006, hull_outer_x_at_z(t, z_cen) - liner_m))
        x_sh = max(x_well + 0.0015, min(x_sh, hb_in - 0.003, hull_outer_x_at_z(t, z_sh) - liner_m))
        x_l = max(x_well + 0.0008, min(0.50 * (x_sh + x_well), x_sh - 0.0005, hull_outer_x_at_z(t, z_l) - liner_m))
        x_u = max(x_sh + 0.0008, min(0.55 * hb_in + 0.45 * x_sh, hb_in - 0.001, hull_outer_x_at_z(t, z_u) - liner_m))
        interior = [
            Vector((hb_in, hull_y_at_z(t, sz), sz)),                 # 17: stbd inner gunwale
            Vector((x_u, hull_y_at_z(t, z_u), z_u)),                 # 18: stbd upper liner wall
            Vector((x_sh, hull_y_at_z(t, z_sh), z_sh)),              # 19: stbd mid liner wall
            Vector((x_l, hull_y_at_z(t, z_l), z_l)),                 # 20: stbd lower liner cove
            Vector((x_well, hull_y_at_z(t, z_cen), z_cen)),          # 21: stbd sole / motorwell corner
            Vector((0.0, hull_y_at_z(t, z_cen), z_cen)),             # 22: centerline sole / motorwell lip
            Vector((-x_well, hull_y_at_z(t, z_cen), z_cen)),         # 23: port sole / motorwell corner
            Vector((-x_l, hull_y_at_z(t, z_l), z_l)),                # 24: port lower liner cove
            Vector((-x_sh, hull_y_at_z(t, z_sh), z_sh)),             # 25: port mid liner wall
            Vector((-x_u, hull_y_at_z(t, z_u), z_u)),                # 26: port upper liner wall
            Vector((-hb_in, hull_y_at_z(t, sz), sz)),                # 27: port inner gunwale
        ]
        # Port outer sheer -> near-keel (16 points: 28..43, skipping duplicate keel 0)
        port_outer = [Vector((-x, hull_y_at_z(t, z), z)) for (x, z) in reversed(outer[1:])]
        rings.append(stbd_outer + interior + port_outer)

    hull_mats = [m["hull_white"], m["antifoul"], m["boot_navy"], m["nonskid"]]

    def init_mat_fn(_ri: int, si: int) -> int:
        # Gunwale caps (16, 27) & flat cockpit sole floor (21, 22) get high-contrast medium-grey nonskid!
        if si in (16, 27, 21, 22):
            return 3
        return 0

    hull = geo.loft(
        "Hull_DeepV",
        rings,
        col,
        hull_mats,
        closed=True,
        cap_start=True,
        cap_end=True,
        mat_fn=init_mat_fn,
        cap_mat=(0, 0),
        smooth=True,
        sharp_angle=45.0,
        recalc=True,
    )

    # Slice true laser-horizontal waterline, white pinstripe reveal (+18mm), & contrasting teal boot-top (+58mm) across outer skin & transom!
    boot_lo = WATERLINE_Z + 0.018
    boot_hi = WATERLINE_Z + 0.058
    bm = bmesh.new()
    bm.from_mesh(hull.data)
    for z_cut in (WATERLINE_Z, boot_lo, boot_hi):
        geom_all = list(bm.verts) + list(bm.edges) + list(bm.faces)
        bmesh.ops.bisect_plane(
            bm,
            geom=geom_all,
            dist=1e-5,
            plane_co=Vector((0.0, 0.0, z_cut)),
            plane_no=Vector((0.0, 0.0, 1.0)),
            clear_inner=False,
            clear_outer=False,
        )
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=8e-4)
    bmesh.ops.dissolve_degenerate(bm, dist=8e-4, edges=bm.edges[:])

    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal
        t_c = _exact_t_at_yz(c.y, c.z)
        is_transom_outer = c.y < Y_TRANSOM + 0.05 and n.y < -0.55
        outer_w = hull_outer_x_at_z(t_c, c.z)
        is_side_or_bottom_skin = (not is_transom_outer) and (
            abs(c.x) >= outer_w - 0.045 and (n.z < 0.65 or abs(n.x) > 0.32 or n.y > 0.35)
        )
        if f.material_index == 3 and c.z > WATERLINE_Z + 0.08:
            continue  # preserve gunwale & cockpit sole nonskid
        if (is_side_or_bottom_skin or is_transom_outer) and c.z < WATERLINE_Z - 1e-4:
            f.material_index = 1  # full dark antifouling bottom INCLUDING submerged lower V-transom!
        elif (is_side_or_bottom_skin or is_transom_outer) and boot_lo - 1e-4 <= c.z <= boot_hi + 1e-4:
            f.material_index = 2  # crisp 4.0 cm Bahama-Teal boot-top stripe above 1.8 cm white waterline reveal!
        elif f.material_index != 3:
            f.material_index = 0

    bm.to_mesh(hull.data)
    bm.free()
    hull.data.update()
    finalize_mesh(hull, part="Hull", role="solid", sharp_angle=45.0)

    # Two pairs of bold sculpted V-bottom planing lifting strakes (strictly below WATERLINE_Z!)
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        for idx, (u_frac, t_end) in enumerate(((0.34, 0.56), (0.65, 0.64))):
            st_rings: list[list[Vector]] = []
            n_st = 28
            for k in range(n_st):
                t = 0.015 + (t_end - 0.015) * (k / (n_st - 1))
                c_in, cz, _fw = hull_chine_point(t)
                kz = hull_keel_z(t)
                u = u_frac
                x_base = c_in * u
                z_base = kz + (cz - kz) * (u + 0.048 * math.sin(math.pi * u))
                yb = hull_y_at_z(t, z_base)
                taper = math.sin(math.pi * min(1.0, k / 3.0) * 0.5) * math.sin(
                    math.pi * min(1.0, (n_st - 1 - k) / 5.0) * 0.5
                )
                drop = 0.038 * max(0.18, taper)
                wid = 0.042 * max(0.22, taper)
                st_rings.append([
                    Vector((sx * max(0.01, x_base - wid), yb, z_base + 0.014)),
                    Vector((sx * (x_base + wid * 0.8), yb, z_base + 0.016)),
                    Vector((sx * (x_base + wid * 0.75), yb, z_base - drop * 0.35)),
                    Vector((sx * x_base, yb, z_base - drop)),
                ])
            strake_mat = m["antifoul"]
            strake = geo.loft(
                f"Hull_LiftingStrake_{side}_{idx}",
                st_rings,
                col,
                strake_mat,
                closed=True,
                cap_start=True,
                cap_end=True,
                smooth=True,
                sharp_angle=32.0,
                recalc=True,
            )
            finalize_mesh(strake, part="Hull", sharp_angle=32.0)

    # Sleek sheer-parallel Deep Bahama Teal upper hull band wrapping from transom corner right up to the raked clipper stem!
    base_paint_ts = [t for t in ts if 0.004 <= t <= 0.980]
    for side_name, sx in (("Port", -1.0), ("Starboard", 1.0)):
        p_rings: list[list[Vector]] = []
        for idx_p, t_base in enumerate(base_paint_ts):
            is_bow_end = idx_p == len(base_paint_ts) - 1
            ring_outer: list[Vector] = []
            ring_inner: list[Vector] = []
            for kv in range(7):
                # Rake only the final bow termination station cleanly parallel to the stem!
                t = min(0.991, t_base + (0.011 * (kv / 6.0) if is_bow_end else 0.0))

                def _sec_at(tq: float) -> list[tuple[float, float]]:
                    oq = hull_outer_profile(tq)
                    tp = (oq[15][0] * 0.42 + oq[16][0] * 0.58, oq[15][1] * 0.42 + oq[16][1] * 0.58)
                    return [oq[10], oq[11], oq[12], oq[13], oq[14], oq[15], tp]

                sec_pts = _sec_at(t)
                xv, zv = sec_pts[kv]
                yv = hull_y_at_z(t, zv)
                p_surf = Vector((sx * xv, yv, zv))

                p_lo = sec_pts[max(0, kv - 1)]
                p_hi = sec_pts[min(6, kv + 1)]
                v_up = Vector((sx * (p_hi[0] - p_lo[0]), hull_y_at_z(t, p_hi[1]) - hull_y_at_z(t, p_lo[1]), max(1e-4, p_hi[1] - p_lo[1]))).normalized()
                # Longitudinal tangent MUST follow constant vertex index kv (NOT constant Z!) so normal matches Hull_DeepV's quad!
                dt = 0.006
                t_a, t_b = max(0.002, t - dt), min(0.992, t + dt)
                xa, za = _sec_at(t_a)[kv]
                xb_t, zb_t = _sec_at(t_b)[kv]
                v_fwd = Vector((sx * (xb_t - xa), hull_y_at_z(t_b, zb_t) - hull_y_at_z(t_a, za), zb_t - za)).normalized()
                n_out = (v_fwd.cross(v_up) if sx > 0 else v_up.cross(v_fwd)).normalized()
                if n_out.x * sx < 0:
                    n_out = -n_out
                ring_outer.append(p_surf + n_out * 0.0085)
                ring_inner.append(p_surf + n_out * 0.0040)
            p_rings.append(ring_outer + list(reversed(ring_inner)))

        panel = geo.loft(
            f"HullPaint_{side_name}",
            p_rings,
            col,
            m["hull_teal"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=34.0,
            recalc=True,
        )
        finalize_mesh(panel, part="PaintPrimary", role="paint", sharp_angle=34.0)


# ---------------------------------------------------------------------------
# 2. Cockpit Sole, Recessed Hatches, Coaming Bolsters, Bow U-Lounge & Swim Steps
# ---------------------------------------------------------------------------
def build_deck_and_seating(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build teak aft sole, molded non-skid walkways, fishbox hatches, bolsters, bow U-lounge & Euro swim steps."""
    # 1. Warm Burmese teak aft fighting-cockpit & helm sole inlay (strictly inside SOLE_Z hull envelope!)
    teak_ys = [-2.26, -1.75, -1.25, -0.78, -0.34]
    teak_stbd = [(_safe_inner_x(y, SOLE_Z, margin=0.14), y) for y in teak_ys]
    teak_port = [(-x, y) for (x, y) in reversed(teak_stbd)]
    build_prism(
        "Deck_TeakSole",
        geo.fillet_poly(_ensure_ccw_2d(teak_port + teak_stbd), 0.07, seg=3),
        SOLE_Z + 0.002,
        SOLE_Z + 0.012,
        col,
        m["teak"],
        bevel=0.003,
        part="Deck",
    )

    # Molded dove-grey diamond non-skid walkaround waterway panels (clamped strictly inside _safe_inner_x!)
    walk_ys = [-0.26, 0.08, 0.42, 0.72]
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        w_outer = [(sx * _safe_inner_x(y, SOLE_Z, margin=0.12), y) for y in walk_ys]
        w_inner = [(sx * min(0.50, _safe_inner_x(y, SOLE_Z, margin=0.12) - 0.08), y) for y in reversed(walk_ys)]
        build_prism(
            f"Deck_WalkwayNonSkid_{side}",
            geo.fillet_poly(_ensure_ccw_2d(w_outer + w_inner), 0.035, seg=3),
            SOLE_Z + 0.002,
            SOLE_Z + 0.011,
            col,
            m["nonskid"],
            bevel=0.003,
            part="Deck",
        )
    fwd_well_ys = [1.44, 1.95, 2.40]
    fw_stbd = [(min(0.26, _safe_inner_x(y, SOLE_Z, margin=0.12)), y) for y in fwd_well_ys]
    fw_port = [(-x, y) for (x, y) in reversed(fw_stbd)]
    build_prism(
        "Deck_FwdFootwellNonSkid",
        geo.fillet_poly(_ensure_ccw_2d(fw_port + fw_stbd), 0.035, seg=3),
        SOLE_Z + 0.002,
        SOLE_Z + 0.011,
        col,
        m["nonskid"],
        bevel=0.003,
        part="Deck",
    )

    # 2. Port & Starboard recessed macerated fishbox floor hatches + aft bilge hatch w/ stainless latches
    for side, sx in (("Port", -0.58), ("Starboard", 0.58)):
        hatch_poly = geo.rrect2d(0.30, 1.02, 0.04, seg=3)
        hatch_pts = [(px + sx, py - 1.56) for (px, py) in hatch_poly]
        build_prism(f"Deck_FishboxHatch_{side}", hatch_pts, SOLE_Z + 0.0045, SOLE_Z + 0.018, col, m["nonskid"], bevel=0.003, part="Deck")
        lat = geo.cylinder(f"Deck_FishboxLatch_{side}", 0.022, 0.018, col, m["stainless"], location=(sx, -1.12, SOLE_Z + 0.016), seg=16, bevel=0.002)
        finalize_mesh(lat, part="Deck")

    bilge_pts = [(px, py - 2.02) for (px, py) in geo.rrect2d(0.44, 0.34, 0.04, seg=3)]
    build_prism("Deck_BilgeHatch", bilge_pts, SOLE_Z + 0.0045, SOLE_Z + 0.018, col, m["nonskid"], bevel=0.003, part="Deck")

    # 3. Aft transom livewell / fold-down bench bulkhead (tapered strictly inside V-hull via build_hull_clamped_loft!)
    aft_wall_pts = [(px, py - 2.48) for (px, py) in geo.rrect2d(1.88, 0.34, 0.06, seg=4)]
    build_hull_clamped_loft("Deck_AftBulkhead", aft_wall_pts, SOLE_Z + 0.002, 1.21, col, m["hull_white"], margin=0.09, bevel=0.012, part="Deck")

    # Oval molded baitwell lid on starboard transom cap
    lw_pts = [(px + 0.72, py - 2.52) for (px, py) in geo.rrect2d(0.40, 0.28, 0.09, seg=4)]
    build_prism("Deck_LivewellLid", lw_pts, 1.20, 1.235, col, m["console_grey"], bevel=0.008, part="Deck")

    # Puffed aft bench seat + transom backrest bolster w/ contrasting slate piping
    aft_seat_poly = [(px, py - 2.34) for (px, py) in [(-0.74, -0.19), (0.74, -0.19), (0.74, 0.19), (-0.74, 0.19)]]
    build_puffed_cushion(
        "Deck_AftBenchCushion",
        aft_seat_poly,
        1.195,
        1.285,
        col,
        m["vinyl_white"],
        part="Deck",
        piping_mat=m["vinyl_slate"],
        corner_r=0.045,
    )
    aft_back_xf = Matrix.Translation((0.0, -2.56, 1.38)) @ Euler((math.radians(82.0), 0.0, 0.0), "XYZ").to_matrix().to_4x4()
    build_puffed_cushion(
        "Deck_AftBackrestBolster",
        [(-0.78, -0.09), (0.78, -0.09), (0.78, 0.09), (-0.78, 0.09)],
        -0.045,
        0.045,
        col,
        m["vinyl_white"],
        part="Deck",
        piping_mat=m["vinyl_slate"],
        corner_r=0.035,
        matrix=aft_back_xf,
    )

    # 4. Splashwell rigging boots (Port & Starboard) where outboard control looms enter hull
    for side, sx in (("Port", -0.18), ("Starboard", 0.18)):
        boot = geo.lathe(
            f"Deck_RiggingBoot_{side}",
            [(0.048, 0.0), (0.046, 0.015), (0.036, 0.032), (0.028, 0.052), (0.001, 0.056)],
            col,
            m["rubber_black"],
            seg=20,
            center=(sx, -3.02, 0.948),
            axis=(0.0, 0.0, 1.0),
            cap_start=True,
            cap_end=True,
        )
        finalize_mesh(boot, part="Deck")

    # 5. Full-length cockpit gunwale coaming bolsters (Port & Starboard) conforming strictly inside hull skin!
    coam_ts = [0.16, 0.28, 0.40, 0.52, 0.64]
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        c_rings: list[list[Vector]] = []
        for idx, t in enumerate(coam_ts):
            sz = hull_sheer_z(t)
            yb = hull_y_at_z(t, sz - 0.10)
            xb = gunwale_inner_half_beam(t)
            pad_thick = 0.042 if 0 < idx < len(coam_ts) - 1 else 0.026
            x_back_lo = min(xb + 0.018, hull_outer_x_at_z(t, sz - 0.21) - 0.045)
            x_back_hi = min(xb + 0.018, hull_outer_x_at_z(t, sz - 0.04) - 0.045)
            x_front = min(xb - pad_thick, x_back_lo - 0.032)
            c_rings.append([
                Vector((sx * x_back_lo, yb, sz - 0.21)),
                Vector((sx * x_front, yb, sz - 0.19)),
                Vector((sx * (x_front - 0.008), yb, sz - 0.12)),
                Vector((sx * x_front, yb, sz - 0.055)),
                Vector((sx * x_back_hi, yb, sz - 0.04)),
            ])
        coam = geo.loft(
            f"Deck_CoamingBolster_{side}",
            c_rings,
            col,
            m["vinyl_white"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=48.0,
            recalc=True,
        )
        finalize_mesh(coam, part="Deck", sharp_angle=48.0)

    # 6. Contoured Bow U-Seating Fiberglass Lockers (strictly clamped inside V-hull -> NEVER overrides _safe_inner_x!)
    bow_ys = [1.42, 1.78, 2.15, 2.52, 2.84]
    inner_xs = [0.36, 0.34, 0.28, 0.19, 0.09]
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        z_l_bot, z_l_top = SOLE_Z + 0.0045, 1.155
        bot_outer, bot_inner = [], []
        top_outer, top_inner = [], []
        for ix, y in zip(inner_xs, bow_ys):
            xo_b = _safe_inner_x(y, z_l_bot, margin=0.085)
            xi_b = min(ix, max(0.018, xo_b - 0.055))
            bot_outer.append((sx * xo_b, y))
            bot_inner.append((sx * xi_b, y))

            xo_t = _safe_inner_x(y, z_l_top, margin=0.085)
            xi_t = min(ix, max(0.022, xo_t - 0.065))
            top_outer.append((sx * xo_t, y))
            top_inner.append((sx * xi_t, y))

        bot_2d = _ensure_ccw_2d(bot_outer + list(reversed(bot_inner)))
        top_2d = _ensure_ccw_2d(top_outer + list(reversed(top_inner)))
        locker = geo.loft(
            f"Deck_BowLocker_{side}",
            [
                [Vector((px, py, z_l_bot)) for (px, py) in bot_2d],
                [Vector((px, py, z_l_top)) for (px, py) in top_2d],
            ],
            col,
            m["hull_white"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=36.0,
            recalc=True,
        )
        finalize_mesh(locker, part="Deck", sharp_angle=36.0)

        # Puffed bow lounge cushion with contrasting slate piping (strictly inside hull flare!)
        c_outer, c_inner = [], []
        for ix, y in zip(inner_xs, bow_ys):
            xo_c = _safe_inner_x(y, 1.15, margin=0.095)
            xi_c = min(ix + 0.012, max(0.025, xo_c - 0.060))
            c_outer.append((sx * xo_c, y))
            c_inner.append((sx * xi_c, y))
        build_puffed_cushion(
            f"Deck_BowCushion_{side}",
            c_outer + list(reversed(c_inner)),
            1.145,
            1.235,
            col,
            m["vinyl_white"],
            part="Deck",
            piping_mat=m["vinyl_slate"],
            corner_r=0.028,
        )

        # Wrap-around bow coaming bolster embedded cleanly into interior liner wall (strictly >= 45 mm inside outer hull!)
        b_rings: list[list[Vector]] = []
        bolster_ts = [k / 96.0 for k in range(62, 84, 2)]
        for idx, t in enumerate(bolster_ts):
            sz = hull_sheer_z(t)
            yb = hull_y_at_z(t, sz - 0.12)
            xb = gunwale_inner_half_beam(t)
            x_sh, z_sh, _xw, _zc = _interior_liner_section(t)
            _zc = min(sz - 0.048, _zc)
            z_sh = max(_zc + 0.022, min(sz - 0.024, z_sh))
            liner_m_b = 0.085 * (1.0 - 0.88 * smoothstep(0.88, 1.0, t))
            x_sh = min(x_sh, hb_in_t := xb, hull_outer_x_at_z(t, z_sh) - liner_m_b)
            z_u_b = 0.55 * sz + 0.45 * z_sh
            x_u_b = min(0.55 * hb_in_t + 0.45 * x_sh, hull_outer_x_at_z(t, z_u_b) - liner_m_b)

            def _liner_x_at_z(zq: float) -> float:
                if zq >= z_u_b:
                    u_l = max(0.0, min(1.0, (zq - z_u_b) / max(sz - z_u_b, 0.02)))
                    return x_u_b + (hb_in_t - x_u_b) * u_l
                u_l = max(0.0, min(1.0, (zq - z_sh) / max(z_u_b - z_sh, 0.02)))
                return x_sh + (x_u_b - x_sh) * u_l

            pt = 0.046 if 1 < idx < len(bolster_ts) - 2 else 0.032
            x_back_lo = max(0.06, min(_liner_x_at_z(sz - 0.21) + 0.012, hull_outer_x_at_z(t, sz - 0.21) - 0.045))
            x_back_hi = max(0.07, min(_liner_x_at_z(sz - 0.045) + 0.012, hull_outer_x_at_z(t, sz - 0.045) - 0.045))
            x_front = max(0.035, min(_liner_x_at_z(sz - 0.125) - pt, x_back_lo - 0.038))
            b_rings.append([
                Vector((sx * x_back_lo, yb, sz - 0.21)),
                Vector((sx * x_front, yb, sz - 0.190)),
                Vector((sx * max(0.030, x_front - 0.008), yb, sz - 0.125)),
                Vector((sx * x_front, yb, sz - 0.060)),
                Vector((sx * x_back_hi, yb, sz - 0.045)),
            ])
        bow_bolster = geo.loft(
            f"Deck_BowBolster_{side}",
            b_rings,
            col,
            m["vinyl_white"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=48.0,
            recalc=True,
        )
        finalize_mesh(bow_bolster, part="Deck", sharp_angle=48.0)

    # Molded center bow step locker + hull-clamped foredeck anchor bulkhead + center filler pad (stepped 27 mm below & overlapped cleanly -> zero z-fight!)
    center_step_poly = [(-0.215, 2.48), (0.215, 2.48), (0.115, 2.92), (-0.115, 2.92)]
    build_hull_clamped_loft("Deck_BowCenterStep", geo.fillet_poly(center_step_poly, 0.025, seg=3), 1.020, 1.128, col, m["hull_white"], margin=0.145, bevel=0.008, part="Deck")
    center_filler = [(-0.17, 2.50), (0.17, 2.50), (0.075, 2.83), (-0.075, 2.83)]
    build_puffed_cushion(
        "Deck_BowCenterCushion",
        center_filler,
        1.116,
        1.204,
        col,
        m["vinyl_white"],
        part="Deck",
        piping_mat=m["vinyl_slate"],
        corner_r=0.025,
    )

    # Hull-conforming foredeck anchor bulkhead (tapers inward cleanly with V-bow -> ZERO shell protrusion!)
    fb_ys = [2.85, 3.12, 3.38, 3.58]
    fb_stbd = [(_safe_inner_x(y, 1.38, margin=0.095), y) for y in fb_ys]
    fb_port = [(-x, y) for (x, y) in reversed(fb_stbd)]
    build_hull_clamped_loft(
        "Deck_ForedeckBulkhead",
        geo.fillet_poly(_ensure_ccw_2d(fb_port + fb_stbd), 0.03, seg=3),
        SOLE_Z + 0.04,
        1.395,
        col,
        m["hull_white"],
        margin=0.085,
        bevel=0.010,
        part="Deck",
    )

    anchor_hatch = [(-0.16, 2.94), (0.16, 2.94), (0.065, 3.50), (-0.065, 3.50)]
    z_ah = 1.395
    build_prism(
        "Deck_AnchorLockerHatch",
        geo.fillet_poly(anchor_hatch, 0.028, seg=3),
        z_ah - 0.025,
        z_ah + 0.016,
        col,
        m["nonskid"],
        bevel=0.005,
        part="Deck",
    )
    a_latch = geo.cylinder("Deck_AnchorLatch", 0.022, 0.018, col, m["stainless"], location=(0.0, 3.04, z_ah + 0.014), seg=18, bevel=0.002)
    finalize_mesh(a_latch, part="Deck")

    # 7. Smooth Molded 6-Slice Euro-Transom Swim Platforms (open air gap forward of V8 midsection leg in side profile!)
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        base_corners = _ensure_ccw_2d(
            [
                (sx * 0.54, Y_TRANSOM + 0.055),
                (sx * 1.10, Y_TRANSOM + 0.060),
                (sx * 1.03, Y_TRANSOM - 0.175),
                (sx * 0.56, Y_TRANSOM - 0.180),
            ]
        )
        filleted_top = _clean_poly2d(geo.fillet_poly(base_corners, [0.035, 0.04, 0.065, 0.060], seg=6))
        cx_p = sx * 0.80
        cy_p = Y_TRANSOM - 0.01
        swim_rings: list[list[Vector]] = []
        # Cosine-faired hull integration from z=0.735 up to z=0.910 -> zero jagged bottom edge!
        for frac_s, sc_x, sc_y, z_s in (
            (0.00, 0.58, 0.36, 0.740),
            (0.22, 0.76, 0.58, 0.775),
            (0.48, 0.90, 0.80, 0.822),
            (0.75, 0.98, 0.95, 0.870),
            (0.92, 1.00, 1.00, 0.900),
            (1.00, 0.985, 0.985, 0.912),
        ):
            _ = frac_s
            swim_rings.append(
                [Vector((cx_p + (px - cx_p) * sc_x, cy_p + (py - cy_p) * sc_y, z_s)) for (px, py) in filleted_top]
            )
        plat_ob = geo.loft(
            f"Deck_SwimPlatform_{side}",
            swim_rings,
            col,
            m["hull_white"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=52.0,
            recalc=True,
        )
        finalize_mesh(plat_ob, part="Deck", sharp_angle=52.0)

        # Molded dark rubber swim-platform perimeter bumper
        bumper_pts = [Vector((px, py, 0.892)) for (px, py) in filleted_top]
        bumper = geo.tube(f"Deck_SwimBumper_{side}", bumper_pts, 0.011, col, m["rubber_black"], seg=10, smooth_samples=0, closed=True)
        finalize_mesh(bumper, part="Deck", sharp_angle=55.0)

        teak_pts = [
            (sx * 0.61, Y_TRANSOM - 0.02),
            (sx * 1.00, Y_TRANSOM - 0.01),
            (sx * 0.96, Y_TRANSOM - 0.145),
            (sx * 0.62, Y_TRANSOM - 0.150),
        ]
        build_prism(
            f"Deck_SwimTeak_{side}",
            geo.fillet_poly(_ensure_ccw_2d(teak_pts), 0.05, seg=3),
            0.895,
            0.918,
            col,
            m["teak"],
            bevel=0.004,
            part="Deck",
        )


# ---------------------------------------------------------------------------
# 3. Sculpted Rounded Center Console, Glass-Bridge Dash, Gauges & Lounge Seat
# ---------------------------------------------------------------------------
def build_console_and_windshield(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build curved-front console, elevated glass-bridge dash (clear above wheel!), top-mount shelf & glass."""
    # 1. Recessed dark toe-kick plinth at cockpit sole (hull-clamped -> zero bottom shell breach!)
    plinth_pts = [(px, py + 0.22) for (px, py) in geo.rrect2d(0.88, 1.08, 0.14, seg=5)]
    build_hull_clamped_loft("Console_ToeKick", plinth_pts, SOLE_Z + 0.002, 0.955, col, m["dash_dark"], margin=0.09, bevel=0.008, part="Console")

    # 2. Contoured curved-front fiberglass console body (elevated upper electronics turret Z = 1.98 m!)
    def console_ring(w: float, l_aft: float, l_fwd: float, z: float, r_aft: float = 0.10, r_fwd: float = 0.22) -> list[Vector]:
        raw = [(-w * 0.5, l_aft), (w * 0.5, l_aft), (w * 0.46, l_fwd), (-w * 0.46, l_fwd)]
        pts = geo.fillet_poly(raw, [r_aft, r_aft, r_fwd, r_fwd], seg=5)
        return [Vector((px, py, z)) for (px, py) in pts]

    c_rings = [
        console_ring(0.98, -0.35, 0.84, 0.940, 0.11, 0.24),
        console_ring(0.98, -0.35, 0.84, 1.46, 0.11, 0.24),
        console_ring(0.95, -0.33, 0.80, 1.56, 0.10, 0.22),
        console_ring(0.88, -0.14, 0.70, 1.95, 0.09, 0.19),
        console_ring(0.82, -0.11, 0.66, 1.98, 0.08, 0.17),
    ]
    c_body = geo.loft(
        "Console_Body",
        c_rings,
        col,
        m["console_grey"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=40.0,
        recalc=True,
    )
    finalize_mesh(c_body, part="Console", sharp_angle=40.0)

    # 3. Overhanging anti-glare helm visor brow wrapping around the elevated electronics dash
    brow_pts = [(-0.45, -0.31), (-0.45, -0.08), (0.45, -0.08), (0.45, -0.31), (0.40, -0.33), (-0.40, -0.33)]
    build_prism(
        "Console_HelmVisorBrow",
        geo.fillet_poly(_ensure_ccw_2d(brow_pts), 0.04, seg=3),
        1.92,
        1.975,
        col,
        m["hull_white"],
        bevel=0.010,
        part="Console",
    )

    # 4. Elevated sloped carbon-black electronics dash panel (screens sit 100% ABOVE steering wheel rim!)
    up_v = Vector((0.0, 0.19, 0.39)).normalized()
    right_v = Vector((1.0, 0.0, 0.0))
    norm_v = right_v.cross(up_v).normalized()
    panel_rot_m = Matrix((right_v, up_v, norm_v)).transposed()
    panel_euler = panel_rot_m.to_euler("XYZ")
    panel_euler_deg = tuple(math.degrees(a) for a in panel_euler)
    panel_origin = Vector((0.0, -0.235, 1.775))

    def dash_elem_box(name: str, u: float, v: float, w: float, h: float, d: float, lift: float, mat, bevel: float = 0.004, role: str = "solid"):
        loc = panel_origin + right_v * u + up_v * v + norm_v * lift
        return build_box(name, (w, h, d), col, mat, location=loc, rotation_deg=panel_euler_deg, bevel=bevel, part="Console", role=role)

    # Dark anodized glass-bridge backing plate (embedded 12 mm into Console_Body)
    dash_elem_box("Console_DashPlate", 0.0, 0.0, 0.82, 0.33, 0.024, 0.002, m["dash_dark"], bevel=0.006)

    # Twin flush 12" Garmin/Simrad MFD Chartplotter displays (raised cleanly above wheel!)
    for idx, ux in enumerate((-0.22, 0.085)):
        dash_elem_box(f"Console_MFDBezel_{idx}", ux, -0.015, 0.268, 0.172, 0.018, 0.012, m["rubber_black"], bevel=0.004)
        dash_elem_box(f"Console_MFDScreen_{idx}", ux, -0.015, 0.240, 0.145, 0.012, 0.018, m["screen_glow"], bevel=0.002)
        knob_loc = panel_origin + right_v * (ux + 0.120) + up_v * (-0.055) + norm_v * 0.018
        kn = geo.cylinder(f"Console_MFDKnob_{idx}", 0.009, 0.020, col, m["stainless"], location=knob_loc, rotation=panel_euler, seg=14, bevel=0.002)
        finalize_mesh(kn, part="Console")

    # 3 Round Analog/Digital Engine Gauge Pods along upper dash row
    for g_idx, ux in enumerate((-0.28, -0.17, -0.06)):
        g_loc = panel_origin + right_v * ux + up_v * 0.115 + norm_v * 0.014
        pod = geo.cylinder(f"Console_GaugePod_{g_idx}", 0.036, 0.020, col, m["rubber_black"], location=g_loc, rotation=panel_euler, seg=24, bevel=0.003)
        finalize_mesh(pod, part="Console")
        bez = geo.torus(
            f"Console_GaugeBezel_{g_idx}",
            0.033,
            0.0045,
            col,
            m["stainless"],
            center=g_loc + norm_v * 0.010,
            axis=norm_v,
            seg=24,
            rseg=10,
        )
        finalize_mesh(bez, part="Console")
        dial = geo.cylinder(f"Console_GaugeDial_{g_idx}", 0.029, 0.008, col, m["dash_dark"], location=g_loc + norm_v * 0.009, rotation=panel_euler, seg=20)
        finalize_mesh(dial, part="Console")
        needle_ang = math.radians(-35.0 + g_idx * 32.0)
        n_dir = right_v * math.cos(needle_ang) + up_v * math.sin(needle_ang)
        build_strut(
            f"Console_GaugeNeedle_{g_idx}",
            tuple(g_loc + norm_v * 0.014 - n_dir * 0.005),
            tuple(g_loc + norm_v * 0.014 + n_dir * 0.020),
            0.0022,
            col,
            m["hull_white"],
            seg=8,
            part="Console",
        )

    # Flush VHF Marine Radio + Coiled Microphone Cord on Starboard upper dash
    dash_elem_box("Console_VHFRadio", 0.315, 0.065, 0.115, 0.075, 0.018, 0.012, m["rubber_black"], bevel=0.004)
    dash_elem_box("Console_VHFScreen", 0.305, 0.070, 0.064, 0.034, 0.012, 0.018, m["screen_glow"], bevel=0.002)
    dash_elem_box("Console_VHFMicHandset", 0.345, -0.045, 0.044, 0.068, 0.026, 0.020, m["rubber_black"], bevel=0.008)

    cord_start = panel_origin + right_v * 0.275 + up_v * 0.040 + norm_v * 0.018
    cord_end = panel_origin + right_v * 0.345 + up_v * (-0.072) + norm_v * 0.022
    coil_pts: list[tuple[float, float, float]] = [tuple(cord_start - norm_v * 0.010)]
    n_coil = 44
    for k in range(n_coil + 1):
        u = k / n_coil
        sag = Vector((0.0, 0.0, -0.065 * math.sin(math.pi * u))) + norm_v * (0.022 * math.sin(math.pi * u))
        base_p = cord_start.lerp(cord_end, u) + sag
        env = math.sin(math.pi * u)
        ang = u * 9.0 * 2.0 * math.pi
        rad = 0.009 * env
        offset = right_v * (rad * math.cos(ang)) + norm_v * (rad * math.sin(ang))
        coil_pts.append(tuple(base_p + offset))
    coil_pts.append(tuple(cord_end - norm_v * 0.012))
    cord = geo.tube("Console_VHFCord", coil_pts, 0.0038, col, m["rubber_black"], seg=8, smooth_samples=0)
    finalize_mesh(cord, part="Console", sharp_angle=55.0)

    # Backlit 8-Gang Stainless Push-Button Switch Bank below MFDs
    dash_elem_box("Console_SwitchPanel", 0.09, -0.132, 0.32, 0.036, 0.014, 0.010, m["aluminum"], bevel=0.003)
    for sw_i in range(8):
        sw_u = -0.045 + sw_i * 0.038
        sw_loc = panel_origin + right_v * sw_u + up_v * (-0.132) + norm_v * 0.015
        sw = geo.cylinder(f"Console_PushBtn_{sw_i}", 0.0072, 0.020, col, m["stainless"], location=sw_loc, rotation=panel_euler, seg=12, bevel=0.0015)
        finalize_mesh(sw, part="Console")

    # 5. Deep Flat Horizontal Helm Control Shelf (Z = 1.39 .. 1.47 m) for Wheel Pod & Top-Mount Binnacle!
    helm_ledge = [(px, py - 0.40) for (px, py) in geo.rrect2d(0.92, 0.34, 0.07, seg=4)]
    build_prism("Console_HelmLedge", helm_ledge, 1.39, 1.472, col, m["console_grey"], bevel=0.014, part="Console")
    # Starboard raised dark binnacle mounting plinth on the horizontal shelf
    binn_pad = [(px + 0.235, py - 0.435) for (px, py) in geo.rrect2d(0.145, 0.22, 0.035, seg=4)]
    build_prism("Console_BinnaclePad", binn_pad, 1.462, 1.488, col, m["dash_dark"], bevel=0.005, part="Console")

    # Sculpted fiberglass helm pod + stainless tilt bezel set port-of-center (X = -0.20, Z = 1.565 -> clears backrest & MFDs!)
    pod_base = (-0.20, -0.40, 1.462)
    pod_tip = (-0.20, -0.515, 1.565)
    build_strut("Console_HelmPod", pod_base, pod_tip, 0.054, col, m["dash_dark"], seg=24, radius2=0.040, part="Console")
    build_strut("Console_HelmShaft", (-0.20, -0.50, 1.560), (-0.20, -0.550, 1.586), 0.024, col, m["stainless"], seg=18, part="Console")

    # Ignition Key / Emergency Kill-Lanyard Panel below helm shelf
    build_box("Console_IgnitionPanel", (0.14, 0.025, 0.085), col, m["dash_dark"], location=(-0.01, -0.352, 1.31), bevel=0.004, part="Console")
    kill_sw = geo.cylinder("Console_KillSwitch", 0.012, 0.018, col, m["nav_red"], location=(0.02, -0.362, 1.31), rotation=(math.radians(90.0), 0.0, 0.0), seg=14)
    finalize_mesh(kill_sw, part="Console")

    # Top Dash Ritchie Offshore Compass Dome + 2 Recessed Stainless Drink Cupholders (at elevated Z = 1.98 m!)
    comp_base = geo.cylinder("Console_CompassBase", 0.062, 0.026, col, m["rubber_black"], location=(-0.19, 0.08, 1.985), seg=24, bevel=0.004)
    finalize_mesh(comp_base, part="Console")
    comp_dome = geo.sphere("Console_CompassDome", 0.048, col, m["dash_dark"], location=(-0.19, 0.08, 1.998), scale=(1.0, 1.0, 0.82), seg=24, rings=12)
    finalize_mesh(comp_dome, part="Console")

    for side, cx in (("Port", -0.34), ("Starboard", 0.34)):
        ch = geo.torus(f"Console_Cupholder_{side}", 0.044, 0.006, col, m["stainless"], center=(cx, 0.06, 1.978), axis=(0.0, 0.0, 1.0), seg=24, rseg=10)
        finalize_mesh(ch, part="Console")
        ch_well = geo.cylinder(f"Console_CupWell_{side}", 0.040, 0.020, col, m["rubber_black"], location=(cx, 0.06, 1.972), seg=20)
        finalize_mesh(ch_well, part="Console")

    # Lower console recessed footrest alcove + angled teak footrest + Port cabin access door w/ latch
    build_box("Console_GloveDoor", (0.52, 0.026, 0.30), col, m["hull_white"], location=(0.0, -0.352, 1.13), bevel=0.006, part="Console")
    g_latch = geo.cylinder("Console_GloveLatch", 0.018, 0.016, col, m["stainless"], location=(0.20, -0.364, 1.17), rotation=(math.radians(90.0), 0.0, 0.0), seg=16)
    finalize_mesh(g_latch, part="Console")

    build_box(
        "Console_FootrestPad",
        (0.66, 0.18, 0.036),
        col,
        m["teak"],
        location=(0.0, -0.37, 0.99),
        rotation_deg=(26.0, 0.0, 0.0),
        bevel=0.006,
        part="Console",
    )

    # Port-side head access door + stainless Southco latch centered cleanly between T-Top forward & aft legs!
    build_box("Console_SideDoor", (0.048, 0.46, 0.55), col, m["hull_white"], location=(-0.476, 0.14, 1.255), bevel=0.006, part="Console")
    s_latch = geo.cylinder("Console_SideDoorLatch", 0.020, 0.022, col, m["stainless"], location=(-0.504, 0.30, 1.28), rotation=(0.0, math.radians(90.0), 0.0), seg=16)
    finalize_mesh(s_latch, part="Console")

    # 6. Contoured Forward Console Lounge Seat + Puffed Piped Cushions (hull-clamped -> zero bottom shell breach!)
    fwd_seat_plan = [(-0.42, 0.78), (0.42, 0.78), (0.39, 1.34), (-0.39, 1.34)]
    build_hull_clamped_loft(
        "Console_FwdLoungeBase",
        geo.fillet_poly(fwd_seat_plan, 0.12, seg=5),
        SOLE_Z + 0.002,
        1.19,
        col,
        m["hull_white"],
        margin=0.085,
        bevel=0.012,
        part="Console",
    )
    build_puffed_cushion(
        "Console_FwdLoungeCushion",
        [(-0.40, 0.82), (0.40, 0.82), (0.37, 1.32), (-0.37, 1.32)],
        1.178,
        1.275,
        col,
        m["vinyl_white"],
        part="Console",
        piping_mat=m["vinyl_slate"],
        corner_r=0.085,
    )
    fwd_back_xf = Matrix.Translation((0.0, 0.835, 1.54)) @ Euler((math.radians(-98.0), 0.0, 0.0), "XYZ").to_matrix().to_4x4()
    build_puffed_cushion(
        "Console_FwdLoungeBackrest",
        [(-0.37, -0.24), (0.37, -0.24), (0.35, 0.24), (-0.35, 0.24)],
        -0.045,
        0.048,
        col,
        m["vinyl_white"],
        part="Console",
        piping_mat=m["vinyl_slate"],
        corner_r=0.065,
        matrix=fwd_back_xf,
    )

    # 7. Curved Smoked Acrylic Windshield (Glass, Z = 1.98 .. 2.34 m) + Rubber Gasket + Bent Stainless Grab Rail
    raw_u = [
        (-0.40, -0.04),
        (-0.40, 0.26),
        (-0.37, 0.54),
        (-0.24, 0.65),
        (0.0, 0.67),
        (0.24, 0.65),
        (0.37, 0.54),
        (0.40, 0.26),
        (0.40, -0.04),
    ]
    smooth_u = geo.catmull_rom([Vector((x, y, 0.0)) for (x, y) in raw_u], samples=4, closed=False)

    gasket_pts = [(p.x, p.y, 1.986) for p in smooth_u]
    gasket = geo.sweep(
        "Console_WindshieldGasket",
        gasket_pts,
        geo.rrect2d(0.028, 0.026, 0.006, seg=2),
        col,
        m["rubber_black"],
        closed_profile=True,
        closed_path=False,
    )
    finalize_mesh(gasket, part="Console", sharp_angle=42.0)

    bot_out, bot_in, top_out, top_in = [], [], [], []
    n_u = len(smooth_u)
    for i, p in enumerate(smooth_u):
        p_prev = smooth_u[max(0, i - 1)]
        p_next = smooth_u[min(n_u - 1, i + 1)]
        tang = (p_next - p_prev).normalized()
        n_out = Vector((-tang.y, tang.x, 0.0))
        u_sym = abs((i / (n_u - 1)) * 2.0 - 1.0)
        z_top = 2.34 - 0.25 * (u_sym**2.2)
        rake_y = -0.11 * (1.0 - 0.55 * (u_sym**2))
        inw_x = 0.93 + 0.05 * (u_sym**2)
        bot_out.append(Vector((p.x + n_out.x * 0.006, p.y + n_out.y * 0.006, 1.982)))
        bot_in.append(Vector((p.x - n_out.x * 0.006, p.y - n_out.y * 0.006, 1.982)))
        top_out.append(Vector((p.x * inw_x + n_out.x * 0.006, p.y + rake_y + n_out.y * 0.006, z_top)))
        top_in.append(Vector((p.x * inw_x - n_out.x * 0.006, p.y + rake_y - n_out.y * 0.006, z_top)))

    w_glass = geo.loft(
        "Console_WindshieldGlass",
        [bot_out + list(reversed(bot_in)), top_out + list(reversed(top_in))],
        col,
        m["glass"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=35.0,
        recalc=True,
    )
    finalize_mesh(w_glass, part="Glass", role="glass", sharp_angle=35.0)

    rail_pts = [
        (-0.34, -0.03, 1.972),
        (-0.35, -0.03, 2.13),
        (-0.33, 0.46, 2.31),
        (0.0, 0.53, 2.37),
        (0.33, 0.46, 2.31),
        (0.35, -0.03, 2.13),
        (0.34, -0.03, 1.972),
    ]
    build_bent_pipe(
        "Console_WindshieldGrabRail",
        rail_pts,
        0.014,
        col,
        m["stainless"],
        part="Console",
        smooth_samples=6,
        flange_start=True,
        flange_end=True,
    )


# ---------------------------------------------------------------------------
# 4. Offshore Leaning Post, Bolster Seats, Rod Holders & Tundra Cooler
# ---------------------------------------------------------------------------
def build_leaning_post(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build mandrel-bent aluminum leaning post, flip-up piped bolsters, 4 rod holders & cooler."""
    # 1. Mandrel-bent side leg hoops rising from bolted oval anodized deck mounting plates!
    for side, sx in (("Port", -0.43), ("Starboard", 0.43)):
        for lbl, ly in (("Fwd", -0.84), ("Aft", -1.24)):
            foot_pts = [(px + sx, py + ly) for (px, py) in geo.rrect2d(0.095, 0.115, 0.03, seg=3)]
            build_prism(f"Leaning_DeckFoot_{lbl}_{side}", foot_pts, SOLE_Z + 0.0068, SOLE_Z + 0.023, col, m["aluminum"], bevel=0.004, part="LeaningPost")
        build_bent_pipe(
            f"Leaning_FwdLeg_{side}",
            [(sx, -0.84, SOLE_Z + 0.012), (sx, -0.85, 1.02), (sx, -0.88, 1.32)],
            0.022,
            col,
            m["aluminum"],
            part="LeaningPost",
            smooth_samples=5,
        )
        build_bent_pipe(
            f"Leaning_AftLeg_{side}",
            [(sx, -1.24, SOLE_Z + 0.012), (sx, -1.22, 1.04), (sx, -1.19, 1.32)],
            0.022,
            col,
            m["aluminum"],
            part="LeaningPost",
            smooth_samples=5,
        )
        build_strut(f"Leaning_SideBrace_{side}", (sx, -1.22, 1.01), (sx, -0.85, 1.01), 0.017, col, m["aluminum"], part="LeaningPost")

    # Folding stainless footrest bar across front legs
    build_bent_pipe(
        "Leaning_Footrest",
        [(-0.43, -0.85, 1.01), (-0.38, -0.74, 0.99), (0.38, -0.74, 0.99), (0.43, -0.85, 1.01)],
        0.015,
        col,
        m["stainless"],
        part="LeaningPost",
        smooth_samples=4,
    )

    # 2. Contoured fiberglass leaning-post seat tub & aft tackle drawer (Z = 1.28 .. 1.38 m)
    tub_pts = [(px, py - 1.04) for (px, py) in geo.rrect2d(0.94, 0.44, 0.08, seg=5)]
    build_prism("Leaning_SeatTub", tub_pts, 1.27, 1.375, col, m["hull_white"], bevel=0.015, part="LeaningPost")
    build_box("Leaning_TackleFace", (0.64, 0.022, 0.068), col, m["dash_dark"], location=(0.0, -1.26, 1.325), bevel=0.004, part="LeaningPost")

    # Side stainless grab handles on leaning post tub
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        build_bent_pipe(
            f"Leaning_SideGrab_{side}",
            [(sx * 0.46, -1.18, 1.33), (sx * 0.52, -1.14, 1.36), (sx * 0.52, -0.92, 1.36), (sx * 0.46, -0.88, 1.33)],
            0.012,
            col,
            m["stainless"],
            part="LeaningPost",
            smooth_samples=4,
        )

    # 3. Dual Flip-Up Helm Bolster Cushions w/ Thigh Rolls & Contrasting Piping (Z = 1.365 .. 1.465 m)
    for side, sx in (("Port", -0.225), ("Starboard", 0.225)):
        seat_p = [(px + sx, py - 1.04) for (px, py) in [(-0.205, -0.19), (0.205, -0.19), (0.205, 0.16), (-0.205, 0.16)]]
        build_puffed_cushion(
            f"Leaning_SeatCushion_{side}",
            seat_p,
            1.362,
            1.455,
            col,
            m["vinyl_white"],
            part="LeaningPost",
            piping_mat=m["vinyl_slate"],
            corner_r=0.045,
        )
        # Raised front thigh-bolster roll (embedded 10 mm into SeatTub -> zero back-to-back contact!)
        roll_p = [(px + sx, py - 0.855) for (px, py) in [(-0.195, -0.055), (0.195, -0.055), (0.195, 0.055), (-0.195, 0.055)]]
        build_puffed_cushion(
            f"Leaning_BolsterRoll_{side}",
            roll_p,
            1.365,
            1.488,
            col,
            m["vinyl_slate"],
            part="LeaningPost",
            corner_r=0.03,
        )

    # 4. Swept Backrest Arms + Puffed Wrap-Around Backrest Bolster + 4 Aft Tulip Rod Holders
    for side, sx in (("Port", -0.35), ("Starboard", 0.35)):
        build_bent_pipe(
            f"Leaning_BackArm_{side}",
            [(sx, -1.20, 1.35), (sx, -1.27, 1.50), (sx, -1.29, 1.66)],
            0.018,
            col,
            m["aluminum"],
            part="LeaningPost",
            smooth_samples=4,
        )
    lp_back_xf = Matrix.Translation((0.0, -1.265, 1.64)) @ Euler((math.radians(80.0), 0.0, 0.0), "XYZ").to_matrix().to_4x4()
    build_puffed_cushion(
        "Leaning_BackrestPad",
        [(-0.44, -0.095), (0.44, -0.095), (0.44, 0.095), (-0.44, 0.095)],
        -0.045,
        0.048,
        col,
        m["vinyl_white"],
        part="LeaningPost",
        piping_mat=m["vinyl_slate"],
        corner_r=0.04,
        matrix=lp_back_xf,
    )

    # 4 proportional 38 mm (1.5") anodized rod holders mounted across aft face of leaning post tub
    build_strut("Leaning_RodBar", (-0.38, -1.280, 1.33), (0.38, -1.280, 1.33), 0.013, col, m["aluminum"], part="LeaningPost")
    for r_i, rx in enumerate((-0.31, -0.105, 0.105, 0.31)):
        build_strut(
            f"Leaning_RodTube_{r_i}",
            (rx, -1.288, 1.255),
            (rx, -1.328, 1.435),
            0.0185,
            col,
            m["stainless"],
            seg=16,
            radius2=0.0205,
            part="LeaningPost",
        )

    # 5. Slide-Out YETI-Style Marine Cooler on Deck Chocks Beneath Leaning Post
    cooler_bot = [(px, py - 1.04) for (px, py) in geo.rrect2d(0.72, 0.36, 0.04, seg=4)]
    build_prism("Leaning_CoolerBody", cooler_bot, SOLE_Z + 0.004, 1.135, col, m["hull_white"], bevel=0.012, taper=1.03, part="LeaningPost")
    cooler_lid = [(px, py - 1.04) for (px, py) in geo.rrect2d(0.75, 0.38, 0.042, seg=4)]
    build_prism("Leaning_CoolerLid", cooler_lid, 1.125, 1.185, col, m["console_grey"], bevel=0.010, part="LeaningPost")
    # Rubber T-latches & side handles
    for lx in (-0.22, 0.22):
        build_box(f"Leaning_CoolerLatch_{lx:.2f}", (0.026, 0.024, 0.068), col, m["rubber_black"], location=(lx, -1.228, 1.13), bevel=0.004, part="LeaningPost")
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        build_bent_pipe(
            f"Leaning_CoolerHandle_{side}",
            [(sx * 0.36, -1.11, 1.08), (sx * 0.40, -1.08, 1.04), (sx * 0.40, -1.00, 1.04), (sx * 0.36, -0.97, 1.08)],
            0.008,
            col,
            m["rubber_black"],
            part="LeaningPost",
            smooth_samples=3,
        )


# ---------------------------------------------------------------------------
# 5. Mandrel-Bent Aluminum T-Top, Cambered Molded Hardtop & Fantom Radome
# ---------------------------------------------------------------------------
def build_ttop_and_radar(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build inward-tapered (/  \\) mandrel-bent T-Top frame, sleek thin-lip hardtop, Fantom radome & launcher."""
    # 1. Pronounced inward-tapering (/  \) offshore T-Top legs (0.58 m -> 0.365 m) bolted to heavy anodized deck base plates!
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        for lbl, ly in (("Fwd", 0.52), ("Aft", -0.26)):
            tf_pts = [(px + sx * 0.58, py + ly) for (px, py) in geo.rrect2d(0.115, 0.145, 0.035, seg=4)]
            build_prism(f"TTop_DeckFoot_{lbl}_{side}", tf_pts, SOLE_Z + 0.0068, SOLE_Z + 0.025, col, m["aluminum"], bevel=0.005, part="TTop")
            for bx, by in ((-0.036, -0.048), (0.036, -0.048), (-0.036, 0.048), (0.036, 0.048)):
                b_ob = geo.cylinder(f"TTop_FootBolt_{lbl}_{side}_{bx:.2f}_{by:.2f}", 0.007, 0.012, col, m["stainless"], location=(sx * 0.58 + bx, ly + by, SOLE_Z + 0.024), seg=6)
                finalize_mesh(b_ob, part="TTop")
        build_bent_pipe(
            f"TTop_FwdMainPipe_{side}",
            [
                (sx * 0.58, 0.52, SOLE_Z + 0.014),
                (sx * 0.530, 0.51, 1.30),
                (sx * 0.465, 0.49, 1.85),
                (sx * 0.405, 0.47, 2.38),
                (sx * 0.365, 0.45, 2.66),
            ],
            0.024,
            col,
            m["aluminum"],
            part="TTop",
            smooth_samples=6,
        )
        build_bent_pipe(
            f"TTop_AftMainPipe_{side}",
            [
                (sx * 0.58, -0.26, SOLE_Z + 0.014),
                (sx * 0.530, -0.28, 1.30),
                (sx * 0.465, -0.32, 1.85),
                (sx * 0.405, -0.44, 2.38),
                (sx * 0.370, -0.58, 2.65),
            ],
            0.024,
            col,
            m["aluminum"],
            part="TTop",
            smooth_samples=6,
        )
        # Console side standoffs bolting main legs cleanly into console flanks
        build_strut(f"TTop_FwdStandoff_{side}", (sx * 0.42, 0.50, 1.62), (sx * 0.50, 0.50, 1.62), 0.019, col, m["aluminum"], part="TTop")
        build_strut(f"TTop_AftStandoff_{side}", (sx * 0.42, -0.29, 1.62), (sx * 0.50, -0.29, 1.62), 0.019, col, m["aluminum"], part="TTop")

        # Curved upper canopy outrigger support bows branching from upper main legs out to canopy perimeter
        for oy, oz in ((0.45, 2.46), (-0.56, 2.46)):
            build_bent_pipe(
                f"TTop_OutriggerArm_{side}_{oy:.2f}",
                [(sx * 0.39, oy, oz), (sx * 0.53, oy, oz + 0.12), (sx * 0.67, oy, 2.64)],
                0.017,
                col,
                m["aluminum"],
                part="TTop",
                smooth_samples=4,
            )

        # Upper longitudinal perimeter truss + curved fore-aft diagonal wind brace
        build_bent_pipe(
            f"TTop_UpperTruss_{side}",
            [(sx * 0.66, -0.98, 2.62), (sx * 0.68, -0.40, 2.64), (sx * 0.66, 0.45, 2.65), (sx * 0.52, 0.94, 2.63)],
            0.018,
            col,
            m["aluminum"],
            part="TTop",
            smooth_samples=5,
        )
        build_bent_pipe(
            f"TTop_DiagBrace_{side}",
            [(sx * 0.45, 0.48, 1.98), (sx * 0.405, 0.10, 2.38), (sx * 0.375, -0.36, 2.62)],
            0.016,
            col,
            m["aluminum"],
            part="TTop",
            smooth_samples=4,
        )
        # Sleek overhead passenger hand-hold grab rail along underside edge
        build_bent_pipe(
            f"TTop_GrabRail_{side}",
            [(sx * 0.67, -0.86, 2.655), (sx * 0.72, -0.25, 2.58), (sx * 0.70, 0.42, 2.59), (sx * 0.60, 0.68, 2.655)],
            0.013,
            col,
            m["stainless"],
            part="TTop",
            smooth_samples=5,
        )

    # Transverse frame bows under hardtop (12 mm clear below hardtop underside!)
    for py, pz in ((-0.58, 2.595), (0.05, 2.608), (0.45, 2.600)):
        build_bent_pipe(
            f"TTop_CrossBow_{py:.2f}",
            [(-0.66, py, pz + 0.024), (0.0, py, pz + 0.026), (0.66, py, pz + 0.024)],
            0.017,
            col,
            m["aluminum"],
            part="TTop",
            smooth_samples=5,
        )

    # 2. Cambered Molded Fiberglass Hardtop Canopy w/ Perimeter Drip-Visor Lip & 8.8 cm Crown!
    canopy_stations = [
        (-1.10, 0.66, -0.020),
        (-1.02, 0.78, -0.010),
        (-0.78, 0.84, 0.000),
        (-0.30, 0.86, 0.010),
        (0.25, 0.85, 0.012),
        (0.72, 0.78, 0.004),
        (1.04, 0.64, -0.008),
        (1.20, 0.44, -0.018),
        (1.26, 0.22, -0.024),
    ]
    ht_rings: list[list[Vector]] = []
    n_lat = 17
    for y_pos, hw, z_rake in canopy_stations:
        top_arc: list[Vector] = []
        bot_arc: list[Vector] = []
        is_end = y_pos in (-1.10, 1.26)
        thick_c = 0.036 if is_end else 0.052
        thick_e = 0.032 if is_end else 0.038
        for k in range(n_lat):
            u = (k / (n_lat - 1)) * 2.0 - 1.0
            x = hw * u
            arch = 0.088 * (1.0 - u * u) * (0.65 if is_end else 1.0)
            zt = 2.668 + z_rake + arch
            th = thick_e + (thick_c - thick_e) * (1.0 - u * u)
            top_arc.append(Vector((x, y_pos, zt)))
            bot_arc.append(Vector((x * 0.985, y_pos, zt - th)))
        ht_rings.append(top_arc + list(reversed(bot_arc)))

    hardtop = geo.loft(
        "TTop_MoldedHardtop",
        ht_rings,
        col,
        [m["hull_white"], m["dash_dark"]],
        closed=True,
        cap_start=True,
        cap_end=True,
        mat_fn=lambda ri, si: 1 if (n_lat + 1 <= si <= 2 * n_lat - 3 and 1 <= ri <= len(ht_rings) - 3) else 0,
        cap_mat=(0, 0),
        smooth=True,
        sharp_angle=48.0,
        recalc=True,
    )
    finalize_mesh(hardtop, part="TTop", sharp_angle=48.0)

    # Bold molded perimeter drip-visor rub molding around hardtop edge (~3.8 cm lip, clean non-parallel overlap!)
    stbd_rim = [Vector((hw + 0.010, y_pos, 2.652 + z_rake)) for (y_pos, hw, z_rake) in canopy_stations]
    port_rim = [Vector((-(hw + 0.010), y_pos, 2.652 + z_rake)) for (y_pos, hw, z_rake) in reversed(canopy_stations[1:-1])]
    rim = geo.tube("TTop_VisorDripRim", stbd_rim + port_rim, 0.022, col, m["dash_dark"], seg=10, smooth_samples=2, closed=True)
    finalize_mesh(rim, part="TTop", sharp_angle=52.0)

    # 3. Overhead Electronics Box w/ Smoked Acrylic Door under forward canopy
    ebox_pts = [(px, py + 0.14) for (px, py) in geo.rrect2d(0.66, 0.34, 0.04, seg=4)]
    build_prism("TTop_ElectronicsBox", ebox_pts, 2.52, 2.71, col, m["console_grey"], bevel=0.012, part="TTop")
    build_box(
        "TTop_ElectronicsDoor",
        (0.58, 0.024, 0.115),
        col,
        m["dash_dark"],
        location=(0.0, -0.032, 2.590),
        rotation_deg=(12.0, 0.0, 0.0),
        bevel=0.004,
        part="TTop",
    )

    # 4. Forward-Raked Aluminum Radar Pedestal + Sculpted Garmin Fantom-18 Radome + GPS Puck + VHF Whip
    ped_pts = [(px, py + 0.24) for (px, py) in geo.rrect2d(0.24, 0.28, 0.04, seg=3)]
    build_prism("TTop_RadarStrut", ped_pts, 2.742, 2.852, col, m["hull_white"], bevel=0.010, taper=0.82, part="TTop")

    radome_prof = [
        (0.012, 0.000),
        (0.185, 0.004),
        (0.238, 0.024),
        (0.246, 0.068),
        (0.236, 0.118),
        (0.205, 0.154),
        (0.135, 0.174),
        (0.012, 0.180),
    ]
    radome = geo.lathe(
        "TTop_FantomRadome",
        radome_prof,
        col,
        m["hull_white"],
        seg=36,
        center=(0.0, 0.24, 2.838),
        axis=(0.0, 0.06, 1.0),
        cap_start=True,
        cap_end=True,
        sharp_angle=48.0,
    )
    finalize_mesh(radome, part="TTop", sharp_angle=48.0)

    build_strut("TTop_AnchorLightMast", (0.0, 0.14, 2.97), (0.0, 0.10, 3.19), 0.013, col, m["stainless"], part="TTop")

    gps = geo.lathe(
        "TTop_GPSPuck",
        [(0.008, 0.0), (0.046, 0.002), (0.048, 0.024), (0.036, 0.038), (0.008, 0.042)],
        col,
        m["hull_white"],
        seg=24,
        center=(0.44, 0.36, 2.715),
        axis=(0.0, 0.0, 1.0),
        cap_start=True,
        cap_end=True,
    )
    finalize_mesh(gps, part="TTop")

    build_box("TTop_VHFRatchet", (0.052, 0.078, 0.048), col, m["stainless"], location=(-0.52, 0.18, 2.720), bevel=0.006, part="TTop")
    build_strut(
        "TTop_VHFAntennaWhip",
        (-0.52, 0.18, 2.735),
        (-0.56, -0.14, 3.48),
        0.0095,
        col,
        m["hull_white"],
        seg=12,
        radius2=0.0045,
        part="TTop",
    )

    for side, sx in (("Port", -0.58), ("Starboard", 0.58)):
        tur = geo.cylinder(f"TTop_OutriggerBase_{side}", 0.038, 0.065, col, m["stainless"], location=(sx, -0.18, 2.715), seg=18, bevel=0.005)
        finalize_mesh(tur, part="TTop")

    # 5. Precision CAD 5-Tube Tulip-Flared Rocket Launcher mounted across aft hardtop
    import_cad_part(
        "rocket_launcher.glb",
        "TTop_RocketLauncher",
        col,
        m["stainless"],
        location=(0.0, -1.03, 2.705),
        rotation_deg=(0.0, 0.0, 0.0),
        part="TTop",
    )


# ---------------------------------------------------------------------------
# 6. Rub Rail, Recessed Bow Rails, Bow Pulpit + Plow Anchor, Trim Tabs & Cleats
# ---------------------------------------------------------------------------
def build_trim_and_cad_hardware(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build heavy D-profile rub rail + stainless insert, bow roller + anchor, trim tabs, ladder & 6 cleats."""
    # 1. Heavy Marine Rub Rail around sheer (excluding recessed center motorwell notch so notch stays open!)
    rr_ts = [0.005 + 0.995 * (i / 42.0) for i in range(43)]
    rr_path: list[Vector] = []
    # Port quarter inboard -> Port transom corner -> Port sheer -> Bow stem -> Stbd sheer -> Stbd quarter inboard
    sz0 = hull_sheer_z(0.005)
    y0 = hull_y_at_z(0.005, sz0 - 0.018)
    rr_path.append(Vector((-0.66, y0 - 0.008, sz0 - 0.018)))
    rr_path.append(Vector((-hull_outer_profile(0.005)[-1][0], y0 - 0.008, sz0 - 0.018)))
    for t in rr_ts[1:]:
        sz = hull_sheer_z(t)
        xb = hull_outer_profile(t)[-1][0]
        rr_path.append(Vector((-xb, hull_y_at_z(t, sz - 0.018), sz - 0.018)))
    rr_path.append(Vector((0.0, hull_y_at_z(1.0, SHEER_BOW - 0.016) + 0.022, SHEER_BOW - 0.016)))
    for t in reversed(rr_ts[1:]):
        sz = hull_sheer_z(t)
        xb = hull_outer_profile(t)[-1][0]
        rr_path.append(Vector((xb, hull_y_at_z(t, sz - 0.018), sz - 0.018)))
    rr_path.append(Vector((hull_outer_profile(0.005)[-1][0], y0 - 0.008, sz0 - 0.018)))
    rr_path.append(Vector((0.66, y0 - 0.008, sz0 - 0.018)))

    # Single manifold 2-material D-profile Rub Rail hugging OUTER sheer lip (+3 mm flange embed -> zero inner-liner breach!)
    rub_prof = [
        (-0.024, -0.024),  # 0: outboard bottom
        (-0.024, -0.008),  # 1: bead lower shoulder
        (-0.032, -0.005),  # 2: stainless insert lower nose
        (-0.032, 0.005),   # 3: stainless insert upper nose
        (-0.024, 0.008),   # 4: bead upper shoulder
        (-0.024, 0.024),   # 5: outboard top
        (0.003, 0.024),    # 6: outer-flange top embed (never enters cockpit!)
        (0.003, -0.024),   # 7: outer-flange bottom embed
    ]
    rub = geo.sweep(
        "Trim_RubRail",
        rr_path,
        rub_prof,
        col,
        [m["rubber_black"], m["stainless"]],
        closed_profile=True,
        closed_path=False,
    )
    # Assign stainless (slot 1) to the outward-facing center insert bead faces!
    for poly in rub.data.polygons:
        if len(poly.vertices) == 4:
            c_p = poly.center
            t_r = _exact_t_at_yz(c_p.y, c_p.z)
            xb_r = hull_outer_profile(t_r)[-1][0]
            if abs(c_p.x) > xb_r + 0.025 or c_p.y > hull_y_at_z(1.0, SHEER_BOW - 0.016) + 0.045:
                poly.material_index = 1
    finalize_mesh(rub, part="TrimHardware", sharp_angle=42.0)

    # 2. Full-Length Recessed Offshore Stainless Bow Grab Rails seated strictly inside the flat gunwale cap!
    bow_ts = [0.55, 0.63, 0.71, 0.78, 0.84]
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        r_pts: list[tuple[float, float, float]] = []
        for idx, t in enumerate(bow_ts):
            sz = hull_sheer_z(t)
            xb = gunwale_inner_half_beam(t) + 0.026 * (1.0 - 0.35 * (t**2))
            ry = hull_y_at_z(t, sz)
            if idx == 0:
                t_a = 0.535
                sz_a = hull_sheer_z(t_a)
                xb_a = gunwale_inner_half_beam(t_a) + 0.026
                ya = hull_y_at_z(t_a, sz_a)
                r_pts.append((sx * xb_a, ya, sz_a + 0.006))
                fl_a = geo.cylinder(f"Trim_BowGrabRail_{side}_FlangeA", 0.021, 0.009, col, m["stainless"], location=(sx * xb_a, ya, sz_a + 0.004), seg=16, bevel=0.002)
                finalize_mesh(fl_a, part="TrimHardware", sharp_angle=42.0)
            lift = 0.122 if idx in (1, 2, 3) else 0.088
            r_pts.append((sx * xb, ry, sz + lift))
            if idx in (1, 2, 3, 4):
                build_strut(
                    f"Trim_BowRailPost_{side}_{idx}",
                    (sx * xb, ry, sz + 0.002),
                    (sx * xb, ry, sz + lift),
                    0.011,
                    col,
                    m["stainless"],
                    part="TrimHardware",
                )
            if idx == len(bow_ts) - 1:
                t_f = 0.865
                sz_f = hull_sheer_z(t_f)
                xb_f = gunwale_inner_half_beam(t_f) + 0.020
                yf = hull_y_at_z(t_f, sz_f)
                r_pts.append((sx * xb_f, yf, sz_f + 0.008))
                fl_b = geo.cylinder(f"Trim_BowGrabRail_{side}_FlangeB", 0.020, 0.009, col, m["stainless"], location=(sx * xb_f, yf, sz_f + 0.004), seg=16, bevel=0.002)
                finalize_mesh(fl_b, part="TrimHardware", sharp_angle=42.0)

        build_bent_pipe(
            f"Trim_BowGrabRail_{side}",
            r_pts,
            0.0135,
            col,
            m["stainless"],
            part="TrimHardware",
            smooth_samples=4,
            flange_start=False,
            flange_end=False,
        )

    # 3. Compact Stainless Bow Roller Channel + Stowed Plow Anchor riding OVER roller sheave (ZERO stem piercing!)
    z_stem = SHEER_BOW
    y_stem = hull_y_at_z(1.0, z_stem)
    build_box("Trim_BowRollerBase", (0.082, 0.36, 0.020), col, m["stainless"], location=(0.0, y_stem - 0.10, z_stem + 0.002), bevel=0.004, part="TrimHardware")
    for sx in (-0.042, 0.042):
        cheek = [(-0.006 + sx, y_stem - 0.27), (0.006 + sx, y_stem - 0.27), (0.006 + sx, y_stem + 0.11), (-0.006 + sx, y_stem + 0.11)]
        build_prism(f"Trim_BowRollerCheek_{sx:.3f}", cheek, z_stem - 0.002, z_stem + 0.066, col, m["stainless"], bevel=0.003, part="TrimHardware")
    roller = geo.cylinder("Trim_BowSheave", 0.028, 0.076, col, m["rubber_black"], location=(0.0, y_stem + 0.075, z_stem + 0.030), rotation=(0.0, math.radians(90.0), 0.0), seg=20, bevel=0.004)
    finalize_mesh(roller, part="TrimHardware")

    # Anchor shank rides horizontally inside stainless roller channel ABOVE deck, then drops outside bow stem!
    build_bent_pipe(
        "Trim_AnchorShank",
        [
            (0.0, y_stem - 0.21, z_stem + 0.030),
            (0.0, y_stem + 0.075, z_stem + 0.042),
            (0.0, y_stem + 0.145, z_stem - 0.115),
        ],
        0.0135,
        col,
        m["stainless"],
        part="TrimHardware",
        smooth_samples=4,
    )
    fluke_pts = [
        (0.0, y_stem + 0.21, z_stem - 0.175),
        (0.105, y_stem + 0.095, z_stem - 0.128),
        (0.0, y_stem + 0.055, z_stem - 0.072),
        (-0.105, y_stem + 0.095, z_stem - 0.128),
    ]
    fluke_top = [Vector(p) + Vector((0.0, -0.012, 0.022)) for p in fluke_pts]
    fluke = geo.loft("Trim_AnchorFluke", [[Vector(p) for p in fluke_pts], fluke_top], col, m["stainless"], closed=True, cap_start=True, cap_end=True, recalc=True)
    finalize_mesh(fluke, part="TrimHardware", sharp_angle=38.0)

    # Stainless Bow Tow Eye on lower stem + Stern Transom Tie-Down Eyes
    y_eye = hull_y_at_z(0.985, 1.24)
    bow_eye_plate = geo.cylinder("Trim_BowEyePlate", 0.030, 0.018, col, m["stainless"], location=(0.0, y_eye + 0.004, 1.24), rotation=(math.radians(72.0), 0.0, 0.0), seg=18)
    finalize_mesh(bow_eye_plate, part="TrimHardware")
    bow_eye_ring = geo.torus("Trim_BowEyeRing", 0.028, 0.0075, col, m["stainless"], center=(0.0, y_eye + 0.026, 1.235), axis=(1.0, 0.0, 0.0), seg=24, rseg=10)
    finalize_mesh(bow_eye_ring, part="TrimHardware")

    for side, sx in (("Port", -0.86), ("Starboard", 0.86)):
        s_plate = geo.cylinder(f"Trim_SternEyePlate_{side}", 0.028, 0.016, col, m["stainless"], location=(sx, Y_TRANSOM - 0.035, 1.02), rotation=(math.radians(90.0), 0.0, 0.0), seg=18)
        finalize_mesh(s_plate, part="TrimHardware")
        s_ring = geo.torus(f"Trim_SternEyeRing_{side}", 0.026, 0.007, col, m["stainless"], center=(sx, Y_TRANSOM - 0.056, 1.02), axis=(0.0, 0.0, 1.0), seg=22, rseg=10)
        finalize_mesh(s_ring, part="TrimHardware")

    # 4. Lenco Stainless Hydraulic Trim Tabs + Actuators at bottom transom edge
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        c_in, cz, _ = hull_chine_point(0.005)
        u_tab = 0.62
        tx = sx * (c_in * u_tab)
        tz = Z_KEEL_AFT + (cz - Z_KEEL_AFT) * u_tab
        deadrise_roll = -sx * 20.5
        build_box(
            f"Trim_TabPlane_{side}",
            (0.32, 0.24, 0.010),
            col,
            m["stainless"],
            location=(tx, Y_TRANSOM - 0.09, tz + 0.008),
            rotation_deg=(-4.0, deadrise_roll, 0.0),
            bevel=0.002,
            part="TrimHardware",
        )
        build_strut(
            f"Trim_TabActuator_{side}",
            (tx, Y_TRANSOM - 0.16, tz + 0.015),
            (tx, Y_TRANSOM + 0.01, tz + 0.24),
            0.016,
            col,
            m["rubber_black"],
            seg=14,
            radius2=0.012,
            part="TrimHardware",
        )

    # 5. Port Euro-Transom Telescoping 3-Step Stainless Boarding Ladder (tucked cleanly forward of V8 leg & clear of bumper!)
    for lx in (-0.91, -0.67):
        build_bent_pipe(
            f"Trim_SwimLadderRail_{lx:.2f}",
            [(lx, -3.40, 0.915), (lx, -3.52, 0.925), (lx, -3.54, 0.62)],
            0.013,
            col,
            m["stainless"],
            part="TrimHardware",
            smooth_samples=4,
            flange_start=True,
        )
    for step_z, step_y in ((0.76, -3.53), (0.65, -3.535)):
        build_box(f"Trim_SwimLadderStep_{step_z:.2f}", (0.25, 0.050, 0.018), col, m["rubber_black"], location=(-0.79, step_y, step_z), bevel=0.004, part="TrimHardware")

    # 6. 4 Flush Gunwale Stainless Rod-Holder Bezels + 6 Precision CAD Deck Cleats (Bow, Spring, Stern)
    for r_label, t_rod in (("Aft", 0.22), ("Mid", 0.38)):
        sz = hull_sheer_z(t_rod)
        ry = hull_y_at_z(t_rod, sz)
        rx_mag = 0.5 * (hull_outer_profile(t_rod)[-1][0] + gunwale_inner_half_beam(t_rod))
        for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
            flange_pts = [(px + sx * rx_mag, py + ry) for (px, py) in geo.ellipse2d(0.036, 0.048, seg=18)]
            build_prism(f"Trim_GunwaleRodBezel_{r_label}_{side}", flange_pts, sz - 0.005, sz + 0.006, col, m["stainless"], bevel=0.002, part="TrimHardware")
            cap = geo.cylinder(f"Trim_GunwaleRodBore_{r_label}_{side}", 0.021, 0.024, col, m["rubber_black"], location=(sx * rx_mag, ry, sz - 0.001), seg=16)
            finalize_mesh(cap, part="TrimHardware")

    cleat_stations = [("Stern", 0.095), ("Spring", 0.48), ("Bow", 0.62)]
    for label, t in cleat_stations:
        sz = hull_sheer_z(t)
        cy = hull_y_at_z(t, sz)
        cx_mag = gunwale_inner_half_beam(t) + 0.038
        # Align cleat in 3D (yaw + sheer pitch!) along the rising gunwale cap above the concave outer flare!
        t_a, t_b = max(0.0, t - 0.015), min(1.0, t + 0.015)
        sz_a, sz_b = hull_sheer_z(t_a), hull_sheer_z(t_b)
        cx_a = gunwale_inner_half_beam(t_a) + 0.038
        cx_b = gunwale_inner_half_beam(t_b) + 0.038
        for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
            p_a = Vector((sx * cx_a, hull_y_at_z(t_a, sz_a), sz_a))
            p_b = Vector((sx * cx_b, hull_y_at_z(t_b, sz_b), sz_b))
            x_ax = (p_b - p_a).normalized()
            z_ax = (Vector((0.0, 0.0, 1.0)) - x_ax * x_ax.z).normalized()
            y_ax = z_ax.cross(x_ax).normalized()
            rot_m = Matrix((x_ax, y_ax, z_ax)).transposed()
            eul_deg = tuple(math.degrees(a) for a in rot_m.to_euler("XYZ"))
            import_cad_part(
                "deck_cleat.glb",
                f"Trim_Cleat_{label}_{side}",
                col,
                m["stainless"],
                location=(sx * cx_mag, cy, sz - 0.0028),
                rotation_deg=eul_deg,
                part="TrimHardware",
            )


# ---------------------------------------------------------------------------
# 7. Flush Shark-Eye Navigation Lights, Spreader Lights & Anchor Beacon
# ---------------------------------------------------------------------------
def build_lights(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build hull-conformant exterior bow shark-eye nav lights (zero inner-liner breach, zero z-fight, zero back-to-back!)."""
    def _hull_surf_and_normal(sx: float, tq: float, zq: float) -> tuple[Vector, Vector]:
        xq = hull_outer_x_at_z(tq, zq)
        yq = hull_y_at_z(tq, zq)
        ps = Vector((sx * xq, yq, zq))
        v_up = Vector((
            sx * (hull_outer_x_at_z(tq, zq + 0.015) - hull_outer_x_at_z(tq, zq - 0.015)),
            hull_y_at_z(tq, zq + 0.015) - hull_y_at_z(tq, zq - 0.015),
            0.030,
        )).normalized()
        v_fw = Vector((
            sx * (hull_outer_x_at_z(tq + 0.008, zq) - hull_outer_x_at_z(tq - 0.008, zq)),
            hull_y_at_z(tq + 0.008, zq) - hull_y_at_z(tq - 0.008, zq),
            0.0,
        )).normalized()
        no = (v_fw.cross(v_up) if sx > 0 else v_up.cross(v_fw)).normalized()
        if no.x * sx < 0:
            no = -no
        return ps, no

    # HullPaint occupies +0.0040..+0.0085 along n_out; Bezel (-0.0045..+0.0175) & Lens (+0.0130..+0.0235) stay >=4.5mm clear of every skin!
    for side, sx, lmat in (("Port", -1.0, m["nav_red"]), ("Starboard", 1.0, m["nav_green"])):
        bez_rings: list[list[Vector]] = []
        for t_s, h_half, d_out in ((0.856, 0.013, 0.0150), (0.870, 0.023, 0.0185), (0.884, 0.011, 0.0145)):
            zc = hull_sheer_z(t_s) - 0.078
            p_lo, n_lo = _hull_surf_and_normal(sx, t_s, zc - h_half)
            p_hi, n_hi = _hull_surf_and_normal(sx, t_s, zc + h_half)
            ring = [
                p_lo - n_lo * 0.0045,
                p_lo + n_lo * d_out,
                p_hi + n_hi * d_out,
                p_hi - n_hi * 0.0045,
            ]
            bez_rings.append(ring if sx > 0 else list(reversed(ring)))
        bez = geo.loft(
            f"Light_SharkBezel_{side}",
            bez_rings,
            col,
            m["stainless"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=42.0,
            recalc=True,
        )
        finalize_mesh(bez, part="TrimHardware", sharp_angle=42.0)

        lens_rings: list[list[Vector]] = []
        for t_s, h_half in ((0.861, 0.009), (0.870, 0.014), (0.879, 0.008)):
            zc = hull_sheer_z(t_s) - 0.078
            p_lo, n_lo = _hull_surf_and_normal(sx, t_s, zc - h_half)
            p_hi, n_hi = _hull_surf_and_normal(sx, t_s, zc + h_half)
            ring = [
                p_lo + n_lo * 0.0132,
                p_lo + n_lo * 0.0240,
                p_hi + n_hi * 0.0240,
                p_hi + n_hi * 0.0132,
            ]
            lens_rings.append(ring if sx > 0 else list(reversed(ring)))
        lens = geo.loft(
            f"Light_NavLens_{side}",
            lens_rings,
            col,
            lmat,
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=42.0,
            recalc=True,
        )
        finalize_mesh(lens, part="Lights", role="neon", sharp_angle=42.0)

    # All-round white LED anchor light at top of T-Top mast
    beacon = geo.cylinder("Light_AnchorBeacon", 0.024, 0.048, col, m["light_white"], location=(0.0, 0.10, 3.205), seg=18, bevel=0.005)
    finalize_mesh(beacon, part="Lights", role="neon")

    # Twin Aft & Forward T-Top LED Spreader Floodlight Pods (dropped cleanly below canopy lip so 100% visible!)
    for side, sx in (("Port", -0.34), ("Starboard", 0.34)):
        build_strut(f"Light_AftSpreaderStem_{side}", (sx, -1.01, 2.645), (sx, -1.03, 2.592), 0.010, col, m["stainless"], part="TTop")
        build_box(f"Light_AftSpreaderHousing_{side}", (0.20, 0.068, 0.052), col, m["hull_white"], location=(sx, -1.045, 2.585), rotation_deg=(-20.0, 0.0, 0.0), bevel=0.008, part="TTop")
        build_box(f"Light_AftSpreaderLens_{side}", (0.17, 0.026, 0.034), col, m["light_white"], location=(sx, -1.074, 2.578), rotation_deg=(-20.0, 0.0, 0.0), bevel=0.004, part="Lights", role="neon")

    build_strut("Light_FwdSpreaderStem", (0.0, 1.10, 2.645), (0.0, 1.12, 2.598), 0.010, col, m["stainless"], part="TTop")
    build_box("Light_FwdSpreaderHousing", (0.21, 0.064, 0.048), col, m["hull_white"], location=(0.0, 1.135, 2.592), rotation_deg=(18.0, 0.0, 0.0), bevel=0.008, part="TTop")
    build_box("Light_FwdSpreaderLens", (0.18, 0.024, 0.032), col, m["light_white"], location=(0.0, 1.162, 2.586), rotation_deg=(18.0, 0.0, 0.0), bevel=0.004, part="Lights", role="neon")

    for idx_c, (cx, cy, cz) in enumerate(((-0.28, -0.32, 2.702), (0.28, -0.32, 2.702), (-0.26, 0.42, 2.704), (0.26, 0.42, 2.704))):
        puck = geo.cylinder(f"Light_CourtesyPuck_{idx_c}", 0.024, 0.022, col, m["light_white"], location=(cx, cy, cz), seg=16, bevel=0.003)
        finalize_mesh(puck, part="Lights", role="neon")


# ---------------------------------------------------------------------------
# 8. Helm Controls & Showpiece 1:1 300HP V8 Offshore Outboard (Motor + Prop)
# ---------------------------------------------------------------------------
def build_helm_controls_and_outboard(col: bpy.types.Collection, m: dict[str, bpy.types.Material]) -> None:
    """Build low-mounted Destroyer Wheel, Top-Mount Binnacle, Chiseled V8 300 Outboard, Bracket & 16" Prop."""
    # 1. CAD 5-Spoke Destroyer Wheel + Edson Power Knob set low on tilted helm pod (100% clear below MFDs!)
    import_cad_part(
        "steering_wheel.glb",
        "Steering_DestroyerWheel",
        col,
        m["stainless"],
        location=(-0.20, -0.548, 1.586),
        rotation_deg=(-25.0, 0.0, 0.0),
        part="Steering",
    )

    # 2. Top-Mount Single-Lever Binnacle Control squarely seated on flat horizontal starboard helm pad!
    import_cad_part(
        "throttle_binnacle.glb",
        "Throttle_HelmBinnacle",
        col,
        m["stainless"],
        location=(0.235, -0.435, 1.482),
        rotation_deg=(0.0, 0.0, 0.0),
        part="Throttle",
    )

    # 3. 1:1 Chiseled 300HP V8 Offshore Outboard w/ Wide Bolted Cast-Graphite Backing Plate, Centered U-Clamp Saddle & Angled Chrome PTT Rams!
    yt = hull_y_at_z(0.0, MOTORWELL_LIP_Z)  # ~ -3.418 m at raked transom top!
    mp_lo_z, mp_hi_z = 0.710, 1.044
    mp_lo_y, mp_hi_y = hull_y_at_z(0.0, mp_lo_z), hull_y_at_z(0.0, mp_hi_z)
    mp_rings = [
        [Vector((x, mp_lo_y + dy, mp_lo_z)) for (x, dy) in ((-0.31, 0.004), (0.31, 0.004), (0.31, -0.054), (-0.31, -0.054))],
        [Vector((x, mp_hi_y + dy, mp_hi_z)) for (x, dy) in ((-0.31, 0.004), (0.31, 0.004), (0.31, -0.054), (-0.31, -0.054))],
    ]
    mp_ob = geo.loft(
        "Motor_TransomMountPlate",
        mp_rings,
        col,
        m["dash_dark"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=35.0,
        recalc=True,
    )
    finalize_mesh(mp_ob, part="Motor", sharp_angle=35.0)

    # Centered full-width cast-silver U-clamp transom saddle bridging Port & Starboard brackets!
    saddle_yz = [
        (yt - 0.015, 1.058),
        (yt + 0.024, 1.086),
        (yt - 0.095, 1.086),
        (yt - 0.115, 1.052),
    ]
    sad_ob = geo.loft(
        "Motor_ClampSaddleBridge",
        [[Vector((-0.175, y, z)) for (y, z) in saddle_yz], [Vector((0.175, y, z)) for (y, z) in saddle_yz]],
        col,
        m["motor_silver"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=35.0,
        recalc=True,
    )
    finalize_mesh(sad_ob, part="Motor", sharp_angle=35.0)

    for side, sx in (("Port", -0.198), ("Starboard", 0.198)):
        clamp_yz = [
            (hull_y_at_z(0.0, 0.74) - 0.022, 0.74),
            (yt - 0.020, MOTORWELL_LIP_Z + 0.004),
            (yt + 0.024, 1.086),
            (yt - 0.145, 1.086),
            (yt - 0.245, 0.74),
            (hull_y_at_z(0.0, 0.72) - 0.072, 0.72),
        ]
        c_rings = [
            [Vector((sx - 0.026, y, z)) for (y, z) in clamp_yz],
            [Vector((sx + 0.026, y, z)) for (y, z) in clamp_yz],
        ]
        cl_ob = geo.loft(f"Motor_ClampBracket_{side}", c_rings, col, m["motor_silver"], closed=True, cap_start=True, cap_end=True, smooth=True, sharp_angle=35.0, recalc=True)
        finalize_mesh(cl_ob, part="Motor", sharp_angle=35.0)

        for bz in (0.790, 0.915, 1.015):
            by_tr = hull_y_at_z(0.0, bz)
            bolt = geo.cylinder(f"Motor_TransomBolt_{side}_{bz:.3f}", 0.016, 0.032, col, m["stainless"], location=(sx * 1.34, by_tr - 0.058, bz), rotation=(math.radians(97.3), 0.0, 0.0), seg=6, bevel=0.002)
            finalize_mesh(bolt, part="Motor")

    # Prominent Front-Mount SeaStar Hydraulic Steering Cylinder, Chrome Shaft & Dual Stainless Tie-Arms (above notch!)
    build_strut("Motor_TiltTube", (-0.25, yt - 0.07, 1.092), (0.25, yt - 0.07, 1.092), 0.021, col, m["stainless"], seg=18, part="Motor")
    build_strut("Motor_SteeringCyl", (-0.18, yt + 0.03, 1.128), (0.18, yt + 0.03, 1.128), 0.026, col, m["aluminum"], seg=20, part="Motor")
    build_strut("Motor_SteeringRod", (-0.30, yt + 0.03, 1.128), (0.30, yt + 0.03, 1.128), 0.011, col, m["stainless"], seg=14, part="Motor")
    for sx in (-0.28, 0.28):
        build_strut(f"Motor_SteerBracket_{sx:.2f}", (sx, yt + 0.03, 1.128), (sx * 0.70, yt - 0.07, 1.092), 0.012, col, m["stainless"], seg=12, part="Motor")
    build_strut("Motor_SteerCenterLink", (0.0, yt + 0.03, 1.128), (0.0, yt - 0.21, 1.092), 0.016, col, m["stainless"], seg=14, part="Motor")

    # Unmistakable Exposed Power Trim & Tilt (PTT): 2 Wide-Stance Angled Trim Cylinders + Gleaming Chrome Rams + Central Tilt Ram!
    build_box("Motor_PTTManifold", (0.38, 0.14, 0.15), col, m["motor_silver"], location=(0.0, yt - 0.10, 0.76), bevel=0.014, part="Motor")
    ptt_motor = geo.cylinder("Motor_PTTElecMotor", 0.040, 0.13, col, m["rubber_black"], location=(-0.125, yt - 0.11, 0.89), seg=18, bevel=0.008)
    finalize_mesh(ptt_motor, part="Motor")
    build_strut("Motor_TiltCylinder", (0.0, yt - 0.10, 0.78), (0.0, yt - 0.24, 0.96), 0.034, col, m["motor_silver"], seg=18, part="Motor")
    build_strut("Motor_TiltChromeRam", (0.0, yt - 0.20, 0.91), (0.0, yt - 0.35, 1.06), 0.021, col, m["stainless"], seg=16, part="Motor")
    for sx in (-0.162, 0.162):
        build_strut(f"Motor_TrimCyl_{sx:.3f}", (sx, yt - 0.09, 0.75), (sx, yt - 0.24, 0.90), 0.030, col, m["motor_silver"], seg=16, part="Motor")
        build_strut(f"Motor_TrimRam_{sx:.3f}", (sx, yt - 0.20, 0.86), (sx * 0.92, yt - 0.38, 1.03), 0.020, col, m["stainless"], seg=16, part="Motor")

    swiv_yz = [(yt - 0.11, 1.11), (yt - 0.27, 1.11), (yt - 0.30, 0.62), (yt - 0.18, 0.60), (yt - 0.13, 0.93)]
    swiv = geo.loft(
        "Motor_SwivelSpine",
        [[Vector((-0.105, y, z)) for (y, z) in swiv_yz], [Vector((0.105, y, z)) for (y, z) in swiv_yz]],
        col,
        m["motor_cowl"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=36.0,
        recalc=True,
    )
    finalize_mesh(swiv, part="Motor", sharp_angle=36.0)

    # Splashwell rigging hoses arching cleanly OVER MOTORWELL_LIP_Z (1.055 m) down into splashwell boots (ZERO transom tunneling!)
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        hose_pts = [
            (sx * 0.075, -3.56, 1.115),
            (sx * 0.13, yt + 0.02, 1.098),
            (sx * 0.18, -3.20, 1.045),
            (sx * 0.18, -3.02, 0.975),
        ]
        build_bent_pipe(
            f"Motor_RiggingLoom_{side}",
            hose_pts,
            0.019,
            col,
            m["rubber_black"],
            part="Motor",
            seg=14,
            smooth_samples=5,
        )

    # --- B. Tall, Chiseled, Flat-Flanked V8 300 Powerhead Cowling (Z = 1.105 .. 1.845 m, exp = 4.6 -> ZERO Egg!) ---
    cowl_stations = [
        # (cz,    cy,      rx,     ry_fwd, ry_aft, exp)
        (1.105, -3.815, 0.218, 0.340, 0.395, 3.8),
        (1.175, -3.820, 0.232, 0.362, 0.418, 4.3),
        (1.300, -3.825, 0.238, 0.376, 0.432, 4.6),
        (1.445, -3.825, 0.236, 0.374, 0.430, 4.7),
        (1.590, -3.820, 0.230, 0.364, 0.418, 4.6),
        (1.715, -3.812, 0.218, 0.346, 0.396, 4.5),
        (1.785, -3.805, 0.198, 0.318, 0.362, 4.2),   # crisp upper architectural shoulder!
        (1.822, -3.800, 0.158, 0.262, 0.298, 3.8),
        (1.840, -3.796, 0.095, 0.165, 0.188, 3.2),
        (1.848, -3.794, 0.018, 0.032, 0.036, 2.4),
    ]
    cowl_rings = [
        se_ring_3d(0.0, cy, cz, rx, rf, ra, exp=ex, seg=64)
        for (cz, cy, rx, rf, ra, ex) in cowl_stations
    ]
    cowl = geo.loft(
        "Motor_V8UpperCowl",
        cowl_rings,
        col,
        m["motor_cowl"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=44.0,
        recalc=True,
    )
    finalize_mesh(cowl, part="Motor", sharp_angle=44.0)

    # Sculpted Top Induction Hood Spine & Rear Tilt-Handle Recess Pocket (signature V8 300 top silhouette!)
    hood_pts = [(px, py - 3.81) for (px, py) in [(-0.088, -0.29), (0.088, -0.29), (0.068, 0.24), (-0.068, 0.24)]]
    build_prism("Motor_TopHoodSpine", geo.fillet_poly(hood_pts, 0.028, seg=4), 1.815, 1.868, col, m["motor_silver"], bevel=0.010, taper=0.86, part="Motor")

    # Port & Starboard Sculpted Side Cold-Air Intake Vents w/ 3 Angled Louver Strakes
    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        build_box(
            f"Motor_SideIntakeRecess_{side}",
            (0.026, 0.32, 0.105),
            col,
            m["rubber_black"],
            location=(sx * 0.214, -3.88, 1.665),
            rotation_deg=(6.0, -sx * 8.0, -sx * 4.0),
            bevel=0.006,
            part="Motor",
        )
        for f_i, fz in enumerate((1.635, 1.665, 1.695)):
            build_box(
                f"Motor_SideVentFin_{side}_{f_i}",
                (0.022, 0.28, 0.010),
                col,
                m["motor_silver"],
                location=(sx * 0.224, -3.88, fz),
                rotation_deg=(6.0, -sx * 8.0, -sx * 4.0),
                bevel=0.002,
                part="Motor",
            )

    # Rubber Cowling Split-Seam Seal Ring at Z = 1.105 m
    seal_ring = se_ring_3d(0.0, -3.815, 1.105, 0.222, 0.344, 0.400, exp=3.8, seg=48)
    seal = geo.tube("Motor_CowlRubberSeal", seal_ring, 0.011, col, m["rubber_black"], seg=10, smooth_samples=0, closed=True)
    finalize_mesh(seal, part="Motor", sharp_angle=60.0)

    # Rear Hot-Air Exhaust Louver Grille + Chrome V8 Badge Bar (flush & continuous along aft spine!)
    build_box(
        "Motor_RearIntakeGrille",
        (0.165, 0.064, 0.056),
        col,
        m["rubber_black"],
        location=(0.0, -4.185, 1.705),
        rotation_deg=(-18.0, 0.0, 0.0),
        bevel=0.008,
        part="Motor",
    )
    build_box(
        "Motor_RearChromeTrim",
        (0.155, 0.036, 0.024),
        col,
        m["stainless"],
        location=(0.0, -4.252, 1.445),
        rotation_deg=(-2.0, 0.0, 0.0),
        bevel=0.005,
        part="Motor",
    )

    # Sleek Narrow Wrap-Around Brushed-Silver & Bahama-Teal V8 Speed Spear along flat chiseled flanks!
    stbd_ks = [53, 55, 57, 59, 61, 63, 1, 3, 5, 7]
    port_ks = [43, 41, 39, 37, 35, 33, 31, 29, 27, 25]
    for side, ks in (("Starboard", stbd_ks), ("Port", port_ks)):
        s_rings: list[list[Vector]] = []
        for r_idx, proud in ((2, 0.0055), (3, 0.0055)):
            ring_src = cowl_rings[r_idx]
            center_v = Vector((0.0, cowl_stations[r_idx][1], cowl_stations[r_idx][0]))
            pts_o, pts_i = [], []
            for pos_i, k_i in enumerate(ks):
                p_surf = ring_src[k_i % 64] + Vector((0.0, 0.0, 0.024 * (pos_i / len(ks))))
                rad_xy = Vector((p_surf.x - center_v.x, p_surf.y - center_v.y, 0.0)).normalized()
                pts_o.append(p_surf + rad_xy * proud)
                pts_i.append(p_surf - rad_xy * 0.014)
            s_rings.append(pts_o + list(reversed(pts_i)))
        swoosh = geo.loft(
            f"Motor_CowlSilverSwoosh_{side}",
            s_rings,
            col,
            m["motor_silver"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=44.0,
            recalc=True,
        )
        finalize_mesh(swoosh, part="Motor", sharp_angle=44.0)

        t_rings: list[list[Vector]] = []
        for z_off in (-0.034, -0.006):
            ring_src = cowl_rings[2]
            center_v = Vector((0.0, cowl_stations[2][1], cowl_stations[2][0]))
            po, pi = [], []
            for pos_i, k_i in enumerate(ks[1:-1]):
                p_surf = ring_src[k_i % 64] + Vector((0.0, 0.0, z_off + 0.020 * (pos_i / len(ks))))
                rad_xy = Vector((p_surf.x - center_v.x, p_surf.y - center_v.y, 0.0)).normalized()
                po.append(p_surf + rad_xy * 0.0075)
                pi.append(p_surf - rad_xy * 0.012)
            t_rings.append(po + list(reversed(pi)))
        pin = geo.loft(
            f"Motor_CowlTealPin_{side}",
            t_rings,
            col,
            m["hull_teal"],
            closed=True,
            cap_start=True,
            cap_end=True,
            smooth=True,
            sharp_angle=44.0,
            recalc=True,
        )
        finalize_mesh(pin, part="Motor", sharp_angle=44.0)

    # --- C. Single Uninterrupted Streamlined Midsection Leg (Z = 0.420 .. 1.115 m, proportional to narrow V8 cowl!) ---
    mid_stations = [
        (1.115, -3.815, 0.212, 0.330, 0.385, 3.6),
        (1.015, -3.800, 0.190, 0.285, 0.345, 3.0),
        (0.905, -3.775, 0.145, 0.230, 0.296, 2.5),
        (0.775, -3.752, 0.108, 0.192, 0.256, 2.2),
        (0.625, -3.736, 0.090, 0.184, 0.240, 2.0),
        (0.422, -3.725, 0.080, 0.198, 0.238, 2.0),
    ]
    mid_rings = [se_ring_3d(0.0, cy, cz, rx, rf, ra, exp=ex, seg=40) for (cz, cy, rx, rf, ra, ex) in mid_stations]
    mid_ob = geo.loft(
        "Motor_ApronAndMidsection",
        mid_rings,
        col,
        [m["motor_silver"], m["motor_cowl"]],
        closed=True,
        cap_start=True,
        cap_end=True,
        mat_fn=lambda ri, _si: 0 if ri == 0 else 1,
        cap_mat=(0, 1),
        smooth=True,
        sharp_angle=52.0,
        recalc=True,
    )
    finalize_mesh(mid_ob, part="Motor", sharp_angle=52.0)

    build_box("Motor_ExhaustRelief", (0.092, 0.042, 0.032), col, m["rubber_black"], location=(0.0, -4.08, 0.96), rotation_deg=(-18.0, 0.0, 0.0), bevel=0.006, part="Motor")

    # --- D. Full-Scale 300HP Lower Unit: ONE Anti-Ventilation Plate, 64 cm Bullet Torpedo, Deep Skeg & 16" Prop ---
    av_pts = geo.fillet_poly(
        [
            (-0.155, -4.14),
            (0.155, -4.14),
            (0.175, -3.80),
            (0.110, -3.48),
            (0.0, -3.41),
            (-0.110, -3.48),
            (-0.175, -3.80),
        ],
        0.032,
        seg=4,
    )
    build_prism("Motor_AntiVentPlate", av_pts, 0.412, 0.432, col, m["motor_cowl"], bevel=0.005, part="Motor")

    anode_pts = [(-0.010, -4.10), (0.014, -4.10), (0.008, -3.99), (-0.008, -3.99)]
    build_prism("Motor_TrimTabAnode", anode_pts, 0.372, 0.418, col, m["motor_silver"], bevel=0.002, part="Motor")

    # Long Swept Hydrofoil Gearcase Strut connecting AV plate down into 64 cm torpedo barrel
    strut_bot = geo.fillet_poly([(-0.058, -3.96), (0.058, -3.96), (0.048, -3.52), (0.0, -3.40), (-0.048, -3.52)], 0.014, seg=3)
    strut_top = geo.fillet_poly([(-0.078, -3.98), (0.078, -3.98), (0.068, -3.50), (0.0, -3.42), (-0.068, -3.50)], 0.016, seg=3)
    gc_strut = geo.loft(
        "Motor_GearcaseStrut",
        [[Vector((x, y, 0.215)) for (x, y) in strut_bot], [Vector((x, y, 0.420)) for (x, y) in strut_top]],
        col,
        m["motor_cowl"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=42.0,
        recalc=True,
    )
    finalize_mesh(gc_strut, part="Motor", sharp_angle=42.0)

    for side, sx in (("Port", -1.0), ("Starboard", 1.0)):
        build_box(
            f"Motor_WaterIntake_{side}",
            (0.016, 0.110, 0.062),
            col,
            m["rubber_black"],
            location=(sx * 0.053, -3.60, 0.305),
            rotation_deg=(0.0, 0.0, -sx * 7.0),
            bevel=0.003,
            part="Motor",
        )

    # Full 0.64 m (25.2") Long Hydrodynamic 300HP Bullet Torpedo Gearcase (Y = -3.99 .. -3.35 m, dia = 152 mm!)
    torpedo_prof = [
        (0.012, 0.000),    # closed aft diaphragm inside exhaust hub
        (0.062, 0.004),    # aft prop-ring lip (Y = -3.986)
        (0.072, 0.055),
        (0.076, 0.175),    # full 152 mm 300HP V8 gearcase barrel
        (0.076, 0.385),
        (0.068, 0.480),
        (0.050, 0.555),
        (0.026, 0.608),
        (0.006, 0.640),    # sleek high-speed parabolic nosecone at Y = -3.350!
    ]
    torpedo = geo.lathe(
        "Motor_BulletTorpedo",
        torpedo_prof,
        col,
        m["motor_cowl"],
        seg=40,
        center=(0.0, -3.990, 0.215),
        axis=(0.0, 1.0, 0.0),
        cap_start=True,
        cap_end=True,
        sharp_angle=52.0,
    )
    finalize_mesh(torpedo, part="Motor", sharp_angle=52.0)

    # Deep Swept NACA Hydrofoil Skeg resting cleanly at Z = 0.0000 m (wide 300HP chord!)
    skeg_top = [
        Vector((0.0, -3.50, 0.230)),
        Vector((0.015, -3.65, 0.230)),
        Vector((0.009, -3.94, 0.230)),
        Vector((0.0, -3.97, 0.230)),
        Vector((-0.009, -3.94, 0.230)),
        Vector((-0.015, -3.65, 0.230)),
    ]
    skeg_mid = [
        Vector((0.0, -3.66, 0.095)),
        Vector((0.010, -3.76, 0.095)),
        Vector((0.007, -3.95, 0.095)),
        Vector((0.0, -3.975, 0.095)),
        Vector((-0.007, -3.95, 0.095)),
        Vector((-0.010, -3.76, 0.095)),
    ]
    skeg_bot = [
        Vector((0.0, -3.76, 0.000)),
        Vector((0.005, -3.82, 0.000)),
        Vector((0.004, -3.95, 0.000)),
        Vector((0.0, -3.97, 0.000)),
        Vector((-0.004, -3.95, 0.000)),
        Vector((-0.005, -3.82, 0.000)),
    ]
    skeg = geo.loft(
        "Motor_SweptSkeg",
        [skeg_bot, skeg_mid, skeg_top],
        col,
        m["motor_cowl"],
        closed=True,
        cap_start=True,
        cap_end=True,
        smooth=True,
        sharp_angle=35.0,
        recalc=True,
    )
    finalize_mesh(skeg, part="Motor", sharp_angle=35.0)

    # 4. CAD 408 mm (16.1") 3-Blade Wide-Ear Stainless Offshore Prop (rotated 28 deg so all 3 blades pop clearly!)
    import_cad_part(
        "outboard_prop.glb",
        "Prop_Offshore3Blade",
        col,
        m["prop_steel"],
        location=(0.0, -4.025, 0.215),
        rotation_deg=(0.0, 28.0, 0.0),
        part="Prop",
    )


# ---------------------------------------------------------------------------
# 9. Roblox BoatService Sockets, Driver Hand IK Targets, Seats & Servo Hinges
# ---------------------------------------------------------------------------
def build_sockets_and_seats(col: bpy.types.Collection) -> None:
    """Create Roblox BoatService sockets, IK hand grips, particle emitters, seats, and servo pivots."""
    core.seat("Driver", col, location=(-0.20, -1.04, 1.455), yaw_deg=0.0, driver=True, size=(2.0, 1.0, 2.0))
    core.seat("CoPilot", col, location=(0.22, -1.04, 1.455), yaw_deg=0.0, driver=False, size=(1.8, 1.0, 1.8))
    core.seat("FwdLounge", col, location=(0.0, 1.08, 1.275), yaw_deg=0.0, driver=False, size=(2.0, 1.0, 1.8))
    core.seat("BowPort", col, location=(-0.66, 2.05, 1.235), yaw_deg=90.0, driver=False, size=(1.6, 1.0, 1.6))
    core.seat("BowStbd", col, location=(0.66, 2.05, 1.235), yaw_deg=-90.0, driver=False, size=(1.6, 1.0, 1.6))
    core.seat("AftBench", col, location=(0.0, -2.34, 1.285), yaw_deg=0.0, driver=False, size=(2.2, 1.0, 1.8))

    # Exact attachment names expected by BoatService.luau
    core.socket("BoatCenterAttachment", col, location=(0.0, 0.05, WATERLINE_Z))
    core.socket("CenterAttachment", col, location=(0.0, 0.05, WATERLINE_Z))
    core.socket("LeftHand", col, location=(-0.35, -0.59, 1.634), parent_part="Steering")
    core.socket("RightHand", col, location=(0.24, -0.415, 1.66), parent_part="Throttle")

    # Spray & prop-wash emitters
    core.socket("BowSprayPort", col, location=(-0.74, 2.45, WATERLINE_Z + 0.05), emitter=True)
    core.socket("BowSprayStbd", col, location=(0.74, 2.45, WATERLINE_Z + 0.05), emitter=True)
    core.socket("PropWash", col, location=(0.0, -4.22, 0.215), emitter=True)
    core.socket("WakeCenter", col, location=(0.0, -3.52, WATERLINE_Z), emitter=True)

    # Servo hinge sockets (Steering column, Throttle binnacle drum, Outboard steering pivot, Prop shaft)
    core.socket("HingeSteering", col, location=(-0.20, -0.548, 1.586), rotation=(math.radians(-65.0), 0.0, 0.0), hinge_only=True)
    core.socket("HingeThrottle", col, location=(0.215, -0.441, 1.534), rotation=(0.0, math.radians(-90.0), 0.0), hinge_only=True)
    core.socket("HingeMotor", col, location=(0.0, Y_TRANSOM - 0.18, 0.90), rotation=(0.0, 0.0, 0.0), hinge_only=True)
    core.socket("HingeProp", col, location=(0.0, -4.025, 0.215), rotation=(math.radians(90.0), 0.0, 0.0), hinge_only=True)


# ---------------------------------------------------------------------------
# 10. High-Res Close-Up Studio Verification Renders
# ---------------------------------------------------------------------------
def render_closeup_verification_views(meshes: list[bpy.types.Object], out_dir: str) -> list[str]:
    """Render 5 high-resolution Cycles GPU studio shots including close-ups of Outboard & Helm."""
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    saved_world = sc.world
    saved_cam = sc.camera

    studio_col = render.setup_studio(meshes, backdrop="product")
    try:
        from vflib import bake as _vf_bake

        _vf_bake.enable_cycles_gpu(sc, use_denoising=True)
    except Exception:
        sc.render.engine = "CYCLES"
        sc.cycles.use_denoising = True
        try:
            sc.render.threads_mode = "FIXED"
            sc.render.threads = min(8, max(2, (os.cpu_count() or 8) // 2))
            sc.cycles.use_auto_tile = True
            sc.cycles.tile_size = 512
        except Exception:
            pass
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for dt in ("OPTIX", "CUDA"):
                try:
                    prefs.compute_device_type = dt
                    prefs.get_devices()
                    devs = [d for d in prefs.devices if d.type == dt]
                    if devs:
                        for d in prefs.devices:
                            d.use = (d.type == dt)
                        sc.cycles.device = "GPU"
                        if dt == "OPTIX":
                            try:
                                sc.cycles.denoising_use_gpu = True
                            except Exception:
                                pass
                            sc.cycles.denoiser = "OPTIX"
                        else:
                            sc.cycles.denoiser = "OPENIMAGEDENOISE"
                            sc.cycles.denoising_use_gpu = True
                        break
                except Exception:
                    continue
        except Exception:
            pass
    sc.cycles.samples = 96

    sc.render.resolution_x = 1600
    sc.render.resolution_y = 1000
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"

    cam_data = bpy.data.cameras.new("SR_VerifyCam")
    cam = bpy.data.objects.new("SR_VerifyCam", cam_data)
    studio_col.objects.link(cam)
    sc.camera = cam

    # (filename, cam_loc, look_target, lens_mm) â€” full-boat hero/profile + symmetrical stern/helm & full-hull underbody!
    shots = [
        ("hero.png", (9.10, 8.75, 3.68), (0.0, 0.35, 1.38), 45.0),
        ("stern_outboard.png", (0.85, -7.15, 1.22), (0.0, -3.65, 0.94), 45.0),
        ("cockpit_helm.png", (0.42, -2.18, 2.28), (0.0, 0.12, 1.50), 33.0),
        ("bow_quarter.png", (6.85, 9.25, 2.58), (0.0, 1.05, 1.35), 46.0),
        ("side_profile.png", (15.20, 0.25, 1.45), (0.0, 0.25, 1.38), 50.0),
        ("underbody_hull.png", (7.65, 6.45, -2.55), (0.0, 0.55, 0.65), 39.0),
    ]

    bot_light_data = bpy.data.lights.new("SR_BottomFill", "AREA")
    bot_light_data.energy = 1200.0
    bot_light_data.size = 6.0
    bot_light = bpy.data.objects.new("SR_BottomFill", bot_light_data)
    bot_light.location = (3.5, 2.0, -3.2)
    bot_light.rotation_euler = (Vector((0.0, 0.2, 0.7)) - bot_light.location).to_track_quat("-Z", "Y").to_euler()
    studio_col.objects.link(bot_light)
    bot_light.hide_render = True

    rendered: list[str] = []
    try:
        backdrop_meshes = [o for o in studio_col.objects if o.type == "MESH"]
        for fname, loc, tgt, lens in shots:
            is_bot = fname == "underbody_hull.png"
            for bm_o in backdrop_meshes:
                bm_o.hide_render = is_bot
            bot_light.hide_render = not is_bot
            cam.location = Vector(loc)
            cam.data.lens = lens
            d = Vector(tgt) - Vector(loc)
            cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
            cam.data.clip_start = 0.05
            cam.data.clip_end = 120.0
            out_path = os.path.join(out_dir, fname)
            try:
                from vflib import bake as _vf_bake

                _vf_bake.render_still_safe(sc, out_path)
            except Exception:
                sc.render.filepath = out_path
                bpy.ops.render.render(write_still=True)
            rendered.append(out_path)
            core.log("rendered close-up", out_path)
    finally:
        sc.camera = saved_cam
        if saved_world is not None:
            sc.world = saved_world
        core.clear_collection(studio_col)
        bpy.data.collections.remove(studio_col)

    return rendered


def _safe_copy(src: str, dst: str) -> bool:
    try:
        from vflib import bake as _vf_bake

        _vf_bake._atomic_copy_fsync(src, dst)
        return True
    except PermissionError:
        core.log(f"WARNING: file locked by open viewer, skipped overwrite of {dst}")
        return False
    except Exception:
        pass
    try:
        abs_dst = os.path.abspath(dst)
        dst_dir = os.path.dirname(abs_dst)
        os.makedirs(dst_dir, exist_ok=True)
        staged = os.path.join(dst_dir, f".__vf_stage_{os.getpid()}_{os.path.basename(abs_dst)}")
        try:
            shutil.copy2(src, staged)
            try:
                with open(staged, "rb+") as fh:
                    fh.flush()
                    os.fsync(fh.fileno())
            except OSError:
                pass
            os.replace(staged, abs_dst)
        finally:
            if os.path.exists(staged):
                try:
                    os.remove(staged)
                except OSError:
                    pass
        return True
    except PermissionError:
        core.log(f"WARNING: file locked by open viewer, skipped overwrite of {dst}")
        return False


def verify_shell_integrity(meshes: list[bpy.types.Object]) -> None:
    """Hard BVH shell-containment & self-intersection gate: FAILS build if ANYTHING clips through hull shell!"""
    from mathutils.bvhtree import BVHTree

    hull_ob = bpy.data.objects.get("Hull_DeepV")
    if hull_ob is None:
        raise RuntimeError("Hull_DeepV missing")

    # 1. Check Hull_DeepV non-adjacent self-intersections
    bm_h = bmesh.new()
    bm_h.from_mesh(hull_ob.data)
    bmesh.ops.triangulate(bm_h, faces=bm_h.faces[:])
    bm_h.faces.ensure_lookup_table()
    bvh_h = BVHTree.FromBMesh(bm_h, epsilon=0.0)
    self_x = 0
    for i, j in bvh_h.overlap(bvh_h):
        if i < j:
            vi = {v.index for v in bm_h.faces[i].verts}
            vj = {v.index for v in bm_h.faces[j].verts}
            if not (vi & vj):
                self_x += 1
    bm_h.free()
    if self_x > 0:
        raise RuntimeError(f"SHELL INTEGRITY FAIL: Hull_DeepV has {self_x} self-intersecting triangle pairs!")

    # 2. Build outer-skin BVH and inner-liner BVH of Hull_DeepV
    def _subset_hull_bvh(want_outer: bool) -> BVHTree:
        bm = bmesh.new()
        bm.from_mesh(hull_ob.data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.faces.ensure_lookup_table()
        to_del = []
        for f in bm.faces:
            c = f.calc_center_median()
            n = f.normal
            t_c = _exact_t_at_yz(c.y, c.z)
            ow = hull_outer_x_at_z(t_c, c.z)
            sz = hull_sheer_z(t_c)
            is_outer = (c.y < Y_TRANSOM + 0.05 and n.y < -0.5) or (
                abs(c.x) >= ow - 0.03 and c.z < sz - 0.015 and (abs(n.x) > 0.25 or n.z < -0.2 or n.y > 0.25)
            )
            is_top_cap = (c.z >= sz - 0.02) or (t_c <= 0.026 and c.z >= MOTORWELL_LIP_Z - 0.022 and n.z > 0.6)
            keep = is_outer if want_outer else (not is_outer and not is_top_cap)
            if not keep:
                to_del.append(f)
        bmesh.ops.delete(bm, geom=to_del, context="FACES")
        tree = BVHTree.FromBMesh(bm, epsilon=0.0)
        bm.free()
        return tree

    outer_bvh = _subset_hull_bvh(True)
    inner_bvh = _subset_hull_bvh(False)

    exterior_ok = (
        "Hull_DeepV",
        "Hull_LiftingStrake",
        "HullPaint_",
        "Trim_RubRail",
        "Trim_BowRoller",
        "Trim_BowSheave",
        "Trim_Anchor",
        "Trim_BowEye",
        "Trim_SternEye",
        "Trim_Tab",
        "Trim_SwimLadder",
        "Deck_Swim",
        "Light_SharkBezel",
        "Light_NavLens",
        "Motor_",
        "Prop_",
    )

    breach_msgs: list[str] = []
    for ob in meshes:
        if ob.name == "Hull_DeepV":
            continue
        bmo = bmesh.new()
        bmo.from_mesh(ob.data)
        bmo.transform(ob.matrix_world)
        bmesh.ops.triangulate(bmo, faces=bmo.faces[:])
        ob_bvh = BVHTree.FromBMesh(bmo, epsilon=0.0)
        bmo.free()

        if not ob.name.startswith(exterior_ok):
            ov_out = ob_bvh.overlap(outer_bvh)
            if ov_out:
                breach_msgs.append(f"INTERIOR PART PIERCES OUTER HULL SHELL: {ob.name} ({len(ov_out)} pairs)")
            for v in ob.data.vertices:
                co = ob.matrix_world @ v.co
                t_v = _exact_t_at_yz(co.y, co.z)
                sz_v = hull_sheer_z(t_v)
                if co.z <= sz_v - 0.01:
                    ox_v = hull_outer_x_at_z(t_v, co.z)
                    if abs(co.x) > ox_v - 0.004 or co.z < hull_keel_z(t_v) + 0.004:
                        breach_msgs.append(
                            f"INTERIOR VERTEX OUTSIDE HULL SHELL: {ob.name} at ({co.x:.3f}, {co.y:.3f}, {co.z:.3f}) vs outer_x={ox_v:.3f}"
                        )
                        break

        if ob.name.startswith(("HullPaint_", "Light_SharkBezel", "Light_NavLens", "Trim_Anchor", "Trim_RubRail", "Motor_Transom", "Motor_Clamp")):
            ov_in = ob_bvh.overlap(inner_bvh)
            if ov_in:
                breach_msgs.append(f"EXTERIOR PART PIERCES INNER COCKPIT LINER: {ob.name} ({len(ov_in)} pairs)")

    if breach_msgs:
        for msg in breach_msgs:
            core.log("SHELL BREACH:", msg)
        raise RuntimeError(f"SHELL INTEGRITY FAIL ({len(breach_msgs)} issues): {breach_msgs[:5]}")
    core.log("SHELL INTEGRITY PASS: 0 outer-shell breaches, 0 inner-liner breaches, 0 hull self-intersections!")


def build_all() -> tuple[bpy.types.Collection, list[bpy.types.Object]]:
    core.ensure_object_mode()
    for name in ("Cube", "Light", "Camera"):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            bpy.data.objects.remove(ob, do_unlink=True)

    col = core.fresh_collection(COLL_NAME)
    m = create_materials()

    build_hull_and_stripe(col, m)
    build_deck_and_seating(col, m)
    build_console_and_windshield(col, m)
    build_leaning_post(col, m)
    build_ttop_and_radar(col, m)
    build_trim_and_cad_hardware(col, m)
    build_lights(col, m)
    build_helm_controls_and_outboard(col, m)
    build_sockets_and_seats(col)

    meshes = core.objects_in(col, types=("MESH",))
    bpy.context.view_layer.update()

    verify_shell_integrity(meshes)
    gameready.validate(meshes, max_tris=20000, verbose=True)
    totals = gameready.budget(meshes)
    core.log("sc_part budgets:", totals)
    return col, meshes


def save_and_export(col: bpy.types.Collection, meshes: list[bpy.types.Object], render_views: bool = False) -> None:
    os.makedirs(THIS_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(DESIGN_OUTPUT_DIR, exist_ok=True)

    for emp in core.objects_in(col, types=("EMPTY",)):
        emp.empty_display_size = 0.06
    render.frame_viewport(meshes)
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == "VIEW_3D":
                for sp in area.spaces:
                    if sp.type == "VIEW_3D":
                        sp.shading.type = "MATERIAL"
                        sp.overlay.show_extras = False
    blend_path = os.path.join(THIS_DIR, "sunrunner_24.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    core.log("saved", blend_path)

    glb_path = os.path.join(THIS_DIR, "sunrunner_24.glb")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.export_scene.gltf(filepath=glb_path, use_selection=True, export_format="GLB", export_apply=True)
    for o in meshes:
        o.select_set(False)
    core.log("exported", glb_path)

    parts_spec = export.parts_from_collection(col)
    collide_parts = {"Hull", "Deck", "Console", "LeaningPost", "TTop"}
    for spec in parts_spec:
        spec["collide"] = spec["name"] in collide_parts
        if spec["name"] == "PaintPrimary":
            spec["material"] = "SmoothPlastic"
        elif spec["name"] == "Glass":
            spec["transparency"] = 0.55

    lo, hi = core.world_bbox(meshes)
    hinges = [
        dict(name="Steering", socket="HingeSteering", part0="@primary", part1="Steering", actuator="Servo", lower=-180, upper=180, speed=8),
        dict(name="Throttle", socket="HingeThrottle", part0="@primary", part1="Throttle", actuator="Servo", lower=-45, upper=45, speed=6),
        dict(name="Motor", socket="HingeMotor", part0="@primary", part1="Motor", actuator="Servo", lower=-38, upper=38, speed=6),
        dict(name="Prop", socket="HingeProp", part0="Motor", part1="Prop", actuator="Motor", torque=1e6),
    ]
    export.export_roblox(
        "Sunrunner24",
        EXPORT_DIR,
        parts=parts_spec,
        source_collection=col,
        primary=dict(name="Boat", center=(lo + hi) * 0.5, size=hi - lo),
        hinges=hinges,
        attributes={"BoatType": "CenterConsole", "MaxSpeed": 46},
        tags=["Boat"],
        reference="Hull",
    )

    _safe_copy(blend_path, os.path.join(DESIGN_OUTPUT_DIR, "sunrunner_24.blend"))
    _safe_copy(glb_path, os.path.join(DESIGN_OUTPUT_DIR, "sunrunner_24.glb"))

    if render_views:
        shots = render_closeup_verification_views(meshes, RENDERS_DIR)
        if shots:
            _safe_copy(shots[0], os.path.join(DESIGN_OUTPUT_DIR, "blender-render-check.png"))
            for sp in shots:
                _safe_copy(sp, os.path.join(DESIGN_OUTPUT_DIR, f"sunrunner24_{os.path.basename(sp)}"))


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    do_renders = "--render-views" in argv
    col, meshes = build_all()
    save_and_export(col, meshes, render_views=do_renders)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

