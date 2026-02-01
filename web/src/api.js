// API client for the FastAPI backend

const API_BASE = '/api'

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`

  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  }

  // Don't set Content-Type for FormData
  if (options.body instanceof FormData) {
    delete config.headers['Content-Type']
  }

  const response = await fetch(url, config)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  // Handle empty responses
  const text = await response.text()
  return text ? JSON.parse(text) : null
}

// Health & Status
export const api = {
  // Health
  getHealth: () => request('/health'),
  getReady: () => request('/ready'),

  // Settings
  getSettingsStatus: () => request('/settings/status'),
  getExportTargets: () => request('/settings/export-targets'),
  updateExportTargets: (targets) => request('/settings/export-targets', {
    method: 'PUT',
    body: JSON.stringify({ targets }),
  }),
  getSheetsConfig: () => request('/settings/sheets'),
  updateSheetsConfig: (config) => request('/settings/sheets', {
    method: 'PUT',
    body: JSON.stringify(config),
  }),
  testSheets: () => request('/settings/test-sheets', { method: 'POST' }),
  getClickUpConfig: () => request('/settings/clickup'),
  updateClickUpConfig: (config) => request('/settings/clickup', {
    method: 'PUT',
    body: JSON.stringify(config),
  }),
  getCDConfig: () => request('/settings/cd'),
  updateCDConfig: (config) => request('/settings/cd', {
    method: 'PUT',
    body: JSON.stringify(config),
  }),
  getEmailConfig: () => request('/settings/email'),
  updateEmailConfig: (config) => request('/settings/email', {
    method: 'PUT',
    body: JSON.stringify(config),
  }),
  getWarehouses: () => request('/settings/warehouses'),
  updateWarehouses: (warehouses) => request('/settings/warehouses', {
    method: 'PUT',
    body: JSON.stringify({ warehouses }),
  }),

  // Test/Sandbox
  uploadPdf: async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request('/test/upload', {
      method: 'POST',
      body: formData,
    })
  },
  classifyPdf: async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request('/test/classify', {
      method: 'POST',
      body: formData,
    })
  },
  previewCD: (data) => request('/test/preview-cd', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  previewSheetsRow: (data) => request('/test/preview-sheets-row', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  dryRun: async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request('/test/dry-run', {
      method: 'POST',
      body: formData,
    })
  },

  // Runs
  listRuns: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/runs/${query ? `?${query}` : ''}`)
  },
  getRun: (runId) => request(`/runs/${runId}`),
  getRunLogs: (runId) => request(`/runs/${runId}/logs`),
  getRunStats: () => request('/runs/stats'),
  deleteRun: (runId) => request(`/runs/${runId}`, { method: 'DELETE' }),
  retryRun: (runId) => request(`/runs/retry/${runId}`, { method: 'POST' }),
  exportRunsCsv: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return `${API_BASE}/runs/export/csv${query ? `?${query}` : ''}`
  },
  searchLogs: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/runs/logs/search${query ? `?${query}` : ''}`)
  },

  // Documents
  listDocuments: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/documents/${query ? `?${query}` : ''}`)
  },
  getDocument: (id) => request(`/documents/${id}`),
  getDocumentText: (id) => request(`/documents/${id}/text`),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  uploadDocument: async (file, auctionTypeId, datasetSplit = 'train') => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('auction_type_id', auctionTypeId)
    formData.append('dataset_split', datasetSplit)
    return request('/documents/upload', {
      method: 'POST',
      body: formData,
    })
  },
  getDocumentStats: () => request('/documents/stats/by-auction-type'),

  // Extractions
  listExtractions: (params = {}) => {
    const query = new URLSearchParams(params).toString()
    return request(`/extractions/${query ? `?${query}` : ''}`)
  },
  getExtraction: (id) => request(`/extractions/${id}`),
  getExtractionStats: () => request('/extractions/stats'),
  runExtraction: (documentId, forceMl = false) => request('/extractions/run', {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId, force_ml: forceMl }),
  }),
  listNeedsReview: (limit = 50) => request(`/extractions/needs-review?limit=${limit}`),

  // Reviews
  getReviewItems: (runId) => request(`/reviews/${runId}/items`),
  submitReview: (data) => request('/reviews/submit', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  // Auction Types
  listAuctionTypes: () => request('/auction-types/'),
  getAuctionType: (id) => request(`/auction-types/${id}`),
}

export default api
