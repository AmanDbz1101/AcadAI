export interface PaperSummary {
  id: number
  paper_name: string
  title?: string | null
  abstract?: string | null
  pdf_url?: string | null
  source_pdf_path?: string | null
  document_uuid?: string | null
  created_at?: string
}

export interface PaperSection {
  id: string
  title: string
  level: number
  page_start: number
  content: string
  stats?: Record<string, unknown>
}

export interface PaperImage {
  id: number
  paper_id: number
  element_id: string
  page_number?: number | null
  image_path?: string | null
  caption?: string | null
}

export interface PaperTable {
  id: number
  paper_id: number
  element_id: string
  page_number?: number | null
  markdown_content?: string | null
  text_content?: string | null
}

export interface PaperBundle {
  paper: PaperSummary
  sections: PaperSection[]
  images: PaperImage[]
  tables: PaperTable[]
  text_blocks: Array<Record<string, unknown>>
}
