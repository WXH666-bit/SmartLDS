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
    <el-button size="small" type="primary" plain @click="showVisionSettings=true; loadVisionSettings()">模型设置</el-button>
  </header>

  <!-- ============ Body ============ -->
  <main class="body">

    <!-- === Upload Stage === -->
    <div v-if="!resultReady" class="upload-stage">
      <section class="home-hero">
        <div class="hero-copy">
          <el-tag size="small" effect="dark" class="hero-pill">SmartLDS · 单证结构化识别</el-tag>
          <h2>把物流单证变成可校正、可导出的结构化字段</h2>
          <p>本地规则优先，低置信度时可切换到视觉大模型兜底。适合提单、报关单、快递面单和复杂表单的混合识别流程。</p>
          <div class="hero-actions">
            <el-button type="primary" size="large" round @click="openMultiInput">上传单据</el-button>
            <el-button size="large" round @click="showVisionSettings=true; loadVisionSettings()">配置大模型</el-button>
          </div>
          <div class="hero-metrics">
            <div><b>规则优先</b><span>高置信度样本不花模型成本</span></div>
            <div><b>原字段名</b><span>每个版式保留自己的 schema</span></div>
            <div><b>可导出</b><span>JSON / Excel 一键保存</span></div>
          </div>
        </div>
        <div class="hero-card">
          <div class="scan-card">
            <div class="scan-top">
              <span></span><span></span><span></span>
            </div>
            <div class="scan-title">BILL OF LADING</div>
            <div class="scan-row"><i>Shipper</i><strong>Johnson PLC</strong></div>
            <div class="scan-row"><i>B/L No.</i><strong>BL10398483</strong></div>
            <div class="scan-row"><i>Port</i><strong>SHANGHAI → HAMBURG</strong></div>
            <div class="scan-light"></div>
          </div>
        </div>
      </section>

      <div class="upload-panel">
        <div class="upload-cols">
          <div class="dz-box files-dz" :class="{ over: filesOver }"
               @dragover.prevent="filesOver=true" @dragleave.prevent="filesOver=false"
               @drop.prevent="filesOver=false; filesDropped($event)">
            <div class="dz-icon file-icon" aria-hidden="true">
              <svg viewBox="0 0 96 96" fill="none">
                <rect x="25" y="14" width="42" height="58" rx="8" fill="url(#fileBody)" />
                <path d="M58 14v15c0 4 3 7 7 7h15L58 14Z" fill="#dbeafe" />
                <rect x="33" y="38" width="26" height="4" rx="2" fill="#60a5fa" opacity=".9" />
                <rect x="33" y="49" width="31" height="4" rx="2" fill="#93c5fd" />
                <rect x="33" y="60" width="20" height="4" rx="2" fill="#bfdbfe" />
                <path d="M20 77h52" stroke="#2563eb" stroke-width="4" stroke-linecap="round" opacity=".18" />
                <defs>
                  <linearGradient id="fileBody" x1="25" y1="14" x2="73" y2="76" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#eff6ff" />
                    <stop offset="1" stop-color="#dbeafe" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <p class="dz-title">拖拽 PDF / 图片到这里</p>
            <p class="dz-hint">支持 PDF、PNG、JPG，单文件最大 32MB</p>
            <el-button type="primary" round @click="openMultiInput">选择文件</el-button>
            <input ref="multiInput" type="file" accept=".pdf,.png,.jpg,.jpeg" multiple hidden @change="onMultiChange">
          </div>

          <div class="dz-box zip-dz" :class="{ over: zipOver }"
               @dragover.prevent="zipOver=true" @dragleave.prevent="zipOver=false"
               @drop.prevent="zipOver=false; zipDropped($event)">
            <div class="dz-icon zip-icon" aria-hidden="true">
              <svg viewBox="0 0 96 96" fill="none">
                <path d="M48 13 78 30 48 47 18 30 48 13Z" fill="#fde68a" />
                <path d="M18 30v35l30 18V47L18 30Z" fill="#f59e0b" />
                <path d="M78 30v35L48 83V47l30-17Z" fill="#d97706" />
                <path d="m35 20 30 17" stroke="#92400e" stroke-width="7" stroke-linecap="round" opacity=".45" />
                <path d="M36 56h12v12H36z" fill="#fff7ed" opacity=".8" />
                <path d="M24 73h48" stroke="#f59e0b" stroke-width="4" stroke-linecap="round" opacity=".2" />
              </svg>
            </div>
            <p class="dz-title">批量导入 ZIP</p>
            <p class="dz-hint">自动解压并加入待识别列表</p>
            <el-button round @click="openZipInput">选择 ZIP</el-button>
            <input ref="zipInput" type="file" accept=".zip" hidden @change="onZipChange">
          </div>
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
          <span class="meta-item source-badge" :class="meta.extraction_source">{{ extractionSourceLabel }}</span>
          <span v-if="meta.confidence !== undefined" class="meta-item">置信度 {{ Math.round((meta.confidence || 0)*100) }}%</span>
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

  <!-- ============ Vision Model Settings ============ -->
  <el-dialog v-model="showVisionSettings" title="视觉大模型兜底设置" width="620px" :close-on-click-modal="false">
    <div v-if="visionSettingsLoading" style="text-align:center;padding:32px">
      <el-icon class="is-loading" :size="28"><Loading /></el-icon>
    </div>
    <el-form v-else label-width="110px" class="vision-form">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="默认仍先跑本地 PaddleOCR + 规则抽取；只有低置信度、unknown 或复杂表单时才调用这里配置的大模型。"
        style="margin-bottom:16px"
      />
      <el-form-item label="启用兜底">
        <el-switch v-model="visionSettings.enabled" active-text="启用" inactive-text="关闭" />
      </el-form-item>
      <el-form-item label="模型供应商">
        <el-select v-model="visionSettings.provider" style="width:100%" @change="onVisionProviderChange">
          <el-option v-for="p in visionOptions.providers" :key="p.key" :label="p.label" :value="p.key" />
        </el-select>
      </el-form-item>
      <el-form-item label="模型">
        <el-select v-model="visionSettings.model" filterable allow-create style="width:100%">
          <el-option v-for="m in currentVisionModels" :key="m.value" :label="m.label" :value="m.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="API Key">
        <el-input v-model="visionSettings.api_key" type="password" show-password clearable placeholder="留空则保留已保存的 key" />
        <div class="form-hint">
          <span v-if="visionSettings.has_api_key">已保存：{{ visionSettings.masked_api_key }}</span>
          <span v-else>尚未保存 API Key</span>
        </div>
      </el-form-item>
      <el-form-item label="触发阈值">
        <el-slider v-model="visionSettings.threshold" :min="0.1" :max="0.95" :step="0.01" show-input />
      </el-form-item>
      <el-form-item label="接口地址">
        <el-input v-model="visionSettings.base_url" clearable />
        <div class="form-hint">千问默认使用 DashScope OpenAI 兼容模式；通常不用改。</div>
      </el-form-item>
      <div class="vision-actions">
        <el-button type="danger" plain @click="clearVisionSettings">清除保存</el-button>
        <div class="spacer"></div>
        <el-button @click="showVisionSettings=false">取消</el-button>
        <el-button type="primary" :loading="visionSettingsSaving" @click="saveVisionSettings">保存设置</el-button>
      </div>
    </el-form>
  </el-dialog>

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

