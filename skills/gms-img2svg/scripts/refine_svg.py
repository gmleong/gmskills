#!/usr/bin/env python3
"""Bounded local-gradient experiments and render-checked SVG compaction.

Core compaction uses existing dependencies. --gradients additionally needs
NumPy, SciPy and scikit-image; --cross-render needs resvg-py.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageOps

from compare_render import binary_edges, flatten, mean_error, render_rgba, svg_complexity, tolerant_edge_f1
from validate_svg import NUMBER_PATTERN, audit as audit_svg, local_name

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def fmt(value: float, digits: int = 3) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return "0" if text in {"", "-0"} else text


def compact_svg(text: str, digits: int) -> str:
    root = ET.fromstring(text)
    for element in root.iter():
        if local_name(element.tag) == "path":
            data = NUMBER_PATTERN.sub(lambda m: fmt(float(m.group()), digits), element.get("d", ""))
            data = re.sub(r"[\s,]+", " ", data.strip())
            data = re.sub(r"\s*([AaCcHhLlMmQqSsTtVvZz])\s*", r"\1", data)
            data = re.sub(r" (?=-)", "", data)
            element.set("d", data)
    # Leave all text, IDs, groups, transforms and element order intact.
    return ET.tostring(root, encoding="unicode")


def structure(text: str) -> list:
    """Only path data may change during compaction; text and grouping are contractual."""
    def node(e, text_parent=False):
        in_text = text_parent or local_name(e.tag) in {"text", "tspan", "textPath"}
        return [e.tag, {k: v for k, v in e.attrib.items() if k != "d"},
                e.text if in_text or (e.text or "").strip() else None,
                e.tail if text_parent or (e.tail or "").strip() else None,
                [node(child, in_text) for child in e]]
    return node(ET.fromstring(text))


def scores(source: Image.Image, rendered: Image.Image) -> dict:
    return {
        "white_mae": mean_error(flatten(source), flatten(rendered)),
        "black_mae": mean_error(flatten(source, "black"), flatten(rendered, "black")),
        "alpha_mae": mean_error(source.getchannel("A"), rendered.getchannel("A")),
    }


def fit_paints(xs, ys, colours, identifier: str):
    """Fit flat, linear and local concentric radial paint; rank by masked MAE."""
    import numpy as np

    def colour(rgb):
        return "#" + "".join(f"{int(v):02x}" for v in np.clip(np.rint(rgb), 0, 255))

    median = np.median(colours, axis=0)
    models = [(float(np.abs(colours - median).mean()), None, colour(median), "flat")]
    xy = np.column_stack([xs, ys]).astype(float)
    centre = xy.mean(axis=0)
    plane = np.linalg.lstsq(np.column_stack([xy - centre, np.ones(len(xy))]), colours, rcond=None)[0]
    # SVD avoids cancellation when RGB channels change in opposite directions.
    direction = np.linalg.svd(plane[:2], full_matrices=False)[0][:, 0]
    linear_t = (xy - centre) @ direction
    radial_t = np.linalg.norm(xy - centre, axis=1)
    for kind, t in (("linear", linear_t), ("radial", radial_t)):
        low, high = (float(t.min()), float(t.max())) if kind == "linear" else (0.0, float(t.max()))
        if high - low < 0.5:
            continue
        u = (t - low) / (high - low)
        slope, intercept = np.linalg.lstsq(np.column_stack([u, np.ones(len(u))]), colours, rcond=None)[0]
        first, last = np.clip(np.rint(intercept), 0, 255), np.clip(np.rint(intercept + slope), 0, 255)
        predicted = first + u[:, None] * (last - first)
        attrs = {"id": identifier, "gradientUnits": "userSpaceOnUse"}
        if kind == "linear":
            start, end = centre + low * direction, centre + high * direction
            attrs.update(dict(zip(("x1", "y1", "x2", "y2"), map(fmt, [*start, *end]))))
        else:
            attrs.update({"cx": fmt(centre[0]), "cy": fmt(centre[1]), "r": fmt(high)})
        gradient = ET.Element(f"{{{NS}}}{kind}Gradient", attrs)
        ET.SubElement(gradient, f"{{{NS}}}stop", {"offset": "0", "stop-color": colour(first)})
        ET.SubElement(gradient, f"{{{NS}}}stop", {"offset": "1", "stop-color": colour(last)})
        models.append((float(np.abs(colours - predicted).mean()), gradient, f"url(#{identifier})", kind))
    return sorted(models, key=lambda item: item[0])


def mask_path(mask, x: int, y: int) -> tuple[str, int]:
    import numpy as np
    from skimage.measure import approximate_polygon, find_contours

    parts, points = [], 0
    # All rings participate in evenodd filling, including holes and disconnected islands.
    for contour in find_contours(np.pad(mask.astype(float), 1), 0.5):
        contour = approximate_polygon(contour, tolerance=0.15) - 0.5
        if len(contour) < 4:
            continue
        parts.append("M" + " ".join(f"{fmt(cx + x)} {fmt(cy + y)}" for cy, cx in contour[:-1]) + "Z")
        points += len(contour) - 1
    return " ".join(parts), points


def refine(source_path: Path, svg_path: Path, output: Path, *, gradients: bool = False,
           cross_render: bool = False, digits: int = 3, chunk_size: int = 12,
           threshold: float = 4, min_area: int = 6, max_candidates: int = 64,
           max_added_paths: int = 32, max_added_points: int = 2048,
           max_added_bytes: int = 32768, min_improvement: float = 0.0001,
           min_improvement_per_kib: float = 0.001, max_mae_increase: float = 0.002,
           max_render_change: float = 0.02, svgo: str | None = None) -> dict:
    report_path = output.with_suffix(".refine.json")
    if output.exists() or report_path.exists():
        raise ValueError("Output or report already exists; allocate a new output path.")
    limits = (threshold, min_improvement, min_improvement_per_kib, max_mae_increase, max_render_change)
    if any(not math.isfinite(v) or v < 0 for v in limits):
        raise ValueError("Error thresholds must be finite and nonnegative.")
    if not 0 <= digits <= 6 or chunk_size < 2 or min_area < 1 or min(max_candidates, max_added_paths, max_added_points, max_added_bytes) < 0:
        raise ValueError("Invalid precision, chunk size or complexity budget.")
    validation = audit_svg(svg_path)
    if validation["status"] != "PASS":
        raise ValueError("Invalid input SVG: " + "; ".join(validation["errors"]))
    with Image.open(source_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGBA")
    original = svg_path.read_text(encoding="utf-8")
    engines = ("cairosvg", "resvg") if cross_render else ("cairosvg",)
    current_images = {engine: render_rgba(svg_path, *source.size, renderer=engine) for engine in engines}
    current_scores = {engine: scores(source, img) for engine, img in current_images.items()}
    source_edges = binary_edges(flatten(source))
    current_edges = {engine: tolerant_edge_f1(source_edges, binary_edges(flatten(img)), radius=1)
                     for engine, img in current_images.items()}
    report = {"source": str(source_path.resolve()), "input": str(svg_path.resolve()),
              "output": str(output.resolve()), "before": copy.deepcopy(current_scores),
              "complexity_before": svg_complexity(svg_path), "accepted": [], "edge_f1_before": current_edges.copy(),
              "limits": {"max_added_paths": max_added_paths, "max_added_points": max_added_points,
                         "max_added_bytes": max_added_bytes, "max_candidates": max_candidates,
                         "min_improvement": min_improvement, "min_improvement_per_kib": min_improvement_per_kib,
                         "max_mae_increase": max_mae_increase, "max_render_change": max_render_change},
              "parameters": {"digits": digits, "chunk_size": chunk_size, "threshold": threshold, "min_area": min_area}}
    text = original
    with tempfile.TemporaryDirectory(prefix="img2svg-refine-") as temporary:
        candidate_path = Path(temporary) / "candidate.svg"
        if gradients:
            import numpy as np
            from scipy import ndimage

            if source.getchannel("A").getextrema() != (255, 255):
                raise ValueError("Gradient experiments currently require opaque input; compaction supports transparency.")
            root = ET.fromstring(text)
            viewbox = [float(v) for v in root.get("viewBox", f"0 0 {source.width} {source.height}").replace(",", " ").split()]
            if len(viewbox) != 4 or viewbox != [0, 0, source.width, source.height] or root.get("transform"):
                raise ValueError("Gradient experiments require a pixel-aligned viewBox: 0 0 source_width source_height.")
            source_array = np.asarray(flatten(source), dtype=float)

            def local_gradient_error(image, box):
                x0, y0, x1, y1 = box
                target = source_array[y0:y1, x0:x1]
                sample = np.asarray(flatten(image).crop(box), dtype=float)
                return sum(float(np.abs(np.diff(sample, axis=axis) - np.diff(target, axis=axis)).sum())
                           for axis in (0, 1))

            error = np.abs(source_array - np.asarray(flatten(current_images["cairosvg"]), dtype=float)).max(axis=2)
            tiles = []
            # ponytail: fixed spatial chunks bound local curvature; adaptive splitting if these prove insufficient.
            for y in range(0, source.height, chunk_size):
                for x in range(0, source.width, chunk_size):
                    patch = error[y:y + chunk_size, x:x + chunk_size]
                    if (patch > threshold).sum() >= min_area:
                        tiles.append((float(patch.sum()), x, y))
            tiles.sort(reverse=True)
            identifiers = {e.get("id") for e in root.iter()}
            prefix = "refine"
            while any(i and i.startswith(prefix + "-") for i in identifiers):
                prefix += "-new"
            baseline_bytes = len(ET.tostring(root, encoding="utf-8"))
            defs = ET.SubElement(root, f"{{{NS}}}defs")
            group = ET.SubElement(root, f"{{{NS}}}g", {"id": prefix + "-details", "data-role": "trace-fragment"})
            used_bytes = used_points = 0
            attempts = 0
            report["seam_rejections"] = 0
            for _, x, y in tiles[:max_candidates]:
                if len(report["accepted"]) >= max_added_paths:
                    break
                current_array = np.asarray(flatten(current_images["cairosvg"]), dtype=float)
                patch = source_array[y:y + chunk_size, x:x + chunk_size]
                residual = np.abs(patch - current_array[y:y + chunk_size, x:x + chunk_size]).max(axis=2) > threshold
                mask = ndimage.binary_dilation(residual, iterations=1)
                ys, xs = np.where(mask)
                if len(xs) < min_area:
                    continue
                data, point_count = mask_path(mask, x, y)
                if not data or used_points + point_count > max_added_points:
                    continue
                index = len(report["accepted"]) + 1
                _, gradient, fill, kind = fit_paints(xs + x + 0.5, ys + y + 0.5, patch[ys, xs], f"{prefix}-paint-{index}")[0]
                path = ET.Element(f"{{{NS}}}path", {"id": f"{prefix}-patch-{index}", "d": data, "fill": fill, "fill-rule": "evenodd"})
                if gradient is not None:
                    defs.append(gradient)
                group.append(path)
                candidate = ET.tostring(root, encoding="unicode")
                added_bytes = len(candidate.encode()) - baseline_bytes - used_bytes
                if used_bytes + added_bytes > max_added_bytes:
                    group.remove(path)
                    if gradient is not None:
                        defs.remove(gradient)
                    continue
                candidate_path.write_text(candidate, encoding="utf-8")
                attempts += 1
                images, measurements, edges = {}, {}, {}
                required = max(min_improvement, min_improvement_per_kib * added_bytes / 1024)
                accepted = True
                for engine in engines:
                    images[engine] = render_rgba(candidate_path, *source.size, renderer=engine)
                    measurements[engine] = scores(source, images[engine])
                    gain = min(current_scores[engine][key] - measurements[engine][key] for key in ("white_mae", "black_mae"))
                    if gain < required or measurements[engine]["alpha_mae"] > current_scores[engine]["alpha_mae"] + 1e-9:
                        accepted = False
                        break
                    # Include one pixel outside the tile to expose low-contrast rectangular seams.
                    box = (max(0, x - 1), max(0, y - 1), min(source.width, x + chunk_size + 1), min(source.height, y + chunk_size + 1))
                    if local_gradient_error(images[engine], box) > local_gradient_error(current_images[engine], box) + 1e-6:
                        report["seam_rejections"] += 1
                        accepted = False
                        break
                    edges[engine] = tolerant_edge_f1(source_edges, binary_edges(flatten(images[engine])), radius=1)
                    if edges[engine] < current_edges[engine]:
                        accepted = False
                        break
                if accepted:
                    current_images, current_scores = images, measurements
                    current_edges = edges
                    used_bytes += added_bytes
                    used_points += point_count
                    report["accepted"].append({"x": x, "y": y, "kind": kind, "bytes": added_bytes, "points": point_count})
                else:
                    group.remove(path)
                    if gradient is not None:
                        defs.remove(gradient)
            if not len(defs):
                root.remove(defs)
            if not len(group):
                root.remove(group)
            text = ET.tostring(root, encoding="unicode") if report["accepted"] else original
            report["gradient_attempts"] = attempts
            report["added_points"] = used_points
            report["added_bytes"] = used_bytes

        compact = compact_svg(text, digits)
        if svgo:
            config = Path(temporary) / "svgo.config.mjs"
            config.write_text("export default " + json.dumps({"plugins": [
                {"name": "convertPathData", "params": {"floatPrecision": digits,
                    "applyTransforms": False, "applyTransformsStroked": False,
                    "makeArcs": False, "straightCurves": False, "convertToQ": False,
                    "convertToZ": False, "curveSmoothShorthands": False,
                    "removeUseless": False, "collapseRepeated": False,
                    "forceAbsolutePath": True}}
            ]}) + ";\n", encoding="utf-8")
            svgo_input = Path(temporary) / "input.svg"
            svgo_input.write_text(text, encoding="utf-8")
            subprocess.run([svgo, "--input", str(svgo_input), "--output", str(candidate_path),
                            "--config", str(config)], capture_output=True, text=True, check=True, timeout=120)
            compact = candidate_path.read_text(encoding="utf-8")
            report["svgo_version"] = subprocess.run([svgo, "--version"], capture_output=True,
                                                     text=True, check=True, timeout=10).stdout.strip()
        candidate_path.write_text(compact, encoding="utf-8")
        if audit_svg(candidate_path)["status"] != "PASS":
            raise ValueError("Compacted SVG failed validation.")
        images = {engine: render_rgba(candidate_path, *source.size, renderer=engine) for engine in engines}
        measurements = {engine: scores(source, image) for engine, image in images.items()}
        changes = {engine: scores(current_images[engine], image) for engine, image in images.items()}
        compact_edges = {engine: tolerant_edge_f1(source_edges, binary_edges(flatten(image)), radius=1)
                         for engine, image in images.items()}
        report["compaction_candidate"] = {"bytes": len(compact.encode()), "scores": measurements,
                                          "render_change": changes, "structure_preserved": structure(compact) == structure(text)}
        keep = structure(compact) == structure(text) and len(compact.encode()) < len(text.encode()) and all(compact_edges[e] >= current_edges[e] for e in engines) and all(
            measurements[e][key] <= current_scores[e][key] + max_mae_increase
            and changes[e][key] <= max_render_change
            for e in engines for key in measurements[e]
        )
        report["compaction_accepted"] = keep
        if keep:
            text, current_scores, current_edges = compact, measurements, compact_edges
        candidate_path.write_text(text, encoding="utf-8")
        report["complexity_after"] = svg_complexity(candidate_path)
        report["after"] = current_scores
        report["edge_f1_after"] = current_edges
        report["limitations"] = ["Added detail patches are trace fragments, not semantic objects.",
                                 "Numerical acceptance does not replace full-canvas and detail visual review."]
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental replacement of existing deliverables.
        with output.open("x", encoding="utf-8") as handle:
            handle.write(text)
        with report_path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gradients", action="store_true")
    parser.add_argument("--cross-render", action="store_true")
    parser.add_argument("--svgo", help="optional SVGO executable; only convertPathData is enabled")
    parser.add_argument("--digits", type=int, default=3)
    parser.add_argument("--chunk-size", type=int, default=12)
    parser.add_argument("--threshold", type=float, default=4)
    parser.add_argument("--min-area", type=int, default=6)
    parser.add_argument("--max-candidates", type=int, default=64)
    parser.add_argument("--max-added-paths", type=int, default=32)
    parser.add_argument("--max-added-points", type=int, default=2048)
    parser.add_argument("--max-added-bytes", type=int, default=32768)
    parser.add_argument("--min-improvement", type=float, default=0.0001)
    parser.add_argument("--min-improvement-per-kib", type=float, default=0.001)
    parser.add_argument("--max-mae-increase", type=float, default=0.002)
    parser.add_argument("--max-render-change", type=float, default=0.02)
    args = vars(parser.parse_args())
    source, svg, output = args.pop("source"), args.pop("svg"), args.pop("output")
    report = refine(source, svg, output, **args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
