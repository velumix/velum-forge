"""Hardware-Safe Cycles GPU (`OPTIX`/`CUDA`) 2K/4K PBR Texture Baker & Blender 5.2+ Helpers (`vflib.bake`).

Protects workstations against simultaneous GPU + all-core CPU power spikes by:
- Enabling STRICTLY GPU devices (`d.use = (d.type == dev_type)`) — NEVER Hybrid GPU + CPU!
- Enabling GPU denoising (`OPTIX` denoiser or `OPENIMAGEDENOISE` with `denoising_use_gpu = True`)
  so post-render denoising never fires an all-core AVX2 CPU spike on top of a hot GPU!
- Capping Blender CPU threads (`FIXED` <= 8 by default, configurable via `VELUM_BLENDER_THREADS`).
- Using safe tiled Cycles baking/rendering (`tile_size = 512`, `VELUM_CYCLES_TILE_SIZE`).
- Inserting a brief thermal/VRM cooldown pause (`VELUM_BAKE_COOLDOWN`, default 1.0s) between passes.
"""
from __future__ import annotations

import gc
import math
import os
import shutil
import tempfile
import time

import bmesh
import bpy
import numpy as np

from . import core, mats

_LAST_COOLDOWN_TS = 0.0


def _safe_thread_count(threads: int | None = None) -> int:
    if threads is not None and int(threads) > 0:
        return int(threads)
    for var in ("VELUM_BLENDER_THREADS", "VELUM_BAKE_THREADS"):
        env_t = os.environ.get(var, "").strip()
        if env_t.isdigit() and int(env_t) > 0:
            return int(env_t)
    cpus = os.cpu_count() or 8
    return min(8, max(2, cpus // 2))


def _safe_tile_size(tile_size: int | None = None) -> int:
    if tile_size is not None and int(tile_size) >= 64:
        return int(tile_size)
    for var in ("VELUM_CYCLES_TILE_SIZE", "VELUM_BAKE_TILE_SIZE"):
        env_ts = os.environ.get(var, "").strip()
        if env_ts.isdigit() and int(env_ts) >= 64:
            return int(env_ts)
    return 512


def _safe_cooldown_sec(seconds: float | None = None) -> float:
    if seconds is not None:
        return max(0.0, float(seconds))
    raw = os.environ.get("VELUM_BAKE_COOLDOWN", "1.0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def thermal_cooldown(seconds: float | None = None, *, min_gap: float = 0.45) -> None:
    """Brief GC + cooldown pause between heavy Cycles GPU passes to avoid back-to-back PSU transient spikes."""
    global _LAST_COOLDOWN_TS
    sec = _safe_cooldown_sec(seconds)
    now = time.monotonic()
    if sec <= 0.0:
        gc.collect()
        return
    if (now - _LAST_COOLDOWN_TS) < min_gap:
        return
    gc.collect()
    time.sleep(sec)
    _LAST_COOLDOWN_TS = time.monotonic()


cooldown = thermal_cooldown


def configure_safe_threads(sc: bpy.types.Scene, threads: int | None = None) -> int:
    """Cap Blender CPU thread count (`FIXED`) so CPU denoising / BVH builds never spike all cores."""
    t = _safe_thread_count(threads)
    try:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = t
    except Exception:
        pass
    return t


def configure_safe_denoising(sc: bpy.types.Scene, backend: str, use_denoising: bool = True) -> None:
    """Configure GPU-accelerated Cycles denoising so OIDN never triggers an all-core CPU AVX2 spike."""
    sc.cycles.use_denoising = bool(use_denoising)
    if not use_denoising:
        return

    b = (backend or "CPU").upper()
    if b != "CPU":
        try:
            sc.cycles.denoising_use_gpu = True
        except (TypeError, AttributeError):
            pass
    if b == "OPTIX":
        # Prefer pure RT-core OptiX denoiser; fall back to GPU OpenImageDenoise
        try:
            sc.cycles.denoiser = "OPTIX"
            return
        except (TypeError, AttributeError):
            pass

    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except (TypeError, AttributeError):
        pass

    if b != "CPU":
        try:
            sc.cycles.denoising_use_gpu = True
        except (TypeError, AttributeError):
            pass
    else:
        try:
            sc.cycles.denoising_use_gpu = False
        except (TypeError, AttributeError):
            pass


def enable_cycles_gpu(
    sc: bpy.types.Scene,
    *,
    device: str | None = None,
    threads: int | None = None,
    max_threads: int | None = None,
    tile_size: int | None = None,
    use_denoising: bool = True,
    allow_cpu_hybrid: bool = False,
) -> str:
    """Activate Cycles strictly on GPU-only (never Hybrid GPU+CPU) with safe GPU denoising, tiling & thread caps."""
    try:
        import addon_utils

        if "cycles" not in bpy.context.preferences.addons:
            addon_utils.enable("cycles", default_set=False, persistent=False)
    except Exception:
        pass

    sc.render.engine = "CYCLES"
    configure_safe_threads(sc, threads=threads if threads is not None else max_threads)

    ts = _safe_tile_size(tile_size)
    try:
        sc.cycles.use_auto_tile = True
        sc.cycles.tile_size = ts
    except (TypeError, AttributeError):
        pass

    raw_dev = device or os.environ.get("VELUM_CYCLES_DEVICE") or os.environ.get("VELUM_BAKE_DEVICE") or "auto"
    req = raw_dev.strip().lower()
    if req == "cpu":
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.get_devices()
            for d in prefs.devices:
                d.use = (d.type == "CPU")
        except Exception:
            pass
        sc.cycles.device = "CPU"
        configure_safe_denoising(sc, "CPU", use_denoising=use_denoising)
        return "CPU"

    if req in ("optix", "cuda", "hip", "oneapi", "metal"):
        order = (req.upper(),)
    else:
        order = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")

    chosen = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in order:
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == dev_type]
                if devs:
                    # CRITICAL: STRICT GPU-ONLY unless allow_cpu_hybrid=True explicitly requested!
                    for d in prefs.devices:
                        d.use = (d.type == dev_type) or (allow_cpu_hybrid and d.type == "CPU")
                    sc.cycles.device = "GPU"
                    chosen = dev_type
                    break
            except Exception:
                continue
    except Exception:
        pass

    if chosen == "CPU":
        sc.cycles.device = "CPU"

    configure_safe_denoising(sc, chosen, use_denoising=use_denoising)
    return chosen


def lin_arr_to_srgb(arr: np.ndarray) -> np.ndarray:
    """Convert linear `[0, 1]` float buffer to sRGB before `Image.pixels.foreach_set` on 8-bit PNGs."""
    a = np.clip(arr, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(np.maximum(a, 1e-8), 1.0 / 2.4) - 0.055)


def mix_rgba(nt: bpy.types.NodeTree, fac, col_a, col_b) -> bpy.types.NodeSocket:
    """Blender 5.2-safe `ShaderNodeMix(data_type='RGBA')` binding explicit socket indices (0, 6, 7 -> out 2)."""
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.clamp_factor = True
    if isinstance(fac, bpy.types.NodeSocket):
        nt.links.new(fac, mx.inputs[0])
    else:
        mx.inputs[0].default_value = float(fac)
    if isinstance(col_a, bpy.types.NodeSocket):
        nt.links.new(col_a, mx.inputs[6])
    else:
        mx.inputs[6].default_value = col_a
    if isinstance(col_b, bpy.types.NodeSocket):
        nt.links.new(col_b, mx.inputs[7])
    else:
        mx.inputs[7].default_value = col_b
    return mx.outputs[2]


def split_material_border_uv_islands(objs: list[bpy.types.Object], angle_deg: float = 58.0, margin: float = 0.006) -> None:
    """Split multi-material border edges prior to UV packing (then re-weld 3D verts) for zero-staircase stripes."""
    import math

    core.ensure_object_mode()
    for ob in objs:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        border_edges = [e for e in bm.edges if len({f.material_index for f in e.link_faces}) > 1]
        if border_edges:
            bmesh.ops.split_edges(bm, edges=border_edges)
        bm.to_mesh(ob.data)
        bm.free()

    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle_deg), island_margin=margin, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin=margin)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        o.select_set(False)

    for ob in objs:
        bm_w = bmesh.new()
        bm_w.from_mesh(ob.data)
        bmesh.ops.remove_doubles(bm_w, verts=bm_w.verts[:], dist=1e-6)
        bm_w.to_mesh(ob.data)
        bm_w.free()
        ob.data.update()


