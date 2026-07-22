import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  buildDisplayTables,
  buildExcludedFieldRows,
  buildFeedbackFieldOptions,
  buildManualFieldPayload,
  buildTableLayoutDraft,
  relabelTableLayout,
  applyManualFieldBindingDraft,
  appendSessionLog,
  buildWarningLogEntries,
  buildResultPreviewJson,
  buildVisibleFieldRows,
  getActiveFieldEditJsonTarget,
  inferManualFieldBinding,
  findJsonPreviewTargetLine,
  finishFieldEdit,
  finishFieldLabelEdit,
  isFieldRowFound,
  isFeedbackCreateConflict,
  resolveFeedbackDefaults,
  splitJsonPreviewLines,
} from '../frontend/src/resultState.js'

assert.deepEqual(
  resolveFeedbackDefaults({
    metaTemplate: 'unknown',
    templates: [{ name: 'bol_201_template' }],
    suggestedName: 'bol_201_template',
  }),
  { mode: 'merge', templateName: 'bol_201_template' },
  '未知版式反哺时，如果自动建议名已存在，应默认合并已有版式，避免创建重名失败'
)

assert.deepEqual(
  resolveFeedbackDefaults({
    metaTemplate: 'unknown',
    templates: [{ name: 'bol_201_template' }],
    suggestedName: 'bol_202_template',
  }),
  { mode: 'create', templateName: 'bol_202_template' },
  '建议名不存在时仍应默认创建新版式'
)

assert.equal(
  isFeedbackCreateConflict({
    mode: 'create',
    templateName: 'bol_201_template',
    templates: [{ name: 'bol_201_template' }],
  }),
  true,
  '创建模式下使用已有版式名应被前端提前识别为冲突'
)

assert.equal(
  isFeedbackCreateConflict({
    mode: 'merge',
    templateName: 'bol_201_template',
    templates: [{ name: 'bol_201_template' }],
  }),
  false,
  '合并模式使用已有版式名不应被识别为冲突'
)

assert.equal(
  isFieldRowFound({ status: 'not_found' }, ''),
  false,
  'not_found 且没有值时应继续显示为未识别'
)

assert.equal(
  isFieldRowFound({ status: 'not_found' }, '韩国'),
  true,
  'not_found 字段被用户填值后应显示为已填/亮起'
)

assert.equal(
  isFieldRowFound({ status: 'extracted' }, ''),
  true,
  '已识别字段即使值为空也不应该按未识别灰掉'
)

const row = {
  status: 'not_found',
  found: false,
  display: '',
  editVal: '纺织品',
  editing: true,
}
finishFieldEdit(row)
assert.equal(row.display, '纺织品')
assert.equal(row.editing, false)
assert.equal(row.found, true, '编辑完成后应立刻亮起，不需要刷新页面')

const labelRow = {
  label: '原产国',
  labelEditVal: '来源国家',
  labelEditing: true,
}
finishFieldLabelEdit(labelRow)
assert.equal(labelRow.label, '来源国家')
assert.equal(labelRow.labelEditing, false)

const baseResult = {
  fields: {
    origin: {
      label: '原产国',
      value: '',
      cleaned: '',
      status: 'not_found',
    },
  },
  meta: {},
}

const previewJson = buildResultPreviewJson(baseResult, [
  {
    name: 'origin',
    label: '来源国家',
    status: 'not_found',
    display: '韩国',
    _original: '',
    _originalLabel: '原产国',
  },
])
const preview = JSON.parse(previewJson)
assert.equal(preview.fields.origin.value, '韩国')
assert.equal(preview.fields.origin.label, '来源国家')
assert.equal(preview.fields.origin.cleaned, '韩国')
assert.equal(preview.fields.origin.corrected, '韩国')
assert.equal(preview.fields.origin.status, 'corrected')
assert.equal(preview.meta.preview_unsaved, true)
assert.equal(baseResult.fields.origin.value, '', 'JSON 预览不应直接污染原始 result 对象')

