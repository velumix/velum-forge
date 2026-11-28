"""Roblox export: bake -> join per MeshPart -> studs -> palette atlas -> FBX + manifest + Studio setup.

Typical use (inside an asset build script):

    from sclib import export
    export.export_roblox("Sunrunner", out_dir, parts=[
        dict(name="Hull", objects=[...], collide=True),
        dict(name="PaintPrimary", objects=[...], role="paint"),
        dict(name="Glass", objects=[...], role="glass", transparency=0.55),
    ], primary=dict(name="Boat", center=Vector(...), size=Vector(...)), attributes={...}, tags=["Boat"])

Socket (`SOCKET_*`) and seat (`SEAT_*`) empties are picked up from `source_collection`.
"""

import json
import os

import bpy
from mathutils import Vector

from . import core, gameready, palette

TEMPLATE = os.path.join(core.LIB_DIR, "templates", "studio_setup.luau")
ROLE_DEFAULTS = {
    "solid": dict(material=None, transparency=0.0),
    "paint": dict(material="SmoothPlastic", transparency=0.0),
    "glass": dict(material="Glass", transparency=0.55),
    "neon": dict(material="Neon", transparency=0.0),
}


def to_roblox(v):
    """Blender axes (X right, Y forward, Z up) -> Roblox axes (X right, Y up, -Z forward)."""
    return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]


def _frame(ob, spm):
    mw = ob.matrix_world
    rot = mw.to_3x3().normalized()
    return dict(
        position=to_roblox(mw.translation * spm),
        look=to_roblox((rot @ Vector((0, 1, 0))).normalized()),
        up=to_roblox((rot @ Vector((0, 0, 1))).normalized()),
    )


def _free_name(name, renamed_sources=None):
    """Make `name` available for an export object while tracking renames so we can restore them."""
    clash = bpy.data.objects.get(name)
    if clash is not None:
        orig_name = clash.name
        clash.name = name + "_src"
        if renamed_sources is not None:
            renamed_sources.append((clash, orig_name))
        core.log(f"temporarily renamed source object '{orig_name}' -> '{clash.name}' during export")


def parts_from_collection(col):
    """Group meshes by their `sc_part` tag -> list of part specs (role from `sc_role`)."""
    groups = {}
    for ob in core.objects_in(col):
        name = ob.get("sc_part")
        if not name or ob.hide_render:
            continue
        spec = groups.setdefault(name, dict(name=name, objects=[], role=ob.get("sc_role", "solid")))
        spec["objects"].append(ob)
    return list(groups.values())


def _to_luau_texture_sets(tex_sets_manifest):
    if not tex_sets_manifest:
        return "{}"
    lines = ["{"]
    for skey in sorted(tex_sets_manifest):
        maps = tex_sets_manifest[skey] or {}
        lines.append(f'\t["{skey}"] = {{')
        for mk in ("Color", "Normal", "Roughness", "Metalness"):
            fname = os.path.basename(str(maps.get(mk, "")))
            hint = f" -- rbxassetid://... ({fname})" if fname else ""
            lines.append(f'\t\t{mk} = "",{hint}')
        lines.append("\t},")
    lines.append("}")
    return "\n".join(lines)


