# Semantic reconstruction workflow

## Reusable entry point

For an ongoing image, locate the last accepted delivery first and continue with `--svg` and its manifest. Do not restart from an older region trace just to exercise a new generic route: that discards already successful gradients and detail layers. The accepted delivery is the regression baseline, alongside the original source. Recheck its previously repaired detail regions in both renderers and visually before promoting the new output. Present one current result; historical experiments are rollback evidence, not parallel user-facing editions.

Use `run_pipeline.py SOURCE --output-dir NEW_JOB` to collect evidence and propose neutral colour regions. Inspect the proposal's omissions and suitability before using it. `NEEDS_PLAN_REVIEW` means there is no reconstructed deliverable yet; it is not an error or a reason to ask the user for routine approval. Codex completes visual review, creates a reviewed region plan or executable semantic scene, and starts a new job with `--plan` or `--scene`.

Use a scene for regular primitives, explicit relationships, live text, or transparent artwork. `build_scene.py` compiles the extended semantic manifest described in `semantic-manifest.md`; no image-specific drawing script is necessary. Use a reviewed region plan for opaque flat art with irregular contours. Automatic candidates are colour cores, not automatically recognized objects. `review_status: "draft"` blocks both the pipeline and reconstruction; legacy reviewed plans without this field remain compatible.

`--svg EXISTING.svg --manifest SEMANTIC.json` reuses geometry. The pipeline retains a baseline, tries bounded native paint correction, then uses render-checked compaction and the existing quality gate. `job.json` records routing, stage results, source hash, artifact paths and failures. `NEEDS_VISUAL_REVIEW` with automated PASS still requires inspecting the comparison. It never implies native Illustrator verification. Whole-image tracing is available only through the explicit `--contract contour-faithful`; its manifest remains coarse provenance and its text is outlined.

`job.json` is the automatic-stage snapshot, not a human-review tracker. Record the completed visual inspection, accepted limitations and final SVG path/hash in the existing delivery report or final response; do not change an automatic status to imply the program inspected the image.

## 1. Preserve and analyze the input

Keep the untouched PNG, JPEG, or WebP. Run `analyze_source.py` to create a preview, edge map, palette map, region overlay, and machine-readable region proposals. Inspect the evidence sheet at sufficient resolution and confirm the domain; its automatic domain selection is only a routing hint.

Create `semantic-manifest.json` schema 1.1 before authoring geometry. The manifest is the completeness contract: every meaningful subject, organelle, arrow, connector, frame, axis, legend, text run, and repeated element must have a stable identifier, bounding box, z-index, intended SVG representation, confidence, and visible evidence. Use `semantic-decomposition.md` for the selected domain.

Create a fresh output directory beside the source or in the user's requested location. Use `allocate_output.py` so previous results are not overwritten.

## 2. Separate semantic structure from text

If the image has visible text, create the text manifest before any cleanup. Text remains live unless the user explicitly requests outlines.

If text must remain editable:

1. Inspect the untouched source at sufficient resolution.
2. Record every text run using `text-manifest.md`.
3. Use the available image-editing capability to remove only text and naturally reconstruct the local background. Preserve all arrows, lines, boxes, axes, legends, subjects, colors, spacing, and layout.
4. Compare the cleaned image with the original before reconstruction. If non-text structure changed materially, redo the cleanup.

Do not use a flat rectangle to cover text when it would erase or obscure underlying structure.

## 3. Reconstruct named vector objects

Build one Master SVG in original paint order. Every required manifest element must map to an SVG element or group using the same `id`; add `data-role` when it improves editability. Use native SVG primitives for regular geometry and Bézier paths for organic shapes. Preserve holes with compound paths or even-odd fill rules. Keep repeated scientific objects separate and consistently styled.

Do not treat pixel contours as semantic objects. Whole-image VTracer is a user-approved fallback, not the default route. For a difficult isolated silhouette, tracing may supply provisional control points, but simplify and integrate the result into the named semantic group before acceptance.

For dense scientific figures, reconstruct in semantic passes: background and frames, large subjects, internal structures, connectors and arrows, annotations and live text. Render after each pass so missing or displaced structures are caught before later layers conceal them.

## 3a. Approximate whole-image fallback

Run `vectorize.py`. The script decodes the image with Pillow, invokes the bundled MIT-licensed `wasm_vtracer` runtime, and writes a new SVG atomically.

Suggested modes:

- `lineart`: black-and-white drawings and signatures.
- `pixel`: pixel art and hard-edged sprites.
- `illustration`: logos, icons, diagrams, and flat artwork.
- `photo`: photographic input where approximation is acceptable.

Use `--remove-background` only for an almost-white background that should become transparent. Increase `--detail` for smaller features; increase `--smoothing` to reduce noisy paths. For antialiased flat artwork with colored fringe paths, try `--edge-blur 0.4 --palette-colors 32`; compare the rendered result because aggressive palette reduction can remove subtle highlights. Avoid chasing photographic fidelity with extreme settings because the SVG can become impractically large.

### Reviewed region reconstruction

`propose_regions.py SOURCE --output-dir NEW_PROPOSAL` prepares a draft using dominant source colours and interior distance-transform seeds. Palette distance, minimum component area and maximum region count are bounded; the proposal lists omitted components/cores and flags large smooth colour changes or excessive residuals. Check these warnings before reviewing a plan. A centroid may fall inside a hole, so the generated seeds always lie in the matching solid core. Transparent images use the scene/existing-SVG route.

For an explicitly requested "split into regions, draw Bézier outlines, then fill" workflow, `rebuild_regions.py` accepts a source-specific reviewed seed plan. Seeds identify intended visible regions, watershed supplies local neighbourhoods, and colour assignment at 3x resolution estimates subpixel interfaces. The bundled VTracer fits the shared region boundaries. Colour merging and speckle deletion are disabled so temporary IDs cannot merge an iris into another region. Exact reversed cubic pairs are counted in `reconstruction.json`, and the intermediate topology is saved as `shared-boundaries.svg`.

The plan contains `source_sha256`, `domain`, RGB `palette`, `parts`, and optional `notes`. Every part has `id`, `palette_index`, `seed`, `role`, `description`, `confidence`, and visible `evidence`. Seeds choosing the same solid core fail explicitly. After changing the source, review a new plan; do not simply bypass its checksum. `scripts/region_rebuild_test.py` constructs a runnable reviewed region-plan example.

Native flat/linear/radial fills are fit to complete region interiors using the existing paint fitter. The background becomes one opaque rectangle; holes remain in foreground paths. The command compares 0, 0.2 and 0.4px same-colour seam strokes using CairoSVG and resvg, selecting only widths that do not worsen either renderer's white/black MAE relative to no stroke. This reduces cutout seams but does not prove perfect topology or fidelity. The fitting tolerance is a tracer setting in source-pixel units, not a measured maximum contour displacement.

`wireframe.svg`, `flat.svg` and `reconstructed.svg` contain identical path geometry. The report includes complexity, seam trials and known combined regions; the manifest records paint models. Inspect at native size and by rendering SVG detail viewBoxes at 4x/8x; magnifying a native-size raster alone does not test vector smoothness. Approximate colour transitions, connected features and sharpness changes remain explicit delivery limitations. This route requires opaque flat artwork and reviewed seeds; it does not provide automatic semantic recognition. Illustrator playback remains a separate step.

Run `scripts/region_rebuild_test.py` for shared boundaries, distinct temporary IDs, holes, iris colour, identical geometry across fill stages, both renderers, source checksum and overwrite protection.

Separate soft paint boundaries from object silhouettes. A blush, soft nose tint or mouth-corner shadow can cross several quantized colours without representing several physical parts. For those regions, restore the underlying surface and fit paint as a separate layer: an elliptical radial opacity gradient for a compact soft spot, a multistop linear gradient for directional colour changes, or a bounded set of smooth colour contours for an irregular two-dimensional gradient. Do not force every gradient into a circular model, or use pixel blend boundaries as permanent cuts in the surface. For a self-contained paint-fitting example, see `scripts/refine_paints_test.py`.

Inspect the original at native size before proposing super-resolution. Upsampling by interpolation can help subpixel curve fitting but does not recover missing evidence and must not be called super-resolution. A small blurred detail may still support a compact shape plus soft paint model; only introduce an actual super-resolution process when source ambiguity is the limiting factor, and compare its inferred details against the unchanged original. The facial example required no super-resolution, no SVG blur filter and no embedded raster.

## 4. Restore live text and verify semantics

Validate the text manifest, then use `merge_text.py`. Text is inserted into root paint order using `paint_order`. Multi-line content becomes a `<text>` element with `<tspan>` lines. Re-run SVG validation with `--require-live-text`, then run `validate_semantic_svg.py` against the semantic manifest.