const previewLines = splitJsonPreviewLines(previewJson)
assert.ok(previewLines.length > 0, 'JSON 预览应可拆分为行以支持高亮渲染')
const labelLine = findJsonPreviewTargetLine(previewJson, { type: 'field', fieldKey: 'origin', prop: 'label' })
const valueLine = findJsonPreviewTargetLine(previewJson, { type: 'field', fieldKey: 'origin', prop: 'value' })
assert.ok(labelLine >= 0, '字段 label 应能定位到 JSON 行')
assert.ok(valueLine >= 0, '字段 value 应能定位到 JSON 行')
assert.match(previewLines[labelLine], /"label": "来源国家"/)
assert.match(previewLines[valueLine], /"value": "韩国"/)

const multiFieldPreviewJson = buildResultPreviewJson({
  fields: {
    first: {
      label: '第一个字段',
      value: 'A',
      cleaned: 'A',
      status: 'extracted',
    },
    second: {
      label: '第二个字段',
      value: 'B',
      cleaned: 'B',
      status: 'extracted',
    },
  },
  meta: {},
}, [])
const multiFieldLines = splitJsonPreviewLines(multiFieldPreviewJson)
const secondFieldLine = findJsonPreviewTargetLine(multiFieldPreviewJson, {
  type: 'field',
  fieldKey: 'second',
  prop: 'value',
})
assert.ok(secondFieldLine >= 0, '第二个及后续字段也应能定位到 JSON 行')
assert.match(multiFieldLines[secondFieldLine], /"value": "B"/)

const specialKeyPreviewJson = buildResultPreviewJson({
  fields: {
    'TO:/A "中文"': {
      label: 'TO:/A "中文"',
      value: 'K. A. Sparrow',
      cleaned: 'K. A. Sparrow',
      status: 'extracted',
    },
  },
  meta: {},
}, [])
const specialValueLine = findJsonPreviewTargetLine(specialKeyPreviewJson, {
  type: 'field',
  fieldKey: 'TO:/A "中文"',
  prop: 'value',
})
assert.ok(specialValueLine >= 0, '含中文和引号的字段 key 也应安全定位')
assert.equal(findJsonPreviewTargetLine(specialKeyPreviewJson, {
  type: 'field',
  fieldKey: 'missing',
  prop: 'value',
}), -1, '找不到目标时应安全退化')

const savedCorrectionPreviewJson = buildResultPreviewJson({
  fields: {
    saved_field: {
      label: '已保存字段',
      learned_value_offset: { dx: 10, dy: 4, tolerance_x: 50, tolerance_y: 20 },
      value: '旧值',
      cleaned: '旧值',
      status: 'manual_added',
    },
  },
  meta: {},
}, [
  {
    name: 'saved_field',
    label: '已保存字段',
    status: 'manual_added',
    display: '新值',
    editVal: '新值',
    editing: true,
    _original: '旧值',
    found: true,
  },
])
const savedCorrectionValueLine = findJsonPreviewTargetLine(savedCorrectionPreviewJson, {
  type: 'field',
  fieldKey: 'saved_field',
  prop: 'value',
})
assert.ok(savedCorrectionValueLine >= 0, '保存修正后字段带嵌套元数据时仍应定位到 value 行')
assert.match(splitJsonPreviewLines(savedCorrectionPreviewJson)[savedCorrectionValueLine], /"value": "新值"/)

assert.deepEqual(
  getActiveFieldEditJsonTarget([
    { name: 'saved_field', label: '保存字段', editing: true, labelEditing: false },
  ]),
  { type: 'field', fieldKey: 'saved_field', fieldLabel: '保存字段', prop: 'value' },
  '字段值进入编辑态后应能持续定位 JSON value 行'
)

assert.deepEqual(
  getActiveFieldEditJsonTarget([
    { name: 'saved_field', label: '保存字段', editing: false, labelEditing: true },
  ]),
  { type: 'field', fieldKey: 'saved_field', fieldLabel: '保存字段', prop: 'label' },
  '字段名进入编辑态后应能持续定位 JSON label 行'
)

const labelFallbackPreviewJson = buildResultPreviewJson({
  fields: {
    '单证编号': {
      label: '单证编号',
      value: 'DO-EXP-0187',
      cleaned: 'DO-EXP-0187',
      status: 'extracted',
    },
  },
  meta: {},
}, [])
const labelFallbackValueLine = findJsonPreviewTargetLine(labelFallbackPreviewJson, {
  type: 'field',
  fieldKey: 'document_no',
  fieldLabel: '单证编号',
  prop: 'value',
})
assert.ok(labelFallbackValueLine >= 0, '字段 key 与 JSON key 不一致时应能用字段名定位 value 行')
assert.match(splitJsonPreviewLines(labelFallbackPreviewJson)[labelFallbackValueLine], /"value": "DO-EXP-0187"/)

