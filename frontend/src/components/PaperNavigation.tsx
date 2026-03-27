import { BookOpenText, ChevronDown, FileText, Upload, X } from 'lucide-react'
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
  uploadedFileName?: string | null
  onFileChange?: (fileName: string | null) => void
  onFileUpload?: (file: File) => void
  isUploading?: boolean
  uploadError?: string | null
  readingGuide?: ReadingGuide | null
  guideStatus?: GuideStatus | null
  onGoHome?: () => void
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
  uploadedFileName,
  onFileChange,
  onFileUpload,
  isUploading,
  uploadError,
  readingGuide,
  guideStatus,
  onGoHome,
}: PaperNavigationProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragActive, setDragActive] = useState(false)

  // Extract phases from reading guide or use defaults
  const readingPhases = extractPhasesFromGuide(readingGuide)
  const phaseIdsSignature = readingPhases.map((phase) => phase.id).join('|')
  const [openPhases, setOpenPhases] = useState<Record<string, boolean>>({
    [readingPhases[0]?.id || 'quick-understanding']: true,
  })

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

  return (
    <aside className="w-[320px] min-w-[280px] max-w-[88vw] bg-panel h-screen sticky top-0 flex flex-col border-r border-border/40">
      <div className="px-6 pt-8 pb-6">
        <button
          type="button"
          onClick={onGoHome}
          className="flex items-center gap-2 text-left hover:opacity-90 transition-opacity"
          title="Go to home"
        >
          <BookOpenText size={18} className="text-text-active" />
          <h1 className="font-ui text-[16px] font-bold text-foreground tracking-tight">
            AcadAI
          </h1>
        </button>
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

      {readingGuide?.paper_title ? (
        <div className="px-4 mb-3">
          <div className="bg-canvas rounded-md border border-border/50 px-3 py-2 space-y-1">
            <p className="font-ui text-[11px] text-foreground leading-snug">
              {readingGuide.paper_title}
            </p>
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

      <ScrollArea className="flex-1 px-4 py-1">
        <div className="space-y-1 pb-4">
          {readingPhases.length === 0 ? (
            <div className="px-3 py-2 rounded-md bg-canvas">
              {guideStatus?.status === 'pending' ? (
                <>
                  <p className="font-ui text-[11px] text-text-secondary leading-relaxed">
                    Reading guide is being generated from your uploaded PDF.
                  </p>
                  <div className="mt-2 flex items-center gap-1.5">
                    <span
                      className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce"
                      style={{ animationDelay: '0ms' }}
                    />
                    <span
                      className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce"
                      style={{ animationDelay: '150ms' }}
                    />
                    <span
                      className="w-1.5 h-1.5 rounded-full bg-text-secondary/60 animate-bounce"
                      style={{ animationDelay: '300ms' }}
                    />
                  </div>
                </>
              ) : guideStatus?.status === 'failed' ? (
                <p className="font-ui text-[11px] text-destructive leading-relaxed">
                  Guide generation failed. Re-upload the paper or try again.
                </p>
              ) : (
                <p className="font-ui text-[11px] text-text-secondary leading-relaxed">
                  No backend reading guide found for this paper yet.
                </p>
              )}
            </div>
          ) : (
            readingPhases.map((phase, idx) => {
              return (
                <Collapsible
                  key={phase.id}
                  open={openPhases[phase.id] ?? false}
                  onOpenChange={(isOpen) => setPhaseOpenState(phase.id, isOpen)}
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
                                        const matched = findSectionByGuideName(
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
