import { useState, useEffect } from 'react'
import api from '../api'

function Settings() {
  const [activeTab, setActiveTab] = useState('targets')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)

  // Data states
  const [targets, setTargets] = useState([])
  const [sheetsConfig, setSheetsConfig] = useState({})
  const [clickupConfig, setClickupConfig] = useState({})
  const [cdConfig, setCdConfig] = useState({})
  const [emailConfig, setEmailConfig] = useState({})
  const [warehouses, setWarehouses] = useState([])

  useEffect(() => {
    loadSettings()
  }, [])

  async function loadSettings() {
    setLoading(true)
    try {
      const [targetsData, sheetsData, clickupData, cdData, emailData, warehousesData] = await Promise.all([
        api.getExportTargets().catch(() => ({ targets: [] })),
        api.getSheetsConfig().catch(() => ({})),
        api.getClickUpConfig().catch(() => ({})),
        api.getCDConfig().catch(() => ({})),
        api.getEmailConfig().catch(() => ({})),
        api.getWarehouses().catch(() => ({ warehouses: [] })),
      ])
      setTargets(targetsData.targets || [])
      setSheetsConfig(sheetsData)
      setClickupConfig(clickupData)
      setCdConfig(cdData)
      setEmailConfig(emailData)
      setWarehouses(warehousesData.warehouses || [])
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setLoading(false)
    }
  }

  function showMessage(type, text) {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 5000)
  }

  async function handleSaveTargets() {
    setSaving(true)
    try {
      await api.updateExportTargets(targets)
      showMessage('success', 'Export targets saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleTestSheets() {
    setSaving(true)
    try {
      const result = await api.testSheets()
      if (result.success) {
        showMessage('success', 'Google Sheets connection successful!')
      } else {
        showMessage('error', result.error || 'Connection failed')
      }
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveSheets() {
    setSaving(true)
    try {
      await api.updateSheetsConfig(sheetsConfig)
      showMessage('success', 'Sheets settings saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveClickUp() {
    setSaving(true)
    try {
      await api.updateClickUpConfig(clickupConfig)
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
      await api.updateCDConfig(cdConfig)
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
      await api.updateEmailConfig(emailConfig)
      showMessage('success', 'Email settings saved')
    } catch (err) {
      showMessage('error', err.message)
    } finally {
      setSaving(false)
    }
  }

  function toggleTarget(target) {
    if (targets.includes(target)) {
      setTargets(targets.filter(t => t !== target))
    } else {
      setTargets([...targets, target])
    }
  }

  const tabs = [
    { id: 'targets', label: 'Export Targets' },
    { id: 'sheets', label: 'Google Sheets' },
    { id: 'clickup', label: 'ClickUp' },
    { id: 'cd', label: 'Central Dispatch' },
    { id: 'email', label: 'Email' },
    { id: 'warehouses', label: 'Warehouses' },
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
        <div className={`mb-6 p-4 rounded-lg ${
          message.type === 'error' ? 'bg-red-50 border border-red-200 text-red-700' :
          'bg-green-50 border border-green-200 text-green-700'
        }`}>
          {message.text}
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="flex space-x-4">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
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
            <label className="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                checked={targets.includes('sheets')}
                onChange={() => toggleTarget('sheets')}
                className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              />
              <div>
                <span className="font-medium">Google Sheets</span>
                <p className="text-sm text-gray-500">Export to Google Spreadsheet</p>
              </div>
            </label>
            <label className="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                checked={targets.includes('clickup')}
                onChange={() => toggleTarget('clickup')}
                className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              />
              <div>
                <span className="font-medium">ClickUp</span>
                <p className="text-sm text-gray-500">Create tasks in ClickUp</p>
              </div>
            </label>
            <label className="flex items-center space-x-3 cursor-pointer">
              <input
                type="checkbox"
                checked={targets.includes('cd')}
                onChange={() => toggleTarget('cd')}
                className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              />
              <div>
                <span className="font-medium">Central Dispatch</span>
                <p className="text-sm text-gray-500">Post listings to CD marketplace</p>
              </div>
            </label>
            <div className="pt-4 border-t border-gray-200">
              <button onClick={handleSaveTargets} disabled={saving} className="btn btn-primary">
                {saving ? 'Saving...' : 'Save Targets'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Google Sheets */}
      {activeTab === 'sheets' && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-medium">Google Sheets Configuration</h3>
          </div>
          <div className="card-body space-y-4">
            <div>
              <label className="form-label">Spreadsheet ID</label>
              <input
                type="text"
                value={sheetsConfig.spreadsheet_id || ''}
                onChange={e => setSheetsConfig({ ...sheetsConfig, spreadsheet_id: e.target.value })}
                className="form-input"
                placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
              />
              <p className="text-xs text-gray-500 mt-1">From your Google Sheets URL: /d/[SPREADSHEET_ID]/edit</p>
            </div>
            <div>
              <label className="form-label">Sheet Name</label>
              <input
                type="text"
                value={sheetsConfig.sheet_name || ''}
                onChange={e => setSheetsConfig({ ...sheetsConfig, sheet_name: e.target.value })}
                className="form-input"
                placeholder="Sheet1"
              />
            </div>
            <div>
              <label className="form-label">Credentials File</label>
              <input
                type="text"
                value={sheetsConfig.credentials_file || ''}
                onChange={e => setSheetsConfig({ ...sheetsConfig, credentials_file: e.target.value })}
                className="form-input"
                placeholder="config/service_account.json"
              />
              <p className="text-xs text-gray-500 mt-1">Path to your Google Service Account JSON file</p>
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="sheets_enabled"
                checked={sheetsConfig.enabled || false}
                onChange={e => setSheetsConfig({ ...sheetsConfig, enabled: e.target.checked })}
                className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              />
              <label htmlFor="sheets_enabled" className="text-sm font-medium">Enabled</label>
            </div>
            <div className="pt-4 border-t border-gray-200 flex space-x-3">
              <button onClick={handleSaveSheets} disabled={saving} className="btn btn-primary">
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button onClick={handleTestSheets} disabled={saving} className="btn btn-secondary">
                {saving ? 'Testing...' : 'Test Connection'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ClickUp */}
      {activeTab === 'clickup' && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-medium">ClickUp Configuration</h3>
          </div>
          <div className="card-body space-y-4">
            <div>
              <label className="form-label">API Token</label>
              <input
                type="password"
                value={clickupConfig.token || ''}
                onChange={e => setClickupConfig({ ...clickupConfig, token: e.target.value })}
                className="form-input"
                placeholder="pk_xxxxx"
              />
            </div>
            <div>
              <label className="form-label">List ID</label>
              <input
                type="text"
                value={clickupConfig.list_id || ''}
                onChange={e => setClickupConfig({ ...clickupConfig, list_id: e.target.value })}
                className="form-input"
                placeholder="901234567"
              />
            </div>
            <div className="pt-4 border-t border-gray-200">
              <button onClick={handleSaveClickUp} disabled={saving} className="btn btn-primary">
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Central Dispatch */}
      {activeTab === 'cd' && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-medium">Central Dispatch Configuration</h3>
          </div>
          <div className="card-body space-y-4">
            <div>
              <label className="form-label">Client ID</label>
              <input
                type="text"
                value={cdConfig.client_id || ''}
                onChange={e => setCdConfig({ ...cdConfig, client_id: e.target.value })}
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">Client Secret</label>
              <input
                type="password"
                value={cdConfig.client_secret || ''}
                onChange={e => setCdConfig({ ...cdConfig, client_secret: e.target.value })}
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">Marketplace ID</label>
              <input
                type="text"
                value={cdConfig.marketplace_id || ''}
                onChange={e => setCdConfig({ ...cdConfig, marketplace_id: e.target.value })}
                className="form-input"
              />
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="cd_enabled"
                checked={cdConfig.enabled || false}
                onChange={e => setCdConfig({ ...cdConfig, enabled: e.target.checked })}
                className="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
              />
              <label htmlFor="cd_enabled" className="text-sm font-medium">Enabled</label>
            </div>
            <div className="pt-4 border-t border-gray-200">
              <button onClick={handleSaveCD} disabled={saving} className="btn btn-primary">
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Email */}
      {activeTab === 'email' && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-medium">Email Configuration</h3>
          </div>
          <div className="card-body space-y-4">
            <div>
              <label className="form-label">Provider</label>
              <select
                value={emailConfig.provider || 'imap'}
                onChange={e => setEmailConfig({ ...emailConfig, provider: e.target.value })}
                className="form-select"
              >
                <option value="imap">IMAP</option>
                <option value="graph">Microsoft Graph</option>
              </select>
            </div>
            <div>
              <label className="form-label">Email Address</label>
              <input
                type="email"
                value={emailConfig.address || ''}
                onChange={e => setEmailConfig({ ...emailConfig, address: e.target.value })}
                className="form-input"
              />
            </div>
            {emailConfig.provider === 'imap' && (
              <>
                <div>
                  <label className="form-label">IMAP Server</label>
                  <input
                    type="text"
                    value={emailConfig.imap_server || ''}
                    onChange={e => setEmailConfig({ ...emailConfig, imap_server: e.target.value })}
                    className="form-input"
                    placeholder="imap.gmail.com"
                  />
                </div>
                <div>
                  <label className="form-label">Password / App Password</label>
                  <input
                    type="password"
                    value={emailConfig.password || ''}
                    onChange={e => setEmailConfig({ ...emailConfig, password: e.target.value })}
                    className="form-input"
                  />
                </div>
              </>
            )}
            <div className="pt-4 border-t border-gray-200">
              <button onClick={handleSaveEmail} disabled={saving} className="btn btn-primary">
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Warehouses */}
      {activeTab === 'warehouses' && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-medium">Warehouse Locations</h3>
            <p className="text-sm text-gray-500 mt-1">Configured in warehouses.yaml</p>
          </div>
          <div className="card-body">
            {warehouses.length === 0 ? (
              <p className="text-gray-500">No warehouses configured</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>City</th>
                    <th>State</th>
                    <th>ZIP</th>
                  </tr>
                </thead>
                <tbody>
                  {warehouses.map(wh => (
                    <tr key={wh.id}>
                      <td className="font-mono text-xs">{wh.id}</td>
                      <td>{wh.name}</td>
                      <td>{wh.city}</td>
                      <td>{wh.state}</td>
                      <td>{wh.zip}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default Settings
