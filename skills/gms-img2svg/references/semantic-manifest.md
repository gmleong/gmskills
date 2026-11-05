# Semantic manifest

Create this manifest before reconstructing a reference image. It is an object inventory and completeness contract, not a generated description.

```json
{
  "schema_version": "1.1",
  "source": "/absolute/path/source.png",
  "domain": "cell",
  "canvas": {"width": 1600, "height": 1200},
  "elements": [
    {
      "id": "cell-membrane",
      "role": "subject",
      "bbox": [140, 120, 960, 820],
      "z_index": 10,
      "render_as": "path",
      "required": true,
      "description": "outer cell membrane",
      "confidence": 0.98,
      "evidence": ["visual:R002", "continuous outer boundary"]
    },
    {
      "id": "nucleus-arrow",
      "role": "arrow",
      "bbox": [900, 370, 220, 24],
      "z_index": 30,
      "render_as": "path",
      "required": true,
      "description": "connector pointing from the label to the nucleus",
      "confidence": 0.96,
      "evidence": ["visible arrowhead points toward nucleus"]
    },
    {
      "id": "label-nucleus",
      "role": "text",
      "bbox": [1120, 360, 180, 48],
      "z_index": 40,
      "render_as": "live_text",
      "required": true,
      "description": "Nucleus",
      "confidence": 0.99,
      "evidence": ["visible text: Nucleus"]
    }
  ],
  "relationships": [
    {"type": "connects", "from": "label-nucleus", "to": "nucleus-arrow"}
  ]
}
```

## Rules

- Use `schema_version: "1.1"` for new work. Version 1.0 remains accepted only for old jobs.
- `domain` is `scientific`, `cell`, `cartoon`, or `mixed`.
- `canvas.width` and `canvas.height` use the source-image coordinate system.
- `id` is stable and unique. Use lowercase ASCII letters, digits, `_`, `.`, or `-`.
- `role` is one of `background`, `subject`, `organelle`, `connector`, `arrow`, `frame`, `axis`, `legend`, `text`, `decoration`, or `other`.
- `bbox` is `[x, y, width, height]` in source coordinates and must stay inside the canvas.
- `z_index` describes bottom-to-top paint order. Equal values are allowed for peers.
- `render_as` is `group`, `path`, `primitive`, or `live_text`. Raster output is not allowed.
- `required` defaults to `true`. Use `false` only for genuinely optional visual noise.
- `confidence` is a visual-review confidence from 0 to 1, not a calibrated model probability.
- `evidence` is a non-empty list of visible reasons. Reference candidate regions from `analysis.json` when useful, but do not use a region id as the only evidence for a biological identity.
- `parent_id` names the semantic container. The SVG object must be nested under the corresponding SVG group.
- `occluded_by` lists objects that paint above this object.
- Every required element must appear in the Master SVG with the same `id`, or as `data-source-id` when one semantic object requires several SVG nodes.
- A `text` role must use `live_text` and must map to a real SVG `<text>` element.
- Record repeated organelles, particles, cells, arrows, and markers as separate elements rather than one combined blob.
- Relationship types are `contains`, `part_of`, `connects`, `points_to`, `labels`, `occludes`, `overlaps`, `repeated_with`, and `aligned_with`.

The manifest should be detailed enough that a reviewer can detect an omitted scientific structure without reopening the source image.

## Executable scenes

Use `build_scene.py` or `run_pipeline.py --scene` when the inventory can describe native primitives, paths and text directly. This avoids a new drawing program for each image. The same schema 1.1 manifest gains `review_status: "reviewed"`, `source_sha256` (the untouched source), optional `gradients`, and a `geometry` field on each element:

```json
{
  "id": "cell-body",
  "role": "subject",
  "render_as": "primitive",
  "bbox": [20, 20, 120, 80],
  "z_index": 1,
  "description": "Visible elliptical cell boundary",
  "confidence": 0.96,
  "evidence": ["Smooth elliptical outline in the reference"],
  "geometry": {
    "tag": "ellipse",
    "attrs": {"cx": 80, "cy": 60, "rx": 60, "ry": 40, "fill": "url(#cell-paint)"}
  }
}
```

`geometry` has `tag`, optional `attrs`, optional `text`, and optional `children` (geometry objects). Supported shapes are `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, and `path`. Use `text`/`tspan` for original wording and line breaks. For a semantic `group`, omit geometry or use `{"tag":"g", ...}`; children that need separate editing/relationships belong in `elements` with `parent_id`, not anonymous geometry. The builder assigns semantic IDs and roles, nests objects by `parent_id`, and orders siblings by `z_index`; an impossible interleaved hierarchy is rejected.

An optional top-level gradient declaration:

```json
{"gradients": [{
  "id": "cell-paint", "tag": "radialGradient",
  "attrs": {"gradientUnits": "userSpaceOnUse", "cx": 80, "cy": 60, "r": 60},
  "stops": [{"offset": 0, "stop-color": "#eff6ff"},
            {"offset": 1, "stop-color": "#93c5fd"}]
}]}
```

The builder uses a strict geometry/attribute whitelist, validates SVG and semantic relationships, and writes `reconstructed.svg` plus a manifest to a new directory. It does not infer geometry or recognize text. Scenes marked as drafts cannot build. Codex reviews the untouched source and records the evidence; changing a status flag alone is not visual review. Legacy manifests without a review field remain accepted for existing jobs.
