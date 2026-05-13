import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownMessageProps {
  content: string
  role: 'user' | 'assistant'
}

function normalizeAssistantMarkdown(content: string): string {
  return content.replace(/^>\s*[💡⚠️📚]\s*/gm, '> ')
}

export function MarkdownMessage({ content, role }: MarkdownMessageProps) {
  if (role === 'user') {
    return (
      <p className="text-sm whitespace-pre-wrap break-words">{content}</p>
    )
  }

  const normalizedContent = normalizeAssistantMarkdown(content)

  return (
    <div className="markdown-body text-sm">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-base font-bold mt-3 mb-1">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-bold mt-3 mb-1">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold mt-2 mb-1 text-gray-700 dark:text-gray-300">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="mb-2 leading-relaxed">{children}</p>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-gray-900 dark:text-gray-100">
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em className="italic text-gray-700 dark:text-gray-300">
              {children}
            </em>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-inside space-y-1 mb-2 ml-2 text-sm">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1 mb-2 ml-2 text-sm">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed">{children}</li>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-blue-400 pl-3 py-1 my-2 bg-blue-50 dark:bg-blue-950/30 rounded-r text-xs text-gray-600 dark:text-gray-400 italic">
              {children}
            </blockquote>
          ),
          code: ({ children, className }) => {
            const isBlock = className?.includes('language-')
            if (isBlock) {
              return (
                <pre className="bg-gray-100 dark:bg-gray-800 rounded p-2 my-2 text-xs overflow-x-auto">
                  <code>{children}</code>
                </pre>
              )
            }

            return (
              <code className="bg-gray-100 dark:bg-gray-800 rounded px-1 py-0.5 text-xs font-mono">
                {children}
              </code>
            )
          },
          hr: () => <hr className="border-gray-200 dark:border-gray-700 my-2" />,
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  )
}