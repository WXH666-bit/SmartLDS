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

function roundUnit(value) {
  return Math.round(value * 10000) / 10000
}

function normalizeImageSize(imageSize) {
  if (!Array.isArray(imageSize) || imageSize.length < 2) return null
  const width = Number(imageSize[0])
  const height = Number(imageSize[1])
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null
  return { width, height }
}

const MIN_TABLE_LAYOUT_HEIGHT_RATIO = 0.035
const TABLE_LAYOUT_X_PADDING_RATIO = 0.03
const TABLE_LAYOUT_Y_PADDING_RATIO = 0.025

export function buildTableLayoutDraft(headers = [], blocks = [], imageSize = null) {
  const cleanHeaders = (headers || []).map(header => String(header || '').trim()).filter(Boolean)
  const size = normalizeImageSize(imageSize)
  const usableBlocks = (blocks || [])
    .map(block => ({ text: String(block?.text || '').trim(), rect: normalizeRect(block?.rect) }))
    .filter(block => block.text && block.rect)
  if (!cleanHeaders.length || !size || !usableBlocks.length) return null

  const xs1 = usableBlocks.map(block => block.rect[0])
  const ys1 = usableBlocks.map(block => block.rect[1])
  const xs2 = usableBlocks.map(block => block.rect[2])
  const ys2 = usableBlocks.map(block => block.rect[3])
  const minX = Math.min(...xs1)
  const minY = Math.min(...ys1)
  const maxX = Math.max(...xs2)
  const maxY = Math.max(...ys2)
  if (maxX <= minX || maxY <= minY) return null
  if ((maxY - minY) / size.height < MIN_TABLE_LAYOUT_HEIGHT_RATIO) return null
  const regionMinX = Math.max(0, minX - size.width * TABLE_LAYOUT_X_PADDING_RATIO)
  const regionMinY = Math.max(0, minY - size.height * TABLE_LAYOUT_Y_PADDING_RATIO)
  const regionMaxX = Math.min(size.width, maxX + size.width * TABLE_LAYOUT_X_PADDING_RATIO)
  const regionMaxY = Math.min(size.height, maxY + size.height * TABLE_LAYOUT_Y_PADDING_RATIO)

  const headerBlocks = cleanHeaders.map(header => {
    const needle = header.replace(/\s+/g, '').toUpperCase()
    return usableBlocks.find(block => {
      const haystack = block.text.replace(/\s+/g, '').toUpperCase()
      return needle && (haystack.includes(needle) || needle.includes(haystack))
    })
  })

  const allHeadersMatched = headerBlocks.length === cleanHeaders.length && headerBlocks.every(Boolean)
  const headerCenters = allHeadersMatched
    ? headerBlocks.map(block => rectCenter(block.rect).x)
    : []
  const columns = cleanHeaders.map((header, index) => {
    if (allHeadersMatched) {
      const left = index === 0 ? regionMinX : (headerCenters[index - 1] + headerCenters[index]) / 2
      const right = index === cleanHeaders.length - 1 ? regionMaxX : (headerCenters[index] + headerCenters[index + 1]) / 2
      return { header, x1: roundUnit(left / size.width), x2: roundUnit(right / size.width) }
    }
    const step = (regionMaxX - regionMinX) / cleanHeaders.length
    return {
      header,
      x1: roundUnit((regionMinX + index * step) / size.width),
      x2: roundUnit((regionMinX + (index + 1) * step) / size.width),
    }
  })

  const anchors = headerBlocks
    .filter(Boolean)
    .map(block => {
      const center = rectCenter(block.rect)
      return {
        text: block.text,
        x: roundUnit(center.x / size.width),
        y: roundUnit(center.y / size.height),
      }
    })

  const layout = {
    mode: 'anchor_region',
    headers: cleanHeaders,
    region: {
      x1: roundUnit(regionMinX / size.width),
      y1: roundUnit(regionMinY / size.height),
      x2: roundUnit(regionMaxX / size.width),
      y2: roundUnit(regionMaxY / size.height),
    },
    columns,
  }
  if (anchors.length) layout.anchors = anchors
  return layout
}

