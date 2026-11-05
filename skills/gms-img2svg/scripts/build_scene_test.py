#!/usr/bin/env python3
"""Two reusable scene fixtures plus safety/contract regression checks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import cairosvg
from PIL import Image

from build_scene import SVG, build


def element(identifier, role, representation, bbox, z, geometry=None, parent=None):
    result = {"id": identifier, "role": role, "render_as": representation, "bbox": bbox,
              "z_index": z, "description": identifier.replace("-", " "), "confidence": 1,
              "evidence": ["Reviewed synthetic fixture with exact declared geometry"], "required": True}
    if geometry is not None:
        result["geometry"] = geometry
    if parent:
        result["parent_id"] = parent
    return result


def fixtures() -> dict[str, dict]:
    """Return independent editable logo and scientific-diagram declarations."""
    logo = {
        "schema_version": "1.1", "review_status": "reviewed", "domain": "mixed",
        "canvas": {"width": 160, "height": 128},
        "gradients": [
            {"id": "logo-paint", "tag": "linearGradient", "attrs": {"gradientUnits": "userSpaceOnUse", "x1": 20, "y1": 0, "x2": 120, "y2": 0},
             "stops": [{"offset": 0, "stop-color": "#2855db"}, {"offset": 1, "stop-color": "#27ba8e"}]},
            {"id": "accent-paint", "tag": "radialGradient", "attrs": {"cx": "50%", "cy": "50%", "r": "50%"},
             "stops": [{"offset": 0, "stop-color": "#fff3ad"}, {"offset": 1, "stop-color": "#ef9835"}]}],
        "elements": [
            element("logo", "subject", "group", [20, 20, 132, 100], 0),
            element("ring", "subject", "path", [20, 20, 100, 100], 1,
                    {"tag": "path", "attrs": {"d": "M20 20H120V120H20Z M45 45H95V95H45Z", "fill-rule": "evenodd", "fill": "url(#logo-paint)"}}, "logo"),
            element("accent", "decoration", "primitive", [124, 24, 28, 28], 2,
                    {"tag": "circle", "attrs": {"cx": 138, "cy": 38, "r": 14, "fill": "url(#accent-paint)"}}, "logo")],
        "relationships": [{"type": "contains", "from": "logo", "to": "ring"}, {"type": "contains", "from": "logo", "to": "accent"}],
    }
    diagram = {
        "schema_version": "1.1", "review_status": "reviewed", "domain": "scientific",
        "canvas": {"width": 360, "height": 180},
        "elements": [
            element("background", "background", "primitive", [0, 0, 360, 180], 0,
                    {"tag": "rect", "attrs": {"width": 360, "height": 180, "fill": "white"}}),
            element("diagram", "subject", "group", [15, 20, 330, 145], 1),
            element("source-cell", "subject", "primitive", [25, 40, 100, 80], 2,
                    {"tag": "ellipse", "attrs": {"cx": 75, "cy": 80, "rx": 50, "ry": 40, "fill": "#dce9ff", "stroke": "#355b91", "stroke-width": 2}}, "diagram"),
            element("target-cell", "subject", "primitive", [235, 40, 100, 80], 3,
                    {"tag": "rect", "attrs": {"x": 235, "y": 40, "width": 100, "height": 80, "rx": 16, "fill": "#dcf4e5", "stroke": "#337755", "stroke-width": 2}}, "diagram"),
            element("signal-arrow", "arrow", "group", [135, 70, 90, 20], 4,
                    {"tag": "g", "attrs": {"fill": "#334455"}, "children": [
                        {"tag": "line", "attrs": {"x1": 135, "y1": 80, "x2": 214, "y2": 80, "stroke": "#334455", "stroke-width": 3}},
                        {"tag": "polygon", "attrs": {"points": "214,70 225,80 214,90"}}]}, "diagram"),
            element("cell-label", "text", "live_text", [37, 70, 78, 23], 5,
                    {"tag": "text", "attrs": {"x": 75, "y": 85, "font-family": "Arial", "font-size": 16, "text-anchor": "middle", "fill": "#243344"}, "text": "Cell A"}, "diagram"),
            element("receptor-label", "text", "live_text", [240, 63, 88, 36], 6,
                    {"tag": "text", "attrs": {"x": 285, "y": 73, "font-family": "Arial", "font-size": 14, "text-anchor": "middle", "fill": "#243344"},
                     "children": [{"tag": "tspan", "text": "Receptor"}, {"tag": "tspan", "attrs": {"x": 285, "dy": 18}, "text": "R2"}]}, "diagram"),
            element("caption", "text", "live_text", [35, 140, 285, 24], 7,
                    {"tag": "text", "attrs": {"x": 180, "y": 156, "font-family": "Arial", "font-size": 14, "text-anchor": "middle", "fill": "#334455"}, "text": "Ligand → receptor signaling"}, "diagram")],
        "relationships": [{"type": "contains", "from": "diagram", "to": "signal-arrow"},
                          {"type": "labels", "from": "cell-label", "to": "source-cell"},
                          {"type": "labels", "from": "receptor-label", "to": "target-cell"},
                          {"type": "points_to", "from": "signal-arrow", "to": "target-cell"}],
    }
    return {"logo": logo, "scientific": diagram}


def save(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    cases = {}
    for name, scene in fixtures().items():
        case = output_dir / name
        case.mkdir()
        plan = case / "scene.json"
        save(plan, scene)
        result = build(plan, case / "output")
        svg = Path(result["svg"])
        raster = cairosvg.svg2png(url=str(svg))
        (case / "rendered.png").write_bytes(raster)
        image = Image.open(io.BytesIO(raster)).convert("RGBA")
        root = ET.parse(svg).getroot()
        nodes = {node.get("id"): node for node in root.iter() if node.get("id")}
        assert result["validation"]["status"] == "PASS"
        if name == "logo":
            assert image.getpixel((70, 70))[3] == 0, "Logo hole was filled"
            assert image.getpixel((30, 30)) != image.getpixel((110, 30)), "Linear gradient was lost"
            assert image.getpixel((138, 38)) != image.getpixel((149, 38)), "Radial gradient was lost"
            assert nodes["ring"] in list(nodes["logo"])
        else:
            assert len(root.findall(f".//{{{SVG}}}text")) == 3
            assert "".join(nodes["receptor-label"].itertext()) == "ReceptorR2"
            assert nodes["receptor-label"].get("font-family") == "Arial"
            assert nodes["signal-arrow"] in list(nodes["diagram"])
            assert [node.get("id") for node in nodes["diagram"]] == [e["id"] for e in scene["elements"] if e.get("parent_id") == "diagram"]
            assert image.getpixel((180, 80))[:3] == (51, 68, 85), "Connector was lost"
        original = svg.read_bytes()
        try:
            build(plan, case / "output")
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing output was overwritten")
        assert svg.read_bytes() == original
        # Bind a scene to an actual source; future reads must use exactly those bytes.
        source = case / "rendered.png"
        scene["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        scene["source"] = str(source)
        save(plan, scene)
        tied = build(plan, case / "source-bound")
        assert json.loads(Path(tied["manifest"]).read_text())["source_sha256"] == scene["source_sha256"]
        cases[name] = {"scene": str(plan), "svg": str(svg), "rendered": str(source), "validation": result["validation"]}

    baseline = fixtures()["logo"]
    bad_scenes = []
    for bad_geometry in [
        {"tag": "image", "attrs": {"href": "https://example.invalid/p.png"}},
        {"tag": "script", "text": "alert(1)"},
        {"tag": "path", "attrs": {"d": "M0 0L10 10", "style": "fill:red"}},
        {"tag": "path", "attrs": {"d": "M0 0L10 10", "onclick": "alert(1)"}},
        {"tag": "path", "attrs": {"d": "M0 0L10 10", "fill": "url(https://example.invalid/paint)"}},
        {"tag": "path", "attrs": {"d": "M0 0L10 10", "fill": "url(#missing)"}},
        {"tag": "path", "attrs": {"d": "M0 0L10 10", "opacity": 3}},
        {"tag": "path", "attrs": {"d": "not a path"}},
        {"tag": "path", "attrs": {"d": "M0 0L10 1e999"}},
        {"tag": "path", "attrs": {"d": "M0 0L10 10", "transform": "translate(4) evil(10)"}},
    ]:
        bad = copy.deepcopy(baseline)
        bad["elements"][1]["geometry"] = bad_geometry
        bad_scenes.append(bad)
    draft = copy.deepcopy(baseline)
    draft["review_status"] = "draft"
    bad_scenes.append(draft)
    offset = copy.deepcopy(baseline)
    offset["gradients"][0]["stops"][0]["offset"] = -0.1
    bad_scenes.append(offset)
    identity = copy.deepcopy(baseline)
    identity["gradients"][0]["id"] = "ring"
    bad_scenes.append(identity)
    hash_mismatch = copy.deepcopy(baseline)
    hash_mismatch.update(source=cases["logo"]["rendered"], source_sha256="0" * 64)
    bad_scenes.append(hash_mismatch)
    size_mismatch = copy.deepcopy(baseline)
    size_mismatch["source"] = cases["scientific"]["rendered"]
    bad_scenes.append(size_mismatch)
    order = fixtures()["scientific"]
    order["elements"][1]["z_index"] = 100  # Cannot move parent after its children.
    bad_scenes.append(order)
    with tempfile.TemporaryDirectory(prefix="img2svg-scene-invalid-") as temp:
        temp = Path(temp)
        rotated = Image.new("RGB", (128, 160), "white")
        exif = rotated.getexif()
        exif[274] = 6
        source = temp / "phone.jpg"
        rotated.save(source, exif=exif)
        oriented = copy.deepcopy(baseline)
        oriented["source"] = str(source)
        oriented["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        plan = temp / "oriented.json"
        save(plan, oriented)
        assert build(plan, temp / "oriented")["validation"]["status"] == "PASS"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == oriented["source_sha256"]
        for i, bad in enumerate(bad_scenes):
            plan = temp / f"bad-{i}.json"
            destination = temp / f"bad-{i}-output"
            save(plan, bad)
            try:
                build(plan, destination)
            except (ValueError, OSError):
                pass
            else:
                raise AssertionError(f"Invalid scene {i} was accepted")
            assert not destination.exists(), "Rejected scene left partial output"
    report = {"status": "PASS", "cases": cases, "rejected_invalid_cases": len(bad_scenes)}
    save(output_dir / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Preserve the two vector/raster scene fixtures in a new directory")
    args = parser.parse_args()
    if args.output_dir:
        print(json.dumps(run(args.output_dir.resolve()), ensure_ascii=False, indent=2))
    else:
        with tempfile.TemporaryDirectory(prefix="img2svg-scene-test-") as temporary:
            report = run(Path(temporary) / "cases")
            print(json.dumps({"status": report["status"], "cases": list(report["cases"]), "rejected_invalid_cases": report["rejected_invalid_cases"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
