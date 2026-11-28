"""Hardware-Safe Headless Blender Wrapper for `vforge bake` (`engine/blender/safe_bake_runner.py`).

Enforces strict GPU-only Cycles execution (disabling hybrid GPU+CPU raytracing), GPU denoising,
capped CPU threads, tiled Cycles execution, and brief inter-pass thermal/transient cooldowns across
ALL `bpy.ops.object.bake` and `bpy.ops.render.render` calls—even inside custom, legacy, or
AI-generated `bake_lod_variants.py` scripts that might otherwise enable `d.use = True` on all
devices or run back-to-back passes without cooldowns.

Usage:
    blender -b --factory-startup -t 8 --python-exit-code 1 \
        -P engine/blender/safe_bake_runner.py -- <path/to/bake_lod_variants.py> [extra_args...]
"""
from __future__ import annotations

import os
import runpy
import sys

import bpy

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from vflib import bake  # noqa: E402


def _enforce_hardware_safe_cycles(scene: bpy.types.Scene | None = None) -> str:
    sc = scene or bpy.context.scene
    if sc is None:
        return "CPU"
    if sc.render.engine == "CYCLES":
        return bake.enable_cycles_gpu(sc, use_denoising=bool(sc.cycles.use_denoising))
    bake.configure_safe_threads(sc)
    return sc.render.engine


class _SafeOpProxy:
    """Thin callable wrapper around `bpy.ops.object.bake` / `bpy.ops.render.render`."""

    def __init__(self, op, is_bake: bool) -> None:
        self._op = op
        self._is_bake = is_bake

    def __call__(self, *args, **kwargs):
        sc = bpy.context.scene
        _enforce_hardware_safe_cycles(sc)
        try:
            return self._op(*args, **kwargs)
        finally:
            if self._is_bake or (sc is not None and sc.render.engine == "CYCLES"):
                bake.thermal_cooldown()

    def __getattr__(self, name: str):
        return getattr(self._op, name)


def _install_ops_guard() -> None:
    """Intercept `bpy.ops.object.bake` & `bpy.ops.render.render` in headless mode.

    Blender 5.x does not fire `bpy.app.handlers.object_bake_pre` for synchronous headless `-b`
    `bpy.ops.object.bake()` invocations; wrapping `_bpy_ops_submodule__getattr__` guarantees every
    bake and render pass is guarded with zero overhead for other operators.
    """
    ops_mod = bpy.ops
    orig_getattr = getattr(ops_mod, "_bpy_ops_submodule__getattr__", None)
    if orig_getattr is None or getattr(orig_getattr, "_vf_guarded", False):
        return

    def _guarded_submodule_getattr(module: str, func: str):
        op = orig_getattr(module, func)
        if module == "object" and func == "bake":
            return _SafeOpProxy(op, is_bake=True)
        if module == "render" and func == "render":
            return _SafeOpProxy(op, is_bake=False)
        return op

    _guarded_submodule_getattr._vf_guarded = True  # type: ignore[attr-defined]
    ops_mod._bpy_ops_submodule__getattr__ = _guarded_submodule_getattr


@bpy.app.handlers.persistent
def _on_render_pre(scene: bpy.types.Scene, *_args) -> None:
    _enforce_hardware_safe_cycles(scene)


@bpy.app.handlers.persistent
def _on_render_post(scene: bpy.types.Scene, *_args) -> None:
    if scene and scene.render.engine == "CYCLES":
        bake.thermal_cooldown()


def _install_guards() -> None:
    _install_ops_guard()
    for hlist, fn in (
        (bpy.app.handlers.render_pre, _on_render_pre),
        (bpy.app.handlers.render_post, _on_render_post),
    ):
        if fn not in hlist:
            hlist.append(fn)


def main() -> int:
    if "--" not in sys.argv:
        print("[vforge-bake] ERROR: Missing target script after '--'.", file=sys.stderr, flush=True)
        return 2

    idx = sys.argv.index("--")
    script_argv = sys.argv[idx + 1 :]
    if not script_argv:
        print("[vforge-bake] ERROR: No target bake script provided.", file=sys.stderr, flush=True)
        return 2

    target_script = os.path.abspath(script_argv[0])
    if not os.path.isfile(target_script):
        print(f"[vforge-bake] ERROR: Target script not found: {target_script}", file=sys.stderr, flush=True)
        return 2

    sc = bpy.context.scene
    backend = bake.enable_cycles_gpu(sc, use_denoising=True)
    _install_guards()

    denoiser = getattr(sc.cycles, "denoiser", "N/A")
    denoise_gpu = getattr(sc.cycles, "denoising_use_gpu", False)
    print(
        f"[vforge-bake] Power-safe mode active: backend={backend} "
        f"(CPU hybrid OFF), denoiser={denoiser} (gpu={denoise_gpu}), "
        f"threads={bake._safe_thread_count()}, tile={bake._safe_tile_size()}px, "
        f"cooldown={bake._safe_cooldown_sec():.1f}s",
        flush=True,
    )

    script_dir = os.path.dirname(target_script)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    extra_args = script_argv[1:]
    old_argv = sys.argv[:]
    sys.argv = [target_script, "--", *extra_args] if extra_args else [target_script]
    try:
        runpy.run_path(target_script, run_name="__main__")
        return 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 1
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    raise SystemExit(main())