// Vision fallback settings
const showVisionSettings = ref(false)
const visionSettingsLoading = ref(false)
const visionSettingsSaving = ref(false)
const visionOptions = reactive({ providers: [] })
const visionSettings = reactive({
  enabled: false,
  provider: 'qwen',
  model: 'qwen3.6-plus',
  base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  api_key: '',
  threshold: 0.55,
  has_api_key: false,
  masked_api_key: ''
})
const currentVisionModels = computed(() => {
  const provider = visionOptions.providers.find(p => p.key === visionSettings.provider)
  return provider?.models || []
})

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

function applyVisionSettingsPayload(payload) {
  const data = payload || {}
  if (data.options?.providers) visionOptions.providers = data.options.providers
  const s = data.settings || {}
  Object.assign(visionSettings, {
    enabled: !!s.enabled,
    provider: s.provider || 'qwen',
    model: s.model || 'qwen3.6-plus',
    base_url: s.base_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    api_key: '',
    threshold: Number(s.threshold ?? 0.55),
    has_api_key: !!s.has_api_key,
    masked_api_key: s.masked_api_key || ''
  })
}

async function loadVisionSettings() {
  visionSettingsLoading.value = true
  try {
    const { data } = await api.getVisionSettings()
    applyVisionSettingsPayload(data)
  } catch (e) {
    ElMessage.error('加载模型设置失败')
  } finally {
    visionSettingsLoading.value = false
  }
}

