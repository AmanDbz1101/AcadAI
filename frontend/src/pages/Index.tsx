import { useState, useRef, useCallback, useEffect, type FormEvent } from 'react'
import PaperNavigation from '@/components/PaperNavigation'
import PaperViewer, { PaperViewerHandle } from '@/components/PaperViewer'
import AIToolsPanel from '@/components/AIToolsPanel'
import ChatAssistant from '@/components/ChatAssistant'
import EmptyStateUpload from '@/components/EmptyStateUpload'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  type AuthUser,
  clearAuthSession,
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

// Wrap entire component to catch errors
const IndexContent = () => {
  console.log("IndexContent rendering");
  const queryClient = useQueryClient()
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
  const [guideCollapsed, setGuideCollapsed] = useState(false)
  const [guideWidth, setGuideWidth] = useState(320) // Default width in pixels
  const [toolsWidth, setToolsWidth] = useState(300) // Default width for AI tools panel
  const [isResizing, setIsResizing] = useState(false)
  const [resizeTarget, setResizeTarget] = useState<'guide' | 'tools' | null>(
    null,
  )
  const [showHomeView, setShowHomeView] = useState(false)
  const [uploadTransitioning, setUploadTransitioning] = useState(false)
  const [uploadedFileName, setUploadedFileName] = useState<string>('')
  const [selectedPdfTerms, setSelectedPdfTerms] = useState<string[]>([])
  const viewerRef = useRef<PaperViewerHandle>(null)

  // Resize functionality
  const handleGuideMouseDown = useCallback((e: React.MouseEvent) => {
    setIsResizing(true)
    setResizeTarget('guide')
    e.preventDefault()
  }, [])

  const handleToolsMouseDown = useCallback((e: React.MouseEvent) => {
    setIsResizing(true)
    setResizeTarget('tools')
    e.preventDefault()
  }, [])

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isResizing || !resizeTarget) return

      if (resizeTarget === 'guide') {
        // Constrain the guide width between 250px and 50% of viewport width
        const minWidth = 250
        const maxWidth = Math.min(600, window.innerWidth * 0.4)
        const newWidth = Math.max(minWidth, Math.min(maxWidth, e.clientX))
        setGuideWidth(newWidth)
      } else if (resizeTarget === 'tools') {
        // Calculate tools width from the right side
        const viewportWidth = window.innerWidth
        const toolsMinWidth = 250
        const toolsMaxWidth = Math.min(500, viewportWidth * 0.4)
        const newToolsWidth = Math.max(
          toolsMinWidth,
          Math.min(toolsMaxWidth, viewportWidth - e.clientX),
        )
        setToolsWidth(newToolsWidth)
      }
    },
    [isResizing, resizeTarget],
  )

  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
    setResizeTarget(null)
  }, [])

  useEffect(() => {
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      // Prevent text selection during resize
      document.body.style.WebkitUserSelect = 'none'
      document.body.style.MozUserSelect = 'none'
      document.body.style.msUserSelect = 'none'
    } else {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.body.style.WebkitUserSelect = ''
      document.body.style.MozUserSelect = ''
      document.body.style.msUserSelect = ''
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.body.style.WebkitUserSelect = ''
      document.body.style.MozUserSelect = ''
      document.body.style.msUserSelect = ''
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

  // Auto-select first paper when papers load and no paper is selected
  // OR restore paperLoaded flag if we have a selectedPaperId from localStorage
  // Skip if showHomeView is true (user clicked logo to go to upload page)
  useEffect(() => {
    if (!authUser || papersQuery.isLoading || showHomeView) return

    if (papers.length > 0) {
      if (!selectedPaperId) {
        // No paper selected, auto-select first one
        setSelectedPaperId(papers[0].id)
        setPaperLoaded(true)
      } else if (!paperLoaded) {
        // Paper was selected (from localStorage) but paperLoaded flag was lost on reload
        setPaperLoaded(true)
      }
    }
  }, [
    papers,
    selectedPaperId,
    authUser,
    papersQuery.isLoading,
    paperLoaded,
    showHomeView,
  ])

  const effectivePaperId = selectedPaperId ?? papers[0]?.id ?? null

  const uploadPaperMutation = useMutation({
    mutationFn: uploadPaper,
    onMutate: (file: File) => {
      setUploadError(null)
      setUploadTransitioning(true)
      setUploadedFileName(file.name)
    },
    onSuccess: async (data) => {
      const newPaperId = data.paper.id
      setSelectedPaperId(newPaperId)
      setActiveSection('')
      setFocusedSection(null)
      setPaperLoaded(true)
      setShowHomeView(false) // Exit home view after successful upload
      setUploadTransitioning(false)
      setUploadedFileName('')

      await queryClient.invalidateQueries({ queryKey: ['papers'] })
      await queryClient.invalidateQueries({
        queryKey: ['paper-bundle', newPaperId],
      })
    },
    onError: (error: Error) => {
      setUploadError(error.message || 'Upload failed')
      setUploadTransitioning(false)
      setUploadedFileName('')
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
  const tables = paperBundleQuery.data?.tables ?? []
  const technicalTerms = paperBundleQuery.data?.technical_terms ?? []

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

  const handleChatSourceClick = useCallback(
    (source: { section_title: string; section_id?: string; page_start?: number }) => {
      if (source.section_id && viewerRef.current?.scrollToSection) {
        setActiveSection(source.section_id)
        setFocusedSection(source.section_id)
        viewerRef.current.scrollToSection(source.section_id)
        console.log(`Chat source click: scrolling to section ${source.section_id}`)
        return
      }

      if (source.section_title && sections.length > 0) {
        const matchedSection = sections.find(
          (section) =>
            (section.title || '').trim().toLowerCase() ===
            source.section_title.trim().toLowerCase(),
        )
        if (matchedSection && viewerRef.current?.scrollToSection) {
          setActiveSection(matchedSection.id)
          setFocusedSection(matchedSection.id)
          viewerRef.current.scrollToSection(matchedSection.id)
          console.log(`Chat source click: matched section title ${matchedSection.title}`)
          return
        }
      }

      if (source.page_start && viewerRef.current?.jumpToPage) {
        viewerRef.current.jumpToPage(source.page_start)
        console.log(`Chat source click: jumping to page ${source.page_start}`)
        return
      }

      console.warn('Chat source click: no navigation target found for', source)
    },
    [sections],
  )

  const handleVisibleSectionChange = useCallback((sectionId: string) => {
    setActiveSection(sectionId)
  }, [])

  const handlePdfTermSelect = useCallback((term: string) => {
    const normalized = term.trim()
    if (!normalized) return

    setSelectedPdfTerms((prev) => {
      const withoutExisting = prev.filter(
        (item) => item.toLowerCase() !== normalized.toLowerCase(),
      )
      return [normalized, ...withoutExisting].slice(0, 30)
    })
  }, [])

  useEffect(() => {
    setSelectedPdfTerms([])
  }, [effectivePaperId])

  const handlePaperSelect = useCallback((paperId: number) => {
    setShowHomeView(false)
    setSelectedPaperId(paperId)
    setActiveSection('')
    setFocusedSection(null)
    setShowHomeView(false) // Exit home view when selecting a paper
  }, [])

  const handleHomeClick = useCallback(() => {
    setSelectedPaperId(null)
    setActiveSection('')
    setFocusedSection(null)
    setShowHomeView(true)
  }, [])

  const handleFileUploaded = useCallback(
    (file: File) => {
      setShowHomeView(false)
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
    [authMode, authEmail, authPassword, authDisplayName, queryClient],
  )

  const handleLogout = useCallback(() => {
    clearAuthSession()
    setAuthUser(null)
    setPaperLoaded(false)
    setSelectedPaperId(null)
    setUploadError(null)
    queryClient.clear()
  }, [queryClient])

  if (!authUser) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', padding: '24px', backgroundColor: '#f5f5f0' }}>
        <div style={{ width: '100%', maxWidth: '400px', border: '1px solid #d1ccc0', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          {/* Header */}
          <div style={{ padding: '24px', borderBottom: '1px solid #e8e4db', background: 'linear-gradient(to right, rgba(116,105,87,0.1), rgba(116,105,87,0.05), transparent)' }}>
            <h1 style={{ fontSize: '22px', fontWeight: 'bold', color: '#1a1411', marginBottom: '8px' }}>
              AcadAI
            </h1>
            <p style={{ fontSize: '13px', color: '#7a7573' }}>
              {authMode === 'register' ? 'Create your account' : 'Sign in to continue'}
            </p>
          </div>

          {/* Form */}
          <div style={{ padding: '24px', backgroundColor: '#fafaf8' }}>
            <form style={{ display: 'flex', flexDirection: 'column', gap: '12px' }} onSubmit={handleAuthSubmit}>
              {authMode === 'register' ? (
                <input
                  type="text"
                  value={authDisplayName}
                  onChange={(e) => setAuthDisplayName(e.target.value)}
                  placeholder="Display name"
                  style={{ width: '100%', borderRadius: '6px', backgroundColor: '#fafaf8', border: '1px solid #d1ccc0', padding: '8px 12px', fontSize: '14px', color: '#1a1411' }}
                />
              ) : null}
              <input
                type="email"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                placeholder="Email"
                required
                style={{ width: '100%', borderRadius: '6px', backgroundColor: '#fafaf8', border: '1px solid #d1ccc0', padding: '8px 12px', fontSize: '14px', color: '#1a1411' }}
              />
              <input
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                placeholder="Password"
                required
                style={{ width: '100%', borderRadius: '6px', backgroundColor: '#fafaf8', border: '1px solid #d1ccc0', padding: '8px 12px', fontSize: '14px', color: '#1a1411' }}
              />
              <button
                type="submit"
                disabled={authSubmitting}
                style={{ width: '100%', borderRadius: '6px', backgroundColor: 'rgba(116,105,87,0.2)', color: '#1a1411', padding: '8px 12px', fontSize: '14px', fontWeight: '600', border: 'none', cursor: 'pointer', opacity: authSubmitting ? 0.6 : 1, transition: 'background-color 0.2s' }}
                onMouseEnter={(e) => !authSubmitting && (e.currentTarget.style.backgroundColor = 'rgba(116,105,87,0.3)')}
                onMouseLeave={(e) => !authSubmitting && (e.currentTarget.style.backgroundColor = 'rgba(116,105,87,0.2)')}
              >
                {authSubmitting
                  ? 'Please wait...'
                  : authMode === 'register'
                    ? 'Create account'
                    : 'Sign in'}
              </button>
            </form>
            {authError ? (
              <p style={{ marginTop: '12px', fontSize: '12px', color: '#dc2626' }}>
                {authError}
              </p>
            ) : null}
            <button
              onClick={() => setAuthMode(authMode === 'register' ? 'login' : 'register')}
              style={{ marginTop: '16px', fontSize: '12px', color: '#7a7573', backgroundColor: 'transparent', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = '#1a1411')}
              onMouseLeave={(e) => (e.currentTarget.style.color = '#7a7573')}
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

  // Show loading while papers query is fetching
  if (papersQuery.isLoading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas">
        <p className="font-ui text-sm text-text-secondary">Loading papers...</p>
      </div>
    )
  }

  // Show error if papers query failed
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

  // Show upload page if no papers exist OR if user clicked home to upload new PDF
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

  // Show loading while bundle is fetching
  if (paperBundleQuery.isLoading && effectivePaperId === null && !uploadTransitioning) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas">
        <p className="font-ui text-sm text-text-secondary">
          Loading paper data from backend...
        </p>
      </div>
    )
  }

  // Show error if bundle query failed
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

  return (
    <div className="flex h-screen overflow-hidden relative bg-canvas">
      {/* Collapsed Guide Panel */}
      {guideCollapsed ? (
        <div
          className="flex items-center bg-white border-r border-border/50 cursor-pointer hover:bg-canvas transition-colors"
          style={{ width: '8px' }}
          onClick={() => setGuideCollapsed(false)}
          onMouseEnter={() => setGuideCollapsed(false)}
        >
          <div className="w-full h-8 bg-border/30 rounded-r-sm"></div>
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
            readingGuide={paperBundleQuery.data?.reading_guide ?? null}
            collapsed={guideCollapsed}
            onToggleCollapse={() => setGuideCollapsed(!guideCollapsed)}
            onHomeClick={handleHomeClick}
            onLogout={handleLogout}
            onUploadPdf={handleFileUploaded}
            isUploadingPdf={uploadPaperMutation.isPending}
            uploadErrorMessage={uploadError}
            onPaperDeleted={() => {
              queryClient.invalidateQueries({ queryKey: ['papers'] })
              setSelectedPaperId(null)
            }}
            style={{ width: `${guideWidth}px` }}
          />

          {/* Resizer */}
          <div
            className="relative flex items-center justify-center w-2 bg-transparent hover:bg-accent/20 cursor-col-resize transition-all duration-200 group"
            onMouseDown={handleGuideMouseDown}
            title="Drag to resize guide panel"
          >
            {/* Resizer Handle */}
            <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 w-0.5 bg-border/40 group-hover:bg-accent/60 group-hover:w-1 transition-all duration-200 rounded-full" />
            {/* Grip Lines */}
            <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 flex flex-col justify-center space-y-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              <div className="w-3 h-0.5 bg-border/60 rounded-full" />
              <div className="w-3 h-0.5 bg-border/60 rounded-full" />
              <div className="w-3 h-0.5 bg-border/60 rounded-full" />
            </div>
            {/* Active resize indicator */}
            {isResizing && resizeTarget === 'guide' && (
              <div className="absolute inset-0 bg-accent/30 border-x border-accent/50" />
            )}
          </div>
        </>
      )}

      <PaperViewer
        ref={viewerRef}
        onVisibleSectionChange={handleVisibleSectionChange}
        onPdfTermSelect={handlePdfTermSelect}
        focusedSection={focusedSection}
        paper={paper}
        sections={sections}
        isProcessingUpload={papers.length === 0 && uploadTransitioning}
        processingFileName={uploadedFileName}
      />

      {/* Right Resizer */}
      <div
        className="relative flex items-center justify-center w-2 bg-transparent hover:bg-accent/20 cursor-col-resize transition-all duration-200 group"
        onMouseDown={handleToolsMouseDown}
        title="Drag to resize AI tools panel"
      >
        {/* Resizer Handle */}
        <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 w-0.5 bg-border/40 group-hover:bg-accent/60 group-hover:w-1 transition-all duration-200 rounded-full" />
        {/* Grip Lines */}
        <div className="absolute inset-y-0 left-1/2 transform -translate-x-1/2 flex flex-col justify-center space-y-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <div className="w-3 h-0.5 bg-border/60 rounded-full" />
          <div className="w-3 h-0.5 bg-border/60 rounded-full" />
          <div className="w-3 h-0.5 bg-border/60 rounded-full" />
        </div>
        {/* Active resize indicator */}
        {isResizing && resizeTarget === 'tools' && (
          <div className="absolute inset-0 bg-accent/30 border-x border-accent/50" />
        )}
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
            selectedPdfTerms={selectedPdfTerms}
            tables={tables}
          />
        </div>
        <div className="border-t border-accent/15 bg-gradient-to-b from-panel via-panel to-canvas/40 px-5 pt-4 pb-0">
          <div className="h-[32vh] min-h-[210px] max-h-[320px] flex flex-col">
            <ChatAssistant
              paperId={effectivePaperId}
              sections={sections}
              onSourceClick={handleChatSourceClick}
              activeSection={activeSection}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

const Index = () => {
  try {
    return <IndexContent />
  } catch (error) {
    console.error("Page error:", error);
    return (
      <div className="h-screen w-full flex items-center justify-center bg-canvas">
        <div className="text-center max-w-md">
          <h2 className="text-2xl font-bold text-foreground mb-4">Page Error</h2>
          <p className="text-text-secondary mb-4">{error instanceof Error ? error.message : "An unknown error occurred"}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:opacity-90 transition"
          >
            Reload page
          </button>
        </div>
      </div>
    );
  }
}

export default Index
