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

  // Tabs
  const [activeTab, setActiveTab] = useState('extraction')

  // Training stats
  const [trainingStats, setTrainingStats] = useState(null)

  // Auction type form
  const [showAuctionTypeForm, setShowAuctionTypeForm] = useState(false)
  const [auctionTypeForm, setAuctionTypeForm] = useState({
    name: '',
    code: '',
    description: '',
    parent_id: null,
  })

  useEffect(() => {
    loadAuctionTypes()
    loadRecentTests()
    loadTrainingStats()
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
      const data = await api.listExtractions({ limit: 20 })
      setRecentTests(data.items || [])
    } catch (err) {
      console.error('Failed to load recent tests:', err)
    } finally {
      setLoadingTests(false)
    }
  }

  async function loadTrainingStats() {
    try {
      const response = await fetch('/api/models/training-stats')
      if (response.ok) {
        const data = await response.json()
        setTrainingStats(data)
      }
    } catch (err) {
      console.error('Failed to load training stats:', err)
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
        : 'Validation errors: ' + (result.validation_errors?.join(', ') || 'Unknown error')
      )
    } catch (err) {
      alert('Dry run failed: ' + err.message)
    }
  }

  async function handleCreateAuctionType(e) {
    e.preventDefault()
    try {
      const response = await fetch('/api/auction-types/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: auctionTypeForm.name,
          code: auctionTypeForm.code.toUpperCase(),
          description: auctionTypeForm.description,
          parent_id: auctionTypeForm.parent_id || null,
          is_custom: true,
        }),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to create auction type')
      }

      setShowAuctionTypeForm(false)
      setAuctionTypeForm({ name: '', code: '', description: '', parent_id: null })
      loadAuctionTypes()
    } catch (err) {
      alert('Error: ' + err.message)
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

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('extraction')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'extraction'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Test Extraction
          </button>
          <button
            onClick={() => setActiveTab('auction-types')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'auction-types'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Auction Types
          </button>
          <button
            onClick={() => setActiveTab('training')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'training'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Training Data
          </button>
        </nav>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <strong>Error:</strong> {error}
          <button onClick={() => setError(null)} className="ml-4 text-sm underline">Dismiss</button>
        </div>
      )}

      {/* Test Extraction Tab */}
      {activeTab === 'extraction' && (
        <>
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
                         result.run_status === 'failed' ? 'Extraction Failed - Manual Entry Required' :
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
                        <p className="text-gray-500">Detected Source</p>
                        <p className="font-medium">{result.detected_source || 'Unknown'}</p>
                      </div>
                    </div>

                    {result.raw_text_preview && (
                      <div>
                        <p className="text-gray-500 text-sm mb-1">Text Preview</p>
                        <pre className="text-xs bg-gray-50 p-3 rounded max-h-32 overflow-auto whitespace-pre-wrap">
                          {result.raw_text_preview}
                        </pre>
                      </div>
                    )}

                    <div className="flex space-x-2 pt-2 border-t">
                      {result.run_id && (
                        <a
                          href={'/review/' + result.run_id}
                          className="btn btn-sm btn-primary flex-1 text-center"
                        >
                          {result.run_status === 'failed' ? 'Enter Data Manually' : 'Review Fields'}
                        </a>
                      )}
                      {result.run_id && result.run_status !== 'failed' && (
                        <button
                          onClick={() => handleDryRunExport(result.run_id)}
                          className="btn btn-sm btn-secondary flex-1"
                        >
                          Dry Run Export
                        </button>
                      )}
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
                            <a href={'/review/' + run.id} className="text-sm text-blue-600 hover:text-blue-800">
                              {run.status === 'failed' ? 'Enter Data' : 'Review'}
                            </a>
                            {run.status !== 'failed' && (
                              <button
                                onClick={() => handleDryRunExport(run.id)}
                                className="text-sm text-gray-600 hover:text-gray-800"
                              >
                                Dry Run
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {/* Auction Types Tab */}
      {activeTab === 'auction-types' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <div className="card">
              <div className="card-header flex items-center justify-between">
                <h2 className="font-semibold">Auction Types</h2>
                <button
                  onClick={() => setShowAuctionTypeForm(true)}
                  className="btn btn-sm btn-primary"
                >
                  + Add Custom Type
                </button>
              </div>
              <div className="card-body p-0">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Code</th>
                      <th>Type</th>
                      <th>Description</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auctionTypes.map((at) => (
                      <tr key={at.id}>
                        <td className="font-medium">{at.name}</td>
                        <td>
                          <span className={`badge ${
                            at.code === 'COPART' ? 'bg-blue-100 text-blue-800' :
                            at.code === 'IAA' ? 'bg-purple-100 text-purple-800' :
                            at.code === 'MANHEIM' ? 'bg-green-100 text-green-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>{at.code}</span>
                        </td>
                        <td>
                          {at.is_base ? (
                            <span className="text-xs text-gray-500">Base</span>
                          ) : (
                            <span className="text-xs text-primary-600">Custom</span>
                          )}
                        </td>
                        <td className="text-sm text-gray-500 truncate max-w-[200px]">
                          {at.description || '-'}
                        </td>
                        <td>
                          {at.is_active ? (
                            <span className="badge badge-success">Active</span>
                          ) : (
                            <span className="badge badge-gray">Inactive</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Create Auction Type Form */}
          <div className="lg:col-span-1">
            {showAuctionTypeForm ? (
              <div className="card">
                <div className="card-header">
                  <h2 className="font-semibold">Create Custom Auction Type</h2>
                </div>
                <form onSubmit={handleCreateAuctionType} className="card-body space-y-4">
                  <div>
                    <label className="form-label">Name</label>
                    <input
                      type="text"
                      value={auctionTypeForm.name}
                      onChange={(e) => setAuctionTypeForm(f => ({ ...f, name: e.target.value }))}
                      className="form-input w-full"
                      placeholder="e.g., Custom Auction"
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Code</label>
                    <input
                      type="text"
                      value={auctionTypeForm.code}
                      onChange={(e) => setAuctionTypeForm(f => ({ ...f, code: e.target.value.toUpperCase() }))}
                      className="form-input w-full font-mono"
                      placeholder="e.g., CUSTOM"
                      maxLength={20}
                      required
                    />
                    <p className="text-xs text-gray-500 mt-1">Unique identifier (uppercase letters)</p>
                  </div>
                  <div>
                    <label className="form-label">Base Type (optional)</label>
                    <select
                      value={auctionTypeForm.parent_id || ''}
                      onChange={(e) => setAuctionTypeForm(f => ({ ...f, parent_id: e.target.value || null }))}
                      className="form-select w-full"
                    >
                      <option value="">None (standalone)</option>
                      {auctionTypes.filter(at => at.is_base).map((at) => (
                        <option key={at.id} value={at.id}>Inherit from {at.name}</option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-500 mt-1">Inherit extraction patterns from base type</p>
                  </div>
                  <div>
                    <label className="form-label">Description</label>
                    <textarea
                      value={auctionTypeForm.description}
                      onChange={(e) => setAuctionTypeForm(f => ({ ...f, description: e.target.value }))}
                      className="form-input w-full"
                      rows={2}
                      placeholder="Optional description..."
                    />
                  </div>
                  <div className="flex space-x-2">
                    <button type="submit" className="btn btn-primary flex-1">
                      Create
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowAuctionTypeForm(false)}
                      className="btn btn-secondary"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              <div className="card">
                <div className="card-body text-center py-8">
                  <svg className="w-12 h-12 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  <p className="text-gray-500 mb-4">Create custom auction types to handle different document formats</p>
                  <button
                    onClick={() => setShowAuctionTypeForm(true)}
                    className="btn btn-primary"
                  >
                    Create Custom Type
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Training Data Tab */}
      {activeTab === 'training' && (
        <div className="space-y-6">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="font-semibold text-blue-800 mb-2">How Training Works</h3>
            <p className="text-sm text-blue-700">
              When you review and correct extracted fields, those corrections are saved as training examples.
              The more corrections you provide, the better the system learns to extract similar documents.
              Each auction type builds its own training dataset.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {auctionTypes.map((at) => {
              const stats = trainingStats?.by_auction_type?.[at.code] || { total: 0, validated: 0 }
              return (
                <div key={at.id} className="card">
                  <div className="card-header">
                    <h3 className="font-semibold">{at.name}</h3>
                  </div>
                  <div className="card-body">
                    <div className="space-y-3">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-500">Training Examples</span>
                        <span className="font-mono text-lg">{stats.total}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-500">Validated</span>
                        <span className="font-mono text-lg text-green-600">{stats.validated}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-green-500 h-2 rounded-full"
                          style={{ width: `${stats.total > 0 ? (stats.validated / stats.total) * 100 : 0}%` }}
                        ></div>
                      </div>
                      <p className="text-xs text-gray-500">
                        {stats.total >= 50 ? (
                          <span className="text-green-600">Ready for training</span>
                        ) : (
                          <span>Need {50 - stats.total} more examples for training</span>
                        )}
                      </p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="card">
            <div className="card-header">
              <h2 className="font-semibold">Training Process</h2>
            </div>
            <div className="card-body">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <div className="w-12 h-12 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center mx-auto mb-2">
                    1
                  </div>
                  <p className="font-medium">Upload Documents</p>
                  <p className="text-xs text-gray-500 mt-1">Upload PDF documents for extraction</p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <div className="w-12 h-12 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center mx-auto mb-2">
                    2
                  </div>
                  <p className="font-medium">Review & Correct</p>
                  <p className="text-xs text-gray-500 mt-1">Fix any extraction errors</p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <div className="w-12 h-12 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center mx-auto mb-2">
                    3
                  </div>
                  <p className="font-medium">Build Training Data</p>
                  <p className="text-xs text-gray-500 mt-1">Corrections become training examples</p>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-lg">
                  <div className="w-12 h-12 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center mx-auto mb-2">
                    4
                  </div>
                  <p className="font-medium">Improve Accuracy</p>
                  <p className="text-xs text-gray-500 mt-1">System learns from your corrections</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
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
