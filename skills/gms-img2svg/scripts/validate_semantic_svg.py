#!/usr/bin/env python3
"""Verify that required semantic objects map to editable SVG elements."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from validate_semantic_manifest import audit as audit_manifest
from validate_svg import audit as audit_svg


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


EXPECTED_TAGS = {
    "group": {"g"},
    "path": {"path"},
    "primitive": {"rect", "circle", "ellipse", "line", "polyline", "polygon"},
    "live_text": {"text", "tspan"},
}


def is_descendant(element: ET.Element, ancestor: ET.Element, parents: dict[int, ET.Element]) -> bool:
    current = parents.get(id(element))
    while current is not None:
        if current is ancestor:
            return True
        current = parents.get(id(current))
    return False


def audit(svg_path: Path, manifest_path: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    manifest_report = audit_manifest(manifest_path)
    svg_report = audit_svg(svg_path)
    if manifest_report["status"] != "PASS":
        errors.append("Semantic manifest validation failed.")
    if svg_report["status"] != "PASS":
        errors.append("SVG vector validation failed.")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        root = ET.parse(svg_path).getroot()
    except (OSError, json.JSONDecodeError, ET.ParseError) as exc:
        errors.append(str(exc))
        return {
            "status": "FAIL",
            "svg": str(svg_path),
            "manifest": str(manifest_path),
            "errors": list(dict.fromkeys(errors)),
            "warnings": warnings,
        }

    all_elements = list(root.iter())
    order_by_identity = {id(element): order for order, element in enumerate(all_elements)}
    parents = {id(child): parent for parent in all_elements for child in list(parent)}
    mapped: dict[str, list[tuple[str, int, ET.Element]]] = {}
    svg_ids: list[str] = []
    for order, element in enumerate(all_elements):
        if element.attrib.get("id"):
            svg_ids.append(element.attrib["id"])
        for key in (element.attrib.get("id"), element.attrib.get("data-source-id")):
            if key:
                mapped.setdefault(key, []).append((local_name(element.tag), order, element))

    duplicate_svg_ids = sorted(key for key, count in Counter(svg_ids).items() if count > 1)
    if duplicate_svg_ids:
        errors.append("SVG contains duplicate id values: " + ", ".join(duplicate_svg_ids))

    missing: list[str] = []
    text_mismatches: list[str] = []
    render_mismatches: list[str] = []
    role_mismatches: list[str] = []
    hierarchy_mismatches: list[str] = []
    ordered: list[tuple[float, int, str]] = []
    manifest_elements = {
        element.get("id"): element
        for element in manifest.get("elements", [])
        if isinstance(element, dict) and isinstance(element.get("id"), str)
    }
    for element in manifest.get("elements", []):
        if not isinstance(element, dict):
            continue
        element_id = element.get("id")
        matches = mapped.get(element_id, [])
        if not matches and element.get("required", True) is True:
            missing.append(str(element_id))
            continue
        if not matches:
            continue
        if element.get("role") == "text" and not any(tag in {"text", "tspan"} for tag, _, _ in matches):
            text_mismatches.append(str(element_id))
        expected = EXPECTED_TAGS.get(element.get("render_as"), set())
        if expected and not any(tag in expected for tag, _, _ in matches):
            render_mismatches.append(f"{element_id} expected {element.get('render_as')}")
        explicit_roles = [node.attrib.get("data-role") for _, _, node in matches if node.attrib.get("data-role")]
        if explicit_roles and element.get("role") not in explicit_roles:
            role_mismatches.append(f"{element_id} expected role {element.get('role')}")
        elif manifest.get("schema_version") == "1.1" and not explicit_roles:
            warnings.append(f"{element_id} has no data-role metadata in SVG.")
        parent_id = element.get("parent_id")
        if parent_id and mapped.get(parent_id):
            if not any(
                child_node is parent_node or is_descendant(child_node, parent_node, parents)
                for _, _, child_node in matches
                for _, _, parent_node in mapped[parent_id]
            ):
                hierarchy_mismatches.append(f"{element_id} is not nested under {parent_id}")
        z_index = element.get("z_index")
        if isinstance(z_index, (int, float)):
            ordered.append((float(z_index), min(order for _, order, _ in matches), str(element_id)))

    if missing:
        errors.append("Required semantic elements missing from SVG: " + ", ".join(missing))
    if text_mismatches:
        errors.append("Semantic text elements are not live SVG text: " + ", ".join(text_mismatches))
    if render_mismatches:
        errors.append("Semantic elements use the wrong SVG representation: " + ", ".join(render_mismatches))
    if role_mismatches:
        errors.append("SVG data-role values conflict with the manifest: " + ", ".join(role_mismatches))
    if hierarchy_mismatches:
        errors.append("Semantic hierarchy does not match SVG nesting: " + ", ".join(hierarchy_mismatches))

    paint_orders = [order for _, order, _ in sorted(ordered, key=lambda item: (item[0], item[1]))]
    if paint_orders != sorted(paint_orders):
        errors.append("Mapped semantic elements do not follow manifest z_index paint order.")

    def paint_span(identifier: str) -> tuple[int, int] | None:
        matches = mapped.get(identifier, [])
        if not matches:
            return None
        orders: list[int] = []
        for _, order, node in matches:
            orders.append(order)
            orders.extend(order_by_identity[id(descendant)] for descendant in node.iter())
        return min(orders), max(orders)

    for element_id, element in manifest_elements.items():
        element_span = paint_span(element_id)
        if not element_span:
            continue
        for occluder_id in element.get("occluded_by", []):
            occluder_span = paint_span(occluder_id)
            if occluder_span and occluder_span[1] <= element_span[1]:
                errors.append(f"Occluder {occluder_id} must paint after {element_id}.")

    for relationship in manifest.get("relationships", []):
        if not isinstance(relationship, dict):
            continue
        kind = relationship.get("type")
        source_id = relationship.get("from")
        target_id = relationship.get("to")
        if kind == "contains" and mapped.get(source_id) and mapped.get(target_id):
            if not any(
                is_descendant(child, parent, parents)
                for _, _, parent in mapped[source_id]
                for _, _, child in mapped[target_id]
            ):
                errors.append(f"Relationship contains({source_id}, {target_id}) is not represented by SVG nesting.")
        if kind == "part_of" and mapped.get(source_id) and mapped.get(target_id):
            if not any(
                is_descendant(child, parent, parents)
                for _, _, child in mapped[source_id]
                for _, _, parent in mapped[target_id]
            ):
                errors.append(f"Relationship part_of({source_id}, {target_id}) is not represented by SVG nesting.")
        if kind == "labels" and manifest_elements.get(source_id, {}).get("role") != "text":
            errors.append(f"Relationship labels({source_id}, {target_id}) must start from a text element.")
        if kind == "points_to" and manifest_elements.get(source_id, {}).get("role") not in {"arrow", "connector"}:
            errors.append(f"Relationship points_to({source_id}, {target_id}) must start from an arrow or connector.")
        if kind == "occludes":
            source_span = paint_span(source_id)
            target_span = paint_span(target_id)
            if source_span and target_span and source_span[1] <= target_span[1]:
                errors.append(f"Relationship occludes({source_id}, {target_id}) has the wrong paint order.")

    return {
        "status": "PASS" if not errors else "FAIL",
        "svg": str(svg_path.resolve()),
        "manifest": str(manifest_path.resolve()),
        "required_elements": manifest_report.get("required_elements", 0),
        "mapped_required_elements": manifest_report.get("required_elements", 0) - len(missing),
        "checked_hierarchy_elements": sum(1 for element in manifest_elements.values() if element.get("parent_id")),
        "checked_relationships": len(manifest.get("relationships", [])),
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings + manifest_report.get("warnings", []) + svg_report.get("warnings", []))),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    report = audit(args.svg.resolve(), args.manifest.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
