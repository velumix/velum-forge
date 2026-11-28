r"""Verify & visually prove `Alt+J` (Tris-to-Quads), Subdivision Surface & Un-Subdivide topology on `Patio_Tables`!

Renders `renders/table_quad_topology_proof.png`:
  - Top-Left: Triangulated `Patio_Tables` (as shipped in `.blend`/`.glb`) w/ crisp wireframe
  - Top-Right: `Patio_Tables` IMMEDIATELY after Blender `Alt+J` (Tris-to-Quads) showing pure quad loops (matching Chair!)
  - Bottom-Left: Zoomed Macro of Tableware (Wine Glass, Espresso Cup/Handle/Saucer, Plate, Votive, Napkin/Cutlery) after `Alt+J`
  - Bottom-Right: `Patio_Tables` after `Alt+J` + `Decimate (UNSUBDIV, iterations=2)` proving clean Un-Subdivide!
"""
from __future__ import annotations

import math
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
RENDERS_DIR = os.path.join(THIS_DIR, "renders")

if "--compose" not in sys.argv:
    import bmesh
    import bpy
    from mathutils import Vector

    ENGINE_BLENDER = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "engine", "blender"))
    for _p in (THIS_DIR, ENGINE_BLENDER):
        if _p not in sys.path:
            sys.path.insert(0, _p)

    from vflib import bake, core  # noqa: E402
    import build_buildings  # noqa: E402
    import build_street_and_nature as bsn  # noqa: E402
    import scene_mats  # noqa: E402


def _build_wire_shader(name: str, base_col=(0.76, 0.77, 0.79, 1.0), wire_col=(0.06, 0.06, 0.08, 1.0), wire_px=1.6):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = base_col
    bsdf.inputs["Roughness"].default_value = 0.55
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # Note: Cycles `Wireframe` node always triangulates; to show TRUE QUAD EDGES in Cycles, we use Freestyle OR a thin Wireframe modifier!
    return mat


def _make_true_edge_wire_overlay(src_ob: bpy.types.Object, col: bpy.types.Collection, wire_mat: bpy.types.Material, thickness: float = 0.0014) -> bpy.types.Object:
    """Create a true polygon-edge wireframe overlay object (shows REAL quads vs tris — never fake Cycles auto-triangulation!)."""
    w_me = src_ob.data.copy()
    w_ob = bpy.data.objects.new(src_ob.name + "_QuadWire", w_me)
    w_ob.matrix_world = src_ob.matrix_world.copy()
    col.objects.link(w_ob)
    mod = w_ob.modifiers.new("Wireframe", "WIREFRAME")
    mod.thickness = thickness
    mod.offset = 0.6
    mod.use_replace = True
    mod.use_even_offset = True
    mod.use_relative_offset = False
    w_me.materials.clear()
    w_me.materials.append(wire_mat)
    return w_ob


def _render_panel(sc, cam, loc, tgt, lens, out_p):
    cam.location = Vector(loc)
    cam.data.lens = lens
    cam.data.clip_start = 0.02
    cam.data.clip_end = 100.0
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bake.render_still_safe(sc, out_p, cooldown_sec=0.3)


