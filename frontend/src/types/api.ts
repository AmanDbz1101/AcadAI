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

export interface ReadingStep {
  step_number: number
  section_to_read: string[]
  needs_figures?: boolean
  needs_tables?: boolean
  objective: string
  questions_to_answer: string[]
  expected_output: string
}

export interface ReadingPass {
  goal: string
  estimated_time: string
  steps: ReadingStep[]
}

export interface ReadingStrategy {
  method: string
  paper_type: string
  estimated_total_time: string
}

export interface FinalTask {
  summary_task: string
  reflection_questions: string[]
}

export interface ReadingGuide {
  paper_title: string
  reading_strategy: ReadingStrategy
  pass1_quick_scan?: ReadingPass
  pass1_field_overview?: ReadingPass
  pass2_method_understanding?: ReadingPass
  pass2_proof_strategy?: ReadingPass
  pass2_taxonomy_understanding?: ReadingPass
  pass3_deep_analysis?: ReadingPass
  pass3_deep_mathematical_analysis?: ReadingPass
  pass3_research_landscape_analysis?: ReadingPass
  final_user_task?: FinalTask
  [key: string]: any // Allow for category-specific fields
}

export interface PaperBundle {
  paper: PaperSummary
  sections: PaperSection[]
  images: PaperImage[]
  tables: PaperTable[]
  text_blocks: Array<Record<string, unknown>>
  reading_guide?: ReadingGuide | null
}
