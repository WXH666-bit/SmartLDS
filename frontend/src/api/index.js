import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

const API = axios.create({
  baseURL: API_BASE,
  timeout: 120000
})

export default {
  // 单文件
  upload(file) {
    const fd = new FormData()
    fd.append('file', file)
    return API.post('/upload', fd)
  },
  recognize(jobId) {
    return API.post(`/recognize/${jobId}`)
  },
  result(jobId) {
    return API.get(`/result/${jobId}`)
  },
  correct(jobId, payload) {
    if (payload && (payload.fields || payload.field_labels || payload.manual_fields || payload.table_patch)) {
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
  recognizeBatch(jobIds) {
    return API.post('/recognize/batch', { job_ids: jobIds }, { timeout: 300000 })
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
  fewshotFromResult(data) {
    return API.post('/fewshot/from-result', data)
  },
  getVisionSettings() {
    return API.get('/vision-settings')
  },
  saveVisionSettings(data) {
    return API.post('/vision-settings', data)
  },
  clearVisionSettings() {
    return API.delete('/vision-settings')
  },
  fewshotLearn(formData) {
    return API.post('/fewshot/learn', formData, { timeout: 300000 })
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
