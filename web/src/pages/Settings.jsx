import { useState, useEffect } from 'react'
import api from '../api'

function Settings() {
  const [activeTab, setActiveTab] = useState('targets')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState(null)

  // Data states
  const [settings, setSettings] = useState({})
  const [warehouses, setWarehouses] = useState([])
  const [emailRules, setEmailRules] = useState([])
  const [emailActivity, setEmailActivity] = useState([])
  const [auditLog, setAuditLog] = useState([])

  // Form states
  const [newWarehouse, setNewWarehouse] = useState({
    id: '', name: '', address: '', city: '', state: '', zip_code: ''
  })
  const [showNewWarehouse, setShowNewWarehouse] = useState(false)

  // Test results
  const [testResults, setTestResults] = useState({})

  useEffect(() => {
    loadAllData()
  }, [])

  async function loadAllData() {
    setLoading(true)
    try {
      const [settingsData, warehousesData] = await Promise.all([
        api.getAllSettings().catch(() => ({})),
        api.getWarehouses().catch(() => []),
      ])
      setSettings(settingsData)
      setWarehouses(warehousesData)
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadAuditLog() {
    try {
      const data = await api.getIntegrationAuditLog()
      setAuditLog(data)
    } catch (err) {
      console.error('Failed to load audit log:', err)
    }
  }

  async function loadEmailActivity() {
    try {
      const data = await api.getEmailActivity()
      setEmailActivity(data)
    } catch (err) {
      console.error('Failed to load email activity:', err)
    }
  }

  async function loadEmailRules() {
    try {
      const data = await api.getEmailRules()
      setEmailRules(data)
    } catch (err) {
      console.error('Failed to load email rules:', err)
    }
  }

  useEffect(() => {
    if (activeTab === 'audit') loadAuditLog()
    if (activeTab === 'email') {
      loadEmailActivity()
      loadEmailRules()
    }
  }, [activeTab])

  function showMessage(type, text) {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 5000)
  }

  // ==================== SAVE HANDLERS ====================

  async function handleSaveExportTargets() {
    setSaving(true)
    try {
      const targets = {
        sheets: settings.export_targets?.sheets || false,
        clickup: settings.export_targets?.clickup || false,
        cd: settings.export_targets?.cd || false,
      }
      await api.updateExportTargets(targets)
      showMessage('success', 'Export targets saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveSheets() {
    setSaving(true)
    try {
      await api.updateSheetsConfig(settings.sheets || {})
      showMessage('success', 'Google Sheets settings saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveClickUp() {
    setSaving(true)
    try {
      await api.updateClickUpConfig(settings.clickup || {})
      showMessage('success', 'ClickUp settings saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveCD() {
    setSaving(true)
    try {
      await api.updateCDConfig(settings.cd || {})
      showMessage('success', 'Central Dispatch settings saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveEmail() {
    setSaving(true)
    try {
      await api.updateEmailConfig(settings.email || {})
      showMessage('success', 'Email settings saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  // ==================== TEST HANDLERS ====================

  async function handleTestClickUp() {
    setTesting(true)
    try {
      const result = await api.testClickUpConnection()
      setTestResults({ ...testResults, clickup: result })
      if (result.success) {
        showMessage('success', `Connected as ${result.user_name || 'user'}`)
      } else {
        showMessage('error', result.error || 'Connection failed')
      }
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setTesting(false)
    }
  }

  async function handleTestSheets() {
    setTesting(true)
    try {
      const result = await api.testSheetsConnection()
      setTestResults({ ...testResults, sheets: result })
      if (result.success) {
        showMessage('success', `Connected to "${result.spreadsheet_title}"`)
      } else {
        showMessage('error', result.error || 'Connection failed')
      }
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setTesting(false)
    }
  }

  async function handleTestCD() {
    setTesting(true)
    try {
      const result = await api.testCDConnection()
      setTestResults({ ...testResults, cd: result })
      if (result.success) {
        showMessage('success', result.shipper_name ? `Connected as ${result.shipper_name}` : 'Connected')
      } else {
        showMessage('error', result.error || 'Connection failed')
      }
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setTesting(false)
    }
  }

  async function handleTestEmail() {
    setTesting(true)
    try {
      const result = await api.testEmailConnection()
      setTestResults({ ...testResults, email: result })
      if (result.success) {
        showMessage('success', `Connected - ${result.unread_count} unread messages`)
      } else {
        showMessage('error', result.error || 'Connection failed')
      }
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setTesting(false)
    }
  }

  // ==================== WAREHOUSE HANDLERS ====================

  async function handleAddWarehouse() {
    if (!newWarehouse.id || !newWarehouse.name) {
      showMessage('error', 'ID and Name are required')
      return
    }
    setSaving(true)
    try {
      await api.addWarehouse(newWarehouse)
      setWarehouses([...warehouses, newWarehouse])
      setNewWarehouse({ id: '', name: '', address: '', city: '', state: '', zip_code: '' })
      setShowNewWarehouse(false)
      showMessage('success', 'Warehouse added')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteWarehouse(id) {
    if (!confirm(`Delete warehouse ${id}?`)) return
    try {
      await api.deleteWarehouse(id)
      setWarehouses(warehouses.filter(w => w.id !== id))
      showMessage('success', 'Warehouse deleted')
    } catch (err) {
      showMessage('error', err.message)
    }
  }

  // ==================== EMAIL RULES ====================

  async function handleSaveEmailRules() {
    setSaving(true)
    try {
      await api.updateEmailRules(emailRules)
      showMessage('success', 'Email rules saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  function addEmailRule() {
    const newRule = {
      id: `rule_${Date.now()}`,
      name: 'New Rule',
      enabled: true,
      condition_type: 'subject_contains',
      condition_value: '',
      action: 'process',
      priority: emailRules.length,
    }
    setEmailRules([...emailRules, newRule])
  }

  function updateEmailRule(index, field, value) {
    const updated = [...emailRules]
    updated[index] = { ...updated[index], [field]: value }
    setEmailRules(updated)
  }

  function deleteEmailRule(index) {
    setEmailRules(emailRules.filter((_, i) => i !== index))
  }

  // ==================== HELPERS ====================

  function updateSettings(section, field, value) {
    setSettings({
      ...settings,
      [section]: {
        ...(settings[section] || {}),
        [field]: value
      }
    })
  }

  function toggleExportTarget(target) {
    const current = settings.export_targets || {}
    updateSettings('export_targets', target, !current[target])
  }

  const tabs = [
    { id: 'targets', label: 'Export Targets' },
    { id: 'sheets', label: 'Google Sheets' },
    { id: 'clickup', label: 'ClickUp' },
    { id: 'cd', label: 'Central Dispatch' },
    { id: 'email', label: 'Email Ingestion' },
    { id: 'warehouses', label: 'Warehouses' },
    { id: 'audit', label: 'Audit Log' },
  ]

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/4 mb-6"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

      {message && (
        <div className={`mb-6 p-4 rounded-lg flex items-center justify-between ${
          message.type === 'error' ? 'bg-red-50 border border-red-200 text-red-700' :
          'bg-green-50 border border-green-200 text-green-700'
        }`}>
          <span>{message.text}</span>
          <button onClick={() => setMessage(null)} className="text-current opacity-50 hover:opacity-100">x</button>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6 overflow-x-auto">
        <nav className="flex space-x-4">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Export Targets */}
      {activeTab === 'targets' && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-medium">Export Targets</h3>
            <p className="text-sm text-gray-500 mt-1">Select where extracted data should be sent</p>
          </div>
          <div className="card-body space-y-4">
            {[
              { key: 'sheets', name: 'Google Sheets', desc: 'Export to Google Spreadsheet' },
              { key: 'clickup', name: 'ClickUp', desc: 'Create tasks in ClickUp' },
              { key: 'cd', name: 'Central Dispatch', desc: 'Post listings to CD marketplace' },
            ].map(target => (
              <label key={target.key} className="flex items-center space-x-3 cursor-pointer p-3 rounded-lg hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={settings.export_targets?.[target.key] || false}
                  onChange={() => toggleExportTarget(target.key)}
                  className="w-5 h-5 text-primary-600 rounded focus:ring-primary-500"
                />
                <div className="flex-1">
                  <span className="font-medium">{target.name}</span>
                  <p className="text-sm text-gray-500">{target.desc}</p>
                </div>
              </label>
            ))}
            <div className="pt-4 border-t border-gray-200">
              <button onClick={handleSaveExportTargets} disabled={saving} className="btn btn-primary">
                {saving ? 'Saving...' : 'Save Targets'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Google Sheets */}
      {activeTab === 'sheets' && (
        <div className="space-y-6">
          <div className="card">
            <div className="card-header">
              <h3 className="font-medium">Google Sheets Configuration</h3>
            </div>
            <div className="card-body space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="form-label">Spreadsheet ID</label>
                  <input
                    type="text"
                    value={settings.sheets?.spreadsheet_id || ''}
                    onChange={e => updateSettings('sheets', 'spreadsheet_id', e.target.value)}
                    className="form-input"
                    placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
                  />
                  <p className="text-xs text-gray-500 mt-1">From URL: /d/[ID]/edit</p>
                </div>
                <div>
                  <label className="form-label">Sheet Name</label>
                  <input
                    type="text"
                    value={settings.sheets?.sheet_name || ''}
                    onChange={e => updateSettings('sheets', 'sheet_name', e.target.value)}
                    className="form-input"
                    placeholder="Pickups"
                  />
                </div>
              </div>
              <div>
                <label className="form-label">Service Account Credentials File</label>
                <input
                  type="text"
                  value={settings.sheets?.credentials_file || ''}
                  onChange={e => updateSettings('sheets', 'credentials_file', e.target.value)}
                  className="form-input"
                  placeholder="config/sheets_credentials.json"
                />
              </div>
              <div className="flex items-center space-x-3 pt-4 border-t border-gray-200">
                <button onClick={handleSaveSheets} disabled={saving} className="btn btn-primary">
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button onClick={handleTestSheets} disabled={testing} className="btn btn-secondary">
                  {testing ? 'Testing...' : 'Test Connection'}
                </button>
              </div>
            </div>
          </div>

          {testResults.sheets && (
            <TestResultCard result={testResults.sheets} type="sheets" />
          )}
        </div>
      )}

      {/* ClickUp */}
      {activeTab === 'clickup' && (
        <div className="space-y-6">
          <div className="card">
            <div className="card-header">
              <h3 className="font-medium">ClickUp Configuration</h3>
            </div>
            <div className="card-body space-y-4">
              <div>
                <label className="form-label">API Token</label>
                <input
                  type="password"
                  value={settings.clickup?.api_token || ''}
                  onChange={e => updateSettings('clickup', 'api_token', e.target.value)}
                  className="form-input"
                  placeholder="pk_xxxxx"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Get your token from ClickUp Settings - Apps - API Token
                </p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="form-label">List ID</label>
                  <input
                    type="text"
                    value={settings.clickup?.list_id || ''}
                    onChange={e => updateSettings('clickup', 'list_id', e.target.value)}
                    className="form-input"
                    placeholder="901234567"
                  />
                </div>
                <div>
                  <label className="form-label">Workspace ID</label>
                  <input
                    type="text"
                    value={settings.clickup?.workspace_id || ''}
                    onChange={e => updateSettings('clickup', 'workspace_id', e.target.value)}
                    className="form-input"
                    placeholder="Auto-detected on test"
                  />
                </div>
              </div>
              <div className="flex items-center space-x-3 pt-4 border-t border-gray-200">
                <button onClick={handleSaveClickUp} disabled={saving} className="btn btn-primary">
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button onClick={handleTestClickUp} disabled={testing} className="btn btn-secondary">
                  {testing ? 'Testing...' : 'Test Connection'}
                </button>
              </div>
            </div>
          </div>

          {testResults.clickup && (
            <TestResultCard result={testResults.clickup} type="clickup" />
          )}
        </div>
      )}

      {/* Central Dispatch */}
      {activeTab === 'cd' && (
        <div className="space-y-6">
          <div className="card">
            <div className="card-header">
              <h3 className="font-medium">Central Dispatch Configuration</h3>
            </div>
            <div className="card-body space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="form-label">Username</label>
                  <input
                    type="text"
                    value={settings.cd?.username || ''}
                    onChange={e => updateSettings('cd', 'username', e.target.value)}
                    className="form-input"
                  />
                </div>
                <div>
                  <label className="form-label">Password</label>
                  <input
                    type="password"
                    value={settings.cd?.password || ''}
                    onChange={e => updateSettings('cd', 'password', e.target.value)}
                    className="form-input"
                  />
                </div>
              </div>
              <div>
                <label className="form-label">Shipper ID</label>
                <input
                  type="text"
                  value={settings.cd?.shipper_id || ''}
                  onChange={e => updateSettings('cd', 'shipper_id', e.target.value)}
                  className="form-input"
                />
              </div>
              <div className="flex items-center space-x-3 pt-4 border-t border-gray-200">
                <button onClick={handleSaveCD} disabled={saving} className="btn btn-primary">
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button onClick={handleTestCD} disabled={testing} className="btn btn-secondary">
                  {testing ? 'Testing...' : 'Test Connection'}
                </button>
              </div>
            </div>
          </div>

          {testResults.cd && (
            <TestResultCard result={testResults.cd} type="cd" />
          )}
        </div>
      )}

      {/* Email Ingestion */}
      {activeTab === 'email' && (
        <div className="space-y-6">
          {/* Email Config */}
          <div className="card">
            <div className="card-header">
              <h3 className="font-medium">Email Server Configuration</h3>
            </div>
            <div className="card-body space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="form-label">IMAP Server</label>
                  <input
                    type="text"
                    value={settings.email?.imap_server || ''}
                    onChange={e => updateSettings('email', 'imap_server', e.target.value)}
                    className="form-input"
                    placeholder="imap.gmail.com"
                  />
                </div>
                <div>
                  <label className="form-label">Port</label>
                  <input
                    type="number"
                    value={settings.email?.imap_port || 993}
                    onChange={e => updateSettings('email', 'imap_port', parseInt(e.target.value))}
                    className="form-input"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="form-label">Email Address</label>
                  <input
                    type="email"
                    value={settings.email?.email_address || ''}
                    onChange={e => updateSettings('email', 'email_address', e.target.value)}
                    className="form-input"
                  />
                </div>
                <div>
                  <label className="form-label">Password / App Password</label>
                  <input
                    type="password"
                    value={settings.email?.password || ''}
                    onChange={e => updateSettings('email', 'password', e.target.value)}
                    className="form-input"
                  />
                </div>
              </div>
              <div className="flex items-center space-x-3 pt-4 border-t border-gray-200">
                <button onClick={handleSaveEmail} disabled={saving} className="btn btn-primary">
                  {saving ? 'Saving...' : 'Save'}
                </button>
                <button onClick={handleTestEmail} disabled={testing} className="btn btn-secondary">
                  {testing ? 'Testing...' : 'Test Connection'}
                </button>
              </div>
            </div>
          </div>

          {testResults.email && (
            <TestResultCard result={testResults.email} type="email" />
          )}

          {/* Email Rules */}
          <div className="card">
            <div className="card-header flex items-center justify-between">
              <div>
                <h3 className="font-medium">Processing Rules</h3>
                <p className="text-sm text-gray-500">Define how incoming emails are processed</p>
              </div>
              <button onClick={addEmailRule} className="btn btn-sm btn-secondary">
                Add Rule
              </button>
            </div>
            <div className="card-body">
              {emailRules.length === 0 ? (
                <p className="text-gray-500 text-center py-4">No rules configured. All emails with PDF attachments will be processed.</p>
              ) : (
                <div className="space-y-4">
                  {emailRules.map((rule, index) => (
                    <div key={rule.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-3">
                        <input
                          type="text"
                          value={rule.name}
                          onChange={e => updateEmailRule(index, 'name', e.target.value)}
                          className="form-input font-medium"
                          style={{ maxWidth: '200px' }}
                        />
                        <div className="flex items-center space-x-2">
                          <label className="flex items-center space-x-2 text-sm">
                            <input
                              type="checkbox"
                              checked={rule.enabled}
                              onChange={e => updateEmailRule(index, 'enabled', e.target.checked)}
                              className="rounded"
                            />
                            <span>Enabled</span>
                          </label>
                          <button
                            onClick={() => deleteEmailRule(index)}
                            className="text-red-600 hover:text-red-700 p-1"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                          <label className="text-xs text-gray-500">Condition</label>
                          <select
                            value={rule.condition_type}
                            onChange={e => updateEmailRule(index, 'condition_type', e.target.value)}
                            className="form-select text-sm"
                          >
                            <option value="subject_contains">Subject contains</option>
                            <option value="from_contains">From contains</option>
                            <option value="attachment_type">Attachment type</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">Value</label>
                          <input
                            type="text"
                            value={rule.condition_value}
                            onChange={e => updateEmailRule(index, 'condition_value', e.target.value)}
                            className="form-input text-sm"
                            placeholder="e.g., Copart, IAA"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500">Action</label>
                          <select
                            value={rule.action}
                            onChange={e => updateEmailRule(index, 'action', e.target.value)}
                            className="form-select text-sm"
                          >
                            <option value="process">Process</option>
                            <option value="ignore">Ignore</option>
                            <option value="forward">Forward</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  ))}
                  <button onClick={handleSaveEmailRules} disabled={saving} className="btn btn-primary">
                    {saving ? 'Saving...' : 'Save Rules'}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Email Activity */}
          <div className="card">
            <div className="card-header">
              <h3 className="font-medium">Recent Activity</h3>
            </div>
            <div className="card-body">
              {emailActivity.length === 0 ? (
                <p className="text-gray-500 text-center py-4">No email activity yet</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="table text-sm">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Subject</th>
                        <th>From</th>
                        <th>Status</th>
                        <th>Rule</th>
                      </tr>
                    </thead>
                    <tbody>
                      {emailActivity.slice(0, 10).map(activity => (
                        <tr key={activity.id}>
                          <td className="text-xs text-gray-500">
                            {new Date(activity.timestamp).toLocaleString()}
                          </td>
                          <td className="truncate max-w-[200px]">{activity.subject}</td>
                          <td className="text-xs">{activity.sender}</td>
                          <td>
                            <span className={`badge ${
                              activity.status === 'processed' ? 'badge-success' :
                              activity.status === 'failed' ? 'badge-error' : 'badge-gray'
                            }`}>
                              {activity.status}
                            </span>
                          </td>
                          <td className="text-xs text-gray-500">{activity.rule_matched || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Warehouses */}
      {activeTab === 'warehouses' && (
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <div>
              <h3 className="font-medium">Warehouse Locations</h3>
              <p className="text-sm text-gray-500 mt-1">Configure delivery destinations</p>
            </div>
            <button
              onClick={() => setShowNewWarehouse(true)}
              className="btn btn-primary"
            >
              Add Warehouse
            </button>
          </div>
          <div className="card-body">
            {/* New Warehouse Form */}
            {showNewWarehouse && (
              <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
                <h4 className="font-medium mb-4">New Warehouse</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  <div>
                    <label className="form-label">ID *</label>
                    <input
                      type="text"
                      value={newWarehouse.id}
                      onChange={e => setNewWarehouse({ ...newWarehouse, id: e.target.value })}
                      className="form-input"
                      placeholder="WH001"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="form-label">Name *</label>
                    <input
                      type="text"
                      value={newWarehouse.name}
                      onChange={e => setNewWarehouse({ ...newWarehouse, name: e.target.value })}
                      className="form-input"
                      placeholder="Main Warehouse"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                  <div className="md:col-span-2">
                    <label className="form-label">Address</label>
                    <input
                      type="text"
                      value={newWarehouse.address}
                      onChange={e => setNewWarehouse({ ...newWarehouse, address: e.target.value })}
                      className="form-input"
                      placeholder="123 Main St"
                    />
                  </div>
                  <div>
                    <label className="form-label">City</label>
                    <input
                      type="text"
                      value={newWarehouse.city}
                      onChange={e => setNewWarehouse({ ...newWarehouse, city: e.target.value })}
                      className="form-input"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="form-label">State</label>
                      <input
                        type="text"
                        value={newWarehouse.state}
                        onChange={e => setNewWarehouse({ ...newWarehouse, state: e.target.value })}
                        className="form-input"
                        maxLength={2}
                      />
                    </div>
                    <div>
                      <label className="form-label">ZIP</label>
                      <input
                        type="text"
                        value={newWarehouse.zip_code}
                        onChange={e => setNewWarehouse({ ...newWarehouse, zip_code: e.target.value })}
                        className="form-input"
                      />
                    </div>
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  <button onClick={handleAddWarehouse} disabled={saving} className="btn btn-primary">
                    {saving ? 'Adding...' : 'Add Warehouse'}
                  </button>
                  <button
                    onClick={() => {
                      setShowNewWarehouse(false)
                      setNewWarehouse({ id: '', name: '', address: '', city: '', state: '', zip_code: '' })
                    }}
                    className="btn btn-secondary"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Warehouse List */}
            {warehouses.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No warehouses configured</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Name</th>
                      <th>Address</th>
                      <th>City</th>
                      <th>State</th>
                      <th>ZIP</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {warehouses.map(wh => (
                      <tr key={wh.id}>
                        <td className="font-mono text-xs">{wh.id}</td>
                        <td className="font-medium">{wh.name}</td>
                        <td className="text-sm">{wh.address || '-'}</td>
                        <td>{wh.city || '-'}</td>
                        <td>{wh.state || '-'}</td>
                        <td>{wh.zip_code || '-'}</td>
                        <td>
                          <button
                            onClick={() => handleDeleteWarehouse(wh.id)}
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
              </div>
            )}
          </div>
        </div>
      )}

      {/* Audit Log */}
      {activeTab === 'audit' && (
        <div className="card">
          <div className="card-header flex items-center justify-between">
            <div>
              <h3 className="font-medium">Integration Audit Log</h3>
              <p className="text-sm text-gray-500 mt-1">Track all integration actions and their results</p>
            </div>
            <button onClick={loadAuditLog} className="btn btn-sm btn-secondary">
              Refresh
            </button>
          </div>
          <div className="card-body">
            {auditLog.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No audit log entries yet</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="table text-sm">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Integration</th>
                      <th>Action</th>
                      <th>Status</th>
                      <th>Duration</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLog.map(entry => (
                      <tr key={entry.id}>
                        <td className="text-xs text-gray-500 whitespace-nowrap">
                          {new Date(entry.timestamp).toLocaleString()}
                        </td>
                        <td>
                          <span className="badge badge-info">{entry.integration}</span>
                        </td>
                        <td>{entry.action}</td>
                        <td>
                          <span className={`badge ${
                            entry.status === 'success' ? 'badge-success' :
                            entry.status === 'failed' ? 'badge-error' : 'badge-warning'
                          }`}>
                            {entry.status}
                          </span>
                        </td>
                        <td className="text-xs text-gray-500">
                          {entry.duration_ms ? `${entry.duration_ms}ms` : '-'}
                        </td>
                        <td className="text-xs">
                          {entry.error ? (
                            <span className="text-red-600">{entry.error}</span>
                          ) : entry.details ? (
                            <span className="text-gray-500">{JSON.stringify(entry.details).substring(0, 50)}...</span>
                          ) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Test Result Card Component
function TestResultCard({ result, type }) {
  if (!result) return null

  return (
    <div className={`card ${result.success ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
      <div className="card-body">
        <div className="flex items-start space-x-3">
          {result.success ? (
            <svg className="w-6 h-6 text-green-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ) : (
            <svg className="w-6 h-6 text-red-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
          <div className="flex-1">
            <h4 className={`font-medium ${result.success ? 'text-green-800' : 'text-red-800'}`}>
              {result.message}
            </h4>

            {result.error && (
              <p className="text-red-600 text-sm mt-1">{result.error}</p>
            )}

            {/* Type-specific details */}
            {type === 'clickup' && result.success && (
              <div className="mt-3 text-sm">
                <p><strong>User:</strong> {result.user_name} ({result.user_email})</p>
                {result.workspaces?.length > 0 && (
                  <p><strong>Workspaces:</strong> {result.workspaces.map(w => w.name).join(', ')}</p>
                )}
                {result.lists?.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-primary-600">View available lists ({result.lists.length})</summary>
                    <ul className="mt-2 space-y-1 text-xs">
                      {result.lists.map(l => (
                        <li key={l.id} className="font-mono">{l.id} - {l.name} ({l.space}/{l.folder})</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}

            {type === 'sheets' && result.success && (
              <div className="mt-3 text-sm">
                <p><strong>Spreadsheet:</strong> {result.spreadsheet_title}</p>
                <p><strong>Sheets:</strong> {result.sheet_names?.join(', ')}</p>
                <p><strong>Rows:</strong> {result.row_count}</p>
                <p><strong>Write Access:</strong> {result.has_write_access ? 'Yes' : 'No'}</p>
              </div>
            )}

            {type === 'cd' && result.success && (
              <div className="mt-3 text-sm">
                <p><strong>Shipper:</strong> {result.shipper_name || 'Connected'}</p>
                <p><strong>Marketplace:</strong> {result.marketplace_access ? 'Accessible' : 'Limited'}</p>
              </div>
            )}

            {type === 'email' && result.success && (
              <div className="mt-3 text-sm">
                <p><strong>Mailboxes:</strong> {result.mailbox_count}</p>
                <p><strong>Unread Messages:</strong> {result.unread_count}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Settings
