import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { generateTechnicalTermDefinition } from '@/lib/api'
import { Maximize2, Minimize2 } from 'lucide-react'
import type {
  PaperImage,
  PaperSection,
  TechnicalTerm,
} from '@/types/api'

interface InsightExtractorProps {
  paperId: number | null
  sections: PaperSection[]
  images: PaperImage[]
  technicalTerms: TechnicalTerm[]
  selectedPdfTerms: string[]
}

const InsightExtractor = ({
  paperId,
  sections,
  images,
  technicalTerms,
  selectedPdfTerms,
}: InsightExtractorProps) => {
  // Keep props for API compatibility with parent components.
  void sections
  void images
  void technicalTerms

  const queryClient = useQueryClient()

  const [termDefinitions, setTermDefinitions] = useState<
    Record<
      string,
      { status: 'idle' | 'loading' | 'ready' | 'error'; definition?: string }
    >
  >({})
  const inFlightTermsRef = useRef<Set<string>>(new Set())

  const backendTermMap = useMemo(() => {
    const map = new Map<string, TechnicalTerm>()
    technicalTerms.forEach((term) => {
      map.set(term.term.toLowerCase(), term)
    })
    return map
  }, [technicalTerms])

  const generateTermDefinition = useCallback(
    async (rawTerm: string) => {
      if (paperId === null) return

      const term = rawTerm.trim()
      if (!term) return
      const key = term.toLowerCase()

      if (inFlightTermsRef.current.has(key)) return

      const current = termDefinitions[key]
      if (current && (current.status === 'loading' || current.status === 'ready')) {
        return
      }

      inFlightTermsRef.current.add(key)
      setTermDefinitions((prev) => ({
        ...prev,
        [key]: { status: 'loading' },
      }))

      try {
        const response = await generateTechnicalTermDefinition(paperId, term, {
          forceLlm: true,
        })
        const definition =
          typeof response.technical_term?.definition === 'string'
            ? response.technical_term.definition.trim()
            : ''

        setTermDefinitions((prev) => ({
          ...prev,
          [key]: {
            status: definition ? 'ready' : 'error',
            definition:
              definition || 'No LLM meaning generated. Click Generate with LLM to retry.',
          },
        }))

        await queryClient.invalidateQueries({
          queryKey: ['paper-bundle', paperId],
        })
      } catch {
        setTermDefinitions((prev) => ({
          ...prev,
          [key]: {
            status: 'error',
            definition: 'Failed to generate LLM meaning. Click Generate with LLM to retry.',
          },
        }))
      } finally {
        inFlightTermsRef.current.delete(key)
      }
    },
    [backendTermMap, paperId, queryClient, termDefinitions],
  )

  useEffect(() => {
    if (paperId === null || selectedPdfTerms.length === 0) return
    selectedPdfTerms.forEach((term) => {
      void generateTermDefinition(term)
    })
  }, [paperId, selectedPdfTerms, generateTermDefinition])

  const visibleTerms = useMemo(() => {
    const seen = new Set<string>()
    const ordered: string[] = []

    selectedPdfTerms.forEach((term) => {
      const trimmed = term.trim()
      if (!trimmed) return
      const key = trimmed.toLowerCase()
      if (seen.has(key)) return
      seen.add(key)
      ordered.push(trimmed)
    })

    technicalTerms.forEach((item) => {
      const trimmed = String(item.term || '').trim()
      if (!trimmed) return
      const key = trimmed.toLowerCase()
      if (seen.has(key)) return
      seen.add(key)
      ordered.push(trimmed)
    })

    return ordered
  }, [selectedPdfTerms, technicalTerms])

  const termCards = useMemo(() => {
    return visibleTerms.map((term) => {
      const key = term.toLowerCase()
      const backendTerm = backendTermMap.get(key)
      const localDefinition = termDefinitions[key]
      const backendLlmDefinition =
        backendTerm?.definition_source === 'llm' ? backendTerm.definition : null

      const hasDefinition = Boolean(backendLlmDefinition || localDefinition?.definition)
      const fallbackMessage =
        localDefinition?.status === 'loading'
          ? 'Generating meaning with LLM...'
          : 'No meaning yet. Click Generate with LLM.'

      const definition =
        backendLlmDefinition ||
        localDefinition?.definition ||
        fallbackMessage

      const sourceLabel = hasDefinition ? 'LLM' : ''

      return {
        key,
        term,
        definition,
        sourceLabel,
        status:
          localDefinition?.status ??
          (hasDefinition ? 'ready' : 'idle' as const),
      }
    })
  }, [backendTermMap, termDefinitions, visibleTerms])

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
          <div className="flex-1 min-h-0 space-y-2 overflow-auto pr-1">
            <p className="font-ui text-[11px] text-text-secondary">
              Ctrl+click selected PDF word to add it here and generate meaning with LLM.
            </p>
            {visibleTerms.length > 0 ? (
              <div className="rounded-sm border border-border/60 bg-canvas p-2">
                <p className="font-ui text-[11px] text-text-secondary mb-1">
                  Keywords found ({visibleTerms.length})
                </p>
                <div className="flex flex-wrap gap-1">
                  {visibleTerms.map((term) => (
                    <span
                      key={`keyword-${term.toLowerCase()}`}
                      className="font-ui text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-foreground"
                    >
                      {term}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
            {termCards.length === 0 ? (
              <div className="rounded-sm border border-border/60 bg-canvas p-2">
                <p className="font-ui text-[12px] text-text-secondary">
                  No terms available yet. Select a word in the PDF and Ctrl+click,
                  or wait for extracted terms from the backend.
                </p>
              </div>
            ) : (
              termCards.map((item) => (
                <div
                  key={item.key}
                  className="rounded-sm border border-border/60 bg-canvas p-2"
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <p className="font-ui text-[12px] font-semibold text-foreground">
                      {item.term}
                    </p>
                    {item.sourceLabel ? (
                      <span className="font-ui text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-text-active uppercase tracking-wide">
                        {item.sourceLabel}
                      </span>
                    ) : null}
                  </div>
                  <p className="font-ui text-[12px] text-text-secondary leading-relaxed whitespace-pre-wrap">
                    {item.definition}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      void generateTermDefinition(item.term)
                    }}
                    className="mt-2 font-ui text-[11px] px-2 py-1 rounded-md border border-border/60 text-foreground hover:border-primary/40 hover:text-text-active transition-all"
                    disabled={item.status === 'loading'}
                  >
                    {item.status === 'loading'
                      ? 'Generating with LLM...'
                      : item.status === 'ready'
                        ? 'Regenerate with LLM'
                        : 'Generate with LLM'}
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export default InsightExtractor
