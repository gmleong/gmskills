#!/usr/bin/env python3
"""Replay an immutable geometry cache into the open Illustrator document."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

PLACEMENTS = {"center", "top-left", "top-right", "bottom-left", "bottom-right"}
SCHEMA = "img2svg-geometry-1.0"


def load_and_validate(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read geometry cache: {exc}") from exc
    if payload.get("schema") != SCHEMA:
        raise SystemExit(f"Unsupported geometry cache schema: {payload.get('schema')!r}")
    atoms = payload.get("atoms")
    batches = payload.get("batches")
    viewbox = payload.get("viewBox")
    if not isinstance(atoms, list) or not atoms:
        raise SystemExit("Geometry cache has no atoms.")
    if not isinstance(viewbox, list) or len(viewbox) != 4 or viewbox[2] <= 0 or viewbox[3] <= 0:
        raise SystemExit("Geometry cache has an invalid viewBox.")
    if not isinstance(batches, list) or not batches:
        raise SystemExit("Geometry cache has no batches.")
    cursor = 0
    names: set[str] = set()
    for index, batch in enumerate(batches):
        if batch.get("start") != cursor or not isinstance(batch.get("end"), int):
            raise SystemExit(f"Batch {index + 1} does not form a contiguous range.")
        size = batch["end"] - batch["start"]
        if size <= 0 or size > 50 or (size < 20 and batch["end"] != len(atoms)):
            raise SystemExit(f"Batch {index + 1} must contain 20-50 atoms, except the final remainder.")
        if batch.get("name") in names:
            raise SystemExit(f"Duplicate batch name: {batch.get('name')}")
        names.add(batch.get("name"))
        cursor = batch["end"]
    if cursor != len(atoms):
        raise SystemExit("Batch ranges do not cover every atom exactly once.")
    return payload


def illustrator_running() -> bool:
    if platform.system() == "Darwin":
        return subprocess.run(["pgrep", "-f", "Adobe Illustrator"], capture_output=True, check=False).returncode == 0
    if platform.system() == "Windows":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not powershell:
            return False
        command = "if (Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -match 'Illustrator'}) { exit 0 } else { exit 1 }"
        return subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, check=False).returncode == 0
    return False


def run_macos(script_path: Path) -> subprocess.CompletedProcess[str]:
    apple_script = """set jsxFile to POSIX file (system attribute \"IMG2SVG_JSX\")
with timeout of 600 seconds
  tell application id \"com.adobe.illustrator\"
    if (count documents) is 0 then error \"Open the target Illustrator document first.\"
    do javascript file jsxFile
  end tell
end timeout
"""
    environment = os.environ.copy()
    environment["IMG2SVG_JSX"] = str(script_path)
    return subprocess.run(["osascript", "-e", apple_script], env=environment, capture_output=True, text=True, check=False)


def run_windows(script_path: Path) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise SystemExit("PowerShell is required for Illustrator automation on Windows.")
    bridge = Path(__file__).resolve().parent / "run_illustrator_windows.ps1"
    return subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(bridge), "-ScriptPath", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    parser.add_argument("--output-ai", type=Path, required=True)
    parser.add_argument("--output-png", type=Path, required=True)
    parser.add_argument("--placement", choices=sorted(PLACEMENTS), default="center")
    parser.add_argument("--max-width-fraction", type=float, default=0.72)
    parser.add_argument("--max-height-fraction", type=float, default=0.78)
    parser.add_argument("--compatibility-probed", action="store_true")
    parser.add_argument(
        "--live-delay-ms",
        type=int,
        default=0,
        help="Redraw Illustrator after every atom and pause this many milliseconds (0 disables live playback).",
    )
    parser.add_argument(
        "--two-pass-live",
        action="store_true",
        help="Create all geometry as wireframes first, then apply final paint to the same native objects.",
    )
    parser.add_argument("--wireframe-delay-ms", type=int, default=120)
    parser.add_argument("--paint-delay-ms", type=int, default=80)
    parser.add_argument("--wireframe-stroke-width", type=float, default=0.5)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cache_path = args.cache.resolve()
    cache = load_and_validate(cache_path)
    if not 0.05 <= args.max_width_fraction <= 1 or not 0.05 <= args.max_height_fraction <= 1:
        raise SystemExit("Artboard fractions must be between 0.05 and 1.")
    if not 0 <= args.live_delay_ms <= 5000:
        raise SystemExit("--live-delay-ms must be between 0 and 5000.")
    if not 0 <= args.wireframe_delay_ms <= 5000 or not 0 <= args.paint_delay_ms <= 5000:
        raise SystemExit("Two-pass playback delays must be between 0 and 5000 milliseconds.")
    if not 0.1 <= args.wireframe_stroke_width <= 5:
        raise SystemExit("--wireframe-stroke-width must be between 0.1 and 5 points.")
    output_ai = args.output_ai.resolve()
    output_png = args.output_png.resolve()
    if output_ai.suffix.lower() != ".ai" or output_png.suffix.lower() != ".png":
        raise SystemExit("Outputs must use .ai and .png extensions.")
    if output_ai == output_png:
        raise SystemExit("AI and PNG outputs must use different paths.")
    if (output_ai.exists() or output_png.exists()) and not args.resume:
        raise SystemExit("An output already exists. Allocate new paths or pass --resume for the same job.")

    preview = {
        "ok": True,
        "dry_run": args.dry_run,
        "cache": str(cache_path),
        "job_id": cache.get("jobId"),
        "atoms": len(cache["atoms"]),
        "batches": len(cache["batches"]),
        "output_ai": str(output_ai),
        "output_png": str(output_png),
        "placement": args.placement,
        "resume": args.resume,
        "compatibility_probed": args.compatibility_probed,
        "live_delay_ms": args.live_delay_ms,
        "two_pass_live": args.two_pass_live,
        "wireframe_delay_ms": args.wireframe_delay_ms,
        "paint_delay_ms": args.paint_delay_ms,
        "wireframe_stroke_width": args.wireframe_stroke_width,
    }
    if args.dry_run:
        print(json.dumps(preview, ensure_ascii=False))
        return 0

    system = platform.system()
    if system not in {"Darwin", "Windows"}:
        raise SystemExit("Illustrator playback is supported on macOS and Windows only.")
    if not illustrator_running():
        raise SystemExit("Illustrator is not running. Open Illustrator and the target document first.")
    output_ai.parent.mkdir(parents=True, exist_ok=True)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "cachePath": str(cache_path),
        "outputAI": str(output_ai),
        "outputPNG": str(output_png),
        "placement": args.placement,
        "maxWidthFraction": args.max_width_fraction,
        "maxHeightFraction": args.max_height_fraction,
        "compatibilityProbed": args.compatibility_probed,
        "liveDelayMs": args.live_delay_ms,
        "twoPassLive": args.two_pass_live,
        "wireframeDelayMs": args.wireframe_delay_ms,
        "paintDelayMs": args.paint_delay_ms,
        "wireframeStrokeWidth": args.wireframe_stroke_width,
        "resume": args.resume,
    }
    runtime = (Path(__file__).resolve().parent / "illustrator_cached_runtime.jsx").read_text(encoding="utf-8")
    wrapper = "var IMG2SVG_CONFIG = " + json.dumps(config, ensure_ascii=False) + ";\n" + runtime
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", encoding="utf-8", delete=False) as handle:
        handle.write(wrapper)
        script_path = Path(handle.name)
    try:
        result = run_macos(script_path) if system == "Darwin" else run_windows(script_path)
    finally:
        script_path.unlink(missing_ok=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown Illustrator bridge error"
        raise SystemExit(f"Illustrator playback bridge failed: {message}")
    response = result.stdout.strip()
    if not response.startswith("OK|"):
        raise SystemExit(f"Illustrator playback failed: {response or 'no response'}")
    preview["dry_run"] = False
    preview["result"] = response
    print(json.dumps(preview, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
