import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, Trash2, Zap, FileText, Link, Loader, Upload, Layers } from 'lucide-react'
import { submitSummarize, getJobStatus, fetchUrlContent, uploadFile } from '../api'
import type { DocumentInput } from '../api'

const DOC_TYPES = ['auto-detect', 'research_paper', 'news_article', 'blog_post', 'legal_document']
const STRATEGIES = ['auto', 'weighted_vote', 'majority_vote', 'highest_credibility_wins', 'conservative']
const DEPTH_OPTIONS = [
  { value: 'brief', label: 'Brief', desc: 'TL;DR — 2-3 key findings, under 200 words' },
  { value: 'standard', label: 'Standard', desc: 'Key findings, conflicts & conclusion' },
  { value: 'detailed', label: 'Detailed', desc: 'Analysis, limitations, implications, 400-700 words' },
  { value: 'deep_research', label: 'Deep Research', desc: 'Full academic breakdown, 600-900 words' },
]

type InputMode = 'text' | 'url' | 'file'
interface DocEntry extends DocumentInput { _id: string; inputMode: InputMode }

const emptyDoc = (): DocEntry => ({
  _id: crypto.randomUUID(), text: '', title: '', source_url: '',
  doc_type: undefined, metadata: {}, inputMode: 'text',
})

const nextMode = (m: InputMode): InputMode => m === 'text' ? 'url' : m === 'url' ? 'file' : 'text'
const modeLabel = (m: InputMode) =>
  m === 'text' ? <><FileText size={12} /> Text</> :
  m === 'url'  ? <><Link size={12} /> URL</> :
                 <><Upload size={12} /> File</>

