<template>
<div class="app-shell">
  <!-- ============ Top Bar ============ -->
  <header class="topbar">
    <div class="brand">
      <div class="logo">LDS</div>
      <div>
        <h1>SmartLDS</h1>
        <span class="subtitle">物流单证智能识别系统</span>
      </div>
    </div>
    <div class="spacer"></div>
    <div class="pipeline-steps">
      <div class="step" :class="{ active: pipelineStep>=1, done: pipelineStep>=2 }">
        <div class="step-dot">{{ pipelineStep>=2 ? '✓' : '1' }}</div>
        <span class="step-label">上传</span>
      </div>
      <div class="step-line" :class="{ done: pipelineStep>=2, pulse: pipelineStep===1 }"></div>
      <div class="step" :class="{ active: pipelineStep>=2, done: pipelineStep>=3 }">
        <div class="step-dot">{{ pipelineStep>=3 ? '✓' : '2' }}</div>
        <span class="step-label">识别</span>
      </div>
      <div class="step-line" :class="{ done: pipelineStep>=3 }"></div>
      <div class="step" :class="{ done: pipelineStep>=3 }">
        <div class="step-dot">3</div>
        <span class="step-label">完成</span>
      </div>
    </div>
    <el-button size="small" text @click="showFewshot=true">Few-shot 学习</el-button>
    <el-button size="small" text @click="showHistory=true; loadHistory()" style="margin-left:12px">历史</el-button>
    <el-button size="small" text @click="showConfig=true; loadConfig()">版式管理</el-button>
  </header>

  <!-- ============ Body ============ -->
  <main class="body">

    <!-- === Upload Stage === -->
    <div v-if="!resultReady" class="upload-stage">
      <!-- Hero illustration -->
      <div class="hero-illustration">
        <svg viewBox="0 0 300 120" fill="none" xmlns="http://www.w3.org/2000/svg">
          <!-- Document -->
          <rect x="50" y="12" width="72" height="96" rx="6" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>
          <rect x="60" y="28" width="52" height="4" rx="2" fill="#e2e8f0"/>
          <rect x="60" y="40" width="40" height="4" rx="2" fill="#e2e8f0"/>
          <rect x="60" y="52" width="46" height="4" rx="2" fill="#e2e8f0"/>
          <rect x="60" y="66" width="24" height="18" rx="3" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.5"/>
          <rect x="90" y="66" width="22" height="18" rx="3" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.5"/>
          <!-- Arrow from doc to cloud -->
          <path d="M128 60 L172 60" stroke="#3b82f6" stroke-width="2.5" stroke-dasharray="6,3"/>
          <polygon points="170,56 178,60 170,64" fill="#3b82f6"/>
          <!-- Cloud with check -->
          <path d="M190 38c-8 0-14-1-16 7-3-2-8-2-10 1-6 0-10 4-10 10s4 10 10 10h26c6 0 10-4 10-10s-4-10-10-10z" fill="#dbeafe" stroke="#93c5fd" stroke-width="2"/>
          <path d="M199 54l4 5 8-9" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          <!-- Decorative scanning lines -->
          <line x1="140" y1="18" x2="140" y2="24" stroke="#94a3b8" stroke-width="1.5" opacity="0.5"/>
          <line x1="140" y1="30" x2="140" y2="36" stroke="#94a3b8" stroke-width="1.5" opacity="0.5"/>
          <line x1="182" y1="80" x2="182" y2="102" stroke="#94a3b8" stroke-width="1.5" opacity="0.5"/>
          <!-- Small parcel -->
          <rect x="216" y="52" width="34" height="28" rx="4" fill="#fef3c7" stroke="#fbbf24" stroke-width="2"/>
          <line x1="233" y1="52" x2="233" y2="80" stroke="#fbbf24" stroke-width="1.5"/>
          <line x1="216" y1="66" x2="250" y2="66" stroke="#fbbf24" stroke-width="1.5"/>
          <text x="150" y="115" text-anchor="middle" font-size="10" fill="#94a3b8" font-family="system-ui">文档上传 · 智能识别 · 结构化提取</text>
        </svg>
      </div>

      <!-- Dropzone + ZIP box side by side -->
      <div class="upload-cols">
        <div class="dz-box files-dz" :class="{ over: filesOver }"
             @dragover.prevent="filesOver=true" @dragleave.prevent="filesOver=false"
             @drop.prevent="filesOver=false; filesDropped($event)">
          <div class="dz-icon">📄</div>
          <p class="dz-title">拖拽文件到此处</p>
          <p class="dz-hint">PDF · PNG · JPG · 最大 32MB</p>
          <el-button type="primary" round @click="$refs.multiInput.click()">选择文件</el-button>
          <input ref="multiInput" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple hidden @change="onMultiChange">
        </div>

        <div class="dz-box zip-dz" :class="{ over: zipOver }"
             @dragover.prevent="zipOver=true" @dragleave.prevent="zipOver=false"
             @drop.prevent="zipOver=false; zipDropped($event)">
          <div class="dz-icon">📦</div>
          <p class="dz-title">拖入 ZIP 压缩包</p>
          <p class="dz-hint">自动解压全部文件</p>
          <el-button type="primary" round @click="$refs.zipInput.click()">选择 ZIP</el-button>
          <input ref="zipInput" type="file" accept=".zip" hidden @change="onZipChange">
        </div>
      </div>

      <!-- File list -->
      <div v-if="fileList.length" class="file-pool">
        <div class="pool-head">
          <span>已添加 <b>{{ fileList.length }}</b> 个文件</span>
          <el-button size="small" @click="clearAll">清空</el-button>
          <el-button size="small" type="success" :loading="phase==='recognizing'" @click="recognizeAll">
            {{ phase==='recognizing' ? '识别中...' : '识别全部' }}
          </el-button>
        </div>
        <div class="pool-grid">
          <div v-for="f in fileList" :key="f.job_id" class="pool-card"
               :class="{ active: viewingJobId===f.job_id, done: f.status==='done' }"
               @click="viewJob(f)">
            <span class="pc-dot" :class="{ ok: f.status==='done', busy: f.status==='processing', err: f.status==='error' }"></span>
            <span class="pc-name">{{ f.filename }}</span>
            <span class="pc-size">{{ f.size }}</span>
            <span v-if="f.status==='done'" class="pc-tpl">{{ f.template }}</span>
            <el-button size="small" text type="danger" @click.stop="removeFile(f.job_id)">✕</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- === Result Stage === -->
    <div v-else class="result-stage">
      <div class="result-toolbar">
        <div class="toolbar-left">
          <el-button size="small" @click="backToList">← 返回列表</el-button>
          <span class="meta-item"><b>{{ meta.template }}</b></span>
          <span class="meta-item">字段 {{ meta.fields_extracted }}/{{ meta.fields_total }}</span>
          <span class="meta-item">OCR {{ meta.ocr_blocks }} 块</span>
          <span v-if="tableData.headers.length" class="meta-item">表格 {{ tableData.rows.length }} 行</span>
        </div>
        <div class="toolbar-right">
          <el-button size="small" @click="doExport('json')">JSON</el-button>
          <el-button size="small" @click="doExport('xlsx')">Excel</el-button>
          <el-button size="small" type="warning" @click="doCorrect">保存校正</el-button>
        </div>
      </div>

      <!-- 2-pane result -->
      <div class="dual-pane">
        <div class="pane-original"><img :src="imageUrl" class="orig-img" alt="原始单证" /></div>
        <div class="pane-fields">
          <!-- Unknown template banner -->
          <div v-if="meta.template==='unknown' || unknownDetected" class="unknown-banner">
            <div class="ub-icon">🔍</div>
            <div class="ub-text">
              <p class="ub-title">未识别的版式</p>
              <p class="ub-desc">系统未匹配到已知版式模板，已提取 {{ meta.ocr_blocks }} 个 OCR 文本块。</p>
              <p class="ub-hint">可添加 2~5 份此版式的标注样本进行 Few-shot 学习，自动适配新模板。</p>
            </div>
            <el-button type="primary" size="small" @click="startFewshot">Few-shot 学习</el-button>
          </div>

          <!-- OCR blocks preview for unknown -->
          <div v-if="(meta.template==='unknown' || unknownDetected) && ocrPreview.length" class="ocr-preview">
            <div class="section-title">OCR 文本块 ({{ ocrPreview.length }})</div>
            <div class="ocr-list">
              <div v-for="(b,i) in ocrPreview" :key="i" class="ocr-row">
                <span class="ocr-idx">{{ i+1 }}</span>
                <span class="ocr-text">{{ b.text }}</span>
                <span class="ocr-conf">{{ Math.round(b.confidence*100) }}%</span>
              </div>
            </div>
          </div>

          <div v-if="!(meta.template==='unknown' || unknownDetected)" class="section-title">字段提取</div>
          <div class="field-cards">
            <div v-for="row in fieldRows" :key="row.name" class="field-card" :class="{ miss: !row.found }">
              <div class="fc-label">{{ row.label }}</div>
              <div class="fc-value" v-if="!row.editing"
                   @dblclick="row.editing=true; row.editVal=row.display"
                   :class="{ empty: !row.display }">{{ row.display || '(空)' }}</div>
              <el-input v-else v-model="row.editVal" size="small" @blur="row.display=row.editVal;row.editing=false" @keyup.enter="row.display=row.editVal;row.editing=false" autofocus />
              <div class="fc-conf" v-if="row.confidence">{{ row.confidence }}</div>
            </div>
          </div>
          <div v-if="tableData.headers.length" class="cargo-box">
            <div class="section-title">货物明细</div>
            <el-table :data="tableData.rows" size="small" stripe border max-height="240">
              <el-table-column v-for="(h,i) in tableData.headers" :key="i" :prop="String(i)" :label="h" min-width="90" show-overflow-tooltip />
            </el-table>
          </div>
          <el-collapse class="json-collapse">
            <el-collapse-item title="JSON"><pre class="json-block">{{ jsonText }}</pre></el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </div>
  </main>

  <!-- ============ History Drawer ============ -->
  <el-drawer v-model="showHistory" size="480px" direction="rtl">
    <template #header>
      <div style="display:flex;align-items:center;justify-content:space-between;width:100%">
        <span>识别历史</span>
        <el-popconfirm title="确定删除全部历史记录？" @confirm="deleteAllHistory">
          <template #reference>
            <el-button v-if="historyList.length" size="small" type="danger" text>清空全部</el-button>
          </template>
        </el-popconfirm>
      </div>
    </template>
    <div v-if="!historyList.length" style="text-align:center;color:#888;padding:40px">暂无历史记录</div>
    <div v-else class="history-list">
      <div v-for="h in historyList" :key="h.job_id" class="history-card">
        <div class="hc-left" @click="window.open('?job='+h.job_id,'_blank')">
          <span class="hc-name">{{ h.filename }}</span>
          <span class="hc-meta">{{ h.template }} · {{ h.fields_extracted }}/{{ h.fields_total }} 字段 · {{ h.ocr_blocks }} 块</span>
        </div>
        <div class="hc-right">
          <span class="hc-time">{{ h.recognized_at?.slice(0,16)?.replace('T',' ') || '' }}</span>
          <el-popconfirm title="删除此记录？" @confirm="deleteSingleHistory(h.job_id)">
            <template #reference>
              <el-button size="small" text type="danger" @click.stop>✕</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
    </div>
  </el-drawer>

  <!-- ============ Few-shot Dialog ============ -->
  <el-dialog v-model="showFewshot" title="Few-shot 版式学习" width="640px" :close-on-click-modal="false">
    <p style="color:#888;font-size:13px;margin:0 0 16px">一次性选择所有 PDF + 标注 JSON 文件，系统按文件名自动配对（2~5 对）</p>

    <!-- Batch file dropzone -->
    <div class="fs-batch-drop" :class="{ over: fsDragOver }"
         @dragover.prevent="fsDragOver=true" @dragleave.prevent="fsDragOver=false"
         @drop.prevent="fsDragOver=false; fsBatchDrop($event)">
      <div class="fs-batch-icon">📂</div>
      <p class="fs-batch-title">拖入文件 或 点击选择</p>
      <p class="fs-batch-hint">同时选多个 .pdf 和 .json · 同文件名自动配对</p>
      <el-button type="primary" size="small" round @click="$refs.fsBatchInput.click()">选择文件</el-button>
      <input ref="fsBatchInput" type="file" accept=".pdf,.json" multiple hidden @change="fsBatchSelect">
    </div>

    <!-- Paired samples -->
    <div v-if="fsPairs.length" class="fs-pairs-box">
      <div class="fs-pairs-head">
        已配对 <b style="color:#10b981">{{ fsPairs.length }}</b> 份样本
        <el-button size="small" text @click="fsPairs=[]; fsUnpaired=[]; fsTemplateName=''">清空</el-button>
      </div>
      <div v-for="(p, i) in fsPairs" :key="i" class="fs-pair-row">
        <span class="fs-pair-idx">{{ i+1 }}</span>
        <span class="fs-pair-name">{{ p.baseName }}</span>
        <span class="fs-pair-detail">{{ p.pdfName }} + {{ p.jsonName }}</span>
        <span class="fs-pair-check">✓</span>
        <el-button size="small" text type="danger" @click="fsPairs.splice(i,1)">✕</el-button>
      </div>
    </div>

    <!-- Unpaired files warning -->
    <div v-if="fsUnpaired.length" style="margin-top:12px;padding:8px 12px;background:#fef3c7;border-radius:8px">
      <div style="font-size:12px;color:#92400e;font-weight:600;margin-bottom:4px">⚠ 未配对文件 ({{ fsUnpaired.length }}) — 将被忽略</div>
      <div v-for="(f, i) in fsUnpaired" :key="i" style="font-size:11px;color:#a16207;padding-left:8px">{{ f.name }}</div>
    </div>

    <!-- Template name + actions -->
    <div style="margin-top:16px;display:flex;align-items:center;gap:10px">
      <span style="font-size:12px;color:#64748b;white-space:nowrap">版式名称：</span>
      <el-input v-model="fsTemplateName" size="small" placeholder="自动生成" style="flex:1;max-width:240px" clearable />
      <div style="flex:1"></div>
      <el-button size="small" type="primary" :loading="fsLearning" @click="doFewshotLearn" :disabled="fsPairs.length<2">开始学习</el-button>
    </div>

    <!-- Result -->
    <div v-if="fsResult" class="fs-result">
      <div class="section-title">学习结果</div>
      <p style="font-size:12px;color:#888;margin:0 0 8px">
        版式: <b>{{ fsResult.template_name }}</b> · {{ fsResult.keywords.length }} 关键词 · {{ Object.keys(fsResult.fields||{}).length }} 字段
      </p>
      <pre class="json-block" style="max-height:280px">{{ fsResult.yaml_text }}</pre>
      <el-button size="small" type="success" @click="fsApplyResult" style="margin-top:8px">应用到系统</el-button>
    </div>
  </el-dialog>

  <!-- ============ Config Drawer ============ -->
  <el-drawer v-model="showConfig" title="版式配置管理" size="700px" direction="rtl">
    <div v-if="configLoading" style="text-align:center;padding:40px"><el-icon class="is-loading" :size="32"><Loading /></el-icon></div>
    <div v-else-if="configTemplates.length" class="config-drawer">
      <div v-for="tpl in configTemplates" :key="tpl.name" class="config-card">
        <div class="cc-head">
          <span class="cc-name">{{ tpl.name }}</span>
          <el-tag v-if="tpl.has_table" size="small" type="success">含表格</el-tag>
          <el-tag v-else size="small" type="info">无表格</el-tag>
          <div class="cc-spacer"></div>
          <el-popconfirm title="确定删除此版式？" @confirm="deleteTemplate(tpl.name)">
            <template #reference>
              <el-button size="small" type="danger" text>删除</el-button>
            </template>
          </el-popconfirm>
        </div>
        <div class="cc-keywords">
          <span class="cc-label">关键词：</span>
          <el-tag v-for="kw in tpl.keywords" :key="kw" size="small" class="cc-kw">{{ kw }}</el-tag>
          <span v-if="!tpl.keywords.length" class="cc-none">自动检测</span>
        </div>
        <div class="cc-fields">
          <div class="cc-field-head">
            <span class="ccf-col" style="width:110px">字段</span>
            <span class="ccf-col" style="flex:1">锚点</span>
            <span class="ccf-col" style="width:60px;text-align:center">位置</span>
            <span class="ccf-col" style="width:80px;text-align:center">校验</span>
          </div>
          <div v-for="f in tpl.fields" :key="f.key" class="cc-field-row">
            <span class="ccf-col field-name" style="width:110px">{{ f.label }}</span>
            <span class="ccf-col" style="flex:1">
              <el-tag v-for="a in f.anchors" :key="a" size="small" effect="plain" class="cc-anchor">{{ a }}</el-tag>
            </span>
            <span class="ccf-col pos-icon" style="width:60px;text-align:center">
              {{ f.position==='right' ? '→' : f.position==='below' ? '↓' : f.position==='either' ? '⇄' : f.position }}
            </span>
            <span class="ccf-col" style="width:80px;text-align:center">
              <el-tag v-if="f.validator" size="small" type="warning">{{ f.validator }}</el-tag>
              <span v-else class="cc-none">—</span>
            </span>
          </div>
        </div>
      </div>
    </div>
    <div v-else style="text-align:center;color:#888;padding:40px">暂无配置数据</div>
  </el-drawer>
