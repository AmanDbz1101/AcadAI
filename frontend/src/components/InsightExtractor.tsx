import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  generateQuestionAnswer,
  generateTechnicalTermDefinition,
  getPaperQuestions,
} from '@/lib/api'
import { Maximize2, Minimize2 } from 'lucide-react'
import type {
  PaperImage,
  PaperQuestion,
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

  const questionsQuery = useQuery({
    queryKey: ['paper-questions', paperId],
    queryFn: () => getPaperQuestions(paperId as number),
    enabled: paperId !== null,
  })

  const generateMutation = useMutation({
    mutationFn: ({ questionId }: { questionId: number }) =>
      generateQuestionAnswer(paperId as number, questionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['paper-questions', paperId],
      })
    },
  })

  const [termDefinitions, setTermDefinitions] = useState<
    Record<string, { status: 'loading' | 'ready' | 'error'; definition?: string }>
  >({})
  const [activePanel, setActivePanel] = useState<'terms' | 'answers'>('terms')
  const inFlightTermsRef = useRef<Set<string>>(new Set())

  const backendTermMap = useMemo(() => {
    const map = new Map<string, TechnicalTerm>()
    technicalTerms.forEach((term) => {
      map.set(term.term.toLowerCase(), term)
    })
    return map
  }, [technicalTerms])

  const generateTermDefinition = useCallback(
    async (rawTerm: string, force = false) => {
      if (paperId === null) return

      const term = rawTerm.trim()
      if (!term) return
      const key = term.toLowerCase()

      if (inFlightTermsRef.current.has(key)) return

      if (!force) {
        const existingBackend = backendTermMap.get(key)
        if (existingBackend?.definition) {
          setTermDefinitions((prev) => ({
            ...prev,
            [key]: {
              status: 'ready',
              definition: existingBackend.definition ?? '',
            },
          }))
          return
        }

        const current = termDefinitions[key]
        if (current && (current.status === 'loading' || current.status === 'ready')) {
          return
        }
      }

      inFlightTermsRef.current.add(key)
      setTermDefinitions((prev) => ({
        ...prev,
        [key]: { status: 'loading' },
      }))

      try {
        const response = await generateTechnicalTermDefinition(paperId, term, {
          forceLlm: force,
        })
        const definition =
          typeof response.technical_term?.definition === 'string'
            ? response.technical_term.definition.trim()
            : ''
        const definitionStatus = response.technical_term?.definition_status

        setTermDefinitions((prev) => ({
          ...prev,
          [key]: {
            status:
              definitionStatus === 'pending_llm' || !definition ? 'error' : 'ready',
            definition:
              definition ||
              'No meaning found via dictionary/Wikipedia. Click Generate meaning to use LLM.',
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
            definition: 'Failed to generate definition. Click regenerate to retry.',
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

  const selectedTermCards = useMemo(() => {
    return selectedPdfTerms.map((term) => {
      const key = term.toLowerCase()
      const backendTerm = backendTermMap.get(key)
      const localDefinition = termDefinitions[key]

      const definition =
        backendTerm?.definition ||
        localDefinition?.definition ||
        (localDefinition?.status === 'loading'
          ? 'Generating definition...'
          : 'Definition is not available yet.')

      const source = backendTerm?.definition_source || null
      const sourceLabel =
        source === 'dbpedia'
          ? 'DBpedia'
          : source === 'dictionary'
            ? 'Dictionary'
          : source === 'wikipedia'
            ? 'Wikipedia'
            : source === 'llm'
              ? 'LLM'
              : ''

      return {
        key,
        term,
        definition,
        sourceLabel,
        status: localDefinition?.status ?? (backendTerm?.definition ? 'ready' : 'error'),
      }
    })
  }, [backendTermMap, selectedPdfTerms, termDefinitions])

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

  const renderAnswerCard = (question: PaperQuestion, index: number) => {
    const isGenerating =
      generateMutation.isPending &&
      generateMutation.variables?.questionId === question.id
    const canGenerate = !isGenerating && question.status !== 'running'

    return (
      <div
        key={question.id}
        className="p-3 rounded-sm bg-canvas animate-fade-in"
        style={{ animationDelay: `${index * 80}ms` }}
      >
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <h4 className="font-ui text-[13px] font-medium text-foreground leading-snug">
            {question.question_text}
          </h4>
          <span className="font-ui text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-text-active uppercase tracking-wide">
            {question.status}
          </span>
        </div>

        {question.answer_text ? (
          <p className="font-ui text-[12px] text-text-secondary leading-relaxed whitespace-pre-wrap">
            {question.answer_text}
          </p>
        ) : (
          <p className="font-ui text-[12px] text-text-secondary leading-relaxed">
            {question.status === 'failed'
              ? question.error_message || 'Answer generation failed. Try again.'
              : 'No generated answer yet. Use the button below to generate this answer.'}
          </p>
        )}

        <button
          onClick={() => generateMutation.mutate({ questionId: question.id })}
          disabled={!canGenerate}
          className="mt-2 font-ui text-[11px] px-2.5 py-1.5 rounded-md border border-border/60 text-foreground hover:border-primary/40 hover:text-text-active transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isGenerating
            ? 'Generating...'
            : question.answer_text
              ? 'Regenerate answer'
              : 'Generate answer'}
        </button>
      </div>
    )
  }

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
          <div className="mb-3 flex-shrink-0 rounded-md border border-border/50 bg-panel/80 p-2">
            <div className="flex w-full gap-2">
              <button
                type="button"
                onClick={() => setActivePanel('terms')}
                className={`flex-1 inline-flex items-center justify-center font-ui text-[11px] px-2.5 py-1.5 rounded-md border transition-colors ${
                  activePanel === 'terms'
                    ? 'bg-primary text-primary-foreground border-primary/70'
                    : 'bg-canvas text-text-secondary border-border/60 hover:text-foreground'
                }`}
              >
                Technical Terms
              </button>
              <button
                type="button"
                onClick={() => setActivePanel('answers')}
                className={`flex-1 inline-flex items-center justify-center font-ui text-[11px] px-2.5 py-1.5 rounded-md border transition-colors ${
                  activePanel === 'answers'
                    ? 'bg-primary text-primary-foreground border-primary/70'
                    : 'bg-canvas text-text-secondary border-border/60 hover:text-foreground'
                }`}
              >
                Answers
              </button>
            </div>
          </div>

          {activePanel === 'terms' ? (
            <div className="flex-1 min-h-0 space-y-2 overflow-auto pr-1">
              <p className="font-ui text-[11px] text-text-secondary">
                Ctrl+click selected PDF word to add it here.
              </p>
              {selectedTermCards.length === 0 ? (
                <div className="rounded-sm border border-border/60 bg-canvas p-2">
                  <p className="font-ui text-[12px] text-text-secondary">
                    Select a word in the PDF and Ctrl+click to add it here.
                  </p>
                </div>
              ) : (
                selectedTermCards.map((item) => (
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
                        void generateTermDefinition(item.term, true)
                      }}
                      className="mt-2 font-ui text-[11px] px-2 py-1 rounded-md border border-border/60 text-foreground hover:border-primary/40 hover:text-text-active transition-all"
                      disabled={item.status === 'loading'}
                    >
                      {item.status === 'loading'
                        ? 'Generating...'
                        : item.status === 'ready'
                          ? 'Regenerate with LLM'
                          : 'Generate meaning'}
                    </button>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="flex-1 min-h-0 space-y-2 overflow-auto pr-1">
              {paperId === null ? (
              <div className="p-3 rounded-sm bg-canvas">
                <p className="font-ui text-[12px] text-text-secondary">
                  Select a paper to view guide questions.
                </p>
              </div>
              ) : questionsQuery.isLoading ? (
              <div className="p-3 rounded-sm bg-canvas animate-fade-in">
                <p className="font-ui text-[12px] text-text-secondary">
                  Loading guide questions...
                </p>
              </div>
              ) : questionsQuery.error ? (
              <div className="p-3 rounded-sm bg-canvas animate-fade-in">
                <p className="font-ui text-[12px] text-destructive">
                  Failed to load questions.
                </p>
              </div>
              ) : (questionsQuery.data?.questions || []).length === 0 ? (
              <div className="p-3 rounded-sm bg-canvas animate-fade-in">
                <p className="font-ui text-[12px] text-text-secondary">
                  Questions will appear here once the guide is generated.
                </p>
              </div>
              ) : (
              (questionsQuery.data?.questions || []).map((question, i) =>
                renderAnswerCard(question, i),
              )
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

export default InsightExtractor
