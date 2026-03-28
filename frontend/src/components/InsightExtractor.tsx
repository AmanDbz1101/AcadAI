import { useEffect, useMemo, useState } from 'react'
import { Maximize2, Minimize2 } from 'lucide-react'
import type {
  PaperImage,
  PaperSection,
  PaperSummary,
  PaperTable,
} from '@/types/api'

type TabKey = 'terms' | 'figures' | 'answers'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'terms', label: 'Technical Terms' },
  { key: 'figures', label: 'Figures' },
  { key: 'answers', label: 'Answers' },
]

interface InsightExtractorProps {
  paper: PaperSummary | null
  sections: PaperSection[]
  images: PaperImage[]
  tables: PaperTable[]
}

const TERM_STOPWORDS = new Set([
  'the',
  'and',
  'for',
  'with',
  'this',
  'that',
  'from',
  'into',
  'their',
  'are',
  'our',
  'using',
  'used',
  'based',
  'method',
  'methods',
  'result',
  'results',
  'study',
  'paper',
])

function extractTechnicalTerms(sections: PaperSection[]): string[] {
  const corpus = sections.map((s) => `${s.title} ${s.content}`).join(' ')
  if (!corpus.trim()) return []

  const candidates = corpus.match(/\b[A-Z][a-zA-Z]{3,}\b|\b[A-Z]{2,}\b/g) || []
  const score = new Map<string, number>()
  candidates.forEach((token) => {
    const clean = token.trim()
    const normalized = clean.toLowerCase()
    if (TERM_STOPWORDS.has(normalized)) return
    if (/^\d/.test(clean)) return
    score.set(clean, (score.get(clean) || 0) + 1)
  })

  return Array.from(score.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8)
    .map(([term]) => term)
}

const InsightExtractor = ({
  paper,
  sections,
  images,
  tables,
}: InsightExtractorProps) => {
  const insightData = useMemo<
    Record<TabKey, { title: string; description: string }[]>
  >(() => {
    const terms = extractTechnicalTerms(sections)

    const termCards = terms.length
      ? terms.map((term) => ({
          title: term,
          description:
            'Detected from section titles/content stored in the paper bundle.',
        }))
      : [
          {
            title: 'No technical terms yet',
            description:
              'Terms will appear when section content is available from the backend.',
          },
        ]

    const figureCards = images.length
      ? images.slice(0, 8).map((img, idx) => ({
          title: `Figure ${idx + 1} · Page ${img.page_number ?? '?'}`,
          description: img.caption || img.image_path || 'Stored image asset',
        }))
      : [
          {
            title: 'No figures',
            description: 'No stored figures for this paper.',
          },
        ]

    const answerCards = [
      {
        title: 'What is this paper about?',
        description:
          paper?.title ||
          paper?.paper_name ||
          'Title metadata is not available for this paper.',
      },
      {
        title: 'How much structured content is stored?',
        description: `${sections.length} sections, ${images.length} figures, ${tables.length} tables loaded from PostgreSQL.`,
      },
      {
        title: 'What should I read first?',
        description: sections[0]?.title
          ? `Start with "${sections[0].title}" and continue in section order from the navigation panel.`
          : 'Section data is still loading or unavailable.',
      },
    ]

    return {
      terms: termCards,
      figures: figureCards,
      answers: answerCards,
    }
  }, [paper, sections, images, tables])

  const [activeTab, setActiveTab] = useState<TabKey>('terms')
  const [isFullscreen, setIsFullscreen] = useState(false)

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
            Insight Extractor
          </h3>
          <button
            type="button"
            onClick={() => setIsFullscreen((prev) => !prev)}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border/60 bg-canvas text-text-secondary hover:text-foreground hover:border-accent/40 transition-colors"
            aria-label={
              isFullscreen
                ? 'Exit fullscreen insight extractor'
                : 'Fullscreen insight extractor'
            }
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>

        <div className="flex-1 min-h-0 p-3 bg-gradient-to-b from-canvas to-panel/30 flex flex-col">
          {/* Tabs */}
          <div className="flex gap-1 mb-4 flex-shrink-0">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`
              font-ui text-[12px] py-1.5 px-3 rounded-md border transition-all duration-200
              ${
                activeTab === tab.key
                  ? 'bg-primary text-primary-foreground border-primary/70 font-medium shadow-sm'
                  : 'text-text-secondary border-border/60 bg-panel hover:text-foreground hover:border-accent/30'
              }
            `}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Cards */}
          <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2">
            {insightData[activeTab].map((item, i) => (
              <div
                key={i}
                className="p-3 rounded-lg border border-border/60 bg-panel animate-fade-in shadow-sm"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <h4 className="font-ui text-[13px] font-medium text-foreground mb-1">
                  {item.title}
                </h4>
                <p className="font-ui text-[12px] text-text-secondary leading-relaxed">
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}

export default InsightExtractor