def _atomic_copy_fsync(src_path: str, dst_path: str, retries: int = 6) -> None:
    """Copy `src_path` -> sibling temp file, fsync to disk, then atomically replace `dst_path` with retry.

    Prevents both OneDrive/cloud-sync `OpenImageIO` write locks and zero-filled (`0x00`) corrupted files
    if system power is unexpectedly interrupted before the OS NTFS write cache flushes.
    """
    abs_dst = os.path.abspath(dst_path)
    dst_dir = os.path.dirname(abs_dst)
    os.makedirs(dst_dir, exist_ok=True)
    staged = os.path.join(dst_dir, f".__vf_stage_{os.getpid()}_{os.path.basename(abs_dst)}")
    try:
        shutil.copy2(src_path, staged)
        try:
            with open(staged, "rb+") as fh:
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            pass
        for attempt in range(retries):
            try:
                os.replace(staged, abs_dst)
                return
            except PermissionError:
                if attempt == retries - 1:
                    raise
                time.sleep(0.4)
    finally:
        if os.path.exists(staged):
            try:
                os.remove(staged)
            except OSError:
                pass


def render_still_safe(
    sc: bpy.types.Scene,
    dst_path: str,
    retries: int = 6,
    cooldown: float | None = None,
    cooldown_sec: float | None = None,
) -> str:
    """Render to local temp directory first, fsync + atomically replace destination, and apply thermal cooldown."""
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    if sc.render.engine == "CYCLES":
        enable_cycles_gpu(sc, use_denoising=bool(sc.cycles.use_denoising))
    else:
        configure_safe_threads(sc)
    tmp_p = os.path.join(tempfile.gettempdir(), f"__vf_rnd_{os.getpid()}_{os.path.basename(dst_path)}")
    sc.render.filepath = tmp_p
    bpy.ops.render.render(write_still=True)
    try:
        _atomic_copy_fsync(tmp_p, dst_path, retries=retries)
    finally:
        try:
            os.remove(tmp_p)
        except OSError:
            pass
    if sc.render.engine == "CYCLES":
        eff_cd = cooldown if cooldown is not None else cooldown_sec
        thermal_cooldown(eff_cd)
    return dst_path


