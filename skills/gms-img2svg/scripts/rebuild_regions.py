#!/usr/bin/env python3
"""Rebuild reviewed colour regions with shared cubic boundaries and native fills.

The plan supplies palette colours and one interior seed per visible region;
it is human-reviewed geometry guidance, not an automatic semantic recognizer.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage as ndi
from skimage.filters import sobel
from skimage.segmentation import watershed
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path

from compare_render import render_rgba, svg_complexity
from refine_svg import compact_svg, fit_paints, scores
from validate_svg import audit
from validate_semantic_svg import audit as audit_semantic

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def tag(name):
    return f"{{{NS}}}{name}"


def encode_regions(count):
    if not 1 <= count <= 255:
        raise ValueError("Use 1..255 reviewed regions.")
    # Every channel is injective modulo 256; never quantize or merge these IDs.
    return np.array([[i * 67 % 256, i * 131 % 256, i * 193 % 256]
                     for i in range(count + 1)], dtype=np.uint8)


def segment(source, plan, scale):
    rgb = np.asarray(source.convert("RGB"), dtype=float)
    h, w = rgb.shape[:2]
    palette = np.asarray(plan["palette"], dtype=float)
    if palette.ndim != 2 or palette.shape[1] != 3 or not np.isfinite(palette).all() or np.any((palette < 0) | (palette > 255)):
        raise ValueError("Palette must contain finite RGB triples in 0..255.")
    classes = np.zeros((h, w), dtype=np.int32)
    best = np.full((h, w), np.inf)
    for i, colour in enumerate(palette):
        error = ((rgb - colour) ** 2).sum(2)
        take = error < best
        classes[take], best[take] = i, error[take]
    seeds = np.zeros((h, w), np.int32)
    means, core_cache = [], {}
    for i, part in enumerate(plan["parts"], 1):
        x, y = part["seed"]
        ci, erosion = part["palette_index"], part.get("core_erosion", 2)
        if not (isinstance(x, int) and isinstance(y, int) and 0 <= x < w and 0 <= y < h
                and isinstance(ci, int) and 0 <= ci < len(palette)
                and isinstance(erosion, int) and 0 <= erosion <= 10):
            raise ValueError(f"Invalid seed/palette/erosion: {part['id']}")
        key = ci, erosion
        if key not in core_cache:
            mask = classes == ci
            if erosion:
                mask = ndi.binary_erosion(mask, iterations=erosion)
            core_cache[key] = ndi.label(mask)[0]
        labels = core_cache[key]
        if labels[y, x] == 0:
            raise ValueError(f"Seed is outside its solid colour core: {part['id']}")
        core = labels == labels[y, x]
        if np.any(seeds[core]):
            raise ValueError(f"Seeds select the same core: {part['id']}")
        seeds[core] = i
        means.append(np.median(rgb[core], axis=0))
    gradient = np.sqrt(sum(sobel(rgb[:, :, c]) ** 2 for c in range(3)))
    labels = watershed(gradient, seeds)
    large = np.asarray(source.convert("RGB").resize((w * scale, h * scale), Image.Resampling.BICUBIC), float)
    best = np.full(large.shape[:2], np.inf)
    regions = np.zeros(large.shape[:2], np.uint16)
    # ponytail: fixed 3px search band suits flat art; textured inputs need a different segmentation model.
    for i, colour in enumerate(means, 1):
        allowed = ndi.binary_dilation(labels == i, iterations=3)
        allowed = np.asarray(Image.fromarray(allowed).resize((w * scale, h * scale), Image.Resampling.NEAREST))
        error = ((large - colour) ** 2).sum(2)
        take = allowed & (error < best)
        regions[take], best[take] = i, error[take]
    if np.any(regions == 0):
        raise ValueError("Region assignment left uncovered pixels.")
    return regions, np.asarray(means), rgb


def shared_cubics(root):
    """Count exact reversed cubic reuse across distinct paths (not a visual guess)."""
    seen, total, shared = {}, 0, 0
    for index, node in enumerate(root.iter(tag("path"))):
        pen = RecordingPen()
        parse_path(node.get("d"), pen)
        for op, points in pen.value:
            if op == "moveTo":
                last = points[0]
            elif op == "lineTo":
                last = points[0]
            elif op == "curveTo":
                curve = tuple(tuple(round(v, 6) for v in p) for p in (last, *points))
                reverse = curve[::-1]
                if reverse in seen and seen[reverse] != index:
                    shared += 1
                seen[curve] = index
                total += 1
                last = points[-1]
    return {"cubic_occurrences": total, "reversed_shared_pairs": shared}


def rebuild(source_path, plan_path, output_dir, *, scale=3, tolerance=0.6):
    if output_dir.exists():
        raise ValueError("Output directory exists; choose a new directory.")
    if scale not in (1, 2, 3, 4) or not np.isfinite(tolerance) or not 0 < tolerance * scale <= 5:
        raise ValueError("Scale must be 1..4 and scaled tolerance must be in (0, 5].")
    plan = json.loads(plan_path.read_text())
    if not isinstance(plan, dict) or plan.get("review_status", "reviewed") != "reviewed":
        raise ValueError("Region draft needs visual review before reconstruction.")
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != plan.get("source_sha256"):
        raise ValueError("Plan source checksum differs; review the plan against this image.")
    ids = [p["id"] for p in plan["parts"]]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-z][a-z0-9-]*", i) for i in ids):
        raise ValueError("Region IDs must be unique lowercase names.")
    colours = encode_regions(len(ids))
    with Image.open(source_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGBA")
    if source.getchannel("A").getextrema() != (255, 255):
        raise ValueError("This region workflow requires opaque flat artwork.")
    background = [i for i, p in enumerate(plan["parts"], 1) if p["role"] == "background"]
    if not background:
        raise ValueError("Plan must identify the visible background.")
    regions, means, rgb = segment(source, plan, scale)
    options = dict(clustering="color-cluster", hierarchical="cutout", mode="spline",
                   simplify=tolerance * scale, maxColors=256, colorPrecision=8,
                   layerDifference=0, filterSpeckle=0, optimize=0, pathPrecision=3)
    with tempfile.TemporaryDirectory(prefix="img2svg-regions-") as temporary:
        stage = Path(temporary)
        Image.fromarray(colours[regions]).save(stage / "labels.png")
        runtime = Path(__file__).with_name("vtracer_smooth_runtime.cjs")
        process = subprocess.run(["node", str(runtime), str(stage / "labels.png"), str(stage / "trace.svg"), json.dumps(options)], capture_output=True, text=True)
        if process.returncode:
            raise ValueError("Region tracer failed: " + process.stderr.strip())
        traced = ET.parse(stage / "trace.svg").getroot()
        topology = shared_cubics(traced)
        root = ET.Element(tag("svg"), {"width": str(source.width), "height": str(source.height),
                          "viewBox": f"0 0 {source.width} {source.height}"})
        definitions = ET.SubElement(root, tag("defs"))
        bg = np.median(means[np.array(background) - 1], axis=0)
        ET.SubElement(root, tag("rect"), {"id": "canvas-background", "data-role": "background", "width": str(source.width), "height": str(source.height), "fill": "#%02x%02x%02x" % tuple(bg.astype(int))})
        lookup = {"#%02X%02X%02X" % tuple(c): i for i, c in enumerate(colours) if i}
        groups, records = {}, []
        native_regions = regions[scale // 2::scale, scale // 2::scale]
        for i, part in enumerate(plan["parts"], 1):
            if i in background:
                continue
            sel = native_regions == i
            ys, xs = np.where(sel)
            if not len(xs):
                raise ValueError(f"Required region disappeared: {part['id']}")
            interior = ndi.binary_erosion(sel, iterations=2)
            if interior.sum() < 10:
                interior = sel
            y, x = np.where(interior)
            models = fit_paints(x + .5, y + .5, rgb[interior], f"paint-{part['id']}")
            flat = next(m for m in models if m[3] == "flat")
            model = models[0] if flat[0] - models[0][0] > .15 else flat
            error, definition, fill, kind = model
            if definition is not None:
                definitions.append(definition)
            group = ET.SubElement(root, tag("g"), {"id": part["id"], "data-role": part["role"], "fill": fill})
            groups[i] = group
            records.append(dict(id=part["id"], role=part["role"], render_as="group", required=True,
                                bbox=[int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)],
                                z_index=len(records) + 1, description=part["description"], confidence=part["confidence"],
                                evidence=part["evidence"], paint=kind, interior_mae=round(error, 4)))
        for node in traced:
            if node.tag != tag("path"):
                continue
            i = lookup.get(node.get("fill", "").upper())
            if i is None:
                raise ValueError("Tracer merged region IDs; refusing a miscoloured reconstruction.")
            if i in background:
                continue
            pen = SVGPathPen(None)
            parse_path(node.get("d"), TransformPen(pen, (1 / scale, 0, 0, 1 / scale, 0, 0)))
            group = groups[i]
            ET.SubElement(group, tag("path"), {"id": f"{group.get('id')}-outline-{len(group)+1}", "d": pen.getCommands()})
        if any(len(group) == 0 for group in groups.values()):
            raise ValueError("Tracer dropped a required region.")
        flat_root = copy.deepcopy(root)
        for i, group in groups.items():
            flat_group = next(n for n in flat_root if n.get("id") == group.get("id"))
            flat_group.set("fill", "#%02x%02x%02x" % tuple(means[i - 1].astype(int)))
        # Choose minimal seam coverage by both independent renderers at native size.
        candidates = []
        for stroke in (0, .2, .4):
            for group in groups.values():
                group.set("stroke", group.get("fill"))
                group.set("stroke-width", str(stroke))
                group.set("stroke-linejoin", "round")
            candidate = stage / "candidate.svg"
            candidate.write_text(compact_svg(ET.tostring(root, encoding="unicode"), 3))
            measured = {engine: scores(source, render_rgba(candidate, *source.size, renderer=engine)) for engine in ("cairosvg", "resvg")}
            candidates.append((stroke, measured, candidate.read_text()))
        # A candidate must improve both engines over the stroke-free version.
        base = candidates[0][1]
        accepted = [c for c in candidates if all(c[1][e]["white_mae"] <= base[e]["white_mae"] and c[1][e]["black_mae"] <= base[e]["black_mae"] for e in base)]
        stroke, measured, final = min(accepted, key=lambda c: sum(s["white_mae"] for s in c[1].values()))
        candidate.write_text(final)
        if audit(candidate)["status"] != "PASS":
            raise ValueError("Reconstruction failed vector validation.")
        manifest = dict(schema_version="1.1", source=str(source_path.resolve()), domain=plan["domain"],
                        canvas=dict(width=source.width, height=source.height), elements=[dict(id="canvas-background", role="background", render_as="primitive", description="Opaque canvas background and visible openings", bbox=[0, 0, source.width, source.height], z_index=0, confidence=.99, evidence=["Opaque source background"]), *records])
        staged_manifest = stage / "semantic-manifest.json"
        staged_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
        validation = audit_semantic(candidate, staged_manifest)
        if validation["status"] != "PASS":
            raise ValueError("Semantic validation failed: " + "; ".join(validation["errors"]))
        output_dir.mkdir(parents=True)
        output = output_dir / "reconstructed.svg"
        output.write_text(final)
        (output_dir / "flat.svg").write_text(compact_svg(ET.tostring(flat_root, encoding="unicode"), 3))
        wire = ET.fromstring(final)
        for group in wire.findall(tag("g")):
            group.set("fill", "none")
            group.set("stroke", "#455c91")
            group.set("stroke-width", ".65")
        (output_dir / "wireframe.svg").write_text(ET.tostring(wire, encoding="unicode"))
        (output_dir / "shared-boundaries.svg").write_bytes((stage / "trace.svg").read_bytes())
        (output_dir / "semantic-manifest.json").write_bytes(staged_manifest.read_bytes())
    report = dict(source=str(source_path.resolve()), plan=str(plan_path.resolve()), options=options, scale=scale,
                  tolerance_source_px=tolerance, topology_before_background_removal=topology,
                  complexity=svg_complexity(output), seam_stroke_width=stroke, metrics=measured,
                  seam_candidates=[dict(stroke_width=s, metrics=m) for s, m, _ in candidates], limitations=plan.get("notes", []))
    (output_dir / "reconstruction.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=3)
    parser.add_argument("--tolerance", type=float, default=.6)
    args = parser.parse_args()
    print(json.dumps(rebuild(args.source, args.plan, args.output_dir, scale=args.scale, tolerance=args.tolerance), indent=2))
