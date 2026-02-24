const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, options)
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return res.json()
}

export const api = {
  getStats: () =>
    request<import('../types').DashboardStats>('/api/dashboard/stats'),

  getRepos: () =>
    request<import('../types').RepoListItem[]>('/api/dashboard/repos'),

  getRepoReviews: (repoId: number) =>
    request<import('../types').PRReviewListItem[]>(
      `/api/dashboard/repos/${repoId}/reviews`
    ),

  getReviewDetail: (prId: number) =>
    request<import('../types').ReviewDetail>(
      `/api/dashboard/reviews/${prId}`
    ),

  reReview: (prId: number) =>
    request<import('../types').ReReviewResponse>(
      `/api/dashboard/reviews/${prId}/re-review`,
      { method: 'POST' }
    ),

  getSettings: () =>
    request<import('../types').SettingsResponse>('/api/dashboard/settings'),

  getTrends: (days = 30) =>
    request<import('../types').TrendDataPoint[]>(
      `/api/dashboard/analytics/trends?days=${days}`
    ),

  getCategories: () =>
    request<import('../types').CategoryBreakdown[]>(
      '/api/dashboard/analytics/categories'
    ),

  getSeverities: () =>
    request<import('../types').SeverityBreakdown[]>(
      '/api/dashboard/analytics/severity'
    ),

  getHealth: () =>
    request<import('../types').HealthResponse>('/api/health'),

  getMe: () =>
    request<{ authenticated: boolean; user: { id: number; username: string; avatar_url: string } | null }>('/auth/me'),

  submitFeedback: (findingId: number, feedback: 'helpful' | 'not_helpful', note?: string) =>
    request<import('../types').FeedbackResponse>(
      `/api/dashboard/findings/${findingId}/feedback`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback, note }),
      }
    ),

  getFeedbackStats: () =>
    request<import('../types').FeedbackStats>(
      '/api/dashboard/analytics/feedback'
    ),
}
