import { useState, useRef, useCallback } from 'react'
import PaperNavigation from '@/components/PaperNavigation'
import PaperViewer, { PaperViewerHandle } from '@/components/PaperViewer'
import AIToolsPanel from '@/components/AIToolsPanel'
import EmptyStateUpload from '@/components/EmptyStateUpload'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getPaperBundle, getPapers, uploadPaper } from '@/lib/api'

const Index = () => {
  const queryClient = useQueryClient()
  const [paperLoaded, setPaperLoaded] = useState(false)
  const [activeSection, setActiveSection] = useState('')
  const [focusedSection, setFocusedSection] = useState<string | null>(null)
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(null)
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const viewerRef = useRef<PaperViewerHandle>(null)

  const papersQuery = useQuery({
    queryKey: ['papers'],
    queryFn: getPapers,
  })

  const papers = papersQuery.data ?? []

  const effectivePaperId = selectedPaperId ?? papers[0]?.id ?? null

  const uploadPaperMutation = useMutation({
    mutationFn: uploadPaper,
    onMutate: (file: File) => {
      setUploadError(null)
      setUploadedFileName(file.name)
    },
    onSuccess: async (data) => {
      const newPaperId = data.paper.id
      setSelectedPaperId(newPaperId)
      setActiveSection('')
      setFocusedSection(null)
      setPaperLoaded(true)

      await queryClient.invalidateQueries({ queryKey: ['papers'] })
      await queryClient.invalidateQueries({
        queryKey: ['paper-bundle', newPaperId],
      })
    },
    onError: (error: Error) => {
      setUploadedFileName(null)
      setUploadError(error.message || 'Upload failed')
    },
  })

  const paperBundleQuery = useQuery({
    queryKey: ['paper-bundle', effectivePaperId],
    queryFn: () => getPaperBundle(effectivePaperId as number),
    enabled: paperLoaded && effectivePaperId !== null,
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

  const handleFileUploaded = useCallback(
    (file: File) => {
      uploadPaperMutation.mutate(file)
    },
    [uploadPaperMutation],
  )

  const handleFileBadgeClear = useCallback((fileName: string | null) => {
    setUploadedFileName(fileName)
    if (fileName === null) {
      setPaperLoaded(false)
    }
  }, [])

  if (!paperLoaded) {
    return (
      <div className="flex h-screen overflow-hidden">
        <EmptyStateUpload
          onFileUploaded={handleFileUploaded}
          isUploading={uploadPaperMutation.isPending}
          errorMessage={uploadError}
        />
      </div>
    )
  }

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
          No papers found in the database yet. Upload a paper to continue.
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
        uploadedFileName={uploadedFileName}
        onFileChange={handleFileBadgeClear}
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
