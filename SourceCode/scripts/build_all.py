"""Unified build script for TaskGuard (Python backend + Electron frontend).

Usage (from SourceCode/ directory, with venv activated):
    python scripts/build_all.py

Or use the convenience wrapper (Windows):
    .\\build.cmd

Steps:
    1. Build Python backend with PyInstaller → dist/backend/taskguard-backend.exe
    2. Build Electron frontend with electron-builder → dist/electron/

Output:
    dist/electron/TaskGuard Setup X.Y.Z.exe    (NSIS installer)
    dist/electron/TaskGuard-Portable-X.Y.Z.exe (portable)

Relates-to: FR-4 Phase 4
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn


# ── Colours (Windows + Unix) ────────────────────────────────────────────────
class _C:
    OK = "\033[92m"
    WARN = "\033[93m"
    ERR = "\033[91m"
    INFO = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


# Enable ANSI colours on Windows
if sys.platform == "win32":
    import ctypes

    _kernel32 = ctypes.windll.kernel32
    _kernel32.SetConsoleMode(_kernel32.GetStdHandle(-11), 7)


def _p(label: str, text: str, colour: str = _C.INFO) -> None:
    """Print a styled log line."""
    print(f"  [{colour}{label}{_C.RESET}] {text}")


def _banner(text: str) -> None:
    """Print a section banner."""
    w = max(64, len(text) + 8)
    print()
    print(f"  {_C.BOLD}{'─' * w}{_C.RESET}")
    print(f"  {_C.BOLD}  {text}{_C.RESET}")
    print(f"  {_C.BOLD}{'─' * w}{_C.RESET}")


def _hr() -> None:
    print(f"  {_C.DIM}{'─' * 60}{_C.RESET}")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run(cmd: list[str], cwd: Path, *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command with optional output capture."""
    if capture:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return subprocess.run(cmd, cwd=cwd, text=True)


def _has_tool(name: str) -> bool:
    """Check if a CLI tool is available in PATH."""
    return shutil.which(name) is not None


def _read_pyproject_version(source_dir: Path) -> str:
    """Extract version from pyproject.toml."""
    path = source_dir / "pyproject.toml"
    if not path.exists():
        return "0.1.0"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("version ="):
            return line.split("=")[1].strip().strip('"')
    return "0.1.0"


def _sync_version_to_package_json(source_dir: Path, version: str) -> None:
    """Sync version from pyproject.toml to frontend/package.json."""
    pkg_path = source_dir / "frontend" / "package.json"
    if not pkg_path.exists():
        return
    data = json.loads(pkg_path.read_text(encoding="utf-8"))
    if data.get("version") != version:
        data["version"] = version
        pkg_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _p("INFO", f"Synced version {version} → frontend/package.json")


def _check_python_deps(source_dir: Path) -> bool:
    """Check that PyInstaller is installed in the active environment."""
    import importlib.util

    if importlib.util.find_spec("PyInstaller") is None:
        _p("WARN", "PyInstaller not found in active Python environment")
        _p("INFO", "Install: pip install pyinstaller")
        return False
    return True


def _check_node_deps(source_dir: Path) -> bool:
    """Check that frontend dependencies are installed."""
    frontend = source_dir / "frontend"
    if not (frontend / "node_modules").exists():
        _p("ERR", "frontend/node_modules not found")
        _p("INFO", "Run: cd frontend && npm install")
        return False
    if (
        not (frontend / "node_modules" / ".bin" / "electron-builder").exists()
        and not (frontend / "node_modules" / "electron-builder" / "package.json").exists()
    ):
        _p("ERR", "electron-builder not found in frontend/node_modules")
        _p("INFO", "Run: cd frontend && npm install -D electron-builder")
        return False
    return True


def _check_prerequisites(source_dir: Path) -> bool:
    """Run all prerequisite checks."""
    _banner("Prerequisite Check")
    ok = True

    # Python
    _p("CHECK", f"Python: {sys.executable}")
    if not _check_python_deps(source_dir):
        ok = False

    # Node.js
    node_cmd = "node"
    if not _has_tool(node_cmd):
        _p("ERR", "Node.js not found in PATH")
        _p("INFO", "Download: https://nodejs.org/")
        ok = False
    else:
        result = _run([node_cmd, "--version"], source_dir, capture=True)
        if result.returncode == 0:
            _p("OK", f"Node.js {result.stdout.strip()}")
        else:
            _p("ERR", "Node.js --version failed")
            ok = False

    # npm
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    if not _has_tool(npm_cmd):
        _p("ERR", "npm not found in PATH")
        ok = False
    else:
        result = _run([npm_cmd, "--version"], source_dir, capture=True)
        if result.returncode == 0:
            _p("OK", f"npm v{result.stdout.strip()}")
        else:
            _p("ERR", "npm --version failed")
            ok = False

    # frontend deps
    if not _check_node_deps(source_dir):
        ok = False

    return ok


