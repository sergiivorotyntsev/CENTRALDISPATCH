import { useState, useCallback } from 'react'
import api from '../api'

function TestLab() {
  const [file, setFile] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState('')
  const [error, setError] = useState(null)
  const [requestId, setRequestId] = useState(null)

  // Results
  const [classification, setClassification] = useState(null)
  const [extraction, setExtraction] = useState(null)
  const [cdPreview, setCdPreview] = useState(null)
  const [sheetsPreview, setSheetsPreview] = useState(null)
  const [dryRunResult, setDryRunResult] = useState(null)

  // Run tracking
  const [documentId, setDocumentId] = useState(null)
  const [runId, setRunId] = useState(null)
  const [runStatus, setRunStatus] = useState(null)

  const handleDrag = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0])
    }
  }, [])

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0])
    }
  }

  async function handleFile(selectedFile) {
    if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setError('Please upload a PDF file')
      return
    }

    setFile(selectedFile)
    setError(null)
    setClassification(null)
    setExtraction(null)
    setCdPreview(null)
    setSheetsPreview(null)
    setDryRunResult(null)

    // Auto-classify
    await handleClassify(selectedFile)
  }

  async function handleClassify(fileToClassify = file) {
    if (!fileToClassify) return

    setLoading(true)
    setLoadingStep('Classifying document...')
    setRequestId(Date.now().toString(36))
    try {
      const result = await api.classifyPdf(fileToClassify)
      setClassification(result)

      // If classification successful (not unknown and has sufficient text), auto-extract
      if (result.source && result.source !== 'UNKNOWN' && !result.needs_ocr) {
        await handleExtract(fileToClassify)
      } else if (result.needs_ocr) {
        setError(`Document needs OCR: Only ${result.text_length} characters extracted. This appears to be a scanned PDF.`)
      } else if (result.source === 'UNKNOWN') {
        setError('Could not detect auction source. Confidence too low or text insufficient.')
      }
    } catch (err) {
      setError(`Classification failed: ${err.message}`)
    } finally {
      setLoading(false)
      setLoadingStep('')
    }
  }

  async function handleExtract(fileToExtract = file) {
    if (!fileToExtract) return

    setLoading(true)
    setLoadingStep('Extracting data...')
    try {
      const result = await api.uploadPdf(fileToExtract)
      setExtraction(result)

      // Capture run info if available
      if (result.document_id) setDocumentId(result.document_id)
      if (result.run_id) setRunId(result.run_id)
      if (result.run_status) setRunStatus(result.run_status)

      // Check for warnings in extraction
      if (result.extraction?.warnings?.length > 0) {
        const warningMsg = result.extraction.warnings.join('; ')
        if (result.extraction.warnings.some(w => w.includes('failed'))) {
          setError(`Extraction warning: ${warningMsg}`)
        }
      }
    } catch (err) {
      setError(`Extraction failed: ${err.message}`)
    } finally {
      setLoading(false)
      setLoadingStep('')
    }
  }

  async function handlePreviewCD() {
    if (!extraction) return

    setLoading(true)
    try {
      const result = await api.previewCD(extraction)
      setCdPreview(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handlePreviewSheets() {
    if (!extraction) return

    setLoading(true)
    try {
      const result = await api.previewSheetsRow(extraction)
      setSheetsPreview(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDryRun() {
    if (!file) return

    setLoading(true)
    try {
      const result = await api.dryRun(file)
      setDryRunResult(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setFile(null)
    setClassification(null)
    setExtraction(null)
    setCdPreview(null)
    setSheetsPreview(null)
    setDryRunResult(null)
    setError(null)
    setDocumentId(null)
    setRunId(null)
    setRunStatus(null)
    setRequestId(null)
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Test Lab</h1>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <div className="flex justify-between items-start">
            <div>
              <strong>Error:</strong> {error}
            </div>
            {requestId && (
              <span className="text-xs text-red-400">Request: {requestId}</span>
            )}
          </div>
          {classification?.needs_ocr && (
            <div className="mt-2 text-sm">
              <strong>Suggestion:</strong> This PDF appears to be a scanned image. OCR processing is required but not yet implemented.
            </div>
          )}
        </div>
      )}

      {/* Upload Zone */}
      <div className="mb-6">
        <div
          className={`dropzone ${dragActive ? 'active' : ''} ${file ? 'border-green-400 bg-green-50' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => document.getElementById('file-input').click()}
        >
          <input
            id="file-input"
            type="file"
            accept=".pdf"
            onChange={handleFileInput}
            className="hidden"
          />
          {file ? (
            <div>
              <svg className="w-12 h-12 mx-auto text-green-500 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-lg font-medium text-gray-900">{file.name}</p>
              <p className="text-sm text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
              <button onClick={(e) => { e.stopPropagation(); reset(); }} className="mt-2 text-sm text-red-600 hover:text-red-700">
                Remove
              </button>
            </div>
          ) : (
            <div>
              <svg className="w-12 h-12 mx-auto text-gray-400 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="text-lg font-medium text-gray-900">Drop PDF here or click to upload</p>
              <p className="text-sm text-gray-500">Copart, IAA, or Manheim invoice</p>
            </div>
          )}
        </div>
      </div>

      {loading && (
        <div className="mb-6 flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          <span className="ml-3 text-gray-600">{loadingStep || 'Processing...'}</span>
        </div>
      )}

      {/* Run Status Banner */}
      {runId && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-medium text-blue-800">Run Created</span>
              <span className="ml-2 text-sm text-blue-600">ID: {runId}</span>
              {documentId && <span className="ml-2 text-sm text-blue-600">| Doc: {documentId}</span>}
            </div>
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              runStatus === 'needs_review' ? 'bg-yellow-100 text-yellow-800' :
              runStatus === 'completed' ? 'bg-green-100 text-green-800' :
              runStatus === 'failed' ? 'bg-red-100 text-red-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {runStatus || 'pending'}
            </span>
          </div>
        </div>
      )}

      {/* Classification Result */}
      {classification && (
        <div className="card mb-6">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-medium">Classification Result</h3>
            <span className={`badge ${
              classification.source === 'UNKNOWN' ? 'badge-error' :
              classification.score >= 60 ? 'badge-success' :
              classification.score >= 30 ? 'badge-warning' : 'badge-error'
            }`}>
              {classification.score?.toFixed(1)}% confidence
            </span>
          </div>
          <div className="card-body">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-gray-500">Source</p>
                <p className="font-medium">{classification.source || 'Unknown'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Extractor</p>
                <p className="font-medium">{classification.extractor || 'None'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Needs OCR</p>
                <p className="font-medium">{classification.needs_ocr ? 'Yes' : 'No'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Text Length</p>
                <p className="font-medium">{classification.text_length || 0} chars</p>
              </div>
            </div>
            {classification.matched_patterns && classification.matched_patterns.length > 0 && (
              <div className="mt-4">
                <p className="text-sm text-gray-500 mb-2">Matched Patterns</p>
                <div className="flex flex-wrap gap-2">
                  {classification.matched_patterns.map((pattern, i) => (
                    <span key={i} className="badge badge-info">{pattern}</span>
                  ))}
                </div>
              </div>
            )}

            {/* OCR Warning */}
            {classification.needs_ocr && (
              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
                <p className="text-sm text-yellow-800">
                  <strong>OCR Required:</strong> This document appears to be a scanned PDF with insufficient text
                  ({classification.text_length} characters). OCR processing is needed for extraction.
                </p>
              </div>
            )}

            {/* All Scores (debug view) */}
            {classification.all_scores && (
              <div className="mt-4">
                <p className="text-sm text-gray-500 mb-2">All Extractor Scores</p>
                <div className="flex flex-wrap gap-2">
                  {classification.all_scores.map((s, i) => (
                    <span key={i} className={`px-2 py-1 rounded text-xs ${
                      s.score >= 60 ? 'bg-green-100 text-green-800' :
                      s.score >= 30 ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {s.source}: {s.score}%
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Extraction Result */}
      {extraction && (
        <div className="card mb-6">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-medium">Extraction Result</h3>
            <div className="flex space-x-2">
              <button onClick={handlePreviewSheets} disabled={loading} className="btn btn-sm btn-secondary">
                Preview Sheets Row
              </button>
              <button onClick={handlePreviewCD} disabled={loading} className="btn btn-sm btn-secondary">
                Preview CD Payload
              </button>
              <button onClick={handleDryRun} disabled={loading} className="btn btn-sm btn-primary">
                Full Dry Run
              </button>
            </div>
          </div>
          <div className="card-body">
            {extraction.invoice ? (
              <div className="space-y-4">
                {/* Basic Info */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-sm text-gray-500">Source</p>
                    <p className="font-medium">{extraction.invoice.source}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Reference ID</p>
                    <p className="font-medium font-mono">{extraction.invoice.reference_id || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Buyer ID</p>
                    <p className="font-medium">{extraction.invoice.buyer_id || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Total Amount</p>
                    <p className="font-medium">{extraction.invoice.total_amount ? `$${extraction.invoice.total_amount.toLocaleString()}` : '-'}</p>
                  </div>
                </div>

                {/* Vehicles */}
                {extraction.invoice.vehicles && extraction.invoice.vehicles.length > 0 && (
                  <div>
                    <p className="text-sm text-gray-500 mb-2">Vehicles ({extraction.invoice.vehicles.length})</p>
                    <table className="table">
                      <thead>
                        <tr>
                          <th>VIN</th>
                          <th>Year</th>
                          <th>Make</th>
                          <th>Model</th>
                          <th>Lot #</th>
                          <th>Color</th>
                          <th>Mileage</th>
                        </tr>
                      </thead>
                      <tbody>
                        {extraction.invoice.vehicles.map((v, i) => (
                          <tr key={i}>
                            <td className="font-mono text-xs">{v.vin || '-'}</td>
                            <td>{v.year || '-'}</td>
                            <td>{v.make || '-'}</td>
                            <td>{v.model || '-'}</td>
                            <td>{v.lot_number || '-'}</td>
                            <td>{v.color || '-'}</td>
                            <td>{v.mileage ? v.mileage.toLocaleString() : '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Pickup Address */}
                {extraction.invoice.pickup_address && (
                  <div>
                    <p className="text-sm text-gray-500 mb-2">Pickup Address</p>
                    <div className="bg-gray-50 p-3 rounded">
                      {extraction.invoice.pickup_address.name && (
                        <p className="font-medium">{extraction.invoice.pickup_address.name}</p>
                      )}
                      {extraction.invoice.pickup_address.street && (
                        <p>{extraction.invoice.pickup_address.street}</p>
                      )}
                      <p>
                        {extraction.invoice.pickup_address.city}, {extraction.invoice.pickup_address.state} {extraction.invoice.pickup_address.postal_code}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-500">No invoice data extracted</p>
            )}
          </div>
        </div>
      )}

      {/* CD Preview */}
      {cdPreview && (
        <div className="card mb-6">
          <div className="card-header">
            <h3 className="font-medium">Central Dispatch Payload Preview</h3>
          </div>
          <div className="card-body">
            <pre className="bg-gray-900 text-gray-100 p-4 rounded text-xs overflow-auto max-h-96">
              {JSON.stringify(cdPreview.payload, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Sheets Preview */}
      {sheetsPreview && (
        <div className="card mb-6">
          <div className="card-header">
            <h3 className="font-medium">Google Sheets Row Preview</h3>
          </div>
          <div className="card-body overflow-auto">
            <table className="table text-xs">
              <thead>
                <tr>
                  {Object.keys(sheetsPreview.row || {}).map(key => (
                    <th key={key}>{key}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  {Object.values(sheetsPreview.row || {}).map((value, i) => (
                    <td key={i}>{value !== null && value !== undefined ? String(value) : '-'}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Dry Run Result */}
      {dryRunResult && (
        <div className="card mb-6">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-medium">Dry Run Result</h3>
            <span className={`badge ${dryRunResult.status === 'ok' ? 'badge-success' : 'badge-error'}`}>
              {dryRunResult.status}
            </span>
          </div>
          <div className="card-body">
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Run ID</p>
                  <p className="font-mono text-sm">{dryRunResult.run_id}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Auction</p>
                  <p className="font-medium">{dryRunResult.auction || 'Unknown'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Score</p>
                  <p className="font-medium">{dryRunResult.score?.toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Warehouse</p>
                  <p className="font-medium">{dryRunResult.warehouse?.id || 'Not matched'}</p>
                </div>
              </div>

              {dryRunResult.would_export && (
                <div>
                  <p className="text-sm text-gray-500 mb-2">Would Export To</p>
                  <div className="flex flex-wrap gap-2">
                    {dryRunResult.would_export.map((target, i) => (
                      <span key={i} className="badge badge-info">{target}</span>
                    ))}
                  </div>
                </div>
              )}

              {dryRunResult.validation_errors && dryRunResult.validation_errors.length > 0 && (
                <div>
                  <p className="text-sm text-red-600 mb-2">Validation Errors</p>
                  <ul className="list-disc list-inside text-sm text-red-600">
                    {dryRunResult.validation_errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default TestLab
