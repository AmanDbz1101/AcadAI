import InsightExtractor from './InsightExtractor'
import ChatAssistant from './ChatAssistant'
import type {
  PaperImage,
  PaperSection,
  PaperSummary,
  PaperTable,
} from '@/types/api'

interface AIToolsPanelProps {
  paper: PaperSummary | null
  sections: PaperSection[]
  images: PaperImage[]
  tables: PaperTable[]
  style?: React.CSSProperties
}

const AIToolsPanel = ({
  paper,
  sections,
  images,
  tables,
  style,
}: AIToolsPanelProps) => {
  return (
    <aside className="w-[300px] min-w-[300px] bg-panel h-screen sticky top-0 flex flex-col border-l border-border/40" style={style}>
      <div className="px-5 pt-8 pb-2 flex-shrink-0">
        <InsightExtractor
          paper={paper}
          sections={sections}
          images={images}
          tables={tables}
        />
      </div>
      <div className="flex-1 min-h-0 px-5 pb-5 flex flex-col">
        <ChatAssistant />
      </div>
    </aside>
  )
}

export default AIToolsPanel
