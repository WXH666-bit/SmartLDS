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
  correct(jobId, fields) {
    return API.post(`/correct/${jobId}`, { fields })
  },
  exportUrl(jobId, format) {
    return `${API_BASE}/export/${jobId}?format=${format}`
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
