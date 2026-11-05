#!/usr/bin/env python3
"""Runnable regression check for bounded gradients and structure-safe compaction."""

import tempfile
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from compare_render import render_rgba
from refine_svg import refine


def main():
    svgo = sys.argv[1] if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory(prefix="img2svg-refinement-test-") as temporary:
        root = Path(temporary)
        reference = root / "reference.svg"
        reference.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
                             '<defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="48" y2="0">'
                             '<stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff"/></linearGradient></defs>'
                             '<rect width="48" height="48" fill="url(#g)"/></svg>')
        source = root / "source.png"
        render_rgba(reference, 48, 48).save(source)
        base = root / "base.svg"
        base.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
                        '<g id="subject" data-role="subject"><path id="body" fill="#800080" d="M 0.000 0.000 L 48.000 0.000 L 48.000 48.000 L 0.000 48.000 Z"/></g></svg>')
        result = root / "refined.svg"
        report = refine(source, base, result, gradients=True, cross_render=True, max_added_paths=2,
                        chunk_size=48, max_added_points=24, max_added_bytes=2000, max_candidates=8)
        assert 0 < len(report["accepted"]) <= 2
        assert any(p["kind"] == "linear" for p in report["accepted"])
        assert report["added_points"] <= 24 and report["added_bytes"] <= 2000
        for renderer in ("cairosvg", "resvg"):
            assert report["after"][renderer]["white_mae"] < report["before"][renderer]["white_mae"]
            assert report["edge_f1_after"][renderer] >= report["edge_f1_before"][renderer]
        group = next(e for e in ET.parse(result).getroot().iter() if e.get("id") == "subject")
        assert group[0].get("id") == "body" and group.get("data-role") == "subject"
        tiled = refine(source, base, root / "tiled.svg", gradients=True, chunk_size=12, max_candidates=2)
        assert tiled["seam_rejections"] > 0 and not tiled["accepted"]
        rejected = refine(source, base, root / "rejected.svg", gradients=True, min_improvement=255, max_candidates=2)
        assert not rejected["accepted"]
        zero_budget = refine(source, base, root / "zero.svg", gradients=True, max_added_bytes=0, max_candidates=2)
        assert not zero_budget["accepted"]
        previous = result.read_bytes()
        try:
            refine(source, base, result)
        except ValueError:
            pass
        else:
            raise AssertionError("Existing output was not protected")
        assert result.read_bytes() == previous

        # Rounding relative coordinates can accumulate: strict rendering guard must roll back.
        precise = root / "precise.svg"
        precise.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48">'
                           '<g id="g"><path id="p" d="M 1.400 1.400 l 10.400 0.400 0.400 10.400 -10.400 0.400 Z"/></g>'
                           '<text id="label" x="1" y="40" font-size="5"> A  B </text></svg>')
        render_rgba(precise, 48, 48).save(source)
        conservative = refine(source, precise, root / "precise-out.svg", digits=0,
                              max_mae_increase=0, max_render_change=0, cross_render=True)
        assert not conservative["compaction_accepted"]
        assert (root / "precise-out.svg").read_bytes() == precise.read_bytes()
        # Integer absolute geometry gives the optimizer a genuinely lossless positive case.
        precise.write_text(precise.read_text().replace('M 1.400 1.400 l 10.400 0.400 0.400 10.400 -10.400 0.400 Z',
                                                      'M 1.000 1.000 L 12.000 1.000 L 12.000 12.000 L 1.000 12.000 Z'))
        render_rgba(precise, 48, 48).save(source)
        compact = refine(source, precise, root / "compact.svg", digits=3, cross_render=True, svgo=svgo)
        assert compact["compaction_accepted"]
        assert compact["complexity_after"]["bytes"] < compact["complexity_before"]["bytes"]
        assert all(compact["after"][r] == compact["before"][r] for r in compact["before"])
        assert next(e.text for e in ET.parse(root / "compact.svg").getroot().iter() if e.get("id") == "label") == " A  B "
    print("PASS: gradients, dual-renderer acceptance, complexity budgets, rounding rollback, IDs/text/order, overwrite guard")


if __name__ == "__main__":
    main()