</div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import api from './api/index.js'

// Check URL for ?job=xxx → auto-load result in new tab
const urlParams = new URLSearchParams(window.location.search)
const urlJobId = urlParams.get('job')

// State
const phase = ref('idle')           // idle | ready | recognizing | done
const filesOver = ref(false); const zipOver = ref(false)
const zipInput = ref(null); const multiInput = ref(null); const fsBatchInput = ref(null)
const fileList = ref([])             // [{job_id, filename, size, status, template, fields_extracted, fields_total}]
const viewingJobId = ref('')
const viewingData = ref(null)        // cached result for current view
const meta = reactive({})
const fieldRows = ref([])
const tableData = reactive({ headers: [], rows: [] })
const jsonText = ref('')
const imageUrl = ref('')
const unknownDetected = ref(false)
const ocrPreview = ref([])  // OCR blocks for unknown template preview

// Config viewer
const showConfig = ref(false)
const configLoading = ref(false)
const configTemplates = ref([])

// History
const showHistory = ref(false)
const historyList = ref([])
async function loadHistory() {
  try { const {data} = await api.getHistory(); historyList.value = data.history || [] }
  catch(e) { ElMessage.error('加载历史失败') }
}
async function deleteSingleHistory(jobId) {
  try {
    await api.deleteHistory(jobId)
    historyList.value = historyList.value.filter(h => h.job_id !== jobId)
    ElMessage.success('已删除')
  } catch(e) { ElMessage.error('删除失败') }
}
async function deleteAllHistory() {
  try {
    await api.deleteAllHistory()
    historyList.value = []
    ElMessage.success('已清空全部历史')
  } catch(e) { ElMessage.error('清空失败') }
}

