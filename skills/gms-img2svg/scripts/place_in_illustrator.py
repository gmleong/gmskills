#!/usr/bin/env python3
"""Append one SVG group to the active Illustrator document without launching it."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from validate_svg import audit

PLACEMENTS = {"center", "top-left", "top-right", "bottom-left", "bottom-right"}


def jsx_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_jsx(svg: Path, name: str, placement: str, max_width: float, max_height: float) -> str:
    return f"""#target illustrator
(function () {{
  if (app.documents.length < 1) throw new Error("Open the target Illustrator document first.");
  var document = app.activeDocument;
  var source = new File({jsx_string(str(svg))});
  if (!source.exists) throw new Error("SVG file not found.");
  var created = null;
  try {{
    created = document.groupItems.createFromFile(source);
    created.name = {jsx_string(name)};
    var artboard = document.artboards[document.artboards.getActiveArtboardIndex()].artboardRect;
    var bounds = created.visibleBounds;
    var width = bounds[2] - bounds[0];
    var height = bounds[1] - bounds[3];
    if (width <= 0 || height <= 0) throw new Error("Imported SVG has empty bounds.");
    var boardWidth = artboard[2] - artboard[0];
    var boardHeight = artboard[1] - artboard[3];
    var scale = Math.min((boardWidth * {max_width}) / width, (boardHeight * {max_height}) / height);
    if (!isFinite(scale) || scale <= 0) throw new Error("Could not calculate placement scale.");
    created.resize(scale * 100, scale * 100, true, true, true, true, scale * 100, Transformation.CENTER);
    bounds = created.visibleBounds;
    width = bounds[2] - bounds[0];
    height = bounds[1] - bounds[3];
    var marginX = boardWidth * (1 - {max_width}) / 2;
    var marginY = boardHeight * (1 - {max_height}) / 2;
    var targetLeft = artboard[0] + (boardWidth - width) / 2;
    var targetTop = artboard[1] - (boardHeight - height) / 2;
    var placement = {jsx_string(placement)};
    if (placement === "top-left") {{ targetLeft = artboard[0] + marginX; targetTop = artboard[1] - marginY; }}
    else if (placement === "top-right") {{ targetLeft = artboard[2] - marginX - width; targetTop = artboard[1] - marginY; }}
    else if (placement === "bottom-left") {{ targetLeft = artboard[0] + marginX; targetTop = artboard[3] + marginY + height; }}
    else if (placement === "bottom-right") {{ targetLeft = artboard[2] - marginX - width; targetTop = artboard[3] + marginY + height; }}
    created.translate(targetLeft - bounds[0], targetTop - bounds[1]);
    return "OK|name=" + created.name + "|placement=" + placement;
  }} catch (error) {{
    if (created !== null) {{ try {{ created.remove(); }} catch (cleanupError) {{}} }}
    throw error;
  }}
}})();
"""


def illustrator_running_macos() -> bool:
    result = subprocess.run(["pgrep", "-f", "Adobe Illustrator"], capture_output=True, check=False)
    return result.returncode == 0


def run_macos(script_path: Path) -> subprocess.CompletedProcess[str]:
    apple_script = """set jsxFile to POSIX file (system attribute \"IMG2SVG_JSX\")
tell application id \"com.adobe.illustrator\"
  if (count documents) is 0 then error \"Open the target Illustrator document first.\"
  do javascript file jsxFile
end tell
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
    parser.add_argument("svg", type=Path)
    parser.add_argument("--placement", choices=sorted(PLACEMENTS), default="center")
    parser.add_argument("--max-width-fraction", type=float, default=0.72)
    parser.add_argument("--max-height-fraction", type=float, default=0.78)
    parser.add_argument("--name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.svg.resolve()
    report = audit(source)
    if report["status"] != "PASS":
        raise SystemExit("SVG validation failed: " + "; ".join(report["errors"]))
    if not 0.05 <= args.max_width_fraction <= 1 or not 0.05 <= args.max_height_fraction <= 1:
        raise SystemExit("Artboard fractions must be between 0.05 and 1.")
    name = args.name or f"img2svg-{source.stem}"
    preview = {
        "ok": True,
        "dry_run": args.dry_run,
        "svg": str(source),
        "name": name,
        "placement": args.placement,
        "vector_elements": report["vector_elements"],
    }
    if args.dry_run:
        print(json.dumps(preview, ensure_ascii=False))
        return 0

    system = platform.system()
    if system == "Darwin" and not illustrator_running_macos():
        raise SystemExit("Illustrator is not running. Open Illustrator and the target document first.")
    if system not in {"Darwin", "Windows"}:
        raise SystemExit("Illustrator insertion is supported on macOS and Windows only.")

    jsx = build_jsx(source, name, args.placement, args.max_width_fraction, args.max_height_fraction)
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", encoding="utf-8", delete=False) as handle:
        handle.write(jsx)
        script_path = Path(handle.name)
    try:
        result = run_macos(script_path) if system == "Darwin" else run_windows(script_path)
    finally:
        script_path.unlink(missing_ok=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown Illustrator error"
        raise SystemExit(f"Illustrator insertion failed: {message}")
    preview["dry_run"] = False
    preview["result"] = result.stdout.strip()
    print(json.dumps(preview, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
