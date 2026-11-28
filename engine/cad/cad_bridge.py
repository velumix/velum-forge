"""Precision B-Rep CAD (build123d) <-> Mesh/QA/Decimation bridge for Velum Forge.

Provides importable helpers (`export_cad_part`, `export_cad_assembly`, `inspect_mesh_file`)
and CLI subcommands (`inspect`, `step-to-glb`, `decimate`, `repair`).

Conventions:
- Modeling coordinates inside build123d scripts and Blender: 1 unit = 1.0 meter, +Z = Up.
- GLB export converts Z-up -> glTF Y-up once, welding vertices via trimesh (`process=True`)
  so Blender's glTF importer produces clean watertight meshes at exact 1:1 meter scale.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pymeshlab
import trimesh
from build123d import Compound, Shape, Unit, export_step, import_step

STUDS_PER_METER_SCLIB = 3.0
ROBLOX_METERS_PER_STUD = 0.28
ROBLOX_MAX_TRIS_PER_PART = 20000

# Blender/CAD (+X right, +Y forward, +Z up) -> glTF (+X right, +Y up, -Z forward)
R_ZUP_TO_GLTF = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=float,
)
R_GLTF_TO_ZUP = R_ZUP_TO_GLTF.T


def _parse_rgba(color: Any) -> list[int]:
    if color is None:
        return [195, 200, 208, 255]
    if isinstance(color, str):
        s = color.lstrip("#")
        if len(s) == 6:
            return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255]
        if len(s) == 8:
            return [int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16)]
    if hasattr(color, "to_tuple"):
        vals = color.to_tuple()
        return [int(round(max(0.0, min(1.0, v)) * 255)) for v in (list(vals) + [1.0])[:4]]
    if isinstance(color, (tuple, list)):
        vals = list(color)
        if all(isinstance(v, float) and v <= 1.0 for v in vals):
            vals = [int(round(max(0.0, min(1.0, v)) * 255)) for v in vals]
        else:
            vals = [int(v) for v in vals]
        return (vals + [255])[:4]
    return [195, 200, 208, 255]


def _shape_to_trimesh(
    shape: Shape,
    *,
    linear_deflection: float = 0.001,
    angular_deflection: float = 0.35,
    scale_factor: float = 1.0,
    color: Any = None,
    metallic: float = 0.2,
    roughness: float = 0.45,
) -> trimesh.Trimesh:
    try:
        from OCP.BRepTools import BRepTools

        if getattr(shape, "wrapped", None) is not None:
            BRepTools.Clean_s(shape.wrapped)
    except Exception:
        pass

    verts, tris = shape.tessellate(tolerance=linear_deflection, angular_tolerance=angular_deflection)
    if not verts or not tris:
        raise ValueError("Shape tessellation produced empty geometry.")

    v_arr = np.array([tuple(v) for v in verts], dtype=float) * float(scale_factor)
    f_arr = np.array(tris, dtype=int)
    mesh = trimesh.Trimesh(vertices=v_arr, faces=f_arr, process=True)
    mesh.update_faces(mesh.nondegenerate_faces(height=1e-8))
    mesh.remove_unreferenced_vertices()
    if not mesh.is_winding_consistent:
        mesh.fix_normals()
    if mesh.is_watertight and mesh.volume < 0:
        mesh.invert()
    mesh.apply_transform(R_ZUP_TO_GLTF)

    rgba = _parse_rgba(color if color is not None else getattr(shape, "color", None))
    mat = trimesh.visual.material.PBRMaterial(
        baseColorFactor=rgba,
        metallicFactor=float(metallic),
        roughnessFactor=float(roughness),
    )
    mesh.visual = trimesh.visual.TextureVisuals(material=mat)
    return mesh


def _write_scene_glb(named_meshes: dict[str, trimesh.Trimesh], out_glb: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_glb)), exist_ok=True)
    scene = trimesh.Scene()
    for part_name, mesh in named_meshes.items():
        scene.add_geometry(mesh, node_name=part_name, geom_name=part_name)
    scene.export(out_glb)


def export_cad_part(
    shape: Shape,
    out_dir: str | os.PathLike[str],
    name: str,
    *,
    export_step_file: bool = True,
    export_glb_file: bool = True,
    linear_deflection: float = 0.001,
    angular_deflection: float = 0.35,
    color: Any = None,
    metallic: float = 0.2,
    roughness: float = 0.45,
) -> dict[str, Any]:
    """Export a single build123d Shape (modeled in meters) to STEP + watertight GLB and inspect it."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    step_path = str(out_path / f"{name}.step") if export_step_file else None
    glb_path = str(out_path / f"{name}.glb") if export_glb_file else None

    if step_path:
        export_step(shape, step_path, unit=Unit.M)

    inspection: dict[str, Any] | None = None
    if glb_path:
        mesh = _shape_to_trimesh(
            shape,
            linear_deflection=linear_deflection,
            angular_deflection=angular_deflection,
            color=color,
            metallic=metallic,
            roughness=roughness,
        )
        _write_scene_glb({name: mesh}, glb_path)
        inspection = inspect_mesh_file(glb_path)

    return {
        "name": name,
        "step": step_path,
        "glb": glb_path,
        "inspection": inspection,
    }


