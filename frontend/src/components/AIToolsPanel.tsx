import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import InsightExtractor from './InsightExtractor'
import ChatAssistant from './ChatAssistant'
import type {
  PaperImage,
  PaperSection,
  PaperSummary,
  PaperTable,
  TechnicalTerm,
} from '@/types/api'

type ActiveTool = 'insight-extractor' | 'research-qa'

interface AIToolsPanelProps {
  paper: PaperSummary | null
  sections: PaperSection[]
  images: PaperImage[]
  technicalTerms: TechnicalTerm[]
  selectedPdfTerms: string[]
  tables: PaperTable[]
  activeTool: ActiveTool
  onToolChange: (tool: ActiveTool) => void
  onSourceClick?: (source: { section_title: string; section_id?: string; page_start?: number }) => void
  activeSection?: string
  style?: React.CSSProperties
}

const AIToolsPanel = ({
  paper,
  sections,
  images,
  technicalTerms,
  selectedPdfTerms,
  tables,
  activeTool,
  onToolChange,
  onSourceClick,
  activeSection,
  style,
}: AIToolsPanelProps) => {
  const isInsightExtractor = activeTool === 'insight-extractor'
  const isResearchQa = activeTool === 'research-qa'

  const toolButtons = useMemo(
    () => [
      {
        id: 'insight-extractor' as const,
        label: 'Insight Extractor',
      },
      {
        id: 'research-qa' as const,
        label: 'Research QA',
      },
    ],
    [],
  )

  return (
    <aside className="h-full flex flex-col" style={style}>
      <div className="relative z-0 flex-1 min-h-0 overflow-hidden px-5 pt-4 pb-5 bg-gradient-to-b from-accent/5 via-panel to-canvas/40">
        <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-accent/20 bg-canvas shadow-sm">
          <div className="flex items-center gap-2 border-b border-accent/20 bg-gradient-to-r from-accent/10 via-accent/5 to-transparent p-2">
            {toolButtons.map((button) => {
              const active = activeTool === button.id
              return (
                <button
                  key={button.id}
                  type="button"
                  onClick={() => onToolChange(button.id)}
                  className={cn(
                    'flex-1 rounded-md px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] transition-colors',
                    active
                      ? 'bg-canvas text-foreground shadow-sm border border-accent/30'
                      : 'text-text-secondary hover:text-foreground hover:bg-canvas/70',
                  )}
                  aria-pressed={active}
                >
                  {button.label}
                </button>
              )
            })}
          </div>

          <div className="flex-1 min-h-0 overflow-hidden">
            {isInsightExtractor ? (
              <InsightExtractor
                paperId={paper?.id ?? null}
                sections={sections}
                images={images}
                technicalTerms={technicalTerms}
                selectedPdfTerms={selectedPdfTerms}
              />
            ) : null}

            {isResearchQa ? (
              <div className="h-full min-h-0">
                <ChatAssistant
                  paperId={paper?.id ?? null}
                  sections={sections}
                  onSourceClick={onSourceClick}
                  activeSection={activeSection}
                />
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </aside>
  )
}

export default AIToolsPanel
