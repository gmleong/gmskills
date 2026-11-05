#!/usr/bin/env python3
"""Exercise the local vectorize, validate, and live-text merge pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw


def run(arguments: list[str], expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if expect_success and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(arguments)}\n{result.stdout}\n{result.stderr}")
    if not expect_success and result.returncode == 0:
        raise RuntimeError(f"Command unexpectedly succeeded: {' '.join(arguments)}")
    return result


def main() -> int:
    scripts = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="img2svg-self-test-") as temporary:
        root = Path(temporary)
        image_path = root / "source.png"
        base_svg = root / "base.svg"
        smooth_svg = root / "smooth.svg"
        fidelity_svg = root / "fidelity.svg"
        fidelity_manifest_path = root / "fidelity-manifest.json"
        final_svg = root / "final.svg"
        manifest_path = root / "text.json"
        semantic_manifest_path = root / "semantic-manifest.json"

        image = Image.new("RGBA", (128, 96), "white")
        drawing = ImageDraw.Draw(image)
        drawing.rounded_rectangle((10, 12, 70, 70), radius=10, fill="#2F6FED")
        drawing.ellipse((74, 18, 118, 62), fill="#EF5B5B")
        drawing.line((20, 82, 108, 82), fill="#172033", width=4)
        image.save(image_path)

        run([sys.executable, str(scripts / "vectorize.py"), str(image_path), "--output", str(base_svg), "--mode", "illustration"])
        run([sys.executable, str(scripts / "validate_svg.py"), str(base_svg)])
        smooth_result = run(
            [
                sys.executable,
                str(scripts / "vectorize_smooth.py"),
                str(image_path),
                "--output",
                str(smooth_svg),
            ]
        )
        if json.loads(smooth_result.stdout)["vector_elements"] < 1:
            raise RuntimeError("Smooth vectorizer returned no geometry.")
        run(
            [
                sys.executable,
                str(scripts / "finalize_fidelity_trace.py"),
                str(base_svg),
                "--source",
                str(image_path),
                "--output",
                str(fidelity_svg),
                "--manifest",
                str(fidelity_manifest_path),
                "--parameters",
                '{"detail":100}',
            ]
        )
        fidelity_payload = json.loads(fidelity_manifest_path.read_text(encoding="utf-8"))
        if fidelity_payload["mode"] != "contour-faithful" or fidelity_payload["structure"]["vector_elements"] < 1:
            raise RuntimeError("Fidelity trace manifest contract failed.")
        fidelity_tree = ET.parse(fidelity_svg)
        fidelity_ids = {element.get("id") for element in fidelity_tree.getroot().iter()}
        if "fidelity-trace" not in fidelity_ids or "trace-fragment-0001" not in fidelity_ids:
            raise RuntimeError("Fidelity trace stable IDs were not added.")

        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "text_elements": [
                        {
                            "id": "test-label",
                            "text": "LIVE",
                            "x": 64,
                            "y": 90,
                            "bbox": [45, 78, 38, 14],
                            "font_family": "Arial",
                            "font_size": 12,
                            "font_weight": "700",
                            "fill": "#172033",
                            "opacity": 1,
                            "rotation": 0,
                            "text_anchor": "middle",
                            "paint_order": 999,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        run([sys.executable, str(scripts / "validate_manifest.py"), str(manifest_path)])
        run([sys.executable, str(scripts / "merge_text.py"), str(base_svg), str(manifest_path), "--output", str(final_svg)])
        final_validation = run(
            [sys.executable, str(scripts / "validate_svg.py"), str(final_svg), "--require-live-text"]
        )
        report = json.loads(final_validation.stdout)
        if report["live_text_elements"] < 1:
            raise RuntimeError("Live text was not preserved.")

        tree = ET.parse(final_svg)
        svg_root = tree.getroot()
        first_vector = next(
            element
            for element in svg_root.iter()
            if element.tag.rsplit("}", 1)[-1] in {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
        )
        first_vector.set("id", "primary-shape")
        first_vector.set("data-role", "subject")
        first_vector.set("fill", "url(#test-gradient)")
        parent = next(parent for parent in svg_root.iter() if first_vector in list(parent))
        first_index = list(parent).index(first_vector)
        parent.remove(first_vector)
        semantic_group = ET.Element("{http://www.w3.org/2000/svg}g", {"id": "test-group", "data-role": "subject"})
        semantic_group.append(first_vector)
        parent.insert(first_index, semantic_group)
        defs = ET.Element("{http://www.w3.org/2000/svg}defs")
        gradient = ET.SubElement(
            defs,
            "{http://www.w3.org/2000/svg}linearGradient",
            {
                "id": "test-gradient",
                "gradientUnits": "userSpaceOnUse",
                "x1": "0",
                "y1": "0",
                "x2": "128",
                "y2": "0",
            },
        )
        ET.SubElement(gradient, "{http://www.w3.org/2000/svg}stop", {"offset": "0", "stop-color": "#2f6fed"})
        ET.SubElement(gradient, "{http://www.w3.org/2000/svg}stop", {"offset": "1", "stop-color": "#ef5b5b"})
        svg_root.insert(0, defs)
        tree.write(final_svg, encoding="utf-8", xml_declaration=True)
        semantic_manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "source": str(image_path),
                    "canvas": {"width": 128, "height": 96},
                    "elements": [
                        {
                            "id": "primary-shape",
                            "role": "subject",
                            "bbox": [10, 12, 108, 58],
                            "z_index": 1,
                            "render_as": "path",
                            "required": True,
                            "description": "primary test geometry",
                        },
                        {
                            "id": "test-label",
                            "role": "text",
                            "bbox": [45, 78, 38, 14],
                            "z_index": 999,
                            "render_as": "live_text",
                            "required": True,
                            "description": "editable test label",
                        },
                    ],
                    "relationships": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        run([sys.executable, str(scripts / "validate_semantic_manifest.py"), str(semantic_manifest_path)])
        run([sys.executable, str(scripts / "validate_semantic_svg.py"), str(final_svg), str(semantic_manifest_path)])

        unsafe_svg = root / "unsafe.svg"
        unsafe_svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<path d="M0 0 L10 0 L10 10 Z"/><image href="data:image/png;base64,AA=="/>'
            "</svg>",
            encoding="utf-8",
        )
        run([sys.executable, str(scripts / "validate_svg.py"), str(unsafe_svg)], expect_success=False)

        cache_dir = root / "cache"
        cache_result = run(
            [
                sys.executable,
                str(scripts / "prepare_geometry_cache.py"),
                str(final_svg),
                "--output-dir",
                str(cache_dir),
                "--batch-size",
                "20",
            ]
        )
        cache_path = Path(json.loads(cache_result.stdout)["cache"])
        cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if not any(atom.get("sourceId") == "primary-shape" for atom in cache_payload["atoms"]):
            raise RuntimeError("Semantic SVG identity was not preserved in the geometry cache.")
        if "test-gradient" not in cache_payload.get("gradients", {}):
            raise RuntimeError("SVG gradient was not preserved in the geometry cache.")
        primary_atom = next(atom for atom in cache_payload["atoms"] if atom.get("sourceId") == "primary-shape")
        if primary_atom.get("groupPath") != [{"id": "test-group", "role": "subject"}]:
            raise RuntimeError("Semantic SVG group hierarchy was not preserved in the geometry cache.")
        dry_run = run(
            [
                sys.executable,
                str(scripts / "playback_illustrator.py"),
                str(cache_path),
                "--output-ai",
                str(root / "result.ai"),
                "--output-png",
                str(root / "result.png"),
                "--live-delay-ms",
                "120",
                "--two-pass-live",
                "--wireframe-delay-ms",
                "140",
                "--paint-delay-ms",
                "90",
                "--dry-run",
            ]
        )
        if not json.loads(dry_run.stdout).get("dry_run"):
            raise RuntimeError("Illustrator dry-run contract failed.")
        if json.loads(dry_run.stdout).get("live_delay_ms") != 120:
            raise RuntimeError("Illustrator live-playback delay was not preserved.")
        if not json.loads(dry_run.stdout).get("two_pass_live"):
            raise RuntimeError("Illustrator two-pass playback flag was not preserved.")

        run([sys.executable, str(scripts / "semantic_regression_test.py")])

    print(json.dumps({"status": "PASS", "pipeline": "semantic-analysis+inventory+vector+live-text", "domains": ["scientific", "cell", "cartoon"], "illustrator": "cached-dry-run"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
