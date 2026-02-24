import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { SettingsResponse } from '../types'

export default function Settings() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState('')

  useEffect(() => {
    api.getSettings()
      .then(setSettings)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    setCopied(label)
    setTimeout(() => setCopied(''), 2000)
  }

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="h-7 w-48 bg-surface-3 rounded-lg mb-6 animate-pulse" />
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="glass-card h-32 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (!settings) {
    return (
      <div className="glass-card p-12 text-center">
        <p className="text-text-muted">Failed to load settings.</p>
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <h2 className="font-display text-2xl font-bold text-white tracking-tight mb-6">
        Settings
      </h2>

      {/* AI Configuration */}
      <div className="glass-card p-6 mb-4">
        <h3 className="font-display text-base font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-accent-violet" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
          </svg>
          AI Configuration
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wide">Model</label>
            <div className="mt-1 px-3 py-2 bg-surface-2 rounded-lg border border-border text-sm text-text-secondary font-mono">
              {settings.ai_model}
            </div>
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wide">API Base URL</label>
            <div className="mt-1 px-3 py-2 bg-surface-2 rounded-lg border border-border text-sm text-text-secondary font-mono truncate">
              {settings.ai_base_url}
            </div>
          </div>
        </div>
        <p className="text-[11px] text-text-muted mt-3">
          To change AI settings, update the <code className="text-accent-cyan">.env</code> file and restart the server.
        </p>
      </div>

      {/* Webhook URL */}
      <div className="glass-card p-6 mb-4">
        <h3 className="font-display text-base font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-accent-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m9.914-3.764a4.5 4.5 0 010 6.364l-4.5 4.5a4.5 4.5 0 01-6.364 0l-1.757-1.757" />
          </svg>
          Webhook URL
        </h3>
        <div className="flex items-center gap-2">
          <div className="flex-1 px-3 py-2 bg-surface-2 rounded-lg border border-border text-sm text-text-secondary font-mono truncate">
            {settings.webhook_url}
          </div>
          <button
            onClick={() => copyToClipboard(settings.webhook_url, 'webhook')}
            className="px-3 py-2 bg-surface-3 hover:bg-surface-2 border border-border rounded-lg text-xs text-text-secondary hover:text-white transition-colors"
          >
            {copied === 'webhook' ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p className="text-[11px] text-text-muted mt-3">
          Paste this URL in your GitHub App webhook settings. For public access, use ngrok or deploy to a cloud provider.
        </p>
      </div>

      {/* Review Limits */}
      <div className="glass-card p-6 mb-4">
        <h3 className="font-display text-base font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-accent-amber" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
          </svg>
          Review Limits
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wide">Max Files Per Review</label>
            <div className="mt-1 px-3 py-2 bg-surface-2 rounded-lg border border-border text-sm text-text-secondary font-mono">
              {settings.max_files_per_review}
            </div>
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wide">Chunk Token Limit</label>
            <div className="mt-1 px-3 py-2 bg-surface-2 rounded-lg border border-border text-sm text-text-secondary font-mono">
              {settings.chunk_token_limit.toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {/* Server Info */}
      <div className="glass-card p-6">
        <h3 className="font-display text-base font-semibold text-white mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-accent-emerald" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 01-3-3m3 3a3 3 0 100 6h13.5a3 3 0 100-6m-16.5-3a3 3 0 013-3h13.5a3 3 0 013 3m-19.5 0a4.5 4.5 0 01.9-2.7L5.737 5.1a3.375 3.375 0 012.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 01.9 2.7m0 0a3 3 0 01-3 3m0 3h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008zm-3 6h.008v.008h-.008v-.008zm0-6h.008v.008h-.008v-.008z" />
          </svg>
          Server
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wide">Host</label>
            <div className="mt-1 px-3 py-2 bg-surface-2 rounded-lg border border-border text-sm text-text-secondary font-mono">
              {settings.app_host}
            </div>
          </div>
          <div>
            <label className="text-xs text-text-muted uppercase tracking-wide">Port</label>
            <div className="mt-1 px-3 py-2 bg-surface-2 rounded-lg border border-border text-sm text-text-secondary font-mono">
              {settings.app_port}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
