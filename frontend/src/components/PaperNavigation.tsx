import { BookOpenText, ChevronDown, FileText, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ScrollArea } from '@/components/ui/scroll-area'
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
  uploadedFileName?: string | null
  onFileChange?: (fileName: string | null) => void
  onFileUpload?: (file: File) => void
  isUploading?: boolean
  uploadError?: string | null
}

interface ReadingPhase {
  id: string
  title: string
  goal: string
  keywords: string[]
  outcome: string
}

const readingPhases: ReadingPhase[] = [
  {
    id: 'quick-understanding',
    title: 'Quick Understanding',
    goal: 'Get a high-level overview of the problem and key contribution.',
    keywords: ['abstract', 'introduction', 'conclusion'],
    outcome: 'You should be able to summarize the paper in 2-3 sentences.',
  },
  {
    id: 'method-understanding',
    title: 'Method Understanding',
    goal: 'Understand how the approach works and how it is evaluated.',
    keywords: ['method', 'model', 'approach', 'architecture', 'experiment'],
    outcome: 'You should be able to explain the method to a peer.',
  },
  {
    id: 'deep-analysis',
    title: 'Deep Analysis',
    goal: 'Evaluate evidence quality, limitations, and practical implications.',
    keywords: [
      'result',
      'discussion',
      'analysis',
      'evaluation',
      'table',
      'figure',
    ],
    outcome: 'You should be able to critique the strength of claims.',
  },
]

const normalize = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

