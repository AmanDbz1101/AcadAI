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

export interface GuideStatus {
  status: 'pending' | 'ready' | 'failed' | 'missing'
  error?: string | null
  updated_at?: string | null
}

export interface PaperQuestion {
  id: number
  paper_id: number
  question_text: string
  scoped_sections_json: string[]
  retrieval_payload_json: Record<string, unknown>
  status: 'pending' | 'running' | 'completed' | 'failed'
  answer_text?: string | null
  confidence?: string | null
  error_message?: string | null
  created_at?: string
  updated_at?: string
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

export interface TechnicalTerm {
  term: string
  type?: string | null
  score?: number | null
  expansion?: string | null
  source_sections?: string[]
  definition?: string | null
  definition_source?: 'dbpedia' | 'dictionary' | 'wikipedia' | 'llm' | null
  definition_status?: 'ready' | 'pending_llm' | null
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
  technical_terms?: TechnicalTerm[]
  images: PaperImage[]
  tables: PaperTable[]
  text_blocks: Array<Record<string, unknown>>
  reading_guide?: ReadingGuide | null
  guide_status?: GuideStatus | null
}
