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
import shutil
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
    # --follow-imports handles regular transitive deps automatically.
    # --include-package is only needed for packages that Nuitka's
    # static analysis might miss:
    #   - The two application packages (workspace layout)
    #   - pydantic (heavy metaclass/dynamic model usage)
    force_packages = [
        "laffybot",
        "laffybot_agent_runtime",
        "pydantic",
    ]
    force_packages.extend(args.extra_packages)

    # ── Build the Nuitka command ─────────────────────────────
    cmd = [
        sys.executable or "python3",
        "-m", "nuitka",
        f"--output-dir={target_dir}",
        "--output-filename=laffybot-backend",
        # standalone (onedir) mode — produces a directory
        "--mode=standalone",
        # follow all imports
        "--follow-imports",
        # enable plugins for compatibility
        "--enable-plugin=pylint-warnings",
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

    # ── Verify and restructure output ──────────────────────────
    # Nuitka with --mode=standalone creates a {entry_module}.dist/ directory
    # named after the entry point module (e.g. __main__.dist).
    # We need to rename it to the expected sidecar directory format.
    dist_dir_name = f"{output_name}"
    build_dir_name = f"{output_name}.build"
    nuitka_dist = os.path.join(target_dir, "__main__.dist")
    nuitka_build = os.path.join(target_dir, "__main__.build")
    target_dist = os.path.join(target_dir, dist_dir_name)
    target_build = os.path.join(target_dir, build_dir_name)

    final_exe_name = "laffybot-backend.exe" if target_triple.startswith("x86_64-pc-windows") else "laffybot-backend"
    final_exe_path = os.path.join(target_dist, final_exe_name)

    if os.path.exists(nuitka_dist):
        # Remove any previous output
        if os.path.exists(target_dist):
            shutil.rmtree(target_dist)
        os.rename(nuitka_dist, target_dist)
        # Also rename the build dir for cleanliness
        if os.path.exists(nuitka_build):
            if os.path.exists(target_build):
                shutil.rmtree(target_build)
            os.rename(nuitka_build, target_build)

        if os.path.exists(final_exe_path):
            size_mb = os.path.getsize(final_exe_path) / (1024 * 1024)
            print(f"\n✅ Build complete: {final_exe_path} ({size_mb:.1f} MB)")
            print(f"   Sidecar name:  {output_name}")
            print(f"   Tauri sidecar path: ui/src-tauri/binaries/{output_name}/")
        else:
            print(f"\n⚠️  Output directory renamed but executable not found:")
            print(f"   Expected: {final_exe_path}")
            print(f"   Check {target_dist} for the actual output.")
            sys.exit(1)
    else:
        # Fallback: check if Nuitka already created the expected path
        if os.path.exists(final_exe_path):
            size_mb = os.path.getsize(final_exe_path) / (1024 * 1024)
            print(f"\n✅ Build complete: {final_exe_path} ({size_mb:.1f} MB)")
        else:
            print(f"\n⚠️  Build finished but executable not found at expected path:")
            print(f"   {final_exe_path}")
            print(f"   Check {target_dir} for the actual output.")
            sys.exit(1)


if __name__ == "__main__":
    main()