def export_roblox(asset_name, out_dir, parts, *, source_collection=None, primary=None, hinges=(),
                  attributes=None, tags=(), reference=None, spm=core.STUDS_PER_METER, palette_size=256,
                  keep=False, fbx_name=None, prebaked_material=None, prebaked_textures=None,
                  prebaked_texture_sets=None, prebaked_materials_by_set=None,
                  max_tris=gameready.ROBLOX_MAX_TRIS_PER_MESH, extra_manifest=None):
    import shutil
    core.ensure_object_mode()
    os.makedirs(out_dir, exist_ok=True)
    tex_dir = os.path.join(out_dir, "textures")
    os.makedirs(tex_dir, exist_ok=True)
    exp_col = core.fresh_collection("EXPORT_" + asset_name)
    renamed_sources = []

    try:
        built = []  # (spec, object, game colour)
        for spec in parts:
            srcs = [o for o in spec["objects"] if o.type == "MESH"]
            if not srcs:
                core.log(f"part {spec['name']}: no meshes, skipped")
                continue
            _free_name(spec["name"], renamed_sources)
            baked = [gameready.bake_object(o, f"__{spec['name']}_{i}", exp_col) for i, o in enumerate(srcs)]
            ob = gameready.join(baked, spec["name"])
            gameready.collapse_materials(ob)
            gameready.scale_mesh(ob, spm)
            first = ob.data.materials[0] if ob.data.materials else None
            color = spec.get("color") or (palette.game_values(first)[0] if first else (1, 1, 1))
            built.append((spec, ob, color))

        all_objs = [b[1] for b in built]
        tex_sets_manifest = {}
        if prebaked_texture_sets:
            for skey, maps in prebaked_texture_sets.items():
                rel_maps = {}
                for mk, src_p in (maps or {}).items():
                    if not src_p:
                        continue
                    src_str = str(src_p)
                    bname = os.path.basename(src_str)
                    dst_p = os.path.join(tex_dir, bname)
                    if os.path.exists(src_str) and os.path.abspath(src_str) != os.path.abspath(dst_p):
                        shutil.copy2(src_str, dst_p)
                    rel_maps[mk] = f"textures/{bname}"
                tex_sets_manifest[skey] = rel_maps

        if prebaked_materials_by_set or (prebaked_material is not None and prebaked_textures is not None):
            tex_dict = dict(prebaked_textures or {})
            if not tex_dict and tex_sets_manifest:
                first_key = next(iter(tex_sets_manifest))
                tex_dict = dict(tex_sets_manifest[first_key])
            mats_by_set = dict(prebaked_materials_by_set or {})
            for spec, ob, _c in built:
                role = str(spec.get("role", "solid"))
                if role == "solid" or role.startswith("baked_"):
                    tset = spec.get("texture_set") or spec.get("asset_set")
                    mat_to_use = mats_by_set.get(tset) if tset else prebaked_material
                    if mat_to_use is not None:
                        palette.assign_single(ob, mat_to_use)
        else:
            mats = palette.collect_materials(all_objs)
            rects, images = palette.build_atlas(mats, f"{asset_name}_Palette", tex_dir, palette_size)
            pmat = palette.palette_material(f"{asset_name}_Palette", images)
            for _spec, ob, _c in built:
                palette.apply_uvs(ob, rects)
                palette.assign_single(ob, pmat)
            tex_dict = {k: f"textures/{asset_name}_Palette_{k}.png" for k in ("Color", "Roughness", "Metalness")}

        reports = gameready.validate(all_objs, max_tris=max_tris, deduplicate_meshes=True)

        # FBX
        fbx_path = os.path.join(out_dir, (fbx_name or asset_name) + ".fbx")
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        for o in all_objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = all_objs[0]
        bpy.ops.export_scene.fbx(
            filepath=fbx_path,
            use_selection=True,
            object_types={"MESH"},
            apply_scale_options="FBX_SCALE_NONE",
            use_triangles=True,
            mesh_smooth_type="OFF",
            use_mesh_modifiers=False,
            add_leaf_bones=False,
            path_mode="COPY",
            embed_textures=False,
            bake_anim=False,
        )
        for o in all_objs:
            o.select_set(False)

        # Manifest
        manifest_parts = {}
        for spec, ob, color in built:
            role = spec.get("role", "solid")
            d = dict(ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["solid"]))
            lo, hi = core.world_bbox([ob])
            rep = next((r for r in reports if r["name"] == ob.name), {"tris": gameready.triangle_count(ob, False)})
            tset = spec.get("texture_set") or spec.get("asset_set")
            manifest_parts[ob.name] = dict(
                role=role,
                center=to_roblox((lo + hi) / 2),
                size=[abs(c) for c in to_roblox(hi - lo)],
                tris=rep["tris"],
                collide=bool(spec.get("collide", False)),
                render_fidelity=spec.get("render_fidelity", "Precise" if ob.name in ("Hull", "PaintPrimary") else "Automatic"),
                color=[round(c, 4) for c in color],
                material=spec.get("material", d["material"]),
                transparency=spec.get("transparency", d["transparency"]),
                group=spec.get("group"),
                rename=spec.get("rename"),
                texture_set=tset,
            )

        sockets, seats = [], []
        if source_collection is not None:
            for ob in source_collection.all_objects:
                if "sc_socket" in ob:
                    s = dict(name=ob["sc_socket"], **_frame(ob, spm))
                    for key in ("parent_part", "emitter", "hinge_only"):
                        if ("sc_" + key) in ob:
                            s["parent" if key == "parent_part" else key] = ob["sc_" + key]
                    sockets.append(s)
                elif "sc_seat" in ob:
                    seats.append(dict(name=ob["sc_seat"], driver=bool(ob.get("sc_driver", False)),
                                      size=list(ob.get("sc_size_studs", (2, 1, 2))), **_frame(ob, spm)))
        sockets.sort(key=lambda s: s["name"])
        seats.sort(key=lambda s: (not s["driver"], s["name"]))

        prim = None
        if primary:
            c, sz = Vector(primary["center"]) * spm, Vector(primary["size"]) * spm
            prim = dict(name=primary.get("name", "Primary"), position=to_roblox(c), look=[0, 0, -1], up=[0, 1, 0],
                        size=[round(sz.x, 3), round(sz.z, 3), round(sz.y, 3)])

        manifest = dict(
            schemaVersion=1,
            asset=asset_name,
            generator="tools/blender/sclib",
            studsPerMeter=spm,
            axes="Blender +X/+Y/+Z -> Roblox +X/-Z/+Y (Blender +Y = Roblox LookVector)",
            fbx=os.path.basename(fbx_path),
            textures=tex_dict,
            texture_sets=tex_sets_manifest,
            reference=reference or built[0][1].name,
            primary=prim,
            parts=manifest_parts,
            sockets=sockets,
            seats=seats,
            hinges=list(hinges),
            attributes=attributes or {},
            tags=list(tags),
            totalTris=sum(p["tris"] for p in manifest_parts.values()),
        )
        if extra_manifest:
            manifest.update(extra_manifest)
        man_path = os.path.join(out_dir, f"{asset_name}.manifest.json")
        with open(man_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        with open(TEMPLATE, encoding="utf-8") as fh:
            luau = (
                fh.read()
                .replace("__ASSET__", asset_name)
                .replace("__TEXTURE_SETS__", _to_luau_texture_sets(tex_sets_manifest))
                .replace("__MANIFEST__", json.dumps(manifest, indent=1))
            )
        luau_path = os.path.join(out_dir, f"{asset_name}.studio_setup.luau")
        with open(luau_path, "w", encoding="utf-8") as fh:
            fh.write(luau)

        if keep:
            core.set_collection_visible(exp_col, False)
        else:
            core.clear_collection(exp_col)
            bpy.data.collections.remove(exp_col)
        core.log(f"exported {fbx_path} ({manifest['totalTris']} tris, {len(built)} parts)")
        return dict(fbx=fbx_path, manifest=man_path, setup=luau_path, report=reports, data=manifest)
    finally:
        if not keep:
            for clash, orig_name in reversed(renamed_sources):
                try:
                    if clash.name in bpy.data.objects and bpy.data.objects.get(orig_name) is None:
                        clash.name = orig_name
                except ReferenceError:
                    pass

