import { Link } from 'react-router-dom'
import type { RepoListItem } from '../types'
import MiniChart from './MiniChart'

interface Props {
  repo: RepoListItem
  findings?: number
}

export default function RepoCard({ repo, findings = 0 }: Props) {
  return (
    <Link
      to={`/repos/${repo.id}`}
      className="glass-card glass-card-glow p-5 block group cursor-pointer"
    >
      {/* Top: repo identifier */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent-violet/20 to-accent-cyan/20 border border-border-subtle flex items-center justify-center">
            <svg className="w-5 h-5 text-accent-violet-light" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
            </svg>
          </div>
          <div>
            <div className="text-[10px] text-text-muted uppercase tracking-wider">
              {repo.owner}
            </div>
            <div className="text-white font-display font-semibold text-sm truncate max-w-[160px]">
              {repo.name}
            </div>
          </div>
        </div>
        <div className="w-7 h-7 rounded-lg border border-border-subtle flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
          <svg className="w-3.5 h-3.5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5l15-15m0 0H8.25m11.25 0v11.25" />
          </svg>
        </div>
      </div>

      {/* Middle: metrics */}
      <div className="mb-3">
        <p className="text-text-muted text-[11px] uppercase tracking-wider mb-1">
          PRs Reviewed
        </p>
        <div className="flex items-baseline gap-2">
          <span className="font-display text-2xl font-bold text-white">{repo.pr_count}</span>
          {repo.is_active && (
            <span className="flex items-center gap-1 text-accent-emerald text-xs font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-emerald" />
              Active
            </span>
          )}
        </div>
      </div>

      {/* Bottom: mini chart placeholder */}
      <div className="h-12 mt-2">
        <MiniChart value={repo.pr_count} accent={findings > 5 ? 'red' : 'emerald'} />
      </div>
    </Link>
  )
}
