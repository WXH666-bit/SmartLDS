# Table Layout Feedback Learning Design

## Goal

When normal OCR detects table text but fails to reconstruct a table, a user can manually add or correct the table once, feed it back, and later recognitions of the same layout can rebuild the table from similar OCR block positions.

This feature learns table structure, not table row content. It depends on OCR text blocks still being present in the table area.

## Scope

In scope:

- Save a learned table layout from manual table correction.
- Store normalized table region coordinates, column x ranges, headers, and optional anchor texts in the template.
- Use the learned layout as a fallback when the normal table extractor returns no usable table or misses table headers.
- Keep the UI lightweight by reusing OCR block selection where possible.

Out of scope:

- Training a new OCR model.
- Learning exact row contents.
- Supporting multi-page table continuation.
- Complex merged-cell reconstruction.

## User Flow

1. The user recognizes a document.
2. If the table is missing or wrong, the user opens the table editor.
3. The user enters or fixes table headers and rows.
4. The user binds the table area by selecting OCR blocks that belong to the table. The frontend computes a bounding region from those blocks.
5. The user starts feedback and keeps "include table" enabled.
6. The backend saves the manual table patch and learned layout into the target template.
7. Future recognition first tries the normal table extractor. If it fails, the learned table layout reconstructs the table from OCR blocks in the learned region.

## Template Shape

```yaml
table_layout:
  mode: anchor_region
  headers: ["Description", "Qty", "Weight"]
  region:
    x1: 0.08
    y1: 0.48
    x2: 0.92
    y2: 0.82
  columns:
    - header: "Description"
      x1: 0.08
      x2: 0.46
    - header: "Qty"
      x1: 0.46
      x2: 0.62
    - header: "Weight"
      x1: 0.62
      x2: 0.92
  anchors:
    - text: "Description"
      x: 0.1
      y: 0.5
```

Coordinates are normalized to the page image size so the layout can tolerate different render resolutions.

## Frontend Changes

- Add a lightweight "bind table area" action in the table editor.
- Let the user select OCR blocks for the table area.
- Compute `table_layout.region` from the selected block rectangles.
- Infer column ranges from selected header blocks when possible. If header blocks are not selected, infer ranges evenly from the current table headers.
- Send the layout inside `table_patch.layout` during correction save.
- Show a compact note when a table layout has been bound.

## Backend Changes

- Extend correction payload normalization to accept `table_patch.layout`.
- Preserve the layout in `apply_corrections`.
- In `/api/fewshot/from-result`, when `include_table` is true, merge `final_result.table_layout` into the template.
- Add a `learned_table_layout` fallback in `field_extractor`.
- The fallback filters OCR blocks to the learned region, clusters by y coordinate into rows, assigns cells by column x ranges, and returns a table with learned headers.

## Error Handling

- If no table headers exist, feedback still warns that there is no usable table structure.
- If a layout is missing or invalid, recognition falls back to current behavior.
- If the learned region has too few OCR blocks on a future document, recognition keeps the normal table result or returns no table.
- Warnings should be surfaced in the existing session log.

## Testing

- Unit test correction normalization keeps `table_patch.layout`.
- API test feedback saves `table_layout` into the template.
- Extractor test learned layout reconstructs a table from OCR blocks when normal table extraction fails.
- Frontend state test table patch can carry layout metadata.
