import InsightExtractor from './InsightExtractor'
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
    <aside className="h-full flex flex-col" style={style}>
      <div className="relative z-0 flex-1 min-h-0 overflow-hidden px-5 pt-4 pb-5 bg-gradient-to-b from-accent/5 via-panel to-canvas/40">
        <InsightExtractor
          paper={paper}
          sections={sections}
          images={images}
          tables={tables}
        />
      </div>
    </aside>
  )
}

export default AIToolsPanel
