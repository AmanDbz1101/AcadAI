import type { PaperBundle, PaperSummary } from '@/types/api'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`API ${response.status}: ${body || response.statusText}`)
  }
  return response.json() as Promise<T>
}

export async function getPapers(): Promise<PaperSummary[]> {
  const data = await fetchJson<{ papers: PaperSummary[] }>('/api/papers')
  return data.papers ?? []
}

export async function getPaperBundle(paperId: number): Promise<PaperBundle> {
  return fetchJson<PaperBundle>(`/api/papers/${paperId}/bundle`)
}