function onVisionProviderChange() {
  const provider = visionOptions.providers.find(p => p.key === visionSettings.provider)
  if (!provider) return
  visionSettings.model = provider.default_model || provider.models?.[0]?.value || visionSettings.model
  visionSettings.base_url = provider.default_base_url || visionSettings.base_url
}

async function saveVisionSettings() {
  visionSettingsSaving.value = true
  try {
    const payload = {
      enabled: visionSettings.enabled,
      provider: visionSettings.provider,
      model: visionSettings.model,
      base_url: visionSettings.base_url,
      threshold: visionSettings.threshold
    }
    if (visionSettings.api_key.trim()) payload.api_key = visionSettings.api_key.trim()
    const { data } = await api.saveVisionSettings(payload)
    applyVisionSettingsPayload(data)
    ElMessage.success('模型设置已保存')
  } catch (e) {
    ElMessage.error('保存模型设置失败: ' + (e.response?.data?.error || e.message))
  } finally {
    visionSettingsSaving.value = false
  }
}

async function clearVisionSettings() {
  try {
    const { data } = await api.clearVisionSettings()
    applyVisionSettingsPayload(data)
    ElMessage.success('模型设置已清除，恢复默认千问配置')
  } catch (e) {
    ElMessage.error('清除模型设置失败')
  }
}

const resultReady = computed(() => phase.value==='done' && !!viewingJobId.value)
const pipelineStep = computed(() => {
  if (phase.value==='done') return 3
  if (phase.value==='recognizing') return 2
  if (fileList.value.length) return 1
  return 0
})
const extractionSourceLabel = computed(() => {
  if (meta.extraction_source === 'vision_fallback') return '视觉兜底'
  if (meta.extraction_source === 'local_rules_with_vision_patch') return '规则+视觉修补'
  return '规则识别'
})

function formatSize(bytes) {
  if (!bytes || bytes < 0) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB'
  return (bytes/1048576).toFixed(1) + ' MB'
}

function openMultiInput() {
  multiInput.value?.click()
}

