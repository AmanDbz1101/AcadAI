import { ChevronDown, ChevronLeft, Home, LogOut, Upload, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { GuideStatus, PaperSummary, ReadingGuide } from '@/types/api'

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
  onPaperDelete?: (paperId: number, paperName: string) => void
  deletingPaperId?: number | null
  readingGuide?: ReadingGuide | null
  guideStatus?: GuideStatus | null
  onGoHome?: () => void
  collapsed?: boolean
  onToggleCollapse?: () => void
  onHomeClick?: () => void
  onLogout?: () => void
  onUploadPdf?: (file: File) => void
  isUploadingPdf?: boolean
  uploadErrorMessage?: string | null
  style?: React.CSSProperties
}

interface ReadingPhase {
  id: string
  title: string
  goal: string
  estimatedTime: string
  steps: GuideStepLike[]
  sectionsToRead?: string[]
}

interface GuideStepLike {
  step_number?: number
  objective?: string
  questions_to_answer?: string[]
  section_to_read?: string[]
  expected_output?: string
  needs_figures?: boolean
  needs_tables?: boolean
}

interface GuidePassLike {
  goal?: string
  estimated_time?: string
  steps?: GuideStepLike[]
}

const normalize = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

const toPassLabel = (passKey: string) =>
  passKey
    .replace(/^pass\d+_/i, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())

function extractPhasesFromGuide(
  readingGuide: ReadingGuide | null | undefined,
): ReadingPhase[] {
  if (!readingGuide) return []

  const phases: ReadingPhase[] = []

  // Dynamically discover pass keys from backend payload. This avoids fallback
  // to default phases when key naming changes slightly.
  const passEntries = Object.entries(readingGuide as Record<string, unknown>)
    .filter(([key, value]) => {
      if (!/^pass\d+_/i.test(key)) return false
      if (!value || typeof value !== 'object') return false
      const maybePass = value as GuidePassLike
      return (
        Array.isArray(maybePass.steps) || typeof maybePass.goal === 'string'
      )
    })
    .sort(([a], [b]) => {
      const an = Number((a.match(/^pass(\d+)/i) || [])[1] || 99)
      const bn = Number((b.match(/^pass(\d+)/i) || [])[1] || 99)
      if (an !== bn) return an - bn
      return a.localeCompare(b)
    })

  for (const [key, value] of passEntries) {
    const pass = value as GuidePassLike
    if (pass) {
      const steps: GuideStepLike[] = Array.isArray(pass.steps) ? pass.steps : []
      const sectionsToRead = Array.from(
        new Set((_extractSectionsFromPass(pass) || []).flat()),
      )

      phases.push({
        id: key,
        title: toPassLabel(key),
        goal: pass.goal || 'Complete this reading pass',
        estimatedTime: pass.estimated_time || 'Not specified',
        steps,
        sectionsToRead: sectionsToRead,
      })
    }
  }

  return phases
}

function _extractSectionsFromPass(pass: GuidePassLike): string[][] {
  if (!pass || !pass.steps || !Array.isArray(pass.steps)) return []
  return pass.steps.map((step) => step.section_to_read || [])
}

function findSectionByGuideName(
  name: string,
  sections: Section[],
): Section | null {
  const needle = normalize(name)
  if (!needle) return null

  const exact = sections.find((section) => normalize(section.title) === needle)
  if (exact) return exact

  const partial = sections.find((section) => {
    const hay = normalize(section.title)
    return hay.includes(needle) || needle.includes(hay)
  })
  return partial || null
}