def export_cad_assembly(
    parts: dict[str, Shape | dict[str, Any]],
    out_dir: str | os.PathLike[str],
    name: str,
    *,
    export_step_file: bool = True,
    export_glb_file: bool = True,
    linear_deflection: float = 0.001,
    angular_deflection: float = 0.35,
) -> dict[str, Any]:
    """Export a named dict of build123d Shapes (modeled in meters) to STEP + multi-node GLB."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    step_path = str(out_path / f"{name}.step") if export_step_file else None
    glb_path = str(out_path / f"{name}.glb") if export_glb_file else None

    labeled_shapes: list[Shape] = []
    named_meshes: dict[str, trimesh.Trimesh] = {}

    for part_name, entry in parts.items():
        if isinstance(entry, dict):
            shp = entry["shape"]
            color = entry.get("color")
            metallic = entry.get("metallic", 0.2)
            roughness = entry.get("roughness", 0.45)
        else:
            shp = entry
            color = None
            metallic = 0.2
            roughness = 0.45

        shp.label = part_name
        labeled_shapes.append(shp)
        if glb_path:
            named_meshes[part_name] = _shape_to_trimesh(
                shp,
                linear_deflection=linear_deflection,
                angular_deflection=angular_deflection,
                color=color,
                metallic=metallic,
                roughness=roughness,
            )

    if step_path:
        comp = Compound(children=labeled_shapes)
        comp.label = name
        export_step(comp, step_path, unit=Unit.M)

    inspection: dict[str, Any] | None = None
    if glb_path:
        _write_scene_glb(named_meshes, glb_path)
        inspection = inspect_mesh_file(glb_path)

    return {
        "name": name,
        "step": step_path,
        "glb": glb_path,
        "part_count": len(parts),
        "inspection": inspection,
    }


def _collect_scene_meshes(loaded: trimesh.Trimesh | trimesh.Scene, convert_y_to_z: bool) -> list[tuple[str, trimesh.Trimesh]]:
    pairs: list[tuple[str, trimesh.Trimesh]] = []
    if isinstance(loaded, trimesh.Trimesh):
        m = loaded.copy()
        if convert_y_to_z:
            m.apply_transform(R_GLTF_TO_ZUP)
        pairs.append(("Mesh", m))
        return pairs

    for node_name in loaded.graph.nodes_geometry:
        xf, geom_name = loaded.graph.get(node_name)
        geom = loaded.geometry[geom_name].copy()
        geom.apply_transform(xf)
        if convert_y_to_z:
            geom.apply_transform(R_GLTF_TO_ZUP)
        pairs.append((str(node_name or geom_name), geom))
    return pairs


def inspect_mesh_file(path: str | os.PathLike[str], max_tris_per_part: int = ROBLOX_MAX_TRIS_PER_PART) -> dict[str, Any]:
    """Inspect a GLB/GLTF/STL/OBJ/PLY mesh for watertightness, tri budget, scale, and grounding."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mesh not found: {p}")

    ext = p.suffix.lower()
    is_gltf = ext in (".glb", ".gltf")
    loaded = trimesh.load(str(p), force=None)
    meshes = _collect_scene_meshes(loaded, convert_y_to_z=is_gltf)

    if not meshes:
        raise ValueError(f"No mesh geometries found in {p}")

    errors: list[str] = []
    warnings: list[str] = []
    part_reports: list[dict[str, Any]] = []

    bmin = np.array([np.inf, np.inf, np.inf], dtype=float)
    bmax = np.array([-np.inf, -np.inf, -np.inf], dtype=float)
    total_tris = 0
    total_verts = 0
    all_watertight = True

    for part_name, m in meshes:
        tris = int(len(m.faces))
        verts = int(len(m.vertices))
        wt = bool(m.is_watertight)
        wc = bool(m.is_winding_consistent)
        vol = float(m.volume) if wt else None
        extents = [round(float(x), 5) for x in m.extents]

        bmin = np.minimum(bmin, m.bounds[0])
        bmax = np.maximum(bmax, m.bounds[1])
        total_tris += tris
        total_verts += verts
        if not wt:
            all_watertight = False
            warnings.append(f"{part_name}: mesh is not watertight")
        if not wc:
            errors.append(f"{part_name}: inconsistent face winding")
        if tris > max_tris_per_part:
            errors.append(f"{part_name}: {tris} tris > Roblox limit {max_tris_per_part}")

        part_reports.append(
            {
                "name": part_name,
                "tris": tris,
                "verts": verts,
                "watertight": wt,
                "winding_consistent": wc,
                "euler_number": int(m.euler_number),
                "volume_m3": round(vol, 8) if vol is not None else None,
                "size_m": extents,
                "size_studs_sclib": [round(x * STUDS_PER_METER_SCLIB, 3) for x in extents],
            }
        )

    size_m = (bmax - bmin).tolist()
    ground_z = round(float(bmin[2]), 5)
    x_sym_offset = round(float(abs(bmin[0] + bmax[0])), 5)
    if abs(ground_z) > 0.002:
        warnings.append(f"lowest Z={ground_z} m (not resting on Z=0)")

    return {
        "pass": len(errors) == 0,
        "file": str(p.resolve()),
        "up_axis_evaluated": "Z-up (meters)",
        "errors": errors,
        "warnings": warnings,
        "totals": {
            "parts": len(part_reports),
            "tris": total_tris,
            "verts": total_verts,
            "all_watertight": all_watertight,
            "bbox_min_m": [round(float(x), 5) for x in bmin],
            "bbox_max_m": [round(float(x), 5) for x in bmax],
            "size_m": [round(float(x), 5) for x in size_m],
            "size_studs_sclib": [round(float(x) * STUDS_PER_METER_SCLIB, 3) for x in size_m],
            "size_studs_metric": [round(float(x) / ROBLOX_METERS_PER_STUD, 3) for x in size_m],
            "ground_z_m": ground_z,
            "x_symmetry_offset_m": x_sym_offset,
        },
        "parts": part_reports,
    }


