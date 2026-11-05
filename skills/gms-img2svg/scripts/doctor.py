#!/usr/bin/env python3
"""Read-only dependency and integrity checks for img2svg."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

EXPECTED_HASHES = {
    "wasm_vtracer_bg.mjs": "833babea15c8f9996530f6031c7146c6f3a3fe2655a06934bc9eb12cc3e4a78c",
    "wasm_vtracer_bg.wasm": "f45816d016aa0d75f86a81ac5737ce24985dacecb7323405fec42210eb8664be",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    checks: dict[str, object] = {}
    errors: list[str] = []
    script_root = Path(__file__).resolve().parent

    node = shutil.which("node")
    checks["node"] = node
    if node:
        version = subprocess.run([node, "-p", "process.versions.node"], capture_output=True, text=True, check=False)
        checks["node_version"] = version.stdout.strip() if version.returncode == 0 else None
    else:
        errors.append("Node.js is missing.")

    try:
        import PIL

        checks["pillow_version"] = PIL.__version__
    except ImportError:
        checks["pillow_version"] = None
        errors.append("Pillow is missing; install scripts/requirements.txt.")

    try:
        import cairosvg

        checks["cairosvg_version"] = cairosvg.__version__
    except ImportError:
        checks["cairosvg_version"] = None
        errors.append("CairoSVG is missing; install scripts/requirements.txt.")

    vendor_status: dict[str, object] = {}
    for filename, expected in EXPECTED_HASHES.items():
        path = script_root / "vendor" / filename
        actual = sha256(path) if path.is_file() else None
        vendor_status[filename] = {"present": path.is_file(), "sha256_ok": actual == expected}
        if actual != expected:
            errors.append(f"Bundled runtime integrity check failed: {filename}")
    checks["vendor"] = vendor_status
    checks["platform"] = platform.system()
    checks["illustrator_bridge_available"] = platform.system() in {"Darwin", "Windows"}
    checks["python"] = sys.executable
    checks["skill_root"] = str(script_root.parent)
    skill_name = script_root.parent.name
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    roots = [Path.home() / ".agents", codex_home]
    roots.extend(parent / ".agents" for parent in Path.cwd().parents)
    roots.insert(0, Path.cwd() / ".agents")
    installed = [root / "skills" / skill_name for root in roots if (root / "skills" / skill_name).is_dir()]
    matching = next((path for path in installed if path.resolve() == script_root.parent), None)
    checks["installed_skill_root"] = str((matching or installed[0]).resolve()) if installed else None
    checks["installed_matches_running"] = matching is not None
    checks["optional_dependencies"] = {name: importlib.util.find_spec(name) is not None
                                       for name in ("numpy", "scipy", "skimage", "resvg_py")}
    checks["advanced_pipeline_available"] = bool(node) and all(checks["optional_dependencies"].values())
    warnings = []
    if not checks["installed_matches_running"]:
        warnings.append("Running from a checkout or a different Skill directory; this does not confirm Codex discovery.")
    if not checks["advanced_pipeline_available"]:
        warnings.append("Reviewed-region and dual-render refinement need scripts/requirements-refine.txt and Node.js.")

    report = {"status": "PASS" if not errors else "FAIL", "checks": checks, "errors": errors, "warnings": warnings}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
