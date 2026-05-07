"""
Section hierarchy models for research paper structure detection.

Represents the logical structure of research papers, including nested sections,
subsections, and their relationships.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SectionNode(BaseModel):
    """
    Represents a single section or subsection in the document hierarchy.
    
    Each node captures the section's metadata, position in document,
    and its relationship to parent and child sections.
    """
    
    # Identification
    section_id: str = Field(..., description="Unique section identifier")
    title: str = Field(..., description="Section heading text")
    
    # Hierarchy information
    level: int = Field(..., ge=1, le=6, description="Section depth (1=top-level, 6=deepest)")
    numbering: Optional[str] = Field(None, description="Section number (e.g., '1.2.3', 'IV-B')")
    parent_id: Optional[str] = Field(None, description="Parent section ID")
    
    # Position in document
    page_start: int = Field(..., ge=1, description="Starting page number (1-indexed)")
    page_end: Optional[int] = Field(None, ge=1, description="Ending page number (1-indexed)")
    
    # Content metadata
    has_subsections: bool = Field(False, description="Whether this section contains subsections")
    child_section_ids: List[str] = Field(default_factory=list, description="IDs of direct child sections")
    section_type: Optional[str] = Field(None, description="Section type (appendix, references, etc.)")
    
    # Typography hints (optional, for detection confidence)
    font_size: Optional[float] = Field(None, description="Font size in points")
    is_bold: Optional[bool] = Field(None, description="Whether heading is bold")
    
    # Reading order
    reading_order: int = Field(..., ge=0, description="Sequential position in document")
    
    @property
    def full_path(self) -> str:
        """Get hierarchical path representation (e.g., '1.2.3 Methodology')."""
        if self.numbering:
            return f"{self.numbering} {self.title}"
        return self.title
    
    @property
    def depth(self) -> int:
        """Alias for level (depth in hierarchy tree)."""
        return self.level


class SectionHierarchy(BaseModel):
    """
    Complete hierarchical structure of a research paper.
    
    Provides navigation and query capabilities over the section tree,
    enabling section-aware chunking and retrieval.
    """
    
    # Document identification
    document_id: str = Field(..., description="Reference to source document")
    
    # Hierarchy tree
    sections: List[SectionNode] = Field(..., description="All sections in reading order")
    root_sections: List[str] = Field(..., description="Top-level section IDs")
    
    # Statistics
    total_sections: int = Field(0, ge=0, description="Total number of sections")
    max_depth: int = Field(0, ge=0, description="Maximum nesting level (0 if no sections)")
    
    # Detection metadata
    detection_method: str = Field("docling+heuristics", description="Method used for detection")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Detection confidence")
    cross_references: List[Dict[str, Any]] = Field(default_factory=list, description="Cross-reference links")
    
    def get_section(self, section_id: str) -> Optional[SectionNode]:
        """Get section by ID."""
        for section in self.sections:
            if section.section_id == section_id:
                return section
        return None
    
    def get_children(self, section_id: str) -> List[SectionNode]:
        """Get direct children of a section."""
        parent = self.get_section(section_id)
        if not parent:
            return []
        
        return [
            self.get_section(child_id) 
            for child_id in parent.child_section_ids 
            if self.get_section(child_id)
        ]
    
    def get_parent(self, section_id: str) -> Optional[SectionNode]:
        """Get parent of a section."""
        section = self.get_section(section_id)
        if not section or not section.parent_id:
            return None
        return self.get_section(section.parent_id)
    
    def get_ancestors(self, section_id: str) -> List[SectionNode]:
        """Get all ancestors of a section (parent, grandparent, etc.)."""
        ancestors = []
        current = self.get_section(section_id)
        
        while current and current.parent_id:
            parent = self.get_parent(current.section_id)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break
        
        return ancestors
    
    def get_descendants(self, section_id: str) -> List[SectionNode]:
        """Get all descendants of a section (children, grandchildren, etc.)."""
        descendants = []
        queue = self.get_children(section_id)
        
        while queue:
            current = queue.pop(0)
            descendants.append(current)
            queue.extend(self.get_children(current.section_id))
        
        return descendants
    
    def get_section_path(self, section_id: str) -> List[SectionNode]:
        """Get full path from root to section."""
        path = []
        section = self.get_section(section_id)
        
        if not section:
            return path
        
        path.append(section)
        path.extend(reversed(self.get_ancestors(section_id)))
        
        return path
    
    def find_sections_by_title(self, title_pattern: str, case_sensitive: bool = False) -> List[SectionNode]:
        """Find sections matching a title pattern."""
        if not case_sensitive:
            title_pattern = title_pattern.lower()
        
        results = []
        for section in self.sections:
            section_title = section.title if case_sensitive else section.title.lower()
            if title_pattern in section_title:
                results.append(section)
        
        return results
    
    def get_sections_by_level(self, level: int) -> List[SectionNode]:
        """Get all sections at a specific hierarchy level."""
        return [s for s in self.sections if s.level == level]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "document_id": self.document_id,
            "sections": [s.model_dump() for s in self.sections],
            "root_sections": self.root_sections,
            "total_sections": self.total_sections,
            "max_depth": self.max_depth,
            "detection_method": self.detection_method,
            "confidence_score": self.confidence_score,
            "cross_references": self.cross_references,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionHierarchy":
        """Create from dictionary."""
        sections = [SectionNode(**s) for s in data["sections"]]
        return cls(
            document_id=data["document_id"],
            sections=sections,
            root_sections=data["root_sections"],
            total_sections=data["total_sections"],
            max_depth=data["max_depth"],
            detection_method=data["detection_method"],
            confidence_score=data.get("confidence_score"),
            cross_references=data.get("cross_references", []),
        )


class SectionDetectionResult(BaseModel):
    """Result from section hierarchy detection pipeline."""
    
    hierarchy: SectionHierarchy = Field(..., description="Detected section hierarchy")
    processing_time_seconds: float = Field(0, ge=0, description="Detection duration")
    warnings: List[str] = Field(default_factory=list, description="Detection warnings or issues")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            SectionNode: lambda v: v.model_dump(),
            SectionHierarchy: lambda v: v.model_dump()
        }
