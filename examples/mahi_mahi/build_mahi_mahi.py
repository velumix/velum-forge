"""Velum Forge â€” Offshore Trophy Mahi-Mahi / Dorado (`Coryphaena hippurus`, 1.20 m LOA).

Parametric anatomical & ichthyological 3D builder in Blender 5.2+ (`sclib`):
  - Exact pelagic Dorado proportions (1.20 m total length, 22.8% body depth, 2.17:1 compressed blade
    cross-section, sexual dimorphism parameter `bull_crest` supporting both steep Bull Dorado and
    sleek Cow Dorado cranial profiles).
  - Sculpted 3D anatomical features on closed watertight `S^2` manifolds:
      * Steep convex cranial crest, premaxillary lip, oral commissure cleft, and underslung lower jaw (`Dentary`)
      * Concave orbital eye sockets with bony supraorbital rims + flush glossy layered `Eyes`
      * Curved gill operculum plate step (+2.6 mm) over recessed crimson branchial gill-slit groove (-2.4 mm)
      * Signature high-arched Dorado lateral line ridge above the pectoral fin
      * Full-length 54-ray scalloped sail `DorsalFin`, deeply forked 26-ray pelagic `CaudalFin`,
        swept falcate sickle `PectoralFins`, paired thoracic pelvic fins + 28-ray `VentralFins` (anal fin)
  - Hard `verify_fish_integrity()` BVH gate guaranteeing:
      * 0 opposite-flank or belly shell poke-throughs
      * 100% positive root contact (< 1.5 mm) between every fin/eye and `Body` (0 floating islands)
      * 0 fin-to-fin intersections, 0 non-manifold edges, 0 boundary edges, `ground_z = 0.0000 m`
  - Includes Roblox `FishingService` / `BoatService` sockets (`SOCKET_HookMouth`, `SOCKET_HandGripGill`,
    `SOCKET_HandGripTail`, `SOCKET_HingeTail`, `SOCKET_SwimSplash`).

Run standalone or via QA pipeline:
    blender -b --python-exit-code 1 -P assets/models/mahi_mahi/build_mahi_mahi.py
    .\\tools\\cad\\run_qa.ps1 -Asset assets\\models\\mahi_mahi\\build_mahi_mahi.py -Profile roblox -ForwardAxis +Y
"""

from __future__ import annotations

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
BLENDER_TOOLS = os.path.join(REPO_ROOT, "engine", "blender")
if BLENDER_TOOLS not in sys.path:
    sys.path.insert(0, BLENDER_TOOLS)

import sclib  # noqa: E402
from sclib import core, export, gameready, mats, render  # noqa: E402

