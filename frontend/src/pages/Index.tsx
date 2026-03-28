import { useState, useRef, useCallback, useEffect, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import PaperNavigation from '@/components/PaperNavigation'
import PaperViewer, { PaperViewerHandle } from '@/components/PaperViewer'
import AIToolsPanel from '@/components/AIToolsPanel'
import ChatAssistant from '@/components/ChatAssistant'
import EmptyStateUpload from '@/components/EmptyStateUpload'
import {
  type AuthUser,
  clearAuthSession,
  deleteCmsPaper,
  getCachedAuthUser,
  getMe,
  getPaperBundle,
  getPapers,
  loginUser,
  registerUser,
  setAuthSession,
  uploadPaper,
} from '@/lib/api'

const SELECTED_PAPER_KEY = 'researchagent.selectedPaperId'

const Index = () => {
  const queryClient = useQueryClient()
  const viewerRef = useRef<PaperViewerHandle>(null)

  const [authUser, setAuthUser] = useState<AuthUser | null>(getCachedAuthUser())
  const [authSubmitting, setAuthSubmitting] = useState(false)
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authDisplayName, setAuthDisplayName] = useState('')
  const [authError, setAuthError] = useState<string | null>(null)

  const [paperLoaded, setPaperLoaded] = useState(false)
  const [activeSection, setActiveSection] = useState('')
  const [focusedSection, setFocusedSection] = useState<string | null>(null)
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(() => {
    const cached = localStorage.getItem(SELECTED_PAPER_KEY)
    return cached ? Number(cached) || null : null
  })

  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadTransitioning, setUploadTransitioning] = useState(false)
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null)
  const [showHomeView, setShowHomeView] = useState(false)

  const [guideCollapsed, setGuideCollapsed] = useState(false)
  const [guideWidth, setGuideWidth] = useState(320)
  const [toolsWidth, setToolsWidth] = useState(300)
  const [isResizing, setIsResizing] = useState(false)
  const [resizeTarget, setResizeTarget] = useState<'guide' | 'tools' | null>(
    null,
  )

  const handleGuideMouseDown = useCallback((event: React.MouseEvent) => {
    setIsResizing(true)
    setResizeTarget('guide')
    event.preventDefault()
  }, [])

  const handleToolsMouseDown = useCallback((event: React.MouseEvent) => {
    setIsResizing(true)
    setResizeTarget('tools')
    event.preventDefault()
  }, [])

  const handleMouseMove = useCallback(
    (event: MouseEvent) => {
      if (!isResizing || !resizeTarget) return

      if (resizeTarget === 'guide') {
        const minWidth = 250
        const maxWidth = Math.min(600, window.innerWidth * 0.4)
        const newWidth = Math.max(minWidth, Math.min(maxWidth, event.clientX))
        setGuideWidth(newWidth)
        return
      }

      const viewportWidth = window.innerWidth
      const minWidth = 250
      const maxWidth = Math.min(500, viewportWidth * 0.4)
      const newWidth = Math.max(
        minWidth,
        Math.min(maxWidth, viewportWidth - event.clientX),
      )
      setToolsWidth(newWidth)
    },
    [isResizing, resizeTarget],
  )

  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
    setResizeTarget(null)
  }, [])

  useEffect(() => {
    if (!isResizing) {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.body.style.webkitUserSelect = ''
      return
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.body.style.webkitUserSelect = 'none'

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.body.style.webkitUserSelect = ''
    }
  }, [isResizing, handleMouseMove, handleMouseUp])

  useEffect(() => {
    if (!authUser) return

    let cancelled = false

    getMe()
      .then((result) => {
        if (!cancelled) {
          setAuthUser(result.user)
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearAuthSession()
          setAuthUser(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [authUser?.id])

  useEffect(() => {
    if (selectedPaperId === null) {
      localStorage.removeItem(SELECTED_PAPER_KEY)
      return
    }

    localStorage.setItem(SELECTED_PAPER_KEY, String(selectedPaperId))
  }, [selectedPaperId])

  const papersQuery = useQuery({
    queryKey: ['papers'],
    queryFn: getPapers,
    enabled: Boolean(authUser),
  })

  const papers = papersQuery.data ?? []

  useEffect(() => {
    if (!authUser || papersQuery.isLoading || showHomeView) return

    if (papers.length > 0) {
      if (!selectedPaperId) {
        setSelectedPaperId(papers[0].id)
      }
      if (!paperLoaded) {
        setPaperLoaded(true)
      }
    }
  }, [
    authUser,
    papers,
    papersQuery.isLoading,
    paperLoaded,
    selectedPaperId,
    showHomeView,
  ])

  const effectivePaperId = selectedPaperId ?? papers[0]?.id ?? null

  const uploadPaperMutation = useMutation({
    mutationFn: uploadPaper,
    onMutate: (file: File) => {
      setUploadError(null)
      setUploadedFileName(file.name)
      setUploadTransitioning(true)
    },
    onSuccess: async (data) => {
      const newPaperId = data.paper.id
      setSelectedPaperId(newPaperId)
      setActiveSection('')
      setFocusedSection(null)
      setPaperLoaded(true)
      setShowHomeView(false)
      setUploadTransitioning(false)

      await queryClient.invalidateQueries({ queryKey: ['papers'] })
      await queryClient.invalidateQueries({ queryKey: ['paper-bundle', newPaperId] })
    },
    onError: (error: Error) => {
      setUploadTransitioning(false)
      setUploadedFileName(null)
      setUploadError(error.message || 'Upload failed')
    },
  })

  const deletePaperMutation = useMutation({
    mutationFn: deleteCmsPaper,
    onSuccess: async (_data, deletedPaperId) => {
      const remainingPapers = papers.filter((item) => item.id !== deletedPaperId)

      if (selectedPaperId === deletedPaperId) {
        const nextPaperId = remainingPapers[0]?.id ?? null
        setSelectedPaperId(nextPaperId)
      }

      if (remainingPapers.length === 0) {
        setShowHomeView(true)
        setPaperLoaded(false)
      }

      setActiveSection('')
      setFocusedSection(null)

      await queryClient.invalidateQueries({ queryKey: ['papers'] })
      await queryClient.invalidateQueries({
        queryKey: ['paper-bundle', deletedPaperId],
      })
    },
  })

  const paperBundleQuery = useQuery({
    queryKey: ['paper-bundle', effectivePaperId],
    queryFn: () => getPaperBundle(effectivePaperId as number),
    enabled: Boolean(authUser) && paperLoaded && effectivePaperId !== null,
    refetchInterval: (query) => {
      const status = (
        query.state.data as { guide_status?: { status?: string } } | undefined
      )?.guide_status?.status
      return status === 'pending' ? 2000 : false
    },
  })

  const sections = paperBundleQuery.data?.sections ?? []
  const paper = paperBundleQuery.data?.paper ?? null
  const images = paperBundleQuery.data?.images ?? []
  const technicalTerms = paperBundleQuery.data?.technical_terms ?? []
  const tables = paperBundleQuery.data?.tables ?? []

  const navSections = sections.map((section, index) => ({
    id: section.id,
    title: section.title,
    label: String(index + 1).padStart(2, '0'),
  }))

  const handleSectionClick = useCallback((sectionId: string) => {
    setActiveSection(sectionId)
    setFocusedSection(sectionId)
    viewerRef.current?.scrollToSection(sectionId)

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
    setShowHomeView(false)
    setPaperLoaded(true)
  }, [])

  const handlePaperDelete = useCallback(
    (paperId: number, paperName: string) => {
      if (deletePaperMutation.isPending) return

      const confirmed = window.confirm(
        `Delete "${paperName}" from CMS? This also removes it from Postgres and Qdrant.`,
      )
      if (!confirmed) return

      deletePaperMutation.mutate(paperId)
    },
    [deletePaperMutation],
  )

  const handleHomeClick = useCallback(() => {
    setSelectedPaperId(null)
    setActiveSection('')
    setFocusedSection(null)
    setShowHomeView(true)
  }, [])

  const handleFileUploaded = useCallback(
    (file: File) => {
      uploadPaperMutation.mutate(file)
    },
    [uploadPaperMutation],
  )

  const handleAuthSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      setAuthError(null)
      setAuthSubmitting(true)

      try {
        const response =
          authMode === 'register'
            ? await registerUser({
                email: authEmail.trim(),
                password: authPassword,
                display_name: authDisplayName.trim() || undefined,
              })
            : await loginUser({
                email: authEmail.trim(),
                password: authPassword,
              })

        setAuthSession(response.token, response.user)
        setAuthUser(response.user)
        setAuthPassword('')
        await queryClient.invalidateQueries({ queryKey: ['papers'] })
      } catch (error) {
        setAuthError(
          error instanceof Error ? error.message : 'Authentication failed',
        )
      } finally {
        setAuthSubmitting(false)
      }
    },
    [authDisplayName, authEmail, authMode, authPassword, queryClient],
  )

  const handleLogout = useCallback(() => {
    clearAuthSession()
    setAuthUser(null)
    setPaperLoaded(false)
    setSelectedPaperId(null)
    setUploadError(null)
    setUploadTransitioning(false)
    setUploadedFileName(null)
    setShowHomeView(false)
    queryClient.clear()
  }, [queryClient])

  if (!authUser) {
    return (
      <div className="h-screen w-full bg-canvas flex items-center justify-center px-6">
        <div className="w-full max-w-md bg-panel border border-border/60 rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-accent/20 bg-gradient-to-r from-accent/10 via-accent/5 to-transparent">
            <h1 className="font-ui text-[22px] font-bold text-foreground mb-1">
              AcadAI
            </h1>
            <p className="font-ui text-[13px] text-text-secondary">
              {authMode === 'register'
                ? 'Create your account'
                : 'Sign in to continue'}
            </p>
          </div>

          <div className="p-6 bg-canvas">
            <form className="space-y-3" onSubmit={handleAuthSubmit}>
              {authMode === 'register' ? (
                <input
                  type="text"
                  value={authDisplayName}
                  onChange={(event) => setAuthDisplayName(event.target.value)}
                  placeholder="Display name"
                  className="w-full rounded-md bg-canvas border border-border/60 px-3 py-2 text-sm text-foreground"
                />
              ) : null}
              <input
                type="email"
                value={authEmail}
                onChange={(event) => setAuthEmail(event.target.value)}
                placeholder="Email"
                required
                className="w-full rounded-md bg-canvas border border-border/60 px-3 py-2 text-sm text-foreground"
              />
              <input
                type="password"
                value={authPassword}
                onChange={(event) => setAuthPassword(event.target.value)}
                placeholder="Password"
                required
                className="w-full rounded-md bg-canvas border border-border/60 px-3 py-2 text-sm text-foreground"
              />
              <button
                type="submit"
                disabled={authSubmitting}
                className="w-full rounded-md bg-accent/20 hover:bg-accent/30 text-foreground px-3 py-2 text-sm font-semibold transition-colors disabled:opacity-60"
              >
                {authSubmitting
                  ? 'Please wait...'
                  : authMode === 'register'
                    ? 'Create account'
                    : 'Sign in'}
              </button>
            </form>
            {authError ? (
              <p className="mt-3 font-ui text-[12px] text-destructive">
                {authError}
              </p>
            ) : null}
            <button
              onClick={() =>
                setAuthMode(authMode === 'register' ? 'login' : 'register')
              }
              className="mt-4 font-ui text-[12px] text-text-secondary hover:text-foreground transition-colors"
            >
              {authMode === 'register'
                ? 'Already have an account? Sign in'
                : 'New here? Create an account'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (papersQuery.isLoading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas">
        <p className="font-ui text-sm text-text-secondary">Loading papers...</p>
      </div>
    )
  }

  if (papersQuery.error) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas px-6">
        <p className="font-ui text-sm text-destructive text-center">
          Unable to load papers. Ensure backend API is running at
          VITE_API_BASE_URL (default http://localhost:8001).
        </p>
      </div>
    )
  }

  if (papers.length === 0 || showHomeView) {
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

  if (paperBundleQuery.error) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas px-6">
        <p className="font-ui text-sm text-destructive text-center">
          Unable to load paper data. Ensure backend API is running at
          VITE_API_BASE_URL (default http://localhost:8001).
        </p>
      </div>
    )
  }

  if (paperBundleQuery.isLoading && !paper) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas">
        <p className="font-ui text-sm text-text-secondary">
          Loading paper data from backend...
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden relative bg-canvas">
      {guideCollapsed ? (
        <div
          className="flex items-center bg-white border-r border-border/50 cursor-pointer hover:bg-canvas transition-colors"
          style={{ width: '8px' }}
          onClick={() => setGuideCollapsed(false)}
          onMouseEnter={() => setGuideCollapsed(false)}
        >
          <div className="w-full h-8 bg-border/30 rounded-r-sm" />
        </div>
      ) : (
        <>
          <PaperNavigation
            activeSection={activeSection}
            onSectionClick={handleSectionClick}
            sections={navSections}
            papers={papers}
            selectedPaperId={effectivePaperId}
            onPaperSelect={handlePaperSelect}
            onPaperDelete={handlePaperDelete}
            deletingPaperId={
              deletePaperMutation.isPending
                ? (deletePaperMutation.variables ?? null)
                : null
            }
            readingGuide={paperBundleQuery.data?.reading_guide ?? null}
            guideStatus={
              paperBundleQuery.data?.guide_status ??
              (paperBundleQuery.isLoading
                ? { status: 'pending', error: null, updated_at: null }
                : null)
            }
            collapsed={guideCollapsed}
            onToggleCollapse={() => setGuideCollapsed(!guideCollapsed)}
            onHomeClick={handleHomeClick}
            onLogout={handleLogout}
            onUploadPdf={handleFileUploaded}
            isUploadingPdf={uploadPaperMutation.isPending}
            uploadErrorMessage={uploadError}
            style={{ width: `${guideWidth}px` }}
          />

          <div
            className="relative flex items-center justify-center w-2 bg-transparent hover:bg-accent/20 cursor-col-resize transition-all duration-200 group"
            onMouseDown={handleGuideMouseDown}
            title="Drag to resize guide panel"
          >
            <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 w-0.5 bg-border/40 group-hover:bg-accent/60 group-hover:w-1 transition-all duration-200 rounded-full" />
            <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 flex flex-col justify-center space-y-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              <div className="w-3 h-0.5 bg-border/60 rounded-full" />
              <div className="w-3 h-0.5 bg-border/60 rounded-full" />
              <div className="w-3 h-0.5 bg-border/60 rounded-full" />
            </div>
            {isResizing && resizeTarget === 'guide' ? (
              <div className="absolute inset-0 bg-accent/30 border-x border-accent/50" />
            ) : null}
          </div>
        </>
      )}

      <PaperViewer
        ref={viewerRef}
        onVisibleSectionChange={handleVisibleSectionChange}
        focusedSection={focusedSection}
        paper={paper}
        sections={sections}
        isProcessingUpload={uploadTransitioning}
        processingFileName={uploadedFileName}
      />

      <div
        className="relative flex items-center justify-center w-2 bg-transparent hover:bg-accent/20 cursor-col-resize transition-all duration-200 group"
        onMouseDown={handleToolsMouseDown}
        title="Drag to resize AI tools panel"
      >
        <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 w-0.5 bg-border/40 group-hover:bg-accent/60 group-hover:w-1 transition-all duration-200 rounded-full" />
        <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 flex flex-col justify-center space-y-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <div className="w-3 h-0.5 bg-border/60 rounded-full" />
          <div className="w-3 h-0.5 bg-border/60 rounded-full" />
          <div className="w-3 h-0.5 bg-border/60 rounded-full" />
        </div>
        {isResizing && resizeTarget === 'tools' ? (
          <div className="absolute inset-0 bg-accent/30 border-x border-accent/50" />
        ) : null}
      </div>

      <div
        className="h-screen flex flex-col border-l border-border/50 bg-panel/95 shadow-sm"
        style={{ width: `${toolsWidth}px` }}
      >
        <div className="flex-1 min-h-0">
          <AIToolsPanel
            paper={paper}
            sections={sections}
            images={images}
            technicalTerms={technicalTerms}
            tables={tables}
          />
        </div>
        <div className="border-t border-accent/15 bg-gradient-to-b from-panel via-panel to-canvas/40 px-5 pt-4 pb-0">
          <div className="h-[32vh] min-h-[210px] max-h-[320px] flex flex-col">
            <ChatAssistant paperId={effectivePaperId} sections={sections} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default Index