def step_to_glb(
    in_step: str,
    out_glb: str,
    *,
    linear_deflection: float = 0.001,
    angular_deflection: float = 0.35,
) -> dict[str, Any]:
    """Import a STEP file (build123d normalizes coordinates to mm) and export 1:1 meter GLB."""
    comp = import_step(in_step)
    solids = list(comp.solids())
    named_meshes: dict[str, trimesh.Trimesh] = {}

    if solids:
        for idx, solid in enumerate(solids):
            raw_name = (getattr(solid, "label", "") or "").strip()
            part_name = raw_name if raw_name and raw_name not in named_meshes else f"Solid_{idx:02d}"
            named_meshes[part_name] = _shape_to_trimesh(
                solid,
                linear_deflection=linear_deflection,
                angular_deflection=angular_deflection,
                scale_factor=0.001,  # STEP import is in mm -> convert to meters
            )
    else:
        named_meshes["Part"] = _shape_to_trimesh(
            comp,
            linear_deflection=linear_deflection,
            angular_deflection=angular_deflection,
            scale_factor=0.001,
        )

    _write_scene_glb(named_meshes, out_glb)
    return inspect_mesh_file(out_glb)


def _save_pymeshlab_output(ms: pymeshlab.MeshSet, in_path: str, out_path: str) -> None:
    out_ext = Path(out_path).suffix.lower()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if out_ext in (".glb", ".gltf"):
        with tempfile.TemporaryDirectory() as td:
            tmp_ply = os.path.join(td, "mesh.ply")
            ms.save_current_mesh(tmp_ply)
            mesh = trimesh.load(tmp_ply, force="mesh")
            if Path(in_path).suffix.lower() not in (".glb", ".gltf"):
                mesh.apply_transform(R_ZUP_TO_GLTF)
            _write_scene_glb({Path(out_path).stem: mesh}, out_path)
    else:
        ms.save_current_mesh(out_path)


