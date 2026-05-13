import { useState, useRef, useEffect, useMemo } from 'react'
import { Maximize2, Minimize2, Send } from 'lucide-react'
import type { PaperSection } from '@/types/api'
import { chatWithPaper } from '@/lib/api'
import { MarkdownMessage } from './MarkdownMessage'
import { SourceSections } from './SourceSections'

interface ChatSource {
  section_title: string
  section_id?: string
  page_start?: number
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  source_sections?: string[]
}

const initialMessages: Message[] = []

interface ChatAssistantProps {
  paperId: number | null
  sections: PaperSection[]
  onSourceClick?: (source: ChatSource) => void
  activeSection?: string
}

const ChatAssistant = ({ paperId, sections, onSourceClick, activeSection }: ChatAssistantProps) => {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [selectedSections, setSelectedSections] = useState<string[]>([])
  const [autoSelectedSection, setAutoSelectedSection] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const sectionNames = useMemo(
    () =>
      Array.from(
        new Set(
          sections
            .map((section) => (section.title || '').trim())
            .filter(Boolean),
        ),
      ),
    [sections],
  )

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  useEffect(() => {
    if (!isFullscreen) return

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsFullscreen(false)
      }
    }

    window.addEventListener('keydown', handleEsc)

    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleEsc)
    }
  }, [isFullscreen])

  useEffect(() => {
    setSelectedSections([])
  }, [paperId])

  useEffect(() => {
    if (!activeSection) return

    const matchedSection = sections.find((section) => section.id === activeSection)
    const sectionTitle = (matchedSection?.title || '').trim()
    if (!sectionTitle) return

    setAutoSelectedSection(sectionTitle)
    setSelectedSections([sectionTitle])
  }, [activeSection, sections])

  const toggleSection = (sectionName: string) => {
    setSelectedSections((prev) =>
      prev.includes(sectionName)
        ? prev.filter((item) => item !== sectionName)
        : [...prev, sectionName],
    )
  }

  const handleSend = async (text?: string) => {
    const msg = (text ?? input).trim()
    if (!msg || isTyping || !paperId) return

    const userMsg: Message = { role: 'user', content: msg }
    const nextMessages = [...messages, userMsg]
    setMessages(nextMessages)
    setInput('')
    setIsTyping(true)

    try {
      const response = await chatWithPaper(paperId, {
        messages: nextMessages,
        allowed_sections: selectedSections.length > 0 ? selectedSections : null,
      })

      const assistantMessage: Message = {
        role: 'assistant',
        content: response.message || response.assistant_message || 'No response received.',
        sources: response.sources?.filter((source) => source.section_title) || [],
        source_sections: response.source_sections || [],
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      const assistantError: Message = {
        role: 'assistant',
        content:
          error instanceof Error
            ? `Failed to get response: ${error.message}`
            : 'Failed to get response from server.',
      }
      setMessages((prev) => [...prev, assistantError])
    } finally {
      setIsTyping(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <>
      {isFullscreen ? (
        <div
          className="fixed inset-0 z-[998] bg-black/35 backdrop-blur-[1px]"
          onClick={() => setIsFullscreen(false)}
        />
      ) : null}

      <div
        className={`flex flex-col min-h-0 rounded-xl border border-accent/30 bg-canvas shadow-sm overflow-hidden ${
          isFullscreen
            ? 'fixed inset-y-4 inset-x-12 z-[999] border-2 border-accent/40 shadow-2xl md:inset-x-20'
            : 'h-full'
        }`}
      >
        <div className="flex items-center justify-between gap-3 px-3 py-2.5 border-b border-accent/20 bg-gradient-to-r from-accent/10 via-accent/5 to-transparent">
          <h3 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-foreground">
            Research Q&A
          </h3>
          <button
            type="button"
            onClick={() => setIsFullscreen((prev) => !prev)}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border/60 bg-canvas text-text-secondary hover:text-foreground hover:border-accent/40 transition-colors"
            aria-label={
              isFullscreen ? 'Exit fullscreen chat' : 'Fullscreen chat'
            }
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>

        {/* Messages */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-3 bg-gradient-to-b from-canvas to-panel/30"
        >
          <div className="space-y-3">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`animate-message-in ${
                  msg.role === 'user'
                    ? 'flex justify-end'
                    : 'flex justify-start'
                }`}
              >
                <div
                  className={`
                max-w-[90%] px-3 py-2.5 font-ui text-[13px] leading-relaxed
                ${
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground rounded-lg rounded-br-sm'
                    : 'bg-panel border border-border/60 text-foreground rounded-lg rounded-bl-sm shadow-sm'
                }
              `}
                >
                  {msg.role === 'assistant' && msg.source_sections && msg.source_sections.length > 0 ? (
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {msg.source_sections.slice(0, 2).map((section, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-800 text-green-100 border border-green-600"
                        >
                          {section}
                        </span>
                      ))}
                    </div>
                  ) : msg.role === 'assistant' ? (
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-700 text-gray-200 border border-gray-600">
                        Section unknown
                      </span>
                    </div>
                  ) : null}
                  <MarkdownMessage content={msg.content} role={msg.role} />
                  {msg.role === 'assistant' && msg.sources?.length ? (
                    <SourceSections sections={msg.sources} onSectionClick={onSourceClick} />
                  ) : null}
                </div>
              </div>
            ))}

            {isTyping && (
              <div className="flex justify-start animate-message-in">
                <div className="bg-panel border border-border/60 px-3 py-2.5 rounded-lg rounded-bl-sm shadow-sm">
                  <span className="font-ui text-[13px] text-text-secondary flex items-center gap-1.5">
                    <span className="flex gap-0.5">
                      <span
                        className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce"
                        style={{ animationDelay: '0ms' }}
                      />
                      <span
                        className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce"
                        style={{ animationDelay: '150ms' }}
                      />
                      <span
                        className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce"
                        style={{ animationDelay: '300ms' }}
                      />
                    </span>
                    Analyzing…
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="px-3 pt-2">
          <p className="mb-2 font-ui text-[11px] tracking-[0.08em] uppercase text-text-secondary/80">
            Focus on sections (optional)
          </p>
          <div className="flex flex-wrap gap-2">
            {sectionNames.map((sectionName) => {
              const isSelected = selectedSections.includes(sectionName)
              const isAutoSelected = autoSelectedSection === sectionName && isSelected
              return (
                <button
                  key={sectionName}
                  type="button"
                  onClick={() => toggleSection(sectionName)}
                  className={`rounded-full border px-3 py-1 font-ui text-[12px] transition-colors ${
                    isSelected
                      ? 'border-accent/70 bg-accent/20 text-foreground'
                      : 'border-border/70 bg-panel/70 text-text-secondary hover:text-foreground hover:border-accent/40'
                  }`}
                >
                    {isAutoSelected ? (
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                    ) : null}
                  {sectionName}
                </button>
              )
            })}
          </div>
        </div>

        {/* Input */}
        <div className="m-3 mt-2 flex items-center gap-2 bg-panel border border-border/60 rounded-lg p-1.5 transition-all duration-200 focus-within:border-accent/30">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about this paper…"
            className="flex-1 bg-transparent font-ui text-[13px] text-foreground placeholder:text-text-secondary/80 outline-none px-2 py-1"
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || isTyping || !paperId}
            className="p-2 rounded-md text-primary-foreground bg-primary border border-primary/70 hover:bg-primary/90 disabled:opacity-50 disabled:bg-primary/40 disabled:text-primary-foreground/80 transition-all duration-200 shadow-sm"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </>
  )
}

export default ChatAssistant
