#!/usr/bin/env python3
"""Convert a raster image to SVG with the bundled wasm_vtracer runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError as exc:  # pragma: no cover - environment-specific
    raise SystemExit("Pillow is required. Run: python3 -m pip install -r scripts/requirements.txt") from exc

from validate_svg import audit

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def remove_white_background(image: Image.Image, threshold: int) -> Image.Image:
    pixels = bytearray(image.tobytes())
    for index in range(0, len(pixels), 4):
        red, green, blue = pixels[index], pixels[index + 1], pixels[index + 2]
        if min(red, green, blue) >= threshold and max(red, green, blue) - min(red, green, blue) <= 10:
            pixels[index + 3] = 0
    return Image.frombytes("RGBA", image.size, bytes(pixels))


def prepare_image(
    path: Path,
    max_dimension: int,
    remove_background: bool,
    threshold: int,
    edge_blur: float,
    palette_colors: int,
) -> Image.Image:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    longest = max(image.size)
    if longest > max_dimension:
        scale = max_dimension / longest
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    if edge_blur:
        alpha = image.getchannel("A")
        rgb = image.convert("RGB").filter(ImageFilter.GaussianBlur(edge_blur))
        image = rgb.convert("RGBA")
        image.putalpha(alpha)
    if palette_colors:
        alpha = image.getchannel("A")
        rgb = image.convert("RGB")
        quantized = rgb.quantize(
            colors=palette_colors,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        ).convert("RGBA")
        quantized.putalpha(alpha)
        image = quantized
    if remove_background:
        image = remove_white_background(image, threshold)
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("illustration", "lineart", "pixel", "photo"), default="illustration")
    parser.add_argument("--detail", type=int, choices=range(0, 101), default=82, metavar="0-100")
    parser.add_argument("--smoothing", type=int, choices=range(0, 101), default=55, metavar="0-100")
    parser.add_argument("--color-precision", type=int, choices=range(1, 9), default=6)
    parser.add_argument("--max-dimension", type=int, default=2048)
    parser.add_argument("--remove-background", action="store_true")
    parser.add_argument("--background-threshold", type=int, choices=range(200, 256), default=245)
    parser.add_argument("--edge-blur", type=float, default=0, help="pre-trace Gaussian edge cleanup radius")
    parser.add_argument("--palette-colors", type=int, default=0, help="pre-trace adaptive palette size; 0 disables")
    parser.add_argument("--force", action="store_true", help="replace an existing output")
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise SystemExit(f"Input image does not exist: {source}")
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise SystemExit("Input must be PNG, JPEG, or WebP.")
    if args.max_dimension < 16 or args.max_dimension > 8192:
        raise SystemExit("--max-dimension must be between 16 and 8192.")
    if not 0 <= args.edge_blur <= 3:
        raise SystemExit("--edge-blur must be between 0 and 3.")
    if args.palette_colors != 0 and not 4 <= args.palette_colors <= 256:
        raise SystemExit("--palette-colors must be 0 or between 4 and 256.")
    if output.exists() and not args.force:
        raise SystemExit(f"Output already exists: {output}. Allocate a new name or pass --force.")
    if shutil.which("node") is None:
        raise SystemExit("Node.js is required to run the bundled vectorizer.")

    script_root = Path(__file__).resolve().parent
    runtime = script_root / "vtracer_runtime.mjs"
    output.parent.mkdir(parents=True, exist_ok=True)
    image = prepare_image(
        source,
        args.max_dimension,
        args.remove_background,
        args.background_threshold,
        args.edge_blur,
        args.palette_colors,
    )

    with tempfile.TemporaryDirectory(prefix="img2svg-") as temporary:
        temp_root = Path(temporary)
        raw_path = temp_root / "input.rgba"
        config_path = temp_root / "config.json"
        staged_svg = temp_root / "output.svg"
        raw_path.write_bytes(image.tobytes())
        config_path.write_text(
            json.dumps(
                {
                    "mode": args.mode,
                    "detail": args.detail,
                    "smoothing": args.smoothing,
                    "colorPrecision": args.color_precision,
                }
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            ["node", str(runtime), str(raw_path), str(image.width), str(image.height), str(config_path), str(staged_svg)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown vectorizer error"
            raise SystemExit(f"Vectorization failed: {message}")
        report = audit(staged_svg)
        if report["status"] != "PASS":
            raise SystemExit("Vectorization produced an invalid SVG: " + "; ".join(report["errors"]))
        staged_svg.replace(output)

    print(
        json.dumps(
            {
                "ok": True,
                "input": str(source),
                "output": str(output),
                "mode": args.mode,
                "width": image.width,
                "height": image.height,
                "vector_elements": report["vector_elements"],
                "edge_blur": args.edge_blur,
                "palette_colors": args.palette_colors,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