export default function SubmitPage() {
  const navigate = useNavigate()
  const [docs, setDocs] = useState<DocEntry[]>([emptyDoc()])
  const [backend, setBackend] = useState<'rag' | 'bart'>('rag')
  const [strategy, setStrategy] = useState('auto')
  const [depth, setDepth] = useState<'brief' | 'standard' | 'detailed' | 'deep_research'>('standard')
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<string>('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [fetchingIds, setFetchingIds] = useState<Set<string>>(new Set())
  const [fetchErrors, setFetchErrors] = useState<Record<string, string>>({})
  const [dragOver, setDragOver] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({})

  const updateDoc = (id: string, patch: Partial<DocEntry>) =>
    setDocs(d => d.map(doc => doc._id === id ? { ...doc, ...patch } : doc))

  const removeDoc = (id: string) => setDocs(d => d.filter(doc => doc._id !== id))

  const handleFileUpload = async (entry: DocEntry, file: File) => {
    setFetchingIds(s => new Set(s).add(entry._id))
    setFetchErrors(e => { const n = { ...e }; delete n[entry._id]; return n })
    try {
      const result = await uploadFile(file)
      updateDoc(entry._id, {
        text: result.text,
        title: entry.title || result.title || file.name.replace(/\.[^.]+$/, ''),
        source_url: '',
      })
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to parse file. Try pasting the text directly.'
      setFetchErrors(prev => ({ ...prev, [entry._id]: msg }))
    } finally {
      setFetchingIds(s => { const n = new Set(s); n.delete(entry._id); return n })
    }
  }

  const fetchUrl = async (entry: DocEntry) => {
    if (!entry.source_url) return
    setFetchingIds(s => new Set(s).add(entry._id))
    setFetchErrors(e => { const n = { ...e }; delete n[entry._id]; return n })
    try {
      const result = await fetchUrlContent(entry.source_url)
      updateDoc(entry._id, {
        text: result.text,
        title: entry.title || result.title,
        source_url: result.source_url,
      })
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to fetch URL. Try pasting the text directly.'
      setFetchErrors(prev => ({ ...prev, [entry._id]: msg }))
    } finally {
      setFetchingIds(s => { const n = new Set(s); n.delete(entry._id); return n })
    }
  }

  const handleSubmit = async () => {
    const urlDocsNeedingFetch = docs.filter(
      d => d.inputMode === 'url' && d.source_url && d.text.trim().length < 50
    )
    if (urlDocsNeedingFetch.length > 0) {
      await Promise.all(urlDocsNeedingFetch.map(fetchUrl))
    }

    setDocs(current => {
      const valid = current.filter(d => d.text.trim().length > 50)
      if (valid.length < 1) {
        setError('Please provide at least 1 document with content (or ensure URLs fetched / files uploaded successfully).')
        return current
      }
      setError(''); setLoading(true)
      const payload = {
        documents: valid.map(d => ({
          text: d.text, title: d.title || undefined,
          source_url: d.source_url || undefined,
          doc_type: d.doc_type === 'auto-detect' ? undefined : d.doc_type || undefined,
          metadata: d.metadata,
        })),
        summarizer_backend: backend,
        conflict_strategy: strategy as any,
        summary_depth: depth,
      }
      submitSummarize(payload)
        .then(job => { setJobId(job.job_id); setJobStatus('pending') })
        .catch((e: any) => {
          setError(e?.response?.data?.detail || 'Submission failed. Is the backend running?')
          setLoading(false)
        })
      return current
    })
  }

  useEffect(() => {
    if (!jobId) return
    pollRef.current = setInterval(async () => {
      try {
        const status = await getJobStatus(jobId)
        setJobStatus(status.status)
        if (status.status === 'done' && status.report_id) {
          clearInterval(pollRef.current!)
          setLoading(false)
          navigate(`/reports/${status.report_id}`)
        } else if (status.status === 'failed') {
          clearInterval(pollRef.current!)
          setLoading(false)
          setError(`Job failed: ${status.error || 'unknown error'}`)
          setJobId(null)
        }
      } catch { /* ignore */ }
    }, 2000)
    return () => clearInterval(pollRef.current!)
  }, [jobId, navigate])

  const progressPct = jobStatus === 'pending' ? 20 : jobStatus === 'running' ? 65 : 95

  return (
    <div>
      <div className="mb-6">
        <h1 className="glow-text">Summarize Documents</h1>
        <p className="mt-2">Add one or more documents. The system auto-classifies each, scores credibility, resolves conflicts (if multiple), and generates a structured summary.</p>
      </div>

      {/* ── Document inputs ───────────────────────────── */}
      <AnimatePresence>
        {docs.map((doc, idx) => (
          <motion.div
            key={doc._id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, height: 0, margin: 0 }}
            transition={{ duration: 0.2 }}
            className="card mb-4"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FileText size={16} style={{ color: 'var(--accent-light)' }} />
                <span style={{ fontWeight: 600, fontSize: '0.92rem' }}>Document {idx + 1}</span>
              </div>
              <div className="flex items-center gap-2">
                {/* Cycle: Text → URL → File → Text */}
                <button
                  className="btn btn-ghost"
                  style={{ padding: '0.3rem 0.7rem', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                  onClick={() => updateDoc(doc._id, { inputMode: nextMode(doc.inputMode), text: '', source_url: '' })}
                >
                  {modeLabel(doc.inputMode)}
                </button>
                {docs.length > 1 && (
                  <button className="btn btn-danger" style={{ padding: '0.3rem 0.6rem' }} onClick={() => removeDoc(doc._id)}>
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>

            <div className="grid-2 mb-3">
              <input type="text" placeholder="Title (optional)" value={doc.title || ''} onChange={e => updateDoc(doc._id, { title: e.target.value })} />
              <select value={doc.doc_type || 'auto-detect'} onChange={e => updateDoc(doc._id, { doc_type: e.target.value === 'auto-detect' ? undefined : e.target.value })}>
                {DOC_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </div>

            {/* ── URL mode ── */}
            {doc.inputMode === 'url' && (
              <div>
                <div className="flex gap-2">
                  <input type="url" placeholder="https://..." value={doc.source_url || ''} onChange={e => updateDoc(doc._id, { source_url: e.target.value, text: '' })} />
                  <button
                    className="btn btn-ghost"
                    onClick={() => fetchUrl(doc)}
                    disabled={fetchingIds.has(doc._id) || !doc.source_url}
                    style={{ flexShrink: 0 }}
                  >
                    {fetchingIds.has(doc._id) ? <><Loader size={14} className="spin" /> Fetching…</> : <><Link size={14} /> Fetch</>}
                  </button>
                </div>
                {fetchErrors[doc._id] && <p style={{ color: 'var(--red)', fontSize: '0.8rem', marginTop: '0.4rem' }}>{fetchErrors[doc._id]}</p>}
                {doc.text.trim().length > 50 && (
                  <p style={{ color: 'var(--green, #4ade80)', fontSize: '0.8rem', marginTop: '0.4rem' }}>
                    ✓ {doc.text.trim().split(/\s+/).length} words fetched
                  </p>
                )}
              </div>
            )}

            {/* ── File upload mode ── */}
            {doc.inputMode === 'file' && (
              <div>
                <input
                  type="file"
                  accept=".pdf,.docx,.doc"
                  style={{ display: 'none' }}
                  ref={el => { fileInputRefs.current[doc._id] = el }}
                  onChange={e => {
                    const file = e.target.files?.[0]
                    if (file) handleFileUpload(doc, file)
                    e.target.value = ''
                  }}
                />
                <div
                  onClick={() => !fetchingIds.has(doc._id) && fileInputRefs.current[doc._id]?.click()}
                  onDragOver={e => { e.preventDefault(); setDragOver(doc._id) }}
                  onDragLeave={() => setDragOver(null)}
                  onDrop={e => {
                    e.preventDefault(); setDragOver(null)
                    const file = e.dataTransfer.files?.[0]
                    if (file) handleFileUpload(doc, file)
                  }}
                  style={{
                    border: `2px dashed ${dragOver === doc._id ? 'var(--accent)' : 'rgba(255,255,255,0.15)'}`,
                    borderRadius: '10px',
                    padding: '2rem',
                    textAlign: 'center',
                    cursor: fetchingIds.has(doc._id) ? 'wait' : 'pointer',
                    transition: 'border-color 0.2s, background 0.2s',
                    background: dragOver === doc._id ? 'rgba(99,102,241,0.08)' : 'transparent',
                  }}
                >
                  {fetchingIds.has(doc._id) ? (
                    <div className="flex items-center justify-center gap-2" style={{ color: 'var(--accent-light)' }}>
                      <Loader size={18} className="spin" /><span>Parsing file…</span>
                    </div>
                  ) : doc.text.trim().length > 50 ? (
                    <div>
                      <p style={{ color: 'var(--green, #4ade80)', fontWeight: 600 }}>
                        ✓ {doc.text.trim().split(/\s+/).length} words extracted
                      </p>
                      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
                        Click or drop a new file to replace
                      </p>
                    </div>
                  ) : (
                    <div>
                      <Upload size={28} style={{ color: 'var(--accent-light)', margin: '0 auto 0.6rem' }} />
                      <p style={{ fontWeight: 600, marginBottom: '0.3rem' }}>Drop PDF or DOCX here</p>
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>or click to browse · max 50 MB</p>
                    </div>
                  )}
                </div>
                {fetchErrors[doc._id] && (
                  <p style={{ color: 'var(--red)', fontSize: '0.8rem', marginTop: '0.5rem' }}>{fetchErrors[doc._id]}</p>
                )}
              </div>
            )}

            {/* ── Text paste mode ── */}
            {doc.inputMode === 'text' && (
              <textarea
                placeholder="Paste document text here (minimum 50 characters)…"
                rows={6}
                value={doc.text}
                onChange={e => updateDoc(doc._id, { text: e.target.value })}
              />
            )}

            {doc.text.trim().length > 10 && doc.inputMode !== 'file' && (
              <div className="flex items-center gap-2 mt-2">
                <span className="text-xs text-muted">{doc.text.trim().split(/\s+/).length} words</span>
                <span className="badge badge-blue text-xs">{doc.doc_type?.replace(/_/g, ' ') || 'auto-detect'}</span>
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>

      <button className="btn btn-ghost w-full mb-6" onClick={() => setDocs(d => [...d, emptyDoc()])}>
        <Plus size={16} /> Add Document
      </button>

      {/* ── Settings ──────────────────────────────────── */}
      <div className="card mb-6">
        <h3 className="mb-4">Settings</h3>
        <div className="grid-2" style={{ marginBottom: '1.2rem' }}>
          <div>
            <label className="text-sm text-secondary mb-2" style={{ display: 'block' }}>Summarizer Backend</label>
            <select value={backend} onChange={e => setBackend(e.target.value as any)}>
              <option value="rag">RAG (GPT-4o-mini + FAISS)</option>
              <option value="bart">BART (Offline)</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-secondary mb-2" style={{ display: 'block' }}>Conflict Strategy</label>
            <select value={strategy} onChange={e => setStrategy(e.target.value)}>
              {STRATEGIES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="text-sm text-secondary mb-2" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Layers size={14} /> Summary Depth
          </label>
          <div className="depth-selector">
            {DEPTH_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                className={`depth-option${depth === opt.value ? ' depth-option--active' : ''}`}
                onClick={() => setDepth(opt.value as typeof depth)}
              >
                <span className="depth-label">{opt.label}</span>
                <span className="depth-desc">{opt.desc}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Error ─────────────────────────────────────── */}
      {error && (
        <div className="card mb-4" style={{ borderColor: 'rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.06)' }}>
          <p style={{ color: 'var(--red)', fontSize: '0.9rem' }}>{error}</p>
        </div>
      )}

      {/* ── Job progress ──────────────────────────────── */}
      {loading && jobId && (
        <div className="card mb-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm" style={{ fontWeight: 600 }}>
              {jobStatus === 'pending' ? '⏳ Queued…' : jobStatus === 'running' ? '🔄 Processing…' : '✅ Finalising…'}
            </span>
            <span className="badge badge-blue mono">{jobId.slice(0, 8)}</span>
          </div>
          <div className="progress-bar">
            <motion.div
              className="progress-bar-fill"
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 0.8, ease: 'easeInOut' }}
            />
          </div>
          <p className="text-xs text-muted mt-2">Classify → Score → Resolve conflicts → Summarise</p>
        </div>
      )}

      {/* ── Submit ────────────────────────────────────── */}
      <button className="btn btn-primary w-full" style={{ padding: '0.85rem', fontSize: '1rem' }} onClick={handleSubmit} disabled={loading}>
        {loading ? 'Processing…' : <><Zap size={18} /> Run Summarization</>}
      </button>
    </div>
  )
}
