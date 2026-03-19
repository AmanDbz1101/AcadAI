import { useState, useRef, useCallback } from 'react'
import PaperNavigation from '@/components/PaperNavigation'
import PaperViewer, { PaperViewerHandle } from '@/components/PaperViewer'
import AIToolsPanel from '@/components/AIToolsPanel'
import { useQuery } from '@tanstack/react-query'
import { getPaperBundle, getPapers } from '@/lib/api'

const Index = () => {
  const [activeSection, setActiveSection] = useState('')
  const [focusedSection, setFocusedSection] = useState<string | null>(null)
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(null)
  const viewerRef = useRef<PaperViewerHandle>(null)

  const papersQuery = useQuery({
    queryKey: ['papers'],
    queryFn: getPapers,
  })

  const papers = papersQuery.data ?? []

  const effectivePaperId = selectedPaperId ?? papers[0]?.id ?? null

  const paperBundleQuery = useQuery({
    queryKey: ['paper-bundle', effectivePaperId],
    queryFn: () => getPaperBundle(effectivePaperId as number),
    enabled: effectivePaperId !== null,
  })

  const sections = paperBundleQuery.data?.sections ?? []
  const paper = paperBundleQuery.data?.paper ?? null
  const images = paperBundleQuery.data?.images ?? []
  const tables = paperBundleQuery.data?.tables ?? []

  const navSections = sections.map((section, idx) => ({
    id: section.id,
    title: section.title,
    label: String(idx + 1).padStart(2, '0'),
  }))

  const handleSectionClick = useCallback((sectionId: string) => {
    setActiveSection(sectionId)
    setFocusedSection(sectionId)
    viewerRef.current?.scrollToSection(sectionId)

    // Clear focus effect after scroll completes
    setTimeout(() => {
      setFocusedSection(null)
    }, 1500)
  }, [])

  const handleVisibleSectionChange = useCallback((sectionId: string) => {
    setActiveSection(sectionId)
  }, [])

  const handlePaperSelect = useCallback((paperId: number) => {
    setSelectedPaperId(paperId)
    setActiveSection('')
    setFocusedSection(null)
  }, [])

  if (papersQuery.isLoading || paperBundleQuery.isLoading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas">
        <p className="font-ui text-sm text-text-secondary">
          Loading paper data from backend...
        </p>
      </div>
    )
  }

  if (papersQuery.error || paperBundleQuery.error) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas px-6">
        <p className="font-ui text-sm text-destructive text-center">
          Unable to load backend data. Ensure backend API is running at
          VITE_API_BASE_URL (default http://localhost:8000).
        </p>
      </div>
    )
  }

  if (papers.length === 0) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas px-6">
        <p className="font-ui text-sm text-text-secondary text-center">
          No papers found in the database yet. Run extraction first to populate
          data.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <PaperNavigation
        activeSection={activeSection}
        onSectionClick={handleSectionClick}
        sections={navSections}
        papers={papers}
        selectedPaperId={effectivePaperId}
        onPaperSelect={handlePaperSelect}
      />
      <PaperViewer
        ref={viewerRef}
        onVisibleSectionChange={handleVisibleSectionChange}
        focusedSection={focusedSection}
        paper={paper}
        sections={sections}
      />
      <AIToolsPanel images={images} tables={tables} />
    </div>
  )
}

export default Index
