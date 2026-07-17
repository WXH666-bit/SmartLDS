import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  buildResultPreviewJson,
  finishFieldEdit,
  finishFieldLabelEdit,
  isFieldRowFound,
} from '../frontend/src/resultState.js'

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

const appVue = fs.readFileSync(new URL('../frontend/src/App.vue', import.meta.url), 'utf8')
assert.match(appVue, /class="json-collapse"/, '结果页应保留第一版的普通 JSON 折叠块')
assert.match(appVue, /title="JSON"/, 'JSON 折叠块标题应回到简单的 JSON')
assert.doesNotMatch(appVue, /result-preview-collapse/, '不应再显示导出预览增强面板')
assert.doesNotMatch(appVue, /resultPreviewTab/, '不应再保留字段键值预览的切换状态')
assert.doesNotMatch(appVue, /导出预览 \/ JSON/, '不应再显示导出预览标题')
assert.doesNotMatch(appVue, /需要查字段、核对导出结构时再展开/, '折叠标题不应放过长说明，避免显得重复啰嗦')
