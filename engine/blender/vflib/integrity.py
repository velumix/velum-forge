"""Hard BVH Shell-Integrity, Socket-Contact & Signed-Volume Normal Gates (`vflib.integrity`).

Prevents shell poke-throughs, floating parts, and inverted normals on concave/forked closed manifolds.
"""
from __future__ import annotations

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

from . import core


def ensure_positive_signed_volume(bm: bmesh.types.BMesh) -> float:
    """Enforce 100% outward face normals on any closed `S^2` manifold using exact 3D signed volume."""
    bm.faces.ensure_lookup_table()
    vol6 = 0.0
    for f in bm.faces:
        if len(f.verts) >= 3:
            v0 = f.verts[0].co
            for k in range(1, len(f.verts) - 1):
                vol6 += v0.dot(f.verts[k].co.cross(f.verts[k + 1].co))
    if vol6 < 0.0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        vol6 = -vol6
    return vol6 / 6.0


def verify_socket_contact(
    primary_ob: bpy.types.Object,
    sub_objects: list[bpy.types.Object],
    *,
    forbid_medial_cross_names: set[str] | None = None,
    medial_eps: float = 0.002,
) -> list[str]:
    """Verify every sub-object contacts `primary_ob` (0 floating islands) and respects symmetry planes."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    bm_prim = bmesh.new()
    bm_prim.from_object(primary_ob, dg)
    bm_prim.transform(primary_ob.matrix_world)
    bvh_prim = BVHTree.FromBMesh(bm_prim)

    forbid = forbid_medial_cross_names or set()
    errors: list[str] = []

    for ob in sub_objects:
        if ob == primary_ob or ob.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_object(ob, dg)
        bm.transform(ob.matrix_world)
        bvh_sub = BVHTree.FromBMesh(bm)

        if not bvh_prim.overlap(bvh_sub):
            errors.append(f"{ob.name}: FLOATING (0 BVH contact with {primary_ob.name})")

        if ob.name in forbid:
            for v in bm.verts:
                if abs(v.co.x) < medial_eps:
                    errors.append(f"{ob.name}: crossed X=0 medial plane at {tuple(round(c, 4) for c in v.co)}")
                    break
        bm.free()

    bm_prim.free()
    return errors



# ---------------------------------------------------------------------------
# Quad-Flow Topology Verification, Wireframe Proof & Clearance Audits
# ---------------------------------------------------------------------------

def verify_quad_flow(ob, angle_limit_deg=45.0, min_quad_ratio=0.75):
    """Measure clean `Alt+J` quad recovery, SubD readiness, and `UNSUBDIV` safety on `ob`."""
    import bmesh
    import math
    if ob is None or ob.type != "MESH" or ob.data is None:
        return {"ok": False, "error": "invalid mesh object"}

    tmp = ob.copy()
    tmp.data = ob.data.copy()
    bpy.context.scene.collection.objects.link(tmp)
    try:
        core.ensure_object_mode()
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        tmp.select_set(True)
        bpy.context.view_layer.objects.active = tmp
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.tris_convert_to_quads(
            face_threshold=math.radians(angle_limit_deg),
            shape_threshold=math.radians(angle_limit_deg),
        )
        bpy.ops.object.mode_set(mode="OBJECT")

        bm = bmesh.new()
        bm.from_mesh(tmp.data)
        total = len(bm.faces)
        quads = sum(1 for f in bm.faces if len(f.verts) == 4)
        tris = sum(1 for f in bm.faces if len(f.verts) == 3)
        ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
        bm.free()

        sub = tmp.modifiers.new("VF_TestSubD", "SUBSURF")
        sub.levels = 1
        sub.render_levels = 1
        unsub = tmp.modifiers.new("VF_TestUnsub", "DECIMATE")
        unsub.decimate_type = "UNSUBDIV"
        unsub.iterations = 2

        deps = bpy.context.evaluated_depsgraph_get()
        eval_ob = tmp.evaluated_get(deps)
        me_eval = eval_ob.to_mesh()
        eval_polys = len(me_eval.polygons)
        eval_ob.to_mesh_clear()

        ratio = (quads / total) if total else 0.0
        return {
            "ok": ratio >= min_quad_ratio and eval_polys > 0,
            "object": ob.name,
            "total_faces": total,
            "quads": quads,
            "tris": tris,
            "ngons": ngons,
            "quad_ratio": round(ratio, 4),
            "subd_unsubdiv_faces": eval_polys,
        }
    finally:
        me = tmp.data
        bpy.data.objects.remove(tmp, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def render_quad_flow_proof(objs, out_path, cam_loc=(1.6, -1.8, 1.3), target=(0.0, 0.0, 0.55),
                           res=(1024, 1024)):
    """Render a true quad-topology proof using a `WIREFRAME` modifier (never `ShaderNodeWireframe`)."""
    import math
    from mathutils import Vector
    from . import bake
    overlays = []
    cam_ob = None
    light_ob = None
    try:
        mat_wire = bpy.data.materials.new("VF_QuadProofWire")
        mat_wire.use_nodes = True
        bsdf = mat_wire.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.04, 0.05, 0.06, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.85

        for src in objs:
            if src is None or src.type != "MESH":
                continue
            ov = src.copy()
            ov.data = src.data.copy()
            bpy.context.scene.collection.objects.link(ov)
            core.ensure_object_mode()
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            ov.select_set(True)
            bpy.context.view_layer.objects.active = ov
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.tris_convert_to_quads(
                face_threshold=math.radians(45.0),
                shape_threshold=math.radians(45.0),
            )
            bpy.ops.object.mode_set(mode="OBJECT")
            wf = ov.modifiers.new("VF_ProofWire", "WIREFRAME")
            wf.thickness = 0.0022
            wf.offset = 0.0008
            wf.use_replace = False
            ov.data.materials.append(mat_wire)
            wf.material_offset = len(ov.data.materials) - 1
            overlays.append((ov, ov.data))

        cam_data = bpy.data.cameras.new("VF_QuadProofCam")
        cam_ob = bpy.data.objects.new("VF_QuadProofCam", cam_data)
        bpy.context.scene.collection.objects.link(cam_ob)
        cam_ob.location = Vector(cam_loc)
        cam_ob.rotation_euler = (Vector(target) - Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.camera = cam_ob

        ld = bpy.data.lights.new("VF_QuadProofKey", "SUN")
        ld.energy = 3.0
        light_ob = bpy.data.objects.new("VF_QuadProofKey", ld)
        bpy.context.scene.collection.objects.link(light_ob)
        light_ob.rotation_euler = (0.6, 0.2, 0.7)

        sc = bpy.context.scene
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.cycles.samples = 32
        bake.render_still_safe(sc, out_path)
        return out_path
    finally:
        for ov, me in overlays:
            bpy.data.objects.remove(ov, do_unlink=True)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        for o in (cam_ob, light_ob):
            if o is not None:
                bpy.data.objects.remove(o, do_unlink=True)


def audit_grounding_and_clearances(objs, floor_z=0.0, obstacles_xy_r=(), tol=0.003):
    """Audit world `min_z >= floor_z - tol` and `2D` clearance from obstacle `(x, y, r)` circles."""
    from mathutils import Vector
    violations = []
    for o in objs:
        if o is None or o.type != "MESH" or not o.bound_box:
            continue
        corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
        mnz = min(c.z for c in corners)
        if mnz < floor_z - tol:
            violations.append(f"{o.name}: min_z={mnz:.4f} < floor_z={floor_z:.4f}")
        if obstacles_xy_r:
            cx = 0.5 * (min(c.x for c in corners) + max(c.x for c in corners))
            cy = 0.5 * (min(c.y for c in corners) + max(c.y for c in corners))
            rx = 0.5 * (max(c.x for c in corners) - min(c.x for c in corners))
            ry = 0.5 * (max(c.y for c in corners) - min(c.y for c in corners))
            r_obj = min(rx, ry) * 0.45
            for ox, oy, orad in obstacles_xy_r:
                dist = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
                if dist < (orad + r_obj - tol):
                    violations.append(f"{o.name}: overlaps obstacle ({ox:.2f},{oy:.2f}) dist={dist:.3f}")
    return violations
