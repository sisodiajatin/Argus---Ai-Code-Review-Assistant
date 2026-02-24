interface Props {
  severity: string
  size?: 'sm' | 'md'
}

const styles: Record<string, string> = {
  critical: 'bg-accent-red/15 text-accent-red-light border-accent-red/20',
  warning: 'bg-accent-amber/15 text-accent-amber-light border-accent-amber/20',
  suggestion: 'bg-accent-cyan/15 text-accent-cyan-light border-accent-cyan/20',
  completed: 'bg-accent-emerald/15 text-accent-emerald-light border-accent-emerald/20',
  reviewing: 'bg-accent-violet/15 text-accent-violet-light border-accent-violet/20',
  pending: 'bg-white/5 text-text-secondary border-border-subtle',
  failed: 'bg-accent-red/15 text-accent-red-light border-accent-red/20',
}

export default function SeverityBadge({ severity, size = 'sm' }: Props) {
  const cls = styles[severity] || styles.pending

  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium capitalize ${cls} ${
        size === 'sm' ? 'px-2.5 py-0.5 text-[11px]' : 'px-3 py-1 text-xs'
      }`}
    >
      {severity}
    </span>
  )
}
