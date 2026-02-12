"""
Heuristic-based metadata extractor.

Uses Docling layout analysis and pattern matching to extract metadata
from research papers.
"""

import re
import logging
from typing import Optional, List, Dict, Any, Tuple

from backend.models.document import ValidatedDocument, PageContent, FontInfo
from backend.models.metadata import ExtractedMetadata, Author


logger = logging.getLogger(__name__)


class MetadataExtractor:
    """
    Extracts metadata from validated documents using heuristic rules.
    
    Uses layout signals (font size, position, formatting) and keyword patterns
    to identify and extract metadata fields from research papers.
    """
    
    def __init__(
        self,
        title_min_font_size: float = 14.0,
        abstract_keywords: List[str] = None,
        keywords_keywords: List[str] = None,
    ):
        """
        Initialize metadata extractor.
        
        Args:
            title_min_font_size: Minimum font size for title detection
            abstract_keywords: Keywords to identify abstract section
            keywords_keywords: Keywords to identify keywords section
        """
        self.title_min_font_size = title_min_font_size
        self.abstract_keywords = abstract_keywords or ["abstract"]
        self.keywords_keywords = keywords_keywords or ["keywords", "key words", "index terms"]
        
        # Common patterns
        self.doi_pattern = re.compile(
            r'(?:doi:|DOI:|https?://doi\.org/)?\s*'
            r'(10\.\d{4,}/[^\s]+)',
            re.IGNORECASE
        )
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        self.affiliation_keywords = [
            "university", "institute", "department", "college",
            "laboratory", "lab", "center", "centre", "school"
        ]
    
    def extract(self, document: ValidatedDocument) -> ExtractedMetadata:
        """
        Extract metadata from a validated document.
        
        Args:
            document: ValidatedDocument from ingestion pipeline
            
        Returns:
            ExtractedMetadata with extracted fields
        """
        logger.info(f"Extracting metadata from document {document.document_id}")
        
        # Focus on first 3 pages for metadata
        first_pages = [p for p in document.pages if p.page_number <= 3]
        
        metadata = ExtractedMetadata()
        
        # Extract each field
        metadata.title = self._extract_title(first_pages)
        metadata.authors = self._extract_authors(first_pages)
        metadata.abstract = self._extract_abstract(document.pages)
        metadata.keywords = self._extract_keywords(first_pages)
        metadata.doi = self._extract_doi(first_pages)
        
        # Track missing fields
        metadata.missing_fields = self._identify_missing_fields(metadata)
        metadata.extraction_method = "heuristic"
        
        # Calculate confidence based on field coverage
        metadata.confidence_score = metadata.get_field_coverage()
        
        logger.info(
            f"Extracted metadata with {len(metadata.missing_fields)} missing fields. "
            f"Confidence: {metadata.confidence_score:.2f}"
        )
        
        return metadata
    
    def _extract_title(self, pages: List[PageContent]) -> Optional[str]:
        """
        Extract paper title from first pages.
        
        Uses heuristics:
        - Largest font size on first page
        - Positioned near top
        - Not in header/footer
        """
        if not pages:
            return None
        
        first_page = pages[0]
        
        # Try to find title using layout signals
        if hasattr(first_page, 'layout_signals') and first_page.layout_signals:
            # In practice, Docling provides blocks with font info
            # For now, we'll use a simpler approach based on text patterns
            pass
        
        # Fallback: Look for largest text block on first page
        # Split into lines and analyze
        lines = first_page.text.strip().split('\n')
        
        # Filter out empty lines
        lines = [line.strip() for line in lines if line.strip()]
        
        if not lines:
            return None
        
        # Title is typically one of the first few lines
        # and longer than 10 characters but shorter than 200
        for line in lines[:10]:
            if 10 < len(line) < 200:
                # Not a URL or email
                if not ('http' in line.lower() or '@' in line):
                    # Not all caps (likely not a header)
                    if not line.isupper() or len(line) < 30:
                        return line
        
        # Fallback to first substantial line
        for line in lines[:5]:
            if len(line) > 10:
                return line
        
        return None
    
    def _extract_authors(self, pages: List[PageContent]) -> List[Author]:
        """
        Extract author information from first pages.
        
        Authors are typically found after the title on the first page.
        """
        if not pages:
            return []
        
        first_page = pages[0]
        lines = first_page.text.strip().split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        
        authors = []
        
        # Skip title (first substantial line)
        title_found = False
        potential_author_lines = []
        
        for i, line in enumerate(lines[:15]):  # Check first 15 lines
            if not title_found and len(line) > 10:
                title_found = True
                continue
            
            if title_found:
                # Check if line contains author-like content
                # Authors often have commas, "and", or multiple words
                if self._looks_like_author_line(line):
                    potential_author_lines.append(line)
                    
                # Stop at abstract or keywords
                if any(kw in line.lower() for kw in self.abstract_keywords + self.keywords_keywords):
                    break
        
        # Parse author lines
        for line in potential_author_lines[:3]:  # Usually 1-3 lines of authors
            parsed_authors = self._parse_author_line(line)
            authors.extend(parsed_authors)
        
        return authors[:20]  # Reasonable limit
    
    def _looks_like_author_line(self, line: str) -> bool:
        """Check if a line looks like it contains author names."""
        # Has commas or "and" (common in author lists)
        if ',' in line or ' and ' in line.lower():
            return True
        
        # Has multiple capitalized words (names)
        words = line.split()
        capitalized = sum(1 for w in words if w and w[0].isupper())
        if capitalized >= 2 and len(words) <= 8:
            return True
        
        # Has superscript-like numbers (affiliations)
        if re.search(r'\d+', line) and len(line) < 100:
            return True
        
        return False
    
    def _parse_author_line(self, line: str) -> List[Author]:
        """Parse a line containing author names."""
        authors = []
        
        # Remove affiliation markers (numbers, asterisks)
        clean_line = re.sub(r'[0-9\*†‡§¶]', '', line)
        
        # Split by commas and "and"
        parts = re.split(r',| and ', clean_line, flags=re.IGNORECASE)
        
        for part in parts:
            part = part.strip()
            if part and len(part) > 2:
                # Check if it's a name (has at least 2 words, not too long)
                words = part.split()
                if 2 <= len(words) <= 5:
                    # Extract email if present
                    email_match = self.email_pattern.search(part)
                    email = email_match.group(0) if email_match else None
                    
                    # Clean name (remove email)
                    name = self.email_pattern.sub('', part).strip()
                    
                    if name:
                        authors.append(Author(name=name, email=email))
        
        return authors
    
    def _extract_abstract(self, pages: List[PageContent]) -> Optional[str]:
        """
        Extract abstract text.
        
        Looks for "Abstract" keyword and extracts following text.
        """
        # Check first 3 pages
        for page in pages[:3]:
            text = page.text
            
            # Find abstract section
            for keyword in self.abstract_keywords:
                pattern = re.compile(
                    rf'\b{keyword}\b[:\.\-\s]*(.+?)(?=\b(?:introduction|keywords|1\.|2\.)\b|\Z)',
                    re.IGNORECASE | re.DOTALL
                )
                
                match = pattern.search(text)
                if match:
                    abstract = match.group(1).strip()
                    
                    # Clean up
                    abstract = re.sub(r'\s+', ' ', abstract)  # Normalize whitespace
                    abstract = abstract.strip()
                    
                    # Validate length (abstracts are typically 100-2000 characters)
                    if 100 <= len(abstract) <= 3000:
                        return abstract
        
        return None
    
    def _extract_keywords(self, pages: List[PageContent]) -> List[str]:
        """
        Extract keywords from first pages.
        
        Looks for "Keywords" section and extracts list.
        """
        keywords = []
        
        for page in pages[:2]:
            text = page.text
            
            # Find keywords section
            for keyword_label in self.keywords_keywords:
                pattern = re.compile(
                    rf'\b{keyword_label}\b[:\.\-\s]*(.+?)(?=\n\n|\n[A-Z]|\Z)',
                    re.IGNORECASE
                )
                
                match = pattern.search(text)
                if match:
                    keywords_text = match.group(1).strip()
                    
                    # Split by common delimiters
                    keyword_list = re.split(r'[,;·•]', keywords_text)
                    
                    for kw in keyword_list:
                        kw = kw.strip()
                        # Clean and validate
                        if kw and 2 <= len(kw) <= 50:
                            # Remove numbers and special chars at start/end
                            kw = re.sub(r'^[\d\W]+|[\d\W]+$', '', kw)
                            if kw:
                                keywords.append(kw)
                    
                    if keywords:
                        return keywords[:15]  # Reasonable limit
        
        return keywords
    
    def _extract_doi(self, pages: List[PageContent]) -> Optional[str]:
        """
        Extract DOI from first pages.
        
        Looks for DOI pattern (10.xxxx/...).
        """
        for page in pages[:2]:
            match = self.doi_pattern.search(page.text)
            if match:
                doi = match.group(1).strip()
                # Clean trailing punctuation
                doi = re.sub(r'[,;.\s]+$', '', doi)
                return doi
        
        return None
    
    def _identify_missing_fields(self, metadata: ExtractedMetadata) -> List[str]:
        """Identify which core metadata fields are missing."""
        missing = []
        
        if not metadata.title:
            missing.append('title')
        if not metadata.authors:
            missing.append('authors')
        if not metadata.abstract:
            missing.append('abstract')
        if not metadata.keywords:
            missing.append('keywords')
        if not metadata.doi:
            missing.append('doi')
        
        return missing
