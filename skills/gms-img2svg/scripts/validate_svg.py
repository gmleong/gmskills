#!/usr/bin/env python3
"""Validate that an SVG contains editable local vector content only."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

VECTOR_TAGS = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
FORBIDDEN_TAGS = {"image", "script", "style", "foreignObject", "iframe", "object", "embed"}
HREF_NAMES = {"href", "{http://www.w3.org/1999/xlink}href"}
NUMBER_PATTERN = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def finite_numbers(value: str) -> bool:
    lowered = value.lower()
    if "nan" in lowered or "infinity" in lowered or "inf" in lowered:
        return False
    return all(math.isfinite(float(item)) for item in NUMBER_PATTERN.findall(value))


def audit(path: Path, require_live_text: bool = False) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    counts: Counter[str] = Counter()
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return {"status": "FAIL", "file": str(path), "errors": [str(exc)], "warnings": []}

    if local_name(root.tag) != "svg":
        errors.append("Root element is not <svg>.")

    for element in root.iter():
        name = local_name(element.tag)
        counts[name] += 1
        if name in FORBIDDEN_TAGS:
            errors.append(f"Forbidden <{name}> element found.")
        for key, value in element.attrib.items():
            attr = local_name(key).lower()
            normalized = value.strip().lower()
            if attr.startswith("on"):
                errors.append(f"Event-handler attribute {attr} is not allowed.")
            if key in HREF_NAMES or attr == "href":
                if normalized and not normalized.startswith("#"):
                    errors.append(f"External reference is not allowed: {value[:80]}")
            if "data:" in normalized or ("url(" in normalized and "url(#" not in normalized.replace(" ", "")):
                errors.append(f"Embedded or external resource is not allowed in {attr}.")
            if attr in {"d", "points", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "width", "height", "viewbox", "transform"}:
                if not finite_numbers(value):
                    errors.append(f"Invalid numeric value in {attr}.")

    vector_count = sum(counts[tag] for tag in VECTOR_TAGS)
    if vector_count == 0:
        errors.append("No editable vector geometry found.")
    if require_live_text and counts["text"] == 0:
        errors.append("Live editable text is required but no <text> element was found.")
    if "viewBox" not in root.attrib and not ({"width", "height"} <= set(root.attrib)):
        warnings.append("SVG has neither a viewBox nor explicit width and height.")

    return {
        "status": "PASS" if not errors else "FAIL",
        "file": str(path.resolve()),
        "vector_elements": vector_count,
        "live_text_elements": counts["text"],
        "errors": list(dict.fromkeys(errors)),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    parser.add_argument("--require-live-text", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit(args.svg.resolve(), args.require_live_text)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.stdout = None
        raise SystemExit(1)
