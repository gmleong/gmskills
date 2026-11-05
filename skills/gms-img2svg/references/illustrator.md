# Illustrator insertion

The full path uses `prepare_geometry_cache.py` followed by `playback_illustrator.py`. It appends native paths from the immutable cache to the document already open in Adobe Illustrator. It does not launch Illustrator and refuses to run when no document is open.

Before permitting an unverified Illustrator version, run `probe_illustrator.py FINAL.svg`. The probe uses a temporary non-UI document and checks imported child path points, Bézier handles, compound children, and mutable visibility without changing the target document. Passing the probe establishes basic compatibility, not full production certification.

Always preview the operation first:

```bash
python3 scripts/prepare_geometry_cache.py FINAL.svg --output-dir JOB/cache --batch-size 30
python3 scripts/playback_illustrator.py JOB/cache/geometry-cache.json --output-ai JOB/result.ai --output-png JOB/result.png --dry-run
```

Then, only when the user requested insertion:

```bash
python3 scripts/playback_illustrator.py JOB/cache/geometry-cache.json --output-ai JOB/result.ai --output-png JOB/result.png --placement center
```

Supported placements are `center`, `top-left`, `top-right`, `bottom-left`, and `bottom-right`. `--max-width-fraction` and `--max-height-fraction` limit proportional fitting to the active artboard.

Playback creates one root group, stable batch groups, and native nested groups copied from SVG `<g>` elements that carry both `id` and `data-role`. Existing objects are not selected, removed, hidden, renamed, or moved. Failed incomplete batches are removed; completed batch groups remain for resume. A semantic group can repeat when its children cross a batch boundary; use a batch size that keeps a small artwork in one batch when a single uninterrupted hierarchy is important. Do not flatten failures.

Cached playback supports solid RGB paint plus SVG `linearGradient` and `radialGradient` definitions that use `gradientUnits="userSpaceOnUse"`. Gradient stops, stop opacity, origin, radius/length, and compatible angle metadata are recreated as Illustrator `Gradient`/`GradientColor` objects. Keep identifiers short only at the SVG layer; runtime swatch names are shortened with a stable hash for Illustrator 2021 compatibility. Cached clipping masks, SVG filters, and gradient meshes are not supported yet.

The macOS bridge uses one AppleScript-to-ExtendScript call after verifying that Illustrator is already running. The Windows bridge verifies the Illustrator process first, then uses one COM call. Illustrator 2026 is the reference target. An older version is allowed only when the compatibility probe passes on the actual SVG; report that this is per-file runtime verification rather than the original project's 2026 certification.
