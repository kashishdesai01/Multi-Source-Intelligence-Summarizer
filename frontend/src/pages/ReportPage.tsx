import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { getReport, deleteReport, updateReport } from '../api'
import type { CredibilityScore, DocumentSummary } from '../api'
import QAPanel from '../components/QAPanel'
import {
  AlertTriangle, CheckCircle, ChevronDown, ChevronUp, Trash2,
  ExternalLink, BookOpen, Bookmark, BookmarkCheck, Pencil, Check, X,
  Layers, Info,
} from 'lucide-react'
import { useState } from 'react'

const DOC_TYPE_COLORS: Record<string, string> = {
  research_paper: '#6366f1',
  news_article: '#3b82f6',
  blog_post: '#8b5cf6',
  legal_document: '#f59e0b',
  unknown: '#6b7280',
}

const DEPTH_LABELS: Record<string, string> = {
  brief: 'Brief',
  standard: 'Standard',
  detailed: 'Detailed',
  deep_research: 'Deep Research',
}

function CredBar({
  label, value, explanation,
}: { label: string; value: number; explanation?: string }) {
  const [showTip, setShowTip] = useState(false)
  const pct = Math.round(value * 100)
  const color = value >= 0.7 ? '#4ade80' : value >= 0.45 ? '#facc15' : '#f87171'

  return (
    <div className="cred-bar-row">
      <div className="cred-bar-label-row">
        <span className="cred-bar-label">{label.replace(/_/g, ' ')}</span>
        <div className="cred-bar-pct-row">
          <span className="cred-bar-pct" style={{ color }}>{pct}%</span>
          {explanation && (
            <div className="cred-tooltip-wrap" style={{ position: 'relative' }}>
              <button
                className="cred-info-btn"
                onMouseEnter={() => setShowTip(true)}
                onMouseLeave={() => setShowTip(false)}
                onClick={() => setShowTip(s => !s)}
                aria-label="Show explanation"
                type="button"
              >
                <Info size={12} />
              </button>
              <AnimatePresence>
                {showTip && (
                  <motion.div
                    className="cred-tooltip"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    transition={{ duration: 0.15 }}
                  >
                    {explanation}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>
      <div className="cred-bar-track">
        <motion.div
          className="cred-bar-fill"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          style={{ background: color }}
        />
      </div>
    </div>
  )
}

function DocCard({ doc }: { doc: DocumentSummary }) {
  const [expanded, setExpanded] = useState(false)
  const score = doc.credibility_score as CredibilityScore | undefined
  const overall = score?.overall ?? 0
  const pct = Math.round(overall * 100)
  const color = overall >= 0.7 ? '#4ade80' : overall >= 0.45 ? '#facc15' : '#f87171'
  const typeColor = DOC_TYPE_COLORS[doc.doc_type] || DOC_TYPE_COLORS.unknown

  return (
    <div className="doc-card">
      <div className="doc-card-header" onClick={() => setExpanded(e => !e)} style={{ cursor: 'pointer' }}>
        <div className="doc-card-meta">
          <span className="badge" style={{ background: typeColor + '22', color: typeColor, border: `1px solid ${typeColor}44` }}>
            {doc.doc_type.replace(/_/g, ' ')}
          </span>
          <span className="doc-card-title">{doc.title || 'Untitled Document'}</span>
        </div>
        <div className="doc-card-right">
          {score && (
            <div className="cred-overall" style={{ color }} title={`Credibility: ${pct}%`}>
              <svg width="36" height="36" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
                <circle
                  cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="3"
                  strokeDasharray={`${pct * 0.94} 94`}
                  strokeLinecap="round"
                  transform="rotate(-90 18 18)"
                />
              </svg>
              <span className="cred-overall-pct">{pct}</span>
            </div>
          )}
          {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div className="doc-card-body">
              {doc.source_url && (
                <a href={doc.source_url} target="_blank" rel="noopener noreferrer" className="doc-source-link">
                  <ExternalLink size={12} /> {doc.source_url.slice(0, 80)}{doc.source_url.length > 80 ? '…' : ''}
                </a>
              )}
              {score && Object.keys(score.breakdown).length > 0 && (
                <div className="cred-breakdown">
                  <p className="cred-breakdown-title">Credibility Breakdown</p>
                  {Object.entries(score.breakdown).map(([k, v]) => (
                    <CredBar
                      key={k}
                      label={k}
                      value={v}
                      explanation={score.explanations?.[k]}
                    />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function ReportPage() {
  const { reportId } = useParams<{ reportId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')

  const { data: report, isLoading, error } = useQuery({
    queryKey: ['report', reportId],
    queryFn: () => getReport(reportId!),
    enabled: !!reportId,
  })

  const patchMut = useMutation({
    mutationFn: (data: { report_title?: string; is_saved?: boolean }) =>
      updateReport(reportId!, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report', reportId] }),
  })

  const deleteMut = useMutation({
    mutationFn: () => deleteReport(reportId!),
    onSuccess: () => navigate('/history'),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center" style={{ minHeight: '60vh' }}>
        <div className="loading-pulse">Loading report…</div>
      </div>
    )
  }

  if (error || !report) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
        <AlertTriangle size={40} style={{ color: 'var(--red)', margin: '0 auto 1rem' }} />
        <p>Could not load report.</p>
      </div>
    )
  }

  const isSingleDoc = report.documents.length === 1
  const hasConflicts = report.conflicts.length > 0 && !isSingleDoc
  const depth = report.summary_depth || 'standard'
  const isSaved = report.is_saved ?? false

  const startEditTitle = () => {
    setTitleDraft(report.report_title || '')
    setEditingTitle(true)
  }

  const saveTitle = () => {
    if (titleDraft.trim() !== (report.report_title ?? '')) {
      patchMut.mutate({ report_title: titleDraft.trim() || undefined })
    }
    setEditingTitle(false)
  }

  const toggleSaved = () => {
    patchMut.mutate({ is_saved: !isSaved })
  }

  return (
    <div>
      {/* ── Report header ─────────────────────────────── */}
      <div className="mb-6">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-2">
          {/* Title + edit */}
          <div className="flex items-center gap-2 flex-wrap">
            {editingTitle ? (
              <>
                <input
                  className="report-title-input"
                  value={titleDraft}
                  onChange={e => setTitleDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveTitle(); if (e.key === 'Escape') setEditingTitle(false) }}
                  autoFocus
                  placeholder="Report title…"
                />
                <button className="btn btn-ghost" style={{ padding: '0.3rem 0.6rem' }} onClick={saveTitle}><Check size={14} /></button>
                <button className="btn btn-ghost" style={{ padding: '0.3rem 0.6rem' }} onClick={() => setEditingTitle(false)}><X size={14} /></button>
              </>
            ) : (
              <>
                <h1 className="glow-text" style={{ fontSize: '1.5rem' }}>
                  {report.report_title || 'Summary Report'}
                </h1>
                <button className="btn btn-ghost" style={{ padding: '0.3rem 0.5rem' }} onClick={startEditTitle} title="Edit title">
                  <Pencil size={13} />
                </button>
              </>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              className={`btn ${isSaved ? 'btn-primary' : 'btn-ghost'}`}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
              onClick={toggleSaved}
              title={isSaved ? 'Unsave this report' : 'Save this report'}
            >
              {isSaved ? <BookmarkCheck size={15} /> : <Bookmark size={15} />}
              {isSaved ? 'Saved' : 'Save'}
            </button>
            <button
              className="btn btn-danger"
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.82rem' }}
              onClick={() => { if (confirm('Delete this report?')) deleteMut.mutate() }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {/* Metadata row */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className="badge badge-blue">
            <BookOpen size={11} style={{ marginRight: '4px', display: 'inline' }} />
            {report.documents.length} doc{report.documents.length !== 1 ? 's' : ''}
          </span>
          <span className="badge" style={{ background: 'rgba(99,102,241,0.12)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.25)' }}>
            <Layers size={11} style={{ marginRight: '4px', display: 'inline' }} />
            {DEPTH_LABELS[depth] || depth}
          </span>
          {report.doc_types_present.map(t => (
            <span key={t} className="badge" style={{
              background: (DOC_TYPE_COLORS[t] || '#6b7280') + '22',
              color: DOC_TYPE_COLORS[t] || '#6b7280',
              border: `1px solid ${(DOC_TYPE_COLORS[t] || '#6b7280')}44`,
            }}>
              {t.replace(/_/g, ' ')}
            </span>
          ))}
          {report.created_at && (
            <span className="text-xs text-muted">
              {new Date(report.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
          )}
        </div>
      </div>

      {/* ── Documents ─────────────────────────────────── */}
      <div className="card mb-6">
        <h2 className="mb-4" style={{ fontSize: '1.1rem', fontWeight: 700 }}>
          Documents Analyzed
        </h2>
        <div className="doc-list">
          {report.documents.map(doc => (
            <DocCard key={doc.doc_id} doc={doc} />
          ))}
        </div>
      </div>

      {/* ── Conflicts ─────────────────────────────────── */}
      {hasConflicts && (
        <div className="card mb-6">
          <h2 className="mb-4" style={{ fontSize: '1.1rem', fontWeight: 700 }}>
            <AlertTriangle size={16} style={{ color: '#f59e0b', display: 'inline', marginRight: '6px' }} />
            Conflicts Detected ({report.conflicts.length})
          </h2>
          <div className="conflict-list">
            {report.conflicts.map((c, i) => (
              <div key={i} className={`conflict-item conflict-item--${c.status}`}>
                <div className="conflict-header">
                  <span className="conflict-topic">{c.topic}</span>
                  <span className={`badge ${c.status === 'resolved' ? 'badge-green' : 'badge-orange'}`}>
                    {c.status === 'resolved' ? <><CheckCircle size={10} /> Resolved</> : 'Unresolved'}
                  </span>
                </div>
                {c.status === 'resolved' && c.resolution && (
                  <p className="conflict-resolution">→ {c.resolution}</p>
                )}
                <div className="conflict-claims">
                  {c.claims.map((cl, j) => (
                    <p key={j} className="conflict-claim">· {cl.text}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Summary sections ──────────────────────────── */}
      {report.sections.length > 0 && (
        <div className="card mb-6">
          <h2 className="mb-4" style={{ fontSize: '1.1rem', fontWeight: 700 }}>Summary</h2>
          <div className="summary-sections">
            {report.sections.map((s, i) => (
              <div key={i} className="summary-section">
                <h3 className="summary-section-title">{s.title}</h3>
                <p className="summary-section-content">{s.content}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Q&A Panel ─────────────────────────────────── */}
      <div className="card mb-6" style={{ padding: 0, overflow: 'hidden' }}>
        <QAPanel reportId={report.report_id} docTypes={report.doc_types_present} />
      </div>
    </div>
  )
}
