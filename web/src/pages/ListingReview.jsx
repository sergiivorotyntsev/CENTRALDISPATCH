import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from '../api'

/**
 * Central Dispatch API Field Definitions
 * These are the only fields that can be exported to CD
 */
const CD_API_FIELDS = [
  // Vehicle Information
  { key: 'vehicle_vin', label: 'VIN', type: 'text', required: true, section: 'vehicle' },
  { key: 'vehicle_year', label: 'Year', type: 'number', required: true, section: 'vehicle' },
  { key: 'vehicle_make', label: 'Make', type: 'text', required: true, section: 'vehicle' },
  { key: 'vehicle_model', label: 'Model', type: 'text', required: true, section: 'vehicle' },
  { key: 'vehicle_color', label: 'Color', type: 'text', required: false, section: 'vehicle' },
  { key: 'vehicle_type', label: 'Vehicle Type', type: 'select', required: true, section: 'vehicle',
    options: ['sedan', 'suv', 'truck', 'van', 'motorcycle', 'other'] },
  { key: 'vehicle_condition', label: 'Condition', type: 'select', required: true, section: 'vehicle',
    options: ['operable', 'inoperable'] },

  // Pickup Location
  { key: 'pickup_name', label: 'Location Name', type: 'text', required: false, section: 'pickup' },
  { key: 'pickup_address', label: 'Street Address', type: 'text', required: true, section: 'pickup' },
  { key: 'pickup_city', label: 'City', type: 'text', required: true, section: 'pickup' },
  { key: 'pickup_state', label: 'State', type: 'text', required: true, section: 'pickup' },
  { key: 'pickup_zip', label: 'ZIP Code', type: 'text', required: true, section: 'pickup' },
  { key: 'pickup_phone', label: 'Phone', type: 'text', required: false, section: 'pickup' },
  { key: 'pickup_contact', label: 'Contact Name', type: 'text', required: false, section: 'pickup' },

  // Delivery Location
  { key: 'delivery_name', label: 'Location Name', type: 'text', required: false, section: 'delivery' },
  { key: 'delivery_address', label: 'Street Address', type: 'text', required: true, section: 'delivery' },
  { key: 'delivery_city', label: 'City', type: 'text', required: true, section: 'delivery' },
  { key: 'delivery_state', label: 'State', type: 'text', required: true, section: 'delivery' },
  { key: 'delivery_zip', label: 'ZIP Code', type: 'text', required: true, section: 'delivery' },
  { key: 'delivery_phone', label: 'Phone', type: 'text', required: false, section: 'delivery' },
  { key: 'delivery_contact', label: 'Contact Name', type: 'text', required: false, section: 'delivery' },

  // Additional Info
  { key: 'lot_number', label: 'Lot Number', type: 'text', required: false, section: 'additional' },
  { key: 'stock_number', label: 'Stock Number', type: 'text', required: false, section: 'additional' },
  { key: 'buyer_id', label: 'Buyer ID', type: 'text', required: false, section: 'additional' },
  { key: 'buyer_name', label: 'Buyer Name', type: 'text', required: false, section: 'additional' },
  { key: 'sale_date', label: 'Sale Date', type: 'date', required: false, section: 'additional' },
  { key: 'total_amount', label: 'Total Amount', type: 'number', required: false, section: 'additional' },

  // Notes
  { key: 'notes', label: 'Notes', type: 'textarea', required: false, section: 'notes' },
  { key: 'transport_special_instructions', label: 'Special Instructions', type: 'textarea', required: false, section: 'notes' },
]

/**
 * Listing Review Page - Production Workflow
 *
 * Reviews and edits extracted data before exporting to Central Dispatch.
 * Different from Test Lab's Review & Train which is for training the model.
 */
