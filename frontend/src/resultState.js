export function isFieldRowFound(info = {}, display = '') {
  if (info?.status !== 'not_found') return true
  return String(display ?? '').trim().length > 0
}

export function finishFieldEdit(row) {
  row.display = row.editVal
  row.editing = false
  row.found = isFieldRowFound({ status: row.status }, row.display)
  return row
}

export function finishFieldLabelEdit(row) {
  const nextLabel = String(row.labelEditVal ?? '').trim()
  if (nextLabel) row.label = nextLabel
  row.labelEditing = false
  return row
}

export function buildResultPreview(result = {}, fieldRows = [], tableData = null) {
  const preview = JSON.parse(JSON.stringify(result || {}))
  const fields = preview.fields && typeof preview.fields === 'object' ? preview.fields : {}
  let hasUnsaved = false

  for (const row of fieldRows || []) {
    const name = row?.name
    if (!name) continue
    const display = String(row.display ?? '')
    const existing = fields[name] && typeof fields[name] === 'object' ? fields[name] : {}
    const valueChanged = display !== String(row._original ?? '')
    if (valueChanged) hasUnsaved = true

    const nextStatus = row.manual
      ? 'manual_added'
      : display.trim()
        ? (existing.status === 'not_found' || valueChanged ? 'corrected' : (existing.status || 'extracted'))
        : (existing.status || 'not_found')

    fields[name] = {
      ...existing,
      label: row.label || existing.label || name,
      value: display,
      cleaned: display,
      corrected: valueChanged || existing.corrected !== undefined ? display : existing.corrected,
      status: nextStatus,
    }
    if (row._originalLabel !== undefined && row.label !== row._originalLabel) {
      fields[name].label_corrected = true
      hasUnsaved = true
    }

    if (row.manual) {
      fields[name].source = 'manual'
      fields[name].confidence = 1.0
    }
  }

  preview.fields = fields

  if (tableData?.headers) {
    preview.table = preview.table && typeof preview.table === 'object' ? preview.table : {}
    preview.table.headers = [...(tableData.headers || [])]
    preview.table.rows = (tableData.rows || []).map(row =>
      preview.table.headers.map((_, index) => String(row?.[String(index)] ?? ''))
    )
    if (tableData.source) preview.table.source = tableData.source
  }

  preview.meta = preview.meta && typeof preview.meta === 'object' ? preview.meta : {}
  if (hasUnsaved) preview.meta.preview_unsaved = true
  else delete preview.meta.preview_unsaved

  return preview
}

export function buildResultPreviewJson(result = {}, fieldRows = [], tableData = null) {
  return JSON.stringify(buildResultPreview(result, fieldRows, tableData), null, 2)
}
