/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          0: '#07070d',
          1: '#0c0d14',
          2: '#13141c',
          3: '#1a1b25',
          4: '#22232f',
        },
        border: {
          subtle: 'rgba(255, 255, 255, 0.06)',
          DEFAULT: 'rgba(255, 255, 255, 0.08)',
          strong: 'rgba(255, 255, 255, 0.12)',
        },
        accent: {
          violet: '#7c5cfc',
          'violet-light': '#a78bfa',
          emerald: '#10b981',
          'emerald-light': '#34d399',
          red: '#ef4444',
          'red-light': '#f87171',
          amber: '#f59e0b',
          'amber-light': '#fbbf24',
          cyan: '#06b6d4',
          'cyan-light': '#22d3ee',
        },
        text: {
          primary: '#ffffff',
          secondary: '#a0a0b8',
          muted: '#5c5c72',
        },
      },
      fontFamily: {
        display: ['"Outfit"', 'sans-serif'],
        body: ['"DM Sans"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out forwards',
        'slide-up': 'slideUp 0.5s ease-out forwards',
        'glow-pulse': 'glowPulse 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        glowPulse: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.8' },
        },
      },
    },
  },
  plugins: [],
}
