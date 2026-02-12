"""
Metadata extractor using Docling + Groq approach.

Extracts title, abstract, and section structure from research papers
using a combination of Docling layout analysis and Groq LLM classification.
"""

import os
import json
import re
import logging
from typing import List, Dict, Any, Optional

from docling.document_converter import DocumentConverter
from groq import Groq

from backend.models.document import ValidatedDocument
from backend.models.metadata import (
    ExtractedMetadata,
    SectionInfo,
    GlobalStats,
    PaperInference
)


logger = logging.getLogger(__name__)


class MetadataExtractor:
    """
    Extracts metadata using Docling structure analysis + Groq LLM classification.
    
    This approach is more accurate than pure heuristics by:
    1. Using Docling to extract document structure (headings, elements)
    2. Using Groq LLM to classify and organize the extracted structure
    3. Fallback to pattern matching for abstract extraction
    """
    
    HEADING_CLASSIFICATION_PROMPT = """You are an expert research paper analyst. Given a list of headings extracted from a research paper, classify and extract the following:

1. **title**: Identify which heading is the main paper title (usually the first major heading)
2. **abstract**: Extract the abstract text if provided in the headings list (return empty string if not found)
3. **sections**: Identify the main content sections ONLY

**EXCLUDE these sections:**
- References / Bibliography
- Acknowledgements / Acknowledgments
- Appendix / Appendices
- Supplementary Material
- Funding / Funding Information
- Author Contributions
- Competing Interests / Conflict of Interest
- Data Availability
- Code Availability
- Ethical Statement / Ethics Statement

**INCLUDE main content sections like:**
- Introduction
- Related Work / Background / Literature Review
- Methodology / Methods / Approach
- Experiments / Evaluation / Results
- Discussion / Analysis
- Conclusion / Future Work
- Any numbered sections that appear to contain main content

## Headings Extracted from Paper

{headings_json}

## Instructions

- Identify the paper title (usually first heading, might be unnumbered)
- Extract abstract text if present (look for "Abstract" heading)
- List main content sections with their level (1-5) and page_start
- Assign appropriate section levels based on heading hierarchy
- If abstract is not in headings, return empty string for abstract
- Be precise and only include sections that contain main paper content

Respond in JSON format:
{{
    "title": "paper title here",
    "abstract": "abstract text or empty string",
    "sections": [
        {{"original_name": "Introduction", "level": 1, "page_start": 1}},
        {{"original_name": "Methodology", "level": 1, "page_start": 3}}
    ]
}}
"""
    
    INFERENCE_PROMPT = """You are an expert research paper analyst. Based on the paper title, abstract, and sections, infer the following properties:

1. **paper_type**: Classify as one of: Survey, System, Theoretical, Empirical, Experimental, Position Paper, Tool Paper, Case Study, or Other
2. **difficulty**: Rate reading difficulty as: easy, medium, or hard
3. **math_heavy**: Determine if the paper contains heavy mathematical content (true/false)

**Title:** {title}

**Abstract:** {abstract}

**Sections:** {sections}

Respond in JSON format:
{{
    "paper_type": "one of the types above",
    "difficulty": "easy, medium, or hard",
    "math_heavy": true or false
}}
"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",
    ):
        """
        Initialize metadata extractor.
        
        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Groq model name
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("Groq API key not found. LLM features will be disabled.")
            self.client = None
        else:
            self.client = Groq(api_key=self.api_key)
        
        self.model = model
        self.converter = DocumentConverter()
    
    def extract(self, document: ValidatedDocument) -> ExtractedMetadata:
        """
        Extract metadata from a validated document.
        
        Args:
            document: ValidatedDocument from ingestion pipeline
            
        Returns:
            ExtractedMetadata with extracted fields
        """
        logger.info(f"Extracting metadata from document {document.document_id}")
        
        # Extract structured data using Docling
        structured_data = self._extract_structured_data(document.pdf_path)
        
        markdown = structured_data["markdown"]
        headings = structured_data["headings"]
        element_counts = structured_data["element_counts"]
        
        logger.info(f"Extracted {len(headings)} headings from document")
        
        # Classify headings using Groq LLM
        if self.client and headings:
            classification = self._classify_headings_llm(headings, markdown)
        else:
            classification = self._classify_headings_fallback(headings, markdown)
        
        logger.info(f"Classified: Title='{classification['title'][:50]}...', {len(classification['sections'])} sections")
        
        # Build global stats
        global_stats = GlobalStats(
            total_formulas=element_counts.get("formulas", 0),
            total_tables=element_counts.get("tables", 0),
            total_figures=element_counts.get("pictures", 0),
            total_pages=document.page_count,
            total_sections=len(classification['sections'])
        )
        
        # Infer paper properties (uses formula counts and other stats)
        if self.client:
            inference = self._infer_paper_properties(
                classification['title'],
                classification['abstract'],
                classification['sections'],
                global_stats
            )
        else:
            # Fallback to heuristic-based inference without LLM
            inference = self._infer_paper_properties_heuristic(global_stats)
        
        # Build metadata
        metadata = ExtractedMetadata(
            title=classification['title'],
            abstract=classification['abstract'],
            sections=classification['sections'],
            global_stats=global_stats,
            inference=inference,
            extraction_method="docling+groq" if self.client else "docling",
            fallback_used=not bool(self.client),
            missing_fields=self._identify_missing_fields(classification)
        )
        
        metadata.confidence_score = metadata.get_field_coverage()
        
        logger.info(
            f"Extracted metadata with {len(metadata.missing_fields)} missing fields. "
            f"Confidence: {metadata.confidence_score:.2f}"
        )
        
        return metadata
    
    def _extract_structured_data(self, pdf_path) -> Dict[str, Any]:
        """
        Extract structured document data using Docling.
        
        Returns:
            Dict with markdown, headings, and element counts
        """
        result = self.converter.convert(str(pdf_path))
        doc = result.document
        
        # Extract markdown
        markdown = doc.export_to_markdown()
        
        # Extract all headings with levels
        headings = []
        for item, level in doc.iterate_items():
            if item.label == "section_header":
                page_no = 1
                if item.prov:
                    page_no = getattr(item.prov[0], "page_no", 0) + 1  # 1-indexed
                
                headings.append({
                    "text": item.text if hasattr(item, 'text') else "",
                    "level": level,
                    "page": page_no
                })
        
        # Count document elements
        element_counts = {
            "formulas": 0,
            "tables": 0,
            "pictures": 0,
        }
        
        for item, level in doc.iterate_items():
            if item.label in ["formula", "equation"]:
                element_counts["formulas"] += 1
            elif item.label == "table":
                element_counts["tables"] += 1
            elif item.label == "picture":
                element_counts["pictures"] += 1
        
        return {
            "markdown": markdown,
            "headings": headings,
            "element_counts": element_counts
        }
    
    def _classify_headings_llm(
        self,
        headings: List[Dict[str, Any]],
        markdown: str
    ) -> Dict[str, Any]:
        """
        Classify headings using Groq LLM.
        
        Args:
            headings: List of heading dicts from Docling
            markdown: Full markdown text
            
        Returns:
            Dict with title, abstract, and sections
        """
        headings_json = json.dumps(headings, indent=2)
        
        prompt = self.HEADING_CLASSIFICATION_PROMPT.format(headings_json=headings_json)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise metadata extraction assistant. Return valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Convert sections to SectionInfo objects
            sections = [
                SectionInfo(**section)
                for section in result.get("sections", [])
            ]
            
            # If abstract is empty or too short, try extracting from markdown
            abstract = result.get("abstract", "")
            if not abstract or len(abstract.strip()) < 50:
                fallback_abstract = self._extract_abstract_from_markdown(markdown)
                if fallback_abstract:
                    abstract = fallback_abstract
            
            return {
                "title": result.get("title", ""),
                "abstract": abstract,
                "sections": sections
            }
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return self._classify_headings_fallback(headings, markdown)
    
    def _classify_headings_fallback(
        self,
        headings: List[Dict[str, Any]],
        markdown: str
    ) -> Dict[str, Any]:
        """
        Fallback classification without LLM using pattern matching.
        
        Args:
            headings: List of heading dicts
            markdown: Full markdown text
            
        Returns:
            Dict with title, abstract, and sections
        """
        # Extract title (first heading)
        title = headings[0]["text"] if headings else "Unknown Title"
        
        # Extract abstract from markdown
        abstract = self._extract_abstract_from_markdown(markdown)
        
        # Filter sections
        exclude_keywords = [
            'reference', 'bibliography', 'acknowledgement', 'acknowledgment',
            'appendix', 'supplementary', 'funding', 'author contribution',
            'competing interest', 'conflict of interest', 'data availability',
            'code availability', 'ethical', 'ethics'
        ]
        
        sections = []
        for heading in headings[1:]:  # Skip first (title)
            text_lower = heading["text"].lower()
            
            # Check if should exclude
            if any(keyword in text_lower for keyword in exclude_keywords):
                continue
            
            sections.append(SectionInfo(
                original_name=heading["text"],
                level=heading["level"],
                page_start=heading["page"]
            ))
        
        return {
            "title": title,
            "abstract": abstract,
            "sections": sections
        }
    
    def _extract_abstract_from_markdown(self, markdown: str) -> str:
        """
        Extract abstract from markdown text using pattern matching.
        
        Args:
            markdown: Full markdown text
            
        Returns:
            Abstract text or empty string
        """
        # Try to find abstract section
        abstract_pattern = r'(?i)(?:^|\n)#{1,3}\s*abstract\s*\n((?:(?!^#{1,3}\s).)+)'
        match = re.search(abstract_pattern, markdown, re.MULTILINE | re.DOTALL)
        
        if match:
            abstract = match.group(1).strip()
            # Clean up the abstract
            abstract = re.sub(r'\n+', ' ', abstract)
            abstract = re.sub(r'\s+', ' ', abstract)
            return abstract
        
        # Fallback: try to find text after "Abstract" keyword
        lines = markdown.split('\n')
        abstract_lines = []
        capture = False
        
        for line in lines:
            line_lower = line.lower().strip()
            
            if 'abstract' in line_lower and len(line_lower) < 50:
                capture = True
                continue
            
            if capture:
                # Stop at next heading or introduction
                if line.startswith('#') or 'introduction' in line.lower():
                    break
                if line.strip():
                    abstract_lines.append(line.strip())
        
        if abstract_lines:
            return ' '.join(abstract_lines)
        
        return ""
    
    def _infer_paper_properties(
        self,
        title: str,
        abstract: str,
        sections: List[SectionInfo],
        global_stats: GlobalStats
    ) -> PaperInference:
        """
        Infer paper properties using Groq LLM with formula counts.
        
        Args:
            title: Paper title
            abstract: Paper abstract
            sections: List of sections
            global_stats: Document statistics including formula count
            
        Returns:
            PaperInference
        """
        sections_str = ", ".join([s.original_name for s in sections[:10]])
        
        # Enhanced prompt with formula count information
        enhanced_prompt = f"""{self.INFERENCE_PROMPT.format(
            title=title,
            abstract=abstract,
            sections=sections_str
        )}

**Additional Context:**
- Total Formulas: {global_stats.total_formulas}
- Formulas per Page: {global_stats.total_formulas / global_stats.total_pages if global_stats.total_pages > 0 else 0:.2f}
- Total Tables: {global_stats.total_tables}
- Total Figures: {global_stats.total_figures}

Use the formula density to help determine if the paper is math_heavy:
- >= 2.0 formulas/page: Definitely math-heavy
- >= 1.0 formulas/page: Likely math-heavy
- >= 10 total formulas: Consider math-heavy
- < 0.5 formulas/page: Probably not math-heavy
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise paper classification assistant. Return valid JSON only. Use the formula counts to accurately determine if a paper is math-heavy."
                    },
                    {
                        "role": "user",
                        "content": enhanced_prompt
                    }
                ],
                temperature=0.1,
                max_tokens=512,
                response_format={"type": "json_object"}
            )
            
            inference_data = json.loads(response.choices[0].message.content)
            
            return PaperInference(
                paper_type=inference_data.get("paper_type", "Unknown"),
                difficulty=inference_data.get("difficulty", "medium"),
                math_heavy=inference_data.get("math_heavy", False)
            )
            
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            return self._infer_paper_properties_heuristic(global_stats)
    
    def _infer_paper_properties_heuristic(
        self,
        global_stats: GlobalStats
    ) -> PaperInference:
        """
        Infer paper properties using heuristics when LLM is unavailable.
        
        Args:
            global_stats: Document statistics
            
        Returns:
            PaperInference
        """
        formulas_per_page = (
            global_stats.total_formulas / global_stats.total_pages 
            if global_stats.total_pages > 0 else 0
        )
        
        # Determine if math-heavy based on formula density
        if formulas_per_page >= 2.0:
            math_heavy = True
            difficulty = "advanced"
            paper_type = "theoretical_research"
        elif formulas_per_page >= 1.0 or global_stats.total_formulas >= 10:
            math_heavy = True
            difficulty = "intermediate"
            paper_type = "research_article"
        elif formulas_per_page >= 0.3 or global_stats.total_formulas >= 5:
            math_heavy = False
            difficulty = "intermediate"
            paper_type = "research_article"
        else:
            math_heavy = False
            # Use section count and page count for difficulty
            if global_stats.total_pages > 20 or global_stats.total_sections > 10:
                difficulty = "intermediate"
            else:
                difficulty = "beginner"
            paper_type = "research_article"
        
        logger.info(
            f"Heuristic inference: formulas={global_stats.total_formulas}, "
            f"density={formulas_per_page:.2f}, math_heavy={math_heavy}, "
            f"difficulty={difficulty}"
        )
        
        return PaperInference(
            paper_type=paper_type,
            difficulty=difficulty,
            math_heavy=math_heavy
        )
    
    def _identify_missing_fields(self, classification: Dict[str, Any]) -> List[str]:
        """Identify which core metadata fields are missing."""
        missing = []
        
        if not classification.get('title'):
            missing.append('title')
        if not classification.get('abstract'):
            missing.append('abstract')
        if not classification.get('sections'):
            missing.append('sections')
        
        return missing
