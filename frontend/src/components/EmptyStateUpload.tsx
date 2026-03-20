import { useRef, useState } from 'react'
import {
  Upload,
  FileText,
  BookOpenText,
  Sparkles,
  List,
  MessageSquare,
} from 'lucide-react'

interface EmptyStateUploadProps {
  onFileUploaded: (file: File) => void
  isUploading?: boolean
  errorMessage?: string | null
}

const EmptyStateUpload = ({
  onFileUploaded,
  isUploading = false,
  errorMessage = null,
}: EmptyStateUploadProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  const handleFile = (file: File) => {
    if (isUploading) return
    if (
      file.type === 'application/pdf' ||
      file.name.toLowerCase().endsWith('.pdf')
    ) {
      onFileUploaded(file)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  const features = [
    {
      icon: List,
      label: 'Section Navigation',
      desc: 'Jump between paper sections instantly',
    },
    {
      icon: Sparkles,
      label: 'Insight Extraction',
      desc: 'Extract key formulas, figures and charts',
    },
    {
      icon: MessageSquare,
      label: 'AI Chat',
      desc: 'Ask questions about the paper',
    },
  ]

  return (
    <div className="flex-1 h-screen overflow-y-auto bg-canvas flex items-center justify-center">
      <div className="max-w-[520px] w-full px-6 animate-fade-in">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2.5 mb-3">
            <BookOpenText size={28} className="text-text-active" />
            <h1 className="font-ui text-[24px] font-bold text-foreground tracking-tight">
              AcadAI
            </h1>
          </div>
          <p className="font-ui text-[14px] text-text-secondary">
            Upload a research paper to start analyzing
          </p>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault()
            setIsDragging(true)
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => !isUploading && fileInputRef.current?.click()}
          className={`
            relative flex flex-col items-center gap-4 py-16 px-8 rounded-xl border-2 border-dashed transition-all duration-300
            ${isUploading ? 'cursor-wait opacity-85' : 'cursor-pointer'}
            ${
              isDragging && !isUploading
                ? 'border-text-active bg-accent/10 scale-[1.01]'
                : 'border-border hover:border-text-active/50 hover:bg-card/50'
            }
          `}
        >
          <div
            className={`
            w-16 h-16 rounded-2xl flex items-center justify-center transition-colors duration-300
            ${isDragging && !isUploading ? 'bg-accent/20' : 'bg-card'}
          `}
          >
            {isDragging && !isUploading ? (
              <FileText size={28} className="text-text-active" />
            ) : (
              <Upload size={28} className="text-text-secondary" />
            )}
          </div>
          <div className="text-center">
            <p className="font-ui text-[15px] font-medium text-foreground mb-1">
              {isUploading
                ? 'Processing and storing your paper...'
                : isDragging
                  ? 'Drop your paper here'
                  : 'Drop a research paper PDF'}
            </p>
            <p className="font-ui text-[12px] text-text-secondary">
              {isUploading
                ? 'This can take a minute for large files'
                : 'or click to browse your files'}
            </p>
          </div>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          className="hidden"
          disabled={isUploading}
        />

        {errorMessage ? (
          <p className="mt-4 text-center font-ui text-[12px] text-destructive">
            {errorMessage}
          </p>
        ) : null}

        <div className="mt-10 grid grid-cols-3 gap-4">
          {features.map((f) => (
            <div key={f.label} className="text-center px-2">
              <div className="w-9 h-9 rounded-lg bg-card flex items-center justify-center mx-auto mb-2">
                <f.icon size={16} className="text-text-active" />
              </div>
              <p className="font-ui text-[11px] font-semibold text-foreground mb-0.5">
                {f.label}
              </p>
              <p className="font-ui text-[10px] text-text-secondary leading-snug">
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default EmptyStateUpload
