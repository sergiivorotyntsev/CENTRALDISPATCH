import { useState, useEffect } from 'react'
import api from '../api'

// Central Dispatch API field definitions
const CD_FIELDS = [
  { key: 'vehicle_vin', label: 'VIN', type: 'text', required: true, description: 'Vehicle Identification Number' },
  { key: 'vehicle_year', label: 'Year', type: 'number', required: true, description: 'Vehicle year' },
  { key: 'vehicle_make', label: 'Make', type: 'text', required: true, description: 'Vehicle manufacturer' },
  { key: 'vehicle_model', label: 'Model', type: 'text', required: true, description: 'Vehicle model' },
  { key: 'vehicle_color', label: 'Color', type: 'text', required: false, description: 'Vehicle color' },
  { key: 'vehicle_type', label: 'Vehicle Type', type: 'select', required: true, description: 'sedan, suv, truck, van, motorcycle, other', options: ['sedan', 'suv', 'truck', 'van', 'motorcycle', 'other'] },
  { key: 'vehicle_condition', label: 'Condition', type: 'select', required: true, description: 'operable, inoperable', options: ['operable', 'inoperable'] },
  { key: 'pickup_name', label: 'Pickup Location Name', type: 'text', required: false, description: 'Name of pickup location (e.g., Copart Dallas)' },
  { key: 'pickup_address', label: 'Pickup Street Address', type: 'text', required: true, description: 'Street address for pickup' },
  { key: 'pickup_city', label: 'Pickup City', type: 'text', required: true, description: 'City for pickup' },
  { key: 'pickup_state', label: 'Pickup State', type: 'text', required: true, description: 'State abbreviation (e.g., TX)' },
  { key: 'pickup_zip', label: 'Pickup ZIP', type: 'text', required: true, description: '5-digit ZIP code' },
  { key: 'pickup_phone', label: 'Pickup Phone', type: 'text', required: false, description: 'Contact phone for pickup location' },
  { key: 'pickup_contact', label: 'Pickup Contact', type: 'text', required: false, description: 'Contact person name' },
  { key: 'delivery_name', label: 'Delivery Location Name', type: 'text', required: false, description: 'Name of delivery location' },
  { key: 'delivery_address', label: 'Delivery Street Address', type: 'text', required: true, description: 'Street address for delivery' },
  { key: 'delivery_city', label: 'Delivery City', type: 'text', required: true, description: 'City for delivery' },
  { key: 'delivery_state', label: 'Delivery State', type: 'text', required: true, description: 'State abbreviation' },
  { key: 'delivery_zip', label: 'Delivery ZIP', type: 'text', required: true, description: '5-digit ZIP code' },
  { key: 'delivery_phone', label: 'Delivery Phone', type: 'text', required: false, description: 'Contact phone for delivery' },
  { key: 'delivery_contact', label: 'Delivery Contact', type: 'text', required: false, description: 'Contact person name' },
  { key: 'buyer_id', label: 'Buyer ID', type: 'text', required: false, description: 'Buyer/Member ID from auction' },
  { key: 'buyer_name', label: 'Buyer Name', type: 'text', required: false, description: 'Buyer name' },
  { key: 'lot_number', label: 'Lot Number', type: 'text', required: false, description: 'Auction lot number' },
  { key: 'stock_number', label: 'Stock Number', type: 'text', required: false, description: 'Stock/Reference number' },
  { key: 'sale_date', label: 'Sale Date', type: 'date', required: false, description: 'Date of sale' },
  { key: 'total_amount', label: 'Total Amount', type: 'number', required: false, description: 'Total sale amount' },
  { key: 'notes', label: 'Notes', type: 'textarea', required: false, description: 'Additional notes or special instructions' },
  { key: 'transport_special_instructions', label: 'Transport Special Instructions', type: 'textarea', required: false, description: 'Special instructions for transport (appointment times, hours, etc.)' },
]

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

  // Selected auction type for editing
  const [editingAuctionType, setEditingAuctionType] = useState(null)
  const [fieldMappings, setFieldMappings] = useState([])
  const [loadingFields, setLoadingFields] = useState(false)

  // Warehouses
  const [warehouses, setWarehouses] = useState([])
  const [showWarehouseForm, setShowWarehouseForm] = useState(false)
  const [warehouseForm, setWarehouseForm] = useState({
    name: '',
    code: '',
    address: '',
    city: '',
    state: '',
    zip_code: '',
    phone: '',
    contact_name: '',
    transport_special_instructions: '',
    is_default: false,
  })
  const [editingWarehouse, setEditingWarehouse] = useState(null)

  // Training data
  const [trainingDocuments, setTrainingDocuments] = useState([])
  const [uploadingTrainingDoc, setUploadingTrainingDoc] = useState(false)

  useEffect(() => {
    loadAuctionTypes()
    loadRecentTests()
    loadTrainingStats()
    loadWarehouses()
  }, [])

  // Load field mappings when editing auction type changes
  useEffect(() => {
    if (editingAuctionType) {
      loadFieldMappings(editingAuctionType.id)
    }
  }, [editingAuctionType])

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

  async function loadWarehouses() {
    try {
      const data = await api.listWarehouses()
      setWarehouses(data.items || [])
    } catch (err) {
      console.error('Failed to load warehouses:', err)
    }
  }

  async function loadFieldMappings(auctionTypeId) {
    setLoadingFields(true)
    try {
      const data = await api.listFields(auctionTypeId, true)
      // Map API response to our format
      const fields = (data || []).map(f => ({
        id: f.id,
        field_key: f.source_key || f.cd_key || f.internal_key,
        display_name: f.display_name || f.source_key,
        field_type: f.field_type || 'text',
        is_required: f.is_required || false,
        description: f.description,
        sort_order: f.display_order || 0,
        is_active: f.is_active !== false,
        extraction_hints: f.extraction_hints || [],
        cd_key: f.cd_key,
        internal_key: f.internal_key,
        source_key: f.source_key,
      }))
      // If fields exist, use them; otherwise initialize with defaults
      if (fields.length > 0) {
        setFieldMappings(fields)
      } else {
        // Initialize with default CD fields
        setFieldMappings(CD_FIELDS.map((f, idx) => ({
          id: null,
          field_key: f.key,
          display_name: f.label,
          field_type: f.type,
          is_required: f.required,
          description: f.description,
          sort_order: idx,
          is_active: true,
          extraction_hints: [],
          cd_key: f.key,
          internal_key: f.key,
          source_key: f.key,
        })))
      }
    } catch (err) {
      console.error('Failed to load field mappings:', err)
      // Initialize with default CD fields if API fails
      setFieldMappings(CD_FIELDS.map((f, idx) => ({
        id: null,
        field_key: f.key,
        display_name: f.label,
        field_type: f.type,
        is_required: f.required,
        description: f.description,
        sort_order: idx,
        is_active: true,
        extraction_hints: [],
        cd_key: f.key,
        internal_key: f.key,
        source_key: f.key,
      })))
    } finally {
      setLoadingFields(false)
    }
  }

  async function handleSaveFieldMappings() {
    if (!editingAuctionType) return

    try {
      for (const field of fieldMappings) {
        if (field.id) {
          // Update existing field
          await api.updateField(editingAuctionType.id, field.id, {
            display_name: field.display_name,
            is_required: field.is_required,
            is_active: field.is_active,
            extraction_hints: field.extraction_hints || [],
            display_order: field.sort_order,
          })
        } else {
          // Create new field using correct API field names
          await api.createField(editingAuctionType.id, {
            source_key: field.field_key,
            internal_key: field.field_key,
            cd_key: field.cd_key || field.field_key,
            display_name: field.display_name,
            field_type: field.field_type,
            is_required: field.is_required,
            description: field.description,
            display_order: field.sort_order,
            extraction_hints: field.extraction_hints || [],
            is_active: true,
          })
        }
      }
      setError(null)
      alert('Field mappings saved successfully!')
      loadFieldMappings(editingAuctionType.id)
    } catch (err) {
      setError('Failed to save field mappings: ' + err.message)
    }
  }

  async function handleCreateWarehouse(e) {
    e.preventDefault()
    try {
      // Format data for the API
      const warehouseData = {
        code: warehouseForm.code,
        name: warehouseForm.name,
        address: warehouseForm.address,
        city: warehouseForm.city,
        state: warehouseForm.state,
        zip_code: warehouseForm.zip_code,
        contact: {
          phone: warehouseForm.phone || null,
          notes: warehouseForm.contact_name || null,
        },
        requirements: {
          special_instructions: warehouseForm.transport_special_instructions || null,
        },
        is_active: true,
      }
      await api.createWarehouse(warehouseData)
      setShowWarehouseForm(false)
      setWarehouseForm({
        name: '',
        code: '',
        address: '',
        city: '',
        state: '',
        zip_code: '',
        phone: '',
        contact_name: '',
        transport_special_instructions: '',
        is_default: false,
      })
      loadWarehouses()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }

  async function handleUpdateWarehouse(e) {
    e.preventDefault()
    if (!editingWarehouse) return
    try {
      const warehouseData = {
        name: warehouseForm.name,
        address: warehouseForm.address,
        city: warehouseForm.city,
        state: warehouseForm.state,
        zip_code: warehouseForm.zip_code,
        contact: {
          phone: warehouseForm.phone || null,
          notes: warehouseForm.contact_name || null,
        },
        requirements: {
          special_instructions: warehouseForm.transport_special_instructions || null,
        },
      }
      await api.updateWarehouse(editingWarehouse.id, warehouseData)
      setEditingWarehouse(null)
      setWarehouseForm({
        name: '',
        code: '',
        address: '',
        city: '',
        state: '',
        zip_code: '',
        phone: '',
        contact_name: '',
        transport_special_instructions: '',
        is_default: false,
      })
      loadWarehouses()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }

  async function handleDeleteWarehouse(id) {
    if (!confirm('Are you sure you want to delete this warehouse?')) return
    try {
      await api.deleteWarehouseFull(id)
      loadWarehouses()
    } catch (err) {
      alert('Error: ' + err.message)
    }
  }

  function startEditWarehouse(wh) {
    setEditingWarehouse(wh)
    setWarehouseForm({
      name: wh.name || '',
      code: wh.code || '',
      address: wh.address || '',
      city: wh.city || '',
      state: wh.state || '',
      zip_code: wh.zip_code || '',
      phone: wh.contact?.phone || '',
      contact_name: wh.contact?.notes || '',
      transport_special_instructions: wh.requirements?.special_instructions || '',
      is_default: false,
    })
  }

  async function handleUploadTrainingDoc(file, auctionTypeId) {
    setUploadingTrainingDoc(true)
    try {
      await api.uploadDocument(file, auctionTypeId, 'train')
      loadTrainingStats()
      loadRecentTests()
    } catch (err) {
      alert('Error uploading training document: ' + err.message)
    } finally {
      setUploadingTrainingDoc(false)
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
          <button
            onClick={() => setActiveTab('warehouses')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'warehouses'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Warehouses
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
          <div className={editingAuctionType ? 'lg:col-span-1' : 'lg:col-span-2'}>
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
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auctionTypes.map((at) => (
                      <tr
                        key={at.id}
                        className={`cursor-pointer hover:bg-gray-50 ${editingAuctionType?.id === at.id ? 'bg-primary-50' : ''}`}
                        onClick={() => setEditingAuctionType(at)}
                      >
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
                        <td>
                          {at.is_active ? (
                            <span className="badge badge-success">Active</span>
                          ) : (
                            <span className="badge badge-gray">Inactive</span>
                          )}
                        </td>
                        <td>
                          <button
                            onClick={(e) => { e.stopPropagation(); setEditingAuctionType(at); }}
                            className="text-sm text-primary-600 hover:text-primary-800"
                          >
                            Configure Fields
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Create Auction Type Form */}
            {showAuctionTypeForm && (
              <div className="card mt-6">
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
                    <button type="submit" className="btn btn-primary flex-1">Create</button>
                    <button type="button" onClick={() => setShowAuctionTypeForm(false)} className="btn btn-secondary">Cancel</button>
                  </div>
                </form>
              </div>
            )}
          </div>

          {/* Field Mapping Configuration Panel */}
          <div className={editingAuctionType ? 'lg:col-span-2' : 'lg:col-span-1'}>
            {editingAuctionType ? (
              <div className="card">
                <div className="card-header flex items-center justify-between">
                  <div>
                    <h2 className="font-semibold">Field Mappings: {editingAuctionType.name}</h2>
                    <p className="text-sm text-gray-500">Configure which fields are extracted and mapped to Central Dispatch</p>
                  </div>
                  <button
                    onClick={() => setEditingAuctionType(null)}
                    className="text-gray-500 hover:text-gray-700"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                <div className="card-body p-0">
                  {loadingFields ? (
                    <div className="p-8 text-center">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
                    </div>
                  ) : (
                    <>
                      <div className="max-h-[500px] overflow-y-auto">
                        <table className="table table-sm">
                          <thead className="sticky top-0 bg-white">
                            <tr>
                              <th className="w-8">Active</th>
                              <th>CD API Field</th>
                              <th>Display Name</th>
                              <th>Required</th>
                              <th>Type</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(fieldMappings.length > 0 ? fieldMappings : CD_FIELDS.map((f, idx) => ({
                              id: null,
                              field_key: f.key,
                              display_name: f.label,
                              field_type: f.type,
                              is_required: f.required,
                              description: f.description,
                              sort_order: idx,
                              is_active: true,
                            }))).map((field, idx) => (
                              <tr key={field.field_key || idx} className="hover:bg-gray-50">
                                <td>
                                  <input
                                    type="checkbox"
                                    checked={field.is_active !== false}
                                    onChange={(e) => {
                                      const updated = [...fieldMappings]
                                      if (updated[idx]) {
                                        updated[idx] = { ...updated[idx], is_active: e.target.checked }
                                        setFieldMappings(updated)
                                      }
                                    }}
                                    className="form-checkbox"
                                  />
                                </td>
                                <td className="font-mono text-xs text-gray-600">{field.field_key}</td>
                                <td>
                                  <input
                                    type="text"
                                    value={field.display_name}
                                    onChange={(e) => {
                                      const updated = [...fieldMappings]
                                      if (updated[idx]) {
                                        updated[idx] = { ...updated[idx], display_name: e.target.value }
                                        setFieldMappings(updated)
                                      }
                                    }}
                                    className="form-input form-input-sm w-full"
                                  />
                                </td>
                                <td>
                                  <input
                                    type="checkbox"
                                    checked={field.is_required}
                                    onChange={(e) => {
                                      const updated = [...fieldMappings]
                                      if (updated[idx]) {
                                        updated[idx] = { ...updated[idx], is_required: e.target.checked }
                                        setFieldMappings(updated)
                                      }
                                    }}
                                    className="form-checkbox"
                                  />
                                </td>
                                <td className="text-xs text-gray-500">{field.field_type}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="p-4 border-t bg-gray-50 flex justify-between items-center">
                        <span className="text-sm text-gray-500">
                          {fieldMappings.filter(f => f.is_active !== false).length} fields active
                        </span>
                        <button onClick={handleSaveFieldMappings} className="btn btn-primary">
                          Save Field Mappings
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="card">
                <div className="card-body text-center py-8">
                  <svg className="w-12 h-12 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                  <p className="text-gray-500 mb-2">Select an auction type to configure field mappings</p>
                  <p className="text-xs text-gray-400">Click on any auction type in the table to configure which fields are extracted and how they map to Central Dispatch API</p>
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

          {/* Upload Training Document */}
          <div className="card">
            <div className="card-header">
              <h2 className="font-semibold">Upload Training Document</h2>
            </div>
            <div className="card-body">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                  <div className="flex items-center space-x-2">
                    <label className="btn btn-secondary flex-1 cursor-pointer text-center">
                      <input
                        type="file"
                        accept=".pdf"
                        onChange={(e) => {
                          if (e.target.files[0]) {
                            handleUploadTrainingDoc(e.target.files[0], selectedAuctionType)
                          }
                        }}
                        className="hidden"
                        disabled={uploadingTrainingDoc}
                      />
                      {uploadingTrainingDoc ? 'Uploading...' : 'Select & Upload PDF'}
                    </label>
                  </div>
                </div>
              </div>
              <p className="text-xs text-gray-500 mt-3">
                Upload documents to build training data. After upload, review and correct the extracted fields to improve accuracy.
              </p>
            </div>
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

      {/* Warehouses Tab */}
      {activeTab === 'warehouses' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <div className="card">
              <div className="card-header flex items-center justify-between">
                <h2 className="font-semibold">Delivery Warehouses</h2>
                <button
                  onClick={() => { setShowWarehouseForm(true); setEditingWarehouse(null); }}
                  className="btn btn-sm btn-primary"
                >
                  + Add Warehouse
                </button>
              </div>
              <div className="card-body p-0">
                {warehouses.length === 0 ? (
                  <div className="p-8 text-center text-gray-500">
                    No warehouses configured. Add your first warehouse to get started.
                  </div>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Code</th>
                        <th>Address</th>
                        <th>Phone</th>
                        <th>Default</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {warehouses.map((wh) => (
                        <tr key={wh.id}>
                          <td className="font-medium">{wh.name}</td>
                          <td><span className="badge bg-gray-100 text-gray-800">{wh.code}</span></td>
                          <td className="text-sm text-gray-500">
                            {wh.address}, {wh.city}, {wh.state} {wh.zip_code}
                          </td>
                          <td className="text-sm">{wh.contact?.phone || '-'}</td>
                          <td>
                            {wh.is_default ? (
                              <span className="badge badge-success">Default</span>
                            ) : (
                              <span className="text-gray-400">-</span>
                            )}
                          </td>
                          <td>
                            <div className="flex space-x-2">
                              <button
                                onClick={() => startEditWarehouse(wh)}
                                className="text-sm text-primary-600 hover:text-primary-800"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => handleDeleteWarehouse(wh.id)}
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
                )}
              </div>
            </div>

            {/* Transport Special Instructions Info */}
            <div className="card mt-6">
              <div className="card-header">
                <h2 className="font-semibold">Transport Special Instructions</h2>
              </div>
              <div className="card-body">
                <p className="text-sm text-gray-600 mb-4">
                  Each warehouse can have special delivery instructions that will be automatically included
                  when exporting to Central Dispatch. Common examples:
                </p>
                <div className="bg-gray-50 p-4 rounded-lg space-y-2 text-sm">
                  <p><strong>Example 1:</strong> "DROP-OFF Appointment required. Working Hours: Mon-Fri 8am-5pm. Call 24h ahead."</p>
                  <p><strong>Example 2:</strong> "Gate code: 1234. Contact John at front office upon arrival."</p>
                  <p><strong>Example 3:</strong> "No deliveries on weekends. Must call 1h before arrival."</p>
                </div>
              </div>
            </div>
          </div>

          {/* Warehouse Form */}
          <div className="lg:col-span-1">
            {(showWarehouseForm || editingWarehouse) ? (
              <div className="card">
                <div className="card-header flex items-center justify-between">
                  <h2 className="font-semibold">{editingWarehouse ? 'Edit Warehouse' : 'Add Warehouse'}</h2>
                  <button
                    onClick={() => { setShowWarehouseForm(false); setEditingWarehouse(null); }}
                    className="text-gray-500 hover:text-gray-700"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                <form onSubmit={editingWarehouse ? handleUpdateWarehouse : handleCreateWarehouse} className="card-body space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="form-label">Name</label>
                      <input
                        type="text"
                        value={warehouseForm.name}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, name: e.target.value }))}
                        className="form-input w-full"
                        placeholder="Main Warehouse"
                        required
                      />
                    </div>
                    <div>
                      <label className="form-label">Code</label>
                      <input
                        type="text"
                        value={warehouseForm.code}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, code: e.target.value.toUpperCase() }))}
                        className="form-input w-full font-mono"
                        placeholder="MAIN"
                        maxLength={20}
                        required
                        disabled={!!editingWarehouse}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="form-label">Street Address</label>
                    <input
                      type="text"
                      value={warehouseForm.address}
                      onChange={(e) => setWarehouseForm(f => ({ ...f, address: e.target.value }))}
                      className="form-input w-full"
                      placeholder="123 Main St"
                      required
                    />
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="form-label">City</label>
                      <input
                        type="text"
                        value={warehouseForm.city}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, city: e.target.value }))}
                        className="form-input w-full"
                        placeholder="Dallas"
                        required
                      />
                    </div>
                    <div>
                      <label className="form-label">State</label>
                      <input
                        type="text"
                        value={warehouseForm.state}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, state: e.target.value.toUpperCase() }))}
                        className="form-input w-full"
                        placeholder="TX"
                        maxLength={2}
                        required
                      />
                    </div>
                    <div>
                      <label className="form-label">ZIP</label>
                      <input
                        type="text"
                        value={warehouseForm.zip_code}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, zip_code: e.target.value }))}
                        className="form-input w-full"
                        placeholder="75001"
                        maxLength={10}
                        required
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="form-label">Phone</label>
                      <input
                        type="text"
                        value={warehouseForm.phone}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, phone: e.target.value }))}
                        className="form-input w-full"
                        placeholder="(555) 123-4567"
                      />
                    </div>
                    <div>
                      <label className="form-label">Contact Name</label>
                      <input
                        type="text"
                        value={warehouseForm.contact_name}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, contact_name: e.target.value }))}
                        className="form-input w-full"
                        placeholder="John Smith"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="form-label">Transport Special Instructions</label>
                    <textarea
                      value={warehouseForm.transport_special_instructions}
                      onChange={(e) => setWarehouseForm(f => ({ ...f, transport_special_instructions: e.target.value }))}
                      className="form-input w-full"
                      rows={3}
                      placeholder="DROP-OFF Appointment required. Working Hours: Mon-Fri 8am-5pm..."
                    />
                    <p className="text-xs text-gray-500 mt-1">These instructions will be included in Central Dispatch listings</p>
                  </div>
                  <div>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={warehouseForm.is_default}
                        onChange={(e) => setWarehouseForm(f => ({ ...f, is_default: e.target.checked }))}
                        className="form-checkbox"
                      />
                      <span className="text-sm">Set as default delivery warehouse</span>
                    </label>
                  </div>
                  <button type="submit" className="btn btn-primary w-full">
                    {editingWarehouse ? 'Update Warehouse' : 'Add Warehouse'}
                  </button>
                </form>
              </div>
            ) : (
              <div className="card">
                <div className="card-body text-center py-8">
                  <svg className="w-12 h-12 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                  </svg>
                  <p className="text-gray-500 mb-4">Configure delivery warehouses for Central Dispatch exports</p>
                  <button
                    onClick={() => setShowWarehouseForm(true)}
                    className="btn btn-primary"
                  >
                    Add Warehouse
                  </button>
                </div>
              </div>
            )}
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