def decimate_mesh(
    in_path: str,
    out_path: str,
    target_tris: int,
    preserve_topology: bool = True,
) -> dict[str, Any]:
    """Decimate a mesh with PyMeshLab Quadric Edge Collapse while keeping geometry clean."""
    before = inspect_mesh_file(in_path)
    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(in_path)
    ms.meshing_decimation_quadric_edge_collapse(
        targetfacenum=int(target_tris),
        preservenormal=True,
        preserveboundary=True,
        preservetopology=bool(preserve_topology),
        planarquadric=True,
    )
    _save_pymeshlab_output(ms, in_path, out_path)
    after = inspect_mesh_file(out_path)
    return {"before_tris": before["totals"]["tris"], "after_tris": after["totals"]["tris"], "after": after}


def repair_mesh(in_path: str, out_path: str) -> dict[str, Any]:
    """Clean duplicate/degenerate geometry, close holes, and orient faces outward."""
    before = inspect_mesh_file(in_path)
    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(in_path)
    ms.meshing_remove_duplicate_vertices()
    ms.meshing_remove_duplicate_faces()
    ms.meshing_repair_non_manifold_edges()
    ms.meshing_repair_non_manifold_vertices()
    try:
        ms.meshing_close_holes(maxholesize=30)
    except Exception:
        pass
    try:
        ms.meshing_re_orient_faces_coherently()
    except Exception:
        pass
    _save_pymeshlab_output(ms, in_path, out_path)
    after = inspect_mesh_file(out_path)
    return {"before": before["totals"], "after": after}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Velum Forge B-Rep CAD & Mesh QA Bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ins = sub.add_parser("inspect", help="Inspect GLB/GLTF/STL/OBJ/PLY mesh metrics & Roblox budgets")
    p_ins.add_argument("mesh_path")
    p_ins.add_argument("--max-tris", type=int, default=ROBLOX_MAX_TRIS_PER_PART)
    p_ins.add_argument("--json", action="store_true")

    p_step = sub.add_parser("step-to-glb", help="Convert a STEP CAD assembly to 1:1 meter watertight GLB")
    p_step.add_argument("in_step")
    p_step.add_argument("out_glb")
    p_step.add_argument("--linear-deflection", type=float, default=0.001)
    p_step.add_argument("--angular-deflection", type=float, default=0.35)

    p_dec = sub.add_parser("decimate", help="Decimate mesh via Quadric Edge Collapse to target triangle budget")
    p_dec.add_argument("in_path")
    p_dec.add_argument("out_path")
    p_dec.add_argument("--target-tris", type=int, required=True)
    p_dec.add_argument("--no-preserve-topology", action="store_true")

    p_rep = sub.add_parser("repair", help="Repair duplicate/non-manifold faces and re-orient normals")
    p_rep.add_argument("in_path")
    p_rep.add_argument("out_path")

    args = parser.parse_args(argv)

    if args.cmd == "inspect":
        rep = inspect_mesh_file(args.mesh_path, max_tris_per_part=args.max_tris)
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            t = rep["totals"]
            status = "PASS" if rep["pass"] else "FAIL"
            print(
                f"[{status}] {rep['file']}\n"
                f"  parts={t['parts']} tris={t['tris']:,} verts={t['verts']:,} watertight={t['all_watertight']}\n"
                f"  size(m)={t['size_m']} studs(3/m)={t['size_studs_sclib']} ground_z={t['ground_z_m']}m"
            )
            for part in rep["parts"]:
                print(
                    f"  - {part['name']}: {part['tris']:,} tris | wt={part['watertight']} | "
                    f"size_m={part['size_m']}"
                )
            for err in rep["errors"]:
                print(f"  ERROR: {err}", file=sys.stderr)
            for warn in rep["warnings"]:
                print(f"  WARN:  {warn}", file=sys.stderr)
        return 0 if rep["pass"] else 1

    if args.cmd == "step-to-glb":
        rep = step_to_glb(
            args.in_step,
            args.out_glb,
            linear_deflection=args.linear_deflection,
            angular_deflection=args.angular_deflection,
        )
        print(json.dumps(rep, indent=2))
        return 0 if rep["pass"] else 1

    if args.cmd == "decimate":
        res = decimate_mesh(
            args.in_path,
            args.out_path,
            target_tris=args.target_tris,
            preserve_topology=not args.no_preserve_topology,
        )
        print(json.dumps(res, indent=2))
        return 0 if res["after"]["pass"] else 1

    if args.cmd == "repair":
        res = repair_mesh(args.in_path, args.out_path)
        print(json.dumps(res, indent=2))
        return 0 if res["after"]["pass"] else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

