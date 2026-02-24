import { type ReactNode } from 'react'

interface Props {
  label: string
  value: string | number
  icon: ReactNode
  accent?: 'violet' | 'emerald' | 'red' | 'cyan' | 'amber'
  subtitle?: string
}

const accentMap = {
  violet: { bg: 'bg-accent-violet/10', text: 'text-accent-violet-light', glow: 'rgba(124,92,252,0.15)' },
  emerald: { bg: 'bg-accent-emerald/10', text: 'text-accent-emerald-light', glow: 'rgba(16,185,129,0.15)' },
  red: { bg: 'bg-accent-red/10', text: 'text-accent-red-light', glow: 'rgba(239,68,68,0.15)' },
  cyan: { bg: 'bg-accent-cyan/10', text: 'text-accent-cyan-light', glow: 'rgba(6,182,212,0.15)' },
  amber: { bg: 'bg-accent-amber/10', text: 'text-accent-amber-light', glow: 'rgba(245,158,11,0.15)' },
}

export default function StatCard({ label, value, icon, accent = 'violet', subtitle }: Props) {
  const a = accentMap[accent]

  return (
    <div className="glass-card glass-card-glow p-5 group">
      {/* Decorative corner glow */}
      <div
        className="absolute -top-8 -right-8 w-24 h-24 rounded-full blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
        style={{ background: a.glow }}
      />

      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-text-muted text-xs font-medium uppercase tracking-wider mb-3">
            {label}
          </p>
          <p className="font-display text-3xl font-bold text-white tracking-tight">
            {value}
          </p>
          {subtitle && (
            <p className="text-text-muted text-xs mt-1.5">{subtitle}</p>
          )}
        </div>
        <div className={`${a.bg} ${a.text} p-2.5 rounded-xl`}>
          {icon}
        </div>
      </div>
    </div>
  )
}
