import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../api'

function Review() {
  const { runId } = useParams()
  const navigate = useNavigate()

  const [run, setRun] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  // Track changes
  const [corrections, setCorrections] = useState({})

  // Fetch run and review items
  const fetchData = useCallback(async () => {
    if (!runId) return

    setLoading(true)
    setError(null)
    try {
      const runData = await api.getExtraction(runId)
      setRun(runData.run)

      const itemsData = await api.getReviewItems(runId)
      setItems(itemsData.items || [])

      // Initialize corrections from existing data
      const initialCorrections = {}
      for (const item of (itemsData.items || [])) {
        initialCorrections[item.id] = {
          item_id: item.id,
          corrected_value: item.corrected_value || item.predicted_value || '',
          is_match_ok: item.is_match_ok || false,
          export_field: item.export_field !== false,
        }
      }
      setCorrections(initialCorrections)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Update correction
  function updateCorrection(itemId, field, value) {
    setCorrections((prev) => ({
      ...prev,
      [itemId]: {
        ...prev[itemId],
        [field]: value,
      },
    }))
  }

  // Mark as correct (copy predicted to corrected, mark ok)
  function markCorrect(itemId, predictedValue) {
    setCorrections((prev) => ({
      ...prev,
      [itemId]: {
        ...prev[itemId],
        corrected_value: predictedValue || '',
        is_match_ok: true,
      },
    }))
  }

  // Submit review
  async function handleSubmit() {
    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const itemsToSubmit = Object.values(corrections)
      await api.submitReview({
        run_id: parseInt(runId),
        items: itemsToSubmit,
      })
      setSuccess('Review submitted successfully!')
      setTimeout(() => {
        navigate('/runs')
      }, 1500)
    } catch (err) {
      setError(`Failed to submit review: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        <span className="ml-3 text-gray-600">Loading review...</span>
      </div>
    )
  }

  if (!run) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          Run not found. <button onClick={() => navigate('/runs')} className="underline">Go back</button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Review Extraction</h1>
          <p className="text-gray-500 mt-1">
            Run #{runId} - {run.document_filename}
          </p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={() => navigate('/runs')}
            className="btn btn-secondary"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="btn btn-primary"
            disabled={saving || items.length === 0}
          >
            {saving ? 'Submitting...' : 'Submit Review'}
          </button>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">
          {success}
        </div>
      )}

      {/* Run Info */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="grid grid-cols-4 gap-4">
          <div>
            <p className="text-sm text-gray-500">Status</p>
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              run.status === 'needs_review' ? 'bg-yellow-100 text-yellow-800' :
              run.status === 'approved' ? 'bg-green-100 text-green-800' :
              run.status === 'failed' ? 'bg-red-100 text-red-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {run.status}
            </span>
          </div>
          <div>
            <p className="text-sm text-gray-500">Auction Type</p>
            <p className="font-medium">{run.auction_type_code || 'Unknown'}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Extractor</p>
            <p className="font-medium">{run.extractor_kind || 'rule'}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Score</p>
            <p className="font-medium">{run.extraction_score ? `${(run.extraction_score * 100).toFixed(1)}%` : '-'}</p>
          </div>
        </div>
      </div>

      {/* Review Items */}
      {items.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No review items found for this run.
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="p-4 border-b border-gray-200">
            <h2 className="font-medium text-gray-900">Extracted Fields ({items.length})</h2>
            <p className="text-sm text-gray-500 mt-1">
              Review each field and correct any errors. Mark as correct or edit the value.
            </p>
          </div>

          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Field</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Predicted</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Corrected</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Correct?</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Export</th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {items.map((item) => (
                <tr key={item.id} className={corrections[item.id]?.is_match_ok ? 'bg-green-50' : ''}>
                  <td className="px-6 py-4">
                    <div>
                      <p className="font-medium text-gray-900">{item.source_key}</p>
                      {item.cd_key && (
                        <p className="text-xs text-gray-500">CD: {item.cd_key}</p>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="font-mono text-sm">{item.predicted_value || '-'}</span>
                    {item.confidence && (
                      <span className="ml-2 text-xs text-gray-400">
                        ({(item.confidence * 100).toFixed(0)}%)
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <input
                      type="text"
                      value={corrections[item.id]?.corrected_value || ''}
                      onChange={(e) => updateCorrection(item.id, 'corrected_value', e.target.value)}
                      className="form-input w-full text-sm"
                      placeholder="Enter corrected value"
                    />
                  </td>
                  <td className="px-6 py-4 text-center">
                    <input
                      type="checkbox"
                      checked={corrections[item.id]?.is_match_ok || false}
                      onChange={(e) => updateCorrection(item.id, 'is_match_ok', e.target.checked)}
                      className="h-4 w-4 text-primary-600 rounded"
                    />
                  </td>
                  <td className="px-6 py-4 text-center">
                    <input
                      type="checkbox"
                      checked={corrections[item.id]?.export_field !== false}
                      onChange={(e) => updateCorrection(item.id, 'export_field', e.target.checked)}
                      className="h-4 w-4 text-blue-600 rounded"
                    />
                  </td>
                  <td className="px-6 py-4 text-center">
                    <button
                      onClick={() => markCorrect(item.id, item.predicted_value)}
                      className="text-sm text-green-600 hover:text-green-800"
                    >
                      Mark OK
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Quick Actions */}
      <div className="mt-6 flex justify-between items-center">
        <div className="text-sm text-gray-500">
          {items.length} fields | {Object.values(corrections).filter(c => c.is_match_ok).length} marked correct
        </div>
        <div className="flex space-x-3">
          <button
            onClick={() => {
              const updated = {}
              items.forEach(item => {
                updated[item.id] = {
                  ...corrections[item.id],
                  is_match_ok: true,
                  corrected_value: item.predicted_value || '',
                }
              })
              setCorrections(updated)
            }}
            className="btn btn-secondary text-sm"
          >
            Mark All Correct
          </button>
          <button
            onClick={handleSubmit}
            className="btn btn-primary"
            disabled={saving || items.length === 0}
          >
            {saving ? 'Submitting...' : 'Submit Review'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default Review
