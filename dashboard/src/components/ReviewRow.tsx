import { Link } from 'react-router-dom'
import type { PRReviewListItem, RepoListItem } from '../types'
import SeverityBadge from './SeverityBadge'

interface Props {
  review: PRReviewListItem
  repo?: RepoListItem
  repoId?: number
}

export default function ReviewRow({ review, repo, repoId }: Props) {
  const rid = repoId ?? repo?.id ?? 0
  const date = review.created_at
    ? new Date(review.created_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : '-'

  return (
    <Link
      to={`/repos/${rid}/reviews/${review.id}`}
      className="flex items-center justify-between px-5 py-4 hover:bg-white/[0.015] transition-colors border-b border-border-subtle last:border-b-0 group"
    >
      <div className="flex items-center gap-4 min-w-0">
        <div className="w-9 h-9 rounded-lg bg-surface-3 border border-border-subtle flex items-center justify-center shrink-0">
          <svg className="w-4 h-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 3.75H6A2.25 2.25 0 003.75 6v1.5M16.5 3.75H18A2.25 2.25 0 0120.25 6v1.5m0 9V18A2.25 2.25 0 0118 20.25h-1.5m-9 0H6A2.25 2.25 0 013.75 18v-1.5" />
          </svg>
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {repo && (
              <span className="text-text-muted text-xs font-mono">{repo.full_name}</span>
            )}
            <span className="text-white font-medium text-sm">
              #{review.pr_number}
            </span>
          </div>
          <p className="text-text-secondary text-sm truncate max-w-[400px]">
            {review.title || 'Untitled'}
          </p>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-text-muted text-xs">by {review.author || 'unknown'}</span>
            <span className="text-text-muted text-xs">{date}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {review.findings_count > 0 && (
          <span className="text-text-muted text-xs font-mono">
            {review.findings_count} findings
          </span>
        )}
        {review.critical_count > 0 && (
          <span className="text-accent-red text-xs font-mono font-medium">
            {review.critical_count} critical
          </span>
        )}
        <SeverityBadge severity={review.status} />
        <svg className="w-4 h-4 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
      </div>
    </Link>
  )
}
