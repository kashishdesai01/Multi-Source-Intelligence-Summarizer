import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { getDocTypes } from '../api'
import type { DocTypeInfo } from '../api'

const COLOR_MAP: Record<string, string> = {
  research_paper: 'var(--purple)',
  news_article: 'var(--blue)',
  blog_post: 'var(--text-secondary)',
  legal_document: 'var(--yellow)',
}

const ICON_MAP: Record<string, string> = {
  research_paper: '🔬', news_article: '📰', blog_post: '✍️', legal_document: '⚖️',
}

export default function DocTypesPage() {
  const { data: types, isLoading } = useQuery<DocTypeInfo[]>({
    queryKey: ['doc-types'],
    queryFn: getDocTypes,
  })

  if (isLoading) return (
    <div style={{ display: 'flex', justifyContent: 'center', marginTop: '5rem' }}>
      <div className="progress-bar" style={{ width: 200 }}>
        <motion.div className="progress-bar-fill" animate={{ width: ['0%', '100%'] }} transition={{ duration: 1.5, repeat: Infinity }} />
      </div>
    </div>
  )

  return (
    <div>
      <div className="mb-6">
        <h1 className="glow-text">Document Types</h1>
        <p className="mt-2">Each document type uses a distinct credibility scoring formula and conflict resolution strategy.</p>
      </div>

      <div className="flex flex-col gap-5">
        {(types || []).map((t, i) => (
          <motion.div
            key={t.doc_type}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
            className="card"
          >
            <div className="flex items-center gap-3 mb-4">
              <div style={{
                width: 44, height: 44, borderRadius: 10, fontSize: '1.4rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--bg-elevated)', flexShrink: 0,
              }}>
                {ICON_MAP[t.doc_type] || '📄'}
              </div>
              <div>
                <h3 style={{ color: COLOR_MAP[t.doc_type] || 'var(--text-primary)' }}>
                  {t.doc_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className="badge badge-gray text-xs">Default strategy: {t.default_strategy.replace(/_/g, ' ')}</span>
                </div>
              </div>
            </div>

            <div className="divider mb-4" />

            <div className="text-xs text-muted mb-2" style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>Credibility Signals</div>
            <div className="flex flex-col gap-2">
              {t.credibility_signals.map((sig, j) => (
                <div key={j} className="flex items-center justify-between" style={{
                  padding: '0.6rem 0.9rem', borderRadius: 'var(--radius-sm)',
                  background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)',
                }}>
                  <span className="text-sm">{sig.signal}</span>
                  <span className="badge badge-gray mono" style={{ fontWeight: 700 }}>{sig.weight}</span>
                </div>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