If the exact font is not installed on the recipient's machine, the renderer may substitute another font. Report this limitation instead of outlining the text without permission.

## 5. Structural and visual critic loop

Run `quality_gate.py` to validate the manifest, SVG representation types, semantic nesting, paint order, and relationships, then render a deterministic source/SVG comparison. Check structure before aesthetics: missing elements, wrong connections, directionality, relative position, scale, and paint order. Then check curves, palette, stroke hierarchy, spacing, and repeated-object consistency. Correct the SVG and repeat until the material mismatches are resolved or explicitly reported.

Visual scores are advisory and cannot prove semantic correctness. A passing validator without inspection of the source/SVG comparison is not completion.

Source and SVG are now both composited on white for appearance comparison, while separate alpha and black-background measurements expose lost transparency. Reports retain the old sampled metrics and add native-size MAE/edge F1, complexity counts and three worst-error detail crops at 4x. Use `--cross-render` on `quality_gate.py` or `compare_render.py` to measure with optional resvg-py as well as CairoSVG. Compare before/after with the same measurement version; older experiments that discarded alpha have different MAE values.

### Bounded refinement and compression

Prefer `refine_paints.py SOURCE BASE.svg --output NEW.svg` for whole-object paint errors before using spatial patches. It tries native flat/linear/radial models while preserving every existing geometry node, ID, hierarchy and text. Automatic candidates are named shapes or leaf groups, ranked by source residual. Black/white probe renders determine visible fill coverage, then edge erosion avoids antialias samples and occluded regions. The object budget defaults to 12. Accept only strict local and whole-image improvement under both CairoSVG and resvg, with no alpha/white/black MAE regression; reject other trials and preserve their reasons in `.paints.json`. Explicit `--target-id` narrows the repair. This does not repair wrong silhouettes, complex shading, transformed/clipped/translucent paint or multi-colour groups. Unsupported objects remain unchanged. Review thin strokes and object boundaries after accepted paint changes because pixel MAE alone cannot prove quality.

Start with `refine_svg.py SOURCE BASE.svg --output NEW.svg --cross-render`. This preserves the original file and emits `NEW.refine.json` containing before/after scores, complexity, parameters and acceptance decisions. Optional `--svgo /path/to/svgo` uses only `convertPathData` with geometry rewrites disabled and absolute coordinates retained. Relative-coordinate rewrites can produce small Cairo rasterization differences even when resvg is unchanged, so both renderers participate in acceptance. A structural signature protects non-path attributes, IDs, nested groups, text and paint order. Failed compression is rolled back.

Only add `--gradients` after inspecting residuals. Parameters `--chunk-size`, `--max-candidates`, `--max-added-paths`, `--max-added-points`, `--max-added-bytes`, `--min-improvement` and `--min-improvement-per-kib` keep the experiment finite. Chunks use local colour slopes for linear fills or a local concentric radial model; this is not adaptive boundary-normal segmentation or complete gradient-layer decomposition. A candidate must improve rendered MAE without worsening alpha, edges or local colour-gradient error, including pixels across chunk boundaries. An opaque input and `viewBox="0 0 source_width source_height"` are currently required for gradient experiments. Compaction supports transparent inputs and other viewBoxes.

Optional dependencies: `python3 -m pip install -r scripts/requirements-refine.txt`. SVGO is an optional external executable, not installed automatically; version 4.1.0 was tested. Run `scripts/self_test.py` for the core pipeline and `scripts/refinement_test.py [SVGO_EXECUTABLE]` for gradients, budgets, dual-renderer acceptance, precision rollback, structure and overwrite protection. Case-specific scripts under `jobs/` remain historical experiments; use the generic entry point for new work.

## 6. Cache geometry and play it into Illustrator

For the full workflow, parse the final Master SVG exactly once with `prepare_geometry_cache.py`. Playback reads only the cache, keeps a single Illustrator automation call, creates native paths in consecutive batches of 20–50, and resumes by stable batch names. Existing artwork must remain unchanged. Save AI and export PNG only after every batch is complete.

Do not replace this path with `createFromFile()` whole-SVG import when claiming original-equivalent behavior.

## 7. Inspect and deliver

Render or open the final SVG and compare it with the untouched source. Validation proves structural invariants, not visual fidelity. Deliver the SVG even when Illustrator is not available; SVG remains editable in Illustrator, Inkscape, Figma, and compatible tools.

When the user explicitly requests Illustrator insertion, follow `illustrator.md` after SVG validation.