function ListingReview() {
  const { id } = useParams() // extraction run ID
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  // Data
  const [extraction, setExtraction] = useState(null)
  const [document, setDocument] = useState(null)
  const [fields, setFields] = useState({})
  const [warehouses, setWarehouses] = useState([])
  const [selectedWarehouse, setSelectedWarehouse] = useState(null)

  // Export state
  const [exporting, setExporting] = useState(false)
  const [exportResult, setExportResult] = useState(null)
  const [showPayloadPreview, setShowPayloadPreview] = useState(false)
  const [payloadPreview, setPayloadPreview] = useState(null)

  // Load data
  useEffect(() => {
    async function loadData() {
      setLoading(true)
      setError(null)
      try {
        // Load extraction details
        const extResult = await api.getExtraction(id)
        setExtraction(extResult)

        // Parse outputs_json
        let outputs = {}
        if (extResult.outputs_json) {
          outputs = typeof extResult.outputs_json === 'string'
            ? JSON.parse(extResult.outputs_json)
            : extResult.outputs_json
        }
        setFields(outputs)

        // Load document
        if (extResult.document_id) {
          try {
            const docResult = await api.getDocument(extResult.document_id)
            setDocument(docResult)
          } catch (err) {
            console.error('Failed to load document:', err)
          }
        }

        // Load warehouses
        const whResult = await api.listWarehouses()
        setWarehouses(whResult.items || [])

        // Set selected warehouse if already set
        if (outputs.warehouse_id) {
          const wh = (whResult.items || []).find(w => w.id === parseInt(outputs.warehouse_id))
          if (wh) setSelectedWarehouse(wh)
        }
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [id])

  // Update field value
  function handleFieldChange(key, value) {
    setFields(prev => ({ ...prev, [key]: value }))
  }

  // Handle warehouse selection
  function handleWarehouseSelect(warehouseId) {
    const wh = warehouses.find(w => w.id === parseInt(warehouseId))
    setSelectedWarehouse(wh)

    if (wh) {
      // Auto-fill delivery fields from warehouse
      setFields(prev => ({
        ...prev,
        warehouse_id: wh.id,
        delivery_name: wh.name,
        delivery_address: wh.address,
        delivery_city: wh.city,
        delivery_state: wh.state,
        delivery_zip: wh.zip_code,
        delivery_phone: wh.contact?.phone || '',
        delivery_contact: wh.contact?.notes || '',
        transport_special_instructions: wh.requirements?.special_instructions || prev.transport_special_instructions || '',
      }))
    }
  }

  // Save changes
  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      // Update extraction with new field values
      await api.updateExtraction(id, {
        outputs_json: fields,
        status: 'reviewed',
      })

      // Reload extraction
      const extResult = await api.getExtraction(id)
      setExtraction(extResult)
    } catch (err) {
      setError(`Save failed: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  // Preview CD payload
  async function handlePreviewPayload() {
    try {
      const result = await api.getCDPayloadPreview(id)
      setPayloadPreview(result)
      setShowPayloadPreview(true)
    } catch (err) {
      setError(`Preview failed: ${err.message}`)
    }
  }

  // Export to Central Dispatch
  async function handleExport() {
    if (!selectedWarehouse) {
      setError('Please select a delivery warehouse before exporting')
      return
    }

    // Validate required fields
    const missing = CD_API_FIELDS
      .filter(f => f.required && !fields[f.key])
      .map(f => f.label)

    if (missing.length > 0) {
      setError(`Missing required fields: ${missing.join(', ')}`)
      return
    }

    setExporting(true)
    setExportResult(null)
    try {
      // Save first
      await api.updateExtraction(id, {
        outputs_json: fields,
        status: 'approved',
      })

      // Then export
      const result = await api.exportToCentralDispatch(id)
      setExportResult({
        success: true,
        message: 'Successfully exported to Central Dispatch',
        orderId: result.cd_listing_id || result.order_id,
      })

      // Reload extraction to get updated status
      const extResult = await api.getExtraction(id)
      setExtraction(extResult)
    } catch (err) {
      setExportResult({
        success: false,
        message: err.message || 'Export failed',
      })
    } finally {
      setExporting(false)
    }
  }

  // Render field input
  function renderFieldInput(field) {
    const value = fields[field.key] || ''
    const isDisabled = extraction?.status === 'exported'

    if (field.type === 'select') {
      return (
        <select
          value={value}
          onChange={(e) => handleFieldChange(field.key, e.target.value)}
          disabled={isDisabled}
          className={`form-select w-full ${isDisabled ? 'bg-gray-100' : ''}`}
        >
          <option value="">Select...</option>
          {field.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )
    }

    if (field.type === 'textarea') {
      return (
        <textarea
          value={value}
          onChange={(e) => handleFieldChange(field.key, e.target.value)}
          disabled={isDisabled}
          className={`form-input w-full ${isDisabled ? 'bg-gray-100' : ''}`}
          rows={3}
        />
      )
    }

    return (
      <input
        type={field.type}
        value={value}
        onChange={(e) => handleFieldChange(field.key, e.target.value)}
        disabled={isDisabled}
        className={`form-input w-full ${isDisabled ? 'bg-gray-100' : ''}`}
      />
    )
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/4 mb-4"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    )
  }

  if (error && !extraction) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h3 className="text-red-800 font-medium">Error</h3>
          <p className="text-red-600 mt-1">{error}</p>
          <button
            onClick={() => navigate('/documents')}
            className="mt-4 text-blue-600 hover:text-blue-800"
          >
            &larr; Back to Documents
          </button>
        </div>
      </div>
    )
  }

  const isExported = extraction?.status === 'exported'
  const canExport = !isExported && selectedWarehouse

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
            <Link to="/documents" className="hover:text-blue-600">&larr; Documents</Link>
            <span>/</span>
            <span>Review Listing</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">
            Review & Export to Central Dispatch
          </h1>
          <div className="flex items-center gap-3 mt-2">
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              extraction?.auction_type_code === 'COPART' ? 'bg-blue-100 text-blue-800' :
              extraction?.auction_type_code === 'IAA' ? 'bg-purple-100 text-purple-800' :
              extraction?.auction_type_code === 'MANHEIM' ? 'bg-green-100 text-green-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {extraction?.auction_type_code}
            </span>
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              extraction?.status === 'exported' ? 'bg-green-100 text-green-800' :
              extraction?.status === 'reviewed' || extraction?.status === 'approved' ? 'bg-blue-100 text-blue-800' :
              extraction?.status === 'needs_review' ? 'bg-yellow-100 text-yellow-800' :
              'bg-gray-100 text-gray-800'
            }`}>
              {extraction?.status}
            </span>
            {fields.lot_number && (
              <span className="text-sm text-gray-600">
                Lot: <span className="font-medium">{fields.lot_number}</span>
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handlePreviewPayload}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
          >
            Preview Payload
          </button>
          <button
            onClick={handleSave}
            disabled={saving || isExported}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
          <button
            onClick={handleExport}
            disabled={!canExport || exporting}
            className={`px-4 py-2 rounded-lg font-medium ${
              canExport
                ? 'bg-green-600 text-white hover:bg-green-700'
                : 'bg-gray-200 text-gray-500 cursor-not-allowed'
            }`}
          >
            {exporting ? 'Exporting...' : isExported ? 'Already Exported' : 'Export to CD'}
          </button>
        </div>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <strong>Error:</strong> {error}
          <button onClick={() => setError(null)} className="ml-4 text-sm underline">Dismiss</button>
        </div>
      )}

      {exportResult && (
        <div className={`mb-6 p-4 rounded-lg ${
          exportResult.success
            ? 'bg-green-50 border border-green-200'
            : 'bg-red-50 border border-red-200'
        }`}>
          <p className={exportResult.success ? 'text-green-800' : 'text-red-800'}>
            {exportResult.message}
            {exportResult.orderId && (
              <span className="ml-2 font-medium">(CD ID: {exportResult.orderId})</span>
            )}
          </p>
        </div>
      )}

      {/* Warehouse Selection Banner */}
      {!isExported && (
        <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-blue-800">Delivery Warehouse</h3>
              <p className="text-sm text-blue-700">Select the warehouse where this vehicle will be delivered</p>
            </div>
            <select
              value={selectedWarehouse?.id || ''}
              onChange={(e) => handleWarehouseSelect(e.target.value)}
              className="form-select"
            >
              <option value="">Select Warehouse...</option>
              {warehouses.map((wh) => (
                <option key={wh.id} value={wh.id}>
                  {wh.name} - {wh.city}, {wh.state}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Vehicle Information */}
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-medium text-gray-900">Vehicle Information</h2>
          </div>
          <div className="p-4 space-y-4">
            {CD_API_FIELDS.filter(f => f.section === 'vehicle').map((field) => (
              <div key={field.key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                  {field.required && <span className="text-red-500 ml-1">*</span>}
                </label>
                {renderFieldInput(field)}
              </div>
            ))}
          </div>
        </div>

        {/* Pickup Location */}
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-medium text-gray-900">Pickup Location</h2>
          </div>
          <div className="p-4 space-y-4">
            {CD_API_FIELDS.filter(f => f.section === 'pickup').map((field) => (
              <div key={field.key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                  {field.required && <span className="text-red-500 ml-1">*</span>}
                </label>
                {renderFieldInput(field)}
              </div>
            ))}
          </div>
        </div>

        {/* Delivery Location */}
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <h2 className="font-medium text-gray-900">Delivery Location</h2>
            {selectedWarehouse && (
              <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                From Warehouse
              </span>
            )}
          </div>
          <div className="p-4 space-y-4">
            {CD_API_FIELDS.filter(f => f.section === 'delivery').map((field) => (
              <div key={field.key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                  {field.required && <span className="text-red-500 ml-1">*</span>}
                </label>
                {renderFieldInput(field)}
              </div>
            ))}
          </div>
        </div>

        {/* Additional Information */}
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-medium text-gray-900">Additional Information</h2>
          </div>
          <div className="p-4 space-y-4">
            {CD_API_FIELDS.filter(f => f.section === 'additional').map((field) => (
              <div key={field.key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                </label>
                {renderFieldInput(field)}
              </div>
            ))}
          </div>
        </div>

        {/* Notes & Instructions - Full Width */}
        <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h2 className="font-medium text-gray-900">Notes & Special Instructions</h2>
          </div>
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            {CD_API_FIELDS.filter(f => f.section === 'notes').map((field) => (
              <div key={field.key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                </label>
                {renderFieldInput(field)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Extraction Metadata */}
      <div className="mt-6 bg-gray-50 rounded-lg p-4">
        <h3 className="font-medium text-gray-900 mb-2">Extraction Details</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div>
            <div className="text-gray-500">Run ID</div>
            <div className="font-medium">{extraction?.id}</div>
          </div>
          <div>
            <div className="text-gray-500">Document</div>
            <div className="font-medium truncate">{document?.filename || '-'}</div>
          </div>
          <div>
            <div className="text-gray-500">Status</div>
            <div className="font-medium">{extraction?.status}</div>
          </div>
          <div>
            <div className="text-gray-500">Confidence</div>
            <div className="font-medium">
              {extraction?.extraction_score
                ? `${Math.round(extraction.extraction_score * 100)}%`
                : 'N/A'}
            </div>
          </div>
          <div>
            <div className="text-gray-500">Created</div>
            <div className="font-medium">
              {extraction?.created_at ? new Date(extraction.created_at).toLocaleString() : '-'}
            </div>
          </div>
        </div>
      </div>

      {/* Payload Preview Modal */}
      {showPayloadPreview && payloadPreview && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-3xl w-full mx-4 max-h-[80vh] overflow-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">Central Dispatch API Payload</h2>
              <button
                onClick={() => setShowPayloadPreview(false)}
                className="text-gray-500 hover:text-gray-700"
              >
                &times;
              </button>
            </div>

            {payloadPreview.validation_errors?.length > 0 && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                <h3 className="font-medium text-red-800 mb-2">Validation Errors</h3>
                <ul className="list-disc list-inside text-sm text-red-700">
                  {payloadPreview.validation_errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </div>
            )}

            <pre className="bg-gray-100 p-4 rounded-lg text-xs overflow-auto max-h-96">
              {JSON.stringify(payloadPreview.payload, null, 2)}
            </pre>

            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowPayloadPreview(false)}
                className="btn btn-secondary"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ListingReview