def save_png_8bit(rgba: np.ndarray, path: str, colorspace: str) -> bpy.types.Image:
    """Save a `[H, W, 4]` float32 array in `[0, 1]` to an 8-bit PNG safely via fsync'd atomic replace."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    h, w, _ = rgba.shape
    iname = os.path.basename(path)
    old = bpy.data.images.get(iname)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(iname, width=w, height=h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.clip(rgba, 0.0, 1.0).astype(np.float32).ravel())
    tmp_p = os.path.join(tempfile.gettempdir(), f"__vf_tex_{os.getpid()}_{iname}")
    img.filepath_raw = tmp_p
    img.file_format = "PNG"
    img.save()
    try:
        _atomic_copy_fsync(tmp_p, path, retries=6)
    finally:
        try:
            os.remove(tmp_p)
        except OSError:
            pass
    img.filepath = path
    img.reload()
    img.colorspace_settings.name = colorspace
    return img


# ---------------------------------------------------------------------------
# Dedicated Multi-Set 2048x2048 Cycles PBR Baking & Dual-UV Helpers
# ---------------------------------------------------------------------------

def unique_mesh_reps(objs):
    """Return one representative object per unique `ob.data` pointer."""
    reps = []
    seen = set()
    for o in objs:
        if o is None or o.type != "MESH" or o.data is None:
            continue
        ptr = o.data.as_pointer()
        if ptr not in seen:
            seen.add(ptr)
            reps.append(o)
    return reps


def group_objects_by_asset_set(objs, default_set="main"):
    """Group mesh objects by `ob.get('vf_asset_set', default_set)`."""
    groups = {}
    for o in objs:
        if o is None or o.type != "MESH":
            continue
        skey = str(o.get("vf_asset_set") or default_set)
        groups.setdefault(skey, []).append(o)
    return groups


def split_multi_mat_edges(ob):
    """Split UV/edge boundaries where adjacent faces use different material slots."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    seam_edges = [
        e for e in bm.edges
        if len(e.link_faces) == 2 and e.link_faces[0].material_index != e.link_faces[1].material_index
    ]
    if seam_edges:
        bmesh.ops.split_edges(bm, edges=seam_edges)
        bm.to_mesh(ob.data)
        ob.data.update()
    bm.free()


