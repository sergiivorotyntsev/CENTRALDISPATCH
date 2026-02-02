import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

/**
 * Documents Page - Production Workflow
 *
 * Lists documents ready for Central Dispatch export.
 * Different from Test Lab which is for training.
 */
function Documents() {
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [auctionTypes, setAuctionTypes] = useState([])
  const [warehouses, setWarehouses] = useState([])

  // Track extraction runs per document
  const [docExtractions, setDocExtractions] = useState({})

  // Filters
  const [filter, setFilter] = useState({
    auction_type_id: '',
    status: '',
    export_status: '',
  })

  // Stats
  const [stats, setStats] = useState({
    total: 0,
    needs_review: 0,
    ready_to_export: 0,
    exported: 0,
  })

  // Upload state
  const [showUpload, setShowUpload] = useState(false)
  const [uploadFile, setUploadFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [selectedAuctionType, setSelectedAuctionType] = useState('auto')
  const [uploadResult, setUploadResult] = useState(null)

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { dataset_split: 'train' } // Only production docs, not test
      if (filter.auction_type_id) params.auction_type_id = filter.auction_type_id

      const result = await api.listDocuments(params)
      // Filter out test documents
      const prodDocs = (result.items || []).filter(d => !d.is_test)
      setDocuments(prodDocs)

      // Calculate stats
      setStats({
        total: prodDocs.length,
        needs_review: 0,
        ready_to_export: 0,
        exported: 0,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

  // Fetch auction types and warehouses
  useEffect(() => {
    async function fetchData() {
      try {
        const [atResult, whResult] = await Promise.all([
          api.listAuctionTypes(),
          api.listWarehouses(),
        ])
        setAuctionTypes(atResult.items || [])
        setWarehouses(whResult.items || [])
      } catch (err) {
        console.error('Failed to fetch data:', err)
      }
    }
    fetchData()
  }, [])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  // Fetch latest extraction status for each document
  const fetchDocExtractions = useCallback(async () => {
    try {
      const result = await api.listExtractions({ limit: 200 })
      const extractionsByDoc = {}
      let needsReview = 0
      let readyToExport = 0
      let exported = 0

      for (const run of (result.items || [])) {
        // Keep the latest extraction per document
        if (!extractionsByDoc[run.document_id] || run.id > extractionsByDoc[run.document_id].id) {
          extractionsByDoc[run.document_id] = run
        }

        // Count stats
        if (run.status === 'needs_review') needsReview++
        else if (run.status === 'reviewed' || run.status === 'approved') readyToExport++
        else if (run.status === 'exported') exported++
      }

      setDocExtractions(extractionsByDoc)
      setStats(prev => ({
        ...prev,
        needs_review: needsReview,
        ready_to_export: readyToExport,
        exported: exported,
      }))
    } catch (err) {
      console.error('Failed to fetch extractions:', err)
    }
  }, [])

  useEffect(() => {
    fetchDocExtractions()
  }, [fetchDocExtractions, documents])

  // Handle upload
  async function handleUpload() {
    if (!uploadFile) return

    setUploading(true)
    setUploadResult(null)
    try {
      const auctionTypeId = selectedAuctionType === 'auto' ? null : parseInt(selectedAuctionType)
      // Use 'train' split for production documents (not test)
      const result = await api.uploadDocument(uploadFile, auctionTypeId, 'train')

      setUploadResult({
        success: true,
        document: result.document,
        detectedSource: result.detected_source,
        classificationScore: result.classification_score,
        isDuplicate: result.is_duplicate,
        runStatus: result.run_status,
      })

      setUploadFile(null)
      fetchDocuments()
      fetchDocExtractions()
    } catch (err) {
      setError(`Upload failed: ${err.message}`)
      setUploadResult({ success: false, error: err.message })
    } finally {
      setUploading(false)
    }
  }

  // Extraction state
  const [extractingDocId, setExtractingDocId] = useState(null)

  // Run extraction on document
  async function handleRunExtraction(docId, forceNew = false) {
    const existingExtraction = docExtractions[docId]
    if (existingExtraction && !forceNew) {
      if (existingExtraction.status === 'needs_review') {
        navigate(`/listing/${existingExtraction.id}`)
        return
      } else if (['reviewed', 'approved'].includes(existingExtraction.status)) {
        if (!confirm('Document already processed. Run extraction again?')) return
      }
    }

    setExtractingDocId(docId)
    try {
      await api.runExtraction(docId)
      fetchDocuments()
      fetchDocExtractions()
    } catch (err) {
      setError(`Extraction failed: ${err.message}`)
    } finally {
      setExtractingDocId(null)
    }
  }

  // Update warehouse for document
  async function handleWarehouseChange(docId, warehouseId, e) {
    e.stopPropagation()
    const extraction = docExtractions[docId]
    if (!extraction) return

    try {
      // Update extraction with warehouse
      await api.updateExtraction(extraction.id, { warehouse_id: warehouseId })
      fetchDocExtractions()
    } catch (err) {
      console.error('Failed to update warehouse:', err)
    }
  }

  // Delete document
  async function handleDelete(docId, e) {
    e.stopPropagation()
    if (!confirm('Delete this document and all related data?')) return
    try {
      await api.deleteDocument(docId)
      fetchDocuments()
    } catch (err) {
      setError(`Delete failed: ${err.message}`)
    }
  }

  // Get source display
  function getSourceDisplay(doc) {
    if (doc.source === 'email') {
      return { label: 'Email', color: 'bg-blue-100 text-blue-800' }
    } else if (doc.source === 'webhook') {
      return { label: 'Webhook', color: 'bg-purple-100 text-purple-800' }
    } else if (doc.source === 'test_lab') {
      return { label: 'Test Lab', color: 'bg-yellow-100 text-yellow-800' }
    }
    return { label: 'Manual', color: 'bg-gray-100 text-gray-800' }
  }

  // Get export status
  function getExportStatus(extraction) {
    if (!extraction) return { label: 'No Data', color: 'bg-gray-100 text-gray-500' }

    if (extraction.status === 'exported') {
      return { label: 'Exported', color: 'bg-green-100 text-green-800' }
    } else if (extraction.status === 'reviewed' || extraction.status === 'approved') {
      return { label: 'Ready', color: 'bg-blue-100 text-blue-800' }
    } else if (extraction.status === 'needs_review') {
      return { label: 'Pending', color: 'bg-yellow-100 text-yellow-800' }
    } else if (extraction.status === 'failed') {
      return { label: 'Failed', color: 'bg-red-100 text-red-800' }
    }
    return { label: extraction.status, color: 'bg-gray-100 text-gray-600' }
  }

  // Navigate to listing review page
  function handleRowClick(doc) {
    const extraction = docExtractions[doc.id]
    if (extraction) {
      navigate(`/listing/${extraction.id}`)
    } else {
      navigate(`/documents/${doc.id}`)
    }
  }

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
          <p className="text-sm text-gray-500 mt-1">
            Production documents for Central Dispatch export
          </p>
        </div>
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

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white p-4 rounded-lg shadow">
          <p className="text-sm text-gray-500">Total</p>
          <p className="text-2xl font-bold text-gray-900">{stats.total}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <p className="text-sm text-gray-500">Needs Review</p>
          <p className="text-2xl font-bold text-yellow-600">{stats.needs_review}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <p className="text-sm text-gray-500">Ready to Export</p>
          <p className="text-2xl font-bold text-blue-600">{stats.ready_to_export}</p>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <p className="text-sm text-gray-500">Exported</p>
          <p className="text-2xl font-bold text-green-600">{stats.exported}</p>
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
            <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
            <select
              value={filter.status}
              onChange={(e) => setFilter({ ...filter, status: e.target.value })}
              className="form-select"
            >
              <option value="">All Status</option>
              <option value="needs_review">Needs Review</option>
              <option value="reviewed">Ready to Export</option>
              <option value="exported">Exported</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <div className="flex items-end">
            <button onClick={fetchDocuments} className="btn btn-secondary">
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
                <option value="auto">Auto-detect (Recommended)</option>
                {auctionTypes.map((at) => (
                  <option key={at.id} value={at.id}>{at.name}</option>
                ))}
              </select>
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
            </div>

            {uploadResult && (
              <div className={`mb-4 p-3 rounded-lg ${uploadResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                {uploadResult.success ? (
                  <div>
                    <p className="font-medium text-green-800">Upload successful!</p>
                    {uploadResult.detectedSource && (
                      <p className="text-sm text-green-700 mt-1">
                        Detected: <strong>{uploadResult.detectedSource}</strong>
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-red-800">{uploadResult.error}</p>
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
          <button onClick={() => setShowUpload(true)} className="btn btn-primary">
            Upload First Document
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Order ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Auction
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Pickup
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Warehouse
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Export
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Source
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Created
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {documents.map((doc) => {
                const extraction = docExtractions[doc.id]
                const outputs = extraction?.outputs_json ? (
                  typeof extraction.outputs_json === 'string'
                    ? JSON.parse(extraction.outputs_json)
                    : extraction.outputs_json
                ) : {}

                const orderId = outputs.lot_number || outputs.stock_number || outputs.order_id || '-'
                const pickupState = outputs.pickup_state || '-'
                const pickupZip = outputs.pickup_zip || ''
                const pickupLocation = pickupState !== '-' ? `${pickupState} ${pickupZip}`.trim() : '-'

                const sourceDisplay = getSourceDisplay(doc)
                const exportStatus = getExportStatus(extraction)
                const isExported = extraction?.status === 'exported'

                return (
                  <tr
                    key={doc.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => handleRowClick(doc)}
                  >
                    <td className="px-4 py-3">
                      <span className="font-mono text-sm font-medium text-gray-900">
                        {orderId}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs font-medium rounded ${
                        doc.auction_type_code === 'COPART' ? 'bg-blue-100 text-blue-800' :
                        doc.auction_type_code === 'IAA' ? 'bg-purple-100 text-purple-800' :
                        doc.auction_type_code === 'MANHEIM' ? 'bg-green-100 text-green-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {doc.auction_type_code || 'Unknown'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-gray-700">{pickupLocation}</span>
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <select
                        value={outputs.warehouse_id || ''}
                        onChange={(e) => handleWarehouseChange(doc.id, e.target.value, e)}
                        disabled={isExported || !extraction}
                        className={`form-select form-select-sm text-xs ${
                          isExported ? 'bg-gray-100 cursor-not-allowed' : ''
                        }`}
                      >
                        <option value="">Select...</option>
                        {warehouses.map((wh) => (
                          <option key={wh.id} value={wh.id}>
                            {wh.name} - {wh.city}, {wh.state}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      {extraction ? (
                        <span className={`px-2 py-1 text-xs font-medium rounded ${
                          extraction.status === 'needs_review' ? 'bg-yellow-100 text-yellow-800' :
                          extraction.status === 'reviewed' || extraction.status === 'approved' ? 'bg-green-100 text-green-800' :
                          extraction.status === 'exported' ? 'bg-blue-100 text-blue-800' :
                          extraction.status === 'failed' ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {extraction.status === 'needs_review' ? 'Needs Review' :
                           extraction.status === 'reviewed' || extraction.status === 'approved' ? 'Reviewed' :
                           extraction.status === 'exported' ? 'Exported' :
                           extraction.status}
                        </span>
                      ) : (
                        <span className="px-2 py-1 text-xs font-medium rounded bg-gray-100 text-gray-600">
                          Not Processed
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs font-medium rounded ${exportStatus.color}`}>
                        {exportStatus.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs font-medium rounded ${sourceDisplay.color}`}>
                        {sourceDisplay.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end items-center space-x-2">
                        {extraction ? (
                          <>
                            <button
                              onClick={() => navigate(`/listing/${extraction.id}`)}
                              className="text-sm text-blue-600 hover:text-blue-800"
                            >
                              {extraction.status === 'needs_review' ? 'Review' : 'View'}
                            </button>
                            {!isExported && (
                              <button
                                onClick={() => handleRunExtraction(doc.id, true)}
                                disabled={extractingDocId === doc.id}
                                className="text-sm text-orange-600 hover:text-orange-800"
                              >
                                {extractingDocId === doc.id ? '...' : 'Re-extract'}
                              </button>
                            )}
                          </>
                        ) : (
                          <button
                            onClick={() => handleRunExtraction(doc.id)}
                            disabled={extractingDocId === doc.id}
                            className="text-sm text-blue-600 hover:text-blue-800"
                          >
                            {extractingDocId === doc.id ? 'Processing...' : 'Extract'}
                          </button>
                        )}
                        <button
                          onClick={(e) => handleDelete(doc.id, e)}
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