const valueFallbackLine = findJsonPreviewTargetLine(labelFallbackPreviewJson, {
  type: 'field',
  fieldKey: 'document_no',
  fieldLabel: 'wrong label',
  fieldValue: 'DO-EXP-0187',
  prop: 'value',
})
assert.ok(valueFallbackLine >= 0, '字段 key/label 都无法匹配时应能用当前字段值兜底定位 value 行')
assert.match(splitJsonPreviewLines(labelFallbackPreviewJson)[valueFallbackLine], /"value": "DO-EXP-0187"/)

const boundManualRow = {
  name: 'gross_weight',
  label: 'Gross Weight',
  status: 'manual_added',
  manual: true,
  display: '4292 KG',
  _original: '',
  anchorText: 'Gross Weight',
  anchorRect: [10, 20, 80, 45],
  valueRect: [130, 20, 220, 45],
}
const boundManualPayload = buildManualFieldPayload(boundManualRow)
assert.equal(boundManualPayload.anchor_text, 'Gross Weight', 'manual field payload keeps OCR anchor text')
assert.deepEqual(boundManualPayload.anchor_rect, [10, 20, 80, 45], 'manual field payload keeps anchor rect')
assert.deepEqual(boundManualPayload.value_rect, [130, 20, 220, 45], 'manual field payload keeps value rect')
assert.equal(boundManualPayload.position, 'right', 'manual field payload infers relative position')
assert.ok(boundManualPayload.learned_value_offset.dx > 0, 'manual field payload includes feedback-ready offset')

const manualPreview = JSON.parse(buildResultPreviewJson({ fields: {}, meta: {} }, [boundManualRow]))
assert.equal(manualPreview.fields.gross_weight.anchor_text, 'Gross Weight', 'JSON preview includes manual position metadata')
assert.deepEqual(manualPreview.fields.gross_weight.value_rect, [130, 20, 220, 45])
assert.ok(manualPreview.fields.gross_weight.learned_value_offset.dx > 0)

const excludedRows = [
  { name: 'keep', label: 'Keep', display: 'A', found: true, excluded: false },
  { name: 'drop', label: 'Drop', display: 'B', found: true, excluded: true },
]
assert.deepEqual(buildVisibleFieldRows(excludedRows).map(row => row.name), ['keep'], 'field cards hide excluded fields')
assert.deepEqual(buildExcludedFieldRows(excludedRows).map(row => row.name), ['drop'], 'excluded fields remain recoverable')
assert.deepEqual(buildFeedbackFieldOptions(excludedRows).map(row => row.name), ['keep'], 'feedback options skip excluded fields')

const excludedPreview = JSON.parse(buildResultPreviewJson({
  fields: {
    keep: { label: 'Keep', value: 'A', cleaned: 'A', status: 'extracted' },
    drop: { label: 'Drop', value: 'B', cleaned: 'B', status: 'extracted' },
  },
  meta: {},
}, excludedRows))
assert.deepEqual(excludedPreview.excluded_fields, ['drop'], 'JSON preview preserves excluded field keys')
assert.equal(excludedPreview.fields.drop.excluded, true, 'JSON preview marks excluded field object')

const inferredBinding = inferManualFieldBinding(
  { text: 'Total', rect: [10, 20, 60, 42] },
  { text: '14991 USD', rect: [120, 20, 210, 42] },
)
assert.equal(inferredBinding.anchorText, 'Total')
assert.equal(inferredBinding.value, '14991 USD')
assert.equal(inferredBinding.position, 'right')

const customNamedManualField = {
  label: '111',
  value: '',
  anchorText: '',
  anchorRect: null,
  valueRect: null,
  position: '',
  learnedValueOffset: null,
}
applyManualFieldBindingDraft(customNamedManualField, inferManualFieldBinding(
  { text: '名称', rect: [10, 20, 60, 42] },
  { text: '张三', rect: [120, 20, 210, 42] },
))
assert.equal(customNamedManualField.label, '111', '选择 OCR 锚点不应覆盖用户已输入的手动字段名')
assert.equal(customNamedManualField.anchorText, '名称', 'OCR 文本应只作为手动字段锚点保存')
assert.equal(customNamedManualField.value, '张三')

