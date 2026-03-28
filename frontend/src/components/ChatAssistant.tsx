import { useState, useRef, useEffect } from 'react'
import { Maximize2, Minimize2, Send } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const initialMessages: Message[] = []

const mockResponses: Record<string, string> = {
  default:
    'The paper proposes a hierarchical attention mechanism that combines local windowed attention with global summary tokens. This achieves near-linear complexity — O(n·(w+k)) instead of O(n²) — by exploiting the observation that most language dependencies are local. The approach reduces training time by 35-60% while maintaining performance within 0.3% of full-attention baselines.',
}

const ChatAssistant = () => {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

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

  const handleSend = (text?: string) => {
    const msg = (text ?? input).trim()
    if (!msg || isTyping) return

    const userMsg: Message = { role: 'user', content: msg }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsTyping(true)

    setTimeout(() => {
      const response: Message = {
        role: 'assistant',
        content: mockResponses.default,
      }
      setMessages((prev) => [...prev, response])
      setIsTyping(false)
    }, 1200)
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
                  {msg.content}
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
            disabled={!input.trim() || isTyping}
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
