import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RepoListItem } from '../types'
import RepoCard from '../components/RepoCard'
import EmptyState from '../components/EmptyState'

export default function Repositories() {
  const [repos, setRepos] = useState<RepoListItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getRepos()
      .then(setRepos)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="mb-8">
          <div className="h-7 w-48 bg-surface-3 rounded-lg animate-pulse" />
          <div className="h-4 w-72 bg-surface-2 rounded mt-2 animate-pulse" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="glass-card p-5 h-44 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="font-display text-2xl font-bold text-white tracking-tight">
            Repositories
          </h2>
          <p className="text-text-muted text-sm mt-1">
            Repositories connected to the review bot
          </p>
        </div>
        <span className="text-text-muted text-xs px-3 py-1.5 rounded-full bg-surface-3 border border-border-subtle font-mono">
          {repos.length} connected
        </span>
      </div>

      {repos.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 stagger">
          {repos.map((repo) => (
            <RepoCard key={repo.id} repo={repo} />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No repositories connected"
          description="Install the GitHub App on a repository to get started with automated code reviews."
          icon={
            <svg className="w-14 h-14" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 10.5v6m3-3H9m4.06-7.19l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
            </svg>
          }
        />
      )}
    </div>
  )
}
