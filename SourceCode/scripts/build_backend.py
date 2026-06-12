"""Build the TaskGuard Python backend as a single executable using PyInstaller.

Usage (from SourceCode/ directory, with venv activated):
    python scripts/build_backend.py

Output:
    ../dist/backend/taskguard-backend.exe

Relates-to: FR-4 Phase 4
"""

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    source_dir = Path(__file__).parent.parent.resolve()
    root_dir = source_dir.parent
    build_dir = source_dir / "build" / "pyinstaller"
    dist_dir = root_dir / "dist" / "backend"

    # Clean previous builds
    # dist_dir may contain runtime data/ (locked by a running backend)
    # Also kill any running taskguard-backend.exe before PyInstaller tries to overwrite it
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/IM", "taskguard-backend.exe"],
            capture_output=True,
        )
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if dist_dir.exists():
        shutil.rmtree(dist_dir, ignore_errors=True)

    build_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Path to the entry script
    entry_script = source_dir / "taskguard" / "api" / "server.py"

    # Collect hidden imports that PyInstaller may miss
    hidden_imports = [
        "taskguard",
        "taskguard.agent",
        "taskguard.api.server",
        "taskguard.api.routes",
        "taskguard.api.websocket",
        "taskguard.api.events",
        "taskguard.collectors.base",
        "taskguard.collectors.file_collector",
        "taskguard.collectors.process_collector",
        "taskguard.storage.metrics_store",
        "taskguard.storage.task_store",
        "taskguard.models.alert",
        "taskguard.models.snapshot",
        "taskguard.models.task",
        "taskguard.models.errors",
        "taskguard.tools",
        "taskguard.tools.watch",
        "taskguard.tools.query",
        "taskguard.tools.collect_all",
        "taskguard.tools.cleanup",
        "taskguard.tools.exec_bash",
        "taskguard.tools.find_process",
        "taskguard.config_loader",
        "taskguard.crash.dumper",
        "taskguard.crash.models",
        "aiohttp",
        "aiohttp.web",
        "aiosqlite",
        "psutil",
        "yaml",
        "anthropic",
        "httpx",
        "typer",
    ]

    # FR-3/5 modules (optional but better to include)
    optional_modules = [
        "taskguard.analyzers.pipeline",
        "taskguard.analyzers.regex_extractor",
        "taskguard.alerters.engine",
        "taskguard.alerters.rules",
        "taskguard.llm.factory",
        "taskguard.llm.claude_provider",
        "taskguard.interaction.intent_parser",
    ]
    hidden_imports.extend(optional_modules)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=taskguard-backend",
        "--onefile",
        "--console",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir / 'work'}",
        f"--specpath={build_dir}",
        "--clean",
        "--noconfirm",
    ]

    # Add hidden imports
    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])

    cmd.append(str(entry_script))

    print(f"[Build] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=source_dir)

    if result.returncode != 0:
        print("[Build] PyInstaller failed")
        return result.returncode

    # Verify output
    exe_path = dist_dir / "taskguard-backend.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"[Build] Success: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"[Build] Warning: Expected output not found at {exe_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