async function loadConfig() {
  configLoading.value = true
  try {
    const { data } = await api.getConfig()
    configTemplates.value = data.templates || []
  } catch (e) { ElMessage.error('加载配置失败') }
  finally { configLoading.value = false }
}

async function deleteTemplate(name) {
  try {
    await api.deleteTemplate(name)
    configTemplates.value = configTemplates.value.filter(t => t.name !== name)
    ElMessage.success(`已删除版式: ${name}`)
  } catch (e) { ElMessage.error('删除失败: ' + (e.response?.data?.error || e.message)) }
}

const resultReady = computed(() => phase.value==='done' && !!viewingJobId.value)
const pipelineStep = computed(() => {
  if (phase.value==='done') return 3
  if (phase.value==='recognizing') return 2
  if (fileList.value.length) return 1
  return 0
})

function formatSize(bytes) {
  if (!bytes || bytes < 0) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB'
  return (bytes/1048576).toFixed(1) + ' MB'
}

// ============ File handling ============
function filesDropped(e) { addFiles(Array.from(e.dataTransfer.files)) }
function zipDropped(e) {
  const files = e.dataTransfer.files
  if (files.length) { const f = files[0]; if (f.name.endsWith('.zip')) { uploadZip(f) } else { addFiles(Array.from(files)) } }
}
function onZipChange(e) { const f=e.target.files[0]; if(f) uploadZip(f) }
function onMultiChange(e) { if(e.target.files.length) { addFiles(Array.from(e.target.files)); e.target.value='' } }