def reweld_and_clamp_uvs(objs, margin=0.001, weld_dist=1e-6):
    """Re-weld split seam vertices, clamp UVs to `[margin, 1-margin]` FIRST, then nudge degenerate 2D UV triangles."""
    import bmesh
    lo, hi = float(margin), 1.0 - float(margin)
    for o in unique_mesh_reps(objs):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        if weld_dist and weld_dist > 0.0:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=float(weld_dist))
        uv_layer = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.active
        if uv_layer is not None:
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
                if abs(area2) < 1e-10:
                    u1.x = min(hi, u1.x + 0.00015)
                    u2.y = min(hi, u2.y + 0.00015)
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()


def pack_into_rect(objs, rect=(0.0, 0.0, 1.0, 1.0), uv_name="UVMap"):
    """Scale and translate packed `UVMap` islands inside `(u0, v0, u1, v1)`."""
    u0, v0, u1, v1 = rect
    du, dv = u1 - u0, v1 - v0
    for o in unique_mesh_reps(objs):
        uv_layer = o.data.uv_layers.get(uv_name) or o.data.uv_layers.active
        if uv_layer is None:
            continue
        for item in uv_layer.data:
            item.uv.x = u0 + item.uv.x * du
            item.uv.y = v0 + item.uv.y * dv
        o.data.update()


def pack_face_subset_into_rect(ob, face_indices, rect, uv_name="UVMap"):
    """Pack a specific subset of polygon UVs into `rect=(u0, v0, u1, v1)`."""
    uv_layer = ob.data.uv_layers.get(uv_name) or ob.data.uv_layers.active
    if uv_layer is None or not face_indices:
        return
    u0, v0, u1, v1 = rect
    du, dv = u1 - u0, v1 - v0
    us, vs = [], []
    for fi in face_indices:
        poly = ob.data.polygons[fi]
        for li in poly.loop_indices:
            uv = uv_layer.data[li].uv
            us.append(uv.x)
            vs.append(uv.y)
    mnu, mxu = min(us), max(us)
    mnv, mxv = min(vs), max(vs)
    span_u = max(1e-6, mxu - mnu)
    span_v = max(1e-6, mxv - mnv)
    for fi in face_indices:
        poly = ob.data.polygons[fi]
        for li in poly.loop_indices:
            uv = uv_layer.data[li].uv
            uv.x = u0 + ((uv.x - mnu) / span_u) * du
            uv.y = v0 + ((uv.y - mnv) / span_v) * dv
    ob.data.update()


def prepare_dedicated_set_uvs(objs, margin=0.002, downweight_parts=None, downweight_scale=0.35):
    """Unwrap & pack `objs` onto a single non-overlapping `UVMap`, weighting tiny parts down."""
    reps = unique_mesh_reps(objs)
    if not reps:
        return
    down_set = set(downweight_parts or ())
    core.ensure_object_mode()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in reps:
        split_multi_mat_edges(o)
        if "UVMap" not in o.data.uv_layers:
            o.data.uv_layers.new(name="UVMap")
        o.data.uv_layers.active = o.data.uv_layers["UVMap"]
        o.select_set(True)
    bpy.context.view_layer.objects.active = reps[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=margin)
    if down_set:
        bpy.ops.object.mode_set(mode="OBJECT")
        for o in reps:
            if o.name in down_set or any(d in o.name for d in down_set):
                uv_layer = o.data.uv_layers["UVMap"]
                for item in uv_layer.data:
                    item.uv.x = 0.5 + (item.uv.x - 0.5) * downweight_scale
                    item.uv.y = 0.5 + (item.uv.y - 0.5) * downweight_scale
        bpy.context.view_layer.objects.active = reps[0]
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=margin)
    bpy.ops.uv.seams_from_islands()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in reps:
        o.select_set(False)
    reweld_and_clamp_uvs(reps)


