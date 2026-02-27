import { useState, useRef, useEffect } from 'react'
import { askQuestion, type QAResponse } from '../api'
import { MessageSquare, Send, Loader2, BookOpen, ChevronDown, ChevronUp } from 'lucide-react'

interface QAPanelProps {
  reportId: string
  docTypes?: string[]
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations?: string[]
}

export default function QAPanel({ reportId, docTypes = [] }: QAPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(true)
  const endRef = useRef<HTMLDivElement>(null)

  const isLegal = docTypes.some(t => t === 'legal_document')

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || loading) return

    const question = input.trim()
    setInput('')
    setError(null)
    setMessages(prev => [...prev, { role: 'user', content: question }])
    setLoading(true)

    try {
      const res: QAResponse = await askQuestion({ report_id: reportId, question })
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: res.answer, citations: res.citations },
      ])
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Failed to get answer. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const suggestions = isLegal
    ? [
        'What are the key obligations of each party?',
        'What are the termination conditions?',
        'Are there any indemnification clauses?',
      ]
    : [
        'What is the main finding of this document?',
        'What methodology was used?',
        'Are there any limitations mentioned?',
      ]

  return (
    <div className="qa-panel">
      {/* Header */}
      <button
        className="qa-header"
        onClick={() => setIsExpanded(e => !e)}
        aria-expanded={isExpanded}
      >
        <div className="qa-header-left">
          <MessageSquare size={18} className="qa-icon" />
          <span>Ask a Question</span>
          {isLegal && <span className="qa-badge">Legal Q&amp;A</span>}
        </div>
        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {isExpanded && (
        <div className="qa-body">
          {/* Suggestions (shown only when no messages yet) */}
          {messages.length === 0 && (
            <div className="qa-suggestions">
              <p className="qa-suggestions-label">
                <BookOpen size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
                Suggested questions
              </p>
              <div className="qa-suggestion-pills">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    className="qa-suggestion-pill"
                    onClick={() => setInput(s)}
                    type="button"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.length > 0 && (
            <div className="qa-messages">
              {messages.map((msg, i) => (
                <div key={i} className={`qa-message qa-message--${msg.role}`}>
                  <div className="qa-message-content">{msg.content}</div>
                  {msg.citations && msg.citations.length > 0 && msg.role === 'assistant' && (
                    <div className="qa-citations">
                      <span className="qa-citations-label">Sources:</span>
                      {msg.citations.map((c, j) => (
                        <span key={j} className="qa-citation-chip">{c}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="qa-message qa-message--assistant qa-message--loading">
                  <Loader2 size={16} className="qa-loading-spinner" />
                  <span>Analyzing documents…</span>
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}

          {/* Error */}
          {error && <p className="qa-error">{error}</p>}

          {/* Input */}
          <form className="qa-form" onSubmit={handleSubmit}>
            <input
              className="qa-input"
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={isLegal ? 'Ask about this legal document…' : 'Ask anything about these documents…'}
              disabled={loading}
            />
            <button
              className="qa-submit"
              type="submit"
              disabled={!input.trim() || loading}
              aria-label="Send question"
            >
              {loading ? <Loader2 size={16} className="qa-loading-spinner" /> : <Send size={16} />}
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
