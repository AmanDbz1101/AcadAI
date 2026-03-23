import { useMemo, useState } from 'react'
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

  return (
    <div className="mb-6">
      <h3 className="font-ui text-xs font-medium uppercase tracking-[0.15em] text-text-secondary mb-4">
        Insight Extractor
      </h3>

      {/* Tabs */}
      <div className="flex gap-1 mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`
              font-ui text-[12px] py-1.5 px-3 rounded-sm transition-all duration-200
              ${
                activeTab === tab.key
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'text-text-secondary hover:text-foreground'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Cards */}
      <div className="space-y-2">
        {insightData[activeTab].map((item, i) => (
          <div
            key={i}
            className="p-3 rounded-sm bg-canvas animate-fade-in"
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
  )
}

export default InsightExtractor
