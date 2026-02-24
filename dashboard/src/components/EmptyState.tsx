import { type ReactNode } from 'react'

interface Props {
  icon?: ReactNode
  title: string
  description?: string
}

export default function EmptyState({ icon, title, description }: Props) {
  return (
    <div className="glass-card p-16 text-center">
      <div className="flex justify-center mb-5 text-text-muted">
        {icon || (
          <svg className="w-14 h-14" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
        )}
      </div>
      <p className="text-white font-display font-semibold text-lg mb-1">{title}</p>
      {description && (
        <p className="text-text-muted text-sm max-w-xs mx-auto">{description}</p>
      )}
    </div>
  )
}