function getSectionsForPhase(
  phase: ReadingPhase,
  sections: Section[],
): Section[] {
  const ranked = sections
    .map((section) => {
      const hay = normalize(section.title)
      const score = phase.keywords.reduce(
        (acc, keyword) => (hay.includes(keyword) ? acc + 1 : acc),
        0,
      )
      return { section, score }
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map((entry) => entry.section)

  if (ranked.length > 0) return ranked

  if (phase.id === 'quick-understanding') {
    return sections.slice(0, Math.min(3, sections.length))
  }

  return []
}

const PaperNavigation = ({
  activeSection,
  onSectionClick,
  sections,
  papers,
  selectedPaperId,
  onPaperSelect,
  uploadedFileName,
  onFileChange,
  onFileUpload,
  isUploading,
  uploadError,
}: PaperNavigationProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragActive, setDragActive] = useState(false)
  const [openPhases, setOpenPhases] = useState<Record<string, boolean>>({
    'quick-understanding': true,
  })

  const togglePhase = (phaseId: string) => {
    setOpenPhases((prev) => ({
      ...prev,
      [phaseId]: !prev[phaseId],
    }))
  }

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

      {uploadedFileName ? (
        <div className="px-4 mb-4">
          <div className="flex items-center gap-2 px-3 py-2.5 bg-accent/10 rounded-lg">
            <FileText size={14} className="text-text-active flex-shrink-0" />
            <span className="font-ui text-[12px] text-foreground truncate flex-1">
              {uploadedFileName}
            </span>
            <button
              onClick={() => onFileChange?.(null)}
              className="text-text-secondary hover:text-foreground transition-colors"
            >
              <X size={12} />
            </button>
          </div>
        </div>
      ) : null}

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
          Reading Guide
        </h2>
      </div>

      <ScrollArea className="flex-1 px-4 py-1">
        <div className="space-y-1 pb-4">
          {readingPhases.map((phase, idx) => {
            const mappedSections = getSectionsForPhase(phase, sections)

            return (
              <Collapsible
                key={phase.id}
                open={openPhases[phase.id] ?? false}
                onOpenChange={() => togglePhase(phase.id)}
              >
                <CollapsibleTrigger className="w-full text-left px-3 py-2.5 rounded-md hover:bg-canvas transition-colors duration-200 group flex items-center gap-2">
                  <span className="font-mono text-[10px] text-text-secondary/60">
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  <span className="font-ui text-[13px] font-medium text-foreground flex-1">
                    {phase.title}
                  </span>
                  <ChevronDown
                    size={14}
                    className={`text-text-secondary transition-transform duration-200 ${
                      openPhases[phase.id] ? 'rotate-180' : ''
                    }`}
                  />
                </CollapsibleTrigger>

                <CollapsibleContent className="animate-fade-in">
                  <div className="ml-[26px] mr-1 mb-2 space-y-2 border-l-2 border-border/40 pl-3 py-2">
                    <p className="font-ui text-[11px] text-text-secondary italic leading-relaxed">
                      {phase.goal}
                    </p>

                    {mappedSections.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {mappedSections.map((section) => {
                          const isActive = activeSection === section.id
                          return (
                            <button
                              key={`${phase.id}-${section.id}`}
                              onClick={() => onSectionClick(section.id)}
                              className={`font-ui text-[11px] px-2 py-0.5 rounded transition-colors ${
                                isActive
                                  ? 'bg-accent/25 text-foreground font-medium'
                                  : 'bg-accent/10 text-foreground hover:bg-accent/20'
                              }`}
                            >
                              {section.title}
                            </button>
                          )
                        })}
                      </div>
                    ) : (
                      <p className="font-ui text-[11px] text-text-secondary leading-relaxed">
                        Matching sections will appear when more structure is
                        extracted.
                      </p>
                    )}

                    <div className="bg-canvas rounded-md px-2.5 py-2">
                      <p className="font-ui text-[10px] font-semibold uppercase tracking-wider text-text-active mb-0.5">
                        Outcome
                      </p>
                      <p className="font-ui text-[11px] text-foreground leading-relaxed">
                        {phase.outcome}
                      </p>
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )
          })}
        </div>

        <div className="px-2 pt-2 pb-1">
          <h3 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary mb-2">
            Paper Structure
          </h3>
          <ul className="space-y-0.5">
            {sections.map((section) => {
              const isActive = activeSection === section.id
              return (
                <li key={section.id}>
                  <button
                    onClick={() => onSectionClick(section.id)}
                    className={`
                      w-full text-left py-2 px-2.5 font-ui text-[12px] rounded-md transition-all duration-200 flex items-center gap-2.5
                      ${
                        isActive
                          ? 'text-text-active bg-accent/10 font-semibold'
                          : 'text-text-secondary hover:text-foreground hover:bg-canvas font-normal'
                      }
                    `}
                  >
                    <span
                      className={`text-[10px] font-mono ${isActive ? 'text-text-active' : 'text-text-secondary/50'}`}
                    >
                      {section.label}
                    </span>
                    <span className="truncate">{section.title}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      </ScrollArea>

      <div className="border-t border-border/40 px-4 py-4">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) {
              onFileUpload?.(file)
              e.target.value = ''
            }
          }}
          className="hidden"
        />
        <div
          onDragEnter={() => setDragActive(true)}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(e) => {
            e.preventDefault()
            setDragActive(true)
          }}
          onDrop={(e) => {
            e.preventDefault()
            setDragActive(false)
            const file = e.dataTransfer.files?.[0]
            if (file && file.type === 'application/pdf') {
              onFileUpload?.(file)
            }
          }}
          onClick={() => fileInputRef.current?.click()}
          className={`
            relative p-3 rounded-lg border-2 border-dashed transition-all cursor-pointer
            ${
              dragActive
                ? 'border-accent/60 bg-accent/10'
                : uploadError
                  ? 'border-destructive/40 bg-destructive/5 hover:bg-destructive/10'
                  : 'border-border/40 bg-canvas hover:border-border/60 hover:bg-canvas/80'
            }
          `}
        >
          <div className="flex flex-col items-center gap-1.5">
            <Upload
              size={16}
              className={
                uploadError
                  ? 'text-destructive/60'
                  : dragActive
                    ? 'text-accent'
                    : 'text-text-secondary'
              }
            />
            <p className="font-ui text-[11px] text-text-secondary text-center">
              {isUploading ? 'Uploading...' : 'Drop PDF or click'}
            </p>
          </div>
        </div>
        {uploadError ? (
          <p className="mt-1.5 font-ui text-[10px] text-destructive text-center">
            {uploadError}
          </p>
        ) : null}
      </div>

      <div className="px-6 pb-6 pt-4 border-t border-border/40">
        <p className="font-ui text-[10px] text-text-secondary/50 tracking-wide">
          Powered by AcadAI
        </p>
      </div>
    </aside>
  )
}

export default PaperNavigation
