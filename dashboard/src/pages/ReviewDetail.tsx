import { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ReviewDetail as ReviewDetailType } from '../types'
import FindingCard from '../components/FindingCard'
import SeverityBadge from '../components/SeverityBadge'
import EmptyState from '../components/EmptyState'

export default function ReviewDetail() {
  const { repoId, prId } = useParams()
  const [review, setReview] = useState<ReviewDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [reReviewing, setReReviewing] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchReview = useCallback(() => {
    if (!prId) return
    api.getReviewDetail(Number(prId))
      .then((data) => {
        setReview(data)
        // Stop polling when review is complete
        if (data.pr.status !== 'reviewing' && data.pr.status !== 'pending') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current)
            pollingRef.current = null
          }
          setReReviewing(false)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [prId])

  useEffect(() => {
    fetchReview()
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [fetchReview])

  // Start polling when review is in progress
  useEffect(() => {
    if (review && (review.pr.status === 'reviewing' || review.pr.status === 'pending')) {
      if (!pollingRef.current) {
        pollingRef.current = setInterval(fetchReview, 3000)
      }
    }
  }, [review?.pr.status, fetchReview])

  const handleReReview = async () => {
    if (!prId) return
    setReReviewing(true)
    try {
      await api.reReview(Number(prId))
      fetchReview()
      if (!pollingRef.current) {
        pollingRef.current = setInterval(fetchReview, 3000)
      }
    } catch {
      setReReviewing(false)
    }
  }

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="h-4 w-32 bg-surface-2 rounded mb-3 animate-pulse" />
        <div className="h-7 w-96 bg-surface-3 rounded-lg mb-4 animate-pulse" />
        <div className="glass-card h-48 mb-6 animate-pulse" />
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="glass-card h-32 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (!review) {
    return (
      <EmptyState
        title="Review not found"
        description="This review may have been removed or the ID is invalid."
      />
    )
  }

  const { pr, findings } = review
  const isReviewing = pr.status === 'reviewing' || pr.status === 'pending'
  const assessmentMap: Record<string, { label: string; severity: string }> = {
    needs_changes: { label: 'Needs Changes', severity: 'critical' },
    minor_issues: { label: 'Minor Issues', severity: 'warning' },
    approved: { label: 'Approved', severity: 'completed' },
  }
  const assessment = assessmentMap[review.overall_assessment ?? '']

  const criticalCount = findings.filter((f) => f.severity === 'critical').length
  const warningCount = findings.filter((f) => f.severity === 'warning').length
  const suggestionCount = findings.filter((f) => f.severity === 'suggestion').length

  return (
    <div className="animate-fade-in">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-text-muted text-xs mb-3">
        <Link to="/repos" className="hover:text-white transition-colors">Repositories</Link>
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
        <Link to={`/repos/${repoId}`} className="hover:text-white transition-colors">
          Repo #{repoId}
        </Link>
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
        <span className="text-text-secondary">PR #{pr.pr_number}</span>
      </div>

      {/* Header with Re-Review button */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-white tracking-tight">
            PR #{pr.pr_number}: {pr.title || 'Untitled'}
          </h2>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="text-text-muted text-sm">by {pr.author || 'unknown'}</span>
            <SeverityBadge severity={pr.status} />
            {pr.created_at && (
              <span className="text-text-muted text-xs font-mono">
                {new Date(pr.created_at).toLocaleDateString('en-US', {
                  month: 'short', day: 'numeric', year: 'numeric',
                })}
              </span>
            )}
          </div>
        </div>
        {!isReviewing && (
          <button
            onClick={handleReReview}
            disabled={reReviewing}
            className="px-4 py-2 bg-accent-violet/20 hover:bg-accent-violet/30 border border-accent-violet/30 rounded-xl text-sm text-accent-violet font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
            </svg>
            {reReviewing ? 'Starting...' : 'Re-Review'}
          </button>
        )}
      </div>

      {/* Reviewing Progress Indicator */}
      {isReviewing && (
        <div className="glass-card p-6 mb-6 border-accent-violet/20">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full border-2 border-accent-violet/30 border-t-accent-violet animate-spin" />
            <div>
              <p className="text-white font-medium">Argus is reviewing...</p>
              <p className="text-text-muted text-sm mt-0.5">Analyzing code changes. This usually takes 10-30 seconds.</p>
            </div>
          </div>
          <div className="mt-4 h-1 bg-surface-2 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-accent-violet to-accent-cyan rounded-full animate-pulse" style={{ width: '60%' }} />
          </div>
        </div>
      )}

      {/* Summary Card */}
      {!isReviewing && review.summary_text && (
        <div className="glass-card p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-base font-semibold text-white">Review Summary</h3>
            {assessment && <SeverityBadge severity={assessment.severity} size="md" />}
          </div>

          {/* Severity breakdown bar */}
          <div className="flex items-center gap-4 mb-4">
            {criticalCount > 0 && (
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-accent-red" />
                <span className="text-xs text-text-secondary">{criticalCount} critical</span>
              </div>
            )}
            {warningCount > 0 && (
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-accent-amber" />
                <span className="text-xs text-text-secondary">{warningCount} warning</span>
              </div>
            )}
            {suggestionCount > 0 && (
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-accent-cyan" />
                <span className="text-xs text-text-secondary">{suggestionCount} suggestion</span>
              </div>
            )}
          </div>

          {/* Metadata */}
          <div className="flex items-center gap-4 mb-4 text-text-muted text-xs font-mono">
            <span>{review.tokens_used.toLocaleString()} tokens</span>
            <span>{Math.round(review.processing_time_ms)}ms</span>
            {review.model_used && <span>{review.model_used}</span>}
          </div>

          <p className="text-text-secondary text-sm leading-relaxed whitespace-pre-wrap">
            {review.summary_text}
          </p>
        </div>
      )}

      {/* Findings */}
      {!isReviewing && (
        <>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-display text-base font-semibold text-white">
              Findings ({findings.length})
            </h3>
          </div>

          {findings.length > 0 ? (
            <div className="space-y-3 stagger">
              {findings.map((f) => (
                <FindingCard key={f.id} finding={f} />
              ))}
            </div>
          ) : (
            <div className="glass-card p-12 text-center">
              <div className="text-accent-emerald mb-2">
                <svg className="w-10 h-10 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-accent-emerald font-display font-semibold">No issues found!</p>
              <p className="text-text-muted text-sm mt-1">The code changes look good.</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
