#!/usr/bin/env python3
"""Runnable regression: draft seeds, holes, islands, tiny details and budgets."""
import json
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from compare_render import render_rgba
from propose_regions import propose
from rebuild_regions import rebuild, segment


def main():
    with tempfile.TemporaryDirectory(prefix="img2svg-proposal-check-") as temporary:
        root = Path(temporary)
        samples = []
        logo = Image.new("RGB", (96, 96), "white")
        draw = ImageDraw.Draw(logo)
        draw.ellipse((12, 12, 83, 83), fill=(30, 60, 110))
        draw.ellipse((30, 30, 65, 65), fill="white")
        samples.append(("hole-logo", logo, [(48, 48, [255, 255, 255]), (48, 20, [30, 60, 110])]))
        islands = Image.new("RGB", (96, 96), "white")
        draw = ImageDraw.Draw(islands)
        draw.rectangle((10, 12, 35, 70), fill=(230, 85, 40))
        draw.rectangle((55, 12, 80, 70), fill=(230, 85, 40))
        draw.rectangle((43, 80, 45, 82), fill=(15, 45, 110))
        samples.append(("islands-detail", islands, [(20, 40, [230, 85, 40]), (65, 40, [230, 85, 40]), (44, 81, [15, 45, 110])]))
        other = Image.new("RGB", (96, 96), (45, 30, 70))
        draw = ImageDraw.Draw(other)
        draw.polygon([(9, 80), (47, 9), (83, 80)], fill=(40, 180, 170))
        draw.ellipse((39, 44, 55, 60), fill=(245, 200, 100))
        samples.append(("other-palette", other, [(47, 52, [245, 200, 100]), (47, 70, [40, 180, 170])]))
        for name, image, checks in samples:
            source = root / f"{name}.png"
            image.save(source)
            result = propose(source, root / name, palette_colors=4)
            plan_path = Path(result["plan"])
            plan = json.loads(plan_path.read_text())
            assert plan["review_status"] == "draft" and "reviewed" not in plan
            assert all(part["confidence"] == 0 for part in plan["parts"])
            assert result["status"] == "NEEDS_REVIEW" and not result["omitted_components"]
            # The actual builder's segmentation rejects invalid / duplicate core
            # seeds, including a ring centroid that lands inside its hole.
            labels, _, _ = segment(image, plan, 1)
            assert len(np.unique(labels)) == len(plan["parts"])
            if name == "islands-detail":
                assert len(plan["parts"]) == 4, "same-colour islands merged or tiny detail lost"
                assert sum(part["core_erosion"] == 0 for part in plan["parts"]) == 1
            # These known synthetic regions are explicitly reviewed by this test;
            # production callers must inspect / name / correct the draft first.
            plan["review_status"] = "reviewed"
            for part in plan["parts"]:
                part["confidence"] = 1
                part["description"] = "Known synthetic region checked against source pixels"
                part["evidence"].append("Synthetic fixture geometry reviewed by regression assertion")
            reviewed = root / f"{name}-reviewed.json"
            reviewed.write_text(json.dumps(plan))
            rebuild(source, reviewed, root / f"{name}-vector", scale=2, tolerance=.3)
            for engine in ("cairosvg", "resvg"):
                pixels = np.asarray(render_rgba(root / f"{name}-vector/reconstructed.svg", 96, 96, renderer=engine))
                for x, y, colour in checks:
                    assert max(abs(pixels[y, x, :3].astype(int) - colour)) < 4, (name, engine, x, y)
            try:
                propose(source, root / name)
            except ValueError as error:
                assert "exists" in str(error)
            else:
                raise AssertionError("Existing output was overwritten")
        budget = propose(root / "islands-detail.png", root / "budget", min_area=10, max_regions=2, palette_colors=4)
        assert {c["reason"] for c in budget["omitted_components"]} == {"below_min_area", "max_regions_core_budget"}
        transparent = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
        transparent.save(root / "transparent.png")
        try:
            propose(root / "transparent.png", root / "transparent")
        except ValueError as error:
            assert "opaque" in str(error)
            assert not (root / "transparent").exists()
        else:
            raise AssertionError("Transparent pixels were treated as opaque colour evidence")
        rng = np.random.default_rng(7)
        Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(root / "texture.png")
        textured = propose(root / "texture.png", root / "texture", palette_colors=4, min_area=1)
        assert textured["status"] == "NEEDS_ALTERNATIVE" and textured["alternative_reasons"]
        gradient = np.repeat(np.arange(256, dtype=np.uint8)[None, :, None], 32, axis=0)
        Image.fromarray(np.repeat(gradient, 3, axis=2)).save(root / "gradient.png")
        shaded = propose(root / "gradient.png", root / "gradient", palette_colors=4)
        assert shaded["source_features"]["smooth_colour_change_fraction"] > .9
        assert any("gradients" in reason for reason in shaded["alternative_reasons"])
    print("PASS: reviewed drafts rebuild three palettes/shapes; holes, same-colour islands, tiny details, output protection, omitted budgets, transparency and texture risk")


if __name__ == "__main__":
    main()
