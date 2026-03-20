import { useState, useRef, useEffect } from "react";
import { Send, Sparkles } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const initialMessages: Message[] = [
  {
    role: "assistant",
    content: "Hi! I've read through this paper on hierarchical attention mechanisms. Ask me about any section — I can explain concepts, compare findings, or help you identify key takeaways.",
  },
];

const mockResponses: Record<string, string> = {
  default:
    "The paper proposes a hierarchical attention mechanism that combines local windowed attention with global summary tokens. This achieves near-linear complexity — O(n·(w+k)) instead of O(n²) — by exploiting the observation that most language dependencies are local. The approach reduces training time by 35-60% while maintaining performance within 0.3% of full-attention baselines.",
};

const suggestedQuestions = [
  "What's the main contribution?",
  "Explain the methodology",
  "Summarize the results",
];

const ChatAssistant = () => {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isTyping) return;

    const userMsg: Message = { role: "user", content: msg };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    setTimeout(() => {
      const response: Message = {
        role: "assistant",
        content: mockResponses.default,
      };
      setMessages((prev) => [...prev, response]);
      setIsTyping(false);
    }, 1200);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <h3 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary mb-3 flex items-center gap-1.5">
        <Sparkles size={13} className="text-text-active" />
        Research Q&A
      </h3>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scrollbar-thin space-y-3 mb-3 min-h-0"
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`animate-message-in ${
              msg.role === "user" ? "flex justify-end" : "flex justify-start"
            }`}
          >
            <div
              className={`
                max-w-[90%] px-3 py-2.5 font-ui text-[13px] leading-relaxed
                ${msg.role === "user"
                  ? "bg-primary text-primary-foreground rounded-lg rounded-br-sm"
                  : "bg-canvas border border-border/50 text-foreground rounded-lg rounded-bl-sm"
                }
              `}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {/* Suggested questions - only show when few messages */}
        {messages.length <= 1 && !isTyping && (
          <div className="flex flex-wrap gap-1.5 pt-1 animate-fade-in">
            {suggestedQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSend(q)}
                className="font-ui text-[11px] px-2.5 py-1.5 rounded-md border border-border/60 text-text-secondary hover:text-text-active hover:border-primary/40 transition-all duration-200"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {isTyping && (
          <div className="flex justify-start animate-message-in">
            <div className="bg-canvas border border-border/50 px-3 py-2.5 rounded-lg rounded-bl-sm">
              <span className="font-ui text-[13px] text-text-secondary flex items-center gap-1.5">
                <span className="flex gap-0.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
                Analyzing…
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 bg-canvas border border-border/50 rounded-lg p-1.5 focus-within:border-primary/40 transition-colors">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about this paper…"
          className="flex-1 bg-transparent font-ui text-[13px] text-foreground placeholder:text-text-secondary/70 outline-none px-2 py-1"
        />
        <button
          onClick={() => handleSend()}
          disabled={!input.trim() || isTyping}
          className="p-1.5 rounded-md text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-30 disabled:bg-transparent disabled:text-text-secondary transition-all"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
};

export default ChatAssistant;
