"""
Heuristic-based section heading detection.

This module detects section headings using rule-based approaches WITHOUT LLM.
"""

import re
from dataclasses import dataclass
from src.text_extraction import TextBlock


@dataclass
class SectionCandidate:
    """Candidate section heading detected by heuristics.
    
    Attributes:
        text: Section heading text
        page_number: Page where section starts
        confidence: Confidence score (0-1) based on heuristics
    """
    text: str
    page_number: int
    confidence: float


class SectionDetector:
    """Detects section headings using heuristic rules."""
    
    # Common section keywords in academic papers
    SECTION_KEYWORDS = {
        'abstract', 'introduction', 'background', 'related work',
        'methodology', 'method', 'approach', 'experiments',
        'experimental setup', 'results', 'evaluation', 'discussion',
        'conclusion', 'future work', 'acknowledgment', 'references',
        'appendix', 'limitations', 'contributions', 'literature review',
        'implementation', 'analysis', 'dataset', 'problem statement',
        'formulation', 'preliminaries', 'notation'
    }
    
    # Patterns for numbered sections
    NUMBERED_PATTERNS = [
        r'^\d+\.$',  # "1.", "2.", etc.
        r'^\d+\s+[A-Z]',  # "1 Introduction"
        r'^\d+\.\d+',  # "1.1", "2.3"
        r'^[IVX]+\.',  # Roman numerals: "I.", "II."
        r'^[IVX]+\s+[A-Z]',  # "I Introduction"
        r'^\d+\)',  # "1)", "2)"
    ]
    
    def __init__(self):
        """Initialize the section detector."""
        self.compiled_patterns = [
            re.compile(pattern) for pattern in self.NUMBERED_PATTERNS
        ]
    
    def detect_sections(self, text_blocks: list[TextBlock]) -> list[SectionCandidate]:
        """Detect section headings from text blocks.
        
        Args:
            text_blocks: List of extracted text blocks from PDF
            
        Returns:
            List of detected section candidates with confidence scores
        """
        candidates = []
        
        for i, block in enumerate(text_blocks):
            text = block.text.strip()
            if not text:
                continue
            
            confidence = self._calculate_confidence(block, text, i, text_blocks)
            
            if confidence > 0.3:  # Threshold for section heading
                candidates.append(
                    SectionCandidate(
                        text=text,
                        page_number=block.page_number,
                        confidence=confidence
                    )
                )
        
        # Sort by page number and confidence
        candidates.sort(key=lambda x: (x.page_number, -x.confidence))
        
        # Filter overlapping candidates on same page
        filtered = self._filter_duplicates(candidates)
        
        return filtered
    
    def _calculate_confidence(
        self,
        block: TextBlock,
        text: str,
        index: int,
        all_blocks: list[TextBlock]
    ) -> float:
        """Calculate confidence that a text block is a section heading.
        
        Args:
            block: Current text block
            text: Cleaned text content
            index: Index of block in list
            all_blocks: All text blocks for context
            
        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.0
        
        # Rule 1: Element type is Title
        if block.element_type == 'Title':
            confidence += 0.4
        
        # Rule 2: Short text (section headings are usually concise)
        word_count = len(text.split())
        if 1 <= word_count <= 8:
            confidence += 0.2
        elif word_count > 20:
            confidence -= 0.2
        
        # Rule 3: Contains section keywords
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in self.SECTION_KEYWORDS):
            confidence += 0.3
        
        # Rule 4: Matches numbered section pattern
        first_chars = text[:20]
        if any(pattern.match(first_chars) for pattern in self.compiled_patterns):
            confidence += 0.3
        
        # Rule 5: Starts with capital letter
        if text[0].isupper():
            confidence += 0.1
        
        # Rule 6: All caps or title case
        if text.isupper() or text.istitle():
            confidence += 0.2
        
        # Rule 7: No ending punctuation (except period after number)
        if not text.endswith(('.', '!', '?', ',')):
            confidence += 0.1
        elif re.match(r'^\d+\.$', text):
            confidence += 0.1
        
        # Rule 8: Position in document (avoid very end)
        doc_position = index / max(len(all_blocks), 1)
        if doc_position < 0.9:  # Not in references section
            confidence += 0.1
        
        # Penalize if looks like body text
        if text.endswith('.') and word_count > 10:
            confidence -= 0.3
        
        return max(0.0, min(1.0, confidence))
    
    def _filter_duplicates(
        self,
        candidates: list[SectionCandidate]
    ) -> list[SectionCandidate]:
        """Filter duplicate or overlapping section candidates.
        
        Args:
            candidates: List of section candidates
            
        Returns:
            Filtered list with duplicates removed
        """
        if not candidates:
            return []
        
        filtered = []
        last_page = -1
        last_text = ""
        
        for candidate in candidates:
            # Skip if same page and very similar text
            if candidate.page_number == last_page:
                similarity = self._text_similarity(candidate.text, last_text)
                if similarity > 0.7:
                    # Keep the one with higher confidence
                    if candidate.confidence > filtered[-1].confidence:
                        filtered[-1] = candidate
                    continue
            
            filtered.append(candidate)
            last_page = candidate.page_number
            last_text = candidate.text
        
        return filtered
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity ratio.
        
        Args:
            text1: First text string
            text2: Second text string
            
        Returns:
            Similarity score between 0 and 1
        """
        text1_lower = text1.lower()
        text2_lower = text2.lower()
        
        if text1_lower == text2_lower:
            return 1.0
        
        # Simple word overlap
        words1 = set(text1_lower.split())
        words2 = set(text2_lower.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
