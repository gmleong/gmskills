#!/usr/bin/env python3
"""Remove path subpaths wholly contained in a rectangular SVG region."""

from __future__ import annotations

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.svgLib.path.parser import parse_path

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def split_subpaths(data: str) -> list[RecordingPen]:
    source = RecordingPen()
    parse_path(data, source)
    result: list[RecordingPen] = []
    current: RecordingPen | None = None
    for command, points in source.value:
        if command == "moveTo":
            if current and current.value:
                result.append(current)
            current = RecordingPen()
        if current is None:
            continue
        getattr(current, command)(*points)
    if current and current.value:
        result.append(current)
    return result


def bounds(pen: RecordingPen) -> tuple[float, float, float, float] | None:
    target = BoundsPen(None)
    pen.replay(target)
    return target.bounds


def serialize(subpaths: list[RecordingPen]) -> str:
    target = SVGPathPen(None)
    for subpath in subpaths:
        subpath.replay(target)
    return target.getCommands()


def contained(box: tuple[float, float, float, float] | None, region: tuple[float, float, float, float]) -> bool:
    if box is None:
        return False
    min_x, min_y, max_x, max_y = box
    x, y, width, height = region
    return min_x >= x and min_y >= y and max_x <= x + width and max_y <= y + height


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    parser.add_argument("--rect", type=float, nargs=4, metavar=("X", "Y", "WIDTH", "HEIGHT"), required=True)
    parser.add_argument("--cover-fill", help="Optionally cover the region after removal with this SVG fill color.")
    parser.add_argument("--group-id", help="Optionally wrap direct root-level artwork paths and cover in one named group.")
    parser.add_argument("--group-role", default="subject", help="data-role used with --group-id (default: subject).")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.svg.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Output already exists: {output}")
    tree = ET.parse(source)
    root = tree.getroot()
    parents = {child: parent for parent in root.iter() for child in parent}
    removed_subpaths = 0
    removed_paths = 0
    for element in list(root.iter()):
        if local_name(element.tag) != "path" or not element.attrib.get("d"):
            continue
        pieces = split_subpaths(element.attrib["d"])
        kept = [piece for piece in pieces if not contained(bounds(piece), tuple(args.rect))]
        removed_subpaths += len(pieces) - len(kept)
        if not kept:
            parent = parents.get(element)
            if parent is not None:
                parent.remove(element)
                removed_paths += 1
        elif len(kept) != len(pieces):
            element.set("d", serialize(kept))

    cover = None
    if args.cover_fill:
        x, y, width, height = args.rect
        cover = ET.Element(
            f"{{{SVG_NS}}}rect",
            {
                "id": "img2svg-region-cover",
                "x": f"{x:g}",
                "y": f"{y:g}",
                "width": f"{width:g}",
                "height": f"{height:g}",
                "fill": args.cover_fill,
            },
        )

    if args.group_id:
        group = ET.Element(
            f"{{{SVG_NS}}}g",
            {"id": args.group_id, "data-role": args.group_role},
        )
        for child in list(root):
            if local_name(child.tag) == "path":
                root.remove(child)
                group.append(child)
        if cover is not None:
            group.append(cover)
            cover = None
        root.append(group)
    if cover is not None:
        root.append(cover)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=output.parent, suffix=".svg.tmp") as handle:
        temporary = Path(handle.name)
        tree.write(handle, encoding="utf-8", xml_declaration=True)
    temporary.replace(output)
    print(json.dumps({"ok": True, "output": str(output), "removed_subpaths": removed_subpaths, "removed_paths": removed_paths}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