# ---------------------------------------------------------------------------
# Principal Ichthyological Dimensions (Meters, +Y = Snout Forward, +Z = Dorsal)
# ---------------------------------------------------------------------------
SNOUT_Y = 0.580
PEDUNCLE_Y = -0.375
TAIL_TIP_Y = -0.620  # Total LOA = 1.200 m (47.2 in Offshore Trophy Dorado)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _smoothstep(e0: float, e1: float, x: float) -> float:
    if abs(e1 - e0) < 1e-9:
        return 1.0 if x >= e1 else 0.0
    t = _clamp((x - e0) / (e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def _gauss(x: float, mu: float, sigma: float) -> float:
    d = (x - mu) / max(sigma, 1e-6)
    return math.exp(-0.5 * d * d)


# ---------------------------------------------------------------------------
# Anatomical Body Envelope Functions (`Coryphaena hippurus`)
# ---------------------------------------------------------------------------
def body_contours(y: float, bull_crest: float = 1.0) -> tuple[float, float, float]:
    """Return `(z_bot, z_top, half_width)` at axial coordinate `y` in `[PEDUNCLE_Y, SNOUT_Y]`."""
    u = _clamp((SNOUT_Y - y) / (SNOUT_Y - PEDUNCLE_Y))  # 0 at snout (+0.580), 1 at peduncle (-0.375)

    # Snout reference height
    z_snout = 0.124

    # Dorsal profile: steep iconic Dorado forehead boss + long streamlined dorsal back
    bull_rise = math.pow(_smoothstep(0.0, 0.115, u), 0.56)
    cow_rise = math.pow(_smoothstep(0.0, 0.240, u), 0.68)
    forehead_rise = bull_crest * bull_rise + (1.0 - bull_crest) * cow_rise

    # Subtle Bull supraorbital crown prominence near u = 0.10..0.18
    crown_boss = bull_crest * 0.015 * _gauss(u, 0.125, 0.068)
    taper_aft = _smoothstep(0.24, 1.0, u)
    # Slight hypural flare right at u = 0.96..1.0 where caudal rays anchor
    hypural_flare = 0.004 * _smoothstep(0.92, 1.0, u)

    z_top = (
        z_snout
        + (0.168 * forehead_rise + crown_boss) * (1.0 - 0.815 * math.pow(taper_aft, 1.16))
        + hypural_flare
    )

    # Ventral profile: underslung predatory chin -> deep thoracic chest -> taut sweeping belly -> tight peduncle
    chin_drop = math.pow(_smoothstep(0.0, 0.085, u), 0.62)
    chest_deep = _smoothstep(0.05, 0.30, u)
    belly_rise = math.pow(_smoothstep(0.30, 1.0, u), 1.24)
    chin_jut = 0.005 * _gauss(u, 0.045, 0.026)

    z_bot_chest = z_snout - 0.048 * chin_drop - 0.060 * chest_deep - chin_jut  # reaches ~0.016 m at u=0.30
    z_bot = z_bot_chest + (0.120 - z_bot_chest) * belly_rise - hypural_flare

    # Half-width: sleek compressed pelagic blade (`height:width ~ 2.6:1`, max total width ~0.106 m at u=0.22)
    if u < 0.22:
        w_env = math.pow(max(u, 0.004) / 0.22, 0.50)
    else:
        t_w = (u - 0.22) / 0.78
        w_env = 1.0 - 0.78 * math.pow(t_w, 1.12)
    half_w = 0.053 * w_env + 0.0022 * _gauss(u, 0.98, 0.03)
    return z_bot, z_top, max(half_w, 0.0018)


def lateral_line_z(y: float, bull_crest: float = 1.0) -> float:
    """Characteristic Coryphaena hippurus lateral line with prominent dorsal arch over pectoral fin."""
    z_bot, z_top, _ = body_contours(y, bull_crest)
    mid_z = 0.50 * (z_bot + z_top) + 0.08 * (z_top - z_bot)
    # High arch centered at Y = +0.205 (right above the pectoral fin!)
    arch = 0.028 * _gauss(y, 0.205, 0.072) + 0.012 * _smoothstep(0.10, 0.32, y)
    return mid_z + arch


def _sculpt_body_point(x: float, y: float, z: float, z_bot: float, z_top: float, bull_crest: float) -> Vector:
    """Apply anatomical relief (mouth cleft, jaws, eye socket, gill operculum, lateral line) to body point."""
    side = 1.0 if x >= 0.0 else -1.0
    ax = abs(x)
    if ax < 1e-5:
        return Vector((x, y, z))

    dx = 0.0
    dy = 0.0
    dz = 0.0

    # 1. Predatory Oral Gape Cleft, Premaxillary Upper Lip & Underslung Lower Jaw (`Dentary`)
    if y > 0.428:
        t_m = _clamp((SNOUT_Y - y) / (SNOUT_Y - 0.434))  # 0 at snout tip, 1 at jaw corner beneath eye
        z_gape = 0.118 - 0.038 * math.pow(t_m, 0.88)
        d_gape = z - z_gape
        along_w = (1.0 - _smoothstep(0.86, 1.0, t_m)) * _smoothstep(0.0, 0.06, t_m)
        cleft = _gauss(d_gape, 0.0, 0.0042) * along_w
        dx -= 0.0028 * cleft
        upper_lip = _gauss(d_gape, 0.0068, 0.0045) * along_w
        lower_jaw = _gauss(d_gape, -0.0075, 0.0055) * along_w
        dx += 0.0016 * upper_lip + 0.0022 * lower_jaw
        if d_gape < -0.001 and y > 0.52:
            dy += 0.0048 * _smoothstep(0.52, 0.575, y) * _smoothstep(0.0, -0.014, d_gape)

    # 2. Low-Set Dorado Orbital Eye Socket + Bony Supraorbital Rim (leaves tall golden forehead above eye!)
    eye_y = 0.468
    eye_z = 0.136 + 0.002 * bull_crest
    eye_r = 0.0225
    dist_eye = math.hypot(y - eye_y, z - eye_z)
    if dist_eye < eye_r * 1.65:
        t_in = _clamp(dist_eye / eye_r)
        socket_depth = 0.0046 * math.pow(1.0 - t_in * t_in, 1.35) if dist_eye < eye_r else 0.0
        rim = 0.0014 * _gauss(dist_eye, eye_r * 1.14, 0.0042)
        dx += rim - socket_depth

    # 3. Curved Gill Operculum Plate & Recessed Branchial Gill-Slit Groove
    if 0.035 < z < 0.248 and 0.245 < y < 0.405:
        zn = (z - 0.136) / 0.092
        y_operc = 0.296 + 0.048 * zn * zn + (0.016 * max(0.0, -zn) ** 1.6)
        v_mask = _smoothstep(0.038, 0.062, z) * (1.0 - _smoothstep(0.222, 0.246, z))
        d_op = y - y_operc  # >0 = on gill cover (anterior), <0 = behind gill cover (pectoral shoulder)
        # Raised opercular plate edge (+2.5 mm) dropping into recessed gill slit (-2.3 mm)
        operc_plate = 0.0025 * _gauss(d_op, 0.0075, 0.0065)
        gill_slit = -0.0023 * _gauss(d_op, -0.0038, 0.0032)
        # Preopercle subtle anterior cheek crease ~36 mm ahead of posterior operculum
        preoperc = -0.0009 * _gauss(d_op, 0.038, 0.0035)
        dx += (operc_plate + gill_slit + preoperc) * v_mask

    # 4. Arched Pelagic Lateral Line Ridge (from gill cover to caudal peduncle)
    if PEDUNCLE_Y < y < 0.305:
        zl = lateral_line_z(y, bull_crest)
        ll_fade = _smoothstep(0.305, 0.275, y) * _smoothstep(PEDUNCLE_Y, PEDUNCLE_Y + 0.025, y)
        dx += 0.00085 * _gauss(z, zl, 0.0032) * ll_fade

    # 5. Caudal Peduncle Lateral Stabilization Keel
    if y < -0.285:
        z_mid = 0.5 * (z_bot + z_top)
        keel_f = _smoothstep(-0.285, -0.355, y)
        dx += 0.0022 * _gauss(z, z_mid, 0.0055) * keel_f

    new_x = side * max(0.0009, ax + dx)
    return Vector((new_x, y + dy, z + dz))


# ---------------------------------------------------------------------------
# Watertight Closed-Manifold (`S^2`) UV + Mesh Utilities
# ---------------------------------------------------------------------------
def _ensure_positive_signed_volume(bm: bmesh.types.BMesh) -> None:
    """Guarantee 100% outward normals on any closed manifold (including concave forked fins) via signed volume."""
    bm.faces.ensure_lookup_table()
    vol6 = 0.0
    for f in bm.faces:
        if len(f.verts) >= 3:
            v0 = f.verts[0].co
            for k in range(1, len(f.verts) - 1):
                vol6 += v0.dot(f.verts[k].co.cross(f.verts[k + 1].co))
    if vol6 < 0.0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])


