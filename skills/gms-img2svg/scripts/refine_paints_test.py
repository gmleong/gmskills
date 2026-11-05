#!/usr/bin/env python3
"""Runnable two-scene regression for object paints, occlusion and safe rollback."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from compare_render import render_rgba
from refine_paints import refine
from validate_svg import local_name


def geometry(path):
    root = ET.parse(path).getroot()
    for element in root.iter():
        element.attrib.pop("fill", None)
    for element in list(root):
        if local_name(element.tag) == "defs":
            root.remove(element)
    return ET.tostring(root)


def main():
    with tempfile.TemporaryDirectory(prefix="img2svg-paint-test-") as directory:
        work = Path(directory)
        frame = '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="96" viewBox="0 0 128 96">'
        backdrop = '<rect width="128" height="96" fill="white"/>'
        linear = ('<defs><linearGradient id="source-paint" gradientUnits="userSpaceOnUse" x1="8" y1="8" x2="80" y2="8">'
                  '<stop offset="0" stop-color="#e63333"/><stop offset="1" stop-color="#3355ee"/></linearGradient></defs>')
        # Shared inherited fill plus same-colour seam stroke; a foreground sibling hides part of the object.
        artwork = ('<g id="panel" fill="PAINT" stroke="#905088" stroke-width="0.2">'
                   '<path id="panel-shape" d="M8 8H80V72H8Z"/></g>'
                   '<g id="stable" fill="#20aa66"><rect x="85" y="8" width="32" height="64"/></g>'
                   '<rect id="cover" x="30" y="8" width="12" height="64" fill="#ffee00"/>'
                   '<text id="label" x="9" y="88" font-size="9">  Live text  </text></svg>')
        reference = work / "linear-reference.svg"
        reference.write_text(frame + linear + backdrop + artwork.replace("PAINT", "url(#source-paint)"))
        base = work / "linear-base.svg"
        base.write_text(frame + backdrop + artwork.replace("PAINT", "#905088"))
        source = work / "linear.png"
        render_rgba(reference, 128, 96).save(source)
        original_source, original_svg = source.read_bytes(), base.read_bytes()
        output = work / "linear-out.svg"
        report = refine(source, base, output)
        assert report["accepted"] == ["panel"], report
        assert next(e for e in report["objects"] if e["id"] == "panel")["model"] == "linear"
        assert next(e for e in report["objects"] if e["id"] == "stable")["status"] == "unchanged"
        assert next(e for e in report["objects"] if e["id"] == "cover")["status"] == "unchanged"
        for engine in ("cairosvg", "resvg"):
            assert report["after"][engine]["white_mae"] < report["before"][engine]["white_mae"] * .2
            assert report["after"][engine]["alpha_mae"] == report["before"][engine]["alpha_mae"]
        before, after = ET.parse(base).getroot(), ET.parse(output).getroot()
        for identifier in ("stable", "cover", "label"):
            assert ET.tostring(next(e for e in before.iter() if e.get("id") == identifier)) == ET.tostring(next(e for e in after.iter() if e.get("id") == identifier))
        assert geometry(base) == geometry(output)
        assert source.read_bytes() == original_source and base.read_bytes() == original_svg
        try:
            refine(source, base, output)
        except ValueError:
            pass
        else:
            raise AssertionError("Overwrote existing output")
        rejected = work / "rejected.svg"
        assert not refine(source, base, rejected, min_improvement=255)["accepted"]
        assert rejected.read_bytes() == original_svg

        radial = ('<defs><radialGradient id="source-paint" gradientUnits="userSpaceOnUse" cx="40" cy="40" r="28">'
                  '<stop offset="0" stop-color="#fff1cc"/><stop offset="1" stop-color="#d07010"/></radialGradient></defs>')
        circles = ('<circle id="disc" cx="40" cy="40" r="28" fill="PAINT"/>'
                   '<g id="translated" transform="translate(80 20)"><rect width="28" height="32" fill="#338899"/></g>'
                   '<rect id="translucent" x="88" y="66" width="24" height="14" fill="#000" opacity=".4"/></svg>')
        reference.write_text(frame + radial + backdrop + circles.replace("PAINT", "url(#source-paint)"))
        second_base = work / "radial-base.svg"
        second_base.write_text(frame + backdrop + circles.replace("PAINT", "#eeac70"))
        second_source = work / "radial.png"
        render_rgba(reference, 128, 96).save(second_source)
        saved_source, saved_svg = second_source.read_bytes(), second_base.read_bytes()
        second_output = work / "radial-out.svg"
        second = refine(second_source, second_base, second_output)
        assert second["accepted"] == ["disc"], second
        assert next(e for e in second["objects"] if e["id"] == "disc")["model"] == "radial"
        assert all(e["status"] == "skipped" for e in second["objects"] if e["id"] in {"translated", "translucent"})
        assert geometry(second_base) == geometry(second_output)
        assert second_source.read_bytes() == saved_source and second_base.read_bytes() == saved_svg
        for engine in ("cairosvg", "resvg"):
            assert second["after"][engine]["white_mae"] < second["before"][engine]["white_mae"] * .2
        restricted = work / "restricted.svg"
        assert not refine(second_source, second_base, restricted, target_ids=["translated", "missing"])["accepted"]
        assert restricted.read_bytes() == saved_svg
        assert not refine(second_source, second_base, work / "zero.svg", max_objects=0)["accepted"]
        empty = refine(second_source, second_base, work / "empty.svg", target_ids=[])
        assert not empty["objects"] and empty["status"] == "UNCHANGED"
        # Unsupported image alpha must be disclosed while preserving the valid SVG delivery.
        rgba = render_rgba(reference, 128, 96)
        rgba.putalpha(128)
        rgba.save(work / "transparent.png")
        transparency = refine(work / "transparent.png", second_base, work / "transparent-out.svg")
        assert all(e["status"] == "skipped" and "opaque source" in e["reason"] for e in transparency["objects"])
    print("PASS: linear/radial scenes, occlusion, inherited paints, fixed geometry/live text, two-renderer rollback, unsupported-input disclosure and source/output protection")


if __name__ == "__main__":
    main()