function openZipInput() {
  zipInput.value?.click()
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
      label: info.label || name,
      canonicalKey: info.canonical_key || '',
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
      fields: fsResult.value.fields,
      validators: fsResult.value.validators || {}
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

/* Home */
.upload-stage{flex:1;display:flex;flex-direction:column;align-items:center;padding:34px 24px;gap:22px;overflow-y:auto;background:
  radial-gradient(circle at 15% 10%,rgba(59,130,246,.18),transparent 30%),
  radial-gradient(circle at 85% 5%,rgba(16,185,129,.12),transparent 26%),
  linear-gradient(180deg,#f8fbff 0%,#f1f5f9 100%)}
.home-hero{width:min(1120px,100%);display:grid;grid-template-columns:minmax(0,1.2fr) 420px;gap:32px;align-items:center}
.hero-copy{padding:18px 0}
.hero-pill{border:none;background:linear-gradient(135deg,#2563eb,#7c3aed);font-weight:700}
.hero-copy h2{font-size:42px;line-height:1.08;margin:18px 0 14px;color:#0f172a;letter-spacing:-1.2px}
.hero-copy p{max-width:620px;font-size:15px;line-height:1.8;color:#64748b;margin:0}
.hero-actions{display:flex;gap:12px;margin-top:24px}
.hero-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:26px;max-width:680px}
.hero-metrics div{padding:14px 16px;border:1px solid rgba(148,163,184,.24);background:rgba(255,255,255,.72);backdrop-filter:blur(10px);border-radius:16px;box-shadow:0 10px 30px rgba(15,23,42,.04)}
.hero-metrics b{display:block;font-size:14px;color:#0f172a;margin-bottom:4px}
.hero-metrics span{font-size:12px;color:#64748b}
.hero-card{display:flex;justify-content:center}
.scan-card{position:relative;width:360px;min-height:330px;border-radius:28px;background:linear-gradient(145deg,#ffffff,#edf4ff);box-shadow:0 30px 80px rgba(37,99,235,.22);border:1px solid rgba(255,255,255,.8);padding:24px;overflow:hidden}
.scan-card:before{content:"";position:absolute;inset:18px;border:1px dashed rgba(37,99,235,.25);border-radius:22px}
.scan-top{display:flex;gap:6px;position:relative;z-index:1}
.scan-top span{width:10px;height:10px;border-radius:50%;background:#cbd5e1}
.scan-title{position:relative;z-index:1;margin:28px 0 20px;font-size:22px;font-weight:900;color:#1d4ed8;letter-spacing:.6px}
.scan-row{position:relative;z-index:1;display:flex;justify-content:space-between;gap:14px;padding:13px 0;border-bottom:1px solid #e2e8f0}
.scan-row i{font-style:normal;color:#64748b;font-size:12px}.scan-row strong{font-size:13px;color:#0f172a;text-align:right}
.scan-light{position:absolute;left:-20%;right:-20%;top:48%;height:32px;background:linear-gradient(90deg,transparent,rgba(59,130,246,.18),transparent);transform:rotate(-8deg);animation:scanline 2.4s ease-in-out infinite}
@keyframes scanline{0%,100%{top:22%;opacity:.25}50%{top:72%;opacity:.85}}

/* Upload */
.upload-panel{width:min(960px,100%);background:linear-gradient(135deg,rgba(255,255,255,.9),rgba(248,250,252,.76));border:1px solid rgba(226,232,240,.9);border-radius:26px;padding:18px;box-shadow:0 22px 70px rgba(15,23,42,.09);backdrop-filter:blur(16px)}
.upload-cols{display:flex;gap:16px;width:100%}
.dz-box{flex:1;position:relative;isolation:isolate;overflow:hidden;padding:36px 28px;border:1px solid rgba(203,213,225,.9);border-radius:20px;text-align:center;background:linear-gradient(180deg,#fff,rgba(248,250,252,.96));transition:transform .25s,box-shadow .25s,border-color .25s;display:flex;flex-direction:column;align-items:center;gap:12px}
.dz-box:before{content:"";position:absolute;inset:-1px;border-radius:inherit;padding:1px;background:linear-gradient(135deg,rgba(59,130,246,.72),rgba(14,165,233,.08),rgba(16,185,129,.45));-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;opacity:.25;transition:opacity .25s;pointer-events:none}
.dz-box:after{content:"";position:absolute;top:-80%;left:-30%;width:50%;height:240%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.72),transparent);transform:rotate(22deg) translateX(-180%);transition:transform .55s ease;z-index:-1;pointer-events:none}
.dz-box>*{position:relative;z-index:1}
.dz-box:hover{border-color:rgba(96,165,250,.8);transform:translateY(-3px);box-shadow:0 18px 42px rgba(37,99,235,.14)}
.dz-box:hover:before,.dz-box.over:before{opacity:.95}
.dz-box:hover:after,.dz-box.over:after{transform:rotate(22deg) translateX(360%)}
.dz-box.over{border-color:#2563eb;background:linear-gradient(180deg,#eff6ff,#fff);box-shadow:0 20px 48px rgba(59,130,246,.2)}
.zip-dz:before{background:linear-gradient(135deg,rgba(245,158,11,.72),rgba(251,191,36,.08),rgba(59,130,246,.32))}
.dz-icon{width:86px;height:86px;border-radius:26px;display:flex;align-items:center;justify-content:center;position:relative;box-shadow:inset 0 1px 0 rgba(255,255,255,.78),0 16px 36px rgba(15,23,42,.1);transition:transform .25s,box-shadow .25s}
.dz-icon:after{content:"";position:absolute;inset:14px;border-radius:20px;background:rgba(255,255,255,.34);filter:blur(14px);z-index:-1;pointer-events:none}
.dz-box:hover .dz-icon,.dz-box.over .dz-icon{transform:translateY(-4px) scale(1.04);box-shadow:inset 0 1px 0 rgba(255,255,255,.85),0 20px 42px rgba(37,99,235,.16)}
.dz-icon svg{width:68px;height:68px;display:block;filter:drop-shadow(0 9px 12px rgba(15,23,42,.1))}
.file-icon{background:radial-gradient(circle at 30% 20%,#fff 0,#eff6ff 34%,#dbeafe 100%)}
.zip-icon{background:radial-gradient(circle at 30% 20%,#fff 0,#fff7ed 34%,#ffedd5 100%)}
.dz-box :deep(.el-button){font-weight:800;box-shadow:0 10px 22px rgba(37,99,235,.13);transition:transform .2s,box-shadow .2s}
.dz-box :deep(.el-button:hover){transform:translateY(-1px);box-shadow:0 14px 28px rgba(37,99,235,.18)}
.dz-title{font-size:16px;font-weight:800;color:#1e293b;margin:0}.dz-hint{font-size:13px;color:#94a3b8;margin:0}

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
.source-badge{font-weight:700}
.source-badge.local_rules{color:#2563eb;background:#eff6ff}
.source-badge.vision_fallback{color:#7c2d12;background:#ffedd5}
.source-badge.local_rules_with_vision_patch{color:#166534;background:#dcfce7}

.dual-pane{flex:1;display:flex;overflow:hidden;gap:2px;background:#d1d5db}
.pane-original{flex:1;overflow:auto;background:#e5e7eb;display:flex;align-items:flex-start;justify-content:center;min-width:0}
.orig-img{max-width:100%;height:auto}
.pane-fields{flex:0 0 42%;min-width:400px;max-width:550px;overflow-y:auto;padding:14px;background:#fff;display:flex;flex-direction:column;gap:10px}
.section-title{font-size:13px;font-weight:700;color:#1e293b;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #f1f5f9;letter-spacing:.3px}
.field-cards{display:flex;flex-direction:column;gap:3px}
.field-card{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;background:#fff;border:1px solid #f1f5f9;font-size:13px;transition:all .2s}
.field-card:hover{border-color:#e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.field-card.miss{opacity:.45;background:#fafafa}
.fc-label{min-width:110px;font-weight:600;flex-shrink:0;font-size:11px;white-space:nowrap;color:#64748b;letter-spacing:.4px}
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

/* Vision settings */
.vision-form{padding-top:4px}
.form-hint{font-size:12px;color:#94a3b8;line-height:1.6;margin-top:6px}
.vision-actions{display:flex;align-items:center;gap:10px;margin-top:18px}

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

@media (max-width: 980px){
  .topbar{gap:10px;padding:10px 14px;flex-wrap:wrap}
  .pipeline-steps{display:none}
  .home-hero{grid-template-columns:1fr}
  .hero-card{display:none}
  .hero-copy h2{font-size:32px}
  .hero-metrics{grid-template-columns:1fr}
  .upload-cols{flex-direction:column}
  .pane-fields{min-width:320px;flex-basis:46%}
}
</style>
