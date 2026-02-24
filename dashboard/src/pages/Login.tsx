import { Link } from 'react-router-dom'

export default function Login() {
  const apiUrl = import.meta.env.VITE_API_URL || ''

  return (
    <div className="min-h-screen bg-surface-0 flex items-center justify-center relative overflow-hidden">
      {/* Background decorative elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] rounded-full bg-accent-violet/[0.04] blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full bg-accent-cyan/[0.03] blur-[100px]" />
      </div>

      {/* Login Card */}
      <div className="relative glass-card p-10 max-w-sm w-full mx-4 text-center">
        {/* Gradient top border */}
        <div className="absolute top-0 left-[15%] right-[15%] h-px bg-gradient-to-r from-transparent via-accent-violet to-transparent" />

        {/* Logo */}
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-violet to-accent-cyan flex items-center justify-center mx-auto mb-6">
          <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
          </svg>
        </div>

        <h1 className="font-display text-2xl font-bold text-white mb-2">
          Argus
        </h1>
        <p className="text-text-muted text-sm mb-8">
          Sign in to the All-Seeing Code Reviewer dashboard
        </p>

        {/* GitHub Login Button */}
        <a
          href={`${apiUrl}/auth/github/login`}
          className="flex items-center justify-center gap-3 w-full px-6 py-3.5 rounded-xl bg-white text-surface-0 font-semibold text-sm hover:bg-white/90 transition-colors"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
          </svg>
          Sign in with GitHub
        </a>

        <div className="mt-6">
          <Link
            to="/dashboard"
            className="text-text-muted hover:text-text-secondary text-sm transition-colors"
          >
            Continue without login &rarr;
          </Link>
        </div>
      </div>
    </div>
  )
}
