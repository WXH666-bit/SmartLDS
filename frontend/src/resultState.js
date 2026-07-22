export function isFieldRowFound(info = {}, display = '') {
  if (info?.status !== 'not_found') return true
  return String(display ?? '').trim().length > 0
}

function templateNameSet(templates = []) {
  return new Set(
    (templates || [])
      .map(template => (typeof template === 'string' ? template : template?.name))
      .map(name => String(name ?? '').trim())
      .filter(Boolean)
  )
}

export function isFeedbackCreateConflict({ mode = 'merge', templateName = '', templates = [] } = {}) {
  if (String(mode || '').toLowerCase() !== 'create') return false
  const name = String(templateName ?? '').trim()
  return !!name && templateNameSet(templates).has(name)
}

export function resolveFeedbackDefaults({ metaTemplate = '', templates = [], suggestedName = '' } = {}) {
  const names = templateNameSet(templates)
  const current = String(metaTemplate ?? '').trim()
  const suggested = String(suggestedName ?? '').trim()
  if (current && current !== 'unknown' && names.has(current)) {
    return { mode: 'merge', templateName: current }
  }
  if (suggested && names.has(suggested)) {
    return { mode: 'merge', templateName: suggested }
  }
  return { mode: 'create', templateName: suggested }
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

function normalizeRect(rect) {
  if (!Array.isArray(rect) || rect.length !== 4) return null
  const values = rect.map(value => Number(value))
  if (values.some(value => !Number.isFinite(value))) return null
  const [x1, y1, x2, y2] = values
  if (x2 <= x1 || y2 <= y1) return null
  return values
}

function rectCenter(rect) {
  return {
    x: (rect[0] + rect[2]) / 2,
    y: (rect[1] + rect[3]) / 2,
  }
}

export function inferFieldPosition(anchorRect, valueRect) {
  const anchor = normalizeRect(anchorRect)
  const value = normalizeRect(valueRect)
  if (!anchor || !value) return ''
  const anchorHeight = Math.max(anchor[3] - anchor[1], 5)
  const anchorCenterY = (anchor[1] + anchor[3]) / 2
  const valueCenterY = (value[1] + value[3]) / 2
  if (value[0] >= anchor[2] - 5 && Math.abs(valueCenterY - anchorCenterY) <= anchorHeight * 1.4) {
    return 'right'
  }
  if (value[1] >= anchor[3] - 5) return 'below'
  return 'right'
}

export function buildLearnedValueOffset(anchorRect, valueRect) {
  const anchor = normalizeRect(anchorRect)
  const value = normalizeRect(valueRect)
  if (!anchor || !value) return null
  const anchorCenter = rectCenter(anchor)
  const valueCenter = rectCenter(value)
  const valueWidth = Math.max(value[2] - value[0], 5)
  const valueHeight = Math.max(value[3] - value[1], 5)
  const anchorHeight = Math.max(anchor[3] - anchor[1], 5)
  return {
    dx: Number((valueCenter.x - anchorCenter.x).toFixed(2)),
    dy: Number((valueCenter.y - anchorCenter.y).toFixed(2)),
    tolerance_x: Number(Math.max(valueWidth * 1.8, 80).toFixed(2)),
    tolerance_y: Number(Math.max(valueHeight * 1.8, anchorHeight * 1.8, 45).toFixed(2)),
  }
}

export function inferManualFieldBinding(anchorBlock = null, valueBlock = null) {
  const anchorRect = normalizeRect(anchorBlock?.rect)
  const valueRect = normalizeRect(valueBlock?.rect)
  const binding = {}
  if (anchorBlock?.text) {
    binding.anchorText = String(anchorBlock.text).trim()
    binding.label = binding.anchorText
  }
  if (valueBlock?.text) binding.value = String(valueBlock.text).trim()
  if (anchorRect) binding.anchorRect = anchorRect
  if (valueRect) binding.valueRect = valueRect
  const offset = buildLearnedValueOffset(anchorRect, valueRect)
  if (offset) {
    binding.position = inferFieldPosition(anchorRect, valueRect)
    binding.learnedValueOffset = offset
  }
  return binding
}

export function applyManualFieldBindingDraft(fieldDraft = {}, binding = {}) {
  if (binding.label && !String(fieldDraft.label ?? '').trim()) {
    fieldDraft.label = binding.label
  }
  if (binding.value) fieldDraft.value = binding.value
  fieldDraft.anchorText = binding.anchorText || ''
  fieldDraft.anchorRect = binding.anchorRect || null
  fieldDraft.valueRect = binding.valueRect || null
  fieldDraft.position = binding.position || ''
  fieldDraft.learnedValueOffset = binding.learnedValueOffset || null
  return fieldDraft
}

export function buildManualFieldPayload(row = {}) {
  const payload = {
    key: row.name,
    label: row.label,
    value: String(row.display ?? ''),
  }
  if (row.anchorText) payload.anchor_text = String(row.anchorText).trim()
  const anchorRect = normalizeRect(row.anchorRect)
  const valueRect = normalizeRect(row.valueRect)
  if (anchorRect) payload.anchor_rect = anchorRect
  if (valueRect) payload.value_rect = valueRect
  const offset = row.learnedValueOffset || buildLearnedValueOffset(anchorRect, valueRect)
  if (offset) payload.learned_value_offset = offset
  const position = row.position || inferFieldPosition(anchorRect, valueRect)
  if (position) payload.position = position
  return payload
}

export function buildVisibleFieldRows(fieldRows = []) {
  return (fieldRows || []).filter(row => !row?.excluded)
}

export function buildExcludedFieldRows(fieldRows = []) {
  return (fieldRows || []).filter(row => !!row?.excluded)
}

export function buildFeedbackFieldOptions(fieldRows = []) {
  return buildVisibleFieldRows(fieldRows)
    .filter(row => row?.found && String(row.display || '').trim())
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
  const excludedFields = []

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
    if (row.excluded) {
      fields[name].excluded = true
      excludedFields.push(name)
    } else {
      delete fields[name].excluded
    }
    if (!!row.excluded !== !!row._originalExcluded) hasUnsaved = true
    if (row._originalLabel !== undefined && fields[name].label !== row._originalLabel) {
      fields[name].label_corrected = true
      hasUnsaved = true
    }

    if (row.manual) {
      fields[name].source = 'manual'
      fields[name].confidence = 1.0
      const manualPayload = buildManualFieldPayload(row)
      if (manualPayload.anchor_text) {
        fields[name].anchor = manualPayload.anchor_text
        fields[name].anchor_text = manualPayload.anchor_text
      }
      if (manualPayload.anchor_rect) fields[name].anchor_rect = manualPayload.anchor_rect
      if (manualPayload.value_rect) {
        fields[name].value_rect = manualPayload.value_rect
        fields[name].rect = manualPayload.value_rect
      }
      if (manualPayload.position) fields[name].position = manualPayload.position
      if (manualPayload.learned_value_offset) fields[name].learned_value_offset = manualPayload.learned_value_offset
    }
  }

  preview.fields = fields
  if (excludedFields.length) preview.excluded_fields = excludedFields
  else delete preview.excluded_fields

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
    .filter(row => !row?.excluded && row?.found && String(row.display ?? '').trim())
    .map(row => ({
      label: row.label || row.name || '',
      value: String(row.display ?? ''),
      status: row.status || '',
      confidence: row.confidence || '',
    }))
}

export function appendSessionLog(logs = [], entry = {}, limit = 80) {
  const level = ['success', 'warning', 'error', 'info'].includes(entry.level) ? entry.level : 'info'
  logs.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    time: new Date().toLocaleTimeString(),
    level,
    source: String(entry.source || '系统'),
    title: String(entry.title || ''),
    detail: String(entry.detail || ''),
    jobId: entry.jobId || '',
    template: entry.template || '',
  })
  while (logs.length > limit) logs.shift()
  return logs
}

export function buildWarningLogEntries(warnings = [], source = '系统', context = {}) {
  return (warnings || [])
    .map(warning => String(warning || '').trim())
    .filter(Boolean)
    .map(warning => ({
      level: 'warning',
      source,
      title: warning,
      detail: warning,
      jobId: context.jobId || '',
      template: context.template || '',
    }))
}
