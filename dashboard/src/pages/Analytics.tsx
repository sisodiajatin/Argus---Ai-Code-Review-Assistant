import { useEffect, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, BarChart, Bar,
} from 'recharts'
import { api } from '../api/client'
import type { TrendDataPoint, CategoryBreakdown, SeverityBreakdown, FeedbackStats } from '../types'

const CATEGORY_COLORS = ['#7c5cfc', '#06b6d4', '#f59e0b', '#10b981', '#ef4444', '#ec4899']
const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  suggestion: '#06b6d4',
}

export default function Analytics() {
  const [trends, setTrends] = useState<TrendDataPoint[]>([])
  const [categories, setCategories] = useState<CategoryBreakdown[]>([])
  const [severities, setSeverities] = useState<SeverityBreakdown[]>([])
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [t, c, s, fb] = await Promise.all([
          api.getTrends(),
          api.getCategories(),
          api.getSeverities(),
          api.getFeedbackStats(),
        ])
        setTrends(t)
        setCategories(c)
        setSeverities(s)
        setFeedbackStats(fb)
      } catch {
        // API not running
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="mb-8">
          <div className="h-7 w-40 bg-surface-3 rounded-lg animate-pulse" />
          <div className="h-4 w-64 bg-surface-2 rounded mt-2 animate-pulse" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <div className="glass-card h-80 animate-pulse" />
          <div className="glass-card h-80 animate-pulse" />
        </div>
        <div className="glass-card h-64 animate-pulse" />
      </div>
    )
  }

  const hasData = trends.length > 0 || categories.length > 0 || severities.length > 0 || (feedbackStats && feedbackStats.total_rated > 0)

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="mb-8">
        <h2 className="font-display text-2xl font-bold text-white tracking-tight">
          Analytics
        </h2>
        <p className="text-text-muted text-sm mt-1">
          Insights from your code reviews
        </p>
      </div>

      {!hasData ? (
        <div className="glass-card p-16 text-center">
          <svg className="w-14 h-14 text-text-muted mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
          <p className="text-white font-display font-semibold text-lg">No analytics data yet</p>
          <p className="text-text-muted text-sm mt-1 max-w-xs mx-auto">
            Analytics will populate as the bot reviews pull requests.
          </p>
        </div>
      ) : (
        <>
          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6 stagger">
            {/* Category Breakdown */}
            <div className="glass-card p-6">
              <h3 className="font-display text-base font-semibold text-white mb-6">
                Findings by Category
              </h3>
              {categories.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={categories}
                      dataKey="count"
                      nameKey="category"
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={3}
                      stroke="none"
                    >
                      {categories.map((_, i) => (
                        <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                      ))}
                    </Pie>
                    <Legend
                      verticalAlign="bottom"
                      iconType="circle"
                      iconSize={8}
                      formatter={(value: string) => (
                        <span className="text-text-secondary text-xs capitalize">{value}</span>
                      )}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#13141c',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: '12px',
                        fontSize: '12px',
                        color: '#e0e0ee',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-text-muted text-sm text-center py-12">No data</p>
              )}
            </div>

            {/* Severity Breakdown */}
            <div className="glass-card p-6">
              <h3 className="font-display text-base font-semibold text-white mb-6">
                Findings by Severity
              </h3>
              {severities.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={severities}
                      dataKey="count"
                      nameKey="severity"
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={3}
                      stroke="none"
                    >
                      {severities.map((s) => (
                        <Cell key={s.severity} fill={SEVERITY_COLORS[s.severity] ?? '#6b7280'} />
                      ))}
                    </Pie>
                    <Legend
                      verticalAlign="bottom"
                      iconType="circle"
                      iconSize={8}
                      formatter={(value: string) => (
                        <span className="text-text-secondary text-xs capitalize">{value}</span>
                      )}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#13141c',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: '12px',
                        fontSize: '12px',
                        color: '#e0e0ee',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-text-muted text-sm text-center py-12">No data</p>
              )}
            </div>
          </div>

          {/* Trend Chart */}
          {trends.length > 0 && (
            <div className="glass-card p-6">
              <h3 className="font-display text-base font-semibold text-white mb-6">
                Reviews per Day (Last 30 Days)
              </h3>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={trends} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#7c5cfc" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#7c5cfc" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="findingsGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.2} />
                      <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#5c5c72', fontSize: 11 }}
                    tickLine={false}
                    axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                    tickFormatter={(v: string) => {
                      const d = new Date(v)
                      return `${d.getMonth() + 1}/${d.getDate()}`
                    }}
                  />
                  <YAxis
                    tick={{ fill: '#5c5c72', fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#13141c',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '12px',
                      fontSize: '12px',
                      color: '#e0e0ee',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="reviews"
                    stroke="#a78bfa"
                    strokeWidth={2}
                    fill="url(#trendGrad)"
                    name="Reviews"
                  />
                  <Area
                    type="monotone"
                    dataKey="findings"
                    stroke="#22d3ee"
                    strokeWidth={1.5}
                    fill="url(#findingsGrad)"
                    name="Findings"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Feedback Quality */}
          {feedbackStats && feedbackStats.total_rated > 0 && (
            <div className="glass-card p-6 mt-6">
              <h3 className="font-display text-base font-semibold text-white mb-6">
                Review Quality (Developer Feedback)
              </h3>

              {/* Summary stats */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="bg-surface-2/50 rounded-xl p-4 text-center">
                  <p className="text-2xl font-bold text-white">{feedbackStats.total_rated}</p>
                  <p className="text-text-muted text-xs mt-1">Findings Rated</p>
                </div>
                <div className="bg-surface-2/50 rounded-xl p-4 text-center">
                  <p className="text-2xl font-bold text-accent-emerald">{feedbackStats.helpful_rate}%</p>
                  <p className="text-text-muted text-xs mt-1">Helpful Rate</p>
                </div>
                <div className="bg-surface-2/50 rounded-xl p-4 text-center">
                  <p className="text-2xl font-bold text-accent-red">{feedbackStats.not_helpful_count}</p>
                  <p className="text-text-muted text-xs mt-1">Not Helpful</p>
                </div>
              </div>

              {/* Per-category quality bar chart */}
              {feedbackStats.by_category.length > 0 && (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart
                    data={feedbackStats.by_category}
                    margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
                    layout="vertical"
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" horizontal={false} />
                    <XAxis
                      type="number"
                      domain={[0, 100]}
                      tick={{ fill: '#5c5c72', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v: number) => `${v}%`}
                    />
                    <YAxis
                      type="category"
                      dataKey="category"
                      tick={{ fill: '#b0b0c8', fontSize: 12 }}
                      tickLine={false}
                      axisLine={false}
                      width={100}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#13141c',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: '12px',
                        fontSize: '12px',
                        color: '#e0e0ee',
                      }}
                      formatter={(value: number) => [`${value}%`, 'Helpful rate']}
                    />
                    <Bar dataKey="rate" fill="#10b981" radius={[0, 6, 6, 0]} barSize={20} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
