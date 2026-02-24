import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type { PRReviewListItem, RepoListItem } from '../types'
import ReviewRow from '../components/ReviewRow'
import EmptyState from '../components/EmptyState'

export default function RepoDetail() {
  const { repoId } = useParams()
  const [reviews, setReviews] = useState<PRReviewListItem[]>([])
  const [repo, setRepo] = useState<RepoListItem | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!repoId) return
    const id = Number(repoId)

    async function load() {
      try {
        const [repos, revs] = await Promise.all([
          api.getRepos(),
          api.getRepoReviews(id),
        ])
        setRepo(repos.find((r) => r.id === id) ?? null)
        setReviews(revs)
      } catch {
        // API not running
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [repoId])

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="h-4 w-32 bg-surface-2 rounded mb-3 animate-pulse" />
        <div className="h-7 w-64 bg-surface-3 rounded-lg mb-8 animate-pulse" />
        <div className="glass-card h-64 animate-pulse" />
      </div>
    )
  }

  const totalFindings = reviews.reduce((s, r) => s + r.findings_count, 0)
  const totalCritical = reviews.reduce((s, r) => s + r.critical_count, 0)

  return (
    <div className="animate-fade-in">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-text-muted text-xs mb-3">
        <Link to="/repos" className="hover:text-white transition-colors">
          Repositories
        </Link>
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
        <span className="text-text-secondary">{repo?.full_name ?? `Repo #${repoId}`}</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="font-display text-2xl font-bold text-white tracking-tight">
            {repo?.full_name ?? `Repository #${repoId}`}
          </h2>
          <div className="flex items-center gap-4 mt-2">
            <span className="text-text-muted text-sm font-mono">{reviews.length} PRs</span>
            <span className="text-text-muted text-sm font-mono">{totalFindings} findings</span>
            {totalCritical > 0 && (
              <span className="text-accent-red text-sm font-mono">{totalCritical} critical</span>
            )}
          </div>
        </div>
        {repo?.is_active && (
          <span className="flex items-center gap-1.5 text-accent-emerald text-xs font-medium px-3 py-1.5 rounded-full bg-accent-emerald/10 border border-accent-emerald/20">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-emerald animate-glow-pulse" />
            Active
          </span>
        )}
      </div>

      {/* Reviews Table */}
      <div className="glass-card">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
          <h3 className="font-display text-base font-semibold text-white">
            Pull Request Reviews
          </h3>
        </div>
        {reviews.length > 0 ? (
          <div>
            {reviews.map((r) => (
              <ReviewRow key={r.id} review={r} repoId={Number(repoId)} />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No reviews yet"
            description="Reviews will appear here when the bot processes pull requests for this repository."
          />
        )}
      </div>
    </div>
  )
}
