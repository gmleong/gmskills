#!/usr/bin/env python3
"""Fit native paints to existing named objects; keep geometry and reject regressions."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path
from PIL import Image, ImageColor, ImageOps
from scipy import ndimage

from compare_render import flatten, render_rgba
from prepare_geometry_cache import path_data
from refine_svg import NS, fit_paints, scores
from validate_svg import VECTOR_TAGS, audit as audit_svg, local_name

ENGINES = ("cairosvg", "resvg")
ET.register_namespace("", NS)


def shapes(node):
    return [node] if local_name(node.tag) in VECTOR_TAGS else [e for e in node if local_name(e.tag) in VECTOR_TAGS]


def ancestors(node, parents):
    while node is not None:
        yield node
        node = parents.get(node)


def inherited(node, key, parents, default):
    return next((e.get(key) for e in ancestors(node, parents) if e.get(key) is not None), default)


def safe_object(node, parents, identifiers):
    if local_name(node.tag) not in VECTOR_TAGS | {"g"}:
        return "Only named shapes or leaf groups can be refined."
    members = shapes(node)
    if local_name(node.tag) == "g" and any(local_name(e.tag) not in VECTOR_TAGS | {"title", "desc", "metadata"} for e in node):
        return "Only leaf groups containing geometry are supported."
    if not members:
        return "No fillable leaf geometry."
    fills = set()
    for shape in members:
        for e in ancestors(shape, parents):
            if local_name(e.tag) in {"defs", "symbol", "clipPath", "mask", "marker", "pattern"}:
                return "Definition geometry is not an independently painted object."
            if local_name(e.tag) == "svg" and e in parents:
                return "Nested SVG coordinate systems are unsupported."
            for key in ("transform", "clip-path", "mask", "filter", "style", "class"):
                if e.get(key):
                    return f"Unsupported {key} on object or ancestor."
            if e.get("display", "") == "none" or e.get("visibility", "") in {"hidden", "collapse"}:
                return "Hidden object."
            for key in ("opacity", "fill-opacity"):
                try:
                    if float(e.get(key, "1")) != 1:
                        return f"Nonopaque {key} is unsupported."
                except ValueError:
                    return f"Unsupported {key} value."
        fill = inherited(shape, "fill", parents, "black").strip()
        if fill == "currentColor":
            fill = inherited(shape, "color", parents, "black")
        match = re.fullmatch(r"url\(\s*#([^\s)]+)\s*\)", fill)
        if match:
            gradient = identifiers.get(match.group(1))
            if gradient is None or local_name(gradient.tag) not in {"linearGradient", "radialGradient"}:
                return "Unsupported paint server."
            if any(local_name(k) in {"href", "gradientTransform", "style"} for k in gradient.attrib):
                return "Linked or transformed gradient is unsupported."
            if len(gradient) < 2:
                return "Gradient has insufficient explicit stops."
            for stop in gradient:
                try:
                    if (local_name(stop.tag) != "stop" or stop.get("style") or
                            float(stop.get("stop-opacity", "1")) != 1 or
                            ImageColor.getcolor(stop.get("stop-color", "black"), "RGBA")[3] != 255):
                        return "Nonopaque or styled gradient stop is unsupported."
                except ValueError:
                    return "Unsupported gradient stop."
        else:
            try:
                if ImageColor.getcolor(fill, "RGBA")[3] != 255:
                    return "Transparent fill is unsupported."
            except ValueError:
                return "No supported opaque fill."
        fills.add(fill)
    if len(fills) != 1:
        return "Multicolour group: select individual named shapes instead."
    return None


def geometry_signature(root, mutable, added):
    """Existing XML is contractual except selected leaf fills and new gradient defs."""
    def visit(node, inside=False):
        if node.get("id") in added:
            return None
        inside = inside or node.get("id") in mutable
        attrs = {k: v for k, v in node.attrib.items() if not (inside and local_name(node.tag) in VECTOR_TAGS and k == "fill")}
        children = [v for c in node if (v := visit(c, inside)) is not None]
        if local_name(node.tag) == "defs" and not children and not node.attrib:
            return None
        return [node.tag, attrs, node.text, node.tail, children]
    return visit(root)


def refine(source_path: Path, svg_path: Path, output: Path, *, target_ids: list[str] | None = None,
           max_objects: int = 12, min_pixels: int = 24, max_samples: int = 8192,
           min_improvement: float = 0.0001) -> dict:
    source_path, svg_path, output = map(Path, (source_path, svg_path, output))
    report_path = output.with_suffix(".paints.json")
    if output.exists() or report_path.exists() or output.resolve() in {source_path.resolve(), svg_path.resolve()}:
        raise ValueError("Output or report already exists; allocate a new path.")
    if (max_objects < 0 or min_pixels < 3 or max_samples < min_pixels or
            not math.isfinite(min_improvement) or min_improvement <= 0):
        raise ValueError("Invalid object/sample budgets or improvement threshold.")
    validation = audit_svg(svg_path)
    if validation["status"] != "PASS":
        raise ValueError("Invalid SVG: " + "; ".join(validation["errors"]))
    source_bytes, original = source_path.read_bytes(), svg_path.read_text(encoding="utf-8")
    with Image.open(source_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGBA")
    actual = np.asarray(flatten(source), dtype=float)
    root = ET.fromstring(original)
    identifiers = {e.get("id"): e for e in root.iter() if e.get("id")}
    if len(identifiers) != sum(bool(e.get("id")) for e in root.iter()):
        raise ValueError("SVG IDs must be unique.")
    parents = {child: parent for parent in root.iter() for child in parent}
    leaf_groups = {e for e in root.iter() if e.get("id") and local_name(e.tag) == "g" and shapes(e)
                   and not any(local_name(c.tag) == "g" for c in e)}
    automatic = [e.get("id") for e in root.iter() if e in leaf_groups or
                 (e.get("id") and local_name(e.tag) in VECTOR_TAGS and
                  not any(p in leaf_groups or local_name(p.tag) in {"defs", "clipPath", "symbol", "pattern", "mask", "marker"}
                          for p in ancestors(parents.get(e), parents)))]
    targets = list(dict.fromkeys(automatic if target_ids is None else target_ids))
    global_reason = None
    try:
        viewbox = [float(v) for v in root.get("viewBox", "").replace(",", " ").split()]
        if viewbox != [0, 0, source.width, source.height]:
            global_reason = "Paint fitting requires viewBox='0 0 source_width source_height'."
    except ValueError:
        global_reason = "Unsupported viewBox."
    if source.getchannel("A").getextrema() != (255, 255):
        global_reason = "Paint fitting requires an opaque source."
    if any(local_name(e.tag) in {"use", "animate", "set", "animateTransform", "animateMotion"} or
           any(e.get(k) for k in ("filter", "mask", "mix-blend-mode")) or
           any(k in e.get("style", "") for k in ("filter", "mask", "mix-blend-mode")) for e in root.iter()):
        global_reason = "Referenced instances, animation, masks, filters or blending require manual review."
    current_images = {engine: render_rgba(svg_path, *source.size, renderer=engine) for engine in ENGINES}
    current_scores = {engine: scores(source, image) for engine, image in current_images.items()}
    report = dict(source=str(source_path.resolve()), source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                  input=str(svg_path.resolve()), output=str(output.resolve()), report=str(report_path.resolve()),
                  before=copy.deepcopy(current_scores), objects=[], accepted=[], max_objects=max_objects,
                  limitations=["Fits opaque flat, two-stop linear and concentric radial paint; no geometry or semantic recognition.",
                               "Numerical acceptance needs visual review; native Illustrator playback is not verified."])
    residual = abs(actual - np.asarray(flatten(current_images["cairosvg"]), float)).mean(axis=2)
    entries = []
    for identifier in targets:
        node = identifiers.get(identifier)
        reason = global_reason or ("Unknown object ID." if node is None else safe_object(node, parents, identifiers))
        entry = dict(id=identifier, status="skipped", reason=reason, candidates=[])
        report["objects"].append(entry)
        if reason:
            continue
        try:
            pen = BoundsPen(None)
            for shape in shapes(node):
                parse_path(path_data(shape), pen)
            if pen.bounds is None:
                raise ValueError("Empty geometry")
            x0, y0, x1, y1 = pen.bounds
            box = (max(0, math.floor(x0)), max(0, math.floor(y0)), min(source.width, math.ceil(x1)), min(source.height, math.ceil(y1)))
            x0, y0, x1, y1 = box
            entry["priority"] = float(residual[y0:y1, x0:x1].sum()) if x1 > x0 and y1 > y0 else 0
            entries.append((entry, identifier))
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            entry["reason"] = "Unsupported geometry for ranking: " + str(exc)
    # ponytail: bounding-box residual ranks bounded candidates; it is advisory, not segmentation.
    entries.sort(key=lambda pair: pair[0]["priority"], reverse=True)
    added, mutable = set(), set()
    before_signature = geometry_signature(root, set(targets), set())
    with tempfile.TemporaryDirectory(prefix="img2svg-paints-") as temporary:
        candidate_path = Path(temporary) / "candidate.svg"

        def render(node):
            candidate_path.write_text(ET.tostring(node, encoding="unicode"), encoding="utf-8")
            return {engine: render_rgba(candidate_path, *source.size, renderer=engine) for engine in ENGINES}

        for index, (entry, identifier) in enumerate(entries):
            if index >= max_objects:
                entry["reason"] = "Object budget reached."
                continue
            masks = []
            for colour in ("#000000", "#ffffff"):
                probe = copy.deepcopy(root)
                target = next(e for e in probe.iter() if e.get("id") == identifier)
                for shape in shapes(target):
                    shape.set("fill", colour)
                masks.append(render(probe))
            coverage = {engine: np.abs(np.asarray(flatten(masks[1][engine]), float) -
                                       np.asarray(flatten(masks[0][engine]), float)).min(axis=2) / 255 for engine in ENGINES}
            visible = np.logical_and.reduce([a > .999 for a in coverage.values()])
            sample = ndimage.binary_erosion(visible, iterations=2, border_value=0)
            ys, xs = np.where(sample)
            entry["visible_pixels"], entry["sample_pixels"] = int(visible.sum()), len(xs)
            if len(xs) < min_pixels:
                entry["reason"] = "Too few fully visible interior pixels after edge erosion."
                continue
            stride = max(1, math.ceil(len(xs) / max_samples))
            xs, ys = xs[::stride], ys[::stride]
            support = np.logical_or.reduce([a > 0 for a in coverage.values()])
            local_before = {engine: float(abs(actual - np.asarray(flatten(current_images[engine]), float))[support].mean()) for engine in ENGINES}
            entry["before"] = local_before
            paint_id = f"paint-refine-{index + 1}"
            while paint_id in identifiers or paint_id in added:
                paint_id += "-new"
            best = None
            for fit_error, gradient, fill, kind in fit_paints(xs + .5, ys + .5, actual[ys, xs], paint_id):
                candidate = copy.deepcopy(root)
                target = next(e for e in candidate.iter() if e.get("id") == identifier)
                for shape in shapes(target):
                    shape.set("fill", fill)
                if gradient is not None:
                    definitions = next((e for e in candidate if local_name(e.tag) == "defs"), None)
                    if definitions is None:
                        definitions = ET.Element(f"{{{NS}}}defs")
                        candidate.insert(0, definitions)
                    definitions.append(gradient)
                images = render(candidate)
                measurements = {engine: scores(source, image) for engine, image in images.items()}
                local_after = {engine: float(abs(actual - np.asarray(flatten(images[engine]), float))[support].mean()) for engine in ENGINES}
                failed = [engine for engine in ENGINES if
                          any(measurements[engine][key] > current_scores[engine][key] + 1e-9 for key in current_scores[engine]) or
                          local_after[engine] > local_before[engine] - min_improvement or
                          current_scores[engine]["white_mae"] - measurements[engine]["white_mae"] < min_improvement]
                decision = dict(model=kind, fit_mae=fit_error, after=measurements, local_mae=local_after,
                                status="rejected" if failed else "eligible", reason="No strict improvement without regression in " + ", ".join(failed) if failed else None)
                entry["candidates"].append(decision)
                rank = sum(measurements[e]["white_mae"] for e in ENGINES)
                if not failed and (best is None or rank < best[0]):
                    best = (rank, candidate, images, measurements, decision, gradient is not None)
            if best is None:
                entry["status"], entry["reason"] = "unchanged", "All paint candidates failed dual-renderer improvement checks."
                continue
            _, root, current_images, current_scores, selected, has_gradient = best
            if has_gradient:
                added.add(paint_id)
            mutable.add(identifier)
            for decision in entry["candidates"]:
                if decision["status"] == "eligible":
                    decision.update(status="not_selected", reason="Another safe candidate has lower combined renderer error.")
            selected.update(status="accepted", reason=None)
            entry.update(status="accepted", reason=None, model=selected["model"], after=selected["local_mae"])
            report["accepted"].append(identifier)
        if geometry_signature(root, set(targets), added) != before_signature:
            raise ValueError("Paint refinement unexpectedly changed geometry, hierarchy or text.")
        final = ET.tostring(root, encoding="unicode") if mutable else original
        candidate_path.write_text(final, encoding="utf-8")
        if audit_svg(candidate_path)["status"] != "PASS":
            raise ValueError("Refined SVG failed validation.")
        report.update(after=current_scores, geometry_preserved=True, status="IMPROVED" if mutable else "UNCHANGED")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            handle.write(final)
        with report_path.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-id", action="append", dest="target_ids")
    parser.add_argument("--max-objects", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(refine(args.source, args.svg, args.output, target_ids=args.target_ids, max_objects=args.max_objects), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
