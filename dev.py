#!/usr/bin/env python3
"""
Laffybot development launcher script.

Usage:
    uv run dev.py              # Start backend + web frontend
    uv run dev.py --backend    # Start backend only
    uv run dev.py --frontend   # Start web frontend only (assumes backend running)
    uv run dev.py --help       # Show help
"""

from __future__ import annotations

import argparse
import atexit
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil

BACKEND_PORT = 8000
FRONTEND_PORT = 1420

_processes: list[psutil.Popen] = []


def get_platform() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> psutil.Popen:
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)

    is_windows = get_platform() == "windows"

    if is_windows:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return psutil.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            shell=True,
            creationflags=creationflags,
        )
    else:
        return psutil.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            start_new_session=True,
        )


def start_backend(project_root: Path) -> psutil.Popen:
    print(f"[Backend] Starting on port {BACKEND_PORT}...")
    return run_command(
        ["uv", "run", "laffybot", "--config", str(project_root / "config.json")],
        cwd=project_root,
    )


def start_frontend_web(project_root: Path) -> psutil.Popen:
    ui_dir = project_root / "ui"
    print(f"[Frontend] Starting Vite dev server on port {FRONTEND_PORT}...")
    return run_command(
        ["pnpm", "run", "dev"],
        cwd=ui_dir,
    )


def kill_process_tree(proc: psutil.Popen) -> None:
    try:
        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return

    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass

    try:
        proc.terminate()
    except psutil.NoSuchProcess:
        pass

    gone, alive = psutil.wait_procs(children + [parent], timeout=5)

    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass


def cleanup() -> None:
    print("\n[Shutdown] Stopping all processes...")
    for proc in _processes:
        if proc.is_running():
            kill_process_tree(proc)
    print("[Shutdown] Done.")


def signal_handler(sig: int, frame: Any) -> None:
    cleanup()
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Laffybot development launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run dev.py              Start backend + web frontend
  uv run dev.py --backend    Start backend only
  uv run dev.py --frontend   Start web frontend only
""",
    )
    parser.add_argument(
        "--backend",
        action="store_true",
        help="Start backend only (no frontend)",
    )
    parser.add_argument(
        "--frontend",
        action="store_true",
        help="Start web frontend only (backend must be running separately)",
    )

    args = parser.parse_args()

    project_root = Path(__file__).parent.resolve()

    if args.backend and args.frontend:
        print("Error: --backend and --frontend are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if args.frontend:
            proc = start_frontend_web(project_root)
            _processes.append(proc)
        elif args.backend:
            proc = start_backend(project_root)
            _processes.append(proc)
        else:
            backend_proc = start_backend(project_root)
            _processes.append(backend_proc)

            time.sleep(2)

            if not backend_proc.is_running():
                print("Error: Backend failed to start", file=sys.stderr)
                cleanup()
                sys.exit(1)

            frontend_proc = start_frontend_web(project_root)
            _processes.append(frontend_proc)

        for proc in _processes:
            proc.wait()

    except KeyboardInterrupt:
        pass
    except Exception:
        raise


if __name__ == "__main__":
    main()
