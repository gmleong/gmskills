#!/usr/bin/env python3
"""Allocate a non-existing SVG output path without touching the filesystem."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip()).strip("-._")
    return stem or "vector"


def allocate(directory: Path, stem: str) -> Path:
    directory = directory.resolve()
    base = safe_stem(stem)
    candidate = directory / f"{base}.svg"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = directory / f"{base}-{index}.svg"
        if not candidate.exists():
            return candidate
        index += 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--stem", required=True)
    args = parser.parse_args()
    result = allocate(args.directory, args.stem)
    print(json.dumps({"ok": True, "path": str(result)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
