"""
Section hierarchy detector.

Detects and builds hierarchical section structure from research papers
using typography cues, numbering patterns, and keyword matching.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from uuid import uuid4

from backend.models.document import ValidatedDocument, PageContent
from backend.models.metadata import ProcessedDocument, SectionInfo
from backend.models.section_hierarchy import SectionNode, SectionHierarchy


logger = logging.getLogger(__name__)


class SectionDetector:
    """
    Detects section hierarchy from document structure.
    
    Uses multiple signals to identify section headers:
    1. Typography (font size, boldness)
    2. Numbering patterns (1., 2.3, IV-B, etc.)
    3. Keyword patterns (Introduction, Methodology, etc.)
    """
    
    # Common section keywords that indicate headers
    SECTION_KEYWORDS = [
        "introduction", "abstract", "background", "related work", "related works",
        "literature review", "methodology", "methods", "approach", "method",
        "implementation", "design", "architecture", "system", "model",
        "experiments", "experimental", "evaluation", "results", "analysis",
        "discussion", "findings", "case study", "case studies",
        "conclusion", "conclusions", "future work", "summary",
        "preliminaries", "problem", "formulation", "notation",
        "contributions", "overview", "motivation"
    ]
    
    # Numbering patterns (ordered by specificity)
    NUMBERING_PATTERNS = [
        # Roman numerals with optional dash/dot (e.g., "IV-B", "II.3", "I.")
        r'^([IVX]+)[\.\-]([A-Z]|\d+)?\s*',
        # Decimal numbering (e.g., "1.2.3", "2.1")
        r'^(\d+(?:\.\d+)*)\s+',
        # Letter-based (e.g., "A.", "B.1")
        r'^([A-Z])[\.\)](\d+)?\s*',
        # Simple number with dot/paren (e.g., "1.", "2)")
        r'^(\d+)[\.)\]]\s+',
    ]
    
    def __init__(
        self,
        min_heading_font_size: float = 10.0,
        use_docling_structure: bool = True
    ):
        """
        Initialize section detector.
        
        Args:
            min_heading_font_size: Minimum font size to consider as heading
            use_docling_structure: Whether to use Docling-extracted structure if available
        """
        self.min_heading_font_size = min_heading_font_size
        self.use_docling_structure = use_docling_structure
        
        # Compile regex patterns
        self.numbering_regex = [re.compile(pattern) for pattern in self.NUMBERING_PATTERNS]
    
    def detect_from_processed_document(
        self,
        processed_doc: ProcessedDocument,
        validated_doc: Optional[ValidatedDocument] = None
    ) -> SectionHierarchy:
        """
        Detect section hierarchy from a ProcessedDocument.
        
        Uses the metadata already extracted (sections from Docling) as the primary source.
        
        Args:
            processed_doc: ProcessedDocument with extracted metadata
            validated_doc: Optional ValidatedDocument for additional context
            
        Returns:
            SectionHierarchy with detected structure
        """
        logger.info(f"Detecting section hierarchy for document {processed_doc.document_id}")
        
        sections_info = processed_doc.metadata.sections
        
        if not sections_info:
            logger.warning("No sections found in metadata, returning empty hierarchy")
            return self._create_empty_hierarchy(str(processed_doc.document_id))
        
        # Convert SectionInfo to SectionNode with hierarchy
        section_nodes = self._build_hierarchy_from_section_info(
            sections_info,
            str(processed_doc.document_id)
        )
        
        # Calculate statistics
        total_sections = len(section_nodes)
        max_depth = max((s.level for s in section_nodes), default=1)
        
        # Identify root sections (level 1)
        root_sections = [s.section_id for s in section_nodes if s.level == 1]
        
        hierarchy = SectionHierarchy(
            document_id=str(processed_doc.document_id),
            sections=section_nodes,
            root_sections=root_sections,
            total_sections=total_sections,
            max_depth=max_depth,
            detection_method="docling+heuristics",
            confidence_score=self._calculate_confidence(section_nodes)
        )
        
        logger.info(
            f"Detected {total_sections} sections with max depth {max_depth}, "
            f"confidence: {hierarchy.confidence_score:.2f}"
        )
        
        return hierarchy
    
    def detect_from_validated_document(
        self,
        validated_doc: ValidatedDocument
    ) -> SectionHierarchy:
        """
        Detect section hierarchy directly from a ValidatedDocument.
        
        Uses typography and pattern matching on raw text when metadata is not available.
        
        Args:
            validated_doc: ValidatedDocument from ingestion pipeline
            
        Returns:
            SectionHierarchy with detected structure
        """
        logger.info(f"Detecting section hierarchy from raw document {validated_doc.document_id}")
        
        # Extract potential headers from pages
        candidate_headers = self._extract_candidate_headers(validated_doc.pages)
        
        # Build hierarchy from candidates
        section_nodes = self._build_hierarchy_from_candidates(
            candidate_headers,
            str(validated_doc.document_id)
        )
        
        # Calculate statistics
        total_sections = len(section_nodes)
        max_depth = max((s.level for s in section_nodes), default=1) if section_nodes else 1
        
        # Identify root sections
        root_sections = [s.section_id for s in section_nodes if s.level == 1]
        
        hierarchy = SectionHierarchy(
            document_id=str(validated_doc.document_id),
            sections=section_nodes,
            root_sections=root_sections,
            total_sections=total_sections,
            max_depth=max_depth,
            detection_method="heuristics",
            confidence_score=self._calculate_confidence(section_nodes)
        )
        
        logger.info(
            f"Detected {total_sections} sections with max depth {max_depth}"
        )
        
        return hierarchy
    
    def _build_hierarchy_from_section_info(
        self,
        sections_info: List[SectionInfo],
        document_id: str
    ) -> List[SectionNode]:
        """
        Build SectionNode list with parent-child relationships from SectionInfo.
        
        Args:
            sections_info: List of SectionInfo from metadata
            document_id: Document identifier
            
        Returns:
            List of SectionNode with hierarchy
        """
        section_nodes = []
        parent_stack: List[Tuple[int, str]] = []  # (level, section_id)
        
        for idx, info in enumerate(sections_info):
            # Generate section ID
            section_id = f"{document_id}_section_{idx}"
            
            # Extract numbering if present
            numbering = self._extract_numbering(info.original_name)
            
            # Determine parent
            # Pop stack until we find a parent at lower level
            while parent_stack and parent_stack[-1][0] >= info.level:
                parent_stack.pop()
            
            parent_id = parent_stack[-1][1] if parent_stack else None
            
            # Create node
            node = SectionNode(
                section_id=section_id,
                title=self._clean_section_title(info.original_name),
                level=info.level,
                numbering=numbering,
                parent_id=parent_id,
                page_start=info.page_start,
                reading_order=idx,
                has_subsections=False,  # Will update later
                child_section_ids=[]
            )
            
            section_nodes.append(node)
            
            # Update parent's children list
            if parent_id:
                for parent_node in section_nodes:
                    if parent_node.section_id == parent_id:
                        parent_node.child_section_ids.append(section_id)
                        parent_node.has_subsections = True
                        break
            
            # Push current section to stack
            parent_stack.append((info.level, section_id))
        
        # Calculate page_end for each section
        self._calculate_page_ranges(section_nodes)
        
        return section_nodes
    
    def _extract_candidate_headers(
        self,
        pages: List[PageContent]
    ) -> List[Dict[str, Any]]:
        """
        Extract potential section headers from pages using typography and patterns.
        
        Args:
            pages: List of PageContent
            
        Returns:
            List of candidate header dicts
        """
        candidates = []
        
        for page in pages:
            # Split into lines
            lines = page.text.split('\n')
            
            for line_idx, line in enumerate(lines):
                line = line.strip()
                
                if not line or len(line) < 3:
                    continue
                
                # Check if line matches header patterns
                is_numbered = self._has_numbering(line)
                is_keyword = self._has_section_keyword(line)
                
                # Check typography if available
                is_large_font = False
                is_bold = False
                
                if page.layout_signals and page.layout_signals.font_info:
                    font_info = page.layout_signals.font_info
                    if font_info.font_size:
                        is_large_font = font_info.font_size >= self.min_heading_font_size
                    is_bold = font_info.is_bold
                
                # Heuristic: likely a header if numbered OR keyword OR (large + bold)
                if is_numbered or is_keyword or (is_large_font and is_bold):
                    candidates.append({
                        "text": line,
                        "page": page.page_number,
                        "is_numbered": is_numbered,
                        "is_keyword": is_keyword,
                        "is_large_font": is_large_font,
                        "is_bold": is_bold,
                        "font_size": page.layout_signals.font_info.font_size if page.layout_signals and page.layout_signals.font_info else None
                    })
        
        return candidates
    
    def _build_hierarchy_from_candidates(
        self,
        candidates: List[Dict[str, Any]],
        document_id: str
    ) -> List[SectionNode]:
        """
        Build hierarchical structure from candidate headers.
        
        Args:
            candidates: List of candidate header dicts
            document_id: Document identifier
            
        Returns:
            List of SectionNode with hierarchy
        """
        if not candidates:
            return []
        
        section_nodes = []
        parent_stack: List[Tuple[int, str]] = []
        
        for idx, candidate in enumerate(candidates):
            section_id = f"{document_id}_section_{idx}"
            
            # Extract numbering
            numbering = self._extract_numbering(candidate["text"])
            
            # Determine level based on numbering depth or font size
            level = self._infer_level(candidate, numbering)
            
            # Determine parent
            while parent_stack and parent_stack[-1][0] >= level:
                parent_stack.pop()
            
            parent_id = parent_stack[-1][1] if parent_stack else None
            
            node = SectionNode(
                section_id=section_id,
                title=self._clean_section_title(candidate["text"]),
                level=level,
                numbering=numbering,
                parent_id=parent_id,
                page_start=candidate["page"],
                font_size=candidate.get("font_size"),
                is_bold=candidate.get("is_bold"),
                reading_order=idx,
                has_subsections=False,
                child_section_ids=[]
            )
            
            section_nodes.append(node)
            
            # Update parent's children
            if parent_id:
                for parent_node in section_nodes:
                    if parent_node.section_id == parent_id:
                        parent_node.child_section_ids.append(section_id)
                        parent_node.has_subsections = True
                        break
            
            parent_stack.append((level, section_id))
        
        self._calculate_page_ranges(section_nodes)
        
        return section_nodes
    
    def _has_numbering(self, text: str) -> bool:
        """Check if text starts with section numbering."""
        for regex in self.numbering_regex:
            if regex.match(text):
                return True
        return False
    
    def _extract_numbering(self, text: str) -> Optional[str]:
        """Extract numbering prefix from text."""
        for regex in self.numbering_regex:
            match = regex.match(text)
            if match:
                return match.group(0).strip()
        return None
    
    def _has_section_keyword(self, text: str) -> bool:
        """Check if text contains common section keywords."""
        text_lower = text.lower()
        for keyword in self.SECTION_KEYWORDS:
            if keyword in text_lower:
                return True
        return False
    
    def _clean_section_title(self, text: str) -> str:
        """Remove numbering prefix from section title."""
        for regex in self.numbering_regex:
            text = regex.sub('', text)
        return text.strip()
    
    def _infer_level(self, candidate: Dict[str, Any], numbering: Optional[str]) -> int:
        """
        Infer section level from candidate information.
        
        Uses numbering depth (e.g., "1.2.3" = level 3) or font size hierarchy.
        """
        if numbering:
            # Count dots in decimal numbering (e.g., "1.2.3" has 2 dots = level 3)
            if '.' in numbering:
                return numbering.count('.') + 1
            # Single number/letter = level 1
            return 1
        
        # Fallback to font size heuristic (larger = higher level)
        # This is a simple heuristic; can be improved
        font_size = candidate.get("font_size")
        if font_size:
            if font_size >= 16:
                return 1
            elif font_size >= 14:
                return 2
            elif font_size >= 12:
                return 3
            else:
                return 4
        
        # Default to level 1
        return 1
    
    def _calculate_page_ranges(self, sections: List[SectionNode]) -> None:
        """
        Calculate page_end for each section based on next section's start.
        
        Modifies sections in place.
        """
        for idx in range(len(sections)):
            if idx < len(sections) - 1:
                # End page is one before next section starts
                sections[idx].page_end = sections[idx + 1].page_start - 1
            else:
                # Last section: leave page_end as None (until document end)
                sections[idx].page_end = None
    
    def _calculate_confidence(self, sections: List[SectionNode]) -> float:
        """
        Calculate confidence score based on section detection quality.
        
        Factors:
        - Presence of numbering
        - Consistent hierarchy
        - Reasonable section count
        """
        if not sections:
            return 0.0
        
        # Count sections with numbering
        numbered_sections = sum(1 for s in sections if s.numbering)
        numbering_ratio = numbered_sections / len(sections)
        
        # Check hierarchy consistency (all sections have valid levels)
        consistent_hierarchy = all(1 <= s.level <= 6 for s in sections)
        
        # Reasonable section count (3-30 sections typical for papers)
        count_reasonable = 3 <= len(sections) <= 30
        
        # Combine factors
        confidence = (
            numbering_ratio * 0.5 +
            (1.0 if consistent_hierarchy else 0.5) * 0.3 +
            (1.0 if count_reasonable else 0.7) * 0.2
        )
        
        return min(confidence, 1.0)
    
    def _create_empty_hierarchy(self, document_id: str) -> SectionHierarchy:
        """Create empty hierarchy for documents with no detected sections."""
        return SectionHierarchy(
            document_id=document_id,
            sections=[],
            root_sections=[],
            total_sections=0,
            max_depth=0,
            detection_method="none",
            confidence_score=0.0
        )
