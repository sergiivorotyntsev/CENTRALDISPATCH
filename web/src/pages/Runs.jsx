import { useState, useEffect } from 'react'
import api from '../api'

function Runs() {
  const [runs, setRuns] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filters
  const [filters, setFilters] = useState({
    status: '',
    source_type: '',
    auction: '',
    limit: 50,
    offset: 0,
  })

  // Selected run for detail view
  const [selectedRun, setSelectedRun] = useState(null)
  const [runLogs, setRunLogs] = useState([])
  const [loadingLogs, setLoadingLogs] = useState(false)

  useEffect(() => {
    loadRuns()
    loadStats()
  }, [filters])

  async function loadRuns() {
    setLoading(true)
    try {
      const params = {}
      if (filters.status) params.status = filters.status
      if (filters.source_type) params.source_type = filters.source_type
      if (filters.auction) params.auction = filters.auction
      params.limit = filters.limit
      params.offset = filters.offset

      const data = await api.listRuns(params)
      setRuns(data.runs || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadStats() {
    try {
      const data = await api.getRunStats()
      setStats(data)
    } catch (err) {
      console.error('Failed to load stats:', err)
    }
  }

  async function selectRun(run) {
    setSelectedRun(run)
    setLoadingLogs(true)
    try {
      const logs = await api.getRunLogs(run.id)
      setRunLogs(logs)
    } catch (err) {
      console.error('Failed to load logs:', err)
      setRunLogs([])
    } finally {
      setLoadingLogs(false)
    }
  }

  async function handleDeleteRun(runId) {
    if (!confirm('Are you sure you want to delete this run?')) return

    try {
      await api.deleteRun(runId)
      setRuns(runs.filter(r => r.id !== runId))
      if (selectedRun?.id === runId) {
        setSelectedRun(null)
        setRunLogs([])
      }
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRetryRun(runId) {
    try {
      const result = await api.retryRun(runId)
      alert(`Retry created: ${result.new_run_id}`)
      loadRuns()
    } catch (err) {
      setError(err.message)
    }
  }

  function exportCsv() {
    const params = {}
    if (filters.status) params.status = filters.status
    if (filters.source_type) params.source_type = filters.source_type
    if (filters.auction) params.auction = filters.auction
    params.limit = 10000

    window.open(api.exportRunsCsv(params), '_blank')
  }

  function updateFilter(key, value) {
    setFilters({ ...filters, [key]: value, offset: 0 })
  }

  function nextPage() {
    setFilters({ ...filters, offset: filters.offset + filters.limit })
  }

  function prevPage() {
    setFilters({ ...filters, offset: Math.max(0, filters.offset - filters.limit) })
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Runs & Logs</h1>
        <button onClick={exportCsv} className="btn btn-secondary">
          <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Export CSV
        </button>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Filters */}
      <div className="card mb-6">
        <div className="card-body">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="form-label">Status</label>
              <select
                value={filters.status}
                onChange={e => updateFilter('status', e.target.value)}
                className="form-select"
              >
                <option value="">All</option>
                <option value="ok">OK</option>
                <option value="failed">Failed</option>
                <option value="error">Error</option>
                <option value="pending">Pending</option>
                <option value="processing">Processing</option>
              </select>
            </div>
            <div>
              <label className="form-label">Source</label>
              <select
                value={filters.source_type}
                onChange={e => updateFilter('source_type', e.target.value)}
                className="form-select"
              >
                <option value="">All</option>
                <option value="email">Email</option>
                <option value="upload">Upload</option>
                <option value="batch">Batch</option>
              </select>
            </div>
            <div>
              <label className="form-label">Auction</label>
              <select
                value={filters.auction}
                onChange={e => updateFilter('auction', e.target.value)}
                className="form-select"
              >
                <option value="">All</option>
                <option value="COPART">Copart</option>
                <option value="IAA">IAA</option>
                <option value="MANHEIM">Manheim</option>
              </select>
            </div>
            <div>
              <label className="form-label">Per Page</label>
              <select
                value={filters.limit}
                onChange={e => updateFilter('limit', parseInt(e.target.value))}
                className="form-select"
              >
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Runs List */}
        <div className="lg:col-span-2">
          <div className="card overflow-hidden">
            {loading ? (
              <div className="p-8 text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
              </div>
            ) : runs.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                No runs found matching your filters
              </div>
            ) : (
              <>
                <table className="table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Time</th>
                      <th>Source</th>
                      <th>Auction</th>
                      <th>Status</th>
                      <th>Score</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(run => (
                      <tr
                        key={run.id}
                        onClick={() => selectRun(run)}
                        className={`cursor-pointer ${selectedRun?.id === run.id ? 'bg-primary-50' : ''}`}
                      >
                        <td className="font-mono text-xs">{run.id}</td>
                        <td className="text-xs text-gray-500">
                          {new Date(run.created_at).toLocaleString()}
                        </td>
                        <td>
                          <span className="badge badge-gray">{run.source_type}</span>
                        </td>
                        <td>
                          {run.auction_detected ? (
                            <span className="badge badge-info">{run.auction_detected}</span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td>
                          <StatusBadge status={run.status} />
                        </td>
                        <td>
                          {run.extraction_score !== null ? (
                            <span className={`font-medium ${
                              run.extraction_score >= 60 ? 'text-green-600' :
                              run.extraction_score >= 30 ? 'text-yellow-600' : 'text-red-600'
                            }`}>
                              {run.extraction_score.toFixed(1)}%
                            </span>
                          ) : '-'}
                        </td>
                        <td>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDeleteRun(run.id); }}
                            className="text-red-600 hover:text-red-700"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Pagination */}
                <div className="px-4 py-3 border-t border-gray-200 flex items-center justify-between">
                  <div className="text-sm text-gray-500">
                    Showing {filters.offset + 1} - {filters.offset + runs.length}
                    {stats && ` of ${stats.total}`}
                  </div>
                  <div className="flex space-x-2">
                    <button
                      onClick={prevPage}
                      disabled={filters.offset === 0}
                      className="btn btn-sm btn-secondary disabled:opacity-50"
                    >
                      Previous
                    </button>
                    <button
                      onClick={nextPage}
                      disabled={runs.length < filters.limit}
                      className="btn btn-sm btn-secondary disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Run Details */}
        <div className="lg:col-span-1">
          {selectedRun ? (
            <div className="card">
              <div className="card-header flex items-center justify-between">
                <h3 className="font-medium">Run Details</h3>
                <button
                  onClick={() => { setSelectedRun(null); setRunLogs([]); }}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="card-body space-y-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-gray-500">Run ID</p>
                    <p className="font-mono">{selectedRun.id}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Status</p>
                    <StatusBadge status={selectedRun.status} />
                  </div>
                  <div>
                    <p className="text-gray-500">Source</p>
                    <p>{selectedRun.source_type}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Auction</p>
                    <p>{selectedRun.auction_detected || '-'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Score</p>
                    <p>{selectedRun.extraction_score?.toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Warehouse</p>
                    <p>{selectedRun.warehouse_id || '-'}</p>
                  </div>
                </div>

                {selectedRun.attachment_name && (
                  <div className="text-sm">
                    <p className="text-gray-500">File</p>
                    <p className="truncate">{selectedRun.attachment_name}</p>
                  </div>
                )}

                {selectedRun.clickup_task_url && (
                  <div className="text-sm">
                    <p className="text-gray-500">ClickUp Task</p>
                    <a href={selectedRun.clickup_task_url} target="_blank" className="text-primary-600 hover:underline truncate block">
                      {selectedRun.clickup_task_url}
                    </a>
                  </div>
                )}

                {selectedRun.error_message && (
                  <div className="text-sm">
                    <p className="text-red-600 font-medium">Error</p>
                    <p className="text-red-600">{selectedRun.error_message}</p>
                  </div>
                )}

                {(selectedRun.status === 'failed' || selectedRun.status === 'error') && (
                  <button
                    onClick={() => handleRetryRun(selectedRun.id)}
                    className="btn btn-sm btn-primary w-full"
                  >
                    Retry Run
                  </button>
                )}

                {/* Logs */}
                <div className="border-t border-gray-200 pt-4">
                  <h4 className="font-medium text-sm mb-2">Logs</h4>
                  {loadingLogs ? (
                    <div className="text-center py-4">
                      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600 mx-auto"></div>
                    </div>
                  ) : runLogs.length === 0 ? (
                    <p className="text-sm text-gray-500">No logs available</p>
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-auto">
                      {runLogs.map(log => (
                        <div key={log.id} className={`text-xs p-2 rounded ${
                          log.level === 'ERROR' ? 'bg-red-50 text-red-700' :
                          log.level === 'WARNING' ? 'bg-yellow-50 text-yellow-700' :
                          'bg-gray-50 text-gray-700'
                        }`}>
                          <div className="flex items-center justify-between">
                            <span className="font-medium">{log.level}</span>
                            <span className="text-gray-400">{new Date(log.timestamp).toLocaleTimeString()}</span>
                          </div>
                          <p className="mt-1">{log.message}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card-body text-center text-gray-500 py-12">
                <svg className="w-12 h-12 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                <p>Select a run to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const styles = {
    ok: 'badge-success',
    completed: 'badge-success',
    success: 'badge-success',
    failed: 'badge-error',
    error: 'badge-error',
    pending: 'badge-warning',
    processing: 'badge-info',
  }

  return (
    <span className={`badge ${styles[status] || 'badge-gray'}`}>
      {status}
    </span>
  )
}

export default Runs
