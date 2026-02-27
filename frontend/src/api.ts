import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({ baseURL: API_BASE })

// ── Types ────────────────────────────────────────────────────────────────────

export interface DocumentInput {
  text: string
  title?: string
  source_url?: string
  doc_type?: string
  metadata?: Record<string, unknown>
}

export interface SummarizeRequest {
  documents: DocumentInput[]
  summarizer_backend: 'rag' | 'bart'
  conflict_strategy: 'auto' | 'weighted_vote' | 'majority_vote' | 'highest_credibility_wins' | 'conservative'
  summary_depth?: 'brief' | 'standard' | 'detailed' | 'deep_research'
}

export interface JobResponse {
  job_id: string
  status: string
  message: string
}

export interface JobStatus {
  job_id: string
  status: 'pending' | 'running' | 'done' | 'failed'
  error?: string
  report_id?: string
  created_at: string
  updated_at: string
}

export interface CredibilityScore {
  overall: number
  breakdown: Record<string, number>
  explanations?: Record<string, string>
  signals: Record<string, unknown>
}

export interface Claim {
  id: string
  text: string
  source_doc_id: string
  confidence: number
}

export interface Conflict {
  claims: Claim[]
  topic: string
  resolution?: string
  status: 'resolved' | 'unresolved'
  confidence: number
}

export interface SummarySection {
  title: string
  content: string
}

export interface DocumentSummary {
  doc_id: string
  doc_type: string
  title?: string
  source_url?: string
  credibility_score?: CredibilityScore
}

export interface SummaryReport {
  report_id: string
  job_id: string
  status: string
  documents: DocumentSummary[]
  resolved_claims: Claim[]
  conflicts: Conflict[]
  sections: SummarySection[]
  full_summary: string
  doc_types_present: string[]
  created_at: string
  summary_depth?: string
  report_title?: string
  is_saved?: boolean
}

export interface DocTypeInfo {
  doc_type: string
  credibility_signals: Array<{ signal: string; weight: string }>
  default_strategy: string
}

export interface UpdateReportRequest {
  report_title?: string
  is_saved?: boolean
}

export interface QARequest {
  report_id: string
  question: string
}

export interface QAResponse {
  question: string
  answer: string
  citations: string[]
}

export interface ReportFilters {
  skip?: number
  limit?: number
  doc_type?: string
  has_conflicts?: boolean
  is_saved?: boolean
  date_from?: string
  date_to?: string
  search?: string
}

// ── API functions ─────────────────────────────────────────────────────────────

export const submitSummarize = (req: SummarizeRequest) =>
  api.post<JobResponse>('/summarize', req).then(r => r.data)

export const getJobStatus = (jobId: string) =>
  api.get<JobStatus>(`/jobs/${jobId}`).then(r => r.data)

export const listReports = (filters: ReportFilters = {}) => {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== null && v !== '')
  )
  return api.get<SummaryReport[]>('/reports', { params }).then(r => r.data)
}

export const getReport = (reportId: string) =>
  api.get<SummaryReport>(`/reports/${reportId}`).then(r => r.data)

export const updateReport = (reportId: string, data: UpdateReportRequest) =>
  api.patch<SummaryReport>(`/reports/${reportId}`, data).then(r => r.data)

export const deleteReport = (reportId: string) =>
  api.delete(`/reports/${reportId}`)

export const getDocTypes = () =>
  api.get<DocTypeInfo[]>('/doc-types').then(r => r.data)

export const fetchUrlContent = (url: string) =>
  api.get<{ title: string; text: string; source_url: string }>('/fetch-url', { params: { url } }).then(r => r.data)

export const uploadFile = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<{ title: string; text: string; source_url: string | null; word_count: number }>(
    '/upload-file', form, { headers: { 'Content-Type': 'multipart/form-data' } }
  ).then(r => r.data)
}

export const askQuestion = (req: QARequest) =>
  api.post<QAResponse>('/qa', req).then(r => r.data)
