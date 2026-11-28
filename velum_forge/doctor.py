"""Deep environment diagnostics, multi-source Blender & Python discovery, and AI skill installer."""
from __future__ import annotations

import glob
import json
import os
import platform
import re
import shutil
import string
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import PLUGIN_SRC_DIR, REPO_ROOT

USER_CONFIG_DIR = Path.home() / ".velum-forge"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"


def load_user_config() -> dict[str, Any]:
    if USER_CONFIG_FILE.is_file():
        try:
            return json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
    return {}


def save_user_config(updates: dict[str, Any]) -> dict[str, Any]:
    cfg = load_user_config()
    cfg.update(updates)
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def _extract_exe_from_command_str(cmd_str: str) -> str | None:
    """Extract an executable path from a Windows shell command string like '"D:\\Blender\\blender.exe" "%1"'."""
    if not cmd_str:
        return None
    s = cmd_str.strip()
    m_quoted = re.match(r'^"([^"]+\.exe)"', s, re.IGNORECASE)
    if m_quoted:
        return m_quoted.group(1)
    m_bare = re.match(r"^([^\s]+?\.exe)\b", s, re.IGNORECASE)
    if m_bare:
        return m_bare.group(1)
    idx = s.lower().find("blender.exe")
    if idx != -1:
        cand = s[: idx + len("blender.exe")].strip(' "\'')
        return cand
    return None


def _windows_drives() -> list[str]:
    if platform.system() != "Windows":
        return []
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            drives.append(root)
    return drives


def _discover_steam_blender_paths() -> list[str]:
    """Locate Blender installed via Steam across all Steam library folders (`libraryfolders.vdf`)."""
    found: list[str] = []
    if platform.system() != "Windows":
        for p in (
            Path.home() / ".steam/steam/steamapps/common/Blender/blender",
            Path.home() / "Library/Application Support/Steam/steamapps/common/Blender/Blender.app/Contents/MacOS/Blender",
        ):
            if p.is_file():
                found.append(str(p))
        return found

    steam_roots: set[Path] = set()
    for pf_var in ("ProgramFiles(x86)", "ProgramFiles"):
        pf = os.environ.get(pf_var)
        if pf:
            sp = Path(pf) / "Steam"
            if sp.is_dir():
                steam_roots.add(sp)

    try:
        import winreg

        for hive, subkey, val_name in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    val, _ = winreg.QueryValueEx(k, val_name)
                    if val and Path(val).is_dir():
                        steam_roots.add(Path(val))
            except OSError:
                continue
    except ImportError:
        pass

    lib_dirs: set[Path] = set(steam_roots)
    for sr in steam_roots:
        vdf = sr / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            try:
                txt = vdf.read_text(encoding="utf-8", errors="ignore")
                for m in re.finditer(r'"path"\s+"([^"]+)"', txt, re.IGNORECASE):
                    raw_p = m.group(1).replace("\\\\", "\\")
                    if Path(raw_p).is_dir():
                        lib_dirs.add(Path(raw_p))
            except Exception:
                pass

    for drv in _windows_drives():
        for name in ("SteamLibrary", "Steam", r"Games\SteamLibrary"):
            p = Path(drv) / name
            if p.is_dir():
                lib_dirs.add(p)

    for lib in lib_dirs:
        exe = lib / "steamapps" / "common" / "Blender" / "blender.exe"
        if exe.is_file():
            found.append(str(exe))
    return found


