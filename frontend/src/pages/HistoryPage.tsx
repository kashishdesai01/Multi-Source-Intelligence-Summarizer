import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { listReports, deleteReport } from '../api'
import type { ReportFilters } from '../api'
import {
  BookOpen, Trash2, ChevronRight, AlertTriangle, Search,
  Filter, BookmarkCheck, Calendar, X,
} from 'lucide-react'

const DOC_TYPE_OPTIONS = [
  { value: 'research_paper', label: 'Research' },
  { value: 'news_article', label: 'News' },
  { value: 'blog_post', label: 'Blog' },
  { value: 'legal_document', label: 'Legal' },
]

const DEPTH_LABELS: Record<string, string> = {
  brief: 'Brief',
  standard: 'Standard',
  detailed: 'Detailed',
  deep_research: 'Deep Research',
}

const DOC_TYPE_COLORS: Record<string, string> = {
  research_paper: '#6366f1',
  news_article: '#3b82f6',
  blog_post: '#8b5cf6',
  legal_document: '#f59e0b',
}

export default function HistoryPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showFilters, setShowFilters] = useState(false)

  // Filter state
  const [search, setSearch] = useState('')
  const [docType, setDocType] = useState('')
  const [hasConflicts, setHasConflicts] = useState<boolean | undefined>(undefined)
  const [isSaved, setIsSaved] = useState<boolean | undefined>(undefined)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const filters: ReportFilters = {
    search: search || undefined,
    doc_type: docType || undefined,
    has_conflicts: hasConflicts,
    is_saved: isSaved,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    limit: 50,
  }

  const hasActiveFilters = !!(search || docType || hasConflicts !== undefined || isSaved !== undefined || dateFrom || dateTo)

  const clearFilters = useCallback(() => {
    setSearch(''); setDocType(''); setHasConflicts(undefined)
    setIsSaved(undefined); setDateFrom(''); setDateTo('')
  }, [])

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['reports', filters],
    queryFn: () => listReports(filters),
    staleTime: 10_000,
  })

  const deleteMut = useMutation({
    mutationFn: deleteReport,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }),
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="glow-text">History</h1>
          <p className="mt-1" style={{ fontSize: '0.9rem' }}>
            {isLoading ? 'Loading…' : `${reports.length} report${reports.length !== 1 ? 's' : ''} found`}
          </p>
        </div>

        {/* Filter toggle */}
        <div className="flex items-center gap-2">
          {hasActiveFilters && (
            <button className="btn btn-ghost" style={{ fontSize: '0.8rem', padding: '0.35rem 0.7rem' }} onClick={clearFilters}>
              <X size={13} /> Clear
            </button>
          )}
          <button
            className={`btn ${showFilters || hasActiveFilters ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: '0.85rem', padding: '0.4rem 0.85rem' }}
            onClick={() => setShowFilters(s => !s)}
          >
            <Filter size={14} /> Filters {hasActiveFilters && `(active)`}
          </button>
        </div>
      </div>

      {/* ── Filter bar ──────────────────────────────────── */}
      <AnimatePresence>
        {showFilters && (
          <motion.div
            className="card mb-6"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            {/* Search */}
            <div className="filter-row mb-4">
              <div className="filter-search-wrap">
                <Search size={14} className="filter-search-icon" />
                <input
                  type="text"
                  placeholder="Search summaries…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="filter-search-input"
                />
              </div>
            </div>

            <div className="filter-grid">
              {/* Doc type */}
              <div>
                <label className="filter-label">Document Type</label>
                <div className="filter-pill-row">
                  {DOC_TYPE_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      className={`filter-pill${docType === opt.value ? ' filter-pill--active' : ''}`}
                      onClick={() => setDocType(docType === opt.value ? '' : opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Saved status */}
              <div>
                <label className="filter-label">Saved Status</label>
                <div className="filter-pill-row">
                  <button
                    type="button"
                    className={`filter-pill${isSaved === true ? ' filter-pill--active' : ''}`}
                    onClick={() => setIsSaved(isSaved === true ? undefined : true)}
                  >
                    <BookmarkCheck size={12} /> Saved
                  </button>
                  <button
                    type="button"
                    className={`filter-pill${isSaved === false ? ' filter-pill--active' : ''}`}
                    onClick={() => setIsSaved(isSaved === false ? undefined : false)}
                  >
                    Unsaved
                  </button>
                </div>
              </div>

              {/* Conflicts */}
              <div>
                <label className="filter-label">Conflicts</label>
                <div className="filter-pill-row">
                  <button
                    type="button"
                    className={`filter-pill${hasConflicts === true ? ' filter-pill--active' : ''}`}
                    onClick={() => setHasConflicts(hasConflicts === true ? undefined : true)}
                  >
                    <AlertTriangle size={12} /> Has conflicts
                  </button>
                  <button
                    type="button"
                    className={`filter-pill${hasConflicts === false ? ' filter-pill--active' : ''}`}
                    onClick={() => setHasConflicts(hasConflicts === false ? undefined : false)}
                  >
                    No conflicts
                  </button>
                </div>
              </div>

              {/* Date range */}
              <div>
                <label className="filter-label"><Calendar size={12} style={{ display: 'inline', marginRight: '4px' }} />Date Range</label>
                <div className="filter-date-row">
                  <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="filter-date-input" />
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>to</span>
                  <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="filter-date-input" />
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Report list ─────────────────────────────────── */}
      {isLoading ? (
        <div className="text-center" style={{ padding: '4rem 0' }}>
          <div className="loading-pulse">Loading reports…</div>
        </div>
      ) : reports.length === 0 ? (
        <motion.div
          className="card"
          style={{ textAlign: 'center', padding: '4rem 2rem' }}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <BookOpen size={40} style={{ color: 'var(--accent)', margin: '0 auto 1rem' }} />
          <h3 className="mb-2">
            {hasActiveFilters ? 'No reports match your filters' : 'No reports yet'}
          </h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            {hasActiveFilters
              ? 'Try adjusting or clearing your filters.'
              : 'Submit documents on the home page to generate your first report.'}
          </p>
          {hasActiveFilters && (
            <button className="btn btn-ghost mt-4" onClick={clearFilters}>
              <X size={14} /> Clear filters
            </button>
          )}
        </motion.div>
      ) : (
        <div className="report-list">
          <AnimatePresence>
            {reports.map((report, i) => (
              <motion.div
                key={report.report_id}
                className="report-card"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -40 }}
                transition={{ duration: 0.2, delay: i * 0.03 }}
                layout
              >
                <div className="report-card-body" onClick={() => navigate(`/reports/${report.report_id}`)}>
                  {/* Title row */}
                  <div className="report-card-title-row">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="report-card-title">
                        {report.report_title || `Report · ${report.report_id.slice(0, 8)}`}
                      </h3>
                      {report.is_saved && (
                        <BookmarkCheck size={14} style={{ color: '#6366f1', flexShrink: 0 }} title="Saved" />
                      )}
                    </div>
                    <ChevronRight size={16} className="report-card-arrow" />
                  </div>

                  {/* Meta pills */}
                  <div className="report-card-meta">
                    <span className="badge badge-blue">
                      <BookOpen size={10} /> {report.documents.length} doc{report.documents.length !== 1 ? 's' : ''}
                    </span>
                    {report.summary_depth && (
                      <span className="badge" style={{ background: 'rgba(99,102,241,0.12)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.25)', fontSize: '0.72rem' }}>
                        {DEPTH_LABELS[report.summary_depth] || report.summary_depth}
                      </span>
                    )}
                    {report.doc_types_present.slice(0, 2).map(t => (
                      <span key={t} className="badge" style={{
                        background: (DOC_TYPE_COLORS[t] || '#6b7280') + '22',
                        color: DOC_TYPE_COLORS[t] || '#9ca3af',
                        border: `1px solid ${(DOC_TYPE_COLORS[t] || '#6b7280')}44`,
                        fontSize: '0.72rem',
                      }}>
                        {t.replace(/_/g, ' ')}
                      </span>
                    ))}
                    {report.conflicts.length > 0 && (
                      <span className="badge badge-orange" style={{ fontSize: '0.72rem' }}>
                        <AlertTriangle size={10} /> {report.conflicts.length} conflict{report.conflicts.length !== 1 ? 's' : ''}
                      </span>
                    )}
                    {report.created_at && (
                      <span className="text-xs text-muted">
                        {new Date(report.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                      </span>
                    )}
                  </div>

                  {/* Summary preview */}
                  {report.full_summary && (
                    <p className="report-card-preview">
                      {report.full_summary.replace(/^##\s*.+\n?/m, '').slice(0, 160)}…
                    </p>
                  )}
                </div>

                {/* Delete */}
                <button
                  className="report-card-delete"
                  onClick={e => {
                    e.stopPropagation()
                    if (confirm('Delete this report?')) deleteMut.mutate(report.report_id)
                  }}
                  title="Delete report"
                >
                  <Trash2 size={14} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
