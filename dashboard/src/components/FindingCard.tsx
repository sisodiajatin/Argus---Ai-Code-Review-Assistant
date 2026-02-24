import { useState } from 'react'
import type { FindingItem } from '../types'
import { api } from '../api/client'
import SeverityBadge from './SeverityBadge'

interface Props {
  finding: FindingItem
}

const borderColors: Record<string, string> = {
  critical: 'border-l-accent-red',
  warning: 'border-l-accent-amber',
  suggestion: 'border-l-accent-cyan',
}

export default function FindingCard({ finding }: Props) {
  const borderColor = borderColors[finding.severity] || 'border-l-border'
  const [feedback, setFeedback] = useState<string | null>(finding.feedback)
  const [submitting, setSubmitting] = useState(false)

  const handleFeedback = async (value: 'helpful' | 'not_helpful') => {
    if (submitting) return
    setSubmitting(true)
    try {
      await api.submitFeedback(finding.id, value)
      setFeedback(value)
    } catch {
      // Silently fail — don't break the UI for feedback
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={`glass-card p-5 border-l-[3px] ${borderColor}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <SeverityBadge severity={finding.severity} />
          <span className="text-[11px] px-2 py-0.5 rounded-md bg-surface-3 text-text-muted border border-border-subtle font-mono">
            {finding.category}
          </span>
          <span className="text-white font-medium text-sm">{finding.title}</span>
        </div>

        {/* Feedback buttons */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => handleFeedback('helpful')}
            disabled={submitting || feedback === 'helpful'}
            title="Helpful"
            className={`p-1.5 rounded-lg transition-all ${
              feedback === 'helpful'
                ? 'bg-accent-emerald/20 text-accent-emerald'
                : 'text-text-muted hover:text-accent-emerald hover:bg-accent-emerald/10'
            } disabled:cursor-default`}
          >
            <svg className="w-4 h-4" fill={feedback === 'helpful' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.633 10.25c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 0 1 2.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 0 0 .322-1.672V3a.75.75 0 0 1 .75-.75 2.25 2.25 0 0 1 2.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282m0 0h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 0 1-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 0 0-1.423-.23H5.904m7.72-5.772H19.6" />
            </svg>
          </button>
          <button
            onClick={() => handleFeedback('not_helpful')}
            disabled={submitting || feedback === 'not_helpful'}
            title="Not helpful"
            className={`p-1.5 rounded-lg transition-all ${
              feedback === 'not_helpful'
                ? 'bg-accent-red/20 text-accent-red'
                : 'text-text-muted hover:text-accent-red hover:bg-accent-red/10'
            } disabled:cursor-default`}
          >
            <svg className="w-4 h-4" fill={feedback === 'not_helpful' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7.498 15.25H4.372c-1.026 0-1.945-.694-2.054-1.715A12.137 12.137 0 0 1 2.25 12c0-2.848.992-5.464 2.649-7.521C5.287 3.997 5.886 3.75 6.504 3.75h4.016c.483 0 .964.078 1.423.23l3.114 1.04a4.501 4.501 0 0 0 1.423.23h1.294M7.498 15.25c.618 0 .991.724.725 1.282A7.471 7.471 0 0 0 7.5 19.5a2.25 2.25 0 0 0 2.25 2.25.75.75 0 0 0 .75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 0 0 2.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384" />
            </svg>
          </button>
        </div>
      </div>

      {/* File path */}
      <div className="mb-3">
        <code className="text-xs font-mono text-accent-violet-light bg-accent-violet/5 px-2 py-0.5 rounded">
          {finding.file_path}
          {finding.line_start && `:${finding.line_start}`}
          {finding.line_end && finding.line_end !== finding.line_start && `-${finding.line_end}`}
        </code>
      </div>

      {/* Description */}
      <p className="text-text-secondary text-sm leading-relaxed">{finding.description}</p>

      {/* Suggested fix */}
      {finding.suggested_fix && (
        <div className="mt-4 p-3.5 bg-surface-0/60 rounded-xl border border-accent-emerald/10">
          <div className="flex items-center gap-1.5 mb-2">
            <svg className="w-3.5 h-3.5 text-accent-emerald" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5.002 5.002 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span className="text-accent-emerald text-[11px] font-semibold uppercase tracking-wider">
              Suggested Fix
            </span>
          </div>
          <pre className="text-text-secondary text-xs font-mono whitespace-pre-wrap leading-relaxed">
            {finding.suggested_fix}
          </pre>
        </div>
      )}

      {/* Feedback confirmation */}
      {feedback && (
        <div className={`mt-3 text-[11px] flex items-center gap-1.5 ${
          feedback === 'helpful' ? 'text-accent-emerald' : 'text-accent-red'
        }`}>
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
          </svg>
          Marked as {feedback === 'helpful' ? 'helpful' : 'not helpful'}
        </div>
      )}
    </div>
  )
}
