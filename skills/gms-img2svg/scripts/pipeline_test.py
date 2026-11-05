#!/usr/bin/env python3
"""End-to-end checks of routing, paint repair, text, drafts and source protection."""
import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

from analyze_source import sha256
from compare_render import render_rgba
from run_pipeline import run


def check(root):
    root.mkdir(parents=True, exist_ok=False)
    source, baseline, manifest = root / "diagram.png", root / "diagram.svg", root / "diagram.json"
    template = ('<svg xmlns="http://www.w3.org/2000/svg" width="180" height="120" viewBox="0 0 180 120">'
                '<rect id="paper" data-role="background" width="180" height="120" fill="white"/>'
                '<circle id="cell" data-role="subject" cx="55" cy="60" r="35" fill="COLOR"/>'
                '<path id="arrow" data-role="arrow" d="M145 60H94M102 54L94 60L102 66" fill="none" stroke="#172033" stroke-width="2"/>'
                '<text id="label" data-role="text" x="96" y="43" font-family="sans-serif" font-size="14">Signal</text></svg>')
    truth = root / "reference.svg"
    truth.write_text(template.replace("COLOR", "#639aca"))
    render_rgba(truth, 180, 120).save(source)
    baseline.write_text(template.replace("COLOR", "#3284bb"))
    elements = []
    for name, role, kind, bbox in [("paper", "background", "primitive", [0, 0, 180, 120]),
                                   ("cell", "subject", "primitive", [20, 25, 70, 70]),
                                   ("arrow", "arrow", "path", [94, 53, 53, 14]),
                                   ("label", "text", "live_text", [96, 26, 65, 18])]:
        elements.append(dict(id=name, role=role, render_as=kind, bbox=bbox, z_index=len(elements),
                             description=name, confidence=1, evidence=["Known controlled reference geometry"]))
    payload = dict(schema_version="1.1", source=str(source), source_sha256=sha256(source),
                   review_status="reviewed", domain="scientific", canvas=dict(width=180, height=120), elements=elements,
                   relationships=[dict(type="points_to", **{"from": "arrow", "to": "cell"})])
    manifest.write_text(json.dumps(payload))
    original = (sha256(source), baseline.read_bytes(), manifest.read_bytes())
    repaired = run(source, root / "repaired", svg=baseline, manifest=manifest)
    assert repaired["status"] == "NEEDS_VISUAL_REVIEW", repaired
    assert repaired["automated_status"] == "PASS", repaired
    assert repaired["stages"]["paint"]["accepted"], "wrong colour was not repaired"
    final = ET.parse(repaired["output"]).getroot()
    assert [n.text for n in final.iter() if n.tag.endswith("}text")] == ["Signal"]
    assert (sha256(source), baseline.read_bytes(), manifest.read_bytes()) == original

    draft = run(source, root / "draft", optimize_paints=False, palette_colors=4)
    assert draft["status"] == "NEEDS_PLAN_REVIEW", draft
    assert "output" not in draft and not (root / "draft/final.svg").exists()
    rejected = run(source, root / "unreviewed", plan=root / "draft/proposal/region-plan.json")
    assert rejected["status"] == "FAIL" and "review" in rejected["error"].lower(), rejected
    payload["source_sha256"] = "wrong-source"
    (root / "wrong.json").write_text(json.dumps(payload))
    wrong = run(source, root / "wrong-source", svg=baseline, manifest=root / "wrong.json")
    assert wrong["status"] == "FAIL" and "checksum" in wrong["error"]
    payload["source_sha256"] = sha256(source)
    payload["canvas"] = [180, 120]
    (root / "bad-canvas.json").write_text(json.dumps(payload))
    bad = run(source, root / "bad-canvas", svg=baseline, manifest=root / "bad-canvas.json")
    assert bad["status"] == "FAIL" and "canvas" in bad["error"]
    assert json.loads((root / "bad-canvas/job.json").read_text())["status"] == "FAIL"
    payload.update(schema_version="1.0", canvas=dict(width=180, height=120))
    payload.pop("domain")
    (root / "legacy.json").write_text(json.dumps(payload))
    legacy = run(source, root / "legacy", svg=baseline, manifest=root / "legacy.json", domain="scientific", optimize_paints=False)
    assert legacy["status"] == "NEEDS_VISUAL_REVIEW", legacy
    try:
        run(source, root / "repaired", svg=baseline, manifest=manifest)
    except ValueError as exc:
        assert "exists" in str(exc)
    else:
        raise AssertionError("existing job overwritten")

    # Transparent hidden RGB must not become a proposed background object.
    alpha = Image.new("RGBA", (96, 80), (217, 30, 90, 0))
    ImageDraw.Draw(alpha).ellipse((30, 24, 66, 60), fill=(20, 130, 90, 255))
    alpha_path = root / "transparent.png"
    alpha.save(alpha_path)
    transparent = run(alpha_path, root / "transparent")
    assert transparent["status"] == "NEEDS_PLAN_REVIEW"
    assert transparent["stages"]["proposal"]["status"] == "SKIPPED"
    evidence = Image.open(root / "transparent/analysis/evidence-sheet.png")
    assert evidence.getpixel((0, 0)) == (255, 255, 255)

    # A deliberate trace request is kept separate from semantic claims.
    logo = Image.new("RGB", (96, 96), "white")
    d = ImageDraw.Draw(logo)
    d.rounded_rectangle((12, 12, 84, 84), radius=12, fill="#234567")
    d.ellipse((30, 30, 66, 66), fill="white")
    logo_path = root / "logo.png"
    logo.save(logo_path)
    trace = run(logo_path, root / "trace", contract="contour-faithful", optimize_paints=False)
    assert trace["status"] == "NEEDS_VISUAL_REVIEW", trace
    assert trace["route"] == "explicit-contour-trace" and "semantic_manifest" not in trace
    assert json.loads((root / "trace/fidelity-manifest.json").read_text())["structure"]["semantic_granularity"] == "coarse"
    result = {"status": "PASS", "checks": ["object colour repair", "live text", "draft routing/rejection", "source binding", "malformed canvas failure state", "legacy manifest domain", "no overwrites", "transparent evidence", "explicit contour contract"],
              "artifacts": str(root), "cases": {"diagram": repaired["quality_report"], "logo": trace["quality_report"]}}
    (root / "regression.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="keep evidence in a new directory; otherwise use a temporary directory")
    args = parser.parse_args()
    if args.output_dir:
        print(json.dumps(check(args.output_dir.resolve()), indent=2))
    else:
        with tempfile.TemporaryDirectory(prefix="img2svg-pipeline-test-") as tmp:
            print(json.dumps(check(Path(tmp) / "cases"), indent=2))
