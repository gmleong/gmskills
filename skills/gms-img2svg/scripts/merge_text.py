#!/usr/bin/env python3
"""Merge a validated text manifest into an SVG as editable text."""

from __future__ import annotations

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from validate_manifest import audit_manifest
from validate_svg import audit as audit_svg

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def fmt(value: object) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.6f}".rstrip("0").rstrip(".")


def build_text(item: dict, fallback_id: str) -> ET.Element:
    x = fmt(item["x"])
    y = fmt(item["y"])
    font_size = float(item["font_size"])
    line_height = float(item.get("line_height", 1.2))
    identifier = str(item.get("id") or fallback_id)
    attrs = {
        "id": identifier,
        "x": x,
        "y": y,
        "font-family": str(item.get("font_family", "Arial")),
        "font-size": fmt(font_size),
        "font-weight": str(item.get("font_weight", "400")),
        "font-style": str(item.get("font_style", "normal")),
        "fill": str(item.get("fill", "#000000")),
        "opacity": fmt(item.get("opacity", 1)),
        "text-anchor": str(item.get("text_anchor", "start")),
        "letter-spacing": fmt(item.get("letter_spacing", 0)),
        "data-img2svg-live-text": "true",
    }
    rotation = float(item.get("rotation", 0))
    if rotation:
        attrs["transform"] = f"rotate({fmt(rotation)} {x} {y})"
    bbox = item.get("bbox")
    if bbox:
        attrs["data-source-bbox"] = " ".join(fmt(value) for value in bbox)

    element = ET.Element(f"{{{SVG_NS}}}text", attrs)
    lines = str(item["text"]).split("\n")
    if len(lines) == 1:
        element.text = lines[0]
        return element
    for index, line in enumerate(lines):
        tspan_attrs = {"x": x, "dy": "0" if index == 0 else fmt(font_size * line_height)}
        tspan = ET.SubElement(element, f"{{{SVG_NS}}}tspan", tspan_attrs)
        tspan.text = line
    return element


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = args.svg.resolve()
    manifest_path = args.manifest.resolve()
    output = args.output.resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"Output already exists: {output}. Allocate a new name or pass --force.")
    manifest_report = audit_manifest(manifest_path)
    if manifest_report["status"] != "PASS":
        raise SystemExit("Invalid text manifest: " + "; ".join(manifest_report["errors"]))
    svg_report = audit_svg(source)
    if svg_report["status"] != "PASS":
        raise SystemExit("Invalid input SVG: " + "; ".join(svg_report["errors"]))

    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    tree = ET.parse(source)
    root = tree.getroot()
    additions: list[tuple[int, ET.Element]] = []
    for index, item in enumerate(payload["text_elements"]):
        additions.append((int(item["paint_order"]), build_text(item, f"img2svg-text-{index + 1}")))
    offset = 0
    for paint_order, element in sorted(additions, key=lambda pair: pair[0]):
        insertion = max(0, min(len(root), paint_order + offset))
        root.insert(insertion, element)
        offset += 1
    root.set("data-img2svg-text-manifest", manifest_path.name)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=output.parent, suffix=".svg.tmp") as handle:
        temporary = Path(handle.name)
        tree.write(handle, encoding="utf-8", xml_declaration=True)
    report = audit_svg(temporary, require_live_text=bool(additions))
    if report["status"] != "PASS":
        temporary.unlink(missing_ok=True)
        raise SystemExit("Merged SVG failed validation: " + "; ".join(report["errors"]))
    temporary.replace(output)
    print(json.dumps({"ok": True, "output": str(output), "live_text_elements": len(additions)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