const emptyNamedManualField = {
  label: '',
  value: '',
  anchorText: '',
  anchorRect: null,
  valueRect: null,
  position: '',
  learnedValueOffset: null,
}
applyManualFieldBindingDraft(emptyNamedManualField, inferManualFieldBinding(
  { text: '名称', rect: [10, 20, 60, 42] },
  { text: '张三', rect: [120, 20, 210, 42] },
))
assert.equal(emptyNamedManualField.label, '名称', '空字段名仍可由 OCR 锚点自动填充')

const sessionLogs = []
appendSessionLog(sessionLogs, {
  level: 'warning',
  source: 'Few-shot',
  title: 'AI 增强未完成',
  detail: '模型未返回有效建议',
})
assert.equal(sessionLogs.length, 1)
assert.equal(sessionLogs[0].level, 'warning')
assert.equal(sessionLogs[0].source, 'Few-shot')
assert.ok(sessionLogs[0].time, 'session log entry should include a timestamp')

const cappedLogs = Array.from({ length: 80 }, (_, index) => ({ id: index, title: String(index) }))
appendSessionLog(cappedLogs, { title: 'latest' }, 60)
assert.equal(cappedLogs.length, 60, 'session log should keep a small recent window')
assert.equal(cappedLogs.at(-1).title, 'latest')

assert.deepEqual(
  buildWarningLogEntries(['第一页之外未处理', 'AI 增强未执行'], '识别', { jobId: 'abc123abc123' })
    .map(item => ({ level: item.level, source: item.source, title: item.title, jobId: item.jobId })),
  [
    { level: 'warning', source: '识别', title: '第一页之外未处理', jobId: 'abc123abc123' },
    { level: 'warning', source: '识别', title: 'AI 增强未执行', jobId: 'abc123abc123' },
  ],
  'warnings should become structured session log entries'
)

const tableLayoutDraft = buildTableLayoutDraft(
  ['品名', '数量'],
  [
    { text: '品名', rect: [100, 300, 180, 330] },
    { text: '数量', rect: [600, 300, 680, 330] },
    { text: '玩具', rect: [100, 360, 180, 390] },
    { text: '12', rect: [600, 360, 650, 390] },
  ],
  [1000, 1000],
)
assert.equal(tableLayoutDraft.mode, 'anchor_region')
assert.deepEqual(tableLayoutDraft.headers, ['品名', '数量'])
assert.deepEqual(tableLayoutDraft.region, { x1: 0.1, y1: 0.3, x2: 0.68, y2: 0.39 })
assert.equal(tableLayoutDraft.columns[0].header, '品名')
assert.equal(tableLayoutDraft.columns[1].x1, 0.39)
assert.equal(tableLayoutDraft.anchors[0].text, '品名')
const relabeledTableLayout = relabelTableLayout(tableLayoutDraft, ['No.', 'Item'])
assert.deepEqual(relabeledTableLayout.headers, ['No.', 'Item'])
assert.equal(relabeledTableLayout.region.y1, tableLayoutDraft.region.y1)
assert.equal(relabeledTableLayout.columns[0].x1, tableLayoutDraft.columns[0].x1)
assert.equal(relabeledTableLayout.columns[0].header, 'No.')
assert.equal(relabelTableLayout(tableLayoutDraft, ['No.', 'Item', 'Qty']), null)
assert.equal(
  buildTableLayoutDraft(
    ['序号', '品名名称', '数量'],
    [
      { text: '序号', rect: [80, 332, 110, 348] },
      { text: '品名名称', rect: [130, 332, 205, 348] },
      { text: '数量', rect: [590, 332, 620, 348] },
    ],
    [1000, 1000],
  ),
  null,
  'selecting only header OCR blocks should not create a learned table layout'
)