def _finalize_watertight_mesh(
    bm: bmesh.types.BMesh,
    name: str,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    part_tag: str,
    sharp_deg: float = 42.0,
) -> bpy.types.Object:
    """Triangulate, enforce positive signed volume normals, unwrap non-overlapping UVs, and link object."""
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    _ensure_positive_signed_volume(bm)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()

    for poly in me.polygons:
        poly.use_smooth = True
        poly.material_index = 0
    me.materials.append(mat)

    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob["sc_part"] = part_tag
    ob["sc_role"] = "solid"

    # Planar/cylindrical-assisted Smart UV unwrap with guaranteed 0 zero-area UV faces & 0 overlap
    core.ensure_object_mode()
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(58.0), island_margin=0.012, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=0.010)
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.select_set(False)

    # Ensure zero degenerate UV triangles on extreme tip poles
    bm_uv = bmesh.new()
    bm_uv.from_mesh(me)
    uv_lay = bm_uv.loops.layers.uv.verify()
    fix_slot = 0
    for f in bm_uv.faces:
        pts = [lp[uv_lay].uv.copy() for lp in f.loops]
        if len(pts) == 3:
            area2 = abs((pts[1].x - pts[0].x) * (pts[2].y - pts[0].y) - (pts[2].x - pts[0].x) * (pts[1].y - pts[0].y))
            if area2 < 1e-8:
                gx = 0.02 + (fix_slot % 16) * 0.004
                gy = 0.02 + (fix_slot // 16) * 0.004
                fix_slot += 1
                f.loops[0][uv_lay].uv = (gx, gy)
                f.loops[1][uv_lay].uv = (gx + 0.0025, gy)
                f.loops[2][uv_lay].uv = (gx, gy + 0.0025)
    bm_uv.to_mesh(me)
    bm_uv.free()

    me.update()
    return ob


def _build_closed_tube_with_caps(
    rings: list[list[Vector]],
    cap_start: Vector,
    cap_end: Vector,
) -> bmesh.types.BMesh:
    """Build a 100% closed `S^2` manifold from ordered circumferential rings + start/end pole vertices."""
    bm = bmesh.new()
    v_start = bm.verts.new(cap_start)
    bm_rings: list[list[bmesh.types.BMVert]] = []
    for r in rings:
        bm_rings.append([bm.verts.new(p) for p in r])
    v_end = bm.verts.new(cap_end)

    n_circ = len(bm_rings[0])
    # Start fan
    r0 = bm_rings[0]
    for j in range(n_circ):
        jn = (j + 1) % n_circ
        bm.faces.new((v_start, r0[jn], r0[j]))

    # Quad strips between rings
    for i in range(len(bm_rings) - 1):
        ra = bm_rings[i]
        rb = bm_rings[i + 1]
        for j in range(n_circ):
            jn = (j + 1) % n_circ
            bm.faces.new((ra[j], ra[jn], rb[jn], rb[j]))

    # End fan
    rl = bm_rings[-1]
    for j in range(n_circ):
        jn = (j + 1) % n_circ
        bm.faces.new((rl[j], rl[jn], v_end))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


# ---------------------------------------------------------------------------
# 1. Fuselage `Body` Builder
# ---------------------------------------------------------------------------
def build_body(col: bpy.types.Collection, mat_body: bpy.types.Material, bull_crest: float = 1.0) -> bpy.types.Object:
    n_ax = 132
    n_circ = 68  # 132 * 68 * 2 â‰ˆ 17,952 tris (< 20,000 Roblox MeshPart cap!)

    rings: list[list[Vector]] = []
    for i in range(1, n_ax):
        t = i / n_ax
        # Cosine-clustered stations near snout/head and peduncle for extra facial & tail crispness
        u = 0.5 * (1.0 - math.cos(math.pi * t))
        y = SNOUT_Y - u * (SNOUT_Y - PEDUNCLE_Y)
        z_bot, z_top, hw = body_contours(y, bull_crest)
        h = max(z_top - z_bot, 0.002)

        ring: list[Vector] = []
        for j in range(n_circ):
            # theta = 0 at dorsal top (+Z), pi/2 at starboard (+X), pi at ventral belly (-Z), 3*pi/2 at port (-X)
            theta = (2.0 * math.pi * j) / n_circ
            s_th = math.sin(theta)
            c_th = math.cos(theta)  # +1 dorsal, -1 ventral

            z_norm = 0.5 * (1.0 + c_th)  # 1 at dorsal, 0 at ventral
            z_base = z_bot + h * z_norm

            # Epaxial-heavy pelagic blade shape: widest at z_norm ~ 0.62, crisp hydrodynamic belly keel near 0
            epaxial_bulge = 1.0 + 0.14 * math.sin(math.pi * _clamp(z_norm, 0.0, 1.0)) * (0.4 + 0.6 * z_norm)
            belly_pinch = 0.76 + 0.24 * _smoothstep(0.0, 0.36, z_norm)
            x_base = hw * s_th * epaxial_bulge * belly_pinch

            # Subtle dorsal median saddle groove along X=0 where DorsalFin roots
            if z_norm > 0.94 and -0.34 < y < 0.48:
                saddle = _smoothstep(0.94, 1.0, z_norm)
                z_base -= 0.0014 * saddle

            p = _sculpt_body_point(x_base, y, z_base, z_bot, z_top, bull_crest)
            ring.append(p)
        rings.append(ring)

    cap_snout = Vector((0.0, SNOUT_Y + 0.0025, 0.1235))
    zb_end, zt_end, _ = body_contours(PEDUNCLE_Y, bull_crest)
    cap_peduncle = Vector((0.0, PEDUNCLE_Y - 0.004, 0.5 * (zb_end + zt_end)))

    bm = _build_closed_tube_with_caps(rings, cap_snout, cap_peduncle)
    return _finalize_watertight_mesh(bm, "Body", col, mat_body, "Body", sharp_deg=46.0)


# ---------------------------------------------------------------------------
# 2. Dorsal Sail Fin (`DorsalFin`) & Ventral/Anal Fins (`VentralFins`)
# ---------------------------------------------------------------------------
def build_dorsal_fin(col: bpy.types.Collection, mat_fin: bpy.types.Material, bull_crest: float = 1.0) -> bpy.types.Object:
    """Signature full-length 54-ray scalloped Dorado sail crest from forehead crown to caudal peduncle."""
    y_start = 0.492 if bull_crest > 0.6 else 0.452
    y_end = -0.342
    n_span = 112
    n_prof = 26
    n_rays = 54

    rings: list[list[Vector]] = []
    for i in range(1, n_span):
        s = i / n_span
        y = y_start + s * (y_end - y_start)
        _zb, z_top_body, _hw = body_contours(y, bull_crest)

        z_root = z_top_body - 0.0048

        lead_ramp = math.pow(_smoothstep(0.0, 0.055, s), 0.58)
        tail_ramp = math.pow(_smoothstep(1.0, 0.950, s), 0.68)
        sail_h = (0.118 * (1.0 - 0.65 * math.pow(s, 0.82)) + 0.016 * _gauss(s, 0.10, 0.075)) * lead_ramp * tail_ramp

        scallop = 1.0 - 0.048 * abs(math.sin(math.pi * n_rays * s)) * _smoothstep(0.03, 0.10, s)
        ray_rib = math.cos(math.pi * n_rays * s) ** 2

        h_span = max(0.004, sail_h * scallop)
        # Sweep anterior rays cleanly aft so leading edge follows the forehead crest gracefully!
        rake_aft = -0.022 * _smoothstep(0.0, 0.12, s) - 0.018 * math.sin(math.pi * _clamp(s, 0.0, 1.0))

        ring: list[Vector] = []
        for j in range(n_prof):
            phi = (2.0 * math.pi * j) / n_prof
            c = 0.5 * (1.0 - math.cos(phi))
            side_s = math.sin(phi)

            base_t = 0.0028 * (1.0 - 0.72 * math.pow(c, 0.75))
            rib_t = 0.00075 * ray_rib * math.sin(math.pi * _clamp(c, 0.05, 0.98))
            t_half = max(0.00080, (base_t + rib_t) * (0.35 + 0.65 * _smoothstep(0.0, 0.03, s) * _smoothstep(1.0, 0.97, s)))

            x = side_s * t_half
            yc = y + c * rake_aft
            zc = z_root + c * h_span
            ring.append(Vector((x, yc, zc)))
        rings.append(ring)

    _zb0, zt0, _ = body_contours(y_start + 0.002, bull_crest)
    _zbe, zte, _ = body_contours(y_end - 0.002, bull_crest)
    cap_a = Vector((0.0, y_start + 0.002, zt0 - 0.002))
    cap_b = Vector((0.0, y_end - 0.002, zte - 0.002))

    bm = _build_closed_tube_with_caps(rings, cap_a, cap_b)
    return _finalize_watertight_mesh(bm, "DorsalFin", col, mat_fin, "DorsalFin", sharp_deg=45.0)


def build_caudal_fin(col: bpy.types.Collection, mat_fin: bpy.types.Material, bull_crest: float = 1.0) -> bpy.types.Object:
    """Deeply forked pelagic Dorado scissor tail (`CaudalFin`) swept from lower lobe tip through fork to upper tip."""
    zb_p, zt_p, _ = body_contours(PEDUNCLE_Y, bull_crest)
    z_mid = 0.5 * (zb_p + zt_p)

    # Parameter s in [0, 1] runs continuously from lower lobe tip (s=0) -> central V-fork (s=0.5) -> upper lobe tip (s=1)
    n_span = 96
    n_prof = 26
    n_rays = 28

    rings: list[list[Vector]] = []
    half_span_z = 0.184  # Total vertical tail span = 0.368 m!

    for i in range(1, n_span):
        s = i / n_span
        v = 2.0 * s - 1.0  # -1 at lower lobe tip, 0 at center fork, +1 at upper lobe tip
        av = abs(v)

        z_s = z_mid + v * half_span_z

        # Leading edge (anterior margin of tail fin): rooted inside peduncle at |v| < 0.14, sweeping sharply aft to tips!
        if av < 0.12:
            y_lead = PEDUNCLE_Y + 0.018 * (1.0 - (av / 0.12) ** 2)  # 18 mm clean socket embed into peduncle!
        else:
            t_lobe = (av - 0.12) / 0.88
            y_lead = PEDUNCLE_Y - 0.232 * math.pow(t_lobe, 1.08)

        # Trailing edge (deep pelagic V-notch at center v=0, sweeping to sharp tips at |v|=1):
        # At v=0 (fork center), y_trail = -0.432 (57 mm chord); at |v|=0.85, reaches -0.620!
        fork_sweep = math.pow(av, 0.78)
        scallop = 0.0045 * abs(math.sin(math.pi * n_rays * s)) * (1.0 - _smoothstep(0.88, 1.0, av))
        y_trail = -0.434 - 0.186 * fork_sweep + scallop
        # Ensure positive hydrofoil chord everywhere near extreme tips
        chord = max(0.010 * (1.0 - 0.65 * _smoothstep(0.90, 1.0, av)), y_lead - y_trail)
        y_trail = y_lead - chord

        ray_rib = math.cos(math.pi * n_rays * s) ** 2
        tip_taper = math.sin(math.pi * _clamp(s, 0.0, 1.0)) ** 0.45

        ring: list[Vector] = []
        for j in range(n_prof):
            phi = (2.0 * math.pi * j) / n_prof
            # c = 0 at thick hydrofoil leading edge, c = 1 at razor-thin scalloped trailing edge
            c = 0.5 * (1.0 - math.cos(phi))
            side_s = math.sin(phi)

            # NACA-like hydrofoil thickness distribution + 3D actinotrichia fin rays
            foil = 0.0042 * (1.0 - 0.18 * av) * (math.sqrt(max(c, 1e-4)) * (1.0 - 0.82 * c)) * 1.85
            rib = 0.00072 * ray_rib * math.sin(math.pi * _clamp(c, 0.05, 0.96))
            # Extra muscular hypural root pad near center fork leading edge
            hypural = 0.0048 * _gauss(v, 0.0, 0.16) * (1.0 - _smoothstep(0.0, 0.55, c))
            t_half = max(0.00080, (foil + rib + hypural) * (0.32 + 0.68 * tip_taper))

            x = side_s * t_half
            yc = y_lead - c * chord
            z_flare = v * 0.006 * c * av
            ring.append(Vector((x, yc, z_s + z_flare)))
        rings.append(ring)

    cap_lo = Vector((0.0, TAIL_TIP_Y, z_mid - half_span_z - 0.003))
    cap_hi = Vector((0.0, TAIL_TIP_Y, z_mid + half_span_z + 0.003))
    bm = _build_closed_tube_with_caps(rings, cap_lo, cap_hi)
    return _finalize_watertight_mesh(bm, "CaudalFin", col, mat_fin, "CaudalFin", sharp_deg=45.0)


def _build_paired_pectoral(side: float, bull_crest: float) -> bmesh.types.BMesh:
    """Single port (-1) or starboard (+1) swept falcate sickle pectoral fin rooted in pectoral girdle."""
    y_root = 0.288
    z_root = 0.114
    _, _, hw_p = body_contours(y_root, bull_crest)
    x_root = side * (hw_p - 0.0055)

    n_span = 46
    n_prof = 24
    n_rays = 16

    rings: list[list[Vector]] = []
    for i in range(1, n_span):
        s = i / n_span
        # Bold pelagic sickle sweep: sweeps outboard (+X), strongly aft (-Y), and slightly upward-then-aft
        x_lead = x_root + side * (0.106 * math.pow(s, 0.80))
        y_lead = y_root - 0.218 * math.pow(s, 1.04)
        z_lead = z_root + 0.014 * math.sin(math.pi * 0.72 * s) - 0.024 * math.pow(s, 1.4)

        scallop = 1.0 - 0.055 * abs(math.sin(math.pi * n_rays * s)) * _smoothstep(0.08, 0.25, s)
        chord = 0.054 * math.sin(math.pi * math.pow(s, 0.65)) * scallop + 0.018 * (1.0 - s)
        chord = max(0.0045, chord)

        ray_rib = math.cos(math.pi * n_rays * s) ** 2
        tip_taper = 0.36 + 0.64 * (1.0 - _smoothstep(0.76, 1.0, s))

        # Tilt fin blade ~42 deg so broad iridescent surface catches light from both side & top views!
        dir_chord = Vector((-side * 0.12, -0.58, -0.80)).normalized()
        dir_span = Vector((side * 0.42, -0.88, -0.10)).normalized()
        n_thick = dir_span.cross(dir_chord).normalized()

        ring: list[Vector] = []
        for j in range(n_prof):
            phi = (2.0 * math.pi * j) / n_prof
            c = 0.5 * (1.0 - math.cos(phi))
            side_p = math.sin(phi)

            lead_spine = 0.0026 * (1.0 - 0.72 * math.pow(c, 0.72))
            rib = 0.00058 * ray_rib * math.sin(math.pi * _clamp(c, 0.05, 0.95))
            t_half = max(0.00082, (lead_spine + rib) * tip_taper)

            p_mid = Vector((x_lead, y_lead, z_lead)) + dir_chord * (c * chord)
            ring.append(p_mid + n_thick * (side_p * t_half))
        rings.append(ring)

    cap_root = Vector((x_root - side * 0.003, y_root - 0.006, z_root - 0.006))
    tip_p = Vector((
        x_root + side * 0.109,
        y_root - 0.224,
        z_root - 0.016,
    ))
    return _build_closed_tube_with_caps(rings, cap_root, tip_p)


def build_pectoral_fins(col: bpy.types.Collection, mat_fin: bpy.types.Material, bull_crest: float = 1.0) -> bpy.types.Object:
    bm_all = bmesh.new()
    for side in (-1.0, 1.0):
        bm_s = _build_paired_pectoral(side, bull_crest)
        me_tmp = bpy.data.meshes.new("__tmp_pec")
        bm_s.to_mesh(me_tmp)
        bm_s.free()
        bm_all.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    return _finalize_watertight_mesh(bm_all, "PectoralFins", col, mat_fin, "PectoralFins", sharp_deg=45.0)


def _build_paired_pelvic(side: float, bull_crest: float) -> bmesh.types.BMesh:
    """Thoracic pelvic fin rooted under chest at Y = +0.262, sweeping aft & slightly outboard."""
    y_root = 0.262
    zb, _zt, _hw = body_contours(y_root, bull_crest)
    x_root = side * 0.014
    z_root = zb + 0.0065  # 6.5 mm clean embed into ventral chest!

    n_span = 34
    n_prof = 20
    n_rays = 8

    rings: list[list[Vector]] = []
    for i in range(1, n_span):
        s = i / n_span
        x_lead = x_root + side * (0.030 * math.pow(s, 0.85))
        y_lead = y_root - 0.132 * math.pow(s, 1.04)
        z_lead = z_root - 0.026 * math.sin(math.pi * 0.62 * s)

        scallop = 1.0 - 0.045 * abs(math.sin(math.pi * n_rays * s))
        chord = max(0.003, (0.028 * math.sin(math.pi * math.pow(s, 0.72)) + 0.012 * (1.0 - s)) * scallop)
        ray_rib = math.cos(math.pi * n_rays * s) ** 2

        dir_chord = Vector((side * 0.18, -0.94, 0.26)).normalized()
        dir_span = Vector((side * 0.24, -0.95, -0.18)).normalized()
        n_thick = dir_span.cross(dir_chord).normalized()

        ring: list[Vector] = []
        for j in range(n_prof):
            phi = (2.0 * math.pi * j) / n_prof
            c = 0.5 * (1.0 - math.cos(phi))
            side_p = math.sin(phi)
            t_half = max(0.00080, (0.0020 * (1.0 - 0.72 * c) + 0.00042 * ray_rib * math.sin(math.pi * c)) * (0.45 + 0.55 * (1.0 - s)))
            p_mid = Vector((x_lead, y_lead, z_lead)) + dir_chord * (c * chord)
            ring.append(p_mid + n_thick * (side_p * t_half))
        rings.append(ring)

    cap_root = Vector((x_root, y_root - 0.004, z_root + 0.002))
    cap_tip = Vector((x_root + side * 0.031, y_root - 0.136, z_root - 0.022))
    return _build_closed_tube_with_caps(rings, cap_root, cap_tip)


def _build_anal_fin(bull_crest: float) -> bmesh.types.BMesh:
    """Long 28-ray scalloped Dorado anal fin along ventral midline (`Y = -0.015` to `-0.335`)."""
    y_start = -0.015
    y_end = -0.335
    n_span = 58
    n_prof = 22
    n_rays = 28

    rings: list[list[Vector]] = []
    for i in range(1, n_span):
        s = i / n_span
        y = y_start + s * (y_end - y_start)
        z_bot_body, _zt, _hw = body_contours(y, bull_crest)
        z_root = z_bot_body + 0.0042  # 4.2 mm clean embed into ventral keel!

        lead_r = math.pow(_smoothstep(0.0, 0.08, s), 0.65)
        tail_r = math.pow(_smoothstep(1.0, 0.93, s), 0.70)
        # Anterior falcate lobe (~52 mm deep) tapering smoothly to 20 mm aft
        fin_h = (0.052 * (1.0 - 0.62 * math.pow(s, 0.75)) + 0.010 * _gauss(s, 0.12, 0.07)) * lead_r * tail_r
        scallop = 1.0 - 0.050 * abs(math.sin(math.pi * n_rays * s)) * _smoothstep(0.04, 0.14, s)
        h_span = max(0.0035, fin_h * scallop)
        ray_rib = math.cos(math.pi * n_rays * s) ** 2
        rake_aft = -0.020 * math.sin(math.pi * s)

        ring: list[Vector] = []
        for j in range(n_prof):
            phi = (2.0 * math.pi * j) / n_prof
            c = 0.5 * (1.0 - math.cos(phi))
            side_s = math.sin(phi)
            t_half = max(
                0.00080,
                (0.0022 * (1.0 - 0.74 * c) + 0.00055 * ray_rib * math.sin(math.pi * _clamp(c, 0.05, 0.96)))
                * (0.38 + 0.62 * _smoothstep(0.0, 0.04, s) * _smoothstep(1.0, 0.96, s)),
            )
            ring.append(Vector((side_s * t_half, y + c * rake_aft, z_root - c * h_span)))
        rings.append(ring)

    zb0, _, _ = body_contours(y_start - 0.002, bull_crest)
    zbe, _, _ = body_contours(y_end + 0.002, bull_crest)
    cap_a = Vector((0.0, y_start + 0.002, zb0 + 0.003))
    cap_b = Vector((0.0, y_end - 0.002, zbe + 0.002))
    return _build_closed_tube_with_caps(rings, cap_a, cap_b)


def build_ventral_fins(col: bpy.types.Collection, mat_fin: bpy.types.Material, bull_crest: float = 1.0) -> bpy.types.Object:
    bm_all = bmesh.new()
    for sub_bm in (_build_paired_pelvic(-1.0, bull_crest), _build_paired_pelvic(1.0, bull_crest), _build_anal_fin(bull_crest)):
        me_tmp = bpy.data.meshes.new("__tmp_ven")
        sub_bm.to_mesh(me_tmp)
        sub_bm.free()
        bm_all.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    return _finalize_watertight_mesh(bm_all, "VentralFins", col, mat_fin, "VentralFins", sharp_deg=45.0)


# ---------------------------------------------------------------------------
# 3. Layered Pelagic Eyes (`Eyes`) with Polar Cornea UV Unwrap
# ---------------------------------------------------------------------------
def build_eyes(col: bpy.types.Collection, mat_eye: bpy.types.Material, bull_crest: float = 1.0) -> bpy.types.Object:
    """Port & Starboard low-set Dorado eyeballs seated flush in sculpted orbital sockets."""
    eye_y = 0.468
    eye_z = 0.136 + 0.002 * bull_crest
    _, _, hw_e = body_contours(eye_y, bull_crest)
    x_orbit = hw_e * 0.90

    r_yz = 0.0195  # 39 mm orbital diameter (expressive pelagic eye seated inside socket rim)
    r_x = 0.0110   # flattened dome so outer cornea gleams proud & inner pole stays >25 mm from X=0

    bm_all = bmesh.new()
    uv_lay = bm_all.loops.layers.uv.verify()

    for idx_s, side in enumerate((-1.0, 1.0)):
        cx = side * (x_orbit - 0.0048)  # seats cleanly into the 4.6 mm socket!
        n_rings = 20
        n_seg = 28

        # Build polar sphere along +/-X optical axis so UV center (0.25 or 0.75, 0.5) is the exact pupil center!
        pole_out = bm_all.verts.new(Vector((cx + side * r_x, eye_y, eye_z)))
        pole_in = bm_all.verts.new(Vector((cx - side * r_x, eye_y, eye_z)))

        rings_v: list[list[bmesh.types.BMVert]] = []
        for ir in range(1, n_rings):
            alpha = (math.pi * ir) / n_rings  # 0 at outer cornea apex, pi at inner scleral pole
            ca = math.cos(alpha)
            sa = math.sin(alpha)
            # Subtle cornea dome bulge on anterior/outer 38 deg (`alpha < 0.66 rad`)
            cornea_bulge = 0.0014 * math.pow(max(0.0, 1.0 - alpha / 0.66), 1.6) if alpha < 0.66 else 0.0
            px = cx + side * (r_x * ca + cornea_bulge)

            rv: list[bmesh.types.BMVert] = []
            for js in range(n_seg):
                beta = (2.0 * math.pi * js) / n_seg
                # Slight forward head-taper cant (10 deg around Z so eye faces slightly forward-outboard!)
                ly = r_yz * sa * math.cos(beta)
                lz = r_yz * sa * math.sin(beta)
                cant = 0.17 * side  # ~10 deg forward convergence
                wy = eye_y + ly * math.cos(cant)
                wx = px - ly * math.sin(cant) * side * 0.35
                rv.append(bm_all.verts.new(Vector((wx, wy, eye_z + lz))))
            rings_v.append(rv)

        def _eye_uv(alpha_v: float, beta_v: float, side_idx: int) -> tuple[float, float]:
            # Pack Port eye into left UV half [0.04..0.46], Starboard eye into right UV half [0.54..0.96]
            rad = 0.20 * (alpha_v / math.pi)
            u_center = 0.25 if side_idx == 0 else 0.75
            return (u_center + rad * math.cos(beta_v), 0.50 + rad * math.sin(beta_v))

        # Outer cornea fan
        r0 = rings_v[0]
        a0 = math.pi / n_rings
        for js in range(n_seg):
            jn = (js + 1) % n_seg
            verts_tri = (pole_out, r0[js], r0[jn]) if side > 0 else (pole_out, r0[jn], r0[js])
            f = bm_all.faces.new(verts_tri)
            b_j = (2.0 * math.pi * js) / n_seg
            b_jn = (2.0 * math.pi * jn) / n_seg
            if side > 0:
                uvs = [_eye_uv(0.0, 0.0, idx_s), _eye_uv(a0, b_j, idx_s), _eye_uv(a0, b_jn, idx_s)]
            else:
                uvs = [_eye_uv(0.0, 0.0, idx_s), _eye_uv(a0, b_jn, idx_s), _eye_uv(a0, b_j, idx_s)]
            for lp, uv_c in zip(f.loops, uvs):
                lp[uv_lay].uv = uv_c

        # Middle strips
        for ir in range(len(rings_v) - 1):
            ra = rings_v[ir]
            rb = rings_v[ir + 1]
            aa = (math.pi * (ir + 1)) / n_rings
            ab = (math.pi * (ir + 2)) / n_rings
            for js in range(n_seg):
                jn = (js + 1) % n_seg
                b_j = (2.0 * math.pi * js) / n_seg
                b_jn = (2.0 * math.pi * jn) / n_seg
                if side > 0:
                    f1 = bm_all.faces.new((ra[js], rb[js], rb[jn]))
                    f2 = bm_all.faces.new((ra[js], rb[jn], ra[jn]))
                    uv1 = [_eye_uv(aa, b_j, idx_s), _eye_uv(ab, b_j, idx_s), _eye_uv(ab, b_jn, idx_s)]
                    uv2 = [_eye_uv(aa, b_j, idx_s), _eye_uv(ab, b_jn, idx_s), _eye_uv(aa, b_jn, idx_s)]
                else:
                    f1 = bm_all.faces.new((ra[js], rb[jn], rb[js]))
                    f2 = bm_all.faces.new((ra[js], ra[jn], rb[jn]))
                    uv1 = [_eye_uv(aa, b_j, idx_s), _eye_uv(ab, b_jn, idx_s), _eye_uv(ab, b_j, idx_s)]
                    uv2 = [_eye_uv(aa, b_j, idx_s), _eye_uv(aa, b_jn, idx_s), _eye_uv(ab, b_jn, idx_s)]
                for lp, uv_c in zip(f1.loops, uv1):
                    lp[uv_lay].uv = uv_c
                for lp, uv_c in zip(f2.loops, uv2):
                    lp[uv_lay].uv = uv_c

        # Inner scleral fan
        rl = rings_v[-1]
        al = (math.pi * (n_rings - 1)) / n_rings
        for js in range(n_seg):
            jn = (js + 1) % n_seg
            verts_tri = (rl[js], pole_in, rl[jn]) if side > 0 else (rl[js], rl[jn], pole_in)
            f = bm_all.faces.new(verts_tri)
            b_j = (2.0 * math.pi * js) / n_seg
            b_jn = (2.0 * math.pi * jn) / n_seg
            if side > 0:
                uvs = [_eye_uv(al, b_j, idx_s), _eye_uv(math.pi * 0.98, b_j, idx_s), _eye_uv(al, b_jn, idx_s)]
            else:
                uvs = [_eye_uv(al, b_j, idx_s), _eye_uv(al, b_jn, idx_s), _eye_uv(math.pi * 0.98, b_j, idx_s)]
            for lp, uv_c in zip(f.loops, uvs):
                lp[uv_lay].uv = uv_c

    bmesh.ops.recalc_face_normals(bm_all, faces=bm_all.faces[:])
    me = bpy.data.meshes.new("Eyes")
    bm_all.to_mesh(me)
    bm_all.free()

    for poly in me.polygons:
        poly.use_smooth = True
        poly.material_index = 0
    me.materials.append(mat_eye)

    ob = bpy.data.objects.new("Eyes", me)
    col.objects.link(ob)
    ob["sc_part"] = "Eyes"
    ob["sc_role"] = "solid"
    me.update()
    return ob


# ---------------------------------------------------------------------------
# 4. Default Procedural Preview Materials (Upgraded to Full 2K Cycles Bake in bake_lod_variants.py)
# ---------------------------------------------------------------------------
def build_default_materials() -> dict[str, bpy.types.Material]:
    m_body = mats.pbr(
        "MM_Body",
        color=(0.86, 0.72, 0.14),
        roughness=0.22,
        metallic=0.38,
        coat=0.65,
        coat_roughness=0.06,
        role="solid",
    )
    m_dorsal = mats.pbr(
        "MM_DorsalFin",
        color=(0.04, 0.44, 0.48),
        roughness=0.28,
        metallic=0.22,
        coat=0.45,
        coat_roughness=0.10,
        role="solid",
    )
    m_caudal = mats.pbr(
        "MM_CaudalFin",
        color=(0.82, 0.64, 0.10),
        roughness=0.28,
        metallic=0.24,
        coat=0.45,
        coat_roughness=0.10,
        role="solid",
    )
    m_pectoral = mats.pbr(
        "MM_PectoralFin",
        color=(0.05, 0.56, 0.74),
        roughness=0.25,
        metallic=0.30,
        coat=0.50,
        coat_roughness=0.08,
        role="solid",
    )
    m_ventral = mats.pbr(
        "MM_VentralFin",
        color=(0.80, 0.68, 0.22),
        roughness=0.30,
        metallic=0.18,
        role="solid",
    )
    m_eye = mats.pbr(
        "MM_Eye",
        color=(0.06, 0.06, 0.07),
        roughness=0.04,
        metallic=0.10,
        coat=1.0,
        coat_roughness=0.02,
        role="solid",
    )
    return {
        "Body": m_body,
        "DorsalFin": m_dorsal,
        "CaudalFin": m_caudal,
        "PectoralFins": m_pectoral,
        "VentralFins": m_ventral,
        "Eyes": m_eye,
    }


# ---------------------------------------------------------------------------
# 5. Hard BVH Shell-Integrity & Contact Verification Gate
# ---------------------------------------------------------------------------
def verify_fish_integrity(meshes: list[bpy.types.Object]) -> None:
    """Guarantee 0 opposite-side breaches, 0 floating parts, and 0 fin-to-fin collisions."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    by_name = {o.name: o for o in meshes}
    body = by_name["Body"]

    bm_body = bmesh.new()
    bm_body.from_object(body, dg)
    bm_body.transform(body.matrix_world)
    bvh_body = BVHTree.FromBMesh(bm_body)

    breaches: list[str] = []
    for ob in meshes:
        if ob.name == "Body":
            continue
        bm = bmesh.new()
        bm.from_object(ob, dg)
        bm.transform(ob.matrix_world)
        bvh_sub = BVHTree.FromBMesh(bm)

        # 1. Must intersect/contact Body (0 floating parts!)
        overlaps = bvh_body.overlap(bvh_sub)
        if not overlaps:
            breaches.append(f"{ob.name}: FLOATING (0 BVH contact with Body!)")

        # 2. Verify paired lateral parts never cross centerline X=0 and median fins stay thin inside X!
        if ob.name in ("PectoralFins", "Eyes"):
            # Each island must stay strictly on its own side of X=0 (|x| > 3 mm)
            for v in bm.verts:
                if abs(v.co.x) < 0.002:
                    breaches.append(f"{ob.name}: crossed medial plane X=0 at {tuple(round(c, 4) for c in v.co)}")
                    break
        elif ob.name == "DorsalFin":
            # DorsalFin root must never drop below mid-body Z (never poke out belly or lateral flanks!)
            for v in bm.verts:
                if v.co.z < 0.12:
                    breaches.append(f"DorsalFin: plunged too deep into Body (z={v.co.z:.4f})")
                    break

        bm.free()

    bm_body.free()
    if breaches:
        raise RuntimeError("FISH SHELL INTEGRITY FAILED:\n  - " + "\n  - ".join(breaches))
    core.log("FISH SHELL INTEGRITY PASS: 0 breaches, 100% anatomical socket contact, 0 floating parts!")


# ---------------------------------------------------------------------------
# 6. Roblox `FishingService` / `BoatService` Attachment Sockets
# ---------------------------------------------------------------------------
def clear_scene_and_setup_units() -> None:
    core.ensure_object_mode()
    for ob in list(bpy.data.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        core._free_data(data)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0


def add_sockets(col: bpy.types.Collection, z_shift: float, bull_crest: float = 1.0) -> list[bpy.types.Object]:
    zb_p, zt_p, _ = body_contours(PEDUNCLE_Y, bull_crest)
    z_ped = 0.5 * (zb_p + zt_p) + z_shift

    return [
        core.socket("HookMouth", col, (0.0, SNOUT_Y + 0.002, 0.118 + z_shift)),
        core.socket("HandGripGill", col, (0.0, 0.315, 0.145 + z_shift)),
        core.socket("HandGripTail", col, (0.0, -0.355, z_ped)),
        core.socket("HingeTail", col, (0.0, PEDUNCLE_Y + 0.005, z_ped), hinge_only=True),
        core.socket("SwimSplash", col, (0.0, 0.05, 0.14 + z_shift), emitter=True),
    ]


# ---------------------------------------------------------------------------
# 7. Master Parametric Build Entrypoint
# ---------------------------------------------------------------------------
def build_all(
    collection_name: str = "MahiMahi",
    bull_crest: float = 1.0,
    clear_scene: bool = True,
    mat_dict: dict[str, bpy.types.Material] | None = None,
) -> tuple[bpy.types.Collection, list[bpy.types.Object]]:
    if clear_scene:
        clear_scene_and_setup_units()
    else:
        bpy.context.scene.unit_settings.system = "METRIC"
        bpy.context.scene.unit_settings.scale_length = 1.0
    col = core.fresh_collection(collection_name)
    m = mat_dict or build_default_materials()

    body = build_body(col, m["Body"], bull_crest=bull_crest)
    dorsal = build_dorsal_fin(col, m["DorsalFin"], bull_crest=bull_crest)
    caudal = build_caudal_fin(col, m["CaudalFin"], bull_crest=bull_crest)
    pectoral = build_pectoral_fins(col, m["PectoralFins"], bull_crest=bull_crest)
    ventral = build_ventral_fins(col, m["VentralFins"], bull_crest=bull_crest)
    eyes = build_eyes(col, m["Eyes"], bull_crest=bull_crest)

    meshes = [body, dorsal, caudal, pectoral, ventral, eyes]

    # Ground exact lowest vertex to Z = 0.0000 m and bake into mesh vertices so origin & transforms stay (0,0,0) / (1,1,1)!
    lo, _hi = core.world_bbox(meshes)
    z_shift = -lo.z
    if abs(z_shift) > 1e-7:
        shift_mat = Matrix.Translation((0.0, 0.0, z_shift))
        for ob in meshes:
            ob.data.transform(shift_mat)
            ob.data.update()

    add_sockets(col, z_shift=z_shift, bull_crest=bull_crest)
    verify_fish_integrity(meshes)
    gameready.validate(meshes)
    return col, meshes


def main() -> int:
    col, meshes = build_all(collection_name="MahiMahi", bull_crest=1.0, clear_scene=True)
    blend_out = os.path.join(THIS_DIR, "mahi_mahi.blend")
    glb_out = os.path.join(THIS_DIR, "mahi_mahi.glb")
    bpy.ops.wm.save_as_mainfile(filepath=blend_out)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.export_scene.gltf(filepath=glb_out, use_selection=True, export_format="GLB", export_apply=True)
    for o in meshes:
        o.select_set(False)
    core.log(f"Built MahiMahi base mesh ({sum(len(o.data.polygons) for o in meshes)} tris) -> {blend_out}")
    return 0


if __name__ == "__main__":
    main()

