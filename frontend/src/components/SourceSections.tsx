interface ChatSource {
  section_title: string
  section_id?: string
  page?: number
}

interface SourceSectionsProps {
  sections: ChatSource[]
  onSectionClick?: (source: ChatSource) => void
}

export const SourceSections = ({
  sections,
  onSectionClick,
}: SourceSectionsProps) => {
  if (!sections || sections.length === 0) {
    return (
      <div className="mt-3 pt-2 border-t border-border/40">
        <p className="mb-2 font-ui text-[11px] tracking-[0.08em] uppercase text-text-secondary/70">
          Used sections
        </p>
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1.5">
          <p className="font-ui text-[11px] text-emerald-700">
            No section metadata returned for this answer.
          </p>
        </div>
      </div>
    )
  }

  const uniqueSections = Array.from(
    new Map(
      sections
        .filter((s) => s.section_title)
        .map((s) => [s.section_title, s]),
    ).values(),
  )

  return (
    <div className="mt-3 pt-2 border-t border-border/40">
      <p className="mb-2 font-ui text-[11px] tracking-[0.08em] uppercase text-text-secondary/70">
        Used sections
      </p>
      <div className="flex flex-wrap gap-1.5">
        {uniqueSections.map((source, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => onSectionClick?.(source)}
            className={`
              inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full
              bg-emerald-500/15 border border-emerald-500/40 hover:border-emerald-500/60
              text-emerald-700 hover:text-emerald-600 hover:bg-emerald-500/20
              font-ui text-[11px] font-medium transition-all duration-200
              hover:shadow-sm hover:shadow-emerald-500/20
              active:scale-95
            `}
            title={`Navigate to ${source.section_title}${source.page ? ` (page ${source.page})` : ''}`}
          >
            <svg
              className="w-3 h-3 flex-shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>{source.section_title}</span>
            {source.page && (
              <span className="text-emerald-600/70 ml-0.5">
                p{source.page}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
