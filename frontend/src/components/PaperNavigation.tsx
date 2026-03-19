import { BookOpenText } from 'lucide-react'
import type { PaperSummary } from '@/types/api'

interface Section {
  id: string
  title: string
  label: string
}

interface PaperNavigationProps {
  activeSection: string
  onSectionClick: (sectionId: string) => void
  sections: Section[]
  papers: PaperSummary[]
  selectedPaperId: number | null
  onPaperSelect: (paperId: number) => void
}

const PaperNavigation = ({
  activeSection,
  onSectionClick,
  sections,
  papers,
  selectedPaperId,
  onPaperSelect,
}: PaperNavigationProps) => {
  return (
    <aside className="w-[260px] min-w-[260px] bg-panel h-screen sticky top-0 flex flex-col border-r border-border/40">
      <div className="px-6 pt-8 pb-6">
        <div className="flex items-center gap-2">
          <BookOpenText size={18} className="text-text-active" />
          <h1 className="font-ui text-[16px] font-bold text-foreground tracking-tight">
            AcadAI
          </h1>
        </div>
        <p className="font-ui text-[11px] text-text-secondary pl-[26px]">
          Research Paper Assistant
        </p>
      </div>

      <div className="px-6 mb-3">
        <label className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary block mb-2">
          Paper
        </label>
        <select
          value={selectedPaperId ?? ''}
          onChange={(e) => onPaperSelect(Number(e.target.value))}
          className="w-full font-ui text-[12px] bg-canvas border border-border/60 rounded-md px-2 py-1.5 text-foreground"
        >
          {papers.map((paper) => (
            <option key={paper.id} value={paper.id}>
              {paper.paper_name}
            </option>
          ))}
        </select>
      </div>

      <div className="px-6 mb-3">
        <h2 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary">
          Paper Structure
        </h2>
      </div>

      <nav className="flex-1 px-4 py-1">
        <ul className="space-y-0.5">
          {sections.map((section) => {
            const isActive = activeSection === section.id
            return (
              <li key={section.id}>
                <button
                  onClick={() => onSectionClick(section.id)}
                  className={`
                    w-full text-left py-2.5 px-3 font-ui text-[13px] rounded-md transition-all duration-200 flex items-center gap-3
                    ${
                      isActive
                        ? 'text-text-active bg-primary/8 font-semibold'
                        : 'text-text-secondary hover:text-foreground hover:bg-canvas font-normal'
                    }
                  `}
                >
                  <span
                    className={`text-[10px] font-mono ${isActive ? 'text-text-active' : 'text-text-secondary/50'}`}
                  >
                    {section.label}
                  </span>
                  {section.title}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="px-6 pb-6">
        <div className="border-t border-border/40 pt-4">
          <p className="font-ui text-[10px] text-text-secondary/50 tracking-wide">
            Powered by AcadAI
          </p>
        </div>
      </div>
    </aside>
  )
}

export default PaperNavigation
