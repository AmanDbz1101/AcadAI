import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

  const generateTermDefinitionMutation = useMutation({
    mutationFn: ({ term }: { term: string }) =>
      generateTechnicalTermDefinition(paperId as number, term),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['paper-bundle', paperId],
      })
    },
  })

  const insightData = useMemo<Record<'terms' | 'figures', { title: string; description: string }[]>>(() => {
    const termCards = technicalTerms.length
      ? technicalTerms.slice(0, 8).map((term) => ({
          title: term.term,
          description: [
            term.expansion ? `Expansion: ${term.expansion}` : null,
            term.source_sections?.length
              ? `Source: ${term.source_sections.join(', ')}`
              : 'Source: abstract/introduction',
          ]
            .filter(Boolean)
            .join(' · '),
        }))
      : [
          {
            title: 'No technical terms yet',
            description:
              'Terms will appear when abstract/introduction content is available from the backend.',
          },
        ]

    const figureCards = images.length
      ? images.slice(0, 8).map((img, idx) => ({
          title: `Figure ${idx + 1} · Page ${img.page_number ?? '?'}`,
          description: img.caption || img.image_path || 'Stored image asset',
        }))
      : [
          {
            title: 'No figures',
            description: 'No stored figures for this paper.',
          },
        ]

    return {
      terms: termCards,
      figures: figureCards,
    }
  }, [technicalTerms, images])

  const [activeTab, setActiveTab] = useState<TabKey>('terms')

  const renderTechnicalTermCard = (term: TechnicalTerm, index: number) => {
    const source = term.definition_source
    const hasApiDefinition = source === 'cso' || source === 'inspire' || source === 'wikipedia'
    const isGenerating =
      generateTermDefinitionMutation.isPending &&
      generateTermDefinitionMutation.variables?.term === term.term
    const canGenerate = !isGenerating && paperId !== null

    const buttonLabel = isGenerating
      ? 'Generating...'
      : hasApiDefinition || source === 'llm'
        ? 'Regenerate'
        : 'Generate definition'

    const sourceLabel = source === 'cso' || source === 'inspire'
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

  return (
    <div className="mb-6">
      <h3 className="font-ui text-xs font-medium uppercase tracking-[0.15em] text-text-secondary mb-4">
        Insight Extractor
      </h3>

      {/* Tabs */}
      <div className="flex gap-1 mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`
              font-ui text-[12px] py-1.5 px-3 rounded-sm transition-all duration-200
              ${
                activeTab === tab.key
                  ? 'bg-primary text-primary-foreground font-medium'
                  : 'text-text-secondary hover:text-foreground'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab !== 'answers' ? (
        <div className="space-y-2">
          {activeTab === 'terms' ? (
            technicalTerms.length > 0 ? (
              technicalTerms.slice(0, 8).map((term, i) => renderTechnicalTermCard(term, i))
            ) : (
              <div className="p-3 rounded-sm bg-canvas animate-fade-in">
                <h4 className="font-ui text-[13px] font-medium text-foreground mb-1">
                  No technical terms yet
                </h4>
                <p className="font-ui text-[12px] text-text-secondary leading-relaxed">
                  Terms will appear when abstract/introduction content is available from the backend.
                </p>
              </div>
            )
          ) : (
            insightData[activeTab].map((item, i) => (
              <div
                key={i}
                className="p-3 rounded-sm bg-canvas animate-fade-in"
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
          )}
        </div>
      ) : (
        <div className="space-y-2">
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
  )
}

export default InsightExtractor
