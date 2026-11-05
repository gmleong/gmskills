# Text manifest schema

Use UTF-8 JSON with `schema_version` set to `1.0` and a `text_elements` array. Coordinates are in the SVG viewBox coordinate system. For a source image with no custom viewBox, pixel coordinates map directly.

```json
{
  "schema_version": "1.0",
  "text_elements": [
    {
      "id": "title-1",
      "text": "Editable title",
      "x": 120,
      "y": 48,
      "bbox": [70, 28, 100, 26],
      "font_family": "Arial",
      "font_size": 18,
      "font_weight": "700",
      "font_style": "normal",
      "fill": "#172033",
      "opacity": 1,
      "rotation": 0,
      "text_anchor": "middle",
      "line_height": 1.2,
      "letter_spacing": 0,
      "paint_order": 12
    }
  ]
}
```

Required per item: `text`, `x`, `y`, `font_size`, and `paint_order`.

- `bbox` is `[x, y, width, height]` and is retained as audit metadata.
- `opacity` is from `0` to `1`.
- `text_anchor` is `start`, `middle`, or `end`.
- `rotation` is clockwise degrees around `(x, y)`.
- Use `\n` inside `text` for line breaks.
- Keep the original wording, capitalization, punctuation, and line breaks.
- Use a stable unique `id` when possible.

Run `validate_manifest.py` before merging. The validator rejects missing fields, duplicate IDs, invalid coordinates, unsafe colors, and unsupported anchors.
