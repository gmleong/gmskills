#!/usr/bin/env python3
"""Create a smooth, seam-free flat-art trace with the bundled VTracer 1 WASM."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from validate_svg import audit

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clustering", choices=("color-cluster", "watershed"), default="watershed")
    parser.add_argument("--watershed-detail", type=int, choices=range(0, 256), default=192, metavar="0-255")
    parser.add_argument("--hierarchical", choices=("cutout", "stacked"), default="cutout")
    parser.add_argument("--simplify", type=float, default=1.5)
    parser.add_argument("--max-colors", type=int, choices=range(4, 257), default=64, metavar="4-256")
    parser.add_argument("--color-precision", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--optimize", type=int, choices=(0, 1, 2), default=1)
    parser.add_argument("--path-precision", type=int, choices=range(0, 7), default=3)
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise SystemExit("Input must be an existing PNG, JPEG, or WebP image.")
    if output.exists():
        raise SystemExit("Output already exists; allocate a new path.")
    if not 0 <= args.simplify <= 5:
        raise SystemExit("--simplify must be between 0 and 5 pixels.")
    if shutil.which("node") is None:
        raise SystemExit("Node.js is required to run the bundled vectorizer.")

    options = {
        "preset": "poster",
        "clustering": args.clustering,
        "watershedDetail": args.watershed_detail,
        "hierarchical": args.hierarchical,
        "mode": "spline",
        "simplify": args.simplify,
        "maxColors": args.max_colors,
        "colorPrecision": args.color_precision,
        "optimize": args.optimize,
        "pathPrecision": args.path_precision,
    }
    runtime = Path(__file__).resolve().parent / "vtracer_smooth_runtime.cjs"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="img2svg-smooth-") as temporary:
        staged_png = Path(temporary) / "source.png"
        staged_svg = Path(temporary) / "result.svg"
        with Image.open(source) as opened:
            ImageOps.exif_transpose(opened).convert("RGBA").save(staged_png)
        result = subprocess.run(
            ["node", str(runtime), str(staged_png), str(staged_svg), json.dumps(options)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or result.stdout.strip() or "VTracer 1 failed.")
        report = audit(staged_svg)
        if report["status"] != "PASS":
            raise SystemExit("Smooth trace failed validation: " + "; ".join(report["errors"]))
        staged_svg.replace(output)

    print(
        json.dumps(
            {"ok": True, "input": str(source), "output": str(output), "options": options, "vector_elements": report["vector_elements"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