async function addFiles(files) {
  let added = 0
  for (const f of files) {
    if (fileList.value.some(x=>x.filename===f.name && x.size!=='...')) continue
    fileList.value.push({ job_id: '...', filename: f.name, size: '...', status: 'uploading' })
    try {
      const {data} = await api.upload(f)
      const idx = fileList.value.findIndex(x=>x.filename===f.name && x.status==='uploading')
      if (idx>=0) Object.assign(fileList.value[idx], {
        job_id: data.job_id, filename: f.name,
        size: formatSize(f.size), status: 'ready'
      })
      added++
    } catch(e) {
      const idx = fileList.value.findIndex(x=>x.filename===f.name && x.status==='uploading')
      if (idx>=0) fileList.value.splice(idx, 1)
      ElMessage.error(f.name + ' 上传失败')
    }
  }
  if (added) ElMessage.success(`已添加 ${added} 个文件`)
}

async function uploadZip(file) {
  fileList.value.push({ job_id: '...', filename: file.name, size: '...', status: 'uploading' })
  try {
    const {data} = await api.uploadZip(file)
    data.jobs.forEach(j => {
      if (!fileList.value.some(x=>x.filename===j.filename)) {
        fileList.value.push({ job_id: j.job_id, filename: j.filename, size: '-', status: 'ready' })
      }
    })
    // Remove the ZIP placeholder
    const zi = fileList.value.findIndex(x=>x.filename===file.name && x.status==='uploading')
    if (zi>=0) fileList.value.splice(zi, 1)
    ElMessage.success(`已添加 ${data.jobs.length} 个文件`)
  } catch(e) {
    fileList.value = fileList.value.filter(x=>x.filename!==file.name || x.status!=='uploading')
    ElMessage.error('ZIP 上传失败')
  }
}

