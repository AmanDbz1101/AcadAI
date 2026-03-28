import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Maximize2, Minimize2 } from 'lucide-react'
import {
  generateQuestionAnswer,
  generateTechnicalTermDefinition,
  getPaperQuestions,
} from '@/lib/api'
import type {
  PaperImage,
  PaperQuestion,
  PaperSection,
  TechnicalTerm,
} from '@/types/api'

type TabKey = 'terms' | 'figures' | 'answers'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'terms', label: 'Technical Terms' },
  { key: 'figures', label: 'Figures' },
  { key: 'answers', label: 'Answers' },
]

interface InsightExtractorProps {
  paperId: number | null
  sections: PaperSection[]
  images: PaperImage[]
  technicalTerms: TechnicalTerm[]
}

const InsightExtractor = ({
  paperId,
  sections,
  images,
  technicalTerms,
}: InsightExtractorProps) => {
  void sections

  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<TabKey>('terms')
  const [isFullscreen, setIsFullscreen] = useState(false)

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

  const generateTermDefinitionMutation = useMutation({
    mutationFn: ({ term }: { term: string }) =>
      generateTechnicalTermDefinition(paperId as number, term),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['paper-bundle', paperId],
      })
    },
  })

  const figureCards = useMemo(
    () =>
      images.length
        ? images.slice(0, 8).map((img, idx) => ({
            title: `Figure ${idx + 1} · Page ${img.page_number ?? '?'}`,
            description: img.caption || img.image_path || 'Stored image asset',
          }))
        : [
            {
              title: 'No figures',
              description: 'No stored figures for this paper.',
            },
          ],
    [images],
  )

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

  const renderTechnicalTermCard = (term: TechnicalTerm, index: number) => {
    const source = term.definition_source
    const hasApiDefinition =
      source === 'cso' || source === 'inspire' || source === 'wikipedia'
    const isGenerating =
      generateTermDefinitionMutation.isPending &&
      generateTermDefinitionMutation.variables?.term === term.term
    const canGenerate = !isGenerating && paperId !== null

    const buttonLabel = isGenerating
      ? 'Generating...'
      : hasApiDefinition || source === 'llm'
        ? 'Regenerate'
        : 'Generate definition'

    const sourceLabel =
      source === 'cso' || source === 'inspire'
        ? 'Ontology/API'
        : source === 'wikipedia'
          ? 'Wikipedia'
          : source === 'llm'
            ? 'LLM'
            : 'LLM (pending)'

    return (
      <div
        key={term.term}
        className="p-3 rounded-sm bg-canvas animate-fade-in"
        style={{ animationDelay: `${index * 80}ms` }}
      >
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <h4 className="font-ui text-[13px] font-medium text-foreground leading-snug">
            {term.term}
          </h4>
          <span className="font-ui text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-text-active uppercase tracking-wide">
            {sourceLabel}
          </span>
        </div>

        {term.definition ? (
          <p className="font-ui text-[12px] text-text-secondary leading-relaxed whitespace-pre-wrap">
            {term.definition}
          </p>
        ) : (
          <p className="font-ui text-[12px] text-text-secondary leading-relaxed">
            Definition is not generated yet. Click the button below to generate it using LLM.
          </p>
        )}

        <p className="mt-1 font-ui text-[11px] text-text-secondary">
          {term.expansion ? `Expansion: ${term.expansion} · ` : ''}
          {term.source_sections?.length
            ? `From: ${term.source_sections.join(', ')}`
            : 'From: abstract/introduction'}
        </p>

        <button
          onClick={() => generateTermDefinitionMutation.mutate({ term: term.term })}
          disabled={!canGenerate}
          className="mt-2 font-ui text-[11px] px-2.5 py-1.5 rounded-md border border-border/60 text-foreground hover:border-primary/40 hover:text-text-active transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {buttonLabel}
        </button>
      </div>
    )
  }

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

  const renderContent = () => {
    if (activeTab === 'answers') {
      if (paperId === null) {
        return (
          <div className="p-3 rounded-sm bg-canvas">
            <p className="font-ui text-[12px] text-text-secondary">
              Select a paper to view guide questions.
            </p>
          </div>
        )
      }

      if (questionsQuery.isLoading) {
        return (
          <div className="p-3 rounded-sm bg-canvas animate-fade-in">
            <p className="font-ui text-[12px] text-text-secondary">
              Loading guide questions...
            </p>
          </div>
        )
      }

      if (questionsQuery.error) {
        return (
          <div className="p-3 rounded-sm bg-canvas animate-fade-in">
            <p className="font-ui text-[12px] text-destructive">
              Failed to load questions.
            </p>
          </div>
        )
      }

      const questions = questionsQuery.data?.questions || []
      if (questions.length === 0) {
        return (
          <div className="p-3 rounded-sm bg-canvas animate-fade-in">
            <p className="font-ui text-[12px] text-text-secondary">
              Questions will appear here once the guide is generated.
            </p>
          </div>
        )
      }

      return questions.map((question, i) => renderAnswerCard(question, i))
    }

    if (activeTab === 'terms') {
      if (technicalTerms.length === 0) {
        return (
          <div className="p-3 rounded-sm bg-canvas animate-fade-in">
            <h4 className="font-ui text-[13px] font-medium text-foreground mb-1">
              No technical terms yet
            </h4>
            <p className="font-ui text-[12px] text-text-secondary leading-relaxed">
              Terms will appear when abstract or introduction content is available from the backend.
            </p>
          </div>
        )
      }

      return technicalTerms
        .slice(0, 8)
        .map((term, i) => renderTechnicalTermCard(term, i))
    }

    return figureCards.map((item, i) => (
      <div
        key={`${item.title}-${i}`}
        className="p-3 rounded-lg border border-border/60 bg-panel animate-fade-in shadow-sm"
        style={{ animationDelay: `${i * 80}ms` }}
      >
        <h4 className="font-ui text-[13px] font-medium text-foreground mb-1">
          {item.title}
        </h4>
        <p className="font-ui text-[12px] text-text-secondary leading-relaxed">
          {item.description}
        </p>
      </div>
    ))
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
          <div className="flex gap-1 mb-4 flex-shrink-0">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`font-ui text-[12px] py-1.5 px-3 rounded-md border transition-all duration-200 ${
                  activeTab === tab.key
                    ? 'bg-primary text-primary-foreground border-primary/70 font-medium shadow-sm'
                    : 'text-text-secondary border-border/60 bg-panel hover:text-foreground hover:border-accent/30'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2">
            {renderContent()}
          </div>
        </div>
      </div>
    </>
  )
}

export default InsightExtractor
