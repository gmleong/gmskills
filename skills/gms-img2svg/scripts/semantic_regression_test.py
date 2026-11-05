#!/usr/bin/env python3
"""Regression tests for scientific, cell, and cartoon semantic contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from compare_render import audit as audit_visual, flat_data, render_rgba, render_svg


def run(arguments: list[str], expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if expect_success and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(arguments)}\n{result.stdout}\n{result.stderr}")
    if not expect_success and result.returncode == 0:
        raise RuntimeError(f"Command unexpectedly succeeded: {' '.join(arguments)}")
    return result


def element(identifier: str, role: str, bbox: list[int], z_index: int, render_as: str, description: str, **extra: object) -> dict:
    return {
        "id": identifier,
        "role": role,
        "bbox": bbox,
        "z_index": z_index,
        "render_as": render_as,
        "required": True,
        "description": description,
        "confidence": 0.95,
        "evidence": [f"visible {description}"],
        **extra,
    }


def write_case(root: Path, name: str, domain: str, svg: str, elements: list[dict], relationships: list[dict]) -> tuple[Path, Path]:
    svg_path = root / f"{name}.svg"
    manifest_path = root / f"{name}.json"
    svg_path.write_text(svg, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "source": str(root / f"{name}.png"),
                "domain": domain,
                "canvas": {"width": 200, "height": 140},
                "elements": elements,
                "relationships": relationships,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return svg_path, manifest_path


def main() -> int:
    scripts = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="img2svg-semantic-regression-") as temporary:
        root = Path(temporary)
        scientific = write_case(
            root,
            "scientific",
            "scientific",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 140">'
            '<rect id="background" data-role="background" width="200" height="140" fill="#fff"/>'
            '<g id="panel-a" data-role="frame">'
            '<line id="x-axis" data-role="axis" x1="20" y1="110" x2="180" y2="110" stroke="#111"/>'
            '<path id="signal" data-role="subject" d="M25 95 C60 85 80 30 120 55 S160 75 175 25" fill="none" stroke="#2563eb"/>'
            '<path id="trend-arrow" data-role="arrow" d="M145 35 L170 24 L158 48 Z" fill="#111"/>'
            '<text id="signal-label" data-role="text" x="110" y="20" font-size="12">Signal</text>'
            '</g></svg>',
            [
                element("background", "background", [0, 0, 200, 140], 0, "primitive", "white background"),
                element("panel-a", "frame", [10, 10, 180, 120], 1, "group", "plot panel"),
                element("x-axis", "axis", [20, 108, 160, 4], 2, "primitive", "horizontal axis", parent_id="panel-a"),
                element("signal", "subject", [25, 25, 150, 70], 3, "path", "signal curve", parent_id="panel-a"),
                element("trend-arrow", "arrow", [145, 24, 25, 24], 4, "path", "trend arrow", parent_id="panel-a"),
                element("signal-label", "text", [90, 8, 50, 16], 5, "live_text", "signal label", parent_id="panel-a"),
            ],
            [
                {"type": "contains", "from": "panel-a", "to": "x-axis"},
                {"type": "points_to", "from": "trend-arrow", "to": "signal"},
                {"type": "labels", "from": "signal-label", "to": "signal"},
            ],
        )
        cell = write_case(
            root,
            "cell",
            "cell",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 140">'
            '<rect id="extracellular" data-role="background" width="200" height="140" fill="#f8fbff"/>'
            '<g id="cell" data-role="subject">'
            '<ellipse id="cell-membrane" data-role="subject" cx="92" cy="72" rx="72" ry="52" fill="#dbeafe" stroke="#2563eb"/>'
            '<g id="nucleus" data-role="organelle"><ellipse id="nucleus-body" data-role="organelle" cx="88" cy="70" rx="28" ry="22" fill="#c4b5fd"/>'
            '<circle id="nucleolus" data-role="organelle" cx="92" cy="70" r="7" fill="#7c3aed"/></g>'
            '<path id="mitochondrion-1" data-role="organelle" d="M120 78 C150 60 165 90 135 102 C112 108 105 90 120 78 Z" fill="#fb923c"/>'
            '</g>'
            '<path id="nucleus-arrow" data-role="arrow" d="M170 28 L118 58 L126 45 Z" fill="#111"/>'
            '<text id="nucleus-label" data-role="text" x="142" y="22" font-size="12">Nucleus</text>'
            '</svg>',
            [
                element("extracellular", "background", [0, 0, 200, 140], 0, "primitive", "extracellular background"),
                element("cell", "subject", [20, 20, 144, 104], 1, "group", "cell body"),
                element("cell-membrane", "subject", [20, 20, 144, 104], 2, "primitive", "cell membrane", parent_id="cell"),
                element("nucleus", "organelle", [60, 48, 56, 44], 3, "group", "nucleus", parent_id="cell"),
                element("nucleus-body", "organelle", [60, 48, 56, 44], 4, "primitive", "nucleus body", parent_id="nucleus"),
                element("nucleolus", "organelle", [85, 63, 14, 14], 5, "primitive", "nucleolus", parent_id="nucleus"),
                element("mitochondrion-1", "organelle", [108, 60, 57, 48], 6, "path", "mitochondrion instance", parent_id="cell"),
                element("nucleus-arrow", "arrow", [118, 28, 52, 30], 7, "path", "nucleus arrow"),
                element("nucleus-label", "text", [140, 10, 55, 16], 8, "live_text", "nucleus label"),
            ],
            [
                {"type": "contains", "from": "cell", "to": "nucleus"},
                {"type": "contains", "from": "nucleus", "to": "nucleolus"},
                {"type": "points_to", "from": "nucleus-arrow", "to": "nucleus"},
                {"type": "labels", "from": "nucleus-label", "to": "nucleus"},
            ],
        )
        cartoon = write_case(
            root,
            "cartoon",
            "cartoon",
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 140">'
            '<rect id="background" data-role="background" width="200" height="140" fill="#fff7ed"/>'
            '<g id="character" data-role="subject">'
            '<path id="back-hair" data-role="subject" d="M45 100 C25 15 175 15 155 100 Z" fill="#172033"/>'
            '<ellipse id="face" data-role="subject" cx="100" cy="72" rx="48" ry="52" fill="#fed7aa"/>'
            '<g id="left-eye" data-role="subject"><ellipse id="left-eye-white" data-role="subject" cx="82" cy="68" rx="14" ry="10" fill="#fff"/>'
            '<circle id="left-iris" data-role="subject" cx="84" cy="68" r="7" fill="#38bdf8"/>'
            '<circle id="left-pupil" data-role="subject" cx="85" cy="69" r="3" fill="#111827"/>'
            '<circle id="left-highlight" data-role="decoration" cx="82" cy="65" r="2" fill="#fff"/></g>'
            '<path id="front-hair" data-role="subject" d="M48 44 C72 5 130 8 154 42 C125 25 118 55 100 30 C82 55 70 25 48 44 Z" fill="#172033"/>'
            '</g></svg>',
            [
                element("background", "background", [0, 0, 200, 140], 0, "primitive", "warm background"),
                element("character", "subject", [25, 8, 150, 115], 1, "group", "character"),
                element("back-hair", "subject", [25, 15, 150, 85], 2, "path", "back hair", parent_id="character"),
                element("face", "subject", [52, 20, 96, 104], 3, "primitive", "face", parent_id="character", occluded_by=["front-hair"]),
                element("left-eye", "subject", [68, 58, 30, 20], 4, "group", "left eye", parent_id="character", occluded_by=["front-hair"]),
                element("left-eye-white", "subject", [68, 58, 28, 20], 5, "primitive", "left eye white", parent_id="left-eye"),
                element("left-iris", "subject", [77, 61, 14, 14], 6, "primitive", "left iris", parent_id="left-eye"),
                element("left-pupil", "subject", [82, 66, 6, 6], 7, "primitive", "left pupil", parent_id="left-eye"),
                element("left-highlight", "decoration", [80, 63, 4, 4], 8, "primitive", "left eye highlight", parent_id="left-eye"),
                element("front-hair", "subject", [48, 8, 106, 47], 9, "path", "front hair", parent_id="character"),
            ],
            [{"type": "occludes", "from": "front-hair", "to": "face"}],
        )

        for svg_path, manifest_path in (scientific, cell, cartoon):
            run([sys.executable, str(scripts / "validate_semantic_manifest.py"), str(manifest_path)])
            run([sys.executable, str(scripts / "validate_semantic_svg.py"), str(svg_path), str(manifest_path)])

        scientific_source = root / "scientific.png"
        render_svg(scientific[0], 200, 140).save(scientific_source)
        quality_result = run(
            [
                sys.executable,
                str(scripts / "quality_gate.py"),
                str(scientific_source),
                str(scientific[0]),
                str(scientific[1]),
                "--output-dir",
                str(root / "quality"),
            ]
        )
        if json.loads(quality_result.stdout).get("status") != "PASS":
            raise RuntimeError("Combined quality gate failed on an identical render.")

        # Hidden RGB in transparent pixels must not affect appearance scores.
        transparent_svg = root / "transparent.svg"
        transparent_svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><path d="M5 5 15 5 15 15 5 15Z" fill="red"/></svg>')
        transparent_png = root / "transparent.png"
        rgba = render_rgba(transparent_svg, 20, 20)
        pixels = list(flat_data(rgba))
        rgba.putdata([(0, 255, 0, 0) if p[3] == 0 else p for p in pixels])
        rgba.save(transparent_png)
        transparency = audit_visual(transparent_png, transparent_svg, root / "transparent-qa", "cartoon")
        assert transparency["metrics"]["native_mae"] == 0
        assert transparency["metrics"]["alpha_mae"] == 0
        assert transparency["complexity"]["path_segments"] == 4  # implicit lines and closing edge
        opaque_svg = root / "opaque.svg"
        opaque_svg.write_text(transparent_svg.read_text().replace('<path', '<rect width="20" height="20" fill="white"/><path'))
        lost_alpha = audit_visual(transparent_png, opaque_svg, root / "opaque-qa", "cartoon")
        assert lost_alpha["metrics"]["native_mae"] == 0
        assert lost_alpha["metrics"]["alpha_mae"] > 0
        assert lost_alpha["metrics"]["black_background_mae"] > 0
        assert lost_alpha["status"] == "REVIEW"

        broken_manifest = json.loads(cell[1].read_text(encoding="utf-8"))
        next(item for item in broken_manifest["elements"] if item["id"] == "nucleolus")["parent_id"] = "extracellular"
        broken_path = root / "cell-broken-hierarchy.json"
        broken_path.write_text(json.dumps(broken_manifest), encoding="utf-8")
        run([sys.executable, str(scripts / "validate_semantic_svg.py"), str(cell[0]), str(broken_path)], expect_success=False)

        wrong_type = json.loads(scientific[1].read_text(encoding="utf-8"))
        next(item for item in wrong_type["elements"] if item["id"] == "x-axis")["render_as"] = "path"
        wrong_type_path = root / "scientific-wrong-type.json"
        wrong_type_path.write_text(json.dumps(wrong_type), encoding="utf-8")
        run([sys.executable, str(scripts / "validate_semantic_svg.py"), str(scientific[0]), str(wrong_type_path)], expect_success=False)

        image_path = root / "analysis-source.png"
        image = Image.new("RGB", (200, 140), "white")
        drawing = ImageDraw.Draw(image)
        drawing.ellipse((28, 18, 170, 125), fill="#dbeafe", outline="#2563eb", width=3)
        drawing.ellipse((64, 46, 120, 92), fill="#c4b5fd")
        drawing.line((145, 24, 112, 52), fill="#111827", width=3)
        image.save(image_path)
        analysis_dir = root / "analysis"
        analysis_result = run([sys.executable, str(scripts / "analyze_source.py"), str(image_path), "--output-dir", str(analysis_dir), "--domain", "cell"])
        analysis_report = json.loads(analysis_result.stdout)
        if analysis_report.get("status") != "PASS" or analysis_report.get("regions", 0) < 2:
            raise RuntimeError("Source analysis did not produce stable region evidence.")
        for artifact in ("analysis.json", "edge-map.png", "palette-map.png", "region-overlay.png", "evidence-sheet.png"):
            if not (analysis_dir / artifact).exists():
                raise RuntimeError(f"Missing analysis artifact: {artifact}")

        auto_dir = root / "analysis-auto"
        auto_result = run([sys.executable, str(scripts / "analyze_source.py"), str(image_path), "--output-dir", str(auto_dir), "--domain", "auto"])
        auto_report = json.loads(auto_result.stdout)
        if auto_report.get("selected_domain") not in {"scientific", "cell", "cartoon", "mixed"}:
            raise RuntimeError("Automatic domain routing returned an invalid domain.")

    print(json.dumps({"status": "PASS", "domains": ["scientific", "cell", "cartoon"], "negative_cases": 2, "analysis_bundle": "PASS", "quality_gate": "PASS"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
