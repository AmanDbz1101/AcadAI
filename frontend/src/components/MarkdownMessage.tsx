import { useMemo } from 'react'

interface MarkdownMessageProps {
  content: string
  role: 'user' | 'assistant'
}

export const MarkdownMessage = ({
  content,
  role = 'assistant',
}: MarkdownMessageProps) => {
  const parsedContent = useMemo(() => {
    if (role === 'user') {
      return <p className="whitespace-pre-wrap">{content}</p>
    }

    const normalizedContent = normalizeListLikeContent(content)
    const lines = normalizedContent.split('\n')
    const elements: JSX.Element[] = []
    let currentList: string[] = []
    let listType: 'ordered' | 'unordered' | null = null

    const flushList = () => {
      if (currentList.length > 0) {
        const ListTag = listType === 'ordered' ? 'ol' : 'ul'
        const key = `list-${elements.length}`

        elements.push(
          <ListTag
            key={key}
            className={`${
              listType === 'ordered'
                ? 'list-decimal pl-5 space-y-1'
                : 'list-disc pl-5 space-y-1'
            } my-2`}
          >
            {currentList.map((item, idx) => (
              <li key={`item-${idx}`} className="text-[13px]">
                {item}
              </li>
            ))}
          </ListTag>,
        )
        currentList = []
        listType = null
      }
    }

    lines.forEach((line, idx) => {
      const trimmed = line.trim()

      // Detect ordered list (1., 2., 3., etc.)
      const orderedMatch = trimmed.match(/^(\d+)\.\s+(.*)$/)
      if (orderedMatch) {
        if (listType !== 'ordered') {
          flushList()
          listType = 'ordered'
        }
        currentList.push(orderedMatch[2])
        return
      }

      // Detect unordered list (-, *, •)
      const unorderedMatch = trimmed.match(/^[-*•]\s+(.*)$/)
      if (unorderedMatch) {
        if (listType !== 'unordered') {
          flushList()
          listType = 'unordered'
        }
        currentList.push(unorderedMatch[1])
        return
      }

      // Handle other content
      flushList()

      if (!trimmed) {
        elements.push(<div key={`empty-${idx}`} className="h-2" />)
        return
      }

      // Handle bold **text** and italic *text*
      const formattedLine = formatInlineMarkdown(trimmed)

      // Handle headers
      const headerMatch = trimmed.match(/^(#+)\s+(.*)$/)
      if (headerMatch) {
        const level = headerMatch[1].length
        const text = headerMatch[2]
        const HeaderTag = `h${Math.min(level + 3, 6)}` as
          | 'h4'
          | 'h5'
          | 'h6'
        const headerClasses = `font-semibold my-2 ${
          level === 1
            ? 'text-[15px]'
            : level === 2
              ? 'text-[14px]'
              : 'text-[13px]'
        }`

        elements.push(
          <HeaderTag key={`header-${idx}`} className={headerClasses}>
            {formattedLine}
          </HeaderTag>,
        )
        return
      }

      elements.push(
        <p key={`p-${idx}`} className="text-[13px] leading-relaxed">
          {formattedLine}
        </p>,
      )
    })

    flushList()
    return <div className="space-y-2">{elements}</div>
  }, [content, role])

  return <div className="markdown-content">{parsedContent}</div>
}

function normalizeListLikeContent(raw: string): string {
  if (!raw) return raw

  // Convert inline numbered list patterns into newline-separated lines.
  let normalized = raw.replace(/\s+(\d+\.\s+)/g, '\n$1')

  // Convert inline bullet markers into newline-separated lines.
  normalized = normalized.replace(/\s+([*-]\s+)/g, '\n$1')

  return normalized
}

function formatInlineMarkdown(text: string): JSX.Element | string {
  const parts: (JSX.Element | string)[] = []
  let lastIndex = 0

  // Match **bold** and *italic* and `code`
  const regex = /\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`/g
  let match

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }

    if (match[1]) {
      // Bold
      parts.push(
        <strong key={`bold-${match.index}`} className="font-semibold">
          {match[1]}
        </strong>,
      )
    } else if (match[2]) {
      // Italic
      parts.push(
        <em key={`italic-${match.index}`} className="italic">
          {match[2]}
        </em>,
      )
    } else if (match[3]) {
      // Code
      parts.push(
        <code
          key={`code-${match.index}`}
          className="bg-accent/10 px-1.5 py-0.5 rounded font-mono text-[12px]"
        >
          {match[3]}
        </code>,
      )
    }

    lastIndex = regex.lastIndex
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts.length > 0 ? <>{parts}</> : text
}