def _discover_windows_registry_blender_paths() -> list[str]:
    """Search Windows Registry (App Paths, .blend ProgIds, Uninstall entries, and Shell MuiCache) for blender.exe."""
    found: list[str] = []
    if platform.system() != "Windows":
        return found
    try:
        import winreg
    except ImportError:
        return found

    # 1. App Paths
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for exe_name in ("blender.exe", "blender-launcher.exe"):
            try:
                with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}") as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    cand = _extract_exe_from_command_str(str(val))
                    if cand and os.path.isfile(cand):
                        found.append(cand)
            except OSError:
                continue

    # 2. .blend File Associations & ProgIds
    prog_ids = {"blendfile", "blend_auto_file", r"Applications\blender.exe"}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.blend\UserChoice") as k:
            pid, _ = winreg.QueryValueEx(k, "ProgId")
            if pid:
                prog_ids.add(str(pid))
    except OSError:
        pass
    for hive, base in ((winreg.HKEY_CLASSES_ROOT, ".blend"), (winreg.HKEY_CURRENT_USER, r"Software\Classes\.blend")):
        try:
            with winreg.OpenKey(hive, base) as k:
                pid, _ = winreg.QueryValueEx(k, "")
                if pid:
                    prog_ids.add(str(pid))
        except OSError:
            pass

    for pid in prog_ids:
        for hive, prefix in ((winreg.HKEY_CLASSES_ROOT, ""), (winreg.HKEY_CURRENT_USER, "Software\\Classes\\")):
            try:
                with winreg.OpenKey(hive, f"{prefix}{pid}\\shell\\open\\command") as k:
                    cmd_val, _ = winreg.QueryValueEx(k, "")
                    cand = _extract_exe_from_command_str(str(cmd_val))
                    if cand:
                        p_cand = Path(cand)
                        # If associated with blender-launcher.exe, prefer sibling blender.exe
                        sib = p_cand.parent / "blender.exe"
                        if sib.is_file():
                            found.append(str(sib))
                        elif p_cand.is_file():
                            found.append(str(p_cand))
            except OSError:
                continue

    # 3. Uninstall keys (MSI, Winget, Steam, InnoSetup, Scoop)
    uninstall_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, u_path in uninstall_roots:
        try:
            with winreg.OpenKey(hive, u_path) as uk:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(uk, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(uk, sub_name) as sk:
                            disp = ""
                            try:
                                disp = str(winreg.QueryValueEx(sk, "DisplayName")[0] or "")
                            except OSError:
                                pass
                            if "blender" not in disp.lower() and "blender" not in sub_name.lower():
                                continue
                            for field in ("InstallLocation", "DisplayIcon", "UninstallString"):
                                try:
                                    fval = str(winreg.QueryValueEx(sk, field)[0] or "").strip(' "\'')
                                except OSError:
                                    continue
                                if not fval:
                                    continue
                                fp = Path(fval.split(",")[0].strip(' "\''))
                                dir_cand = fp if fp.is_dir() else fp.parent
                                bexe = dir_cand / "blender.exe"
                                if bexe.is_file():
                                    found.append(str(bexe))
                    except OSError:
                        continue
        except OSError:
            continue

    # 4. Shell MuiCache (catches portable .zip extracts on ANY folder/drive ever launched by the user!)
    mui_keys = [
        r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
        r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store",
    ]
    for mk in mui_keys:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, mk) as k:
                j = 0
                while True:
                    try:
                        vname, _vdata, _vtype = winreg.EnumValue(k, j)
                        j += 1
                    except OSError:
                        break
                    vn_low = vname.lower()
                    if "blender.exe" in vn_low or "blender-launcher.exe" in vn_low:
                        idx = vn_low.find(".exe")
                        raw_exe = vname[: idx + 4].strip(' "\'')
                        p_exe = Path(raw_exe)
                        sib = p_exe.parent / "blender.exe"
                        if sib.is_file():
                            found.append(str(sib))
                        elif p_exe.is_file():
                            found.append(str(p_exe))
        except OSError:
            continue

    return found


def _discover_windows_filesystem_and_store_blender() -> list[str]:
    """Scan all drives, Blender Launcher, Scoop, Chocolatey, Start Menu shortcuts & MS Store Appx."""
    found: list[str] = []
    if platform.system() != "Windows":
        return found

    home = Path.home()
    local_app = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    prog_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))

    # Common user-space managers (Blender Launcher, Scoop, Chocolatey, Portable folders)
    glob_patterns = [
        str(local_app / "Programs" / "Blender Foundation" / "Blender*" / "blender.exe"),
        str(home / "Blender Launcher" / "**" / "blender.exe"),
        str(local_app / "Blender Launcher" / "**" / "blender.exe"),
        str(home / "scoop" / "apps" / "blender" / "*" / "blender.exe"),
        str(prog_data / "chocolatey" / "lib" / "blender*" / "**" / "blender.exe"),
        str(home / "Desktop" / "blender*" / "blender.exe"),
        str(home / "OneDrive" / "Desktop" / "blender*" / "blender.exe"),
        str(home / "Downloads" / "blender*" / "blender.exe"),
    ]
    for drv in _windows_drives():
        glob_patterns.extend(
            [
                os.path.join(drv, "Program Files", "Blender Foundation", "Blender*", "blender.exe"),
                os.path.join(drv, "Program Files (x86)", "Blender Foundation", "Blender*", "blender.exe"),
                os.path.join(drv, "Blender Foundation", "Blender*", "blender.exe"),
                os.path.join(drv, "Blender*", "blender.exe"),
                os.path.join(drv, "Blender*", "Blender*", "blender.exe"),
                os.path.join(drv, "Tools", "blender*", "blender.exe"),
                os.path.join(drv, "Apps", "blender*", "blender.exe"),
            ]
        )

    for pat in glob_patterns:
        try:
            for hit in glob.glob(pat, recursive=("**" in pat)):
                if os.path.isfile(hit):
                    found.append(hit)
        except Exception:
            continue

    # Microsoft Store (MSIX / AppxPackage)
    store_alias = local_app / "Microsoft" / "WindowsApps" / "blender.exe"
    if store_alias.exists():
        found.append(str(store_alias))
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-AppxPackage *Blender* | Select-Object -ExpandProperty InstallLocation)"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in (cp.stdout or "").splitlines():
            loc = line.strip()
            if loc and Path(loc).is_dir():
                for sub_rel in ("Blender/blender.exe", "blender.exe"):
                    cand = Path(loc) / sub_rel
                    if cand.is_file():
                        found.append(str(cand))
    except Exception:
        pass

    return found


