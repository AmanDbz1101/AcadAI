interface SourceSection {
  section_title: string
  section_id?: string
  page_start?: number
}

interface SourceSectionsProps {
  sections: SourceSection[]
  onSectionClick?: (section: SourceSection) => void
}

export function SourceSections({ sections, onSectionClick }: SourceSectionsProps) {
  if (!sections || sections.length === 0) return null

  const unique = sections.filter(
    (section, index, arr) =>
      arr.findIndex((item) => item.section_title === section.section_title) === index,
  )

  return (
    <div className="mt-2 pt-2 border-t border-gray-100 dark:border-gray-700">
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-1 font-medium uppercase tracking-wide">
        Sources
      </p>
      <div className="flex flex-wrap gap-1.5">
        {unique.map((section, index) => (
          <button
            key={index}
            type="button"
            onClick={() => onSectionClick?.(section)}
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 transition-all duration-150 ${
              onSectionClick
                ? 'cursor-pointer hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600 dark:hover:bg-blue-950/40 dark:hover:border-blue-700 dark:hover:text-blue-400 active:scale-95'
                : 'cursor-default'
            }`}
            title={
              section.page_start
                ? `Jump to ${section.section_title} (p.${section.page_start})`
                : `Jump to ${section.section_title}`
            }
          >
            <svg
              className="w-3 h-3 opacity-60 flex-shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <span className="font-medium">{section.section_title}</span>
            {section.page_start ? (
              <span className="opacity-50 text-[10px]">p.{section.page_start}</span>
            ) : null}
            {onSectionClick ? (
              <svg
                className="w-2.5 h-2.5 opacity-40 flex-shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
                />
              </svg>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  )
}