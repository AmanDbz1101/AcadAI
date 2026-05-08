import type { GuideStatus, PaperBundle, PaperQuestion, PaperSummary } from '@/types/api'

export interface AuthUser {
  id: number
  email: string
  display_name?: string | null
  created_at?: string
}

export interface AuthResponse {
  token: string
  user: AuthUser
}

export interface RegisterPayload {
  email: string
  password: string
  display_name?: string
}

export interface LoginPayload {
  email: string
  password: string
}

export interface UploadPaperResponse {
  paper: PaperSummary
  database: {
    stored: boolean
    paper_id: number | null
    paper_name?: string | null
    reason?: string | null
  }
  guide_status?: GuideStatus
}

export interface PaperQuestionsResponse {
  paper: PaperSummary
  questions: PaperQuestion[]
}

export interface GenerateQuestionAnswerPayload {
  force_regenerate?: boolean
}

export interface GenerateQuestionAnswerResponse {
  paper: PaperSummary
  question: PaperQuestion
}

export interface GenerateTechnicalTermDefinitionResponse {
  paper: PaperSummary
  technical_term: {
    term: string
    definition?: string | null
    definition_source?: 'dbpedia' | 'dictionary' | 'wikipedia' | 'llm' | null
    definition_status?: 'ready' | 'pending_llm' | null
  }
}

export interface ChatMessagePayload {
  role: 'user' | 'assistant'
  content: string
}

export interface PaperChatPayload {
  messages: ChatMessagePayload[]
  allowed_sections: string[] | null
}

export interface PaperChatResponse {
  paper: PaperSummary
  message: string
  assistant_message?: string
  sources?: Array<{
    section_title: string
    section_id?: string
    page_start?: number
  }>
}

export interface GenerateTechnicalTermDefinitionPayload {
  forceLlm?: boolean
}

export interface CmsDeletePaperResponse {
  paper_id: number
  deleted: boolean
  paper_deleted: boolean
  reason?: string | null
  remaining_links?: number
  qdrant?: {
    deleted?: boolean
    reason?: string
    document_id?: string
    collection?: string
    was_indexed?: boolean
  }
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001'

const API_BASE_CANDIDATES = Array.from(
  new Set([
    API_BASE_URL,
    'http://127.0.0.1:8001',
    'http://localhost:8001',
  ]),
)

const AUTH_TOKEN_KEY = 'researchagent.auth.token'
const AUTH_USER_KEY = 'researchagent.auth.user'

function getAuthHeader(): HeadersInit {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function joinApiUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/$/, '')}${path}`
}

function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError
}

function buildNetworkError(): Error {
  return new Error(
    `Failed to fetch API. Tried: ${API_BASE_CANDIDATES.join(', ')}. Ensure backend is running on port 8001.`,
  )
}

async function fetchWithFallback(
  path: string,
  init: RequestInit,
): Promise<Response> {
  let lastError: unknown = null

  for (const baseUrl of API_BASE_CANDIDATES) {
    try {
      return await fetch(joinApiUrl(baseUrl, path), init)
    } catch (error) {
      lastError = error
      if (!isNetworkError(error)) {
        throw error
      }
    }
  }

  if (isNetworkError(lastError)) {
    throw buildNetworkError()
  }

  throw new Error('Failed to reach API endpoint.')
}

export function setAuthSession(token: string, user: AuthUser): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token)
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user))
}

export function clearAuthSession(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY)
  localStorage.removeItem(AUTH_USER_KEY)
}

export function getCachedAuthUser(): AuthUser | null {
  const raw = localStorage.getItem(AUTH_USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetchWithFallback(path, {
    headers: {
      ...getAuthHeader(),
    },
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`API ${response.status}: ${body || response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetchWithFallback(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(),
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`API ${response.status}: ${text || response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetchWithFallback(path, {
    method: 'DELETE',
    headers: {
      ...getAuthHeader(),
    },
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`API ${response.status}: ${text || response.statusText}`)
  }
  return response.json() as Promise<T>
}

export async function registerUser(
  payload: RegisterPayload,
): Promise<AuthResponse> {
  return postJson<AuthResponse>('/api/auth/register', payload)
}

export async function loginUser(payload: LoginPayload): Promise<AuthResponse> {
  return postJson<AuthResponse>('/api/auth/login', payload)
}

export async function getMe(): Promise<{ user: AuthUser }> {
  return fetchJson<{ user: AuthUser }>('/api/auth/me')
}

export async function getPapers(): Promise<PaperSummary[]> {
  const data = await fetchJson<{ papers: PaperSummary[] }>('/api/papers')
  return data.papers ?? []
}

export async function getPaperBundle(paperId: number): Promise<PaperBundle> {
  return fetchJson<PaperBundle>(`/api/papers/${paperId}/bundle`)
}

export async function uploadPaper(file: File): Promise<UploadPaperResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetchWithFallback('/api/papers/upload', {
    method: 'POST',
    headers: {
      ...getAuthHeader(),
    },
    body: formData,
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(`API ${response.status}: ${body || response.statusText}`)
  }

  return response.json() as Promise<UploadPaperResponse>
}

export async function deleteCmsPaper(
  paperId: number,
): Promise<CmsDeletePaperResponse> {
  return deleteJson<CmsDeletePaperResponse>(`/api/cms/papers/${paperId}`)
}

export async function getPaperQuestions(
  paperId: number,
): Promise<PaperQuestionsResponse> {
  return fetchJson<PaperQuestionsResponse>(`/api/papers/${paperId}/questions`)
}

export async function generateQuestionAnswer(
  paperId: number,
  questionId: number,
  payload: GenerateQuestionAnswerPayload = {},
): Promise<GenerateQuestionAnswerResponse> {
  return postJson<GenerateQuestionAnswerResponse>(
    `/api/papers/${paperId}/questions/${questionId}/generate`,
    {
      force_regenerate: Boolean(payload.force_regenerate),
    },
  )
}

export async function generateTechnicalTermDefinition(
  paperId: number,
  term: string,
  payload: GenerateTechnicalTermDefinitionPayload = {},
): Promise<GenerateTechnicalTermDefinitionResponse> {
  return postJson<GenerateTechnicalTermDefinitionResponse>(
    `/api/papers/${paperId}/technical-terms/generate`,
    {
      term,
      force_llm: Boolean(payload.forceLlm),
    },
  )
}

export async function chatWithPaper(
  paperId: number,
  payload: PaperChatPayload,
): Promise<PaperChatResponse> {
  return postJson<PaperChatResponse>(`/api/papers/${paperId}/chat`, payload)
}