export function relabelTableLayout(layout, headers = []) {
  if (!layout || typeof layout !== 'object') return null
  const cleanHeaders = (headers || []).map(header => String(header || '').trim()).filter(Boolean)
  const layoutHeaders = (layout.headers || []).map(header => String(header || '').trim()).filter(Boolean)
  if (!cleanHeaders.length || layoutHeaders.length !== cleanHeaders.length) return null

  const next = {
    ...layout,
    headers: cleanHeaders,
    columns: (layout.columns || []).map((column, index) => ({
      ...column,
      header: cleanHeaders[index] || String(column?.header || '').trim(),
    })),
  }
  if (next.columns.length && next.columns.length !== cleanHeaders.length) return null
  return next
}

export function fillTableEditorTextDraft(tableEditor, target, text) {
  const value = String(text || '').trim()
  if (!value || !tableEditor || !target) return false
  const colIndex = Number(target.colIndex)
  if (!Number.isInteger(colIndex)) return false

  if (target.type === 'header') {
    if (!Array.isArray(tableEditor.headers) || colIndex < 0 || colIndex >= tableEditor.headers.length) return false
    tableEditor.headers[colIndex] = value
    return true
  }

  if (target.type === 'cell') {
    const rowIndex = Number(target.rowIndex)
    if (!Number.isInteger(rowIndex) || !Array.isArray(tableEditor.rows)) return false
    const row = tableEditor.rows[rowIndex]
    if (!Array.isArray(row) || colIndex < 0 || colIndex >= row.length) return false
    row[colIndex] = value
    return true
  }

  return false
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

export function getActiveFieldEditJsonTarget(fieldRows = []) {
  const activeRow = (fieldRows || []).find(row => row?.labelEditing || row?.editing)
  if (!activeRow?.name) return null
  const target = {
    type: 'field',
    fieldKey: activeRow.name,
    fieldLabel: activeRow.label || activeRow.labelEditVal || '',
    prop: activeRow.labelEditing ? 'label' : 'value',
  }
  const fieldValue = activeRow.editing ? activeRow.editVal : activeRow.display
  if (fieldValue !== undefined) target.fieldValue = fieldValue
  return target
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
    layout: table.layout || null,
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
    if (tableData.layout) {
      preview.table.layout = tableData.layout
      preview.table_layout = tableData.layout
    }
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
  const fieldIndent = lines[startIndex]?.search(/\S/) ?? -1
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const trimmed = lines[index].trim()
    const indent = lines[index].search(/\S/)
    if (indent >= 0 && indent <= fieldIndent && trimmed.startsWith('}')) return -1
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

function findFieldKeyByLabel(jsonText, fieldLabel) {
  const label = String(fieldLabel ?? '').trim()
  if (!label) return ''
  try {
    const parsed = JSON.parse(String(jsonText ?? '{}'))
    const fields = parsed?.fields && typeof parsed.fields === 'object' ? parsed.fields : {}
    const entry = Object.entries(fields).find(([key, info]) =>
      key === label
      || String(info?.label ?? '').trim() === label
      || String(info?.canonical_key ?? '').trim() === label
    )
    return entry?.[0] || ''
  } catch {
    return ''
  }
}

function findPropertyValueLine(lines, prop, value) {
  if (value === undefined || value === null) return -1
  const propToken = `${JSON.stringify(String(prop))}:`
  const valueText = JSON.stringify(String(value))
  return lines.findIndex(line => {
    const trimmed = line.trim()
    return trimmed.startsWith(propToken) && trimmed.includes(valueText)
  })
}

export function findJsonPreviewTargetLine(jsonText = '', target = {}) {
  const lines = splitJsonPreviewLines(jsonText)
  if (!lines.length || !target?.type) return -1

  if (target.type === 'field') {
    let fieldIndex = findFieldObjectLine(lines, target.fieldKey)
    if (fieldIndex < 0 && target.fieldLabel) {
      const labelKey = findFieldKeyByLabel(jsonText, target.fieldLabel)
      if (labelKey) fieldIndex = findFieldObjectLine(lines, labelKey)
    }
    if (fieldIndex < 0) return findPropertyValueLine(lines, target.prop, target.fieldValue)
    if (!target.prop) return fieldIndex
    const propIndex = findPropertyLine(lines, fieldIndex, target.prop)
    if (propIndex >= 0) return propIndex
    const valueIndex = findPropertyValueLine(lines, target.prop, target.fieldValue)
    return valueIndex >= 0 ? valueIndex : fieldIndex
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
