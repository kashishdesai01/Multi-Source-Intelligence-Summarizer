import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { FileText, History, Info, Sparkles } from 'lucide-react'
import SubmitPage from './pages/SubmitPage'
import HistoryPage from './pages/HistoryPage'
import ReportPage from './pages/ReportPage'
import DocTypesPage from './pages/DocTypesPage'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="layout">
          {/* ── Sidebar ─────────────────────────────── */}
          <aside className="sidebar">
            <div className="flex items-center gap-2 mb-6" style={{ padding: '0 0.5rem' }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: 'linear-gradient(135deg, #6366f1, #a78bfa)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <Sparkles size={16} color="#fff" />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.95rem', lineHeight: 1.2 }}>MultiDoc</div>
                <div className="text-muted text-xs">Summarizer</div>
              </div>
            </div>

            <div className="divider" />

            <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <FileText size={16} /> Summarize
            </NavLink>
            <NavLink to="/history" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <History size={16} /> History
            </NavLink>
            <NavLink to="/doc-types" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Info size={16} /> Doc Types
            </NavLink>

            <div style={{ flex: 1 }} />
            <div className="text-xs text-muted" style={{ padding: '0 0.5rem' }}>
              v1.0.0 · Agentic RAG
            </div>
          </aside>

          {/* ── Page content ────────────────────────── */}
          <main className="main-content">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
            >
              <Routes>
                <Route path="/" element={<SubmitPage />} />
                <Route path="/history" element={<HistoryPage />} />
                <Route path="/reports/:reportId" element={<ReportPage />} />
                <Route path="/doc-types" element={<DocTypesPage />} />
              </Routes>
            </motion.div>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
