import {
  useEffect,
  useState,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useCallback,
  useRef,
} from 'react'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react'
import { Document, Page, pdfjs } from 'react-pdf'
import type { PaperSection, PaperSummary } from '@/types/api'

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

// Positive value nudges landing upward so section clicks do not land below target.
const SECTION_JUMP_TOP_OFFSET_PX = 500
const SCROLL_ANIMATION_MS = 500
const MIN_PDF_SCALE = 0.6
const MAX_PDF_SCALE = 2.5

interface WebkitGestureEvent extends Event {
  scale: number
}

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
  ({ paper, sections, onVisibleSectionChange, focusedSection }, ref) => {
    const scrollContainerRef = useRef<HTMLDivElement>(null)
    const pageRefs = useRef<Record<number, HTMLDivElement | null>>({})
    const jumpCorrectionTimerRef = useRef<number | null>(null)
    const alignAfterRenderPageRef = useRef<number | null>(null)
    const scrollAnimationFrameRef = useRef<number | null>(null)
    const scrollTickingRef = useRef(false)
    const lastGestureScaleRef = useRef(1)

    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [pdfBlob, setPdfBlob] = useState<Blob | null>(null)
    const [numPages, setNumPages] = useState<number>(0)
    const [pageNumber, setPageNumber] = useState<number>(1)
    const [scale, setScale] = useState<number>(1.1)
    const [pendingJumpPage, setPendingJumpPage] = useState<number | null>(null)

    const sortedSections = useMemo(
      () =>
        [...sections].sort(
          (a, b) =>
            Math.max(1, Number(a.page_start) || 1) -
            Math.max(1, Number(b.page_start) || 1),
        ),
      [sections],
    )

    const sectionPageMap = useMemo(
      () =>
        new Map(
          sections.map((section) => [
            String(section.id),
            Math.max(1, Number(section.page_start) || 1),
          ]),
        ),
      [sections],
    )

    const pageToSectionMap = useMemo(() => {
      const map = new Map<number, string>()
      if (sortedSections.length === 0 || numPages <= 0) return map

      let activeSectionId = String(sortedSections[0].id)
      for (let page = 1; page <= numPages; page += 1) {
        const match = sortedSections.find((section, idx) => {
          const currentStart = Math.max(1, Number(section.page_start) || 1)
          const nextStart =
            idx + 1 < sortedSections.length
              ? Math.max(1, Number(sortedSections[idx + 1].page_start) || 1)
              : Number.MAX_SAFE_INTEGER
          return page >= currentStart && page < nextStart
        })
        if (match) {
          activeSectionId = String(match.id)
        }
        map.set(page, activeSectionId)
      }
      return map
    }, [numPages, sortedSections])

    const getPageTop = useCallback((target: number) => {
      const container = scrollContainerRef.current
      const pageNode = pageRefs.current[target]
      if (!container || !pageNode) return null

      const containerRect = container.getBoundingClientRect()
      const pageRect = pageNode.getBoundingClientRect()
      const paddingTop = parseFloat(getComputedStyle(container).paddingTop) || 0
      const viewportNudge = container.clientHeight * 0.08

      return Math.max(
        0,
        pageRect.top -
          containerRect.top +
          container.scrollTop -
          paddingTop -
          SECTION_JUMP_TOP_OFFSET_PX -
          viewportNudge,
      )
    }, [])

    const stopScrollAnimation = useCallback(() => {
      if (scrollAnimationFrameRef.current) {
        window.cancelAnimationFrame(scrollAnimationFrameRef.current)
        scrollAnimationFrameRef.current = null
      }
    }, [])

    const smoothScrollTo = useCallback(
      (top: number, durationMs = SCROLL_ANIMATION_MS) => {
        const container = scrollContainerRef.current
        if (!container) return false

        stopScrollAnimation()

        const startTop = container.scrollTop
        const delta = top - startTop
        if (Math.abs(delta) < 1) {
          container.scrollTop = top
          return true
        }

        const start = performance.now()
        const easeInOutCubic = (t: number) =>
          t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2

        const step = (now: number) => {
          const elapsed = now - start
          const progress = Math.min(1, elapsed / durationMs)
          const eased = easeInOutCubic(progress)
          container.scrollTop = startTop + delta * eased
          if (progress < 1) {
            scrollAnimationFrameRef.current = window.requestAnimationFrame(step)
          } else {
            scrollAnimationFrameRef.current = null
          }
        }

        scrollAnimationFrameRef.current = window.requestAnimationFrame(step)
        return true
      },
      [stopScrollAnimation],
    )

    const alignPageToTop = useCallback(
      (target: number, behavior: ScrollBehavior = 'auto') => {
        const container = scrollContainerRef.current
        if (!container) return false

        const top = getPageTop(target)
        if (top === null) return false

        if (behavior === 'smooth') {
          return smoothScrollTo(top)
        }

        stopScrollAnimation()
        container.scrollTo({ top, behavior })
        return true
      },
      [getPageTop, smoothScrollTo, stopScrollAnimation],
    )

    const jumpToPage = useCallback(
      (rawPage: number, behavior: ScrollBehavior = 'smooth') => {
        const target = Math.max(
          1,
          numPages > 0 ? Math.min(rawPage, numPages) : rawPage,
        )
        setPageNumber(target)
        alignAfterRenderPageRef.current = target

        if (!alignPageToTop(target, behavior)) {
          setPendingJumpPage(target)
          return
        }

        // Re-apply alignment after render/layout settles to avoid slight drift.
        if (jumpCorrectionTimerRef.current) {
          window.clearTimeout(jumpCorrectionTimerRef.current)
        }
        jumpCorrectionTimerRef.current = window.setTimeout(() => {
          const container = scrollContainerRef.current
          const desiredTop = getPageTop(target)
          if (!container || desiredTop === null) return

          const drift = Math.abs(container.scrollTop - desiredTop)
          if (drift > 2) {
            smoothScrollTo(desiredTop, 180)
          }
        }, 180)
      },
      [alignPageToTop, getPageTop, numPages, smoothScrollTo],
    )

    const jumpToSection = useCallback(
      (sectionId: string) => {
        if (!sectionId) return
        const targetPage = sectionPageMap.get(String(sectionId))
        if (!targetPage) return
        jumpToPage(targetPage)
      },
      [jumpToPage, sectionPageMap],
    )

    useImperativeHandle(
      ref,
      () => ({
        scrollToSection: (sectionId: string) => {
          jumpToSection(sectionId)
        },
      }),
      [jumpToSection],
    )

    useEffect(() => {
      if (!focusedSection) return
      jumpToSection(focusedSection)
    }, [focusedSection, jumpToSection])

    useEffect(() => {
      if (!pendingJumpPage) return
      if (numPages <= 0) return
      jumpToPage(pendingJumpPage, 'auto')
      setPendingJumpPage(null)
    }, [jumpToPage, numPages, pendingJumpPage])

    useEffect(() => {
      return () => {
        if (jumpCorrectionTimerRef.current) {
          window.clearTimeout(jumpCorrectionTimerRef.current)
        }
        stopScrollAnimation()
        alignAfterRenderPageRef.current = null
      }
    }, [stopScrollAnimation])

    useEffect(() => {
      const activeSectionId = pageToSectionMap.get(pageNumber)
      if (activeSectionId) {
        onVisibleSectionChange(activeSectionId)
      }
    }, [onVisibleSectionChange, pageNumber, pageToSectionMap])

    useEffect(() => {
      const abortController = new AbortController()

      async function loadPdf(): Promise<void> {
        if (!paper?.id || !paper?.pdf_url) {
          setIsLoading(false)
          setError(null)
          setPdfBlob(null)
          setNumPages(0)
          setPageNumber(1)
          return
        }

        setIsLoading(true)
        setError(null)
        setPdfBlob(null)
        setNumPages(0)
        setPageNumber(1)
        setPendingJumpPage(null)
        setScale(1.1)

        const token = localStorage.getItem('researchagent.auth.token')
        const apiBase =
          import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
        const url = `${apiBase}${paper.pdf_url}`

        try {
          const response = await fetch(url, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            signal: abortController.signal,
          })

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`)
          }

          const contentType = response.headers.get('content-type') || ''
          if (!contentType.toLowerCase().includes('application/pdf')) {
            const preview = (await response.text()).slice(0, 200)
            throw new Error(
              `Expected PDF but got ${contentType || 'unknown type'}: ${preview}`,
            )
          }

          const blob = await response.blob()
          setPdfBlob(blob)
        } catch (err) {
          if ((err as Error).name === 'AbortError') return
          setError('Failed to load PDF. The document may not be available.')
          console.error('[PaperViewer] PDF fetch failed', err)
        } finally {
          setIsLoading(false)
        }
      }

      loadPdf()

      return () => {
        abortController.abort()
      }
    }, [paper?.id, paper?.pdf_url])

    const totalPages = numPages || 1
    const canGoPrev = pageNumber > 1
    const canGoNext = pageNumber < totalPages

    const zoomOut = () =>
      setScale((prev) => Math.max(MIN_PDF_SCALE, +(prev - 0.1).toFixed(2)))
    const zoomIn = () =>
      setScale((prev) => Math.min(MAX_PDF_SCALE, +(prev + 0.1).toFixed(2)))
    const goPrev = () => canGoPrev && jumpToPage(pageNumber - 1)
    const goNext = () => canGoNext && jumpToPage(pageNumber + 1)

    const handleViewerWheel = useCallback(
      (event: React.WheelEvent<HTMLDivElement>) => {
        // Trackpad pinch is surfaced as ctrl/meta+wheel in most browsers.
        if (!event.ctrlKey && !event.metaKey) return

        event.preventDefault()
        event.stopPropagation()

        const zoomStep = -event.deltaY * 0.0025
        setScale((prev) => {
          const next = prev + zoomStep
          const clamped = Math.min(MAX_PDF_SCALE, Math.max(MIN_PDF_SCALE, next))
          return +clamped.toFixed(2)
        })
      },
      [],
    )

    const handleViewerScroll = useCallback(() => {
      if (scrollTickingRef.current) return
      scrollTickingRef.current = true

      window.requestAnimationFrame(() => {
        const container = scrollContainerRef.current
        if (!container || numPages <= 0) {
          scrollTickingRef.current = false
          return
        }

        const viewportMarker =
          container.scrollTop + container.clientHeight * 0.25
        let nearestPage = 1
        let smallestDistance = Number.POSITIVE_INFINITY

        for (let page = 1; page <= numPages; page += 1) {
          const node = pageRefs.current[page]
          if (!node) continue
          const distance = Math.abs(node.offsetTop - viewportMarker)
          if (distance < smallestDistance) {
            smallestDistance = distance
            nearestPage = page
          }
        }

        setPageNumber((prev) => (prev === nearestPage ? prev : nearestPage))
        scrollTickingRef.current = false
      })
    }, [numPages])

    useEffect(() => {
      const container = scrollContainerRef.current
      if (!container) return

      // Safari trackpad pinch emits gesture events rather than ctrl+wheel.
      const handleGestureStart = (event: Event) => {
        const gestureEvent = event as WebkitGestureEvent
        event.preventDefault()
        lastGestureScaleRef.current = gestureEvent.scale || 1
      }

      const handleGestureChange = (event: Event) => {
        const gestureEvent = event as WebkitGestureEvent
        event.preventDefault()
        const currentScale = gestureEvent.scale || 1
        const ratio =
          currentScale / Math.max(0.0001, lastGestureScaleRef.current)
        lastGestureScaleRef.current = currentScale

        setScale((prev) => {
          const next = prev * ratio
          const clamped = Math.min(MAX_PDF_SCALE, Math.max(MIN_PDF_SCALE, next))
          return +clamped.toFixed(2)
        })
      }

      const handleGestureEnd = (event: Event) => {
        event.preventDefault()
        lastGestureScaleRef.current = 1
      }

      container.addEventListener('gesturestart', handleGestureStart, {
        passive: false,
      })
      container.addEventListener('gesturechange', handleGestureChange, {
        passive: false,
      })
      container.addEventListener('gestureend', handleGestureEnd, {
        passive: false,
      })

      return () => {
        container.removeEventListener('gesturestart', handleGestureStart)
        container.removeEventListener('gesturechange', handleGestureChange)
        container.removeEventListener('gestureend', handleGestureEnd)
      }
    }, [])

    return (
      <div className="flex-1 h-screen overflow-hidden bg-canvas flex flex-col">
        {/* Paper header */}
        <div className="border-b border-border/40 px-6 py-4 flex-shrink-0 bg-gradient-to-r from-accent/10 via-panel to-panel shadow-sm">
          <h1 className="font-serif text-[22px] leading-tight font-semibold text-foreground">
            {paper?.paper_name || 'No paper selected'}
          </h1>
        </div>

        {/* PDF Viewer or Loading/Error State */}
        {paper && pdfBlob ? (
          <div className="flex-1 relative bg-canvas overflow-hidden p-4">
            <div className="h-full flex flex-col rounded-xl border border-border/60 bg-panel shadow-sm overflow-hidden">
              <div className="h-12 border-b border-border/40 bg-gradient-to-r from-accent/10 via-panel to-panel px-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <button
                    onClick={goPrev}
                    disabled={!canGoPrev}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-border/60 text-text-secondary hover:text-foreground hover:bg-canvas disabled:opacity-40 disabled:cursor-not-allowed"
                    aria-label="Previous page"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <div className="px-2 py-1 rounded-md border border-border/70 bg-canvas min-w-[86px] text-center shadow-sm">
                    <span className="font-ui text-[12px] text-foreground">
                      {pageNumber} / {totalPages}
                    </span>
                  </div>
                  <button
                    onClick={goNext}
                    disabled={!canGoNext}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-border/60 text-text-secondary hover:text-foreground hover:bg-canvas disabled:opacity-40 disabled:cursor-not-allowed"
                    aria-label="Next page"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={zoomOut}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-border/60 text-text-secondary hover:text-foreground hover:bg-canvas"
                    aria-label="Zoom out"
                  >
                    <ZoomOut size={15} />
                  </button>
                  <div className="px-2 py-1 rounded-md border border-border/70 bg-canvas min-w-[72px] text-center shadow-sm">
                    <span className="font-ui text-[12px] text-foreground">
                      {Math.round(scale * 100)}%
                    </span>
                  </div>
                  <button
                    onClick={zoomIn}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-border/60 text-text-secondary hover:text-foreground hover:bg-canvas"
                    aria-label="Zoom in"
                  >
                    <ZoomIn size={15} />
                  </button>
                </div>
              </div>

              <div
                ref={scrollContainerRef}
                className="flex-1 overflow-auto p-5 bg-canvas"
                onScroll={handleViewerScroll}
                onWheel={handleViewerWheel}
              >
                <div className="min-h-full flex justify-center">
                  <Document
                    file={pdfBlob}
                    loading={
                      <div className="text-center py-14">
                        <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent mx-auto mb-3" />
                        <p className="font-ui text-sm text-text-secondary">
                          Rendering PDF...
                        </p>
                      </div>
                    }
                    onLoadSuccess={({ numPages: loadedPages }) => {
                      setNumPages(loadedPages)
                      setPageNumber((prev) =>
                        Math.max(1, Math.min(prev, loadedPages)),
                      )
                    }}
                    onLoadError={(docError) => {
                      console.error(
                        '[PaperViewer] Document load failed',
                        docError,
                      )
                      setError('Unable to render PDF document.')
                    }}
                  >
                    <div className="space-y-5 pb-6">
                      {Array.from({ length: numPages }, (_, idx) => {
                        const page = idx + 1
                        return (
                          <div
                            key={page}
                            ref={(node) => {
                              pageRefs.current[page] = node
                            }}
                            className="flex justify-center"
                            data-page-number={page}
                          >
                            <Page
                              pageNumber={page}
                              scale={scale}
                              renderTextLayer={false}
                              renderAnnotationLayer={false}
                              loading={
                                <div className="text-center py-8">
                                  <p className="font-ui text-sm text-text-secondary">
                                    Loading page {page}...
                                  </p>
                                </div>
                              }
                              onRenderError={(pageError) => {
                                console.error(
                                  '[PaperViewer] Page render failed',
                                  pageError,
                                )
                                setError('Unable to render this page.')
                              }}
                              onRenderSuccess={() => {
                                if (alignAfterRenderPageRef.current === page) {
                                  alignPageToTop(page, 'smooth')
                                  alignAfterRenderPageRef.current = null
                                }
                              }}
                            />
                          </div>
                        )
                      })}
                    </div>
                  </Document>
                </div>
              </div>
            </div>

            {!isLoading && !error && sections.length > 0 ? (
              <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 px-2 py-1 rounded-full bg-panel/90 border border-border/50 shadow-sm">
                <span className="font-ui text-[11px] text-text-secondary">
                  Click any topic in Reading Guide or Paper Structure to jump to
                  its page.
                </span>
              </div>
            ) : null}

            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-canvas/80 z-20">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-2 border-accent border-t-transparent mx-auto mb-3" />
                  <p className="font-ui text-sm text-text-secondary">
                    Loading document...
                  </p>
                </div>
              </div>
            )}

            {error && (
              <div className="absolute inset-0 flex items-center justify-center bg-canvas/90 z-30">
                <div className="max-w-md text-center px-6">
                  <div className="text-3xl mb-4">⚠️</div>
                  <p className="font-ui text-sm text-destructive mb-2">
                    {error}
                  </p>
                  <p className="font-ui text-xs text-text-secondary">
                    This may be an extracted content preview instead of the
                    original PDF.
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <p className="font-ui text-sm text-text-secondary">
              {paper ? 'Loading PDF...' : 'No paper selected'}
            </p>
          </div>
        )}
      </div>
    )
  },
)

PaperViewer.displayName = 'PaperViewer'
export default PaperViewer
