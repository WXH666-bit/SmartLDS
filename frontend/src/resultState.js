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

function normalizeDisplayTable(table = {}) {
  const headers = Array.isArray(table.headers)
    ? table.headers.map(header => String(header ?? '').trim()).filter(Boolean)
    : []
  const rows = Array.isArray(table.rows)
    ? table.rows.map(row => {
      const objectRow = {}
      headers.forEach((_, index) => {
        objectRow[String(index)] = String(Array.isArray(row) ? row[index] ?? '' : row?.[String(index)] ?? '')
      })
      return objectRow
    })
    : []
  return {
    title: String(table.title ?? '').trim(),
    headers,
    rows,
    source: table.source || '',
    confidence: table.confidence,
  }
}

export function buildDisplayTables(result = {}) {
  const rawTables = Array.isArray(result.tables) && result.tables.length
    ? result.tables
    : (result.table ? [result.table] : [])
  return rawTables
    .map(table => normalizeDisplayTable(table))
    .filter(table => table.headers.length || table.rows.length)
}

export function buildResultPreview(result = {}, fieldRows = [], tableData = null) {
  const preview = JSON.parse(JSON.stringify(result || {}))
  const fields = preview.fields && typeof preview.fields === 'object' ? preview.fields : {}
  let hasUnsaved = false

  for (const row of fieldRows || []) {
    const name = row?.name
    if (!name) continue
    const display = String(row.editing ? row.editVal ?? '' : row.display ?? '')
    const label = String(row.labelEditing ? row.labelEditVal ?? '' : row.label ?? '').trim()
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
      label: label || row.label || existing.label || name,
      value: display,
      cleaned: display,
      corrected: valueChanged || existing.corrected !== undefined ? display : existing.corrected,
      status: nextStatus,
    }
    if (row._originalLabel !== undefined && fields[name].label !== row._originalLabel) {
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
    preview.table.title = tableData.title || preview.table.title || ''
    preview.table.headers = [...(tableData.headers || [])]
    preview.table.rows = (tableData.rows || []).map(row =>
      preview.table.headers.map((_, index) => String(row?.[String(index)] ?? ''))
    )
    if (tableData.source) preview.table.source = tableData.source
    if (Array.isArray(preview.tables) && preview.tables.length) {
      preview.tables[0] = { ...preview.tables[0], ...preview.table }
    } else if (preview.table.headers.length || preview.table.rows.length) {
      preview.tables = [{ ...preview.table }]
    }
  }

  preview.meta = preview.meta && typeof preview.meta === 'object' ? preview.meta : {}
  if (hasUnsaved) preview.meta.preview_unsaved = true
  else delete preview.meta.preview_unsaved

  return preview
}

export function buildResultPreviewJson(result = {}, fieldRows = [], tableData = null) {
  return JSON.stringify(buildResultPreview(result, fieldRows, tableData), null, 2)
}

export function splitJsonPreviewLines(jsonText = '') {
  const text = String(jsonText ?? '')
  return text ? text.split('\n') : []
}

function findPropertyLine(lines, startIndex, prop) {
  const propToken = `${JSON.stringify(String(prop))}:`
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const trimmed = lines[index].trim()
    if (trimmed === '},' || trimmed === '}') return -1
    if (trimmed.startsWith(propToken)) return index
  }
  return -1
}

function findFieldObjectLine(lines, fieldKey) {
  const fieldToken = `${JSON.stringify(String(fieldKey))}:`
  const fieldsToken = '"fields":'
  const fieldsIndex = lines.findIndex(line => line.trim().startsWith(fieldsToken))
  if (fieldsIndex < 0) return -1
  const fieldsIndent = lines[fieldsIndex].search(/\S/)
  for (let index = fieldsIndex + 1; index < lines.length; index += 1) {
    const trimmed = lines[index].trim()
    const indent = lines[index].search(/\S/)
    if (indent <= fieldsIndent && trimmed.startsWith('}')) return -1
    if (trimmed.startsWith(fieldToken)) return index
  }
  return -1
}

export function findJsonPreviewTargetLine(jsonText = '', target = {}) {
  const lines = splitJsonPreviewLines(jsonText)
  if (!lines.length || !target?.type) return -1

  if (target.type === 'field') {
    const fieldIndex = findFieldObjectLine(lines, target.fieldKey)
    if (fieldIndex < 0) return -1
    if (!target.prop) return fieldIndex
    const propIndex = findPropertyLine(lines, fieldIndex, target.prop)
    return propIndex >= 0 ? propIndex : fieldIndex
  }

  if (target.type === 'table') {
    const tableIndex = lines.findIndex(line => line.trim().startsWith('"table":'))
    if (tableIndex >= 0) return tableIndex
    return lines.findIndex(line => line.trim().startsWith('"tables":'))
  }

  return -1
}

export function buildFieldValueRows(fieldRows = []) {
  return (fieldRows || [])
    .filter(row => row?.found && String(row.display ?? '').trim())
    .map(row => ({
      label: row.label || row.name || '',
      value: String(row.display ?? ''),
      status: row.status || '',
      confidence: row.confidence || '',
    }))
}
