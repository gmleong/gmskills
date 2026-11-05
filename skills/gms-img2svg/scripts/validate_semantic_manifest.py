#!/usr/bin/env python3
"""Validate the semantic object inventory used for SVG reconstruction."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
ROLES = {
    "background",
    "subject",
    "organelle",
    "connector",
    "arrow",
    "frame",
    "axis",
    "legend",
    "text",
    "decoration",
    "other",
}
RENDER_TYPES = {"group", "path", "primitive", "live_text"}
SCHEMA_VERSIONS = {"1.0", "1.1"}
DOMAINS = {"scientific", "cell", "cartoon", "mixed"}
RELATIONSHIP_TYPES = {
    "aligned_with",
    "connects",
    "contains",
    "labels",
    "occludes",
    "overlaps",
    "part_of",
    "points_to",
    "repeated_with",
}


def finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def audit(path: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "file": str(path), "errors": [str(exc)], "warnings": []}

    schema_version = payload.get("schema_version")
    if schema_version not in SCHEMA_VERSIONS:
        errors.append("schema_version must be '1.0' or '1.1'.")
    strict_semantics = schema_version == "1.1"
    if strict_semantics and payload.get("domain") not in DOMAINS:
        errors.append("domain must be scientific, cell, cartoon, or mixed for schema_version 1.1.")

    canvas = payload.get("canvas")
    width = canvas.get("width") if isinstance(canvas, dict) else None
    height = canvas.get("height") if isinstance(canvas, dict) else None
    if not finite_number(width) or width <= 0 or not finite_number(height) or height <= 0:
        errors.append("canvas.width and canvas.height must be positive finite numbers.")

    elements = payload.get("elements")
    if not isinstance(elements, list) or not elements:
        errors.append("elements must be a non-empty array.")
        elements = []

    seen: set[str] = set()
    elements_by_id: dict[str, dict] = {}
    required = 0
    text_count = 0
    previous_z: float | None = None
    parent_references: dict[str, str] = {}
    occlusion_references: dict[str, list[str]] = {}
    for index, element in enumerate(elements):
        label = f"elements[{index}]"
        if not isinstance(element, dict):
            errors.append(f"{label} must be an object.")
            continue
        element_id = element.get("id")
        if not isinstance(element_id, str) or not ID_PATTERN.fullmatch(element_id):
            errors.append(f"{label}.id must be a stable SVG-compatible identifier.")
        elif element_id in seen:
            errors.append(f"Duplicate element id: {element_id}")
        else:
            seen.add(element_id)
            elements_by_id[element_id] = element

        role = element.get("role")
        render_as = element.get("render_as")
        if role not in ROLES:
            errors.append(f"{label}.role is unsupported: {role!r}")
        if render_as not in RENDER_TYPES:
            errors.append(f"{label}.render_as is unsupported: {render_as!r}")
        if role == "text":
            text_count += 1
            if render_as != "live_text":
                errors.append(f"{label} has role 'text' and must render_as 'live_text'.")

        description = element.get("description")
        if strict_semantics and (not isinstance(description, str) or not description.strip()):
            errors.append(f"{label}.description must be a non-empty string for schema_version 1.1.")

        confidence = element.get("confidence")
        if strict_semantics:
            if not finite_number(confidence) or not 0 <= confidence <= 1:
                errors.append(f"{label}.confidence must be a finite number from 0 to 1.")
            elif element.get("required", True) is True and confidence < 0.7:
                warnings.append(f"{element_id} is required but has confidence below 0.7; review it visually.")
            evidence = element.get("evidence")
            if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence):
                errors.append(f"{label}.evidence must be a non-empty array of strings.")

        parent_id = element.get("parent_id")
        if parent_id is not None:
            if not isinstance(parent_id, str):
                errors.append(f"{label}.parent_id must be a string when present.")
            elif isinstance(element_id, str):
                parent_references[element_id] = parent_id

        occluded_by = element.get("occluded_by", [])
        if not isinstance(occluded_by, list) or not all(isinstance(item, str) for item in occluded_by):
            errors.append(f"{label}.occluded_by must be an array of ids when present.")
        elif isinstance(element_id, str):
            occlusion_references[element_id] = occluded_by

        bbox = element.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4 or not all(finite_number(value) for value in bbox):
            errors.append(f"{label}.bbox must contain four finite numbers.")
        elif finite_number(width) and finite_number(height):
            x, y, box_width, box_height = bbox
            if x < 0 or y < 0 or box_width < 0 or box_height < 0:
                errors.append(f"{label}.bbox cannot contain negative coordinates or dimensions.")
            elif x + box_width > width + 1e-6 or y + box_height > height + 1e-6:
                errors.append(f"{label}.bbox extends outside the canvas.")

        z_index = element.get("z_index")
        if not finite_number(z_index):
            errors.append(f"{label}.z_index must be a finite number.")
        else:
            if previous_z is not None and z_index < previous_z:
                warnings.append("elements are not listed in ascending z_index order.")
            previous_z = z_index

        if element.get("required", True) is True:
            required += 1
        elif element.get("required") is not False:
            errors.append(f"{label}.required must be true or false when present.")

    relationships = payload.get("relationships", [])
    if not isinstance(relationships, list):
        errors.append("relationships must be an array when present.")
    else:
        for index, relationship in enumerate(relationships):
            label = f"relationships[{index}]"
            if not isinstance(relationship, dict):
                errors.append(f"{label} must be an object.")
                continue
            for endpoint in ("from", "to"):
                if relationship.get(endpoint) not in seen:
                    errors.append(f"{label}.{endpoint} references an unknown element id.")
            if not isinstance(relationship.get("type"), str) or not relationship["type"].strip():
                errors.append(f"{label}.type must be a non-empty string.")
            elif strict_semantics and relationship["type"] not in RELATIONSHIP_TYPES:
                errors.append(f"{label}.type is unsupported for schema_version 1.1: {relationship['type']!r}")

    for child_id, parent_id in parent_references.items():
        if parent_id not in seen:
            errors.append(f"Element {child_id} references unknown parent_id {parent_id}.")
        elif child_id == parent_id:
            errors.append(f"Element {child_id} cannot be its own parent.")
        elif elements_by_id.get(parent_id, {}).get("render_as") != "group":
            errors.append(f"Element {child_id} parent {parent_id} must render_as 'group'.")
    for element_id, occluders in occlusion_references.items():
        for occluder in occluders:
            if occluder not in seen:
                errors.append(f"Element {element_id} references unknown occluder {occluder}.")
            elif occluder == element_id:
                errors.append(f"Element {element_id} cannot occlude itself.")

    for start in parent_references:
        chain: set[str] = set()
        current = start
        while current in parent_references:
            if current in chain:
                errors.append(f"Parent hierarchy contains a cycle involving {current}.")
                break
            chain.add(current)
            current = parent_references[current]

    return {
        "status": "PASS" if not errors else "FAIL",
        "file": str(path.resolve()),
        "elements": len(elements),
        "required_elements": required,
        "text_elements": text_count,
        "schema_version": schema_version,
        "domain": payload.get("domain"),
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    report = audit(args.manifest.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
