#!/usr/bin/env python3
"""Run the structural and visual img2svg completion gates in one command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compare_render import DOMAIN_FLOORS, audit as audit_visual
from validate_semantic_manifest import audit as audit_manifest
from validate_semantic_svg import audit as audit_semantic_svg
from validate_svg import audit as audit_svg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("svg", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--domain", choices=sorted(DOMAIN_FLOORS))
    parser.add_argument("--cross-render", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    svg = args.svg.resolve()
    manifest = args.manifest.resolve()
    output_dir = args.output_dir.resolve()
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    domain = args.domain or payload.get("domain")
    if domain not in DOMAIN_FLOORS:
        raise SystemExit("A valid --domain is required when the manifest does not declare one.")

    reports = {
        "manifest": audit_manifest(manifest),
        "svg": audit_svg(svg, require_live_text=any(element.get("role") == "text" for element in payload.get("elements", []) if isinstance(element, dict))),
        "semantic_svg": audit_semantic_svg(svg, manifest),
    }
    structural_failure = any(report.get("status") != "PASS" for report in reports.values())
    visual = (
        {"status": "SKIPPED", "reason": "SVG validation failed; rendering unsafe content is disabled."}
        if reports["svg"]["status"] != "PASS"
        else audit_visual(source, svg, output_dir, domain, cross_render=args.cross_render)
    )
    reports["visual"] = visual
    status = "FAIL" if structural_failure else visual["status"]
    combined = {
        "status": status,
        "reports": reports,
        "decision": (
            "Fix structural errors before delivery."
            if status == "FAIL"
            else "Inspect the comparison and resolve or disclose material mismatches."
            if status == "REVIEW"
            else "Automated gates passed; final visual inspection is still required."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "quality-gate.json"
    report_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    combined["report"] = str(report_path)
    print(json.dumps(combined, ensure_ascii=False, indent=2))
    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
