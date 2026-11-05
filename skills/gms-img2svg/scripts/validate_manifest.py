#!/usr/bin/env python3
"""Validate img2svg live-text manifests."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

COLOR_PATTERN = re.compile(r"^(?:#[0-9a-fA-F]{3,8}|[a-zA-Z]+|none)$")
ANCHORS = {"start", "middle", "end"}


def finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def audit_manifest(path: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "file": str(path), "errors": [str(exc)], "warnings": []}

    if not isinstance(payload, dict):
        return {"status": "FAIL", "file": str(path), "errors": ["Manifest must be a JSON object."], "warnings": []}
    if payload.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'.")
    items = payload.get("text_elements")
    if not isinstance(items, list):
        errors.append("text_elements must be an array.")
        items = []

    identifiers: set[str] = set()
    required = ("text", "x", "y", "font_size", "paint_order")
    for index, item in enumerate(items):
        label = f"text_elements[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object.")
            continue
        for key in required:
            if key not in item:
                errors.append(f"{label}.{key} is required.")
        if not isinstance(item.get("text"), str) or not item.get("text", "").strip():
            errors.append(f"{label}.text must be a non-empty string.")
        for key in ("x", "y", "font_size", "paint_order"):
            if key in item and not finite_number(item[key]):
                errors.append(f"{label}.{key} must be a finite number.")
        if finite_number(item.get("paint_order")) and (
            float(item["paint_order"]) < 0 or not float(item["paint_order"]).is_integer()
        ):
            errors.append(f"{label}.paint_order must be a non-negative integer.")
        if finite_number(item.get("font_size")) and float(item["font_size"]) <= 0:
            errors.append(f"{label}.font_size must be positive.")
        identifier = item.get("id")
        if identifier is not None:
            if not isinstance(identifier, str) or not identifier.strip():
                errors.append(f"{label}.id must be a non-empty string when provided.")
            elif identifier in identifiers:
                errors.append(f"Duplicate id: {identifier}")
            else:
                identifiers.add(identifier)
        anchor = item.get("text_anchor", "start")
        if anchor not in ANCHORS:
            errors.append(f"{label}.text_anchor must be start, middle, or end.")
        color = item.get("fill", "#000000")
        if not isinstance(color, str) or not COLOR_PATTERN.fullmatch(color.strip()):
            errors.append(f"{label}.fill is not a supported color.")
        opacity = item.get("opacity", 1)
        if not finite_number(opacity) or not 0 <= float(opacity) <= 1:
            errors.append(f"{label}.opacity must be between 0 and 1.")
        bbox = item.get("bbox")
        if bbox is not None and (
            not isinstance(bbox, list) or len(bbox) != 4 or not all(finite_number(value) for value in bbox)
        ):
            errors.append(f"{label}.bbox must contain four finite numbers.")
        if "font_family" not in item:
            warnings.append(f"{label} has no font_family; Arial will be used.")

    return {
        "status": "PASS" if not errors else "FAIL",
        "file": str(path.resolve()),
        "text_elements": len(items),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    report = audit_manifest(args.manifest.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
