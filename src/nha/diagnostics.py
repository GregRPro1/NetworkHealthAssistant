# src/nha/diagnostics.py
import os, platform, shutil, subprocess, sys

def is_windows() -> bool:
    return platform.system().lower().startswith("win")

def is_admin() -> bool:
    if not is_windows():
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        import ctypes  # type: ignore
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except Exception:
        return False

def which_nmap() -> str | None:
    return shutil.which("nmap")

def npcap_installed() -> bool:
    if not is_windows():
        return True  # not applicable
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Npcap") as _:
            return True
    except Exception:
        return False

def nmap_version() -> str | None:
    exe = which_nmap()
    if not exe:
        return None
    try:
        out = subprocess.check_output([exe, "--version"], text=True, timeout=10)
        return out.splitlines()[0].strip()
    except Exception:
        return None

def run_env_diagnostics() -> dict:
    """Return a dict of environment checks & recommendations."""
    win = is_windows()
    admin = is_admin()
    nmap_path = which_nmap()
    npcap = npcap_installed()
    nmap_ver = nmap_version()

    ok = True
    problems = []
    advice = []

    if win and not admin:
        ok = False
        problems.append("App is not running with Administrator privileges.")
        advice.append("Right-click VS Code (or PowerShell) → Run as administrator, then run the app again.")

    if win and not npcap:
        ok = False
        problems.append("Npcap driver not detected.")
        advice.append("Install Npcap from https://nmap.org/npcap/ (enable 'WinPcap API-compatible mode').")

    if not nmap_path:
        ok = False
        problems.append("nmap is not installed or not on PATH.")
        advice.append("Install nmap from https://nmap.org/download.html#windows and check 'Add Nmap to PATH'.")

    if nmap_path and not nmap_ver:
        ok = False
        problems.append("nmap is installed but failed to run '--version'.")
        advice.append("Ensure nmap is accessible from your terminal. Try closing/reopening VS Code as Admin.")

    return {
        "os": platform.platform(),
        "windows": win,
        "admin": admin,
        "npcap": npcap,
        "nmap_path": nmap_path,
        "nmap_version": nmap_ver,
        "ok": ok,
        "problems": problems,
        "advice": advice,
    }
