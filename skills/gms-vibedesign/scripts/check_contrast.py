#!/usr/bin/env python3
"""Check the VibeDesign contract's four body-text color pairs; stdlib only."""
import argparse
import json
import math
import re
import sys
from pathlib import Path


def luminance(color):
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError(f"无效颜色，需使用 #RRGGBB：{color!r}")
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(foreground, background):
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + 0.05) / (a + 0.05)


def check(design):
    colors = design["tokens"]["colors"]
    pairs = (
        ("foreground", "background"),
        ("mutedForeground", "background"),
        ("mutedForeground", "muted"),
        ("primaryForeground", "primary"),
    )
    results = []
    for foreground, background in pairs:
        ratio = contrast(colors[foreground], colors[background])
        results.append({"pair": f"{foreground}/{background}", "ratio": round(ratio, 3), "pass": ratio >= 4.5})
    return results


def self_test():
    assert math.isclose(contrast("#000000", "#FFFFFF"), 21)
    assert math.isclose(contrast("#ffffff", "#FFFFFF"), 1)
    assert contrast("#777777", "#FFFFFF") < 4.5
    assert contrast("#767676", "#FFFFFF") >= 4.5
    try:
        luminance("#fff")
    except ValueError:
        pass
    else:
        raise AssertionError("非法颜色未被拒绝")
    results = check({"tokens": {"colors": dict.fromkeys(("foreground", "background", "mutedForeground", "muted", "primaryForeground", "primary"), "#FFFFFF")}})
    assert len(results) == 4 and not any(item["pass"] for item in results)
    print("contrast self-test passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design_system", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        if args.design_system is None:
            parser.error("请提供 design-system.json 路径")
        try:
            report = check(json.loads(args.design_system.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(f"设计数据读取失败：{error}", file=sys.stderr)
            sys.exit(2)
        print(json.dumps({"threshold": 4.5, "pairs": report}, ensure_ascii=False, indent=2))
        sys.exit(0 if all(item["pass"] for item in report) else 1)
