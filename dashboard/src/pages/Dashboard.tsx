import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DashboardStats, RepoListItem, PRReviewListItem } from '../types'
import StatCard from '../components/StatCard'
import RepoCard from '../components/RepoCard'
import ReviewRow from '../components/ReviewRow'
import EmptyState from '../components/EmptyState'

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [repos, setRepos] = useState<RepoListItem[]>([])
  const [reviews, setReviews] = useState<{ pr: PRReviewListItem; repo?: RepoListItem }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [s, r] = await Promise.all([api.getStats(), api.getRepos()])
        setStats(s)
        setRepos(r)

        // Load recent reviews from all repos
        const allReviews: { pr: PRReviewListItem; repo?: RepoListItem }[] = []
        for (const repo of r.slice(0, 5)) {
          const prs = await api.getRepoReviews(repo.id)
          for (const pr of prs.slice(0, 3)) {
            allReviews.push({ pr, repo })
          }
        }
        allReviews.sort((a, b) => {
          const da = a.pr.created_at ? new Date(a.pr.created_at).getTime() : 0
          const db = b.pr.created_at ? new Date(b.pr.created_at).getTime() : 0
          return db - da
        })
        setReviews(allReviews.slice(0, 10))
      } catch {
        // API may not be running
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return <LoadingSkeleton />

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="mb-8">
        <h2 className="font-display text-2xl font-bold text-white tracking-tight">
          Dashboard
        </h2>
        <p className="text-text-muted text-sm mt-1">
          Overview of your AI-powered code review activity
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-8 stagger">
        <StatCard
          label="Repositories"
          value={stats?.total_repos ?? 0}
          accent="violet"
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
            </svg>
          }
        />
        <StatCard
          label="PRs Reviewed"
          value={stats?.total_prs_reviewed ?? 0}
          accent="emerald"
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          subtitle={stats?.avg_processing_time_ms ? `avg ${Math.round(stats.avg_processing_time_ms)}ms` : undefined}
        />
        <StatCard
          label="Total Findings"
          value={stats?.total_findings ?? 0}
          accent="cyan"
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
          }
          subtitle={stats?.total_tokens_used ? `${(stats.total_tokens_used / 1000).toFixed(1)}k tokens` : undefined}
        />
        <StatCard
          label="Critical Issues"
          value={stats?.critical_findings ?? 0}
          accent="red"
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          }
        />
      </div>

      {/* Top Repositories */}
      {repos.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-lg font-semibold text-white">
              Top Repositories
            </h3>
            <span className="text-text-muted text-xs px-2.5 py-1 rounded-full bg-surface-3 border border-border-subtle">
              {repos.length} Repos
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 stagger">
            {repos.slice(0, 3).map((repo) => (
              <RepoCard key={repo.id} repo={repo} />
            ))}
          </div>
        </div>
      )}

      {/* Promo Card + Recent Reviews */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Recent Reviews */}
        <div className="xl:col-span-3">
          <div className="glass-card">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
              <h3 className="font-display text-base font-semibold text-white">
                Recent Reviews
              </h3>
              <div className="flex items-center gap-2 text-text-muted text-xs">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Latest activity
              </div>
            </div>
            {reviews.length > 0 ? (
              <div>
                {reviews.map((r) => (
                  <ReviewRow
                    key={r.pr.id}
                    review={r.pr}
                    repo={r.repo}
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                title="No reviews yet"
                description="Reviews will appear here when your bot processes pull requests."
              />
            )}
          </div>
        </div>

        {/* Quick Actions Card */}
        <div className="xl:col-span-1">
          <div className="glass-card p-5 h-full">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-accent-violet to-accent-cyan flex items-center justify-center">
                <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                </svg>
              </div>
              <h3 className="font-display text-sm font-semibold text-white">
                Quick Actions
              </h3>
            </div>

            <div className="space-y-3">
              <a
                href={`${import.meta.env.VITE_API_URL || ''}/api/health`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-3 rounded-xl bg-surface-3/50 border border-border-subtle hover:border-border-strong transition-colors group"
              >
                <div className="w-8 h-8 rounded-lg bg-accent-emerald/10 flex items-center justify-center">
                  <svg className="w-4 h-4 text-accent-emerald" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <div className="text-xs font-medium text-white">Health Check</div>
                  <div className="text-[10px] text-text-muted">API Status</div>
                </div>
              </a>

              <a
                href="/analytics"
                className="flex items-center gap-3 p-3 rounded-xl bg-surface-3/50 border border-border-subtle hover:border-border-strong transition-colors group"
              >
                <div className="w-8 h-8 rounded-lg bg-accent-violet/10 flex items-center justify-center">
                  <svg className="w-4 h-4 text-accent-violet-light" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75z" />
                  </svg>
                </div>
                <div>
                  <div className="text-xs font-medium text-white">View Analytics</div>
                  <div className="text-[10px] text-text-muted">Charts & Trends</div>
                </div>
              </a>

              <a
                href="/repos"
                className="flex items-center gap-3 p-3 rounded-xl bg-surface-3/50 border border-border-subtle hover:border-border-strong transition-colors group"
              >
                <div className="w-8 h-8 rounded-lg bg-accent-cyan/10 flex items-center justify-center">
                  <svg className="w-4 h-4 text-accent-cyan-light" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 10.5v6m3-3H9m4.06-7.19l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
                  </svg>
                </div>
                <div>
                  <div className="text-xs font-medium text-white">All Repositories</div>
                  <div className="text-[10px] text-text-muted">Browse repos</div>
                </div>
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <div className="h-7 w-40 bg-surface-3 rounded-lg animate-pulse" />
        <div className="h-4 w-64 bg-surface-2 rounded mt-2 animate-pulse" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="glass-card p-5 h-28 animate-pulse">
            <div className="h-3 w-20 bg-surface-3 rounded mb-4" />
            <div className="h-8 w-16 bg-surface-3 rounded" />
          </div>
        ))}
      </div>
      <div className="glass-card h-64 animate-pulse" />
    </div>
  )
}
