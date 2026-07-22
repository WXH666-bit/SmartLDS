import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'
const AI_OPERATION_TIMEOUT_MS = 600000
const MODEL_OPERATION_RETRY_OVERHEAD_MS = 30000

const API = axios.create({
  baseURL: API_BASE,
  timeout: 120000
})

function modelOperationTimeoutMs(timeoutSeconds, fallbackMs = AI_OPERATION_TIMEOUT_MS) {
  const seconds = Number(timeoutSeconds)
  if (!Number.isFinite(seconds) || seconds <= 0) return fallbackMs
  return Math.max(fallbackMs, Math.ceil(seconds) * 2 * 1000 + MODEL_OPERATION_RETRY_OVERHEAD_MS)
}

export default {
  // 单文件
  upload(file) {
    const fd = new FormData()
    fd.append('file', file)
    return API.post('/upload', fd)
  },
  recognize(jobId, timeoutSeconds) {
    return API.post(`/recognize/${jobId}`, null, { timeout: modelOperationTimeoutMs(timeoutSeconds) })
  },
  result(jobId) {
    return API.get(`/result/${jobId}`)
  },
  correct(jobId, payload) {
    if (payload && (payload.fields || payload.field_labels || payload.manual_fields || payload.excluded_fields || payload.table_patch)) {
      return API.post(`/correct/${jobId}`, payload)
    }
    return API.post(`/correct/${jobId}`, { fields: payload || {} })
  },
  exportUrl(jobId, format, options = {}) {
    const params = new URLSearchParams({ format })
    for (const [key, value] of Object.entries(options || {})) {
      params.set(key, value ? '1' : '0')
    }
    return `${API_BASE}/export/${jobId}?${params.toString()}`
  },
  imageUrl(jobId) {
    return `${API_BASE}/image/${jobId}`
  },

  // 批量
  uploadZip(file) {
    const fd = new FormData()
    fd.append('file', file)
    return API.post('/upload/zip', fd)
  },
  recognizeBatch(jobIds, timeoutSeconds) {
    return API.post('/recognize/batch', { job_ids: jobIds }, { timeout: modelOperationTimeoutMs(timeoutSeconds) })
  },

  getConfig() {
    return API.get('/config')
  },
  deleteTemplate(name) {
    return API.delete(`/config/${name}`)
  },
  applyConfig(data) {
    return API.post('/config/apply', data)
  },
  fewshotFromResult(data, timeoutSeconds) {
    return API.post('/fewshot/from-result', data, { timeout: modelOperationTimeoutMs(timeoutSeconds) })
  },
  getVisionSettings() {
    return API.get('/vision-settings')
  },
  saveVisionSettings(data) {
    return API.post('/vision-settings', data)
  },
  probeVisionModels(data) {
    return API.post('/vision-settings/probe', data, { timeout: 60000 })
  },
  revealVisionApiKey(params = {}) {
    return API.get('/vision-settings/api-key', { params })
  },
  clearVisionSettings() {
    return API.delete('/vision-settings')
  },
  fewshotLearn(formData, timeoutSeconds) {
    return API.post('/fewshot/learn', formData, { timeout: modelOperationTimeoutMs(timeoutSeconds) })
  },
  getHistory() {
    return API.get('/history')
  },
  deleteHistory(jobId) {
    return API.delete(`/history/${jobId}`)
  },
  deleteAllHistory() {
    return API.delete('/history')
  },
  health() {
    return API.get('/health')
  }
}