const multiTableResult = {
  fields: {
    'TO:': {
      label: 'TO:',
      value: 'K. A. Sparrow',
      cleaned: 'K. A. Sparrow',
      status: 'extracted',
    },
  },
  table: {
    title: 'WITHIN THE REGION',
    headers: ['NAME OF ACCOUNT', 'NO. OF STORES'],
    rows: [['Sico Serve', '18']],
  },
  tables: [
    {
      title: 'WITHIN THE REGION',
      headers: ['NAME OF ACCOUNT', 'NO. OF STORES'],
      rows: [['Sico Serve', '18']],
      confidence: 0.91,
    },
    {
      title: 'OUTSIDE THE REGION',
      headers: ['NAME OF ACCOUNT', 'NO. OF STORES'],
      rows: [['Kroger', '21']],
      confidence: 0.89,
    },
  ],
  meta: {},
}
const multiTablePreview = JSON.parse(buildResultPreviewJson(multiTableResult, [], {
  title: 'WITHIN THE REGION',
  headers: ['NAME OF ACCOUNT', 'NO. OF STORES'],
  rows: [{ 0: 'Sico Serve', 1: '18' }],
  source: 'vision_fallback',
  layout: tableLayoutDraft,
}))
assert.equal(multiTablePreview.tables.length, 2, '多表格预览应保留完整 tables 数组')
assert.equal(multiTablePreview.tables[1].title, 'OUTSIDE THE REGION')
assert.deepEqual(multiTablePreview.table.rows, [['Sico Serve', '18']], '旧 table 兼容字段应继续可用')
assert.equal(multiTablePreview.table_layout.mode, 'anchor_region', 'JSON preview should include learned table layout metadata')
const multiTablePreviewJson = buildResultPreviewJson(multiTableResult, [], {
  title: 'WITHIN THE REGION',
  headers: ['NAME OF ACCOUNT', 'NO. OF STORES'],
  rows: [{ 0: 'Sico Serve', 1: '18' }],
  source: 'vision_fallback',
})
assert.ok(findJsonPreviewTargetLine(multiTablePreviewJson, { type: 'table' }) >= 0, '表格保存后应能定位到 JSON 表格区域')

const displayTables = buildDisplayTables(multiTableResult)
assert.equal(displayTables.length, 2, '结果页应展示所有视觉兜底表格，而不是只展示第一个 table')
assert.equal(displayTables[0].title, 'WITHIN THE REGION')
assert.deepEqual(displayTables[1].rows, [{ 0: 'Kroger', 1: '21' }])

