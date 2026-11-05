---
name: gms-img2svg
description: Reconstruct logos, scientific figures, cell diagrams, cartoons, and line art as editable SVG with named objects, Bézier contours, gradients, and live text. Use for image-to-vector conversion, vector refinement, or requested native Illustrator playback; photographic input supports approximation only.
---

# gms-img2svg

Turn a reference into editable vector objects, preserving geometry, holes, paint order, relationships and original text. Codex performs visual planning and review; local scripts propose geometry, build reviewed plans, fit paint and measure results. This is a Skill with a local execution pipeline. Keep the source unchanged and write each run to a new directory.

When continuing an existing image, start from the current accepted SVG and its manifest with `--svg`/`--manifest`. Preserve successful earlier detail work, even if it came from a specialized reconstruction. Compare the candidate with both the untouched source and that accepted result, including previously corrected regions. Promote one current deliverable only after this review; keep rejected alternatives and superseded versions as history. A newer pipeline or smaller file is not evidence of better visual quality.

## Choose the representation

Use `semantic-clean` by default. Choose native primitives for regular logos, boxes, circles, axes and connectors; Bézier paths for organic boundaries; separate paint from geometry for shading. Use the scene builder for diagrams with text, explicit hierarchy, transparent backgrounds, or regular geometry. Use reviewed region reconstruction for opaque flat illustrations with irregular shared contours. A colour boundary is not necessarily an object boundary: a blush or shadow normally belongs to its supporting surface.

Use `contour-faithful` only when the user prioritizes unchanged linework or accepts approximate whole-image tracing. Trace fragments have coarse provenance, not recognized object semantics. Do not silently switch a difficult semantic task to this route. For photographs, disclose simplified/approximate output. Do not claim pixel identity, compactness and complete semantics unless each is independently verified.

## Run the reusable workflow

Resolve paths relative to this skill's actual directory. Use a Python environment with `scripts/requirements.txt`; advanced region/paint workflows also need `scripts/requirements-refine.txt` and Node.js. `doctor.py` reports the running skill directory, installed entry point, Python and available dependencies. A project copy and installed skill may differ; inspect the reported paths before claiming an upgrade is active.

```bash
python3 scripts/doctor.py
python3 scripts/run_pipeline.py SOURCE.png --output-dir NEW_JOB
```

Without a plan the pipeline writes source evidence and, for opaque input, a neutral colour-region draft. `NEEDS_PLAN_REVIEW` is expected: inspect the source, candidate overlay, omitted components, soft-paint warnings and domain. Proposals are not semantic truth. Correct IDs, roles, seeds, background, confidence and visible evidence; account for text, holes, repeated objects and relationships. Set `review_status: "reviewed"` only after that review. Codex can do this review within the user's existing task; it does not require another user approval.

For regular geometry or text, create an executable schema 1.1 scene using [references/semantic-manifest.md](references/semantic-manifest.md). Each element carries native `geometry`; `parent_id` and `z_index` preserve editability and paint order. For regions, use the generated plan schema with reviewed palette and seeds. Change the plan data for a new image, not the program:

```bash
python3 scripts/run_pipeline.py SOURCE.png --scene REVIEWED_SCENE.json --output-dir NEW_JOB
python3 scripts/run_pipeline.py SOURCE.png --plan REVIEWED_REGIONS.json --output-dir NEW_JOB
python3 scripts/run_pipeline.py SOURCE.png --svg EXISTING.svg --manifest SEMANTIC.json --output-dir NEW_JOB
```

For text-described artwork without a reference raster, create the reviewed scene and run `build_scene.py SCENE.json --output-dir NEW_JOB` directly. Validate its structure and inspect the rendered SVG; source-fidelity measurements are unavailable until a reference exists.

The pipeline validates source binding, builds or reuses geometry, tries bounded object-level paint correction, compacts paths with render checks, then runs semantic and dual-render quality checks. It retains the baseline, candidate reports, final SVG, comparisons and `job.json`. Draft plans, wrong source checksums and existing output directories are rejected. Failure stays `FAIL`; successful automated output stays `NEEDS_VISUAL_REVIEW` until Codex has inspected it. No Illustrator insertion is implied.

Paint fitting tries flat, linear and radial fills in visible object interiors, in residual priority order. It keeps geometry, IDs, hierarchy and text. Each accepted change must improve source error with both CairoSVG and resvg; non-improving candidates roll back. Unsupported transforms, clipped/transparent paint or inadequate samples are skipped with reasons. Use `--no-paint` to retain fills, or `--max-paint-objects` to bound work (default 12). This fitter is not a general soft-layer decomposition or gradient-mesh engine. Never call every numerical improvement visually correct.

Explicit contour tracing is available through the same entry point:

```bash
python3 scripts/run_pipeline.py SOURCE.png --contract contour-faithful --output-dir NEW_JOB
```

This whole-image trace outlines source text. When editable wording is required, use a reviewed scene or restore live text before acceptance. Existing SVGs should be validated/refined instead of traced again.

## Visual reasoning and source limits

Read [references/semantic-decomposition.md](references/semantic-decomposition.md) for domain-specific completeness, and [references/workflow.md](references/workflow.md) for reconstruction, manual refinement and detailed commands. Inspect the untouched source at native size before considering super-resolution. Interpolation may help subpixel fitting but adds no evidence and is not super-resolution. Actual SR is optional only when source ambiguity limits the result; inferred detail must be compared against the original.

A small error average can hide a missing eye, arrow or label. Inspect the full comparison and worst-error regions; render SVG detail viewBoxes at 4×/8× to check curves rather than only enlarging pixels. Distinguish silhouette mistakes, fill mistakes, missing objects and source uncertainty. Edit the relevant plan/object and run a new job. Preserve a better baseline when a candidate regresses; do not add unrestricted patch layers to chase one score.

## Output invariants

- Preserve source aspect ratio; SVG must contain real local vector geometry. Never embed raster content, external references, scripts or foreign objects.
- Require `validate_svg.py` before calling output vector-only, and `validate_semantic_svg.py` before claiming object-level completeness. Required uncertain elements need visual review or explicit disclosure.
- Preserve wording, line breaks and original language as `<text>`/`<tspan>` unless the user requests outlines. Read [references/text-manifest.md](references/text-manifest.md) for text restoration; never invent illegible text.
- Do not use Xiaomiao or another remote vectorization provider unless requested. Before a separately configured remote provider transmits image data, disclose that transfer when not already clear.
- Keep original files and previous outputs; allocate new paths. Case-specific scripts under `jobs/` are historical experiments, not dependencies of this skill.

## Illustrator and delivery

Only perform native Illustrator insertion when requested. Read [references/illustrator.md](references/illustrator.md), require a running target document, validate compatibility, build the geometry cache and use cached native-object playback. Whole-SVG import is not equivalent to native reconstructed objects. Clipping masks and gradient meshes are not supported by cached playback; SVG render success alone does not verify Illustrator behavior.

Deliver clickable paths to the final SVG, semantic/provenance manifest, quality report and comparison. Explain material limitations and unverified Illustrator behavior. Automated PASS is advisory; source comparison and semantic completeness remain Codex's responsibility.

For regression checks use `self_test.py`, `semantic_regression_test.py`, and the relevant `pipeline_test.py`, `build_scene_test.py`, `propose_regions_test.py`, `region_rebuild_test.py`, `refine_paints_test.py`, or `refinement_test.py`. Run checks matching the changes rather than every experiment.