def _parse_version_tuple(ver_str: str, fallback_path: str = "") -> tuple[int, int, int]:
    m = re.search(r"Blender\s+(\d+)\.(\d+)(?:\.(\d+))?", ver_str, re.IGNORECASE)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    mp = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", fallback_path)
    if mp:
        return (int(mp.group(1)), int(mp.group(2)), int(mp.group(3) or 0))
    return (0, 0, 0)


def _probe_blender_version(exe: str | None) -> str | None:
    if not exe:
        return None
    try:
        cp = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=8, check=False)
        if cp.returncode != 0:
            return None
        lines = [ln.strip() for ln in (cp.stdout or "").splitlines() if ln.strip()]
        if lines and "blender" in lines[0].lower():
            return lines[0]
    except Exception:
        return None
    return None


def find_all_blender_installs() -> list[dict[str, Any]]:
    """Discover all valid working Blender installations on the PC, sorted highest version first."""
    cfg = load_user_config()
    raw_candidates: list[str] = []

    # Priority 1: Explicit user override & env var
    if cfg.get("blender_exe"):
        raw_candidates.append(str(cfg["blender_exe"]))
    if os.environ.get("VELUM_BLENDER_EXE"):
        raw_candidates.append(str(os.environ["VELUM_BLENDER_EXE"]))

    # Priority 2: PATH
    which_b = shutil.which("blender")
    if which_b:
        raw_candidates.append(which_b)

    # Priority 3: Platform-specific deep scan
    if platform.system() == "Windows":
        raw_candidates.extend(_discover_windows_filesystem_and_store_blender())
        raw_candidates.extend(_discover_steam_blender_paths())
        raw_candidates.extend(_discover_windows_registry_blender_paths())
    elif platform.system() == "Darwin":
        for p in glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender") + glob.glob(str(Path.home() / "Applications/Blender*.app/Contents/MacOS/Blender")):
            raw_candidates.append(p)
        raw_candidates.extend(_discover_steam_blender_paths())
    else:
        for p in ("/snap/bin/blender", "/usr/bin/blender", "/usr/local/bin/blender", str(Path.home() / ".local/bin/blender")):
            if os.path.isfile(p):
                raw_candidates.append(p)
        for flatpak_b in glob.glob("/var/lib/flatpak/exports/bin/*blender*"):
            raw_candidates.append(flatpak_b)
        raw_candidates.extend(_discover_steam_blender_paths())

    # Deduplicate while preserving discovery order, then verify with `--version`
    seen: set[str] = set()
    verified: list[dict[str, Any]] = []
    user_pinned = os.path.normcase(os.path.abspath(cfg["blender_exe"])) if cfg.get("blender_exe") and os.path.exists(cfg["blender_exe"]) else None

    for c in raw_candidates:
        if not c:
            continue
        try:
            norm = os.path.normcase(os.path.abspath(c))
        except Exception:
            continue
        if norm in seen or not os.path.exists(c):
            continue
        seen.add(norm)

        ver_line = _probe_blender_version(c)
        if not ver_line:
            continue
        v_tup = _parse_version_tuple(ver_line, c)
        verified.append(
            {
                "exe": os.path.abspath(c),
                "version": ver_line,
                "version_tuple": v_tup,
                "pinned": (user_pinned == norm),
            }
        )

    # Sort pinned first, then highest version first (e.g. 5.3 > 5.2 > 4.2)
    verified.sort(key=lambda item: (1 if item["pinned"] else 0, item["version_tuple"]), reverse=True)
    return verified