# ── Build Steps ───────────────────────────────────────────────────────────────


def build_backend(source_dir: Path, version: str) -> int:
    """Step 1: Build Python backend executable."""
    _banner("Step 1/2 — Build Python Backend")
    start = time.monotonic()

    result = _run(
        [sys.executable, str(source_dir / "scripts" / "build_backend.py")],
        source_dir,
    )
    elapsed = time.monotonic() - start

    if result.returncode != 0:
        _p("ERR", f"PyInstaller failed ({elapsed:.1f}s)")
        return result.returncode

    # Verify output
    exe = source_dir / "dist" / "backend" / "taskguard-backend.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        _p("OK", f"taskguard-backend.exe ({size_mb:.1f} MB) — {elapsed:.1f}s")
    else:
        _p("WARN", "Expected output not found")

    return 0


def build_frontend(source_dir: Path, version: str) -> int:
    """Step 2: Build Electron frontend."""
    _banner("Step 2/2 — Build Electron Frontend")
    start = time.monotonic()

    frontend_dir = source_dir / "frontend"
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    # Verify backend artifacts
    backend_dir = source_dir / "dist" / "backend"
    if not backend_dir.exists():
        _p("ERR", f"Backend not found at {backend_dir}")
        _p("INFO", "Run backend build first")
        return 1

    result = _run([npm_cmd, "run", "build"], frontend_dir)
    elapsed = time.monotonic() - start

    if result.returncode != 0:
        _p("ERR", f"electron-builder failed ({elapsed:.1f}s)")
        return result.returncode

    _p("OK", f"Electron build completed — {elapsed:.1f}s")
    return 0


def print_summary(source_dir: Path, version: str, total_time: float) -> None:
    """Print build summary with output files."""
    _banner(f"Build Complete — {total_time:.1f}s Total")

    dist = source_dir / "dist"
    if not dist.exists():
        _p("WARN", "dist/ directory not found")
        return

    files: list[Path] = []
    for pattern in ("**/*.exe", "**/*.msi"):
        files.extend(dist.glob(pattern))

    if not files:
        _p("WARN", "No build artifacts found")
        return

    _p("INFO", f"Version: {_C.BOLD}{version}{_C.RESET}")
    _hr()
    for f in sorted(files):
        size_mb = f.stat().st_size / (1024 * 1024)
        rel = f.relative_to(dist)
        kind = (
            "Installer" if "Setup" in f.name else ("Portable" if "Portable" in f.name else "Other")
        )
        _p("OUT", f"{rel}  ({size_mb:.1f} MB)  [{kind}]")
    _hr()

    # Output directory reminder
    abs_dist = dist.resolve()
    _p("INFO", f"Output directory: {abs_dist}")


def main() -> NoReturn:
    source_dir = Path(__file__).parent.parent.resolve()
    version = _read_pyproject_version(source_dir)

    print()
    print(f"  {_C.BOLD}╔══════════════════════════════════════════════════════════════╗{_C.RESET}")
    print(
        f"  {_C.BOLD}║        TaskGuard Unified Build  v{version:<8}                  ║{_C.RESET}"
    )
    print(f"  {_C.BOLD}╚══════════════════════════════════════════════════════════════╝{_C.RESET}")
    print(f"  Source: {source_dir}")

    # Sync version
    _sync_version_to_package_json(source_dir, version)

    # Prerequisites
    if not _check_prerequisites(source_dir):
        _p("ERR", "Prerequisite check failed. Install missing dependencies first.")
        sys.exit(1)

    overall_start = time.monotonic()

    # Step 1: Backend
    rc = build_backend(source_dir, version)
    if rc != 0:
        sys.exit(rc)

    # Step 2: Frontend
    rc = build_frontend(source_dir, version)
    if rc != 0:
        sys.exit(rc)

    total = time.monotonic() - overall_start
    print_summary(source_dir, version, total)

    sys.exit(0)


if __name__ == "__main__":
    main()
