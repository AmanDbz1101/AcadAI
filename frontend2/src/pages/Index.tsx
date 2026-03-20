import { useState, useRef, useCallback } from "react";
import PaperNavigation from "@/components/PaperNavigation";
import PaperViewer, { PaperViewerHandle } from "@/components/PaperViewer";
import AIToolsPanel from "@/components/AIToolsPanel";
import EmptyStateUpload from "@/components/EmptyStateUpload";

const Index = () => {
  const [paperLoaded, setPaperLoaded] = useState(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState("abstract");
  const [focusedSection, setFocusedSection] = useState<string | null>(null);
  const viewerRef = useRef<PaperViewerHandle>(null);

  const handleSectionClick = useCallback((sectionId: string) => {
    setActiveSection(sectionId);
    setFocusedSection(sectionId);
    viewerRef.current?.scrollToSection(sectionId);
    setTimeout(() => setFocusedSection(null), 1500);
  }, []);

  const handleVisibleSectionChange = useCallback((sectionId: string) => {
    setActiveSection(sectionId);
  }, []);

  const handleFileUploaded = useCallback((fileName: string) => {
    setUploadedFileName(fileName);
    setPaperLoaded(true);
  }, []);

  if (!paperLoaded) {
    return (
      <div className="flex h-screen overflow-hidden">
        <EmptyStateUpload onFileUploaded={handleFileUploaded} />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <PaperNavigation
        activeSection={activeSection}
        onSectionClick={handleSectionClick}
        uploadedFileName={uploadedFileName}
        onFileChange={setUploadedFileName}
      />
      <PaperViewer
        ref={viewerRef}
        onVisibleSectionChange={handleVisibleSectionChange}
        focusedSection={focusedSection}
      />
      <AIToolsPanel />
    </div>
  );
};

export default Index;
