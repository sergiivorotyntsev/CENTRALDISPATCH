import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

function Documents() {
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [auctionTypes, setAuctionTypes] = useState([])

  // Track extraction runs per document
  const [docExtractions, setDocExtractions] = useState({})

  // Filters
  const [filter, setFilter] = useState({
    auction_type_id: '',
    dataset_split: '',
  })

  // Stats
  const [stats, setStats] = useState({ train_count: 0, test_count: 0 })

  // Upload state
  const [showUpload, setShowUpload] = useState(false)
  const [uploadFile, setUploadFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [selectedAuctionType, setSelectedAuctionType] = useState('auto') // Default to auto-detect
  const [uploadResult, setUploadResult] = useState(null)

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = {}
      if (filter.auction_type_id) params.auction_type_id = filter.auction_type_id
      if (filter.dataset_split) params.dataset_split = filter.dataset_split

      const result = await api.listDocuments(params)
      setDocuments(result.items || [])
      setStats({
        train_count: result.train_count || 0,
        test_count: result.test_count || 0,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

  // Fetch auction types
  useEffect(() => {
    async function fetchAuctionTypes() {
      try {
        const result = await api.listAuctionTypes()
        setAuctionTypes(result.items || [])
        // Keep 'auto' as default, don't auto-select first type
      } catch (err) {
        console.error('Failed to fetch auction types:', err)
      }
    }
    fetchAuctionTypes()
  }, [])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  // Handle upload
  async function handleUpload() {
    if (!uploadFile) return

    setUploading(true)
    setUploadResult(null)
    try {
      // If auto-detect, pass null for auction_type_id
      const auctionTypeId = selectedAuctionType === 'auto' ? null : parseInt(selectedAuctionType)
      const result = await api.uploadDocument(uploadFile, auctionTypeId, 'train')

      // Show upload result with classification info
      setUploadResult({
        success: true,
        document: result.document,
        detectedSource: result.detected_source,
        classificationScore: result.classification_score,
        isDuplicate: result.is_duplicate,
        needsOcr: result.needs_ocr,
        runStatus: result.run_status,
      })

      setUploadFile(null)
      fetchDocuments()
    } catch (err) {
      setError(`Upload failed: ${err.message}`)
      setUploadResult({ success: false, error: err.message })
    } finally {
      setUploading(false)
    }
  }

  // Extraction state
  const [extractingDocId, setExtractingDocId] = useState(null)
  const [extractionResult, setExtractionResult] = useState(null)

  // Fetch latest extraction status for each document
  const fetchDocExtractions = useCallback(async () => {
    try {
      const result = await api.listExtractions({ limit: 100 })
      const extractionsByDoc = {}
      for (const run of (result.items || [])) {
        // Keep the latest extraction per document
        if (!extractionsByDoc[run.document_id] || run.id > extractionsByDoc[run.document_id].id) {
          extractionsByDoc[run.document_id] = run
        }
      }
      setDocExtractions(extractionsByDoc)
    } catch (err) {
      console.error('Failed to fetch extractions:', err)
    }
  }, [])

  useEffect(() => {
    fetchDocExtractions()
  }, [fetchDocExtractions, documents])

  // Navigate to extraction results / review
  function handleViewExtraction(docId) {
    const extraction = docExtractions[docId]
    if (extraction) {
      // Navigate to review page for this run
      navigate(`/review/${extraction.id}`)
    } else {
      // No extraction yet - show message
      setExtractionResult({
        success: false,
        docId,
        message: 'No extraction found. Click Extract to process this document.'
      })
    }
  }

  // Run extraction on document (with check for existing)
  async function handleRunExtraction(docId, forceNew = false) {
    // Check if extraction already exists
    const existingExtraction = docExtractions[docId]
    if (existingExtraction && !forceNew) {
      // Extraction exists - navigate to review instead
      if (existingExtraction.status === 'needs_review') {
        navigate(`/review/${existingExtraction.id}`)
        return
      } else if (existingExtraction.status === 'reviewed' || existingExtraction.status === 'approved') {
        // Already reviewed - ask if they want to re-extract
        if (!confirm('This document has already been processed. Run extraction again?')) {
          return
        }
      }
    }

    setExtractingDocId(docId)
    setExtractionResult(null)
    try {
      const result = await api.runExtraction(docId)
      setExtractionResult({
        success: true,
        docId,
        runId: result.id,
        status: result.status,
        message: result.status === 'needs_review'
          ? 'Extraction complete! Click to review results.'
          : result.status === 'failed'
          ? 'Extraction failed. Check the error details.'
          : 'Extraction started.'
      })
      fetchDocuments()
      fetchDocExtractions()
    } catch (err) {
      setExtractionResult({
        success: false,
        docId,
        message: `Extraction failed: ${err.message}`
      })
    } finally {
      setExtractingDocId(null)
    }
  }

  // Delete document
  async function handleDelete(docId) {
    if (!confirm('Are you sure you want to delete this document?')) return
    try {
      await api.deleteDocument(docId)
      fetchDocuments()
    } catch (err) {
      setError(`Delete failed: ${err.message}`)
    }
  }

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
        <button
          onClick={() => setShowUpload(true)}
          className="btn btn-primary"
        >
          Upload Document
        </button>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <strong>Error:</strong> {error}
          <button onClick={() => setError(null)} className="ml-4 text-sm underline">Dismiss</button>
        </div>
      )}

      {/* Extraction Result Notification */}
      {extractionResult && (
        <div className={`mb-6 p-4 rounded-lg ${
          extractionResult.success
            ? 'bg-green-50 border border-green-200 text-green-700'
            : 'bg-red-50 border border-red-200 text-red-700'
        }`}>
          <strong>{extractionResult.success ? 'Success:' : 'Error:'}</strong> {extractionResult.message}
          {extractionResult.success && extractionResult.runId && (
            <a
              href={`/runs?run=${extractionResult.runId}`}
              className="ml-4 text-sm underline"
            >
              View Results →
            </a>
          )}
          <button
            onClick={() => setExtractionResult(null)}
            className="ml-4 text-sm underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white p-4 rounded-lg shadow">
          <p className="text-sm text-gray-500">Total Documents</p>
          <p className="text-2xl font-bold text-gray-900">{documents.length}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <p className="text-sm text-gray-500">Training Set</p>
          <p className="text-2xl font-bold text-green-600">{stats.train_count}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <p className="text-sm text-gray-500">Test Set</p>
          <p className="text-2xl font-bold text-blue-600">{stats.test_count}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white p-4 rounded-lg shadow mb-6">
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Auction Type</label>
            <select
              value={filter.auction_type_id}
              onChange={(e) => setFilter({ ...filter, auction_type_id: e.target.value })}
              className="form-select"
            >
              <option value="">All Types</option>
              {auctionTypes.map((at) => (
                <option key={at.id} value={at.id}>{at.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Dataset</label>
            <select
              value={filter.dataset_split}
              onChange={(e) => setFilter({ ...filter, dataset_split: e.target.value })}
              className="form-select"
            >
              <option value="">All</option>
              <option value="train">Training</option>
              <option value="test">Test</option>
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={fetchDocuments}
              className="btn btn-secondary"
            >
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Upload Modal */}
      {showUpload && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-lg w-full mx-4">
            <h2 className="text-xl font-bold mb-4">Upload Document</h2>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">Auction Type</label>
              <select
                value={selectedAuctionType}
                onChange={(e) => setSelectedAuctionType(e.target.value)}
                className="form-select w-full"
              >
                <option value="auto">🔍 Auto-detect (Recommended)</option>
                {auctionTypes.map((at) => (
                  <option key={at.id} value={at.id}>{at.name}</option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                {selectedAuctionType === 'auto'
                  ? 'System will automatically detect the auction type from document content'
                  : 'Manual override - use when auto-detection fails'}
              </p>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">PDF File</label>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => {
                  setUploadFile(e.target.files[0])
                  setUploadResult(null)
                }}
                className="form-input w-full"
              />
              {uploadFile && (
                <p className="text-sm text-gray-500 mt-1">{uploadFile.name}</p>
              )}
            </div>

            {/* Upload Result */}
            {uploadResult && (
              <div className={`mb-4 p-3 rounded-lg ${uploadResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                {uploadResult.success ? (
                  <div>
                    <p className="font-medium text-green-800">
                      {uploadResult.isDuplicate ? '⚠️ Duplicate detected' : '✅ Upload successful!'}
                    </p>
                    {uploadResult.detectedSource && (
                      <p className="text-sm text-green-700 mt-1">
                        Detected: <strong>{uploadResult.detectedSource}</strong>
                        {uploadResult.classificationScore && ` (${uploadResult.classificationScore}% confidence)`}
                      </p>
                    )}
                    <p className="text-sm text-green-700">
                      Status: <span className={`px-2 py-0.5 rounded text-xs ${
                        uploadResult.runStatus === 'needs_review' ? 'bg-yellow-100 text-yellow-800' :
                        uploadResult.runStatus === 'failed' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>{uploadResult.runStatus || 'pending'}</span>
                    </p>
                  </div>
                ) : (
                  <p className="text-red-800">❌ {uploadResult.error}</p>
                )}
              </div>
            )}

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowUpload(false)
                  setUploadFile(null)
                  setUploadResult(null)
                }}
                className="btn btn-secondary"
                disabled={uploading}
              >
                {uploadResult?.success ? 'Close' : 'Cancel'}
              </button>
              {!uploadResult?.success && (
                <button
                  onClick={handleUpload}
                  className="btn btn-primary"
                  disabled={!uploadFile || uploading}
                >
                  {uploading ? 'Uploading...' : 'Upload'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Documents Table */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          <span className="ml-3 text-gray-600">Loading documents...</span>
        </div>
      ) : documents.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500 mb-4">No documents found</p>
          <button
            onClick={() => setShowUpload(true)}
            className="btn btn-primary"
          >
            Upload First Document
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Document
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Auction
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Order ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {documents.map((doc) => {
                const extraction = docExtractions[doc.id]
                // Get auction_source and order_id from extraction outputs
                const outputs = extraction?.outputs || {}
                const auctionSource = outputs.auction_source || doc.auction_type_code || 'Unknown'
                const orderId = outputs.order_id || '-'
                return (
                  <tr
                    key={doc.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => handleViewExtraction(doc.id)}
                  >
                    <td className="px-6 py-4">
                      <div>
                        <p className="font-medium text-gray-900">{doc.filename}</p>
                        <p className="text-sm text-gray-500 font-mono">ID: {doc.id}</p>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 text-xs font-medium rounded ${
                        auctionSource === 'COPART' ? 'bg-blue-100 text-blue-800' :
                        auctionSource === 'IAA' ? 'bg-purple-100 text-purple-800' :
                        auctionSource === 'MANHEIM' ? 'bg-green-100 text-green-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {auctionSource}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-mono text-sm text-gray-700">
                        {orderId}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      {extraction ? (
                        <div className="flex items-center space-x-2">
                          <span className={`px-2 py-1 text-xs font-medium rounded ${
                            extraction.status === 'needs_review' ? 'bg-yellow-100 text-yellow-800' :
                            extraction.status === 'reviewed' || extraction.status === 'approved' ? 'bg-green-100 text-green-800' :
                            extraction.status === 'failed' ? 'bg-red-100 text-red-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                            {extraction.status === 'needs_review' ? 'Needs Review' :
                             extraction.status === 'reviewed' ? 'Reviewed' :
                             extraction.status === 'approved' ? 'Approved' :
                             extraction.status === 'failed' ? 'Failed' :
                             extraction.status}
                          </span>
                          {extraction.extraction_score && (
                            <span className="text-xs text-gray-500">
                              {(extraction.extraction_score * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="px-2 py-1 text-xs font-medium rounded bg-gray-100 text-gray-600">
                          Not Processed
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end items-center space-x-2" onClick={(e) => e.stopPropagation()}>
                        {extractionResult?.docId === doc.id && (
                          <span className={`text-xs px-2 py-1 rounded ${
                            extractionResult.success ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                          }`}>
                            {extractionResult.success ? '✓' : '✗'}
                          </span>
                        )}
                        {extraction ? (
                          <>
                            <button
                              onClick={() => navigate(`/review/${extraction.id}`)}
                              className="text-sm text-blue-600 hover:text-blue-800"
                            >
                              {extraction.status === 'needs_review' ? 'Review' : 'View'}
                            </button>
                            <button
                              onClick={() => handleRunExtraction(doc.id, true)}
                              disabled={extractingDocId === doc.id}
                              className={`text-sm ${
                                extractingDocId === doc.id
                                  ? 'text-gray-400 cursor-not-allowed'
                                  : 'text-orange-600 hover:text-orange-800'
                              }`}
                            >
                              {extractingDocId === doc.id ? 'Extracting...' : 'Re-extract'}
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => handleRunExtraction(doc.id)}
                            disabled={extractingDocId === doc.id}
                            className={`text-sm ${
                              extractingDocId === doc.id
                                ? 'text-gray-400 cursor-not-allowed'
                                : 'text-blue-600 hover:text-blue-800'
                            }`}
                          >
                            {extractingDocId === doc.id ? 'Extracting...' : 'Extract'}
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="text-sm text-red-600 hover:text-red-800"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default Documents
