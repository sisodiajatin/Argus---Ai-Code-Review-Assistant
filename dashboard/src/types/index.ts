export interface DashboardStats {
  total_repos: number
  total_prs_reviewed: number
  total_findings: number
  critical_findings: number
  avg_processing_time_ms: number
  total_tokens_used: number
}

export interface RepoListItem {
  id: number
  full_name: string
  owner: string
  name: string
  is_active: boolean
  pr_count: number
  last_review: string | null
}

export interface PRReviewListItem {
  id: number
  pr_number: number
  title: string | null
  author: string | null
  status: string
  findings_count: number
  critical_count: number
  created_at: string | null
  completed_at: string | null
}

export interface FindingItem {
  id: number
  file_path: string
  line_start: number | null
  line_end: number | null
  category: string
  severity: string
  title: string
  description: string
  suggested_fix: string | null
  feedback: string | null
  feedback_note: string | null
}

export interface ReviewDetail {
  pr: PRReviewListItem
  findings: FindingItem[]
  summary_text: string | null
  overall_assessment: string | null
  model_used: string | null
  tokens_used: number
  processing_time_ms: number
}

export interface TrendDataPoint {
  date: string
  reviews: number
  findings: number
}

export interface CategoryBreakdown {
  category: string
  count: number
}

export interface SeverityBreakdown {
  severity: string
  count: number
}

export interface HealthResponse {
  status: string
  version: string
  timestamp: string
}

export interface SettingsResponse {
  ai_model: string
  ai_base_url: string
  app_host: string
  app_port: number
  webhook_url: string
  ignored_paths: string[]
  max_files_per_review: number
  chunk_token_limit: number
}

export interface ReReviewResponse {
  status: string
  message: string
}

export interface FeedbackResponse {
  id: number
  feedback: string
  message: string
}

export interface FeedbackStats {
  total_rated: number
  helpful_count: number
  not_helpful_count: number
  helpful_rate: number
  by_category: FeedbackCategoryRate[]
}

export interface FeedbackCategoryRate {
  category: string
  total: number
  helpful: number
  rate: number
}
