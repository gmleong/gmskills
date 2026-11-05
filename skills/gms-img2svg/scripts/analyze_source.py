#!/usr/bin/env python3
"""Build deterministic visual evidence for semantic reconstruction.

This script proposes regions; it deliberately does not assign biological or
illustrative meaning. Semantic labels remain the responsibility of the visual
reasoning pass described by the skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


DOMAINS = ("auto", "scientific", "cell", "cartoon", "mixed")


def flat_data(image: Image.Image):
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter else image.getdata()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def saturation(rgb: tuple[int, int, int]) -> float:
    highest = max(rgb)
    lowest = min(rgb)
    return 0.0 if highest == 0 else (highest - lowest) / highest


def connected_regions(indexed: Image.Image, source_size: tuple[int, int], min_area_fraction: float) -> list[dict]:
    width, height = indexed.size
    source_width, source_height = source_size
    pixels = list(flat_data(indexed))
    palette = indexed.getpalette() or []
    visited = bytearray(width * height)
    minimum_area = max(12, round(width * height * min_area_fraction))
    regions: list[dict] = []

    for seed in range(width * height):
        if visited[seed]:
            continue
        color_index = pixels[seed]
        stack = [seed]
        visited[seed] = 1
        area = 0
        sum_x = 0
        sum_y = 0
        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        perimeter = 0
        border_touching = False
        while stack:
            current = stack.pop()
            y, x = divmod(current, width)
            area += 1
            sum_x += x
            sum_y += y
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                border_touching = True
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    perimeter += 1
                    continue
                neighbor = ny * width + nx
                if pixels[neighbor] != color_index:
                    perimeter += 1
                elif not visited[neighbor]:
                    visited[neighbor] = 1
                    stack.append(neighbor)

        if area < minimum_area:
            continue
        scale_x = source_width / width
        scale_y = source_height / height
        red, green, blue = palette[color_index * 3 : color_index * 3 + 3]
        compactness = 0.0 if perimeter == 0 else min(1.0, 4 * math.pi * area / (perimeter * perimeter))
        regions.append(
            {
                "candidate_id": "",
                "bbox": [
                    round(min_x * scale_x, 2),
                    round(min_y * scale_y, 2),
                    round((max_x - min_x + 1) * scale_x, 2),
                    round((max_y - min_y + 1) * scale_y, 2),
                ],
                "centroid": [round((sum_x / area + 0.5) * scale_x, 2), round((sum_y / area + 0.5) * scale_y, 2)],
                "area_fraction": round(area / (width * height), 6),
                "representative_color": f"#{red:02x}{green:02x}{blue:02x}",
                "border_touching": border_touching,
                "compactness": round(compactness, 4),
            }
        )

    regions.sort(key=lambda item: item["area_fraction"], reverse=True)
    for index, region in enumerate(regions, 1):
        region["candidate_id"] = f"R{index:03d}"
    for region in regions:
        x, y, width_value, height_value = region["bbox"]
        right = x + width_value
        bottom = y + height_value
        containers = []
        for candidate in regions:
            if candidate is region or candidate["area_fraction"] <= region["area_fraction"]:
                continue
            cx, cy, candidate_width, candidate_height = candidate["bbox"]
            if cx <= x and cy <= y and cx + candidate_width >= right and cy + candidate_height >= bottom:
                containers.append(candidate)
        containers.sort(key=lambda item: item["area_fraction"])
        region["container_candidates"] = [item["candidate_id"] for item in containers[:3]]
    return regions


def repeated_region_families(regions: list[dict]) -> list[dict]:
    buckets: dict[tuple, list[str]] = {}
    for region in regions:
        if region["border_touching"] or region["area_fraction"] > 0.12:
            continue
        color = region["representative_color"]
        rgb = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
        key = (
            tuple(channel // 48 for channel in rgb),
            round(math.log10(max(region["area_fraction"], 1e-6)) * 2),
            round(region["compactness"] * 4),
        )
        buckets.setdefault(key, []).append(region["candidate_id"])
    families = [members for members in buckets.values() if len(members) >= 2]
    families.sort(key=lambda members: (-len(members), members[0]))
    return [
        {
            "family_id": f"F{index:03d}",
            "candidate_ids": members,
            "count": len(members),
            "basis": "similar quantized color, area scale, and compactness; needs visual confirmation",
        }
        for index, members in enumerate(families[:50], 1)
    ]


def foreground_ratio(image: Image.Image) -> float:
    rgb = image.convert("RGB")
    width, height = rgb.size
    corners = [rgb.getpixel((0, 0)), rgb.getpixel((width - 1, 0)), rgb.getpixel((0, height - 1)), rgb.getpixel((width - 1, height - 1))]
    background = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    foreground = 0
    for pixel in flat_data(rgb):
        if max(abs(pixel[channel] - background[channel]) for channel in range(3)) > 24:
            foreground += 1
    return foreground / (width * height)


def domain_hypotheses(white_ratio: float, edge_density: float, mean_saturation: float, palette_entropy: float) -> list[dict]:
    scores = {
        "scientific": 0.25 + 0.45 * white_ratio + 0.15 * min(1.0, edge_density * 5) + 0.15 * (1 - mean_saturation),
        "cell": 0.25 + 0.30 * (1 - white_ratio) + 0.25 * mean_saturation + 0.20 * min(1.0, palette_entropy / 4),
        "cartoon": 0.25 + 0.30 * mean_saturation + 0.25 * min(1.0, edge_density * 5) + 0.20 * (1 - min(1.0, palette_entropy / 5)),
    }
    total = sum(scores.values()) or 1
    return [
        {"domain": name, "score": round(score / total, 4)}
        for name, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


def analyze(source: Path, output_dir: Path, domain: str, max_dimension: int, palette_colors: int, min_area_fraction: float, max_regions: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    original = ImageOps.exif_transpose(Image.open(source)).convert("RGBA")
    source_size = original.size
    preview = original.copy()
    preview.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    preview_path = output_dir / "source-preview.png"
    preview.save(preview_path)

    # Hidden RGB in transparent pixels is not evidence of visible objects.
    rgb = Image.alpha_composite(Image.new("RGBA", preview.size, "white"), preview).convert("RGB")
    quantized = rgb.quantize(colors=palette_colors, method=Image.Quantize.MEDIANCUT)
    palette_map_path = output_dir / "palette-map.png"
    quantized.convert("RGB").save(palette_map_path)

    grayscale = ImageOps.grayscale(rgb)
    edge = ImageOps.autocontrast(grayscale.filter(ImageFilter.FIND_EDGES))
    edge_path = output_dir / "edge-map.png"
    edge.save(edge_path)

    edge_histogram = edge.histogram()
    edge_density = sum(edge_histogram[40:]) / (preview.width * preview.height)
    palette_counts = Counter(flat_data(quantized))
    total = preview.width * preview.height
    palette_entropy = -sum((count / total) * math.log2(count / total) for count in palette_counts.values() if count)
    sampled = list(flat_data(rgb.resize((min(128, rgb.width), min(128, rgb.height)), Image.Resampling.BILINEAR)))
    mean_saturation = sum(saturation(pixel) for pixel in sampled) / max(1, len(sampled))
    white_ratio = sum(1 for pixel in sampled if min(pixel) >= 238) / max(1, len(sampled))

    all_regions = connected_regions(quantized, source_size, min_area_fraction)
    regions = all_regions[:max_regions]
    overlay = rgb.copy()
    drawing = ImageDraw.Draw(overlay)
    scale_x = preview.width / source_size[0]
    scale_y = preview.height / source_size[1]
    for region in regions[:50]:
        x, y, width, height = region["bbox"]
        box = (x * scale_x, y * scale_y, (x + width) * scale_x, (y + height) * scale_y)
        color = "#e11d48" if region["border_touching"] else "#2563eb"
        drawing.rectangle(box, outline=color, width=2)
        drawing.text((box[0] + 3, box[1] + 2), region["candidate_id"], fill=color, stroke_width=2, stroke_fill="white")
    overlay_path = output_dir / "region-overlay.png"
    overlay.save(overlay_path)

    enhanced_edge = ImageEnhance.Contrast(edge).enhance(1.5)
    evidence_sheet = Image.new("RGB", (preview.width * 2, preview.height * 2), "white")
    evidence_sheet.paste(rgb, (0, 0))
    evidence_sheet.paste(quantized.convert("RGB"), (preview.width, 0))
    evidence_sheet.paste(Image.merge("RGB", (enhanced_edge, enhanced_edge, enhanced_edge)), (0, preview.height))
    evidence_sheet.paste(overlay, (preview.width, preview.height))
    evidence_sheet_path = output_dir / "evidence-sheet.png"
    evidence_sheet.save(evidence_sheet_path)

    hypotheses = domain_hypotheses(white_ratio, edge_density, mean_saturation, palette_entropy)
    if domain != "auto":
        selected_domain = domain
        domain_selection = "user"
    else:
        top = hypotheses[0]
        runner_up = hypotheses[1]
        decisive = top["score"] >= 0.55 and top["score"] - runner_up["score"] >= 0.15
        selected_domain = top["domain"] if decisive else "mixed"
        domain_selection = "heuristic-high-confidence-needs-visual-confirmation" if decisive else "ambiguous-needs-visual-confirmation"
    report = {
        "schema_version": "1.0",
        "source": str(source.resolve()),
        "source_sha256": sha256(source),
        "canvas": {"width": source_size[0], "height": source_size[1]},
        "analysis_size": {"width": preview.width, "height": preview.height},
        "selected_domain": selected_domain,
        "domain_selection": domain_selection,
        "domain_hypotheses": hypotheses,
        "signals": {
            "white_ratio": round(white_ratio, 4),
            "foreground_ratio": round(foreground_ratio(rgb), 4),
            "has_transparency": original.getchannel("A").getextrema() != (255, 255),
            "edge_density": round(edge_density, 4),
            "mean_saturation": round(mean_saturation, 4),
            "palette_entropy": round(palette_entropy, 4),
        },
        "candidate_regions": regions,
        "candidate_region_count_before_cap": len(all_regions),
        "repeated_region_families": repeated_region_families(regions),
        "artifacts": {
            "preview": str(preview_path),
            "palette_map": str(palette_map_path),
            "edge_map": str(edge_path),
            "region_overlay": str(overlay_path),
            "evidence_sheet": str(evidence_sheet_path),
        },
        "limitations": [
            "Candidate regions are color-connected components, not semantic labels.",
            "The selected domain is only a routing hint until visually confirmed.",
        ],
    }
    report_path = output_dir / "analysis.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "PASS", "analysis": str(report_path), "regions": len(regions), "selected_domain": selected_domain}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--domain", choices=DOMAINS, default="auto")
    parser.add_argument("--max-dimension", type=int, default=1024)
    parser.add_argument("--palette-colors", type=int, default=16)
    parser.add_argument("--min-area-fraction", type=float, default=0.0004)
    parser.add_argument("--max-regions", type=int, default=240)
    args = parser.parse_args()
    if args.max_dimension < 128:
        raise SystemExit("--max-dimension must be at least 128")
    if not 4 <= args.palette_colors <= 64:
        raise SystemExit("--palette-colors must be between 4 and 64")
    if not 0 < args.min_area_fraction < 0.1:
        raise SystemExit("--min-area-fraction must be between 0 and 0.1")
    if not 24 <= args.max_regions <= 1000:
        raise SystemExit("--max-regions must be between 24 and 1000")
    result = analyze(args.source.resolve(), args.output_dir.resolve(), args.domain, args.max_dimension, args.palette_colors, args.min_area_fraction, args.max_regions)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
