#!/usr/bin/env python3
"""Propose neutral, unreviewed colour-region seeds for opaque flat artwork.

The draft uses rebuild_regions' nearest-RGB / eroded-core contract. Colour
components are geometry evidence, not recognized objects or semantic labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage as ndi


def propose(source: Path, output_dir: Path, *, palette_colors=16, min_area=4,
            max_regions=240, domain="mixed", palette_distance=16) -> dict:
    source, output_dir = Path(source), Path(output_dir)
    if output_dir.exists():
        raise ValueError("Output directory exists; choose a new directory.")
    if (not isinstance(palette_colors, int) or not 2 <= palette_colors <= 64
            or not isinstance(min_area, int) or min_area < 1
            or not isinstance(max_regions, int) or not 2 <= max_regions <= 255
            or not np.isfinite(palette_distance) or not 0 <= palette_distance <= 64
            or domain not in ("scientific", "cell", "cartoon", "mixed")):
        raise ValueError("Use 2..64 colours, min_area >= 1, 2..255 regions, palette_distance in 0..64, and a supported domain.")
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    if image.getchannel("A").getextrema() != (255, 255):
        raise ValueError("Region proposals require opaque artwork; transparent input needs an alpha-aware route.")
    if image.width * image.height > 16_000_000:
        raise ValueError("Region proposals are limited to 16 million source pixels; use reviewed crops for larger artwork.")
    rgb_image = image.convert("RGB")
    rgb = np.asarray(rgb_image, dtype=np.float32)
    h, w = rgb.shape[:2]
    # Histogram bins absorb low-level compression / antialias noise. Median-cut
    # can spend its entire budget on near-identical black and white in flat art.
    bins = (rgb.astype(np.int32) // 8)
    bins = ((bins[:, :, 0] * 32 + bins[:, :, 1]) * 32 + bins[:, :, 2]).ravel()
    counts = np.bincount(bins, minlength=32768)
    means = np.column_stack([np.bincount(bins, weights=rgb[:, :, c].ravel(), minlength=32768)
                             / np.maximum(counts, 1) for c in range(3)])
    selected = []
    for index in np.argsort(-counts, kind="stable"):
        if not counts[index]:
            break
        colour = means[index]
        if not selected or np.min(np.max(np.abs(np.asarray(selected) - colour), axis=1)) >= palette_distance:
            selected.append(colour)
        if len(selected) == palette_colors:
            break
    palette = np.round(selected).astype(np.float32)
    # Match segment() exactly, including first-palette-entry tie breaking. PIL's
    # own quantized labels are not guaranteed to use this same distance rule.
    classes, best = np.zeros((h, w), np.int32), np.full((h, w), np.inf)
    for ci, colour in enumerate(palette):
        error = ((rgb - colour) ** 2).sum(2)
        take = error < best
        classes[take], best[take] = ci, error[take]

    candidates, omitted = [], []
    border = np.zeros((h, w), bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    for ci in range(len(palette)):
        mask = classes == ci
        components, _ = ndi.label(mask)
        cores, _ = ndi.label(ndi.binary_erosion(mask, iterations=2))
        slices = ndi.find_objects(components)
        for label, box in enumerate(slices, 1):
            if box is None:
                continue
            component = components[box] == label
            area = int(component.sum())
            y0, x0 = box[0].start, box[1].start
            bbox = [x0, y0, box[1].stop - x0, box[0].stop - y0]
            if area < min_area:
                omitted.append(dict(palette_index=ci, bbox=bbox, area_px=area, reason="below_min_area"))
                continue
            core_ids = np.unique(cores[box][component])
            core_ids = core_ids[core_ids != 0]
            # Each eroded core needs its own marker. Mixing erosion=0 and =2
            # within one original component would overlap markers in segment().
            for core_id in core_ids if len(core_ids) else [0]:
                core = cores[box] == core_id if core_id else component
                distance = ndi.distance_transform_edt(np.pad(core, 1))[1:-1, 1:-1]
                sy, sx = np.unravel_index(np.argmax(distance), core.shape)
                ys, xs = np.where(core)
                candidates.append(dict(palette_index=ci, seed=[int(sx + x0), int(sy + y0)],
                    core_erosion=2 if core_id else 0, core_area_px=int(core.sum()),
                    component_area_px=area, component_bbox=bbox,
                    bbox=[int(xs.min() + x0), int(ys.min() + y0), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)],
                    border_pixels=int((component & border[box]).sum()),
                    split_core_count=len(core_ids) or 1,
                    colour_std=float(np.std(rgb[box][core], axis=0).mean())))
    if not candidates:
        raise ValueError("No colour region meets min_area; lower the area budget or choose another route.")
    # A border-connected region is only a background hypothesis. Leave enclosed
    # same-colour islands neutral: they could be holes, eyes, lettering or paint.
    background = max(candidates, key=lambda c: (c["border_pixels"], c["component_area_px"]))
    candidates.sort(key=lambda c: (c is not background, -c["core_area_px"], c["palette_index"], c["seed"]))
    for item in candidates[max_regions:]:
        omitted.append(dict(palette_index=item["palette_index"], bbox=item["bbox"],
                            area_px=item["core_area_px"], reason="max_regions_core_budget"))
    before_cap = len(candidates)
    candidates = candidates[:max_regions]
    parts = []
    for index, candidate in enumerate(candidates, 1):
        identifier = f"region-{index:03d}"
        candidate["id"] = identifier
        parts.append(dict(id=identifier, palette_index=candidate["palette_index"],
            seed=candidate["seed"], core_erosion=candidate["core_erosion"],
            role="background" if candidate is background else "other",
            description=f"Unreviewed colour region {index}; assign meaning only after visual inspection",
            confidence=0.0, evidence=[f"Nearest RGB palette class {candidate['palette_index']} has an interior seed at {candidate['seed']}",
                f"Distinct eroded core contains {candidate['core_area_px']} source pixels; no semantic identity inferred"]))

    change = np.zeros((h, w), np.float32)
    change[:, 1:] = np.max(np.abs(rgb[:, 1:] - rgb[:, :-1]), axis=2)
    change[1:] = np.maximum(change[1:], np.max(np.abs(rgb[1:] - rgb[:-1]), axis=2))
    palette_mae = float(np.abs(rgb - palette[classes]).mean())
    smooth_fraction = float(((change > 0) & (change <= 8)).mean())
    omitted_pixels = sum(item["area_px"] for item in omitted)
    features = dict(width=w, height=h, source_pixels=w * h, has_transparency=False,
        palette_colours=len(palette), palette_mae=round(palette_mae, 4),
        smooth_colour_change_fraction=round(smooth_fraction, 4),
        strong_neighbour_edge_fraction=round(float((change > 32).mean()), 4),
        candidate_cores_before_cap=before_cap,
        thin_or_tiny_regions=sum(p["core_erosion"] == 0 for p in parts))
    warnings = [
        "Neutral region names, roles and confidence=0 require visual review; this is not semantic recognition.",
        "The background is a border-colour hypothesis. Check holes, same-colour islands, text, touching objects and occlusion before accepting it.",
        "The palette budget and minimum colour distance can merge similar intentional colours; inspect the palette map and lower palette_distance if needed.",
        "Colour changes can be paint gradients rather than shape boundaries. Merge such regions and model their paint separately; antialias shades are not new objects.",
        "Original pixels remain the evidence. Resizing is interpolation, not super-resolution; review tiny details at native size before inventing curves.",
    ]
    if min(w, h) < 256 or features["thin_or_tiny_regions"]:
        warnings.append("Low source resolution or sub-5px details limit contour evidence. Any super-resolution result must be checked against the untouched original.")
    if any(c["split_core_count"] > 1 for c in candidates):
        warnings.append("Some connected colours split into multiple eroded cores; review these as possible parts of one object, not separate recognized objects.")
    alternatives = []
    # ponytail: these measured thresholds flag risk, not image-class recognition;
    # use a reviewed object/paint plan when flat-colour evidence is insufficient.
    if palette_mae > 12:
        alternatives.append("Palette residual is high; textured/photographic content or too few colours needs another route.")
    if smooth_fraction > .35 and palette_mae > 3:
        alternatives.append("Broad smooth colour variation may be gradients; avoid treating palette bands as object contours.")
    if omitted_pixels / (w * h) > .025:
        alternatives.append("The component budget omits more than 2.5% of source pixels/cores; increase the budget or review another route.")
    if omitted:
        warnings.append(f"Omitted {len(omitted)} components/cores ({omitted_pixels} pixels in reported masks); inspect omissions before reconstruction.")
    plan = dict(schema_version="1.0", source=str(source.resolve()),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), domain=domain,
        review_status="draft", canvas=dict(width=w, height=h),
        palette=palette.astype(int).tolist(), parts=parts, notes=warnings + alternatives)
    report = dict(status="NEEDS_ALTERNATIVE" if alternatives else "NEEDS_REVIEW",
        source=str(source.resolve()), source_sha256=plan["source_sha256"],
        plan=str((output_dir / "region-plan.json").resolve()), source_features=features,
        parameters=dict(palette_colors=palette_colors, palette_distance=palette_distance, min_area=min_area, max_regions=max_regions),
        candidate_regions=candidates, omitted_components=omitted,
        omitted_mask_pixels=omitted_pixels, warnings=warnings, alternative_reasons=alternatives,
        artifacts={name: str((output_dir / filename).resolve()) for name, filename in
                   (("plan", "region-plan.json"), ("overlay", "region-overlay.png"),
                    ("palette_map", "palette-map.png"), ("report", "proposal.json"))})
    overlay = rgb_image.copy()
    drawing = ImageDraw.Draw(overlay)
    for part in parts:
        x, y = part["seed"]
        colour = "#e11d48" if part["role"] == "background" else "#2563eb"
        drawing.ellipse((x - 3, y - 3, x + 3, y + 3), outline="white", fill=colour)
        drawing.text((x + 5, y), part["id"], fill=colour, stroke_width=1, stroke_fill="white")
    output_dir.mkdir(parents=True)
    overlay.save(output_dir / "region-overlay.png")
    Image.fromarray(palette[classes].astype(np.uint8)).save(output_dir / "palette-map.png")
    (output_dir / "region-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (output_dir / "proposal.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--palette-colors", type=int, default=16)
    parser.add_argument("--palette-distance", type=float, default=16)
    parser.add_argument("--min-area", type=int, default=4)
    parser.add_argument("--max-regions", type=int, default=240)
    parser.add_argument("--domain", choices=("scientific", "cell", "cartoon", "mixed"), default="mixed")
    args = parser.parse_args()
    print(json.dumps(propose(args.source, args.output_dir, palette_colors=args.palette_colors,
        min_area=args.min_area, max_regions=args.max_regions, domain=args.domain,
        palette_distance=args.palette_distance), indent=2))
