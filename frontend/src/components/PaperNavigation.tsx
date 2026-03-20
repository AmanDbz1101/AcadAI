import { BookOpenText, FileText, X, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import type { PaperSummary } from '@/types/api'

interface Section {
  id: string
  title: string
  label: string
}

interface PaperNavigationProps {
  activeSection: string
  onSectionClick: (sectionId: string) => void
  sections: Section[]
  papers: PaperSummary[]
  selectedPaperId: number | null
  onPaperSelect: (paperId: number) => void
  uploadedFileName?: string | null
  onFileChange?: (fileName: string | null) => void
  onFileUpload?: (file: File) => void
  isUploading?: boolean
  uploadError?: string | null
}

const PaperNavigation = ({
  activeSection,
  onSectionClick,
  sections,
  papers,
  selectedPaperId,
  onPaperSelect,
  uploadedFileName,
  onFileChange,
  onFileUpload,
  isUploading,
  uploadError,
}: PaperNavigationProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragActive, setDragActive] = useState(false)
  return (
    <aside className="w-[260px] min-w-[260px] bg-panel h-screen sticky top-0 flex flex-col border-r border-border/40">
      <div className="px-6 pt-8 pb-6">
        <div className="flex items-center gap-2">
          <BookOpenText size={18} className="text-text-active" />
          <h1 className="font-ui text-[16px] font-bold text-foreground tracking-tight">
            AcadAI
          </h1>
        </div>
        <p className="font-ui text-[11px] text-text-secondary pl-[26px]">
          Research Paper Assistant
        </p>
      </div>

      {uploadedFileName ? (
        <div className="px-4 mb-4">
          <div className="flex items-center gap-2 px-3 py-2.5 bg-accent/10 rounded-lg">
            <FileText size={14} className="text-text-active flex-shrink-0" />
            <span className="font-ui text-[12px] text-foreground truncate flex-1">
              {uploadedFileName}
            </span>
            <button
              onClick={() => onFileChange?.(null)}
              className="text-text-secondary hover:text-foreground transition-colors"
            >
              <X size={12} />
            </button>
          </div>
        </div>
      ) : null}

      <div className="px-6 mb-3">
        <label className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary block mb-2">
          Paper
        </label>
        <select
          value={selectedPaperId ?? ''}
          onChange={(e) => onPaperSelect(Number(e.target.value))}
          className="w-full font-ui text-[12px] bg-canvas border border-border/60 rounded-md px-2 py-1.5 text-foreground"
        >
          {papers.map((paper) => (
            <option key={paper.id} value={paper.id}>
              {paper.paper_name}
            </option>
          ))}
        </select>
      </div>

      <div className="px-6 mb-3">
        <h2 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary">
          Paper Structure
        </h2>
      </div>

      <nav className="flex-1 px-4 py-1 overflow-y-auto">
        <ul className="space-y-0.5">
          {sections.map((section) => {
            const isActive = activeSection === section.id
            return (
              <li key={section.id}>
                <button
                  onClick={() => onSectionClick(section.id)}
                  className={`
                    w-full text-left py-2.5 px-3 font-ui text-[13px] rounded-md transition-all duration-200 flex items-center gap-3
                    ${
                      isActive
                        ? 'text-text-active bg-accent/10 font-semibold'
                        : 'text-text-secondary hover:text-foreground hover:bg-canvas font-normal'
                    }
                  `}
                >
                  <span
                    className={`text-[10px] font-mono ${isActive ? 'text-text-active' : 'text-text-secondary/50'}`}
                  >
                    {section.label}
                  </span>
                  {section.title}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="border-t border-border/40 px-4 py-4">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) {
              onFileUpload?.(file)
              e.target.value = ''
            }
          }}
          className="hidden"
        />
        <div
          onDragEnter={() => setDragActive(true)}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(e) => {
            e.preventDefault()
            setDragActive(true)
          }}
          onDrop={(e) => {
            e.preventDefault()
            setDragActive(false)
            const file = e.dataTransfer.files?.[0]
            if (file && file.type === 'application/pdf') {
              onFileUpload?.(file)
            }
          }}
          onClick={() => fileInputRef.current?.click()}
          className={`
            relative p-3 rounded-lg border-2 border-dashed transition-all cursor-pointer
            ${
              dragActive
                ? 'border-accent/60 bg-accent/10'
                : uploadError
                  ? 'border-destructive/40 bg-destructive/5 hover:bg-destructive/10'
                  : 'border-border/40 bg-canvas hover:border-border/60 hover:bg-canvas/80'
            }
          `}
        >
          <div className="flex flex-col items-center gap-1.5">
            <Upload
              size={16}
              className={
                uploadError
                  ? 'text-destructive/60'
                  : dragActive
                    ? 'text-accent'
                    : 'text-text-secondary'
              }
            />
            <p className="font-ui text-[11px] text-text-secondary text-center">
              {isUploading ? 'Uploading...' : 'Drop PDF or click'}
            </p>
          </div>
        </div>
        {uploadError ? (
          <p className="mt-1.5 font-ui text-[10px] text-destructive text-center">
            {uploadError}
          </p>
        ) : null}
      </div>

      <div className="px-6 pb-6 pt-4 border-t border-border/40">
        <p className="font-ui text-[10px] text-text-secondary/50 tracking-wide">
          Powered by AcadAI
        </p>
      </div>
    </aside>
  )
}

export default PaperNavigation
