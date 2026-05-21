#!/usr/bin/env python3
"""
Laffybot development launcher script.

Usage:
    uv run dev.py              # Start backend + web frontend
    uv run dev.py --tauri      # Start backend + Tauri desktop
    uv run dev.py --backend    # Start backend only
    uv run dev.py --frontend   # Start web frontend only (assumes backend running)
    uv run dev.py --help       # Show help
"""

from __future__ import annotations

import argparse
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_PORT = 8000
FRONTEND_PORT = 1420


def get_platform() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[Any]:
    full_env = None
    if env:
        full_env = dict(os.environ)
        full_env.update(env)

    if get_platform() == "windows":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            shell=True,
            creationflags=creationflags,
        )
    else:
        return subprocess.Popen(cmd, cwd=cwd, env=full_env)


def start_backend(project_root: Path) -> subprocess.Popen[Any]:
    print(f"[Backend] Starting on port {BACKEND_PORT}...")
    return run_command(
        ["uv", "run", "laffybot", "--config", str(project_root / "config.json")],
        cwd=project_root,
    )


def start_frontend_web(project_root: Path) -> subprocess.Popen[Any]:
    ui_dir = project_root / "ui"
    print(f"[Frontend] Starting Vite dev server on port {FRONTEND_PORT}...")
    return run_command(
        ["pnpm", "run", "dev"],
        cwd=ui_dir,
    )


def start_frontend_tauri(project_root: Path) -> subprocess.Popen[Any]:
    ui_dir = project_root / "ui"
    print("[Tauri] Starting Tauri dev mode...")
    return run_command(
        ["pnpm", "run", "tauri", "dev"],
        cwd=ui_dir,
    )


def terminate_process(proc: subprocess.Popen[Any]) -> None:
    if get_platform() == "windows":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGTERM)


def kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    if get_platform() == "windows":
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            proc.kill()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Laffybot development launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run dev.py              Start backend + web frontend
  uv run dev.py --tauri      Start backend + Tauri desktop
  uv run dev.py --backend    Start backend only
  uv run dev.py --frontend   Start web frontend only
""",
    )
    parser.add_argument(
        "--tauri",
        action="store_true",
        help="Start Tauri desktop instead of web frontend",
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
    processes: list[subprocess.Popen[Any]] = []

    if args.backend and args.frontend:
        print("Error: --backend and --frontend are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    def cleanup() -> None:
        print("\n[Shutdown] Stopping processes...")
        for proc in processes:
            if proc.poll() is None:
                terminate_process(proc)
        for proc in processes:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    kill_process_tree(proc)
        print("[Shutdown] Done.")

    def signal_handler(sig: int, frame: Any) -> None:
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if args.frontend:
            proc = start_frontend_web(project_root)
            processes.append(proc)
        elif args.backend:
            proc = start_backend(project_root)
            processes.append(proc)
        else:
            backend_proc = start_backend(project_root)
            processes.append(backend_proc)

            import time

            time.sleep(2)

            if backend_proc.poll() is not None:
                print("Error: Backend failed to start", file=sys.stderr)
                cleanup()
                sys.exit(1)

            if args.tauri:
                frontend_proc = start_frontend_tauri(project_root)
            else:
                frontend_proc = start_frontend_web(project_root)
            processes.append(frontend_proc)

        for proc in processes:
            proc.wait()

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