const PaperNavigation = ({
  activeSection,
  onSectionClick,
  sections,
  papers,
  selectedPaperId,
  onPaperSelect,
  onPaperDelete,
  deletingPaperId,
  readingGuide,
  guideStatus,
  collapsed = false,
  onToggleCollapse,
  onHomeClick,
  onGoHome,
  onLogout,
  onUploadPdf,
  isUploadingPdf = false,
  uploadErrorMessage,
  style,
}: PaperNavigationProps) => {
  void guideStatus

  // Extract phases from reading guide or use defaults
  const readingPhases = extractPhasesFromGuide(readingGuide)
  const phaseIdsSignature = readingPhases.map((phase) => phase.id).join('|')
  const [openPhases, setOpenPhases] = useState<Record<string, boolean>>({
    [readingPhases[0]?.id || 'quick-understanding']: true,
  })
  const [paperStructureOpen, setPaperStructureOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Keep collapsible state aligned when phases change between papers/guide types.
  useEffect(() => {
    const ids = readingPhases.map((phase) => phase.id)
    if (ids.length === 0) return

    setOpenPhases((prev) => {
      const next: Record<string, boolean> = {}

      for (const id of ids) {
        next[id] = Boolean(prev[id])
      }

      const prevKeys = Object.keys(prev)
      const nextKeys = Object.keys(next)
      if (
        prevKeys.length === nextKeys.length &&
        nextKeys.every((key) => prev[key] === next[key])
      ) {
        return prev
      }

      return next
    })
  }, [phaseIdsSignature, readingPhases])

  const setPhaseOpenState = (phaseId: string, isOpen: boolean) => {
    setOpenPhases((prev) => ({
      ...prev,
      [phaseId]: isOpen,
    }))
  }

  const homeHandler = onHomeClick ?? onGoHome

  const handleUploadButtonClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileInputChange = (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0]
    if (file && onUploadPdf) {
      onUploadPdf(file)
    }

    // Allow selecting the same file again if needed.
    event.currentTarget.value = ''
  }

  return (
    <aside
      className="bg-panel/95 h-screen sticky top-0 flex flex-col border-r border-border/50 shadow-sm"
      style={style}
    >
      <div className="relative flex h-full flex-col">
        <div className="px-6 pt-4 pb-3 border-b border-border/40 bg-gradient-to-r from-accent/10 via-panel to-panel">
          <div className="flex items-center justify-between">
            <button
              onClick={homeHandler}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border/60 bg-canvas text-text-active hover:bg-accent/10 transition-colors"
              title="Home"
              aria-label="Home"
            >
              <Home size={14} />
            </button>

            {onLogout ? (
              <button
                onClick={onLogout}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-primary/80 bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                title="Logout"
                aria-label="Logout"
              >
                <LogOut size={14} />
              </button>
            ) : null}
          </div>
        </div>

        {onToggleCollapse ? (
          <button
            onClick={onToggleCollapse}
            className="absolute right-0 top-1/2 z-20 inline-flex h-9 w-4 -translate-y-1/2 items-center justify-center rounded-l-md rounded-r-none border border-r-0 border-border/60 bg-canvas shadow-sm hover:bg-accent/10 transition-colors"
            title={collapsed ? 'Expand guide panel' : 'Collapse guide panel'}
            aria-label={collapsed ? 'Expand guide panel' : 'Collapse guide panel'}
          >
            <ChevronLeft size={14} className="text-text-secondary" />
          </button>
        ) : null}

        <div className="px-6 mt-4 mb-3">
          <label className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary block mb-2">
            Paper
          </label>
          <select
            value={selectedPaperId ?? ''}
            onChange={(e) => onPaperSelect(Number(e.target.value))}
            className="w-full font-ui text-[12px] bg-canvas border border-border/70 rounded-md px-2 py-1.5 text-foreground shadow-sm"
          >
            {papers.map((paper) => (
              <option key={paper.id} value={paper.id}>
                {paper.paper_name}
              </option>
            ))}
          </select>

          <div className="mt-2 space-y-1 max-h-28 overflow-y-auto pr-1">
            {papers.map((paper) => {
              const isSelected = selectedPaperId === paper.id
              const isDeleting = deletingPaperId === paper.id

              return (
                <div
                  key={`paper-delete-item-${paper.id}`}
                  className={`flex items-center justify-between gap-2 rounded-md border px-2 py-1 ${
                    isSelected
                      ? 'border-accent/60 bg-accent/10'
                      : 'border-border/50 bg-canvas'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onPaperSelect(paper.id)}
                    className={`min-w-0 flex-1 truncate text-left font-ui text-[11px] ${
                      isSelected ? 'text-foreground font-semibold' : 'text-text-secondary hover:text-foreground'
                    }`}
                    title={paper.paper_name}
                  >
                    {paper.paper_name}
                  </button>

                  {onPaperDelete ? (
                    <button
                      type="button"
                      onClick={() => onPaperDelete(paper.id, paper.paper_name)}
                      disabled={Boolean(deletingPaperId)}
                      className="inline-flex h-5 w-5 items-center justify-center rounded border border-destructive/30 bg-destructive/10 text-destructive hover:bg-destructive/20 disabled:opacity-60"
                      title={`Delete ${paper.paper_name}`}
                      aria-label={`Delete ${paper.paper_name}`}
                    >
                      {isDeleting ? (
                        <span className="font-ui text-[10px]">...</span>
                      ) : (
                        <X size={12} />
                      )}
                    </button>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>

        <div className="px-6 mb-3">
          <h2 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary">
            Reading Guide
          </h2>
        </div>

        {readingGuide?.paper_title ? (
          <div className="px-4 mb-3">
            <div className="bg-canvas rounded-md border border-border/50 px-3 py-2 space-y-1">
              <div className="flex flex-wrap gap-1">
                {readingGuide.reading_strategy?.paper_type ? (
                  <span className="font-ui text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-text-active">
                    {readingGuide.reading_strategy.paper_type}
                  </span>
                ) : null}
                {readingGuide.reading_strategy?.estimated_total_time ? (
                  <span className="font-ui text-[10px] px-1.5 py-0.5 rounded bg-canvas text-text-secondary border border-border/50">
                    {readingGuide.reading_strategy.estimated_total_time}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        <ScrollArea className="flex-1 px-4 py-2">
          <div className="space-y-1 pb-4">
            {readingPhases.length === 0 ? (
              <div className="px-3 py-2 rounded-md bg-canvas">
                <p className="font-ui text-[11px] text-text-secondary leading-relaxed">
                  No backend reading guide found for this paper yet.
                </p>
              </div>
            ) : (
              readingPhases.map((phase, idx) => {
                return (
                  <Collapsible
                    key={phase.id}
                    open={openPhases[phase.id] ?? false}
                    onOpenChange={(isOpen) =>
                      setPhaseOpenState(phase.id, isOpen)
                    }
                  >
                    <CollapsibleTrigger className="w-full text-left px-3 py-2.5 rounded-md hover:bg-canvas transition-colors duration-200 group flex items-center gap-2">
                      <span className="font-mono text-[10px] text-text-secondary/60">
                        {String(idx + 1).padStart(2, '0')}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="font-ui text-[12px] font-semibold text-foreground truncate">
                          {phase.title}
                        </p>
                      </div>
                      <ChevronDown
                        size={14}
                        className={`text-text-secondary transition-transform duration-200 ${
                          openPhases[phase.id] ? 'rotate-180' : ''
                        }`}
                      />
                    </CollapsibleTrigger>

                    <CollapsibleContent className="animate-fade-in">
                      <div className="ml-[26px] mr-1 mb-2 space-y-2 border-l-2 border-border/40 pl-3 py-2">
                        <div className="bg-canvas rounded-md border border-border/40 px-2.5 py-2 space-y-1">
                          <p className="font-ui text-[10px] font-semibold uppercase tracking-wider text-text-active">
                            Pass Goal
                          </p>
                          <p className="font-ui text-[11px] text-foreground leading-relaxed">
                            {phase.goal}
                          </p>
                          <p className="font-ui text-[10px] text-text-secondary">
                            Estimated time: {phase.estimatedTime}
                          </p>
                        </div>

                        {phase.steps.length === 0 ? (
                          <p className="font-ui text-[11px] text-text-secondary leading-relaxed">
                            No step details available for this pass.
                          </p>
                        ) : (
                          phase.steps.map((step, stepIdx) => {
                            const stepNumber = step.step_number || stepIdx + 1
                            const guideSections = step.section_to_read || []

                            return (
                              <div
                                key={`${phase.id}-step-${stepNumber}`}
                                className="bg-canvas rounded-md border border-border/40 px-2.5 py-2 space-y-1.5"
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <p className="font-ui text-[10px] font-semibold uppercase tracking-wider text-text-active">
                                    Step {stepNumber}
                                  </p>
                                  <div className="flex gap-1">
                                    {step.needs_figures ? (
                                      <span className="font-ui text-[9px] px-1.5 py-0.5 rounded bg-accent/15 text-text-secondary">
                                        figures
                                      </span>
                                    ) : null}
                                    {step.needs_tables ? (
                                      <span className="font-ui text-[9px] px-1.5 py-0.5 rounded bg-accent/15 text-text-secondary">
                                        tables
                                      </span>
                                    ) : null}
                                  </div>
                                </div>

                                <div>
                                  <p className="font-ui text-[10px] font-semibold text-text-secondary mb-1">
                                    Sections to read
                                  </p>
                                  {guideSections.length > 0 ? (
                                    <div className="flex flex-wrap gap-1">
                                      {guideSections.map(
                                        (sectionName, sectionIdx) => {
                                          const matched =
                                            findSectionByGuideName(
                                              sectionName,
                                              sections,
                                            )
                                          const isActive = matched
                                            ? activeSection === matched.id
                                            : false

                                          return matched ? (
                                            <button
                                              key={`${phase.id}-${stepNumber}-section-${sectionIdx}`}
                                              onClick={() =>
                                                onSectionClick(matched.id)
                                              }
                                              className={`font-ui text-[10px] px-2 py-0.5 rounded transition-colors ${
                                                isActive
                                                  ? 'bg-accent/25 text-foreground font-medium'
                                                  : 'bg-accent/10 text-foreground hover:bg-accent/20'
                                              }`}
                                            >
                                              {sectionName}
                                            </button>
                                          ) : (
                                            <span
                                              key={`${phase.id}-${stepNumber}-section-${sectionIdx}`}
                                              className="font-ui text-[10px] px-2 py-0.5 rounded bg-canvas border border-border/50 text-text-secondary"
                                            >
                                              {sectionName}
                                            </span>
                                          )
                                        },
                                      )}
                                    </div>
                                  ) : (
                                    <p className="font-ui text-[11px] text-text-secondary">
                                      No sections specified.
                                    </p>
                                  )}
                                </div>

                                <div>
                                  <p className="font-ui text-[10px] font-semibold text-text-secondary">
                                    Objective
                                  </p>
                                  <p className="font-ui text-[11px] text-foreground leading-relaxed">
                                    {step.objective || 'No objective provided.'}
                                  </p>
                                </div>

                                <div>
                                  <p className="font-ui text-[10px] font-semibold text-text-secondary">
                                    Questions to answer
                                  </p>
                                  {step.questions_to_answer &&
                                  step.questions_to_answer.length > 0 ? (
                                    <ul className="space-y-1">
                                      {step.questions_to_answer.map(
                                        (question, questionIdx) => (
                                          <li
                                            key={`${phase.id}-${stepNumber}-question-${questionIdx}`}
                                            className="font-ui text-[11px] text-foreground leading-relaxed"
                                          >
                                            {question}
                                          </li>
                                        ),
                                      )}
                                    </ul>
                                  ) : (
                                    <p className="font-ui text-[11px] text-text-secondary">
                                      No questions listed.
                                    </p>
                                  )}
                                </div>

                                <div>
                                  <p className="font-ui text-[10px] font-semibold text-text-secondary">
                                    Expected output
                                  </p>
                                  <p className="font-ui text-[11px] text-foreground leading-relaxed">
                                    {step.expected_output ||
                                      'No expected output provided.'}
                                  </p>
                                </div>
                              </div>
                            )
                          })
                        )}
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                )
              })
            )}
          </div>

          <div className="px-2 pt-2 pb-1">
            <Collapsible
              open={paperStructureOpen}
              onOpenChange={setPaperStructureOpen}
            >
              <CollapsibleTrigger className="w-full text-left rounded-md px-1 py-1.5 hover:bg-canvas transition-colors duration-200 flex items-center justify-between gap-2">
                <h3 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary">
                  Paper Structure
                </h3>
                <ChevronDown
                  size={14}
                  className={`text-text-secondary transition-transform duration-200 ${
                    paperStructureOpen ? 'rotate-180' : ''
                  }`}
                />
              </CollapsibleTrigger>

              <CollapsibleContent className="animate-fade-in">
                <ul className="space-y-0.5 mt-1">
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
              </CollapsibleContent>
            </Collapsible>
          </div>
        </ScrollArea>

        <div className="px-4 pb-4 pt-3 border-t border-border/40 bg-gradient-to-b from-panel to-canvas/50">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            className="hidden"
            onChange={handleFileInputChange}
          />
          {onUploadPdf ? (
            <button
              type="button"
              onClick={handleUploadButtonClick}
              disabled={isUploadingPdf}
              className="w-full rounded-md border border-primary/70 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-60 px-3 py-2 font-ui text-[12px] font-semibold transition-colors flex items-center justify-center gap-2 shadow-md"
            >
              <Upload size={14} className="text-primary-foreground" />
              {isUploadingPdf ? 'Uploading PDF...' : 'Upload PDF'}
            </button>
          ) : null}
          {uploadErrorMessage ? (
            <p className="mt-2 font-ui text-[11px] text-destructive leading-snug">
              {uploadErrorMessage}
            </p>
          ) : null}
        </div>
      </div>
    </aside>
  )
}

export default PaperNavigation
