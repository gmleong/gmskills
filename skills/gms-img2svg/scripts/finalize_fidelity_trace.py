#!/usr/bin/env python3
"""Finalize a direct trace with stable IDs and an honest provenance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageOps

from validate_svg import audit

SVG_NS = "http://www.w3.org/2000/svg"
VECTOR_TAGS = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_hex_color(value: str | None) -> tuple[int, int, int] | None:
    if not value or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return None
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path, help="validated direct-trace SVG")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, help="optional compare_render.py report")
    parser.add_argument("--parameters", default="{}", help="JSON object describing trace parameters")
    parser.add_argument(
        "--seal-seams",
        type=float,
        default=0,
        help="same-color stroke width used to cover cutout renderer seams; 0 disables",
    )
    parser.add_argument(
        "--flatten-neutral",
        action="store_true",
        help="collapse neutral antialias fragments to the darkest/lightest neutral; use only for flat artwork",
    )
    args = parser.parse_args()

    trace = args.trace.resolve()
    source = args.source.resolve()
    output = args.output.resolve()
    manifest = args.manifest.resolve()
    if output.exists() or manifest.exists():
        raise SystemExit("Output or manifest already exists; allocate new paths.")
    if audit(trace)["status"] != "PASS":
        raise SystemExit("Input trace did not pass SVG validation.")
    try:
        parameters = json.loads(args.parameters)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--parameters must be valid JSON: {exc}") from exc
    if not isinstance(parameters, dict):
        raise SystemExit("--parameters must decode to a JSON object.")
    if not 0 <= args.seal_seams <= 1:
        raise SystemExit("--seal-seams must be between 0 and 1.")

    ET.register_namespace("", SVG_NS)
    tree = ET.parse(trace)
    root = tree.getroot()
    width = root.get("width")
    height = root.get("height")
    if root.get("viewBox") is None and width and height:
        root.set("viewBox", f"0 0 {width} {height}")

    group = ET.Element(f"{{{SVG_NS}}}g", {"id": "fidelity-trace", "data-role": "subject"})
    movable = [child for child in list(root) if local_name(child.tag) != "defs"]
    for child in movable:
        root.remove(child)
        group.append(child)
    root.append(group)

    source_vectors = [element for element in group.iter() if local_name(element.tag) in VECTOR_TAGS]
    neutral_colors = []
    for element in source_vectors:
        color = parse_hex_color(element.get("fill"))
        if color and max(color) - min(color) <= 18:
            neutral_colors.append(color)
    dark_neutral = min(neutral_colors, key=sum) if neutral_colors else None
    light_neutral = max(neutral_colors, key=sum) if neutral_colors else None

    vector_count = 0
    command_count = 0
    for element in group.iter():
        tag = local_name(element.tag)
        if tag not in VECTOR_TAGS:
            continue
        vector_count += 1
        color = parse_hex_color(element.get("fill"))
        if args.flatten_neutral and color and max(color) - min(color) <= 18:
            target = dark_neutral if sum(color) / 3 < 160 else light_neutral
            if target:
                element.set("fill", f"#{target[0]:02X}{target[1]:02X}{target[2]:02X}")
        element.set("id", f"trace-fragment-{vector_count:04d}")
        element.set("data-role", "trace-fragment")
        if args.seal_seams and element.get("fill") not in {None, "none"}:
            element.set("stroke", element.get("fill", "none"))
            element.set("stroke-width", str(args.seal_seams))
            element.set("stroke-linejoin", "round")
            element.set("paint-order", "stroke fill")
        if tag == "path":
            command_count += len(re.findall(r"[AaCcHhLlMmQqSsTtVvZz]", element.get("d", "")))

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)
    report = audit(output)
    if report["status"] != "PASS":
        output.unlink(missing_ok=True)
        raise SystemExit("Finalized SVG failed validation: " + "; ".join(report["errors"]))

    with Image.open(source) as opened:
        source_size = ImageOps.exif_transpose(opened).size
    metrics = None
    if args.metrics:
        metrics_payload = json.loads(args.metrics.resolve().read_text(encoding="utf-8"))
        metrics = metrics_payload.get("metrics")
    payload = {
        "schema": "img2svg-fidelity-trace-1.0",
        "mode": "contour-faithful",
        "source": {"path": str(source), "sha256": sha256(source), "size": list(source_size)},
        "output": str(output),
        "parameters": parameters,
        "structure": {
            "root_group": "fidelity-trace",
            "vector_elements": vector_count,
            "path_commands": command_count,
            "semantic_granularity": "coarse",
            "seam_seal_width": args.seal_seams,
            "flatten_neutral": args.flatten_neutral,
        },
        "appearance_metrics": metrics,
        "limitations": [
            "Stable fragment IDs are editable but do not assert object-level semantics.",
            "Raster antialiasing cannot be reproduced identically by every SVG renderer.",
            "Higher contour fidelity increases path and anchor-point complexity.",
        ],
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
