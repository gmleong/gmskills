#!/usr/bin/env python3
"""Probe the Illustrator SVG-import object model without touching the target document."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from validate_svg import audit


def jsx_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_jsx(svg: Path) -> str:
    return f"""#target illustrator
(function () {{
  var sourceDoc = null;
  var result = {{version: app.version, paths: 0, points: 0, compounds: 0, texts: 0, visibilityMutable: false}};
  function walk(container) {{
    for (var index = container.pageItems.length - 1; index >= 0; index -= 1) {{
      var item = container.pageItems[index];
      if (item.typename === "GroupItem" && !item.clipped) walk(item);
      else if (item.typename === "PathItem") {{
        result.paths += 1;
        for (var pointIndex = 0; pointIndex < item.pathPoints.length; pointIndex += 1) {{
          var point = item.pathPoints[pointIndex];
          var anchor = point.anchor;
          var left = point.leftDirection;
          var right = point.rightDirection;
          if (anchor.length !== 2 || left.length !== 2 || right.length !== 2) throw new Error("Invalid path-point data");
          result.points += 1;
        }}
        if (!result.visibilityMutable) {{
          var previous = item.hidden;
          item.hidden = !previous;
          result.visibilityMutable = item.hidden !== previous;
          item.hidden = previous;
        }}
      }} else if (item.typename === "CompoundPathItem") {{
        result.compounds += 1;
        for (var childIndex = 0; childIndex < item.pathItems.length; childIndex += 1) {{
          var child = item.pathItems[childIndex];
          result.paths += 1;
          result.points += child.pathPoints.length;
          if (child.pathPoints.length > 0) {{
            var childAnchor = child.pathPoints[0].anchor;
            if (childAnchor.length !== 2) throw new Error("Invalid compound child point");
          }}
        }}
      }} else if (item.typename === "TextFrame") {{
        result.texts += 1;
        if (item.contents.length < 1) throw new Error("Imported text frame is empty");
      }} else throw new Error("Unsupported imported item: " + item.typename);
    }}
  }}
  try {{
    if (app.documents.length < 1) throw new Error("Open a target document first");
    sourceDoc = app.documents.addDocumentNoUI(app.startupPresetsList[0]);
    var imported = sourceDoc.groupItems.createFromFile(new File({jsx_string(str(svg))}));
    $.sleep(250);
    walk(imported);
    if (result.paths < 1 || result.points < 2) throw new Error("Imported children did not expose path points");
    return "PASS|version=" + result.version + "|paths=" + result.paths + "|points=" + result.points +
      "|compounds=" + result.compounds + "|texts=" + result.texts + "|visibilityMutable=" + result.visibilityMutable;
  }} catch (error) {{
    return "FAIL|version=" + app.version + "|message=" + error.message + "|line=" + error.line;
  }} finally {{
    if (sourceDoc !== null) {{ try {{ sourceDoc.closeNoUI(); }} catch (closeError) {{}} }}
  }}
}})();
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("svg", type=Path)
    args = parser.parse_args()
    source = args.svg.resolve()
    report = audit(source)
    if report["status"] != "PASS":
        raise SystemExit("SVG validation failed: " + "; ".join(report["errors"]))
    if platform.system() != "Darwin":
        raise SystemExit("This probe currently targets the macOS Illustrator bridge.")
    running = subprocess.run(["pgrep", "-f", "Adobe Illustrator"], capture_output=True, check=False)
    if running.returncode != 0:
        raise SystemExit("Illustrator is not running.")
    # Illustrator 2021 can intermittently fail createFromFile() when the SVG
    # lives under a non-ASCII path, so always probe an ASCII-safe temp copy.
    with tempfile.NamedTemporaryFile("wb", prefix="img2svg-probe-", suffix=".svg", delete=False) as handle:
        probe_svg = Path(handle.name)
    shutil.copyfile(source, probe_svg)
    with tempfile.NamedTemporaryFile("w", prefix="img2svg-probe-", suffix=".jsx", encoding="utf-8", delete=False) as handle:
        handle.write(build_jsx(probe_svg))
        jsx_path = Path(handle.name)
    apple_script = """set jsxFile to POSIX file (system attribute \"IMG2SVG_JSX\")
with timeout of 600 seconds
  tell application id \"com.adobe.illustrator\"
    do javascript file jsxFile
  end tell
end timeout
"""
    environment = os.environ.copy()
    environment["IMG2SVG_JSX"] = str(jsx_path)
    try:
        result = subprocess.run(["osascript", "-e", apple_script], env=environment, capture_output=True, text=True, check=False)
    finally:
        jsx_path.unlink(missing_ok=True)
        probe_svg.unlink(missing_ok=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "Illustrator probe bridge failed.")
    output = result.stdout.strip()
    print(output)
    return 0 if output.startswith("PASS|") else 1


if __name__ == "__main__":
    raise SystemExit(main())