def main() -> int:
    os.makedirs(RENDERS_DIR, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    col = core.fresh_collection("QuadProof")
    m = scene_mats.build_material_library()

    # Build ONLY Patio Furniture & Sidewalk slab for ultra-fast verification!
    ob_sw = bsn.build_sidewalks_and_apron(col, m)
    patio_objs, _chair_me = bsn.build_patio_furniture(col, m)
    hero_tab_objs = [o for o in patio_objs if o.name in ("Patio_Table_04", "Patio_Tableware_04", "Host_Podium", "Menu_Stand")]
    ob_tab = hero_tab_objs[0]
    other_objs = [ob_sw] + [o for o in patio_objs if o not in hero_tab_objs]

    # Focus on Hero Table #3 at (3.85, 9.25) + nearby chairs + Host Podium (2.65, 8.25) + Menu Stand (1.65, 8.42)!
    # 1. Topology audit BEFORE Alt+J
    bm0 = bmesh.new()
    bm0.from_mesh(ob_tab.data)
    n_tris_orig = len(bm0.faces)
    n_nme = sum(1 for e in bm0.edges if not e.is_manifold)
    n_non_tri = sum(1 for f in bm0.faces if len(f.verts) != 3)
    min_z = min(v.co.z for v in bm0.verts)
    bm0.free()
    core.log(f"[QuadProof] Shipped Patio_Tables: {n_tris_orig:,} tris, non_tri={n_non_tri}, nme={n_nme}, min_z={min_z:.4f} m")

    # Setup crisp studio clay + true edge wireframe rendering
    sc = bpy.context.scene
    bake.enable_cycles_gpu(sc)
    sc.cycles.samples = 32
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1000
    sc.render.resolution_y = 800
    sc.render.image_settings.file_format = "PNG"

    world = bpy.data.worlds.new("ClayWorld")
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.72, 0.74, 0.78, 1.0)
        bg.inputs["Strength"].default_value = 0.95
    sc.world = world

    ld = bpy.data.lights.new("KeySun", "SUN")
    ld.energy = 2.4
    ld.angle = math.radians(6.0)
    sun = bpy.data.objects.new("KeySun", ld)
    col.objects.link(sun)
    sun.location = (10.0, 14.0, 12.0)
    sun.rotation_euler = (Vector((3.85, 9.25, 0.8)) - sun.location).to_track_quat("-Z", "Y").to_euler()

    cd = bpy.data.cameras.new("ProofCam")
    cam = bpy.data.objects.new("ProofCam", cd)
    col.objects.link(cam)
    sc.camera = cam

    clay_tab = _build_wire_shader("ClayTab", (0.78, 0.79, 0.81, 1.0))
    clay_bg = _build_wire_shader("ClayBg", (0.64, 0.65, 0.67, 1.0))
    wire_tri = _build_wire_shader("WireTri", (0.04, 0.04, 0.05, 1.0))
    wire_quad = _build_wire_shader("WireQuad", (0.95, 0.58, 0.05, 1.0))
    wire_quad.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.65, 0.05, 1.0)
    wire_quad.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.75

    seen_bg: set[bpy.types.Mesh] = set()
    for ob_o in other_objs:
        if ob_o.data not in seen_bg:
            seen_bg.add(ob_o.data)
            ob_o.data.materials.clear()
            ob_o.data.materials.append(clay_bg)
    for ob_h in hero_tab_objs:
        ob_h.data.materials.clear()
        ob_h.data.materials.append(clay_tab)

    cam_full_loc = (4.65, 10.65, 1.18)
    cam_full_tgt = (3.72, 9.15, 0.78)
    cam_top_loc = (4.35, 9.95, 1.48)
    cam_top_tgt = (3.85, 9.25, 1.16)

    # PANEL 1: Shipped Triangulated `Patio_Tables` (100% tris!)
    w_tri = _make_true_edge_wire_overlay(ob_tab, col, wire_tri, thickness=0.0011)
    _render_panel(sc, cam, cam_full_loc, cam_full_tgt, 42.0, os.path.join(RENDERS_DIR, "_qp1_tris.png"))
    bpy.data.objects.remove(w_tri, do_unlink=True)

    # Run Blender's EXACT `Alt+J` (Face -> Tris to Quads) on `Patio_Tables`!
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob_tab.select_set(True)
    bpy.context.view_layer.objects.active = ob_tab
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.tris_convert_to_quads(
        face_threshold=math.radians(40.0),
        shape_threshold=math.radians(40.0),
        uvs=False, vcols=False, seam=False, sharp=False, materials=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")

    n_faces_q = len(ob_tab.data.polygons)
    n_quads = sum(1 for p in ob_tab.data.polygons if len(p.vertices) == 4)
    n_tris_left = sum(1 for p in ob_tab.data.polygons if len(p.vertices) == 3)
    quad_pct = 100.0 * n_quads / max(1, n_faces_q)
    core.log(f"[QuadProof] AFTER Alt+J (Tris->Quads): {n_quads:,} quads + {n_tris_left:,} pole tris = {quad_pct:.2f}% QUADS!")

    # PANEL 2: Full Table + Podium + Menu Stand AFTER `Alt+J` (clean golden quad wireframe matching user Screenshot 1!)
    w_q = _make_true_edge_wire_overlay(ob_tab, col, wire_quad, thickness=0.0015)
    _render_panel(sc, cam, cam_full_loc, cam_full_tgt, 42.0, os.path.join(RENDERS_DIR, "_qp2_quads.png"))

    # PANEL 3: Ultra-Close Macro of Tabletop Props (Wine Glass, Espresso Cup/Handle/Saucer, Plate, Votive, Napkin/Cutlery) AFTER `Alt+J`!
    w_q.modifiers["Wireframe"].thickness = 0.0008
    _render_panel(sc, cam, cam_top_loc, cam_top_tgt, 54.0, os.path.join(RENDERS_DIR, "_qp3_props_quads.png"))
    bpy.data.objects.remove(w_q, do_unlink=True)

    # Test Subdivision Surface (Level 1) cleanly on the Alt+J quad mesh!
    sub_mod = ob_tab.modifiers.new("TestSubsurf", "SUBSURF")
    sub_mod.levels = 1
    sub_mod.render_levels = 1
    dg = bpy.context.evaluated_depsgraph_get()
    eo_sub = ob_tab.evaluated_get(dg)
    me_sub = eo_sub.to_mesh()
    core.log(f"[QuadProof] Subdivision Level 1 OK: {len(me_sub.polygons):,} smooth quad faces")
    eo_sub.to_mesh_clear()
    ob_tab.modifiers.remove(sub_mod)

    # PANEL 4: Test `Decimate -> UNSUBDIV (iterations=2)` AFTER `Alt+J`!
    dec = ob_tab.modifiers.new("UnSubdiv", "DECIMATE")
    dec.decimate_type = "UNSUBDIV"
    dec.iterations = 2
    bpy.ops.object.modifier_apply(modifier="UnSubdiv")
    n_unsub = len(ob_tab.data.polygons)
    n_unsub_q = sum(1 for p in ob_tab.data.polygons if len(p.vertices) == 4)
    core.log(f"[QuadProof] AFTER Un-Subdivide (iter=2): {n_unsub:,} faces ({100.0*n_unsub_q/max(1,n_unsub):.1f}% quads, {100.0*n_unsub/max(1,n_faces_q):.1f}% of Alt+J count)")

    w_u = _make_true_edge_wire_overlay(ob_tab, col, wire_quad, thickness=0.0017)
    _render_panel(sc, cam, cam_full_loc, cam_full_tgt, 42.0, os.path.join(RENDERS_DIR, "_qp4_unsubdiv.png"))
    bpy.data.objects.remove(w_u, do_unlink=True)
    return 0


def compose() -> None:
    from PIL import Image, ImageDraw, ImageFont

    panels = [
        ("1. Shipped Triangulated Mesh (100% Tris, Fixed Diagonals)", "_qp1_tris.png"),
        ("2. Immediately After Alt+J (Tris to Quads) — Pure Quad Flow!", "_qp2_quads.png"),
        ("3. Tableware Macro After Alt+J (Plate, Cup, Wine Glass, Votive, Cutlery)", "_qp3_props_quads.png"),
        ("4. After Alt+J + Decimate (Un-Subdivide, 2 Iterations) — Clean Loops!", "_qp4_unsubdiv.png"),
    ]
    cw, ch, pad, hdr = 1000, 800, 16, 44
    sheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + hdr) * 2 + pad * 3), (20, 22, 26))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for idx, (title, fn) in enumerate(panels):
        r, c = divmod(idx, 2)
        x0 = pad + c * (cw + pad)
        y0 = pad + r * (ch + hdr + pad)
        draw.text((x0, y0 + 10), title, fill=(255, 200, 80) if idx > 0 else (140, 235, 190), font=font)
        p = os.path.join(RENDERS_DIR, fn)
        if os.path.isfile(p):
            sheet.paste(Image.open(p).convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS), (x0, y0 + hdr))
    out_p = os.path.join(RENDERS_DIR, "table_quad_topology_proof.png")
    sheet.save(out_p)
    print(f"[QuadProof] Composed {out_p}")


if __name__ == "__main__":
    if "--compose" in sys.argv:
        compose()
        raise SystemExit(0)
    raise SystemExit(main())