def prepare_sign_fixture_uvs(objs, graphic_uv_name="GraphicUV", sign_rect=(0.02, 0.02, 0.62, 0.98),
                             frame_rect=(0.64, 0.02, 0.98, 0.98)):
    """Pack Dual-UV signs/frames: preserve `GraphicUV` artwork faces into `sign_rect`, rest in `frame_rect`."""
    reps = unique_mesh_reps(objs)
    prepare_dedicated_set_uvs(reps)
    for o in reps:
        guv = o.data.uv_layers.get(graphic_uv_name)
        uv = o.data.uv_layers.get("UVMap")
        if guv is None or uv is None:
            continue
        sign_faces, other_faces = [], []
        for poly in o.data.polygons:
            us = [guv.data[li].uv.x for li in poly.loop_indices]
            vs = [guv.data[li].uv.y for li in poly.loop_indices]
            if max(us) - min(us) > 0.02 or max(vs) - min(vs) > 0.02:
                sign_faces.append(poly.index)
                for li in poly.loop_indices:
                    uv.data[li].uv = guv.data[li].uv.copy()
            else:
                other_faces.append(poly.index)
        if sign_faces:
            pack_face_subset_into_rect(o, sign_faces, sign_rect, "UVMap")
        if other_faces:
            pack_face_subset_into_rect(o, other_faces, frame_rect, "UVMap")
    reweld_and_clamp_uvs(reps)


def prepare_continuous_graphic_atlas_uvs(objs, graphic_uv_name="GraphicUV"):
    """Tile multiple continuous artwork/poster faces cleanly into a grid on `UVMap` while preserving `GraphicUV`."""
    reps = unique_mesh_reps(objs)
    prepare_dedicated_set_uvs(reps)
    n = max(1, len(reps))
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    cw, ch = 1.0 / cols, 1.0 / rows
    pad = 0.015
    for idx, o in enumerate(reps):
        r = idx // cols
        c = idx % cols
        rect = (
            c * cw + pad * cw,
            r * ch + pad * ch,
            (c + 1) * cw - pad * cw,
            (r + 1) * ch - pad * ch,
        )
        guv = o.data.uv_layers.get(graphic_uv_name)
        uv = o.data.uv_layers.get("UVMap")
        if guv is not None and uv is not None:
            for li in range(len(uv.data)):
                uv.data[li].uv = guv.data[li].uv.copy()
        pack_into_rect([o], rect, "UVMap")
    reweld_and_clamp_uvs(reps)


def _ensure_bake_target_nodes(mats_list, img):
    added = []
    for m in mats_list:
        if m is None or m.node_tree is None:
            continue
        nt = m.node_tree
        node = nt.nodes.new("ShaderNodeTexImage")
        node.name = "VF_BakeTarget"
        node.image = img
        nt.nodes.active = node
        node.select = True
        added.append((nt, node))
    return added


def _clear_bake_target_nodes(added):
    for nt, node in added:
        if node.name in nt.nodes:
            nt.nodes.remove(node)


