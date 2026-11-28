"""Game-ready pipeline: bake modifiers, join, triangle budgets, validation, collision proxies."""

import bmesh
import bpy
from mathutils import Matrix

from . import core

ROBLOX_MAX_TRIS_PER_MESH = 20000
ROBLOX_MAX_SIZE_STUDS = 2048.0


def triangle_count(ob, evaluated=True):
    if ob.type != "MESH":
        return 0
    if evaluated:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        n = sum(len(p.vertices) - 2 for p in me.polygons)
        ev.to_mesh_clear()
        return n
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def budget(objs, evaluated=True):
    """Triangle counts grouped by `sc_part` -> {part: tris}."""
    out = {}
    for ob in objs:
        if ob.type != "MESH":
            continue
        part = ob.get("sc_part", ob.name)
        out[part] = out.get(part, 0) + triangle_count(ob, evaluated)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def bake_object(ob, name=None, col=None):
    """Return a new object with modifiers and transforms applied (custom normals preserved)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    me.name = name or (ob.name + "_baked")
    mw = ob.matrix_world.copy()
    me.transform(mw)
    if mw.determinant() < 0:
        me.flip_normals()
    new = bpy.data.objects.new(me.name, me)
    (col or bpy.context.scene.collection).objects.link(new)
    for k in ob.keys():
        if k.startswith("sc_"):
            new[k] = ob[k]
    return new


def join(objs, name):
    """Join mesh objects into objs[0] (renamed `name`). Keeps custom normals and materials."""
    objs = [o for o in objs if o and o.type == "MESH"]
    if not objs:
        return None
    target = objs[0]
    if len(objs) > 1:
        core.ensure_object_mode()
        with bpy.context.temp_override(active_object=target, object=target, selected_objects=objs,
                                       selected_editable_objects=objs):
            bpy.ops.object.join()
    target.name = name
    target.data.name = name
    return target


def scale_mesh(ob, factor):
    ob.data.transform(Matrix.Scale(factor, 4))
    ob.data.update()


def collapse_materials(ob):
    """Merge duplicate material slots referencing the same material."""
    me = ob.data
    uniq, remap = [], {}
    for i, m in enumerate(me.materials):
        if m not in uniq:
            uniq.append(m)
        remap[i] = uniq.index(m)
    if len(uniq) == len(me.materials):
        return
    idx = [0] * len(me.polygons)
    me.polygons.foreach_get("material_index", idx)
    me.materials.clear()
    for m in uniq:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", [remap.get(i, 0) for i in idx])


def validate(objs, max_tris=ROBLOX_MAX_TRIS_PER_MESH, units_to_studs=1.0, verbose=True, deduplicate_meshes=False):
    """Check meshes for common game-engine problems. Returns a list of per-object reports."""
    reports = []
    seen_meshes = set()
    for ob in objs:
        if ob.type != "MESH" or ob.data is None:
            continue
        me = ob.data
        ptr = me.as_pointer()
        if deduplicate_meshes and ptr in seen_meshes:
            continue
        seen_meshes.add(ptr)
        bm = bmesh.new()
        bm.from_mesh(me)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        boundary = sum(1 for e in bm.edges if e.is_boundary)
        loose = sum(1 for v in bm.verts if not v.link_faces)
        degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
        bm.free()
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
        dims = [d * units_to_studs for d in ob.dimensions]
        issues = []
        if tris > max_tris:
            issues.append(f"{tris} tris > {max_tris} limit")
        if loose:
            issues.append(f"{loose} loose verts")
        if degenerate:
            issues.append(f"{degenerate} degenerate faces")
        if non_manifold:
            issues.append(f"{non_manifold} non-manifold edges")
        if not me.uv_layers:
            issues.append("no UV map")
        if any(abs(s - 1.0) > 1e-4 for s in ob.scale):
            issues.append("unapplied scale")
        if any(abs(r) > 1e-5 for r in ob.rotation_euler) and not (ob.get("vf_instanced") or ob.get("vf_asset_set")):
            issues.append("unapplied transform")
        if max(dims) > ROBLOX_MAX_SIZE_STUDS:
            issues.append("larger than Roblox max part size")
        rep = dict(name=ob.name, tris=tris, verts=len(me.vertices), ngons=ngons, boundary_edges=boundary,
                   materials=len(me.materials), dims_studs=[round(d, 3) for d in dims], issues=issues)
        reports.append(rep)
    if verbose:
        core.log(f"{'object':28s} {'tris':>7s} {'verts':>7s} {'mats':>4s}  issues")
        for r in reports:
            core.log(f"{r['name'][:28]:28s} {r['tris']:7d} {r['verts']:7d} {r['materials']:4d}  "
                     + ("; ".join(r["issues"]) or "ok"))
        core.log(f"TOTAL tris: {sum(r['tris'] for r in reports)}")
    return reports


def convex_hull(objs, name, col, max_faces=None):
    """Single convex hull around several objects (useful as a simple collision proxy)."""
    bm = bmesh.new()
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in objs:
        if ob.type != "MESH":
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        for v in me.vertices:
            bm.verts.new(ob.matrix_world @ v.co)
        ev.to_mesh_clear()
    bmesh.ops.convex_hull(bm, input=bm.verts)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    if max_faces and len(me.polygons) > max_faces:
        m = ob.modifiers.new("Decimate", "DECIMATE")
        m.ratio = max_faces / len(me.polygons)
    return ob


def make_lod(ob, ratio, name=None, col=None):
    """Decimated copy for manual LODs (Roblox auto-LODs MeshParts, other engines may not)."""
    new = bake_object(ob, name or f"{ob.name}_LOD", col)
    m = new.modifiers.new("Decimate", "DECIMATE")
    m.ratio = ratio
    m.use_collapse_triangulate = True
    baked = bake_object(new, new.name, col)
    me = new.data
    bpy.data.objects.remove(new, do_unlink=True)
    bpy.data.meshes.remove(me)
    return baked