def find_blender_exe() -> str | None:
    """Return the best working Blender executable on this machine (persisting discovery to config)."""
    installs = find_all_blender_installs()
    if not installs:
        return None
    best = installs[0]["exe"]
    cfg = load_user_config()
    if not cfg.get("blender_exe") or not os.path.exists(str(cfg.get("blender_exe"))):
        try:
            save_user_config({"blender_exe": best})
        except Exception:
            pass
    return best


def set_custom_blender_exe(exe_path: str) -> dict[str, Any]:
    """Validate and persist a user-selected `blender.exe` path."""
    p = Path(exe_path.strip(' "\''))
    if p.is_dir():
        for rel in ("blender.exe", "Contents/MacOS/Blender", "blender"):
            if (p / rel).is_file():
                p = p / rel
                break
    ver = _probe_blender_version(str(p))
    if not ver:
        return {"ok": False, "error": f"'{p}' is not a valid runnable Blender executable."}
    save_user_config({"blender_exe": str(p.resolve())})
    return {"ok": True, "blender_exe": str(p.resolve()), "version": ver}


# ---------------------------------------------------------------------------
# Deep Python & `uv` Discovery (Rejects Fake Windows Store Stub!)
# ---------------------------------------------------------------------------
def is_working_python(exe: str | Path | None) -> tuple[bool, str]:
    """Verify `exe` is a real Python 3.11+ interpreter (rejecting Microsoft Store WindowsApps stubs)."""
    if not exe:
        return False, ""
    s_exe = str(exe)
    if "windowsapps" in s_exe.lower() and not os.path.islink(s_exe):
        # Probe carefully — un-installed WindowsApps alias exits 9009 or prints nothing
        pass
    try:
        cp = subprocess.run(
            [s_exe, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')"],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        ver = (cp.stdout or "").strip()
        if cp.returncode == 0 and re.match(r"^\d+\.\d+\.\d+$", ver):
            maj, minor, _ = (int(x) for x in ver.split("."))
            if (maj, minor) >= (3, 11):
                return True, ver
    except Exception:
        pass
    return False, ""


def find_uv_exe() -> str | None:
    w = shutil.which("uv")
    if w:
        return w
    home = Path.home()
    local_app = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    candidates = [
        home / ".local" / "bin" / ("uv.exe" if platform.system() == "Windows" else "uv"),
        home / ".cargo" / "bin" / ("uv.exe" if platform.system() == "Windows" else "uv"),
    ]
    if platform.system() == "Windows":
        for hit in glob.glob(str(local_app / "Microsoft" / "WinGet" / "Packages" / "astral-sh.uv*" / "**" / "uv.exe"), recursive=True):
            candidates.append(Path(hit))
        candidates.append(home / "scoop" / "shims" / "uv.exe")
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def find_venv_python() -> str:
    if platform.system() == "Windows":
        cand = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        cand = REPO_ROOT / ".venv" / "bin" / "python"
    ok, _ = is_working_python(cand)
    if ok:
        return str(cand)

    cfg = load_user_config()
    if cfg.get("python_exe"):
        ok_c, _ = is_working_python(cfg["python_exe"])
        if ok_c:
            return str(cfg["python_exe"])

    ok_sys, _ = is_working_python(sys.executable)
    if ok_sys:
        return sys.executable

    # Scan non-PATH Windows Python locations (py.exe launcher, AppData\Local\Programs\Python, uv managed pythons, Registry)
    if platform.system() == "Windows":
        home = Path.home()
        local_app = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        roam_app = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        search_pats = [
            str(local_app / "Programs" / "Python" / "Python3*" / "python.exe"),
            r"C:\Program Files\Python3*\python.exe",
            str(roam_app / "uv" / "python" / "cpython-3.12*" / "python.exe"),
            str(local_app / "uv" / "python" / "cpython-3.12*" / "python.exe"),
            str(roam_app / "uv" / "python" / "cpython-3.*" / "python.exe"),
            str(home / "scoop" / "apps" / "python*" / "current" / "python.exe"),
            str(home / "miniconda3" / "python.exe"),
            str(home / "anaconda3" / "python.exe"),
        ]
        for pat in search_pats:
            for hit in sorted(glob.glob(pat), reverse=True):
                ok_h, _ = is_working_python(hit)
                if ok_h:
                    return hit
    return sys.executable


def _probe_cad_packages(py_exe: str) -> dict[str, bool]:
    code = (
        "import importlib.util, json; "
        "mods=['build123d','trimesh','pymeshlab','PIL','numpy']; "
        "print(json.dumps({m: importlib.util.find_spec(m) is not None for m in mods}))"
    )
    try:
        cp = subprocess.run([py_exe, "-c", code], capture_output=True, text=True, timeout=10, check=False)
        if cp.returncode == 0 and cp.stdout.strip():
            return json.loads(cp.stdout.strip().splitlines()[-1])
    except Exception:
        pass
    return {m: False for m in ("build123d", "trimesh", "pymeshlab", "PIL", "numpy")}


def get_design_output_dir() -> Path:
    env_d = os.environ.get("VELUM_DESIGN_OUTPUT_DIR")
    if env_d:
        return Path(env_d)
    home = Path.home()
    od = home / "OneDrive" / "Desktop"
    if od.is_dir():
        return od / "Design Model Output"
    return home / "Desktop" / "Design Model Output"


def run_doctor() -> dict[str, Any]:
    """Return comprehensive health report for Blender, CAD venv, GPU tools, and AI agent plugins."""
    all_blenders = find_all_blender_installs()
    blender_exe = all_blenders[0]["exe"] if all_blenders else None
    blender_ver = all_blenders[0]["version"] if all_blenders else None
    if blender_exe:
        cfg = load_user_config()
        if cfg.get("blender_exe") != blender_exe and not cfg.get("blender_exe"):
            save_user_config({"blender_exe": blender_exe})

    venv_py = find_venv_python()
    has_venv = (REPO_ROOT / ".venv").is_dir()
    cad_mods = _probe_cad_packages(venv_py)
    uv_exe = find_uv_exe()
    gh_exe = shutil.which("gh")

    home = Path.home()
    agy_plugin_dir = home / ".gemini" / "config" / "plugins" / "velum-forge"
    claude_skills_dir = home / ".claude" / "skills"
    src_skills_dir = PLUGIN_SRC_DIR / "skills"
    expected_skills = sorted(p.name for p in src_skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()) if src_skills_dir.is_dir() else [
        "velum-3d-workflow",
        "velum-architecture-environments",
        "velum-cad-brep",
        "velum-organic-species",
        "velum-pbr-bake-lods",
    ]
    agy_missing = [s for s in expected_skills if not (agy_plugin_dir / "skills" / s / "SKILL.md").is_file()]
    if not (agy_plugin_dir / "rules" / "AGENTS.md").is_file():
        agy_missing.append("rules/AGENTS.md")
    claude_missing = [s for s in expected_skills if not (claude_skills_dir / s / "SKILL.md").is_file()]
    claude_installed = len(claude_missing) == 0 and len(expected_skills) > 0
    agy_installed = (agy_plugin_dir / "plugin.json").is_file() and len(agy_missing) == 0
    dmo = get_design_output_dir()

    checks = [
        {
            "id": "blender",
            "label": "Blender 5.2+ LTS Engine",
            "ok": blender_exe is not None,
            "detail": (
                f"{blender_ver} ({blender_exe})"
                if blender_exe
                else "Not auto-detected — click 'Locate Blender.exe' above or install Blender 5.2 LTS+"
            ),
        },
        {
            "id": "venv",
            "label": "Velum Forge Python .venv",
            "ok": has_venv and all(cad_mods.values()),
            "detail": f"{venv_py} | modules: " + ", ".join(f"{k}={'OK' if v else 'MISSING'}" for k, v in cad_mods.items()),
        },
        {
            "id": "uv",
            "label": "uv Standalone Python Bootstrapper",
            "ok": uv_exe is not None,
            "detail": uv_exe or "Auto-installed by install.ps1 when needed",
        },
        {
            "id": "antigravity",
            "label": "Antigravity Plugin (velum-forge)",
            "ok": agy_installed,
            "detail": (
                f"{len(expected_skills)}/{len(expected_skills)} skills synced ({agy_plugin_dir})"
                if agy_installed
                else (f"Missing in {agy_plugin_dir}: {', '.join(agy_missing)} — run 'vforge install-ai'" if (agy_plugin_dir / "plugin.json").is_file() else "Not installed yet (click 'Sync AI Skills')")
            ),
        },
        {
            "id": "claude",
            "label": "Claude Code CLI Skills (~/.claude/skills)",
            "ok": claude_installed,
            "detail": (
                f"{len(expected_skills)}/{len(expected_skills)} skills synced ({claude_skills_dir})"
                if claude_installed
                else (f"Missing in {claude_skills_dir}: {', '.join(claude_missing)} — run 'vforge install-ai'" if claude_skills_dir.is_dir() else "Not installed yet (click 'Sync AI Skills')")
            ),
        },
        {
            "id": "output_dir",
            "label": "Design Model Output Showcase Folder",
            "ok": dmo.is_dir(),
            "detail": str(dmo),
        },
    ]

    all_core_ok = bool(blender_exe) and all(cad_mods.values())
    return {
        "ok": all_core_ok,
        "repo_root": str(REPO_ROOT),
        "config_file": str(USER_CONFIG_FILE),
        "blender_exe": blender_exe,
        "blender_version": blender_ver,
        "blender_installs": [{"exe": b["exe"], "version": b["version"], "pinned": b["pinned"]} for b in all_blenders],
        "venv_python": venv_py,
        "uv_exe": uv_exe,
        "gh_exe": gh_exe,
        "cad_modules": cad_mods,
        "antigravity_plugin_installed": agy_installed,
        "claude_skills_installed": claude_installed,
        "design_output_dir": str(dmo),
        "checks": checks,
    }


def install_ai_integrations(
    *,
    antigravity: bool = True,
    claude_code: bool = True,
    workspace_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Install Velum Forge plugin, skills & rules into Antigravity, Claude Code, and optional workspace."""
    home = Path.home()
    installed: dict[str, Any] = {}

    dmo = get_design_output_dir()
    dmo.mkdir(parents=True, exist_ok=True)
    installed["design_output_dir"] = str(dmo)

    if antigravity:
        dst_plugin = home / ".gemini" / "config" / "plugins" / "velum-forge"
        if dst_plugin.exists():
            shutil.rmtree(dst_plugin)
        dst_plugin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(PLUGIN_SRC_DIR, dst_plugin)
        (dst_plugin / ".velum_forge_root").write_text(str(REPO_ROOT), encoding="utf-8")
        installed["antigravity_plugin"] = str(dst_plugin)

    if claude_code:
        claude_skills = home / ".claude" / "skills"
        claude_skills.mkdir(parents=True, exist_ok=True)
        copied_skills: list[str] = []
        src_skills = PLUGIN_SRC_DIR / "skills"
        for sk_dir in sorted(src_skills.iterdir()):
            if sk_dir.is_dir() and (sk_dir / "SKILL.md").is_file():
                dst_sk = claude_skills / sk_dir.name
                if dst_sk.exists():
                    shutil.rmtree(dst_sk)
                shutil.copytree(sk_dir, dst_sk)
                copied_skills.append(sk_dir.name)
        installed["claude_skills"] = copied_skills

    if workspace_dir:
        ws = Path(workspace_dir).resolve()
        ws_agents = ws / ".agents" / "skills"
        ws_agents.mkdir(parents=True, exist_ok=True)
        for sk_dir in sorted((PLUGIN_SRC_DIR / "skills").iterdir()):
            if sk_dir.is_dir():
                dst_sk = ws_agents / sk_dir.name
                if dst_sk.exists():
                    shutil.rmtree(dst_sk)
                shutil.copytree(sk_dir, dst_sk)
        cursor_rules = ws / ".cursor" / "rules"
        cursor_rules.mkdir(parents=True, exist_ok=True)
        rules_body = (PLUGIN_SRC_DIR / "rules" / "AGENTS.md").read_text(encoding="utf-8")
        mdc = (
            "---\n"
            "description: Velum Forge 3D CAD, Blender 5.2+ PBR Baking, QA & LOD Rules\n"
            "globs: **/*.py, **/*.blend, **/*.glb, **/*.step\n"
            "alwaysApply: false\n"
            "---\n\n"
            + rules_body
        )
        (cursor_rules / "velum-forge.mdc").write_text(mdc, encoding="utf-8")
        installed["workspace_configured"] = str(ws)

    return installed
