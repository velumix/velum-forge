"""Hardware-safe Cycles GPU/CPU bake runner & cross-process sequential GPU lock (`velum_forge.bake_guard`).

Prevents simultaneous GPU + all-core CPU power spikes and overlapping GPU bakes by:
- Routing headless bake scripts through `engine/blender/safe_bake_runner.py` so every
  `bpy.ops.object.bake` and `bpy.ops.render.render` call enforces GPU-only devices, GPU denoising,
  thread caps, tiling, and thermal cooldowns—even in custom or legacy bake scripts.
- Enforcing safe CPU thread caps (`-t` + `VELUM_BLENDER_THREADS` + `OMP`/`TBB`/`OPENBLAS`/`MKL`).
- Exporting safe Cycles environment defaults (`VELUM_CYCLES_DEVICE`, `VELUM_CYCLES_TILE_SIZE`, `VELUM_BAKE_COOLDOWN`).
- Running headless Blender with `--factory-startup` by default (opt-in `--user-addons`) and Windows
  `BELOW_NORMAL_PRIORITY_CLASS` so background batch jobs stay thermally smooth and responsive.
- Serializing concurrent GPU bakes via a crash-safe, stale-PID-recovering lock file (`~/.velum-forge/gpu_bake.lock`, opt-out via `--no-lock`).
"""
from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterator

from . import BLENDER_ENGINE_DIR

LOCK_PATH = Path.home() / ".velum-forge" / "gpu_bake.lock"
SAFE_BAKE_RUNNER = BLENDER_ENGINE_DIR / "safe_bake_runner.py"


def windows_creationflags() -> int:
    """Return `BELOW_NORMAL_PRIORITY_CLASS` on Windows (0 elsewhere) for smoother batch scheduling."""
    if platform.system() == "Windows":
        return getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000)
    return 0


def default_safe_threads() -> int:
    """Return a conservative CPU thread budget (capped at 8) to prevent all-core AVX2 power spikes."""
    env_val = os.environ.get("VELUM_BLENDER_THREADS", "").strip()
    if env_val.isdigit() and int(env_val) > 0:
        return int(env_val)
    cpus = os.cpu_count() or 8
    return min(8, max(2, cpus // 2))


def build_safe_blender_bake_cmd(
    blender_exe: str,
    script_path: str,
    *,
    threads: int | None = None,
    user_addons: bool = False,
    extra_script_args: list[str] | None = None,
    use_runner: bool = True,
) -> list[str]:
    """Construct a hardware-safe headless Blender command routed through `safe_bake_runner.py`."""
    t_count = max(1, int(threads if threads is not None else default_safe_threads()))
    cmd = [blender_exe, "-b"]
    if not user_addons:
        cmd.append("--factory-startup")
    abs_script = os.path.abspath(script_path)
    if use_runner and SAFE_BAKE_RUNNER.is_file():
        cmd.extend(["-t", str(t_count), "--python-exit-code", "1", "-P", str(SAFE_BAKE_RUNNER), "--", abs_script])
        if extra_script_args:
            cmd.extend(extra_script_args)
    else:
        cmd.extend(["-t", str(t_count), "--python-exit-code", "1", "-P", abs_script])
        if extra_script_args:
            cmd.append("--")
            cmd.extend(extra_script_args)
    return cmd


def build_safe_cycles_env(
    *,
    threads: int | None = None,
    device: str = "auto",
    cooldown: float = 1.0,
    tile_size: int = 512,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return environment dictionary carrying safe Cycles GPU/CPU guardrails into Blender."""
    env = dict(base_env if base_env is not None else os.environ)
    t_count = max(1, int(threads if threads is not None else default_safe_threads()))
    env["VELUM_BLENDER_THREADS"] = str(t_count)
    env["VELUM_CYCLES_DEVICE"] = str(device or "auto").strip().lower()
    env["VELUM_BAKE_COOLDOWN"] = str(max(0.0, float(cooldown)))
    env["VELUM_CYCLES_TILE_SIZE"] = str(max(64, int(tile_size)))
    # Cap OpenMP/TBB/BLAS worker pools used by OpenImageDenoise, mesh ops & NumPy
    env["OMP_NUM_THREADS"] = str(t_count)
    env["TBB_NUM_THREADS"] = str(t_count)
    env["OPENBLAS_NUM_THREADS"] = str(t_count)
    env["MKL_NUM_THREADS"] = str(t_count)
    return env


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            import ctypes

            SYNCHRONIZE = 0x00100000
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == 259  # STILL_ACTIVE
                return True
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _try_clear_stale_lock(lock_file: Path) -> bool:
    try:
        raw = json.loads(lock_file.read_text(encoding="utf-8"))
        pid = int(raw.get("pid", 0))
        if pid > 0 and not _pid_is_alive(pid):
            lock_file.unlink(missing_ok=True)
            return True
    except Exception:
        try:
            # If lock file is unreadable and older than 10 seconds, clear it
            if lock_file.exists() and (time.time() - lock_file.stat().st_mtime) > 10.0:
                lock_file.unlink(missing_ok=True)
                return True
        except OSError:
            pass
    return False


@contextlib.contextmanager
def gpu_bake_lock(
    *,
    enabled: bool = True,
    lock_file: Path | None = None,
    label: str = "bake",
    poll_interval: float = 0.5,
    log_fn: Callable[[str], None] | None = None,
) -> Iterator[None]:
    """Acquire a cross-process sequential GPU bake lock so two GPU bakes never overlap."""
    if not enabled:
        yield
        return

    lf = lock_file or LOCK_PATH
    lf.parent.mkdir(parents=True, exist_ok=True)
    waited = False
    fd = None

    while True:
        try:
            fd = os.open(str(lf), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = json.dumps({"pid": os.getpid(), "label": label, "started_at": time.time()}).encode("utf-8")
            os.write(fd, payload)
            try:
                os.fsync(fd)
            except OSError:
                pass
            os.close(fd)
            fd = None
            break
        except FileExistsError:
            if _try_clear_stale_lock(lf):
                continue
            if not waited:
                waited = True
                if log_fn:
                    log_fn(f"[Velum Forge] Another GPU bake is active ({lf}); waiting sequentially...")
            time.sleep(poll_interval)

    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            # Only remove if we own it
            if lf.exists():
                raw = json.loads(lf.read_text(encoding="utf-8"))
                if int(raw.get("pid", -1)) == os.getpid():
                    lf.unlink(missing_ok=True)
        except Exception:
            lf.unlink(missing_ok=True)
