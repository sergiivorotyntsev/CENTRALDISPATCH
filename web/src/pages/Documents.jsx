import { useState, useEffect, useCallback } from 'react'
import api from '../api'

function Documents() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [auctionTypes, setAuctionTypes] = useState([])

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
  const [selectedAuctionType, setSelectedAuctionType] = useState('')

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
        if (result.items?.length > 0) {
          setSelectedAuctionType(result.items[0].id.toString())
        }
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
    if (!uploadFile || !selectedAuctionType) return

    setUploading(true)
    try {
      await api.uploadDocument(uploadFile, parseInt(selectedAuctionType), 'train')
      setUploadFile(null)
      setShowUpload(false)
      fetchDocuments()
    } catch (err) {
      setError(`Upload failed: ${err.message}`)
    } finally {
      setUploading(false)
    }
  }

  // Run extraction on document
  async function handleRunExtraction(docId) {
    try {
      await api.runExtraction(docId)
      fetchDocuments() // Refresh to show updated status
    } catch (err) {
      setError(`Extraction failed: ${err.message}`)
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
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-bold mb-4">Upload Document</h2>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">Auction Type</label>
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

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">PDF File</label>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => setUploadFile(e.target.files[0])}
                className="form-input w-full"
              />
              {uploadFile && (
                <p className="text-sm text-gray-500 mt-1">{uploadFile.name}</p>
              )}
            </div>

            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowUpload(false)
                  setUploadFile(null)
                }}
                className="btn btn-secondary"
                disabled={uploading}
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                className="btn btn-primary"
                disabled={!uploadFile || !selectedAuctionType || uploading}
              >
                {uploading ? 'Uploading...' : 'Upload'}
              </button>
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
                  Auction Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Dataset
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Size
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
              {documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div>
                      <p className="font-medium text-gray-900">{doc.filename}</p>
                      <p className="text-sm text-gray-500 font-mono">ID: {doc.id}</p>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">
                      {doc.auction_type_code || 'Unknown'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs font-medium rounded ${
                      doc.dataset_split === 'train'
                        ? 'bg-green-100 text-green-800'
                        : 'bg-purple-100 text-purple-800'
                    }`}>
                      {doc.dataset_split}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {doc.file_size ? `${(doc.file_size / 1024).toFixed(1)} KB` : '-'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '-'}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex justify-end space-x-2">
                      <button
                        onClick={() => handleRunExtraction(doc.id)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        Extract
                      </button>
                      <button
                        onClick={() => handleDelete(doc.id)}
                        className="text-sm text-red-600 hover:text-red-800"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default Documents
