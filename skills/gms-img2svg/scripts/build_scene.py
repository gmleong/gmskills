#!/usr/bin/env python3
"""Build editable SVG from reviewed schema 1.1 geometry declarations.

An element's geometry is {tag, attrs, text?, children?}; children are allowed
only on g/text/tspan. Semantic nesting comes from parent_id. Top-level gradients
contain {id, tag, attrs, stops: [{offset, stop-color, stop-opacity?}, ...]}.
No geometry, wording, or semantic identity is inferred by this compiler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageColor, ImageOps
from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path.parser import parse_path

from validate_semantic_manifest import ID_PATTERN, audit as audit_manifest
from validate_semantic_svg import EXPECTED_TAGS, audit as audit_semantics
from validate_svg import audit as audit_svg

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NUMBER_RE = re.compile(NUMBER)
COMMON = set("fill stroke stroke-width opacity fill-opacity stroke-opacity fill-rule stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset transform".split())
TEXT = set("x y dx dy rotate font-family font-size font-weight font-style text-anchor dominant-baseline letter-spacing word-spacing textLength lengthAdjust".split())
SHAPE = {
    "g": set(), "path": {"d"}, "rect": set("x y width height rx ry".split()),
    "circle": {"cx", "cy", "r"}, "ellipse": {"cx", "cy", "rx", "ry"},
    "line": {"x1", "y1", "x2", "y2"}, "polyline": {"points"}, "polygon": {"points"},
    "text": TEXT, "tspan": TEXT,
}
GRADIENT = {
    "linearGradient": set("x1 y1 x2 y2 gradientUnits gradientTransform spreadMethod".split()),
    "radialGradient": set("cx cy r fx fy fr gradientUnits gradientTransform spreadMethod".split()),
}
ENUMS = {
    "fill-rule": {"nonzero", "evenodd"}, "stroke-linecap": {"butt", "round", "square"},
    "stroke-linejoin": {"miter", "round", "bevel"}, "font-style": {"normal", "italic", "oblique"},
    "font-weight": {"normal", "bold", "bolder", "lighter", *(str(n) for n in range(100, 1000, 100))},
    "text-anchor": {"start", "middle", "end"}, "lengthAdjust": {"spacing", "spacingAndGlyphs"},
    "dominant-baseline": {"auto", "alphabetic", "middle", "central", "hanging", "text-before-edge", "text-after-edge", "ideographic"},
    "gradientUnits": {"userSpaceOnUse", "objectBoundingBox"}, "spreadMethod": {"pad", "reflect", "repeat"},
}


def scalar(value, *, percent=False) -> float:
    raw = str(value)
    if isinstance(value, bool) or not re.fullmatch(NUMBER + ("%?" if percent else ""), raw):
        raise ValueError(f"Expected a finite number, got {value!r}")
    number = float(raw.rstrip("%")) / (100 if raw.endswith("%") else 1)
    if not math.isfinite(number):
        raise ValueError("Non-finite number")
    return number


def numbers(value: str) -> list[float]:
    if not isinstance(value, str) or not value.strip() or re.sub(NUMBER, "", value).strip(" ,\t\r\n"):
        raise ValueError(f"Invalid numeric list: {value!r}")
    return [scalar(part) for part in NUMBER_RE.findall(value)]


def transform(value: str):
    if not isinstance(value, str):
        raise ValueError("Transforms must be strings")
    pattern = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^()]*)\)")
    if pattern.sub("", value).strip(" ,\t\r\n") or not pattern.search(value):
        raise ValueError(f"Unsupported transform: {value}")
    arities = {"matrix": {6}, "translate": {1, 2}, "scale": {1, 2}, "rotate": {1, 3}, "skewX": {1}, "skewY": {1}}
    for name, raw in pattern.findall(value):
        if len(numbers(raw)) not in arities[name]:
            raise ValueError(f"Invalid {name} transform")


def paint(value, gradients: set[str], *, solid=False):
    if not isinstance(value, str):
        raise ValueError("Paint must be a CSS color or declared gradient reference")
    match = re.fullmatch(r"url\(#([A-Za-z][A-Za-z0-9_.-]*)\)", value)
    if match and not solid and match[1] in gradients:
        return
    if value == "none" and not solid:
        return
    try:
        ImageColor.getrgb(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Unsupported color or unknown gradient: {value}") from exc


def attributes(tag: str, attrs: dict, gradients: set[str]) -> dict[str, str]:
    if not isinstance(attrs, dict):
        raise ValueError(f"{tag}.attrs must be an object")
    allowed = (COMMON | SHAPE[tag]) if tag in SHAPE else GRADIENT[tag]
    for key, value in attrs.items():
        if key not in allowed:
            raise ValueError(f"Unsupported {tag} attribute: {key}")
        if key in {"fill", "stroke"}:
            paint(value, gradients)
        elif key in ENUMS:
            if str(value) not in ENUMS[key]:
                raise ValueError(f"Invalid {key}: {value}")
        elif key in {"transform", "gradientTransform"}:
            transform(value)
        elif key == "d":
            if not isinstance(value, str) or re.sub(NUMBER + r"|[MmZzLlHhVvCcSsQqTtAa\s,]", "", value):
                raise ValueError("Invalid path data")
            pen = RecordingPen()
            try:
                parse_path(value, pen)
            except (ValueError, IndexError, TypeError, AssertionError) as exc:
                raise ValueError(f"Invalid path data: {exc}") from exc
            if not any(op in {"lineTo", "curveTo", "qCurveTo"} for op, _ in pen.value):
                raise ValueError("Path has no drawable segments")
            for _, points in pen.value:
                if any(point is not None and not all(math.isfinite(n) for n in point) for point in points):
                    raise ValueError("Non-finite path coordinate")
        elif key == "points":
            coords = numbers(value)
            if len(coords) % 2 or len(coords) < (6 if tag == "polygon" else 4):
                raise ValueError("points must contain complete coordinate pairs")
        elif key == "stroke-dasharray":
            if value != "none" and (any(n < 0 for n in numbers(value)) or not any(numbers(value))):
                raise ValueError("Invalid stroke dash array")
        elif key == "font-family":
            if not isinstance(value, str) or not value.strip() or re.search(r"[<>;{}()\x00-\x1f]", value):
                raise ValueError("Invalid font-family")
        elif tag in {"text", "tspan"} and key in {"x", "y", "dx", "dy", "rotate"}:
            numbers(str(value))
        else:
            number = scalar(value, percent=tag in GRADIENT)
            if key in {"opacity", "fill-opacity", "stroke-opacity"} and not 0 <= number <= 1:
                raise ValueError(f"{key} must be between zero and one")
            if key in {"width", "height", "r", "rx", "ry", "fr", "stroke-width", "textLength"} and number < 0:
                raise ValueError(f"{key} must be non-negative")
            if key == "font-size" and number <= 0:
                raise ValueError("font-size must be positive")
            if key == "stroke-miterlimit" and number < 1:
                raise ValueError("stroke-miterlimit must be at least one")
    return {key: str(value) for key, value in attrs.items()}


def geometry(spec: dict, gradients: set[str], *, parent_tag=None) -> ET.Element:
    if not isinstance(spec, dict) or set(spec) - {"tag", "attrs", "text", "children"}:
        raise ValueError("Geometry must contain only tag, attrs, text, children")
    tag = spec.get("tag")
    if tag not in SHAPE or (tag == "tspan" and parent_tag not in {"text", "tspan"}):
        raise ValueError(f"Unsupported geometry tag: {tag}")
    if parent_tag in {"text", "tspan"} and tag != "tspan":
        raise ValueError("Text children must be tspan")
    attrs = attributes(tag, spec.get("attrs", {}), gradients)
    required = {"path": {"d"}, "rect": {"width", "height"}, "circle": {"r"}, "ellipse": {"rx", "ry"},
                "polyline": {"points"}, "polygon": {"points"}, "text": {"font-family", "font-size"}}
    if required.get(tag, set()) - attrs.keys():
        raise ValueError(f"Missing required {tag} geometry attributes")
    children = spec.get("children", [])
    if not isinstance(children, list) or (children and tag not in {"g", "text", "tspan"}):
        raise ValueError(f"{tag} cannot contain geometry children")
    node = ET.Element(f"{{{SVG}}}{tag}", attrs)
    if tag in {"text", "tspan"}:
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    if "text" in spec:
        if tag not in {"text", "tspan"} or not isinstance(spec["text"], str):
            raise ValueError("Only text/tspan can contain a text string")
        node.text = spec["text"]
    for child in children:
        node.append(geometry(child, gradients, parent_tag=tag))
    if tag in {"text", "tspan"} and not "".join(node.itertext()).strip():
        raise ValueError("Live text must have explicitly supplied wording")
    return node


def build(scene_path: Path, output_dir: Path, *, source_path: Path | None = None) -> dict:
    scene_path, output_dir = Path(scene_path).resolve(), Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"Output already exists: {output_dir}")
    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    if not isinstance(scene, dict) or scene.get("schema_version") != "1.1":
        raise ValueError("A schema 1.1 scene object is required")
    if scene.get("review_status", "reviewed") != "reviewed":
        raise ValueError("Scene is not reviewed")
    report = audit_manifest(scene_path)
    if report["status"] != "PASS":
        raise ValueError("Invalid semantic scene: " + "; ".join(report["errors"]))
    source = source_path if source_path is not None else scene.get("source")
    if source is not None and not isinstance(source, (str, Path)):
        raise ValueError("source must be a local image path")
    if source:
        source = Path(source).expanduser()
        source = (scene_path.parent / source).resolve() if source_path is None and not source.is_absolute() else source.resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if scene.get("source_sha256") is not None and scene["source_sha256"] != digest:
            raise ValueError("Source SHA-256 mismatch")
        with Image.open(source) as image:
            if ImageOps.exif_transpose(image).size != (scene["canvas"]["width"], scene["canvas"]["height"]):
                raise ValueError("Canvas dimensions do not match source image")
        scene["source"], scene["source_sha256"] = str(source), digest
    elif "source_sha256" in scene:
        raise ValueError("source_sha256 requires a source image")
    width, height = scene["canvas"]["width"], scene["canvas"]["height"]
    root = ET.Element(f"{{{SVG}}}svg", {"width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}"})
    gradients = scene.get("gradients", [])
    if not isinstance(gradients, list):
        raise ValueError("gradients must be an array")
    identifiers = {element["id"] for element in scene["elements"]}
    gradient_ids: set[str] = set()
    defs = ET.SubElement(root, f"{{{SVG}}}defs") if gradients else None
    for gradient in gradients:
        if not isinstance(gradient, dict) or set(gradient) - {"id", "tag", "attrs", "stops"}:
            raise ValueError("Invalid gradient declaration")
        identifier, tag = gradient.get("id"), gradient.get("tag")
        if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier) or identifier in identifiers | gradient_ids:
            raise ValueError("Gradient id is invalid or duplicated")
        if tag not in GRADIENT:
            raise ValueError("Only native linearGradient/radialGradient are supported")
        gradient_ids.add(identifier)
        node = ET.SubElement(defs, f"{{{SVG}}}{tag}", {"id": identifier, **attributes(tag, gradient.get("attrs", {}), set())})
        stops = gradient.get("stops")
        if not isinstance(stops, list) or len(stops) < 2:
            raise ValueError("Gradients require at least two explicit stops")
        previous = -1
        for stop in stops:
            if not isinstance(stop, dict) or set(stop) - {"offset", "stop-color", "stop-opacity"} or not {"offset", "stop-color"} <= stop.keys():
                raise ValueError("Invalid gradient stop")
            offset = scalar(stop["offset"], percent=True)
            if not 0 <= offset <= 1 or offset < previous:
                raise ValueError("Gradient offsets must increase between zero and one")
            previous = offset
            paint(stop["stop-color"], set(), solid=True)
            if not 0 <= scalar(stop.get("stop-opacity", 1)) <= 1:
                raise ValueError("Invalid gradient stop opacity")
            ET.SubElement(node, f"{{{SVG}}}stop", {key: str(value) for key, value in stop.items()})
    nodes = {}
    for element in scene["elements"]:
        spec = element.get("geometry", {"tag": "g"} if element["render_as"] == "group" else None)
        node = geometry(spec, gradient_ids)
        if spec["tag"] not in EXPECTED_TAGS[element["render_as"]]:
            raise ValueError(f"Geometry type differs from render_as for {element['id']}")
        node.set("id", element["id"])
        node.set("data-role", element["role"])
        nodes[element["id"]] = node
    for element in sorted(scene["elements"], key=lambda item: item["z_index"]):
        parent = nodes[element["parent_id"]] if element.get("parent_id") else root
        parent.append(nodes[element["id"]])
    # Stage in a disposable directory: failed audit never leaves a partial delivery.
    with tempfile.TemporaryDirectory(prefix="img2svg-scene-") as temporary:
        staged = Path(temporary)
        svg, manifest = staged / "reconstructed.svg", staged / "semantic-manifest.json"
        ET.ElementTree(root).write(svg, encoding="utf-8", xml_declaration=True)
        manifest.write_text(json.dumps(scene, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = audit_semantics(svg, manifest)
        vector_validation = audit_svg(svg)
        if validation["status"] != "PASS" or vector_validation["status"] != "PASS":
            raise ValueError("Scene validation failed: " + "; ".join(validation["errors"] + vector_validation["errors"]))
        output_dir.mkdir(parents=True, exist_ok=False)
        created = []
        try:
            for name in ("reconstructed.svg", "semantic-manifest.json"):
                with (output_dir / name).open("xb") as handle:
                    created.append(output_dir / name)
                    handle.write((staged / name).read_bytes())
        except BaseException:
            for path in created:
                path.unlink(missing_ok=True)
            try:
                output_dir.rmdir()
            except OSError:
                pass  # Preserve anything another process added to the directory.
            raise
    validation["svg"], validation["manifest"] = str(output_dir / svg.name), str(output_dir / manifest.name)
    return {"svg": validation["svg"], "manifest": validation["manifest"], "validation": validation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.scene, args.output_dir, source_path=args.source), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, ET.ParseError) as exc:
        parser.exit(1, f"build_scene: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
