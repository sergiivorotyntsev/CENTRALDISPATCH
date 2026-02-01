import { useState, useEffect } from 'react'
import api from '../api'

function TestLab() {
  const [auctionTypes, setAuctionTypes] = useState([])
  const [selectedAuctionType, setSelectedAuctionType] = useState('')
  const [testFile, setTestFile] = useState(null)
  const [processing, setProcessing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  // Recent test runs
  const [recentTests, setRecentTests] = useState([])
  const [loadingTests, setLoadingTests] = useState(true)

  useEffect(() => {
    loadAuctionTypes()
    loadRecentTests()
  }, [])

  async function loadAuctionTypes() {
    try {
      const data = await api.listAuctionTypes()
      setAuctionTypes(data.items || [])
      if (data.items?.length > 0) {
        setSelectedAuctionType(data.items[0].id.toString())
      }
    } catch (err) {
      console.error('Failed to load auction types:', err)
    }
  }

  async function loadRecentTests() {
    setLoadingTests(true)
    try {
      const data = await api.listExtractions({ source: 'test_lab', limit: 10 })
      setRecentTests(data.items || [])
    } catch (err) {
      console.error('Failed to load recent tests:', err)
    } finally {
      setLoadingTests(false)
    }
  }

  async function handleTestUpload() {
    if (!testFile || !selectedAuctionType) return

    setProcessing(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', testFile)
      formData.append('auction_type_id', selectedAuctionType)
      formData.append('dataset_split', 'test')
      formData.append('source', 'test_lab')
      formData.append('is_test', 'true')

      const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Upload failed')
      }

      const data = await response.json()

      setResult({
        document: data.document,
        run_id: data.run_id,
        run_status: data.run_status,
        needs_ocr: data.needs_ocr,
        text_length: data.text_length,
        detected_source: data.detected_source,
        classification_score: data.classification_score,
        raw_text_preview: data.raw_text_preview,
      })

      loadRecentTests()
    } catch (err) {
      setError(err.message)
    } finally {
      setProcessing(false)
    }
  }

  async function handleDryRunExport(runId) {
    try {
      const result = await api.cdDryRun(runId)
      alert(result.is_valid
        ? 'Dry run passed! Payload ready for export.'
        : 'Validation errors: ' + result.validation_errors.join(', ')
      )
    } catch (err) {
      alert('Dry run failed: ' + err.message)
    }
  }

  function clearResult() {
    setResult(null)
    setTestFile(null)
    setError(null)
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Test Lab</h1>
          <p className="text-gray-500 mt-1">
            Sandbox environment for testing PDF extraction without affecting production data
          </p>
        </div>
        <span className="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm font-medium">
          Sandbox Mode
        </span>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <strong>Error:</strong> {error}
          <button onClick={() => setError(null)} className="ml-4 text-sm underline">Dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Upload Section */}
        <div className="card">
          <div className="card-header">
            <h2 className="font-semibold">Test PDF Extraction</h2>
          </div>
          <div className="card-body space-y-4">
            <div>
              <label className="form-label">Auction Type</label>
              <select
                value={selectedAuctionType}
                onChange={(e) => setSelectedAuctionType(e.target.value)}
                className="form-select w-full"
              >
                {auctionTypes.map((at) => (
                  <option key={at.id} value={at.id}>{at.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="form-label">PDF Document</label>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
                {testFile ? (
                  <div>
                    <p className="font-medium text-gray-900">{testFile.name}</p>
                    <p className="text-sm text-gray-500">
                      {(testFile.size / 1024).toFixed(1)} KB
                    </p>
                    <button
                      onClick={() => setTestFile(null)}
                      className="mt-2 text-sm text-red-600 hover:text-red-800"
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <label className="cursor-pointer">
                    <input
                      type="file"
                      accept=".pdf"
                      onChange={(e) => setTestFile(e.target.files[0])}
                      className="hidden"
                    />
                    <div className="text-gray-500">
                      <svg className="w-12 h-12 mx-auto mb-2 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                      <p>Click to select PDF</p>
                      <p className="text-xs mt-1">or drag and drop</p>
                    </div>
                  </label>
                )}
              </div>
            </div>

            <button
              onClick={handleTestUpload}
              disabled={!testFile || processing}
              className="btn btn-primary w-full"
            >
              {processing ? 'Processing...' : 'Run Test Extraction'}
            </button>

            <div className="text-xs text-gray-500 bg-gray-50 p-3 rounded">
              <strong>Note:</strong> Test Lab documents are marked as test and cannot be exported to Central Dispatch.
            </div>
          </div>
        </div>

        {/* Result Section */}
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <h2 className="font-semibold">Extraction Result</h2>
            {result && (
              <button onClick={clearResult} className="text-sm text-gray-500 hover:text-gray-700">
                Clear
              </button>
            )}
          </div>
          <div className="card-body">
            {result ? (
              <div className="space-y-4">
                <div className="flex items-center space-x-2">
                  <StatusIndicator status={result.run_status} />
                  <span className="font-medium">
                    {result.run_status === 'needs_review' ? 'Extraction Complete' :
                     result.run_status === 'manual_required' ? 'Manual Review Required' :
                     result.run_status === 'failed' ? 'Extraction Failed' :
                     result.run_status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="text-gray-500">Document ID</p>
                    <p className="font-mono">{result.document?.id}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Run ID</p>
                    <p className="font-mono">{result.run_id || '-'}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Text Length</p>
                    <p>{result.text_length} chars</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Needs OCR</p>
                    <p>{result.needs_ocr ? 'Yes' : 'No'}</p>
                  </div>
                  {result.detected_source && (
                    <div>
                      <p className="text-gray-500">Detected Source</p>
                      <p>{result.detected_source}</p>
                    </div>
                  )}
                  {result.classification_score && (
                    <div>
                      <p className="text-gray-500">Classification Score</p>
                      <p>{result.classification_score}%</p>
                    </div>
                  )}
                </div>

                {result.raw_text_preview && (
                  <div>
                    <p className="text-gray-500 text-sm mb-1">Text Preview</p>
                    <pre className="text-xs bg-gray-50 p-3 rounded max-h-32 overflow-auto">
                      {result.raw_text_preview}
                    </pre>
                  </div>
                )}

                <div className="flex space-x-2 pt-2 border-t">
                  {result.run_id && result.run_status === 'needs_review' && (
                    <>
                      <a
                        href={'/review/' + result.run_id}
                        className="btn btn-sm btn-primary flex-1 text-center"
                      >
                        Review Fields
                      </a>
                      <button
                        onClick={() => handleDryRunExport(result.run_id)}
                        className="btn btn-sm btn-secondary flex-1"
                      >
                        Dry Run Export
                      </button>
                    </>
                  )}
                </div>

                <div className="text-xs text-yellow-700 bg-yellow-50 p-3 rounded border border-yellow-200">
                  This is a <strong>test document</strong>. Export to Central Dispatch is disabled.
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                <svg className="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <p>Upload a PDF to see extraction results</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent Tests */}
      <div className="card mt-6">
        <div className="card-header flex items-center justify-between">
          <h2 className="font-semibold">Recent Test Runs</h2>
          <button onClick={loadRecentTests} className="btn btn-sm btn-secondary">
            Refresh
          </button>
        </div>
        <div className="card-body p-0">
          {loadingTests ? (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
            </div>
          ) : recentTests.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              No test runs yet. Upload a PDF to get started.
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Document</th>
                  <th>Auction Type</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recentTests.map((run) => (
                  <tr key={run.id}>
                    <td className="font-mono text-xs">{run.id}</td>
                    <td className="text-sm truncate max-w-[150px]">
                      {run.document_filename || 'Doc #' + run.document_id}
                    </td>
                    <td>
                      <span className="badge badge-info">{run.auction_type_code}</span>
                    </td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="text-xs text-gray-500">
                      {run.created_at ? new Date(run.created_at).toLocaleString() : '-'}
                    </td>
                    <td>
                      <div className="flex space-x-2">
                        {run.status === 'needs_review' && (
                          <a href={'/review/' + run.id} className="text-sm text-blue-600 hover:text-blue-800">
                            Review
                          </a>
                        )}
                        <button
                          onClick={() => handleDryRunExport(run.id)}
                          className="text-sm text-gray-600 hover:text-gray-800"
                        >
                          Dry Run
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusIndicator({ status }) {
  const colors = {
    needs_review: 'bg-yellow-500',
    approved: 'bg-green-500',
    reviewed: 'bg-green-500',
    exported: 'bg-green-500',
    failed: 'bg-red-500',
    manual_required: 'bg-orange-500',
    pending: 'bg-gray-400',
    processing: 'bg-blue-500',
  }

  return (
    <span className={'w-3 h-3 rounded-full ' + (colors[status] || 'bg-gray-400')}></span>
  )
}

function StatusBadge({ status }) {
  const styles = {
    needs_review: 'badge-warning',
    approved: 'badge-success',
    reviewed: 'badge-success',
    exported: 'badge-success',
    failed: 'badge-error',
    manual_required: 'badge-info',
    pending: 'badge-gray',
    processing: 'badge-info',
  }

  const labels = {
    needs_review: 'Needs Review',
    manual_required: 'Manual Required',
  }

  return (
    <span className={'badge ' + (styles[status] || 'badge-gray')}>
      {labels[status] || status}
    </span>
  )
}

export default TestLab
