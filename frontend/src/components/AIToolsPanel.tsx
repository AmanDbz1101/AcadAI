import InsightExtractor from './InsightExtractor'
import ChatAssistant from './ChatAssistant'
import type {
  PaperImage,
  PaperSection,
  PaperSummary,
  TechnicalTerm,
} from '@/types/api'

interface AIToolsPanelProps {
  paper: PaperSummary | null
  sections: PaperSection[]
  images: PaperImage[]
  technicalTerms: TechnicalTerm[]
}

const AIToolsPanel = ({
  paper,
  sections,
  images,
  technicalTerms,
}: AIToolsPanelProps) => {
  return (
    <aside className="w-[300px] min-w-[300px] bg-panel h-screen sticky top-0 flex flex-col border-l border-border/40">
      <div className="px-5 pt-8 pb-2 flex-shrink-0">
        <InsightExtractor
          paperId={paper?.id ?? null}
          sections={sections}
          images={images}
          technicalTerms={technicalTerms}
        />
      </div>
      <div className="flex-1 min-h-0 px-5 pb-5 flex flex-col">
        <ChatAssistant />
      </div>
    </aside>
  )
}

export default AIToolsPanel
