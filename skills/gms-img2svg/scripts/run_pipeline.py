#!/usr/bin/env python3
"""One local entry point: evidence, reviewed reconstruction, bounded repair and QA.

No semantic decisions are inferred from colour components. A new image without
a reviewed plan produces reviewable evidence; Codex completes the visual plan.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageOps

from analyze_source import analyze, sha256
from compare_render import audit as compare
from refine_svg import refine as compact
from validate_semantic_svg import audit as validate_semantics
from validate_svg import audit as validate_svg


def write_json(path, payload):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def command(script, arguments, log):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name(script)),
                             *map(str, arguments)], capture_output=True, text=True)
    with log.open("x", encoding="utf-8") as handle:
        handle.write(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError(f"{script} failed; see {log}")


def check_source(payload, source, size):
    """Reviewed artifacts must describe this exact source and coordinate system."""
    if not isinstance(payload, dict):
        raise ValueError("Plan/manifest must be a JSON object.")
    if payload.get("review_status", "reviewed") != "reviewed":
        raise ValueError("Draft plan needs visual review; do not use it as a semantic result.")
    if payload.get("source_sha256") and payload["source_sha256"] != sha256(source):
        raise ValueError("Plan/manifest source checksum differs.")
    canvas = payload.get("canvas")
    if canvas is not None:
        if not isinstance(canvas, dict):
            raise ValueError("Plan/manifest canvas must be an object with width and height.")
        if (canvas.get("width"), canvas.get("height")) != size:
            raise ValueError("Plan/manifest canvas differs from the source dimensions.")


def check_canvas(svg, size):
    root = ET.parse(svg).getroot()
    box = root.get("viewBox")
    if box:
        values = [float(v) for v in box.replace(",", " ").split()]
        if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
            raise ValueError("SVG viewBox must have positive width and height.")
        ratio = values[2] / values[3]
    else:
        try:
            ratio = float(root.get("width", "").removesuffix("px")) / float(root.get("height", "").removesuffix("px"))
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError("An SVG viewBox or positive pixel dimensions are required.") from exc
    if abs(ratio / (size[0] / size[1]) - 1) > 1e-6:
        raise ValueError("SVG aspect ratio differs from the untouched source.")


def run(source, output_dir, *, plan=None, scene=None, svg=None, manifest=None,
        contract="semantic-clean", domain="mixed", optimize_paints=True,
        max_paint_objects=12, palette_colors=12, scale=3, tolerance=.6):
    source, output_dir = Path(source).resolve(), Path(output_dir).resolve()
    if output_dir.exists():
        raise ValueError("Output directory exists; choose a new job directory.")
    if contract not in {"semantic-clean", "contour-faithful"}:
        raise ValueError("Unsupported fidelity contract.")
    if domain not in {"mixed", "scientific", "cell", "cartoon"}:
        raise ValueError("Unsupported domain.")
    if sum(x is not None for x in (plan, scene, svg)) > 1:
        raise ValueError("Choose only one of plan, scene or existing SVG.")
    if bool(svg) != bool(manifest):
        raise ValueError("An existing semantic SVG requires its semantic manifest.")
    if contract == "contour-faithful" and any(x is not None for x in (plan, scene, svg)):
        raise ValueError("Contour tracing cannot replace a supplied semantic artifact.")
    if not 0 <= max_paint_objects <= 255:
        raise ValueError("max_paint_objects must be in 0..255.")
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    checksum = sha256(source)
    output_dir.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "1.0", "source": str(source), "source_sha256": checksum,
              "contract": contract, "status": "RUNNING", "stages": {},
              "visual_review_required": True, "illustrator_verified": False}
    try:
        report["stages"]["analysis"] = analyze(source, output_dir / "analysis", domain, 1024, 16, .0004, 240)
        if not any(x is not None for x in (plan, scene, svg)) and contract == "semantic-clean":
            report["route"] = "reviewed-plan-needed"
            if image.getchannel("A").getextrema() == (255, 255):
                from propose_regions import propose
                report["stages"]["proposal"] = propose(source, output_dir / "proposal", palette_colors=palette_colors, domain=domain)
            else:
                report["stages"]["proposal"] = {"status": "SKIPPED", "reason": "Colour-region reconstruction requires opaque input; preserve transparency with a reviewed scene."}
            report["status"] = "NEEDS_PLAN_REVIEW"
            report["next_action"] = "Inspect source and evidence; confirm domain, text, objects and soft paint. Supply a reviewed region plan or semantic scene in a new run. Colour proposals are not semantics."
            if report["stages"]["proposal"]["status"] == "NEEDS_ALTERNATIVE":
                report["next_action"] = "Region evidence exceeds its suitability limits. Inspect proposal.json and use a reviewed scene or adjust the proposal after visual inspection. Do not reconstruct the draft as-is."
        else:
            semantic = None
            if scene is not None:
                from build_scene import build
                scene = Path(scene).resolve()
                check_source(json.loads(scene.read_text()), source, image.size)
                report["route"] = "semantic-scene"
                report["stages"]["build"] = build(scene, output_dir / "build", source_path=source)
                baseline = output_dir / "build/reconstructed.svg"
                semantic = output_dir / "build/semantic-manifest.json"
            elif plan is not None:
                from rebuild_regions import rebuild
                plan = Path(plan).resolve()
                check_source(json.loads(plan.read_text()), source, image.size)
                report["route"] = "reviewed-regions"
                report["stages"]["build"] = rebuild(source, plan, output_dir / "build", scale=scale, tolerance=tolerance)
                baseline = output_dir / "build/reconstructed.svg"
                semantic = output_dir / "build/semantic-manifest.json"
            elif svg is not None:
                report["route"] = "existing-semantic-svg"
                svg, manifest = Path(svg).resolve(), Path(manifest).resolve()
                check_source(json.loads(manifest.read_text()), source, image.size)
                baseline, semantic = output_dir / "baseline.svg", output_dir / "semantic-manifest.json"
                shutil.copyfile(svg, baseline)
                shutil.copyfile(manifest, semantic)
            else:
                report["route"] = "explicit-contour-trace"
                raw, baseline = output_dir / "raw-trace.svg", output_dir / "baseline.svg"
                command("vectorize_smooth.py", [source, "--output", raw], output_dir / "trace.log")
                command("finalize_fidelity_trace.py", [raw, "--source", source, "--output", baseline,
                        "--manifest", output_dir / "fidelity-manifest.json"], output_dir / "finalize.log")
                report["limitations"] = ["Trace fragments have coarse provenance, not object-level semantic recognition; source text is outlined."]

            structural = validate_svg(baseline)
            if structural["status"] != "PASS":
                raise ValueError("Baseline SVG invalid: " + "; ".join(structural["errors"]))
            check_canvas(baseline, image.size)
            if semantic:
                structural = validate_semantics(baseline, semantic)
                if structural["status"] != "PASS":
                    raise ValueError("Baseline semantics invalid: " + "; ".join(structural["errors"]))
            current = baseline
            if optimize_paints and semantic and max_paint_objects:
                from refine_paints import refine
                painted = output_dir / "painted.svg"
                report["stages"]["paint"] = refine(source, current, painted, max_objects=max_paint_objects)
                current = painted
            final = output_dir / "final.svg"
            report["stages"]["compaction"] = compact(source, current, final, cross_render=True, max_mae_increase=0)
            if semantic:
                quality_domain = json.loads(semantic.read_text()).get("domain") or domain
                command("quality_gate.py", [source, final, semantic, "--output-dir", output_dir / "qa",
                        "--domain", quality_domain, "--cross-render"], output_dir / "quality.log")
                gate = json.loads((output_dir / "qa/quality-gate.json").read_text())
                report["semantic_manifest"] = str(semantic)
                report["quality_report"] = str(output_dir / "qa/quality-gate.json")
            else:
                gate = compare(source, final, output_dir / "qa", domain, cross_render=True)
                report["quality_report"] = str(output_dir / "qa/visual-report.json")
            report.update(status="NEEDS_VISUAL_REVIEW", automated_status=gate["status"], output=str(final),
                          next_action="Inspect qa/source-vs-svg.png and details; disclose material mismatches before delivery.")
    except Exception as exc:
        # A failed stage must never leave a persisted job claiming RUNNING.
        report.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
    finally:
        if sha256(source) != checksum:
            report.update(status="FAIL", error="Source changed while running; do not deliver this result.")
        write_json(output_dir / "job.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    route = parser.add_mutually_exclusive_group()
    route.add_argument("--plan", type=Path)
    route.add_argument("--scene", type=Path)
    route.add_argument("--svg", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--contract", choices=("semantic-clean", "contour-faithful"), default="semantic-clean")
    parser.add_argument("--domain", choices=("mixed", "scientific", "cell", "cartoon"), default="mixed")
    parser.add_argument("--no-paint", action="store_true", help="retain original fills; still validate and compact")
    parser.add_argument("--max-paint-objects", type=int, default=12)
    parser.add_argument("--palette-colors", type=int, default=12)
    parser.add_argument("--scale", type=int, default=3)
    parser.add_argument("--tolerance", type=float, default=.6)
    args = vars(parser.parse_args())
    args["optimize_paints"] = not args.pop("no_paint")
    report = run(**args)
    print(json.dumps({key: report[key] for key in ("status", "route", "output", "quality_report", "next_action", "error") if key in report}, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
