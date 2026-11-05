#!/usr/bin/env python3
"""Render an SVG and produce repeatable visual-difference evidence."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path.parser import parse_path
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat

from validate_svg import VECTOR_TAGS, audit as audit_svg, local_name


DOMAIN_FLOORS = {
    "scientific": {"multiscale_similarity": 0.80, "edge_f1": 0.68, "foreground_iou": 0.72},
    "cell": {"multiscale_similarity": 0.72, "edge_f1": 0.58, "foreground_iou": 0.62},
    "cartoon": {"multiscale_similarity": 0.76, "edge_f1": 0.62, "foreground_iou": 0.66},
    "mixed": {"multiscale_similarity": 0.68, "edge_f1": 0.52, "foreground_iou": 0.58},
}


def flat_data(image: Image.Image):
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter else image.getdata()


def flatten(image: Image.Image, background: str = "white") -> Image.Image:
    rgba = image.convert("RGBA")
    return Image.alpha_composite(Image.new("RGBA", rgba.size, background), rgba).convert("RGB")


def render_rgba(svg_path: Path, width: int, height: int, renderer: str = "cairosvg") -> Image.Image:
    if renderer == "resvg":
        try:
            import resvg_py
        except ImportError as exc:
            raise RuntimeError("Cross-rendering requires the optional resvg-py package.") from exc
        png = resvg_py.svg_to_bytes(svg_path=str(svg_path), width=width, height=height)
    elif renderer == "cairosvg":
        import cairosvg
        png = cairosvg.svg2png(url=str(svg_path), output_width=width, output_height=height)
    else:
        raise ValueError(f"Unknown renderer: {renderer}")
    return Image.open(BytesIO(png)).convert("RGBA")


def render_svg(svg_path: Path, width: int, height: int) -> Image.Image:
    return flatten(render_rgba(svg_path, width, height))


def mean_error(first: Image.Image, second: Image.Image) -> float:
    means = ImageStat.Stat(ImageChops.difference(first, second)).mean
    return sum(means) / len(means)


def svg_complexity(path: Path) -> dict:
    elements = list(ET.parse(path).getroot().iter())
    segments = points = 0
    for element in elements:
        if local_name(element.tag) == "path":
            pen = RecordingPen()
            parse_path(element.get("d", ""), pen)
            segments += sum(op not in {"moveTo", "closePath", "endPath"} for op, _ in pen.value)
            points += sum(len(args) for _, args in pen.value)
    return {
        "bytes": path.stat().st_size,
        "vector_elements": sum(local_name(e.tag) in VECTOR_TAGS for e in elements),
        "path_elements": sum(local_name(e.tag) == "path" for e in elements),
        "path_segments": segments,
        "path_coordinate_pairs": points,
    }


def pixel_similarity(first: Image.Image, second: Image.Image) -> float:
    difference = ImageChops.difference(first.convert("RGB"), second.convert("RGB"))
    mean = sum(ImageStat.Stat(difference).mean) / 3
    return max(0.0, 1 - mean / 255)


def binary_edges(image: Image.Image) -> Image.Image:
    sample = ImageOps.grayscale(image).filter(ImageFilter.GaussianBlur(0.6)).filter(ImageFilter.FIND_EDGES)
    return sample.point(lambda value: 255 if value >= 36 else 0)


def tolerant_edge_f1(first: Image.Image, second: Image.Image, radius: int = 3) -> float:
    first_data = first.tobytes()
    second_data = second.tobytes()
    first_dilated = first.filter(ImageFilter.MaxFilter(radius * 2 + 1)).tobytes()
    second_dilated = second.filter(ImageFilter.MaxFilter(radius * 2 + 1)).tobytes()
    first_count = sum(1 for value in first_data if value)
    second_count = sum(1 for value in second_data if value)
    if first_count == 0 and second_count == 0:
        return 1.0
    recall = sum(1 for edge, nearby in zip(first_data, second_dilated) if edge and nearby) / max(1, first_count)
    precision = sum(1 for edge, nearby in zip(second_data, first_dilated) if edge and nearby) / max(1, second_count)
    return 0.0 if recall + precision == 0 else 2 * recall * precision / (recall + precision)


def binary_foreground(image: Image.Image) -> bytes:
    rgb = image.convert("RGB")
    width, height = rgb.size
    corners = [rgb.getpixel((0, 0)), rgb.getpixel((width - 1, 0)), rgb.getpixel((0, height - 1)), rgb.getpixel((width - 1, height - 1))]
    background = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    return bytes(255 if max(abs(pixel[channel] - background[channel]) for channel in range(3)) > 24 else 0 for pixel in flat_data(rgb))


def iou(first: bytes, second: bytes) -> float:
    intersection = sum(1 for left, right in zip(first, second) if left and right)
    union = sum(1 for left, right in zip(first, second) if left or right)
    return 1.0 if union == 0 else intersection / union


def audit(source_path: Path, svg_path: Path, output_dir: Path, domain: str, *, cross_render: bool = False) -> dict:
    validation = audit_svg(svg_path)
    if validation["status"] != "PASS":
        raise ValueError("Cannot render invalid SVG: " + "; ".join(validation["errors"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as opened:
        source_rgba = ImageOps.exif_transpose(opened).convert("RGBA")
    source = flatten(source_rgba)
    rendered_rgba = render_rgba(svg_path, *source.size)
    rendered = flatten(rendered_rgba)
    rendered_path = output_dir / "rendered.png"
    rendered.save(rendered_path)

    comparison = Image.new("RGB", (source.width * 2, source.height), "white")
    comparison.paste(source, (0, 0))
    comparison.paste(rendered, (source.width, 0))
    comparison_path = output_dir / "source-vs-svg.png"
    comparison.save(comparison_path)

    raw_difference = ImageChops.difference(source, rendered)
    diff_path = output_dir / "difference.png"
    ImageEnhance.Contrast(raw_difference).enhance(2.5).save(diff_path)

    regions = []
    for y in range(0, source.height, 96):
        for x in range(0, source.width, 96):
            box = (x, y, min(x + 96, source.width), min(y + 96, source.height))
            regions.append((sum(ImageStat.Stat(raw_difference.crop(box)).mean) / 3, box))
    regions.sort(reverse=True)
    regions = regions[:3]
    details = Image.new("RGB", (768, 408 * len(regions)), "white")
    labels = ImageDraw.Draw(details)
    for i, (error, box) in enumerate(regions):
        labels.text((4, i * 408 + 4), f"Source | SVG    crop={box}    MAE={error:.4f}    4x", fill="black")
        for column, image in enumerate((source, rendered)):
            crop = image.crop(box)
            details.paste(crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.NEAREST), (column * 384, i * 408 + 24))
    details_path = output_dir / "detail-comparison.png"
    details.save(details_path)

    analysis_size = min(768, max(source.size))
    ratio = analysis_size / max(source.size)
    sampled_size = (max(1, round(source.width * ratio)), max(1, round(source.height * ratio)))
    source_sample = source.resize(sampled_size, Image.Resampling.LANCZOS)
    rendered_sample = rendered.resize(sampled_size, Image.Resampling.LANCZOS)
    scales = (64, 128, 256)
    similarities = []
    for scale in scales:
        ratio = scale / max(source.size)
        size = (max(1, round(source.width * ratio)), max(1, round(source.height * ratio)))
        similarities.append(pixel_similarity(source.resize(size, Image.Resampling.LANCZOS), rendered.resize(size, Image.Resampling.LANCZOS)))

    metrics = {
        "native_mae": round(mean_error(source, rendered), 6),
        "native_pixel_similarity": round(pixel_similarity(source, rendered), 6),
        "alpha_mae": round(mean_error(source_rgba.getchannel("A"), rendered_rgba.getchannel("A")), 6),
        "black_background_mae": round(mean_error(flatten(source_rgba, "black"), flatten(rendered_rgba, "black")), 6),
        "native_edge_f1_1px": round(tolerant_edge_f1(binary_edges(source), binary_edges(rendered), radius=1), 6),
        "pixel_similarity": round(pixel_similarity(source_sample, rendered_sample), 4),
        "multiscale_similarity": round(sum(similarities) / len(similarities), 4),
        "edge_f1": round(tolerant_edge_f1(binary_edges(source_sample), binary_edges(rendered_sample)), 4),
        "foreground_iou": round(iou(binary_foreground(source_sample), binary_foreground(rendered_sample)), 4),
    }
    floors = DOMAIN_FLOORS[domain]
    below = [name for name, minimum in floors.items() if metrics[name] < minimum]
    report = {
        "status": "PASS" if not below else "REVIEW",
        "source": str(source_path.resolve()),
        "svg": str(svg_path.resolve()),
        "domain": domain,
        "metrics": metrics,
        "measurement": {
            "renderer": "cairosvg",
            "native_size": list(source.size),
            "sampled_size": list(sampled_size),
            "sampled_edge_tolerance_px": 3,
            "background": "white",
            "mae_units": "channel levels, 0..255 (lower is better)",
        },
        "complexity": svg_complexity(svg_path),
        "advisory_floors": floors,
        "below_advisory_floor": below,
        "artifacts": {
            "rendered": str(rendered_path),
            "comparison": str(comparison_path),
            "difference": str(diff_path),
            "details": str(details_path),
        },
        "detail_regions": [{"box": list(box), "native_mae": round(error, 6)} for error, box in regions],
        "limitations": [
            "These metrics measure appearance and silhouette, not semantic correctness.",
            "A REVIEW result requires visual inspection; it is not an automatic rejection.",
        ],
    }
    if cross_render:
        other = render_rgba(svg_path, *source.size, renderer="resvg")
        other_path = output_dir / "rendered-resvg.png"
        other.save(other_path)
        report["cross_render"] = {
            "renderer": "resvg",
            "native_mae": round(mean_error(source, flatten(other)), 6),
            "alpha_mae": round(mean_error(source_rgba.getchannel("A"), other.getchannel("A")), 6),
            "black_background_mae": round(mean_error(flatten(source_rgba, "black"), flatten(other, "black")), 6),
            "renderer_difference_mae": round(mean_error(rendered, flatten(other)), 6),
        }
        report["artifacts"]["resvg"] = str(other_path)
    if metrics["alpha_mae"] > 1:
        report["status"] = "REVIEW"
        report["limitations"].append("Alpha differs by more than 1 channel level on average; inspect transparency.")
    report_path = output_dir / "visual-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--domain", choices=sorted(DOMAIN_FLOORS), required=True)
    parser.add_argument("--cross-render", action="store_true", help="also measure with optional resvg-py")
    args = parser.parse_args()
    report = audit(args.source.resolve(), args.svg.resolve(), args.output_dir.resolve(), args.domain, cross_render=args.cross_render)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