function removeFile(jobId) { fileList.value = fileList.value.filter(f=>f.job_id!==jobId) }
function clearAll() { fileList.value=[]; viewingJobId.value=''; phase.value='idle' }

// ============ Recognize ============
async function viewJob(f) {
  if (f.status==='done') {
    // Already done → open in new tab
    window.open(`?job=${f.job_id}`, '_blank')
    return
  }
  if (f.status==='ready') {
    f.status='processing'; phase.value='recognizing'
    try {
      await api.recognize(f.job_id)
      const {data} = await api.result(f.job_id)
      const m = data.meta || {}
      Object.assign(f, { status: 'done', template: m.template || '?',
        fields_extracted: m.fields_extracted || 0, fields_total: m.fields_total || 0 })
      window.open(`?job=${f.job_id}`, '_blank')
      phase.value='idle'
    } catch(e) { f.status='error'; phase.value='idle'; ElMessage.error('识别失败') }
    return
  }
}

// Auto-load from ?job=xxx on mount
onMounted(async () => {
  if (urlJobId) {
    phase.value='done'
    viewingJobId.value = urlJobId
    try {
      const {data} = await api.result(urlJobId)
      showResult(data)
    } catch(e) { ElMessage.error('加载失败'); phase.value='idle' }
  }
})

function showResult(data) {
  const fields = data.fields || {}
  const table = data.table || {}
  const corrections = data.corrections || {}
  Object.assign(meta, data.meta || {})
  fieldRows.value = Object.entries(fields).map(([name, info]) => {
    const display = corrections[name] ?? info.corrected ?? info.cleaned ?? info.value ?? ''
    return {
      name,
      label: (info.label && info.label!==name) ? `${name} (${info.label})` : name,
      found: info.status!=='not_found',
      display,
      confidence: info.confidence ? Math.round(info.confidence*100)+'%' : '',
      editing: false, _original: display,
      editVal: display
    }
  })
  tableData.headers = table.headers || []
  tableData.rows = (table.rows||[]).map((row,i) => { const o={}; row.forEach((c,j)=>o[String(j)]=c); return o })
  jsonText.value = JSON.stringify(data, null, 2)
  imageUrl.value = api.imageUrl(data.job_id || viewingJobId.value)

  // Unknown template detection
  const tpl = data.meta?.template || data.template || ''
  unknownDetected.value = (tpl === 'unknown')
  // If unknown, show OCR blocks as preview
  const blocks = data.blocks || []
  ocrPreview.value = tpl === 'unknown' ? blocks : []
}

// Few-shot dialog
const showFewshot = ref(false)
const fsPairs = ref([])       // [{baseName, pdf:File, json:File, pdfName, jsonName, jsonContent}]
const fsUnpaired = ref([])    // [{name, type}]
const fsDragOver = ref(false)
const fsTemplateName = ref('')
const fsLearning = ref(false)
const fsResult = ref(null)

function fsBatchDrop(e) {
  fsBatchSelect({ target: e.dataTransfer })
}

