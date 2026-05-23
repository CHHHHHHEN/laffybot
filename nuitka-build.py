#!/usr/bin/env python3
"""Nuitka compilation script for Laffybot backend.

Builds the Python backend into a standalone executable directory
suitable for bundling as a Tauri sidecar.

Usage:
    python nuitka-build.py                           # auto-detect target
    python nuitka-build.py --target-dir ./dist        # custom output dir
    python nuitka-build.py --target-triple x86_64-unknown-linux-gnu

Output:
    laffybot-backend-{target_triple}/
    ├── laffybot-backend(.exe)       # main executable
    ├── laffybot-backend.dist/       # compiled Python modules
    └── ...                          # shared libraries (.so/.dll/.dylib)

The output directory follows Tauri sidecar naming convention:
  {name}-{target_triple}/
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys


TARGET_TRIPLES = {
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Windows", "ARM64"): "aarch64-pc-windows-msvc",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
}


def detect_target_triple() -> str:
    system = platform.system()
    machine = platform.machine()
    triple = TARGET_TRIPLES.get((system, machine))
    if triple is None:
        print(
            f"Error: Unsupported platform: {system} {machine}",
            file=sys.stderr,
        )
        sys.exit(1)
    return triple


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Laffybot backend with Nuitka"
    )
    parser.add_argument(
        "--target-dir",
        default=None,
        help="Output directory for the compiled binary (default: cwd)",
    )
    parser.add_argument(
        "--target-triple",
        default=None,
        help=(
            "Target triple for sidecar naming. "
            "Auto-detected from host if omitted."
        ),
    )
    parser.add_argument(
        "--include-package",
        action="append",
        default=[],
        dest="extra_packages",
        help="Additional packages to force-include",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress Nuitka output except errors",
    )
    args = parser.parse_args()

    target_triple = args.target_triple or detect_target_triple()
    output_name = f"laffybot-backend-{target_triple}"
    target_dir = args.target_dir or os.getcwd()
    output_dir = os.path.join(target_dir, output_name)

    # ── Project root (two levels up from this script) ────────
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = script_dir

    # ── Packages that must be force-included ──────────────────
    # These are imported dynamically or via lazy imports and
    # Nuitka's auto-follow might miss them.
    force_packages = [
        "laffybot",
        "laffybot_agent_runtime",
        "pydantic",
        "pydantic_settings",
        "jinja2",
        "jinja2.ext",
        "openai",
        "httpx",
        "httpx_sse",
        "aiosqlite",
        "cryptography",
        "loguru",
        "uvicorn",
        "fastapi",
        "json_repair",
        "anyio",
        "sniffio",
        "h11",
        "httpcore",
    ]
    force_packages.extend(args.extra_packages)

    # ── Build the Nuitka command ─────────────────────────────
    cmd = [
        sys.executable or "python3",
        "-m", "nuitka",
        f"--output-dir={target_dir}",
        f"--output-filename={output_name}",
        # standalone (onedir) mode — produces a directory
        "--mode=standalone",
        # follow all imports
        "--follow-imports",
        # enable plugins for compatibility
        "--enable-plugin=pylint-warnings",
        "--enable-plugin=multiprocessing",
        # disable console window on Windows
        "--disable-console",
        # Auto download Walker
        "--assume-yes-for-downloads",
    ]

    for pkg in force_packages:
        cmd.append(f"--include-package={pkg}")

    # The entry point
    entry_point = os.path.join(project_root, "laffybot", "__main__.py")
    cmd.append(entry_point)

    # ── Print build info ─────────────────────────────────────
    print(f"🔨 Laffybot Backend — Nuitka Build")
    print(f"   Target triple:  {target_triple}")
    print(f"   Output dir:     {output_dir}")
    print(f"   Entry point:    {entry_point}")
    print(f"   Force packages: {len(force_packages)}")
    print(f"   Python:         {sys.version}")
    print()

    # ── Run Nuitka ───────────────────────────────────────────
    env = os.environ.copy()

    if args.quiet:
        cmd.append("--quiet")

    print(f"   Running: {' '.join(cmd)}")
    print()

    result = subprocess.run(
        cmd,
        cwd=project_root,
        env=env,
    )

    if result.returncode != 0:
        print(f"\n❌ Nuitka build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    # ── Verify output ────────────────────────────────────────
    exe_name = "laffybot-backend.exe" if target_triple.startswith("x86_64-pc-windows") else "laffybot-backend"
    exe_path = os.path.join(output_dir, exe_name)

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n✅ Build complete: {exe_path} ({size_mb:.1f} MB)")
        print(f"   Sidecar name:  {output_name}")
        print(f"   Copy to:       ui/src-tauri/binaries/{output_name}/")
    else:
        print(f"\n⚠️  Build finished but executable not found at expected path:")
        print(f"   {exe_path}")
        print(f"   Check {output_dir} for the actual output.")
        sys.exit(1)


if __name__ == "__main__":
    main()
