# Semantic decomposition playbooks

Use this reference for scientific figures, cell diagrams, and cartoon illustrations. The analysis bundle supplies visual evidence and region proposals; it does not supply semantic truth.

## Shared method

1. Inspect the untouched source and `analysis/evidence-sheet.png` at full canvas and detail scale.
2. Confirm the domain. Never accept the heuristic domain label without visual confirmation.
3. Inventory the image in five passes: canvas/panels, major subjects, internal parts, connectors/annotations, text/legends.
4. Give each meaningful object a stable id, a parent, paint order, confidence, and concrete evidence. Use candidate region ids such as `visual:R014` when useful; `container_candidates` can suggest nesting and `repeated_region_families` can suggest repeated instances, but both require visual confirmation. Also describe visible shape, color, position, or text.
5. Record overlap explicitly. `occluded_by` means the named object must be painted later. Do not invent hidden geometry unless a complete editable object is necessary; label inferred geometry as such.
6. Review all low-confidence required elements before authoring SVG. If ambiguity remains, preserve the visible geometry and use a neutral description instead of asserting an unsupported identity.
7. Build SVG in semantic passes and run the quality gate after every major pass.

Do not combine repeated objects into a single semantic id. Reuse geometry through SVG groups or symbols only after each instance retains a distinct `id` or `data-source-id`.

## Scientific figures

Inventory in this order:

- panel backgrounds, separators, frames, titles, and panel letters;
- axes, ticks, grids, legends, scales, and units;
- primary experimental subjects or mechanisms;
- arrows and connectors, including direction and endpoint;
- labels, captions inside the figure, symbols, and repeated markers.

Treat arrows and text as separate objects. Use `points_to` from the arrow to its target and `labels` from live text to the subject it names. Do not merge axis lines, ticks, or legend swatches into a traced blob. Preserve every panel even when panels repeat.

## Cell diagrams

Inventory spatial containment before naming organelles:

- extracellular background and cell boundary;
- cytoplasm and nucleus/nucleolus;
- visually distinct membranes, compartments, vesicles, filaments, and organelles;
- repeated particles or organelles as separate instances;
- membrane crossings, transport arrows, receptors, labels, and legends.

Use `parent_id` and `contains` to express compartments. Use `connects` or `points_to` for pathways. If an internal body could be several organelles, describe it by visible morphology and lower confidence rather than guessing. A scientific name is allowed only when text, morphology, or context supports it.

Before acceptance, count repeated structures in the source and manifest independently. Check that every arrow has a direction, every label has a target when one is visible, and every nested object is inside the correct SVG group.

## Cartoon illustrations

Inventory by occlusion and character anatomy:

- background and large silhouette;
- hair/back shapes, head, neck, torso, limbs, and clothing;
- facial features as separate objects: brows, eye whites, irises, pupils, highlights, nose, mouth;
- foreground hair locks, accessories, contour strokes, highlights, and shadows;
- repeated paired features as distinct left/right objects.

Separate filled silhouettes from contour strokes. Do not let a whole-image trace determine semantic grouping. Record `occluded_by` for foreground hair, hands, clothing, and accessories. Preserve intentional asymmetry; do not mirror one side merely because the subject is approximately symmetric.

## Review thresholds

- `confidence >= 0.90`: directly visible and unambiguous.
- `0.70–0.89`: likely, but confirm against the source during visual review.
- `< 0.70`: uncertain. A required element must be reviewed and either renamed neutrally, corrected, or explicitly disclosed.

Confidence is evidence tracking, not a claim of calibrated model probability.
