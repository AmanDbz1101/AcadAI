import {
  useEffect,
  useRef,
  useState,
  forwardRef,
  useImperativeHandle,
} from 'react'
import type { PaperSection, PaperSummary } from '@/types/api'

export interface PaperViewerHandle {
  scrollToSection: (sectionId: string) => void
}

interface PaperViewerProps {
  onVisibleSectionChange: (sectionId: string) => void
  focusedSection: string | null
  paper: PaperSummary | null
  sections: PaperSection[]
}

const PaperViewer = forwardRef<PaperViewerHandle, PaperViewerProps>(
  ({ onVisibleSectionChange, focusedSection, paper, sections }, ref) => {
    const containerRef = useRef<HTMLDivElement>(null)
    const sectionRefs = useRef<Record<string, HTMLElement | null>>({})

    useImperativeHandle(ref, () => ({
      scrollToSection: (sectionId: string) => {
        const el = sectionRefs.current[sectionId]
        if (el && containerRef.current) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      },
    }))

    useEffect(() => {
      const container = containerRef.current
      if (!container) return

      const observer = new IntersectionObserver(
        (entries) => {
          const visible = entries
            .filter((e) => e.isIntersecting)
            .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
          if (visible.length > 0) {
            const id = visible[0].target.getAttribute('data-section')
            if (id) onVisibleSectionChange(id)
          }
        },
        { root: container, rootMargin: '-20% 0px -60% 0px', threshold: 0 },
      )

      Object.values(sectionRefs.current).forEach((el) => {
        if (el) observer.observe(el)
      })

      return () => observer.disconnect()
    }, [onVisibleSectionChange])

    return (
      <div
        ref={containerRef}
        className="flex-1 h-screen overflow-y-auto scrollbar-thin bg-canvas"
      >
        <div className="max-w-[720px] mx-auto px-6 py-12">
          {/* Paper title */}
          <header className="mb-12">
            <h1 className="font-serif text-[28px] leading-[1.3] font-semibold text-foreground mb-4">
              {paper?.paper_name || 'No paper selected'}
            </h1>
            <p className="font-ui text-[13px] text-text-secondary leading-relaxed">
              {paper?.title || 'Research Paper'}
            </p>
            <p className="font-ui text-[12px] text-text-secondary opacity-60 mt-1">
              {paper?.source_pdf_path || 'Stored in PostgreSQL'}
            </p>
          </header>

          {/* Paper sections */}
          {sections.map((section) => (
            <section
              key={section.id}
              data-section={section.id}
              ref={(el) => {
                sectionRefs.current[section.id] = el
              }}
              className={`mb-10 transition-opacity duration-600 ${
                focusedSection && focusedSection !== section.id
                  ? 'section-faded'
                  : 'section-focused'
              }`}
            >
              <h2 className="font-serif text-[20px] font-semibold text-foreground mb-4">
                {section.title}
              </h2>
              {(section.content || 'No text mapped for this section yet.')
                .split('\n\n')
                .filter((paragraph) => paragraph.trim().length > 0)
                .map((paragraph, i) => (
                  <p
                    key={i}
                    className="font-serif text-[15px] leading-[1.8] text-foreground mb-4 last:mb-0"
                  >
                    {paragraph}
                  </p>
                ))}
            </section>
          ))}

          <div className="h-32" />
        </div>
      </div>
    )
  },
)

PaperViewer.displayName = 'PaperViewer'
export default PaperViewer
