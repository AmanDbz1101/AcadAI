"""
Abstract extraction from research papers.

This module extracts the abstract section using heuristic rules.
"""

import re
from metadata_extraction.src.text_extraction import TextBlock
from metadata_extraction.src.section_detection import SectionCandidate


class AbstractExtractor:
    """Extracts abstract from research paper."""
    
    def extract(
        self,
        text_blocks: list[TextBlock],
        section_candidates: list[SectionCandidate]
    ) -> str:
        """Extract abstract from text blocks.
        
        Args:
            text_blocks: All text blocks from PDF
            section_candidates: Detected section headings
            
        Returns:
            Extracted abstract text, or empty string if not found
        """
        # Find the abstract heading
        abstract_start_idx = self._find_abstract_start(text_blocks)
        
        if abstract_start_idx == -1:
            return ""
        
        # Find where abstract ends (first section after abstract)
        abstract_end_idx = self._find_abstract_end(
            text_blocks,
            section_candidates,
            abstract_start_idx
        )
        
        # Extract abstract text
        abstract_blocks = text_blocks[abstract_start_idx + 1:abstract_end_idx]
        abstract_text = ' '.join(block.text.strip() for block in abstract_blocks)
        
        # Clean the abstract
        abstract_text = self._clean_abstract(abstract_text)
        
        return abstract_text
    
    def _find_abstract_start(self, text_blocks: list[TextBlock]) -> int:
        """Find the index where abstract heading appears.
        
        Args:
            text_blocks: All text blocks from PDF
            
        Returns:
            Index of abstract heading, or -1 if not found
        """
        abstract_pattern = re.compile(r'\babstract\b', re.IGNORECASE)
        
        for i, block in enumerate(text_blocks):
            text = block.text.strip().lower()
            
            # Look for "abstract" as standalone heading
            if abstract_pattern.match(text) and len(text.split()) <= 3:
                return i
            
            # Sometimes abstract is inline with other text
            if text.startswith('abstract:') or text.startswith('abstract.'):
                return i
        
        return -1
    
    def _find_abstract_end(
        self,
        text_blocks: list[TextBlock],
        section_candidates: list[SectionCandidate],
        abstract_start_idx: int
    ) -> int:
        """Find where abstract ends.
        
        Args:
            text_blocks: All text blocks from PDF
            section_candidates: Detected section headings
            abstract_start_idx: Index where abstract starts
            
        Returns:
            Index where abstract ends
        """
        abstract_start_page = text_blocks[abstract_start_idx].page_number
        
        # Find first section after abstract
        for candidate in section_candidates:
            # Skip abstract itself
            if 'abstract' in candidate.text.lower():
                continue
            
            # Find corresponding text block
            for i in range(abstract_start_idx + 1, len(text_blocks)):
                block = text_blocks[i]
                
                # Check if this block matches the section candidate
                if (block.page_number == candidate.page_number and
                    candidate.text.lower() in block.text.lower()):
                    return i
        
        # If no section found, use heuristic: abstract usually within 1-2 pages
        for i in range(abstract_start_idx + 1, len(text_blocks)):
            if text_blocks[i].page_number > abstract_start_page + 2:
                return i
        
        # Fallback: next 10 blocks
        return min(abstract_start_idx + 10, len(text_blocks))
    
    def _clean_abstract(self, abstract_text: str) -> str:
        """Clean abstract text by removing artifacts.
        
        Args:
            abstract_text: Raw abstract text
            
        Returns:
            Cleaned abstract text
        """
        # Remove extra whitespace
        text = ' '.join(abstract_text.split())
        
        # Remove common artifacts
        text = re.sub(r'^Abstract[:\.]?\s*', '', text, flags=re.IGNORECASE)
        
        # Remove page numbers if present
        text = re.sub(r'\b\d+\b\s*$', '', text)
        
        return text.strip()