def bake_pbr_set(objs, out_dir, prefix, *, res=2048, samples=64, isolate_for_ao=True,
                 cooldown_s=1.0, shared_non_color=None):
    """Bake a 6-map `res x res` Cycles PBR texture set (`Color`, `Normal`, `Roughness`, `Metalness`, `AO`, `ORM`).

    When `shared_non_color` is provided (dict with `Normal`, `Roughness`, `Metalness`, `AO`, `ORM` paths from
    an earlier variant using the identical UV layout), only the variant `Color` pass is re-baked and composited
    with the cached `AO` map (5x faster multi-variant builds!).
    """
    os.makedirs(out_dir, exist_ok=True)
    reps = unique_mesh_reps(objs)
    if not reps:
        return {}

    sc = bpy.context.scene
    enable_cycles_gpu(sc)
    sc.cycles.samples = int(samples)
    all_mats = list({slot.material for o in reps for slot in o.material_slots if slot.material is not None})

    # Helper to execute one bake pass safely into an Image datablock
    def _run_pass(pass_type, colorspace, target_path, bake_filter=None):
        img = bpy.data.images.new(
            f"__vf_bake_{pass_type}_{os.path.basename(target_path)}",
            width=res, height=res, alpha=False, float_buffer=True,
        )
        img.colorspace_settings.name = colorspace
        added = _ensure_bake_target_nodes(all_mats, img)
        hidden_restore = []
        saved_metals = []
        try:
            if pass_type == "DIFFUSE":
                for m in all_mats:
                    if m.node_tree is None:
                        continue
                    bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
                    if bsdf is None or "Metallic" not in bsdf.inputs:
                        continue
                    met_in = bsdf.inputs["Metallic"]
                    links = list(met_in.links)
                    saved_metals.append((m.node_tree, met_in, [lk.from_socket for lk in links], float(met_in.default_value)))
                    for lk in links:
                        m.node_tree.links.remove(lk)
                    met_in.default_value = 0.0
            core.ensure_object_mode()
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            for o in reps:
                o.select_set(True)
            bpy.context.view_layer.objects.active = reps[0]
            if isolate_for_ao and pass_type == "AO":
                rep_set = set(reps)
                for scene_ob in bpy.context.scene.objects:
                    if scene_ob.type == "MESH" and scene_ob not in rep_set and not scene_ob.hide_render:
                        hidden_restore.append(scene_ob)
                        scene_ob.hide_render = True
            sc.render.bake.use_pass_direct = False
            sc.render.bake.use_pass_indirect = False
            sc.render.bake.use_pass_color = True
            sc.render.bake.margin = 16
            kwargs = {"type": pass_type}
            if bake_filter:
                kwargs["pass_filter"] = bake_filter
            bpy.ops.object.bake(**kwargs)
            buf = np.empty(res * res * 4, dtype=np.float32)
            img.pixels.foreach_get(buf)
            arr = buf.reshape((res, res, 4)).copy()
            save_arr = lin_arr_to_srgb(arr) if colorspace == "sRGB" else arr
            saved_img = save_png_8bit(save_arr, target_path, colorspace)
            if saved_img is not None and saved_img != img:
                try:
                    bpy.data.images.remove(saved_img)
                except ReferenceError:
                    pass
            return arr
        finally:
            for nt, met_in, from_socks, orig_val in saved_metals:
                met_in.default_value = orig_val
                for fs in from_socks:
                    nt.links.new(fs, met_in)
            for scene_ob in hidden_restore:
                scene_ob.hide_render = False
            _clear_bake_target_nodes(added)
            try:
                if img.name in bpy.data.images:
                    bpy.data.images.remove(img)
            except ReferenceError:
                pass
            cooldown(cooldown_s)

    paths = {
        "Color": os.path.join(out_dir, f"{prefix}_Color.png"),
        "Normal": os.path.join(out_dir, f"{prefix}_Normal.png"),
        "Roughness": os.path.join(out_dir, f"{prefix}_Roughness.png"),
        "Metalness": os.path.join(out_dir, f"{prefix}_Metalness.png"),
        "AO": os.path.join(out_dir, f"{prefix}_AO.png"),
        "ORM": os.path.join(out_dir, f"{prefix}_ORM.png"),
    }

    diff_buf = _run_pass("DIFFUSE", "sRGB", paths["Color"], bake_filter={"COLOR"})

    can_reuse = bool(
        shared_non_color
        and all(shared_non_color.get(k) and os.path.isfile(shared_non_color[k]) for k in ("Normal", "Roughness", "Metalness", "AO", "ORM"))
    )
    if can_reuse:
        for k in ("Normal", "Roughness", "Metalness", "AO", "ORM"):
            paths[k] = shared_non_color[k]
        ao_img = bpy.data.images.load(paths["AO"], check_existing=False)
        try:
            ao_img.colorspace_settings.name = "Non-Color"
            ao_flat = np.empty(res * res * 4, dtype=np.float32)
            ao_img.pixels.foreach_get(ao_flat)
            ao_buf = ao_flat.reshape((res, res, 4)).copy()
        finally:
            bpy.data.images.remove(ao_img)
        comp_color = diff_buf.copy()
        comp_color[..., :3] *= np.clip(ao_buf[..., :3] * 0.72 + 0.28, 0.0, 1.0)
        comp_img = save_png_8bit(lin_arr_to_srgb(comp_color), paths["Color"], "sRGB")
        if comp_img is not None:
            bpy.data.images.remove(comp_img)
        return paths

    _run_pass("NORMAL", "Non-Color", paths["Normal"])
    rough_buf = _run_pass("ROUGHNESS", "Non-Color", paths["Roughness"])
    ao_buf = _run_pass("AO", "Non-Color", paths["AO"])

    # Bake Metallic via temporary emission wiring from Principled BSDF Metallic input
    saved_links = []
    for m in all_mats:
        if m.node_tree is None:
            continue
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if bsdf and out:
            old_surf = next((lk for lk in nt.links if lk.to_node == out and lk.to_socket.name == "Surface"), None)
            if old_surf:
                saved_links.append((nt, old_surf.from_socket, old_surf.to_socket))
                nt.links.remove(old_surf)
            emit = nt.nodes.new("ShaderNodeEmission")
            emit.name = "VF_TempMetalEmit"
            met_in = bsdf.inputs["Metallic"]
            if met_in.is_linked:
                nt.links.new(met_in.links[0].from_socket, emit.inputs["Color"])
            else:
                v = float(met_in.default_value)
                emit.inputs["Color"].default_value = (v, v, v, 1.0)
            nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    try:
        met_buf = _run_pass("EMIT", "Non-Color", paths["Metalness"])
    finally:
        for nt, from_s, to_s in saved_links:
            emit = nt.nodes.get("VF_TempMetalEmit")
            if emit:
                nt.nodes.remove(emit)
            nt.links.new(from_s, to_s)

    # Composite Color * AO (in linear space before sRGB) and ORM (R=AO, G=Roughness, B=Metalness)
    comp_color = diff_buf.copy()
    comp_color[..., :3] *= np.clip(ao_buf[..., :3] * 0.72 + 0.28, 0.0, 1.0)
    comp_img = save_png_8bit(lin_arr_to_srgb(comp_color), paths["Color"], "sRGB")
    if comp_img is not None:
        bpy.data.images.remove(comp_img)

    orm = np.ones((res, res, 4), dtype=np.float32)
    orm[..., 0] = ao_buf[..., 0]
    orm[..., 1] = rough_buf[..., 0]
    orm[..., 2] = met_buf[..., 0]
    orm_img = save_png_8bit(orm, paths["ORM"], "Non-Color")
    if orm_img is not None:
        bpy.data.images.remove(orm_img)
    return paths


