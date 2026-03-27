import { useState, useRef, useCallback, useEffect, type FormEvent } from 'react'
import PaperNavigation from '@/components/PaperNavigation'
import PaperViewer, { PaperViewerHandle } from '@/components/PaperViewer'
import AIToolsPanel from '@/components/AIToolsPanel'
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

const Index = () => {
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
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadTransitioning, setUploadTransitioning] = useState(false)
  const [showUploadHome, setShowUploadHome] = useState(false)
  const viewerRef = useRef<PaperViewerHandle>(null)

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
  useEffect(() => {
    if (!authUser || papersQuery.isLoading) return

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
  }, [papers, selectedPaperId, authUser, papersQuery.isLoading, paperLoaded])

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
      setUploadTransitioning(false)

      await queryClient.invalidateQueries({ queryKey: ['papers'] })
      await queryClient.invalidateQueries({
        queryKey: ['paper-bundle', newPaperId],
      })
    },
    onError: (error: Error) => {
      setUploadTransitioning(false)
      setUploadedFileName(null)
      setUploadError(error.message || 'Upload failed')
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
    setShowUploadHome(false)
    setSelectedPaperId(paperId)
    setActiveSection('')
    setFocusedSection(null)
  }, [])

  const handleFileUploaded = useCallback(
    (file: File) => {
      setShowUploadHome(false)
      uploadPaperMutation.mutate(file)
    },
    [uploadPaperMutation],
  )

  const handleGoHome = useCallback(() => {
    setShowUploadHome(true)
    setUploadError(null)
    setUploadedFileName(null)
  }, [])

  const handleFileBadgeClear = useCallback((fileName: string | null) => {
    setUploadedFileName(fileName)
  }, [])

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
    setUploadedFileName(null)
    setUploadError(null)
    queryClient.clear()
  }, [queryClient])

  if (!authUser) {
    return (
      <div className="h-screen w-full bg-canvas flex items-center justify-center px-6">
        <div className="w-full max-w-md bg-panel border border-border/50 rounded-xl p-6">
          <h1 className="font-ui text-[22px] font-bold text-foreground mb-1">
            AcadAI
          </h1>
          <p className="font-ui text-[13px] text-text-secondary mb-5">
            {authMode === 'register'
              ? 'Create your account'
              : 'Sign in to continue'}
          </p>
          <form className="space-y-3" onSubmit={handleAuthSubmit}>
            {authMode === 'register' ? (
              <input
                type="text"
                value={authDisplayName}
                onChange={(e) => setAuthDisplayName(e.target.value)}
                placeholder="Display name"
                className="w-full rounded-md bg-canvas border border-border/60 px-3 py-2 text-sm text-foreground"
              />
            ) : null}
            <input
              type="email"
              value={authEmail}
              onChange={(e) => setAuthEmail(e.target.value)}
              placeholder="Email"
              required
              className="w-full rounded-md bg-canvas border border-border/60 px-3 py-2 text-sm text-foreground"
            />
            <input
              type="password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
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

  // Show upload page if no papers exist
  if (papers.length === 0 && !uploadTransitioning) {
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

  if (showUploadHome && !uploadTransitioning) {
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
    <div className="flex h-screen overflow-hidden relative">
      <button
        onClick={handleLogout}
        className="absolute top-3 right-4 z-50 bg-panel border border-border/50 rounded-md px-3 py-1.5 text-[12px] text-text-secondary hover:text-foreground"
      >
        Logout
      </button>
      <PaperNavigation
        activeSection={activeSection}
        onSectionClick={handleSectionClick}
        sections={navSections}
        papers={papers}
        selectedPaperId={effectivePaperId}
        onPaperSelect={handlePaperSelect}
        uploadedFileName={uploadedFileName}
        onFileChange={handleFileBadgeClear}
        onFileUpload={handleFileUploaded}
        isUploading={uploadPaperMutation.isPending}
        uploadError={uploadError}
        readingGuide={paperBundleQuery.data?.reading_guide ?? null}
        guideStatus={
          paperBundleQuery.data?.guide_status ??
          ((paperBundleQuery.isLoading || (papers.length === 0 && uploadTransitioning))
            ? { status: 'pending', error: null, updated_at: null }
            : null)
        }
        onGoHome={handleGoHome}
      />
      <PaperViewer
        ref={viewerRef}
        onVisibleSectionChange={handleVisibleSectionChange}
        focusedSection={focusedSection}
        paper={paper}
        sections={sections}
        isProcessingUpload={papers.length === 0 && uploadTransitioning}
        processingFileName={uploadedFileName}
      />
      <AIToolsPanel
        paper={paper}
        sections={sections}
        images={images}
        technicalTerms={technicalTerms}
      />
    </div>
  )
}

export default Index