function fsBatchSelect(e) {
  const dt = e.target
  const files = Array.from(dt.files || [])
  if (!files.length) return

  // Group by base name (without extension)
  const fileMap = {}  // baseName -> {pdf, json}
  for (const f of files) {
    const dotIdx = f.name.lastIndexOf('.')
    const baseName = dotIdx > 0 ? f.name.substring(0, dotIdx) : f.name
    const ext = dotIdx > 0 ? f.name.substring(dotIdx + 1).toLowerCase() : ''

    if (!fileMap[baseName]) fileMap[baseName] = {}
    if (ext === 'pdf') fileMap[baseName].pdf = f
    else if (ext === 'json') fileMap[baseName].json = f
  }

  // Form pairs
  const pairs = []
  const unpaired = []
  for (const [baseName, parts] of Object.entries(fileMap)) {
    if (parts.pdf && parts.json) {
      pairs.push({
        baseName,
        pdf: parts.pdf,
        json: parts.json,
        pdfName: parts.pdf.name,
        jsonName: parts.json.name,
        jsonContent: null
      })
    } else {
      if (parts.pdf) unpaired.push({ name: parts.pdf.name, type: 'PDF (缺 JSON)' })
      if (parts.json) unpaired.push({ name: parts.json.name, type: 'JSON (缺 PDF)' })
    }
  }

  if (pairs.length) {
    fsPairs.value = [...fsPairs.value, ...pairs]
    if (fsPairs.value.length > 5) fsPairs.value = fsPairs.value.slice(0, 5)
    // Auto-generate default template name
    if (!fsTemplateName.value && pairs[0]) {
      fsTemplateName.value = pairs[0].baseName + '_learned'
    }
  }
  fsUnpaired.value = unpaired

  // Read JSON content for each pair
  pairs.forEach(p => {
    const reader = new FileReader()
    reader.onload = () => {
      try {
        JSON.parse(reader.result)
        p.jsonContent = reader.result
      } catch {
        ElMessage.error(p.jsonName + ' 不是合法 JSON')
      }
    }
    reader.readAsText(p.json)
  })

  // Reset input so same file can be re-selected
  if (dt.files !== undefined) {
    const input = document.querySelector('input[ref="fsBatchInput"]')
    if (input) input.value = ''
  }
}

async function doFewshotLearn() {
  const valid = fsPairs.value.filter(s => s.pdf && s.jsonContent)
  if (valid.length < 2) return ElMessage.error('至少需要 2 份完整配对的样本')
  fsLearning.value = true; fsResult.value = null
  try {
    const fd = new FormData()
    valid.forEach(s => { fd.append('files', s.pdf); fd.append('gts', s.jsonContent) })
    const { data } = await api.fewshotLearn(fd)
    if (data.success) {
      fsResult.value = data.result
      // Auto-fill template name if user hasn't named it
      if (!fsTemplateName.value) {
        fsTemplateName.value = data.result.template_name
      }
      ElMessage.success('学习完成')
    }
    else { ElMessage.error(data.error || '学习失败') }
  } catch(e) { ElMessage.error('请求失败: ' + e.message) }
  finally { fsLearning.value = false }
}

async function fsApplyResult() {
  if (!fsResult.value) return
  const name = fsTemplateName.value.trim() || fsResult.value.template_name
  try {
    const { data } = await api.applyConfig({
      template_name: name,
      keywords: fsResult.value.keywords,
      fields: fsResult.value.fields
    })
    ElMessage.success(`已应用版式 "${data.template}"，添加 ${data.fields_count} 个字段`)
    showFewshot.value = false
    fsResult.value = null
    fsPairs.value = []
    fsUnpaired.value = []
    fsTemplateName.value = ''
  } catch (e) { ElMessage.error('应用失败: ' + (e.response?.data?.error || e.message)) }
}

function startFewshot() {
  fsPairs.value = []
  fsUnpaired.value = []
  fsTemplateName.value = ''
  fsResult.value = null
  showFewshot.value = true
}

async function recognizeAll() {
  const ready = fileList.value.filter(f=>f.status==='ready')
  if (!ready.length) return ElMessage.info('没有待识别的文件')
  phase.value='recognizing'
  const jids = ready.map(f=>f.job_id)
  ready.forEach(f=>f.status='processing')
  try {
    const {data} = await api.recognizeBatch(jids)
    data.results.forEach(r => {
      const f = fileList.value.find(x=>x.job_id===r.job_id)
      if (f) Object.assign(f, {
        status: r.status, template: r.template || '?',
        fields_extracted: r.fields_extracted || 0, fields_total: r.fields_total || 0
      })
    })
    phase.value='idle'
    const done = data.results.filter(r=>r.status==='done').length
    const err = data.results.filter(r=>r.status==='error').length
    ElMessage.success(`完成 ${done} 份` + (err ? `，${err} 失败` : ''))
  } catch(e) { ElMessage.error('批量识别失败'); phase.value='idle' }
}

function backToList() {
  if (urlJobId) {
    // In a result-only tab → go to main page
    window.location.href = window.location.pathname
  } else {
    viewingJobId.value=''; phase.value='idle'
  }
}

// ============ Actions ============
async function doCorrect() {
  const edits={}
  fieldRows.value.forEach(r=>{ if(r.display!==r._original) edits[r.name]=r.display })
  if(!Object.keys(edits).length) return ElMessage.info('没有修改')
  try { await api.correct(viewingJobId.value,edits); ElMessage.success('已保存')
    const {data}=await api.result(viewingJobId.value); showResult(data)
  } catch(e) { ElMessage.error('失败') }
}
function doExport(fmt) { const a=document.createElement('a'); a.href=api.exportUrl(viewingJobId.value,fmt); a.click() }
</script>

