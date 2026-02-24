import { AreaChart, Area, ResponsiveContainer } from 'recharts'
import { useMemo } from 'react'

interface Props {
  value: number
  accent?: 'emerald' | 'red' | 'violet' | 'cyan'
}

const colorMap = {
  emerald: { stroke: '#34d399', fill: '#10b981' },
  red: { stroke: '#f87171', fill: '#ef4444' },
  violet: { stroke: '#a78bfa', fill: '#7c5cfc' },
  cyan: { stroke: '#22d3ee', fill: '#06b6d4' },
}

export default function MiniChart({ value, accent = 'emerald' }: Props) {
  const colors = colorMap[accent]

  // Generate deterministic sparkline data from value
  const data = useMemo(() => {
    const seed = value * 7 + 13
    return Array.from({ length: 12 }, (_, i) => ({
      v: Math.max(0, Math.sin(i * 0.8 + seed * 0.1) * 30 + value + Math.cos(i * 1.3 + seed * 0.2) * 15),
    }))
  }, [value])

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`grad-${accent}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colors.fill} stopOpacity={0.3} />
            <stop offset="100%" stopColor={colors.fill} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={colors.stroke}
          strokeWidth={1.5}
          fill={`url(#grad-${accent})`}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