def make_baked_pbr_material(name, tex_paths):
    """Create a clean Principled PBR material wired to `tex_paths` (`UVMap`)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    def _load(key, cs):
        p = tex_paths.get(key)
        if not p or not os.path.exists(p):
            return None
        img = bpy.data.images.load(p, check_existing=True)
        img.colorspace_settings.name = cs
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        return tex

    t_col = _load("Color", "sRGB")
    if t_col:
        nt.links.new(t_col.outputs["Color"], bsdf.inputs["Base Color"])
    t_rgh = _load("Roughness", "Non-Color")
    if t_rgh:
        nt.links.new(t_rgh.outputs["Color"], bsdf.inputs["Roughness"])
    t_met = _load("Metalness", "Non-Color")
    if t_met:
        nt.links.new(t_met.outputs["Color"], bsdf.inputs["Metallic"])
    t_nrm = _load("Normal", "Non-Color")
    if t_nrm:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(t_nrm.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def assign_baked_and_strip_graphic_uv(objs, mat, graphic_uv_name="GraphicUV"):
    """Assign baked PBR `mat` to `objs` and strip temporary `GraphicUV` layers."""
    for o in unique_mesh_reps(objs):
        o.data.materials.clear()
        o.data.materials.append(mat)
        guv = o.data.uv_layers.get(graphic_uv_name)
        if guv is not None:
            o.data.uv_layers.remove(guv)
        o.data.update()