<style scoped>
.app-shell{display:flex;flex-direction:column;height:100vh;background:#f0f2f5;font-family:-apple-system,'Segoe UI',sans-serif}
.topbar{display:flex;align-items:center;padding:10px 24px;background:#fff;border-bottom:1px solid #e5e7eb;gap:20px;flex-shrink:0}
.brand{display:flex;align-items:center;gap:12px}
.logo{width:36px;height:36px;background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;letter-spacing:-0.5px}
.brand h1{font-size:16px;margin:0;line-height:1.2}.subtitle{font-size:11px;color:#888}
.spacer{flex:1}

.pipeline-steps{display:flex;align-items:center;gap:0}
.step{display:flex;align-items:center;gap:6px}
.step-dot{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;background:#f3f4f6;color:#9ca3af;transition:all .3s}
.step.active .step-dot{background:#3b82f6;color:#fff;box-shadow:0 0 0 4px rgba(59,130,246,.2)}
.step.done .step-dot{background:#10b981;color:#fff}
.step-label{font-size:11px;color:#9ca3af;transition:all .3s}
.step.active .step-label{color:#3b82f6;font-weight:600}.step.done .step-label{color:#10b981}
.step-line{width:32px;height:2px;background:#f3f4f6;margin:0 2px;transition:all .3s}
.step-line.done{background:#10b981}
.step-line.pulse{background:linear-gradient(90deg,#10b981 50%,#e5e7eb 50%);animation:pulse .8s infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

.body{flex:1;overflow:hidden;display:flex}

/* Hero */
.hero-illustration{width:100%;max-width:500px;margin-bottom:8px}
.hero-illustration svg{width:100%;height:auto}

/* Upload */
.upload-stage{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;gap:24px;overflow-y:auto}
.upload-cols{display:flex;gap:20px;max-width:840px;width:100%}
.dz-box{flex:1;max-width:400px;padding:56px 32px;border:2px dashed #d1d5db;border-radius:16px;text-align:center;background:#fff;transition:all .3s;display:flex;flex-direction:column;align-items:center;gap:14px}
.dz-box:hover{border-color:#94a3b8;box-shadow:0 2px 12px rgba(0,0,0,.04)}
.dz-box.over{border-color:#3b82f6;background:#eff6ff;box-shadow:0 4px 24px rgba(59,130,246,.1)}
.dz-icon{font-size:52px}.dz-title{font-size:16px;font-weight:600;color:#374151}.dz-hint{font-size:13px;color:#94a3b8}

/* File pool */
.file-pool{width:840px;max-width:95%}
.pool-head{display:flex;align-items:center;gap:10px;padding:8px 14px;background:#fff;border-radius:10px 10px 0 0;border:1px solid #e5e7eb;border-bottom:none;font-size:13px}
.pool-head b{color:#1e293b}
.pool-grid{background:#fff;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 10px 10px;max-height:360px;overflow-y:auto}
.pool-card{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid #f1f5f9;font-size:13px;cursor:pointer;transition:.1s}
.pool-card:hover{background:#f8fafc}.pool-card:last-child{border-bottom:none}
.pool-card.active{background:#eff6ff;border-left:3px solid #3b82f6;padding-left:11px}
.pool-card.done .pc-name{color:#374151}
.pc-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;background:#e5e7eb}
.pc-dot.ok{background:#10b981}.pc-dot.busy{background:#f59e0b;animation:pulse .8s infinite}.pc-dot.err{background:#ef4444}
.pc-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}
.pc-size{font-size:11px;color:#94a3b8;flex-shrink:0;width:50px;text-align:right}
.pc-tpl{font-size:10px;background:#f1f5f9;color:#64748b;padding:1px 6px;border-radius:3px;flex-shrink:0}

/* Result */
.result-stage{flex:1;display:flex;flex-direction:column;overflow:hidden}
.result-toolbar{display:flex;justify-content:space-between;align-items:center;padding:10px 20px;background:#fff;border-bottom:1px solid #e5e7eb;flex-shrink:0;gap:12px;box-shadow:0 1px 3px rgba(0,0,0,.03)}
.toolbar-left,.toolbar-right{display:flex;align-items:center;gap:10px}
.meta-item{font-size:12px;color:#64748b;padding:2px 8px;background:#f8fafc;border-radius:4px}

.dual-pane{flex:1;display:flex;overflow:hidden;gap:2px;background:#d1d5db}
.pane-original{flex:1;overflow:auto;background:#e5e7eb;display:flex;align-items:flex-start;justify-content:center;min-width:0}
.orig-img{max-width:100%;height:auto}
.pane-fields{flex:0 0 42%;min-width:400px;max-width:550px;overflow-y:auto;padding:14px;background:#fff;display:flex;flex-direction:column;gap:10px}
.section-title{font-size:13px;font-weight:700;color:#1e293b;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #f1f5f9;letter-spacing:.3px}
.field-cards{display:flex;flex-direction:column;gap:3px}
.field-card{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;background:#fff;border:1px solid #f1f5f9;font-size:13px;transition:all .2s}
.field-card:hover{border-color:#e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.field-card.miss{opacity:.45;background:#fafafa}
.fc-label{min-width:110px;font-weight:600;flex-shrink:0;font-size:11px;white-space:nowrap;color:#64748b;text-transform:uppercase;letter-spacing:.4px}
.fc-value{flex:1;cursor:pointer;word-break:break-all;border-radius:4px;padding:3px 6px;transition:.15s;color:#1e293b;font-weight:500}
.fc-value:hover{background:#f0f9ff}
.fc-value.empty{color:#cbd5e1;font-style:italic;font-weight:400}
.fc-conf{font-size:10px;color:#94a3b8;flex-shrink:0;font-family:Consolas,monospace;background:#f8fafc;padding:1px 5px;border-radius:3px}
.cargo-box{margin-top:12px}
.json-collapse{margin-top:8px}
.json-block{background:#1e293b;color:#a5b4c2;padding:14px;font-size:11px;font-family:Consolas,monospace;max-height:300px;overflow:auto;white-space:pre-wrap;border-radius:8px;margin:0;line-height:1.5}

/* Unknown template */
.unknown-banner{display:flex;align-items:flex-start;gap:12px;padding:16px;background:linear-gradient(135deg,#fef3c7,#fef9c3);border:1px solid #fbbf24;border-radius:10px;margin-bottom:12px}
.ub-icon{font-size:28px;flex-shrink:0}
.ub-text{flex:1}
.ub-title{font-size:14px;font-weight:700;color:#92400e;margin:0 0 4px}
.ub-desc{font-size:12px;color:#a16207;margin:0 0 4px}
.ub-hint{font-size:11px;color:#ca8a04;margin:0}
.ocr-preview{margin-top:12px}
.ocr-list{max-height:260px;overflow-y:auto;border:1px solid #e5e7eb;border-radius:8px;background:#fafafa}
.ocr-row{display:flex;align-items:center;gap:8px;padding:5px 10px;border-bottom:1px solid #f3f4f6;font-size:12px}
.ocr-row:last-child{border-bottom:none}
.ocr-idx{width:28px;text-align:center;color:#94a3b8;font-size:10px;flex-shrink:0}
.ocr-text{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#374151}
.ocr-conf{font-size:10px;color:#94a3b8;flex-shrink:0;font-family:Consolas,monospace}

/* Few-shot dialog */
.fs-batch-drop{padding:40px 24px;border:2px dashed #d1d5db;border-radius:12px;text-align:center;background:#fff;transition:all .3s;display:flex;flex-direction:column;align-items:center;gap:8px}
.fs-batch-drop:hover{border-color:#94a3b8}
.fs-batch-drop.over{border-color:#3b82f6;background:#eff6ff}
.fs-batch-icon{font-size:40px}.fs-batch-title{font-size:15px;font-weight:600;color:#374151;margin:0}.fs-batch-hint{font-size:12px;color:#94a3b8;margin:0}
.fs-pairs-box{margin-top:16px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}
.fs-pairs-head{padding:8px 14px;background:#f8fafc;font-size:13px;color:#374151;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;justify-content:space-between}
.fs-pair-row{display:flex;align-items:center;gap:10px;padding:8px 14px;border-bottom:1px solid #f8fafc;font-size:13px}
.fs-pair-row:last-child{border-bottom:none}
.fs-pair-idx{width:22px;height:22px;background:#f1f5f9;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:#64748b;flex-shrink:0}
.fs-pair-name{font-weight:600;color:#1e293b;flex-shrink:0}
.fs-pair-detail{flex:1;font-size:11px;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fs-pair-check{font-size:14px;color:#10b981;flex-shrink:0}
.fs-result{margin-top:16px}

/* History */
.history-list{display:flex;flex-direction:column;gap:8px}
.history-card{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer;transition:.15s}
.history-card:hover{background:#f8fafc;border-color:#93c5fd}
.hc-left{flex:1;overflow:hidden}
.hc-name{display:block;font-size:13px;font-weight:600;color:#1e293b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hc-meta{display:block;font-size:11px;color:#94a3b8;margin-top:2px}
.hc-right{flex-shrink:0}
.hc-time{font-size:11px;color:#cbd5e1}

/* Config drawer */
.config-drawer{display:flex;flex-direction:column;gap:16px}
.config-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px}
.cc-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.cc-name{font-size:15px;font-weight:700;color:#1e293b}
.cc-spacer{flex:1}
.cc-keywords{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:12px;font-size:12px}
.cc-label{color:#888;font-size:12px}
.cc-kw{margin:0}
.cc-none{color:#cbd5e1;font-size:12px;font-style:italic}
.cc-fields{border:1px solid #f1f5f9;border-radius:8px;overflow:hidden}
.cc-field-head{display:flex;align-items:center;padding:8px 12px;background:#f8fafc;border-bottom:1px solid #f1f5f9;font-size:11px;font-weight:600;color:#64748b}
.cc-field-row{display:flex;align-items:center;padding:7px 12px;border-bottom:1px solid #f8fafc;font-size:12px}
.cc-field-row:last-child{border-bottom:none}
.ccf-col{flex-shrink:0;overflow:hidden;text-overflow:ellipsis}
.field-name{font-weight:500;color:#374151}
.cc-anchor{margin:0 2px 2px 0}
.pos-icon{font-size:16px;color:#3b82f6;font-weight:700}
</style>
