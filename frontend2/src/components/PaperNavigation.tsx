import { BookOpenText, FileText, X } from "lucide-react";

interface Section {
  id: string;
  title: string;
  label: string;
}

const sections: Section[] = [
  { id: "abstract", title: "Abstract", label: "01" },
  { id: "introduction", title: "Introduction", label: "02" },
  { id: "methodology", title: "Methodology", label: "03" },
  { id: "main-concepts", title: "Main Concepts", label: "04" },
  { id: "results", title: "Results", label: "05" },
  { id: "discussion", title: "Discussion", label: "06" },
  { id: "conclusion", title: "Conclusion", label: "07" },
];

interface PaperNavigationProps {
  activeSection: string;
  onSectionClick: (sectionId: string) => void;
  uploadedFileName?: string | null;
  onFileChange?: (fileName: string | null) => void;
}

const PaperNavigation = ({ activeSection, onSectionClick, uploadedFileName, onFileChange }: PaperNavigationProps) => {
  return (
    <aside className="w-[260px] min-w-[260px] bg-panel h-screen sticky top-0 flex flex-col border-r border-border/40">
      <div className="px-6 pt-8 pb-6">
        <div className="flex items-center gap-2">
          <BookOpenText size={18} className="text-text-active" />
          <h1 className="font-ui text-[16px] font-bold text-foreground tracking-tight">AcadAI</h1>
        </div>
        <p className="font-ui text-[11px] text-text-secondary pl-[26px]">Research Paper Assistant</p>
      </div>

      {/* Current file */}
      {uploadedFileName && (
        <div className="px-4 mb-4">
          <div className="flex items-center gap-2 px-3 py-2.5 bg-accent/10 rounded-lg">
            <FileText size={14} className="text-text-active flex-shrink-0" />
            <span className="font-ui text-[12px] text-foreground truncate flex-1">{uploadedFileName}</span>
            <button
              onClick={() => onFileChange?.(null)}
              className="text-text-secondary hover:text-foreground transition-colors"
            >
              <X size={12} />
            </button>
          </div>
        </div>
      )}

      <div className="px-6 mb-3">
        <h2 className="font-ui text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary">
          Paper Structure
        </h2>
      </div>

      <nav className="flex-1 px-4 py-1">
        <ul className="space-y-0.5">
          {sections.map((section) => {
            const isActive = activeSection === section.id;
            return (
              <li key={section.id}>
                <button
                  onClick={() => onSectionClick(section.id)}
                  className={`
                    w-full text-left py-2.5 px-3 font-ui text-[13px] rounded-md transition-all duration-200 flex items-center gap-3
                    ${isActive
                      ? "text-text-active bg-accent/10 font-semibold"
                      : "text-text-secondary hover:text-foreground hover:bg-canvas font-normal"
                    }
                  `}
                >
                  <span className={`text-[10px] font-mono ${isActive ? "text-text-active" : "text-text-secondary/50"}`}>
                    {section.label}
                  </span>
                  {section.title}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="px-6 pb-6">
        <div className="border-t border-border/40 pt-4">
          <p className="font-ui text-[10px] text-text-secondary/50 tracking-wide">
            Powered by AcadAI
          </p>
        </div>
      </div>
    </aside>
  );
};

export default PaperNavigation;
