#!/usr/bin/env python3
"""One runnable end-to-end check: regions, holes, IDs, fills and source protection."""
import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from rebuild_regions import encode_regions, rebuild, tag
from compare_render import render_rgba
from validate_semantic_svg import audit


def main():
    with tempfile.TemporaryDirectory(prefix="img2svg-region-check-") as temporary:
        p = Path(temporary)
        source = Image.new("RGB", (96, 96), "white")
        draw = ImageDraw.Draw(source)
        draw.rectangle((8, 8, 87, 87), fill=(20, 25, 35))
        draw.ellipse((24, 24, 71, 71), fill=(20, 110, 190))
        draw.rectangle((36, 36, 59, 59), fill="white")
        source.save(p / "source.png")
        plan = dict(source_sha256=hashlib.sha256((p / "source.png").read_bytes()).hexdigest(), domain="cartoon",
                    palette=[[255, 255, 255], [20, 25, 35], [20, 110, 190]], parts=[])
        for name, ci, seed, role in [("background", 0, [2, 2], "background"), ("outline", 1, [14, 14], "subject"), ("iris", 2, [48, 29], "subject"), ("hole", 0, [48, 48], "background")]:
            plan["parts"].append(dict(id=name, palette_index=ci, seed=seed, role=role, description=name, confidence=1, evidence=["Known synthetic shape"]))
        (p / "plan.json").write_text(json.dumps(plan))
        result = rebuild(p / "source.png", p / "plan.json", p / "output", scale=2, tolerance=.4)
        final = p / "output/reconstructed.svg"
        assert result["topology_before_background_removal"]["reversed_shared_pairs"] > 0
        assert audit(final, p / "output/semantic-manifest.json")["status"] == "PASS"
        for engine in ("cairosvg", "resvg"):
            image = np.asarray(render_rgba(final, 96, 96, renderer=engine))
            assert max(abs(image[29, 48, :3].astype(int) - [20, 110, 190])) < 3, "iris paint was merged"
            assert min(image[48, 48, :3]) == 255, "hole was filled"
            assert image[:, :, 3].min() == 255, "transparent cutout seam"
            assert result["metrics"][engine]["white_mae"] < 5
        for name in ("flat.svg", "wireframe.svg"):
            paths = [n.get("d") for n in ET.parse(p / "output" / name).iter(tag("path"))]
            assert paths == [n.get("d") for n in ET.parse(final).iter(tag("path"))], "painting changed geometry"
        try:
            rebuild(p / "source.png", p / "plan.json", p / "output")
        except ValueError as error:
            assert "exists" in str(error)
        else:
            raise AssertionError("overwrote existing result")
        plan["source_sha256"] = "wrong"
        (p / "wrong-plan.json").write_text(json.dumps(plan))
        try:
            rebuild(p / "source.png", p / "wrong-plan.json", p / "wrong-output")
        except ValueError as error:
            assert "checksum" in str(error)
        else:
            raise AssertionError("accepted a plan for another source")
        # Regression for the lost iris: all 32 encoded IDs must survive tracing.
        colours = encode_regions(32)
        labels = np.repeat(colours[1:][None, :, :], 16, axis=0)
        labels = np.repeat(labels, 8, axis=1)
        Image.fromarray(labels).save(p / "ids.png")
        runtime = Path(__file__).with_name("vtracer_smooth_runtime.cjs")
        subprocess.run(["node", str(runtime), str(p / "ids.png"), str(p / "ids.svg"), json.dumps(result["options"])], check=True)
        fills = {n.get("fill").upper() for n in ET.parse(p / "ids.svg").iter(tag("path"))}
        assert fills == {"#%02X%02X%02X" % tuple(c) for c in colours[1:]}
    print("PASS: shared curves, distinct region colours, holes, fill-only stages, both renderers and output/source protection")


if __name__ == "__main__":
    main()