const appVue = fs.readFileSync(new URL('../frontend/src/App.vue', import.meta.url), 'utf8')
const apiSource = fs.readFileSync(new URL('../frontend/src/api/index.js', import.meta.url), 'utf8')
const activeDoCorrectSource = appVue.slice(appVue.lastIndexOf('async function doCorrect(options = {})'))
assert.match(appVue, /选择字段名 OCR 块/, 'manual field dialog should select an OCR anchor block')
assert.match(appVue, /选择字段值 OCR 块/, 'manual field dialog should select an OCR value block')
assert.match(appVue, /buildManualFieldPayload\(row\)/, 'correction payload should include manual field position metadata')
assert.match(appVue, /excluded_fields: excludedFields/, 'correction payload should include excluded_fields')
assert.match(appVue, /已排除字段/, 'result page should show recoverable excluded fields')
assert.match(apiSource, /payload\.excluded_fields/, 'correct API should treat excluded_fields as a structured payload')
assert.match(appVue, /class="logo smartlds-logo"/, '顶部品牌应使用 SmartLDS 动态 SVG 图标')
assert.match(appVue, /class="logo-scan"/, '动态图标应包含扫描光线')
assert.match(appVue, /class="logo-node/, '动态图标应包含数据节点')
assert.match(appVue, /@media \(prefers-reduced-motion: reduce\)/, '动态图标应支持 reduced-motion 静态兜底')
assert.match(appVue, /metric-visual rule-priority/, '规则优先卡片应包含动态规则优先视觉点')
assert.match(appVue, /metric-visual schema-labels/, '原字段名卡片应包含动态 schema 标签视觉点')
assert.match(appVue, /metric-visual export-ready/, '可导出卡片应包含动态导出视觉点')
assert.match(appVue, /@keyframes metric-scan/, '首页指标卡应包含扫描动效')
assert.match(appVue, /@keyframes metric-float/, '首页指标卡应包含轻量浮动动效')
assert.match(appVue, /class="json-collapse"/, '结果页应保留第一版的普通 JSON 折叠块')
assert.match(appVue, /title="JSON"/, 'JSON 折叠块标题应回到简单的 JSON')
assert.match(appVue, /class="json-inspector"/, 'JSON 预览应移动到最右侧检查栏')
assert.match(appVue, /\.json-inspector\{[^}]*background:#f8fafc/, 'JSON 检查栏应使用浅色核对面板背景')
assert.match(appVue, /\.json-inspector \.json-block\{[^}]*background:#fff/, '右侧 JSON 代码块应使用浅色纸面背景')
assert.match(appVue, /\.json-line\.active\{[^}]*rgba\(59,130,246,\.12\)/, 'JSON 高亮应使用柔和蓝色核对态')
assert.match(appVue, /jsonInspectorOpen/, 'JSON 检查栏应支持显示和隐藏')
assert.match(appVue, /toggleJsonInspector/, '用户应能手动切换右侧 JSON 检查栏')
assert.match(appVue, /jsonInspectorOpen\.value = true/, '字段编辑定位时应自动展开右侧 JSON 检查栏')
assert.match(appVue, /jsonCollapseActive/, 'JSON 折叠块应有主动展开状态以便编辑时自动展开')
assert.match(appVue, /jsonBlockRef/, 'JSON 预览应有滚动容器 ref')
assert.match(appVue, /activeJsonLine/, 'JSON 预览应记录当前高亮行')
assert.match(appVue, /findRenderedJsonLine/, 'JSON 追踪应等待保存后重新渲染出的目标行')
assert.match(appVue, /clearJsonHighlightTimer\(\)\s+jsonInspectorOpen\.value = true/, 'JSON 追踪开始时应先清理旧高亮定时器')
assert.match(appVue, /@input="previewFieldValueInJson\(row\)"/, '字段值输入中应实时同步并定位 JSON')
assert.match(appVue, /@input="previewFieldLabelInJson\(row\)"/, '字段名输入中应实时同步并定位 JSON')
assert.match(appVue, /syncJsonPreview\(\{ type: 'table' \}\)/, '表格保存后应定位到 JSON 表格区域')
assert.match(appVue, /bindTableLayoutFromOcr/, 'table editor should bind selected OCR blocks as a learned layout')
assert.match(appVue, /选择表格 OCR 块/, 'table editor should expose OCR block selection for table layout learning')
assert.match(activeDoCorrectSource, /payload\.table_patch\.layout = tableData\.layout/, 'correction payload should include learned table layout metadata')
assert.match(appVue, /fsAiEnhance/, 'Few-shot 学习弹窗应提供 AI 增强开关状态')
assert.match(appVue, /fd\.append\('ai_enhance', fsAiEnhance\.value \? '1' : '0'\)/, 'Few-shot 学习请求应把 AI 增强开关传给后端')
assert.match(appVue, /fsResult\.detection\?\.features\?\.length/, 'Few-shot 结果应展示样本版式特征数量而不是预设关键词数量')
assert.match(appVue, /detection: fsResult\.value\.detection/, '应用 Few-shot 版式时应保存布局签名')
assert.match(appVue, /tpl\.detection\?\.mode === 'anchor_layout'/, '版式管理应区分锚点布局识别与旧关键词识别')
assert.match(appVue, /feedbackProgressText/, '反哺弹窗应显示当前反哺或 AI 增强进度文案')
assert.match(appVue, /fsProgressText/, 'Few-shot 学习弹窗应显示当前学习或 AI 增强进度文案')
assert.match(appVue, /class="operation-progress feedback-progress"/, '反哺弹窗应包含进度条区域')
assert.match(appVue, /class="operation-progress fs-progress"/, 'Few-shot 弹窗应包含进度条区域')
assert.match(appVue, /operation-progress-fill[^"]*indeterminate/, 'AI 增强进行中应使用动态进度条状态')
assert.match(appVue, /AI 增强未完成|AI 增强未执行/, '普通流程成功但 AI 增强未应用时应给用户明确提示')
assert.match(appVue, /showSessionLog/, 'top bar should expose a lightweight session log drawer')
assert.match(appVue, /运行日志/, 'session log drawer should be labelled for runtime diagnostics')
assert.match(appVue, /addWarningLogs\(data\.result\?\.warnings \|\| \[\], 'Few-shot'/, 'Few-shot warnings should be copied into the session log')
assert.match(appVue, /addWarningLogs\(data\.warnings \|\| \[\], '反哺'/, 'feedback warnings should be copied into the session log')
assert.match(appVue, /addLog\(\{ level: 'error', source: '识别'/, 'recognition errors should be copied into the session log')
assert.match(apiSource, /const AI_OPERATION_TIMEOUT_MS = 600000/, 'AI 增强相关长任务不应使用默认 120 秒超时')
assert.match(apiSource, /function modelOperationTimeoutMs/, 'front-end API should derive long request timeouts from model settings')
assert.match(apiSource, /recognize\(jobId, timeoutSeconds/, 'recognition requests should accept configurable model timeout')
assert.match(apiSource, /API\.post\('\/fewshot\/from-result', data, \{ timeout: modelOperationTimeoutMs\(timeoutSeconds\) \}\)/, '结果页 AI 反哺接口应使用模型设置超时')
assert.match(apiSource, /API\.post\('\/fewshot\/learn', formData, \{ timeout: modelOperationTimeoutMs\(timeoutSeconds\) \}\)/, 'Few-shot AI 学习接口应使用模型设置超时')
assert.match(apiSource, /probeVisionModels\(data\)/, '前端 API 应提供模型检测接口')
assert.match(apiSource, /API\.post\('\/vision-settings\/probe', data, \{ timeout: 60000 \}\)/, '模型检测应调用后端 probe 接口并使用独立超时')
assert.match(apiSource, /revealVisionApiKey\(params = \{\}\)/, '前端 API 应提供按当前配置查看已保存 API Key 的接口')
assert.match(apiSource, /API\.get\('\/vision-settings\/api-key', \{ params \}\)/, '查看已保存 API Key 应按当前 provider/model 调用后端明文取回接口')
assert.match(appVue, /visionDetectedModels/, '模型设置应保存检测返回的模型列表')
assert.match(appVue, /probeVisionModels/, '模型设置应提供检测模型按钮逻辑')
assert.match(appVue, /检测模型/, '模型设置弹窗应显示检测模型按钮')
assert.match(appVue, /visionProbeMessage/, '模型设置应显示检测结果提示')
assert.match(appVue, /View, Hide/, 'API Key 查看按钮应使用眼睛图标')
assert.match(appVue, /revealSavedVisionApiKey/, '模型设置应支持点击眼睛查看已保存 API Key')
assert.match(appVue, /visionSavedApiKeyVisible/, '已保存 API Key 应支持显示和隐藏切换')
assert.match(appVue, /visionSavedApiKeyDisplay/, '已保存 API Key 显示文本应在掩码和明文间切换')
assert.match(appVue, /visionSavedProfiles/, '模型设置应缓存后端返回的 provider profiles，切换 provider 不应丢配置')
assert.match(appVue, /visionSettings\.provider === 'ollama'/, 'Ollama provider 应有独立 UI 分支')
assert.match(appVue, /不需要 API Key/, 'Ollama 模式应提示不需要 API Key')
assert.match(appVue, /http:\/\/localhost:11434/, 'Ollama 地址提示应使用原生服务根地址')
assert.match(appVue, /function formatApiError/, '长任务超时时应把 Axios 技术错误转换成可读提示')
assert.match(appVue, /backendWarning/, '模型检测失败时应显示后端 warning，而不是裸 400')
assert.match(appVue, /模型响应超时/, 'AI 长任务超时时应提示模型响应超时')
assert.match(appVue, /反哺失败: ' \+ formatApiError\(e\)/, '反哺失败提示应使用友好错误文案')
assert.match(appVue, /请求失败: ' \+ formatApiError\(e\)/, 'Few-shot 学习失败提示应使用友好错误文案')
assert.match(appVue, /高性能电脑或服务器/, 'Ollama mode should explain local vision extraction needs a powerful computer or server')
assert.match(appVue, /响应超时/, 'model settings dialog should expose response timeout')
assert.match(appVue, /timeout: visionSettings\.timeout/, 'model settings save payload should include timeout')
assert.match(appVue, /api\.recognize\(f\.job_id, visionSettings\.timeout\)/, 'recognition should use configured model timeout')
assert.doesNotMatch(appVue, /result-preview-collapse/, '不应再显示导出预览增强面板')
assert.doesNotMatch(appVue, /resultPreviewTab/, '不应再保留字段键值预览的切换状态')
assert.doesNotMatch(appVue, /导出预览 \/ JSON/, '不应再显示导出预览标题')
assert.doesNotMatch(appVue, /需要查字段、核对导出结构时再展开/, '折叠标题不应放过长说明，避免显得重复啰嗦')
