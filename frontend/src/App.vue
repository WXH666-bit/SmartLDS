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
               :class="{ active: viewingJobId===f.job_id, done: f.status==='done', error: f.status==='error' }"
               @click="viewJob(f)">
            <span class="pc-dot" :class="{ ok: f.status==='done', busy: f.status==='processing' || f.status==='uploading', err: f.status==='error' }"></span>
            <div class="pc-main">
              <div class="pc-row">
                <span class="pc-name">{{ f.filename }}</span>
                <span class="pc-size">{{ f.size }}</span>
                <span v-if="f.status==='done'" class="pc-tpl">{{ f.template }}</span>
                <span class="pc-state" :class="f.status">{{ fileStatusLabel(f) }} · {{ fileProgress(f) }}%</span>
              </div>
              <div class="pc-progress">
                <span class="pc-progress-fill" :class="f.status" :style="{ width: fileProgress(f) + '%' }"></span>
              </div>
            </div>
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
          <span v-if="tableList.length" class="meta-item">表格 {{ displayTableRowCount }} 行</span>
        </div>
        <div class="toolbar-right">
          <el-button size="small" type="primary" plain @click="openAddFieldDialog">添加字段</el-button>
          <el-button size="small" type="primary" plain @click="openTableEditor">编辑表格</el-button>
          <el-button size="small" type="success" plain @click="openFeedbackDialog">反哺版式</el-button>
          <el-button size="small" plain @click="toggleJsonInspector">{{ jsonInspectorOpen ? '隐藏 JSON' : '显示 JSON' }}</el-button>
          <el-button size="small" @click="openExportDialog('json')">JSON</el-button>
          <el-button size="small" @click="openExportDialog('xlsx')">Excel</el-button>
          <el-button size="small" type="warning" @click="doCorrect">保存校正</el-button>
        </div>
      </div>
      <div v-if="meta.warnings?.length" class="result-warning-bar">
        <el-alert
          v-for="(warning, index) in meta.warnings"
          :key="index"
          type="warning"
          show-icon
          :closable="false"
          :title="warning"
        />
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
            <div v-for="row in fieldRows" :key="row.name" class="field-card" :class="{ miss: !row.found, manual: row.manual }">
              <div
                v-if="!row.labelEditing"
                class="fc-label"
                title="双击修改字段名"
                @dblclick="row.labelEditing=true; row.labelEditVal=row.label"
              >{{ row.label }}</div>
              <el-input
                v-else
                v-model="row.labelEditVal"
                size="small"
                class="fc-label-input"
                @input="previewFieldLabelInJson(row)"
                @blur="finishFieldLabelEditAndSync(row)"
                @keyup.enter="finishFieldLabelEditAndSync(row)"
                autofocus
              />
              <el-tag v-if="row.manual" size="small" type="success" effect="plain">人工</el-tag>
              <div class="fc-value" v-if="!row.editing"
                   @dblclick="row.editing=true; row.editVal=row.display"
                   :class="{ empty: !row.display }">{{ row.display || '(空)' }}</div>
              <el-input v-else v-model="row.editVal" size="small" @input="previewFieldValueInJson(row)" @blur="finishFieldEditAndSync(row)" @keyup.enter="finishFieldEditAndSync(row)" autofocus />
              <div class="fc-conf" v-if="row.confidence">{{ row.confidence }}</div>
              <el-button v-if="row.manual" size="small" text type="danger" @click="removeManualField(row.name)">删除</el-button>
            </div>
          </div>
          <div v-if="tableList.length" class="cargo-box">
            <div class="section-title">货物明细</div>
            <div class="table-tools">
              <el-tag v-if="tableData.source" size="small" effect="plain">{{ tableData.source }}</el-tag>
              <el-button size="small" text type="primary" @click="openTableEditor">编辑</el-button>
            </div>
            <div v-for="(table, tableIndex) in tableList" :key="tableIndex" class="cargo-table-block">
              <div v-if="table.title || table.confidence !== undefined" class="cargo-table-title">
                <span>{{ table.title || `表格 ${tableIndex + 1}` }}</span>
                <el-tag v-if="table.confidence !== undefined" size="small" effect="plain">{{ Math.round((table.confidence || 0)*100) }}%</el-tag>
              </div>
              <el-table :data="table.rows" size="small" stripe border max-height="240">
                <el-table-column v-for="(h,i) in table.headers" :key="i" :prop="String(i)" :label="h" min-width="90" show-overflow-tooltip />
              </el-table>
            </div>
          </div>
        </div>
        <aside class="json-inspector" :class="{ collapsed: !jsonInspectorOpen }">
          <button
            v-if="!jsonInspectorOpen"
            class="json-inspector-rail"
            type="button"
            @click="toggleJsonInspector"
          >
            JSON
          </button>
          <div v-else class="json-inspector-panel">
            <div class="json-inspector-head">
              <span>JSON 检查</span>
              <el-button size="small" text @click="toggleJsonInspector">隐藏</el-button>
            </div>
            <el-collapse v-model="jsonCollapseActive" class="json-collapse">
              <el-collapse-item title="JSON" name="json">
                <pre ref="jsonBlockRef" class="json-block"><span
                  v-for="(line, index) in jsonLines"
                  :key="index"
                  class="json-line"
                  :class="{ active: index === activeJsonLine }"
                  :data-json-line="index"
                >{{ line }}</span></pre>
              </el-collapse-item>
            </el-collapse>
          </div>
        </aside>
      </div>
    </div>
  </main>

  <!-- ============ Manual field dialog ============ -->
  <el-dialog v-model="showAddField" title="添加人工字段" width="420px">
    <el-form label-width="80px">
      <el-form-item label="字段名">
        <el-input v-model="newField.label" placeholder="例如：客户备注 / XXX字段" />
      </el-form-item>
      <el-form-item label="字段值">
        <el-input v-model="newField.value" type="textarea" :rows="3" placeholder="填写字段值" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showAddField=false">取消</el-button>
      <el-button type="primary" @click="addManualField">添加</el-button>
    </template>
  </el-dialog>

  <!-- ============ Manual table editor ============ -->
  <el-dialog v-model="showTableEditor" title="编辑最终表格" width="760px" :close-on-click-modal="false">
    <div class="table-editor">
      <div class="table-editor-head">
        <span class="te-title">表头列</span>
        <el-button size="small" type="primary" plain @click="addTableColumn">新增列</el-button>
        <el-button size="small" type="success" plain @click="addTableRow">新增行</el-button>
      </div>
      <div v-if="!tableEditor.headers.length" class="table-empty-tip">还没有表头，先新增一列即可创建人工表格。</div>
      <div v-else class="table-edit-grid">
        <div class="table-edit-header">
          <div v-for="(h, colIndex) in tableEditor.headers" :key="'h'+colIndex" class="table-edit-cell table-edit-head-cell">
            <el-input v-model="tableEditor.headers[colIndex]" size="small" placeholder="列名" />
            <el-button size="small" text type="danger" @click="removeTableColumn(colIndex)">删列</el-button>
          </div>
          <div class="table-row-actions">操作</div>
        </div>
        <div v-for="(row, rowIndex) in tableEditor.rows" :key="'r'+rowIndex" class="table-edit-row">
          <div v-for="(_, colIndex) in tableEditor.headers" :key="'c'+rowIndex+'_'+colIndex" class="table-edit-cell">
            <el-input v-model="tableEditor.rows[rowIndex][colIndex]" size="small" />
          </div>
          <div class="table-row-actions">
            <el-button size="small" text type="danger" @click="removeTableRow(rowIndex)">删行</el-button>
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="showTableEditor=false">取消</el-button>
      <el-button type="primary" @click="saveTableEditor">保存表格</el-button>
    </template>
  </el-dialog>

  <!-- ============ Export options ============ -->
  <el-dialog v-model="showExportDialog" :title="`导出 ${exportFormatLabel}`" width="460px">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="字段键值适合人工查看；字段明细适合调试和程序读取。"
      style="margin-bottom:14px"
    />
    <el-checkbox v-model="exportOptions.field_values" class="export-option">
      字段键值 <span>两列/键值对，最直观</span>
    </el-checkbox>
    <el-checkbox v-model="exportOptions.field_details" class="export-option">
      字段明细 <span>包含状态、置信度、锚点等</span>
    </el-checkbox>
    <el-checkbox v-model="exportOptions.table" class="export-option">
      表格数据 <span>导出最终表格/货物明细</span>
    </el-checkbox>
    <el-checkbox v-model="exportOptions.meta" class="export-option">
      元信息 <span>任务、版式、识别时间等</span>
    </el-checkbox>
    <template #footer>
      <el-button @click="showExportDialog=false">取消</el-button>
      <el-button type="primary" @click="confirmExport">导出</el-button>
    </template>
  </el-dialog>

  <!-- ============ Feedback current result into template ============ -->
  <el-dialog v-model="showFeedback" title="反哺到指定版式" width="620px" :close-on-click-modal="false">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="可选择合并到已有版式，也可以用当前最终字段、人工新增字段和最终表头结构创建新版式；创建后会作为独立 schema 参与后续识别。"
      style="margin-bottom:14px"
    />
    <el-form label-width="90px">
      <el-form-item label="方式">
        <el-radio-group v-model="feedback.mode">
          <el-radio-button label="create">创建新版式</el-radio-button>
          <el-radio-button label="merge">合并已有版式</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="feedback.mode==='create'" label="新版式">
        <el-input v-model="feedback.template_name" clearable placeholder="例如 customs_import_v1" />
      </el-form-item>
      <el-form-item v-if="feedback.mode==='merge'" label="目标版式">
        <el-select v-model="feedback.template_name" filterable placeholder="选择要反哺的版式" style="width:100%">
          <el-option v-for="tpl in configTemplates" :key="tpl.name" :label="tpl.name" :value="tpl.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="字段">
        <el-checkbox-group v-model="feedback.field_names" class="feedback-field-list">
          <el-checkbox v-for="row in feedbackFieldOptions" :key="row.name" :label="row.name">
            {{ row.label }} <span class="feedback-value">{{ row.display }}</span>
          </el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="表格">
        <el-checkbox v-model="feedback.include_table" :disabled="!tableData.headers.length">保存当前最终表头结构</el-checkbox>
      </el-form-item>
      <el-form-item label="AI 增强">
        <el-switch
          v-model="feedback.ai_enhance"
          active-text="让视觉大模型辅助补锚点、校验和多行配置"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showFeedback=false">取消</el-button>
      <el-button type="primary" :loading="feedback.loading" @click="submitFeedback">开始反哺</el-button>
    </template>
  </el-dialog>

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
        <el-input v-model="visionSettings.api_key" type="password" show-password clearable :placeholder="visionApiKeyPlaceholder" />
        <div class="form-hint">
          <span v-if="visionSettings.has_api_key">已保存：{{ visionSettings.masked_api_key }}</span>
          <span v-else>{{ visionApiKeyHint }}</span>
        </div>
      </el-form-item>
      <el-form-item label="触发阈值">
        <el-slider v-model="visionSettings.threshold" :min="0.1" :max="0.95" :step="0.01" show-input />
      </el-form-item>
      <el-form-item label="接口地址">
        <el-input v-model="visionSettings.base_url" clearable />
        <div class="form-hint">{{ visionBaseUrlHint }}</div>
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
      <el-switch
        v-model="fsAiEnhance"
        size="small"
        active-text="AI 增强"
      />
      <el-button size="small" type="primary" :loading="fsLearning" @click="doFewshotLearn" :disabled="fsPairs.length<2">开始学习</el-button>
    </div>
    <p v-if="fsAiEnhance && !visionSettings.enabled" class="fs-ai-hint">需要先在“模型设置”中启用视觉兜底并保存模型设置。</p>

    <!-- Result -->
    <div v-if="fsResult" class="fs-result">
      <div class="section-title">学习结果</div>
      <p style="font-size:12px;color:#888;margin:0 0 8px">
        版式: <b>{{ fsResult.template_name }}</b> · {{ fsResult.keywords.length }} 关键词 · {{ Object.keys(fsResult.fields||{}).length }} 字段
        <el-tag v-if="fsResult.ai_enhanced" size="small" type="success" effect="plain" style="margin-left:8px">AI 已增强</el-tag>
      </p>
      <el-alert
        v-for="(warning, index) in (fsResult.warnings || [])"
        :key="index"
        type="warning"
        show-icon
        :closable="false"
        :title="warning"
        style="margin-bottom:8px"
      />
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
import { ref, reactive, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import api from './api/index.js'
import {
  buildDisplayTables,
  findJsonPreviewTargetLine,
  buildResultPreviewJson,
  finishFieldEdit,
  finishFieldLabelEdit,
  isFieldRowFound,
  splitJsonPreviewLines,
} from './resultState.js'

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
const tableData = reactive({ title: '', headers: [], rows: [], source: '', confidence: undefined })
const tableList = ref([])
const tableDirty = ref(false)
const jsonText = ref('')
const jsonInspectorOpen = ref(true)
const jsonCollapseActive = ref(['json'])
const jsonBlockRef = ref(null)
const activeJsonLine = ref(-1)
const imageUrl = ref('')
const unknownDetected = ref(false)
const ocrPreview = ref([])  // OCR blocks for unknown template preview
let progressTimer = null
let jsonHighlightTimer = null

// 识别后人工补充：字段、表格、反哺指定版式
const showAddField = ref(false)
const newField = reactive({ label: '', value: '' })
const manualDirty = ref(false)
const showTableEditor = ref(false)
const tableEditor = reactive({ headers: [], rows: [] })
const showExportDialog = ref(false)
const exportFormat = ref('json')
const exportOptions = reactive({
  field_values: true,
  field_details: true,
  table: true,
  meta: true
})
const exportFormatLabel = computed(() => exportFormat.value === 'xlsx' ? 'Excel' : 'JSON')
const showFeedback = ref(false)
const feedback = reactive({
  mode: 'merge',
  template_name: '',
  field_names: [],
  include_table: true,
  ai_enhance: false,
  loading: false
})
const feedbackFieldOptions = computed(() =>
  fieldRows.value.filter(row => row.found && String(row.display || '').trim())
)

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
const currentVisionProvider = computed(() =>
  visionOptions.providers.find(p => p.key === visionSettings.provider) || {}
)
const visionApiKeyPlaceholder = computed(() => {
  const hint = currentVisionProvider.value.api_key_hint || 'API Key'
  return `留空则保留已保存的 ${hint}`
})
const visionApiKeyHint = computed(() => {
  if (currentVisionProvider.value.requires_api_key === false) {
    return '本地兼容服务可留空；Ollama 会使用 ollama 作为占位 key。'
  }
  return `尚未保存 ${currentVisionProvider.value.api_key_hint || 'API Key'}`
})
const visionBaseUrlHint = computed(() => {
  if (visionSettings.provider === 'custom') {
    return '自定义模型使用 OpenAI-compatible chat/completions；Ollama 通常填 http://localhost:11434/v1。'
  }
  if (visionSettings.provider === 'openai') {
    return 'OpenAI 默认使用 Responses API；通常不用改。'
  }
  return '千问默认使用 DashScope OpenAI 兼容模式；通常不用改。'
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
const displayTableRowCount = computed(() =>
  tableList.value.reduce((total, table) => total + (table.rows?.length || 0), 0)
)
const jsonLines = computed(() => splitJsonPreviewLines(jsonText.value))

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

function fileProgress(file) {
  const value = Number(file?.progress ?? 0)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
}

function fileStatusLabel(file) {
  if (file?.status === 'uploading') return '\u4e0a\u4f20\u4e2d'
  if (file?.status === 'ready') return '\u5f85\u8bc6\u522b'
  if (file?.status === 'processing') return '\u8bc6\u522b\u4e2d'
  if (file?.status === 'done') return '\u5b8c\u6210'
  if (file?.status === 'error') return '\u5931\u8d25'
  return '\u7b49\u5f85'
}

function setFileProgress(file, progress) {
  if (!file) return
  file.progress = Math.max(0, Math.min(100, progress))
}

function hasActiveProgress() {
  return fileList.value.some(file => ['uploading', 'processing'].includes(file.status))
}

function stopProgressTickerIfIdle() {
  if (!progressTimer || hasActiveProgress()) return
  clearInterval(progressTimer)
  progressTimer = null
}

function startProgressTicker() {
  if (progressTimer) return
  progressTimer = setInterval(() => {
    fileList.value.forEach(file => {
      if (file.status === 'uploading') {
        setFileProgress(file, Math.min(28, (file.progress || 8) + 4))
      } else if (file.status === 'processing') {
        const current = file.progress || 35
        const step = current < 70 ? 3 : current < 86 ? 1.5 : 0.6
        setFileProgress(file, Math.min(92, current + step))
      }
    })
    stopProgressTickerIfIdle()
  }, 650)
}

onUnmounted(() => {
  if (progressTimer) clearInterval(progressTimer)
  clearJsonHighlightTimer()
})

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
    fileList.value.push({ job_id: '...', filename: f.name, size: '...', status: 'uploading', progress: 8 })
    startProgressTicker()
    try {
      const {data} = await api.upload(f)
      const idx = fileList.value.findIndex(x=>x.filename===f.name && x.status==='uploading')
      if (idx>=0) Object.assign(fileList.value[idx], {
        job_id: data.job_id, filename: f.name,
        size: formatSize(f.size), status: 'ready', progress: 30
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
  fileList.value.push({ job_id: '...', filename: file.name, size: '...', status: 'uploading', progress: 8 })
  startProgressTicker()
  try {
    const {data} = await api.uploadZip(file)
    data.jobs.forEach(j => {
      if (!fileList.value.some(x=>x.filename===j.filename)) {
        fileList.value.push({ job_id: j.job_id, filename: j.filename, size: '-', status: 'ready', progress: 30 })
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
function clearAll() {
  fileList.value=[]; viewingJobId.value=''; phase.value='idle'
  if (progressTimer) { clearInterval(progressTimer); progressTimer = null }
}

// ============ Recognize ============
async function viewJob(f) {
  if (f.status==='done') {
    // Already done → open in new tab
    window.open(`?job=${f.job_id}`, '_blank')
    return
  }
  if (f.status==='ready') {
    f.status='processing'; f.progress = 35; phase.value='recognizing'; startProgressTicker()
    try {
      await api.recognize(f.job_id)
      const {data} = await api.result(f.job_id)
      const m = data.meta || {}
      Object.assign(f, { status: 'done', template: m.template || '?',
        fields_extracted: m.fields_extracted || 0, fields_total: m.fields_total || 0,
        progress: 100 })
      window.open(`?job=${f.job_id}`, '_blank')
      phase.value='idle'
    } catch(e) { f.status='error'; f.progress=100; phase.value='idle'; ElMessage.error('识别失败') }
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
  viewingData.value = data
  const fields = data.fields || {}
  const table = data.table || {}
  const rawCorrections = data.corrections || {}
  const corrections = rawCorrections.fields || rawCorrections
  Object.assign(meta, data.meta || {})
  fieldRows.value = Object.entries(fields).map(([name, info]) => {
    const display = corrections[name] ?? info.corrected ?? info.cleaned ?? info.value ?? ''
    const manual = info.status === 'manual_added' || info.source === 'manual'
    const found = isFieldRowFound(info, display)
    return {
      name,
      label: info.label || name,
      _originalLabel: info.label || name,
      labelEditing: false,
      labelEditVal: info.label || name,
      canonicalKey: info.canonical_key || '',
      found,
      display,
      confidence: info.confidence ? Math.round(info.confidence*100)+'%' : '',
      manual,
      status: info.status || '',
      editing: false, _original: display,
      editVal: display
    }
  })
  tableList.value = buildDisplayTables(data)
  const firstTable = tableList.value[0] || { title: '', headers: table.headers || [], rows: [], source: table.source || '', confidence: table.confidence }
  tableData.title = firstTable.title || table.title || ''
  tableData.headers = firstTable.headers || []
  tableData.rows = firstTable.rows || []
  tableData.source = firstTable.source || table.source || ''
  tableData.confidence = firstTable.confidence
  tableDirty.value = false
  manualDirty.value = false
  syncJsonPreview()
  imageUrl.value = api.imageUrl(data.job_id || viewingJobId.value)

  // Unknown template detection
  const tpl = data.meta?.template || data.template || ''
  unknownDetected.value = (tpl === 'unknown')
  // If unknown, show OCR blocks as preview
  const blocks = data.blocks || []
  ocrPreview.value = tpl === 'unknown' ? blocks : []
}

function clearJsonHighlightTimer() {
  if (!jsonHighlightTimer) return
  clearTimeout(jsonHighlightTimer)
  jsonHighlightTimer = null
}

function toggleJsonInspector() {
  jsonInspectorOpen.value = !jsonInspectorOpen.value
}

async function revealJsonTarget(target) {
  if (!target) return
  jsonInspectorOpen.value = true
  if (!jsonCollapseActive.value.includes('json')) {
    jsonCollapseActive.value = ['json']
  }
  await nextTick()
  const lineIndex = findJsonPreviewTargetLine(jsonText.value, target)
  if (lineIndex < 0) return
  activeJsonLine.value = lineIndex
  await nextTick()
  const block = jsonBlockRef.value
  const lineEl = block?.querySelector?.(`[data-json-line="${lineIndex}"]`)
  if (block && lineEl) {
    const targetTop = lineEl.offsetTop - (block.clientHeight * 0.35)
    block.scrollTop = Math.max(0, targetTop)
  }
  clearJsonHighlightTimer()
  jsonHighlightTimer = setTimeout(() => {
    activeJsonLine.value = -1
    jsonHighlightTimer = null
  }, 1800)
}

function syncJsonPreview(target = null) {
  if (!viewingData.value) return
  jsonText.value = buildResultPreviewJson(viewingData.value, fieldRows.value, tableData)
  if (target) revealJsonTarget(target)
}

function previewFieldValueInJson(row) {
  syncJsonPreview({ type: 'field', fieldKey: row.name, prop: 'value' })
}

function previewFieldLabelInJson(row) {
  syncJsonPreview({ type: 'field', fieldKey: row.name, prop: 'label' })
}

function finishFieldEditAndSync(row) {
  finishFieldEdit(row)
  syncJsonPreview({ type: 'field', fieldKey: row.name, prop: 'value' })
}

function finishFieldLabelEditAndSync(row) {
  finishFieldLabelEdit(row)
  syncJsonPreview({ type: 'field', fieldKey: row.name, prop: 'label' })
}

// Few-shot dialog
const showFewshot = ref(false)
const fsPairs = ref([])       // [{baseName, pdf:File, json:File, pdfName, jsonName, jsonContent}]
const fsUnpaired = ref([])    // [{name, type}]
const fsDragOver = ref(false)
const fsTemplateName = ref('')
const fsAiEnhance = ref(false)
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
    fd.append('ai_enhance', fsAiEnhance.value ? '1' : '0')
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
      validators: fsResult.value.validators || {},
      has_table: !!fsResult.value.has_table,
      table_headers: fsResult.value.table_headers || []
    })
    ElMessage.success(`已应用版式 "${data.template}"，添加 ${data.fields_count} 个字段`)
    showFewshot.value = false
    fsResult.value = null
    fsPairs.value = []
    fsUnpaired.value = []
    fsTemplateName.value = ''
    fsAiEnhance.value = false
  } catch (e) { ElMessage.error('应用失败: ' + (e.response?.data?.error || e.message)) }
}

function startFewshot() {
  fsPairs.value = []
  fsUnpaired.value = []
  fsTemplateName.value = ''
  fsAiEnhance.value = false
  fsResult.value = null
  showFewshot.value = true
}

async function recognizeAll() {
  const ready = fileList.value.filter(f=>f.status==='ready')
  if (!ready.length) return ElMessage.info('没有待识别的文件')
  phase.value='recognizing'
  const jids = ready.map(f=>f.job_id)
  ready.forEach(f=>{ f.status='processing'; f.progress=35 })
  startProgressTicker()
  try {
    const {data} = await api.recognizeBatch(jids)
    data.results.forEach(r => {
      const f = fileList.value.find(x=>x.job_id===r.job_id)
      if (f) Object.assign(f, {
        status: r.status, template: r.template || '?',
        fields_extracted: r.fields_extracted || 0, fields_total: r.fields_total || 0,
        progress: 100
      })
    })
    phase.value='idle'
    const done = data.results.filter(r=>r.status==='done').length
    const err = data.results.filter(r=>r.status==='error').length
    ElMessage.success(`完成 ${done} 份` + (err ? `，${err} 失败` : ''))
  } catch(e) {
    ready.forEach(f=>{ f.status='error'; f.progress=100 })
    ElMessage.error('批量识别失败'); phase.value='idle'
  }
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
/* legacy doCorrect disabled; the manual-field/table-aware implementation is below.
async function doCorrect() {
  const edits={}
  fieldRows.value.forEach(r=>{ if(r.display!==r._original) edits[r.name]=r.display })
  if(!Object.keys(edits).length) return ElMessage.info('没有修改')
  try { await api.correct(viewingJobId.value,edits); ElMessage.success('已保存')
    const {data}=await api.result(viewingJobId.value); showResult(data)
  } catch(e) { ElMessage.error('失败') }
}
*/
function makeUniqueFieldKey(label) {
  const base = String(label || 'field').trim() || 'field'
  const used = new Set(fieldRows.value.map(row => row.name))
  if (!used.has(base)) return base
  let index = 2
  while (used.has(`${base}__${index}`)) index += 1
  return `${base}__${index}`
}

function openAddFieldDialog() {
  newField.label = ''
  newField.value = ''
  showAddField.value = true
}

function addManualField() {
  const label = newField.label.trim()
  if (!label) return ElMessage.error('请填写字段名')
  const value = newField.value.trim()
  const key = makeUniqueFieldKey(label)
  fieldRows.value.push({
    name: key,
    label,
    _originalLabel: label,
    labelEditing: false,
    labelEditVal: label,
    canonicalKey: '',
    found: true,
    display: value,
    confidence: '100%',
    manual: true,
    status: 'manual_added',
    editing: false,
    _original: '',
    editVal: value
  })
  manualDirty.value = true
  syncJsonPreview()
  showAddField.value = false
}

function removeManualField(name) {
  fieldRows.value = fieldRows.value.filter(row => row.name !== name)
  manualDirty.value = true
  syncJsonPreview()
}

function tableRowsToArrays() {
  return (tableData.rows || []).map(row =>
    tableData.headers.map((_, index) => String(row[String(index)] ?? ''))
  )
}

function tableArraysToObjects(headers, rows) {
  return (rows || []).map(row => {
    const objectRow = {}
    ;(headers || []).forEach((_, index) => {
      objectRow[String(index)] = String(row?.[index] ?? '')
    })
    return objectRow
  })
}

function normalizeTableEditorRows() {
  tableEditor.rows = tableEditor.rows.map(row => {
    const next = [...row]
    while (next.length < tableEditor.headers.length) next.push('')
    return next.slice(0, tableEditor.headers.length)
  })
}

function openTableEditor() {
  tableEditor.headers = [...(tableData.headers || [])]
  tableEditor.rows = tableRowsToArrays()
  if (!tableEditor.headers.length) {
    tableEditor.headers = ['列A']
    tableEditor.rows = [['']]
  }
  normalizeTableEditorRows()
  showTableEditor.value = true
}

function addTableColumn() {
  tableEditor.headers.push(`列${tableEditor.headers.length + 1}`)
  tableEditor.rows.forEach(row => row.push(''))
  if (!tableEditor.rows.length) tableEditor.rows.push(tableEditor.headers.map(() => ''))
}

function removeTableColumn(index) {
  tableEditor.headers.splice(index, 1)
  tableEditor.rows.forEach(row => row.splice(index, 1))
}

function addTableRow() {
  if (!tableEditor.headers.length) tableEditor.headers.push('列A')
  tableEditor.rows.push(tableEditor.headers.map(() => ''))
}

function removeTableRow(index) {
  tableEditor.rows.splice(index, 1)
}

function saveTableEditor() {
  const headers = tableEditor.headers.map(h => String(h || '').trim()).filter(Boolean)
  if (!headers.length) {
    tableData.title = ''
    tableData.headers = []
    tableData.rows = []
    tableData.source = 'manual_patch'
    tableData.confidence = undefined
  } else {
    tableEditor.headers = headers
    normalizeTableEditorRows()
    tableData.headers = [...headers]
    tableData.rows = tableArraysToObjects(headers, tableEditor.rows)
    tableData.source = tableData.source || 'manual_patch'
  }
  const firstTable = {
    title: tableData.title,
    headers: [...tableData.headers],
    rows: [...tableData.rows],
    source: tableData.source,
    confidence: tableData.confidence,
  }
  if (tableList.value.length) tableList.value[0] = firstTable
  else if (firstTable.headers.length || firstTable.rows.length) tableList.value = [firstTable]
  tableDirty.value = true
  syncJsonPreview({ type: 'table' })
  showTableEditor.value = false
}

function suggestTemplateName() {
  const raw = viewingData.value?.filename || viewingJobId.value || 'new_template'
  const base = String(raw)
    .replace(/\.[^.]+$/, '')
    .replace(/[^\w\u4e00-\u9fa5]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return `${base || 'new_template'}_template`
}

async function openFeedbackDialog() {
  if (!configTemplates.value.length) await loadConfig()
  const currentTemplate = meta.template && meta.template !== 'unknown' ? meta.template : ''
  const canMergeCurrent = configTemplates.value.some(t => t.name === currentTemplate)
  feedback.mode = canMergeCurrent ? 'merge' : 'create'
  feedback.template_name = canMergeCurrent ? currentTemplate : suggestTemplateName()
  feedback.field_names = feedbackFieldOptions.value.map(row => row.name)
  feedback.include_table = !!tableData.headers.length
  feedback.ai_enhance = false
  showFeedback.value = true
}

async function submitFeedback() {
  if (!feedback.template_name) return ElMessage.error('请填写或选择目标版式')
  if (!feedback.field_names.length && !feedback.include_table) {
    return ElMessage.error('至少选择一个字段或表格')
  }
  feedback.loading = true
  try {
    await doCorrect({ silent: true })
    const { data } = await api.fewshotFromResult({
      job_id: viewingJobId.value,
      template_name: feedback.template_name,
      field_names: feedback.field_names,
      include_table: feedback.include_table,
      ai_enhance: feedback.ai_enhance,
      mode: feedback.mode
    })
    const warn = data.warnings?.length ? `，${data.warnings.length} 条提醒` : ''
    const ai = data.ai_enhanced ? '，AI 已增强' : ''
    const action = data.created ? '已创建并反哺到' : '已反哺到'
    ElMessage.success(`${action} ${data.template}${ai}${warn}`)
    showFeedback.value = false
    await loadConfig()
  } catch (e) {
    ElMessage.error('反哺失败: ' + (e.response?.data?.error || e.message))
  } finally {
    feedback.loading = false
  }
}

/* doCorrect implementation with corrupted localized strings disabled.
async function doCorrect(options = {}) {
  const edits={}
  const manualFields=[]
  fieldRows.value.forEach(r=>{
    if(r.manual || r.status === 'manual_added') {
      manualFields.push({ key: r.name, label: r.label, value: r.display })
    } else if(r.display!==r._original) {
      edits[r.name]=r.display
    }
  })
  const payload = { fields: edits, manual_fields: manualFields }
  if (tableDirty.value) {
    payload.table_patch = {
      mode: 'replace',
      headers: [...tableData.headers],
      rows: tableRowsToArrays()
    }
  }
  const hasChanges = Object.keys(edits).length || manualFields.length || manualDirty.value || tableDirty.value
  if(!hasChanges) {
    if (!options.silent) ElMessage.info('娌℃湁淇敼')
    return
  }
  try { await api.correct(viewingJobId.value,payload); if (!options.silent) ElMessage.success('宸蹭繚瀛?)
    const {data}=await api.result(viewingJobId.value); showResult(data)
  } catch(e) { if (!options.silent) ElMessage.error('澶辫触'); else throw e }
}

*/
async function doCorrect(options = {}) {
  const edits = {}
  const fieldLabels = {}
  const manualFields = []
  fieldRows.value.forEach(row => {
    if (row.manual || row.status === 'manual_added') {
      manualFields.push({ key: row.name, label: row.label, value: row.display })
    } else if (row.display !== row._original) {
      edits[row.name] = row.display
    }
    if (!row.manual && row.label !== row._originalLabel) {
      fieldLabels[row.name] = row.label
    }
  })

  const payload = { fields: edits, field_labels: fieldLabels, manual_fields: manualFields }
  if (tableDirty.value) {
    payload.table_patch = {
      mode: 'replace',
      headers: [...tableData.headers],
      rows: tableRowsToArrays()
    }
  }

  const hasChanges = Object.keys(edits).length || Object.keys(fieldLabels).length || manualFields.length || manualDirty.value || tableDirty.value
  if (!hasChanges) {
    if (!options.silent) ElMessage.info('\u6ca1\u6709\u4fee\u6539')
    return
  }

  try {
    await api.correct(viewingJobId.value, payload)
    if (!options.silent) ElMessage.success('\u5df2\u4fdd\u5b58')
    const { data } = await api.result(viewingJobId.value)
    showResult(data)
  } catch (e) {
    if (!options.silent) ElMessage.error('\u4fdd\u5b58\u5931\u8d25')
    else throw e
  }
}

function openExportDialog(fmt) {
  exportFormat.value = fmt
  showExportDialog.value = true
}

function confirmExport() {
  if (!exportOptions.field_values && !exportOptions.field_details && !exportOptions.table && !exportOptions.meta) {
    ElMessage.error('至少选择一项导出内容')
    return
  }
  const a = document.createElement('a')
  a.href = api.exportUrl(viewingJobId.value, exportFormat.value, exportOptions)
  a.click()
  showExportDialog.value = false
}
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
.pool-card{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #f1f5f9;font-size:13px;cursor:pointer;transition:.1s}
.pool-card:hover{background:#f8fafc}.pool-card:last-child{border-bottom:none}
.pool-card.active{background:#eff6ff;border-left:3px solid #3b82f6;padding-left:11px}
.pool-card.done .pc-name{color:#374151}
.pool-card.error{background:#fff7f7}
.pc-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;background:#e5e7eb}
.pc-dot.ok{background:#10b981}.pc-dot.busy{background:#f59e0b;animation:pulse .8s infinite}.pc-dot.err{background:#ef4444}
.pc-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px}
.pc-row{display:flex;align-items:center;gap:10px;min-width:0}
.pc-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}
.pc-size{font-size:11px;color:#94a3b8;flex-shrink:0;width:50px;text-align:right}
.pc-tpl{font-size:10px;background:#f1f5f9;color:#64748b;padding:1px 6px;border-radius:3px;flex-shrink:0}
.pc-state{font-size:11px;color:#64748b;flex-shrink:0;width:76px;text-align:right}
.pc-state.processing,.pc-state.uploading{color:#2563eb}
.pc-state.done{color:#059669}
.pc-state.error{color:#dc2626}
.pc-progress{height:4px;background:#edf2f7;border-radius:999px;overflow:hidden}
.pc-progress-fill{display:block;height:100%;width:0;border-radius:inherit;background:#60a5fa;transition:width .45s ease,background-color .2s ease}
.pc-progress-fill.uploading{background:#93c5fd}
.pc-progress-fill.processing{background:linear-gradient(90deg,#3b82f6,#06b6d4)}
.pc-progress-fill.done{background:#10b981}
.pc-progress-fill.error{background:#ef4444}

/* Result */
.result-stage{flex:1;display:flex;flex-direction:column;overflow:hidden}
.result-toolbar{display:flex;justify-content:space-between;align-items:center;padding:10px 20px;background:#fff;border-bottom:1px solid #e5e7eb;flex-shrink:0;gap:12px;box-shadow:0 1px 3px rgba(0,0,0,.03)}
.toolbar-left,.toolbar-right{display:flex;align-items:center;gap:10px}
.result-warning-bar{display:flex;flex-direction:column;gap:6px;padding:8px 18px;background:#fffbeb;border-bottom:1px solid #fde68a;flex-shrink:0}
.result-warning-bar :deep(.el-alert){padding:6px 10px}
.meta-item{font-size:12px;color:#64748b;padding:2px 8px;background:#f8fafc;border-radius:4px}
.source-badge{font-weight:700}
.source-badge.local_rules{color:#2563eb;background:#eff6ff}
.source-badge.vision_fallback{color:#7c2d12;background:#ffedd5}
.source-badge.local_rules_with_vision_patch{color:#166534;background:#dcfce7}

.dual-pane{flex:1;display:flex;overflow:hidden;gap:2px;background:#d1d5db}
.pane-original{flex:1;overflow:auto;background:#e5e7eb;display:flex;align-items:flex-start;justify-content:center;min-width:0}
.orig-img{max-width:100%;height:auto}
.pane-fields{flex:0 0 34%;min-width:360px;max-width:500px;overflow-y:auto;padding:14px;background:#fff;display:flex;flex-direction:column;gap:10px}
.section-title{font-size:13px;font-weight:700;color:#1e293b;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #f1f5f9;letter-spacing:.3px}
.field-cards{display:flex;flex-direction:column;gap:3px}
.field-card{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:8px;background:#fff;border:1px solid #f1f5f9;font-size:13px;transition:all .2s}
.field-card:hover{border-color:#e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.field-card.miss{opacity:.45;background:#fafafa}
.field-card.manual{border-color:#bbf7d0;background:linear-gradient(90deg,#f0fdf4,#fff)}
.fc-label{min-width:110px;font-weight:600;flex-shrink:0;font-size:11px;white-space:nowrap;color:#64748b;letter-spacing:.4px}
.fc-label:hover{color:#2563eb}
.fc-label-input{width:130px;flex-shrink:0}
.fc-value{flex:1;cursor:pointer;word-break:break-all;border-radius:4px;padding:3px 6px;transition:.15s;color:#1e293b;font-weight:500}
.fc-value:hover{background:#f0f9ff}
.fc-value.empty{color:#cbd5e1;font-style:italic;font-weight:400}
.fc-conf{font-size:10px;color:#94a3b8;flex-shrink:0;font-family:Consolas,monospace;background:#f8fafc;padding:1px 5px;border-radius:3px}
.cargo-box{margin-top:12px}
.section-title-row,.table-tools{display:flex;align-items:center;gap:8px}
.section-title-row span:first-child{flex:1}
.table-tools{justify-content:flex-end;margin:-4px 0 8px}
.cargo-table-block{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.cargo-table-block:first-of-type{margin-top:0}
.cargo-table-title{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px;font-weight:800;color:#334155}
.json-inspector{flex:0 0 420px;min-width:320px;max-width:460px;background:#0f172a;color:#cbd5e1;display:flex;overflow:hidden;transition:flex-basis .2s,min-width .2s}
.json-inspector.collapsed{flex-basis:42px;min-width:42px;max-width:42px;background:#111827}
.json-inspector-rail{width:42px;height:100%;border:0;background:#111827;color:#dbeafe;font-size:11px;font-weight:800;letter-spacing:.8px;writing-mode:vertical-rl;text-orientation:mixed;cursor:pointer}
.json-inspector-rail:hover{background:#1e293b;color:#fff}
.json-inspector-panel{display:flex;flex-direction:column;gap:8px;width:100%;min-width:0;padding:12px}
.json-inspector-head{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:28px;border-bottom:1px solid rgba(148,163,184,.22);padding-bottom:8px;font-size:12px;font-weight:800;color:#e2e8f0}
.json-inspector-head :deep(.el-button){color:#93c5fd}
.json-collapse{margin-top:0;min-height:0}
.json-inspector .json-collapse{flex:1;display:flex;flex-direction:column}
.json-inspector .json-collapse :deep(.el-collapse){border:0}
.json-inspector .json-collapse :deep(.el-collapse-item__wrap){background:transparent;border:0}
.json-inspector .json-collapse :deep(.el-collapse-item__content){padding-bottom:0}
.json-inspector .json-collapse :deep(.el-collapse-item__header){background:#172033;color:#bfdbfe;border:1px solid rgba(148,163,184,.18);border-radius:8px;height:34px;padding:0 10px;font-size:12px;font-weight:800}
.json-block{background:#1e293b;color:#a5b4c2;padding:14px;font-size:11px;font-family:Consolas,monospace;max-height:300px;overflow:auto;white-space:pre-wrap;border-radius:8px;margin:0;line-height:1.5}
.json-inspector .json-block{height:calc(100vh - 190px);max-height:none;border:1px solid rgba(148,163,184,.18)}
.json-line{display:block;min-height:16px;border-left:3px solid transparent;padding-left:6px;margin-left:-6px;transition:background .2s,border-color .2s,color .2s}
.json-line.active{background:rgba(250,204,21,.18);border-left-color:#facc15;color:#fef9c3}

.table-editor{display:flex;flex-direction:column;gap:12px}
.table-editor-head{display:flex;align-items:center;gap:8px}
.te-title{font-size:13px;font-weight:800;color:#1e293b;flex:1}
.table-empty-tip{padding:18px;border:1px dashed #cbd5e1;border-radius:10px;color:#64748b;background:#f8fafc;text-align:center}
.table-edit-grid{overflow:auto;border:1px solid #e5e7eb;border-radius:10px}
.table-edit-header,.table-edit-row{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(140px,1fr);align-items:stretch;min-width:max-content}
.table-edit-header{background:#f8fafc;border-bottom:1px solid #e5e7eb}
.table-edit-row{border-bottom:1px solid #f1f5f9}
.table-edit-row:last-child{border-bottom:none}
.table-edit-cell{padding:8px;border-right:1px solid #f1f5f9;display:flex;align-items:center;gap:6px}
.table-edit-head-cell{font-weight:700}
.table-row-actions{width:86px;padding:8px;display:flex;align-items:center;justify-content:center;background:#fafafa}
.feedback-field-list{max-height:260px;overflow:auto;display:flex;flex-direction:column;gap:6px;padding:8px;border:1px solid #e5e7eb;border-radius:10px;background:#fafafa}
.feedback-value{margin-left:8px;color:#94a3b8;font-size:12px}
.export-option{display:flex;margin:10px 0;padding:10px 12px;border:1px solid #e5e7eb;border-radius:10px;background:#fafafa}
.export-option span{margin-left:8px;color:#94a3b8;font-size:12px}

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
.fs-ai-hint{font-size:11px;color:#a16207;margin:8px 0 0;text-align:right}

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
  .json-inspector{flex-basis:360px;min-width:300px}
  .json-inspector.collapsed{flex-basis:38px;min-width:38px;max-width:38px}
  .json-inspector-rail{width:38px}
}
</style>
