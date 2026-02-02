"""
Simple metadata extraction with Groq-based heading classification
"""

import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from .models import (
    HeadingClassificationOutput,
    SimpleMetadata,
    SectionInfo,
    GlobalStats,
    PaperInference
)
from .docling_extractor import DoclingExtractor

load_dotenv()


class SimpleMetadataExtractor:
    """Extract simple metadata using Groq classification"""
    
    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    
    HEADING_CLASSIFICATION_PROMPT = """You are an expert research paper analyst. Given a list of headings extracted from a research paper, classify and extract the following:

1. **title**: Identify which heading is the main paper title (usually the first major heading)
2. **abstract**: Extract the abstract text if provided in the headings list
3. **sections**: Identify the main content sections ONLY. 

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
- Extract abstract text (look for "Abstract" heading)
- List main content sections with their level (1-5) and page_start
- Assign appropriate section levels based on heading hierarchy
- If abstract is not in headings, return empty string
- Be precise and only include sections that contain main paper content

{format_instructions}
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
    
    def __init__(self, model_name: str = None):
        """Initialize extractor"""
        self.model_name = model_name or self.DEFAULT_MODEL
        self.api_key = os.getenv("GROQ_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Groq API key not found. Set GROQ_API_KEY in .env file."
            )
        
        # Initialize LLM with JSON mode
        self.llm = ChatGroq(
            model=self.model_name,
            api_key=self.api_key,
            temperature=0.1,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        
        # Initialize output parser for heading classification
        self.heading_parser = PydanticOutputParser(
            pydantic_object=HeadingClassificationOutput
        )
        
        # Create prompts
        self.heading_prompt = PromptTemplate(
            template=self.HEADING_CLASSIFICATION_PROMPT,
            input_variables=["headings_json"],
            partial_variables={
                "format_instructions": self.heading_parser.get_format_instructions()
            }
        )
        
        self.inference_prompt = PromptTemplate(
            template=self.INFERENCE_PROMPT,
            input_variables=["title", "abstract", "sections"]
        )
        
        self.docling = DoclingExtractor()
    
    def extract_metadata(
        self,
        pdf_path: str,
        document_id: str
    ) -> SimpleMetadata:
        """
        Extract simple metadata from PDF
        
        Args:
            pdf_path: Path to PDF file
            document_id: UUID document identifier
            
        Returns:
            SimpleMetadata object
        """
        # Extract structured data using Docling
        print(f"🔄 Extracting document structure with Docling...")
        docling_data = self.docling.extract_structured_data(pdf_path)
        
        markdown = docling_data["markdown"]
        headings = docling_data["headings"]
        element_counts = docling_data["element_counts"]
        total_pages = docling_data["total_pages"]
        
        print(f"✅ Extracted {len(headings)} headings, {total_pages} pages")
        
        # Classify headings using Groq LLM
        print(f"🤖 Classifying headings with Groq LLM...")
        classification = self._classify_headings(headings, markdown)
        
        print(f"✅ Classified: Title='{classification.title[:50]}...', {len(classification.sections)} sections")
        
        # Add stats to sections (initialize with zeros, can be enhanced later)
        for section in classification.sections:
            if not hasattr(section, 'stats') or section.stats is None:
                from .models import SectionStats
                section.stats = SectionStats()
        
        # Compute global statistics
        global_stats = GlobalStats(
            total_formulas=element_counts.get("formulas", 0),
            total_tables=element_counts.get("tables", 0),
            total_figures=element_counts.get("pictures", 0),
            total_text_blocks=element_counts.get("text_blocks", 0),
            total_pages=total_pages,
            total_sections=len(classification.sections)
        )
        
        # Infer paper properties
        print(f"🤖 Inferring paper properties...")
        inference = self._infer_paper_properties(
            classification.title,
            classification.abstract,
            classification.sections
        )
        
        print(f"✅ Inference: {inference.paper_type}, {inference.difficulty}, math_heavy={inference.math_heavy}")
        
        # Build metadata
        metadata = SimpleMetadata(
            document_id=document_id,
            paper_title=classification.title,
            abstract=classification.abstract,
            sections=classification.sections,
            global_stats=global_stats,
            inference=inference
        )
        
        return metadata
    
    def _classify_headings(
        self,
        headings: List[Dict[str, Any]],
        markdown: str
    ) -> HeadingClassificationOutput:
        """
        Classify headings using Groq LLM with structured output
        
        Args:
            headings: List of heading dicts from Docling
            markdown: Full markdown text for abstract extraction
            
        Returns:
            HeadingClassificationOutput
        """
        # Format headings for LLM
        headings_json = json.dumps(headings, indent=2)
        
        # Create chain
        chain = self.heading_prompt | self.llm | self.heading_parser
        
        # Invoke LLM
        try:
            result = chain.invoke({"headings_json": headings_json})
            
            # If abstract is empty, try to extract from markdown
            if not result.abstract or len(result.abstract.strip()) < 50:
                fallback_abstract = self.docling.extract_abstract_from_markdown(markdown)
                if fallback_abstract:
                    result.abstract = fallback_abstract
            
            return result
        
        except Exception as e:
            print(f"⚠️  Warning: LLM classification failed: {e}")
            # Fallback to simple extraction
            return self._fallback_classification(headings, markdown)
    
    def _fallback_classification(
        self,
        headings: List[Dict[str, Any]],
        markdown: str
    ) -> HeadingClassificationOutput:
        """Fallback classification without LLM"""
        
        # Extract title (first heading)
        title = headings[0]["text"] if headings else "Unknown Title"
        
        # Extract abstract
        abstract = self.docling.extract_abstract_from_markdown(markdown)
        
        # Filter sections (simple heuristic)
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
        
        return HeadingClassificationOutput(
            title=title,
            abstract=abstract,
            sections=sections
        )
    
    def _infer_paper_properties(
        self,
        title: str,
        abstract: str,
        sections: List[SectionInfo]
    ) -> PaperInference:
        """
        Infer paper properties using Groq LLM
        
        Args:
            title: Paper title
            abstract: Paper abstract
            sections: List of sections
            
        Returns:
            PaperInference
        """
        # Format sections
        sections_str = ", ".join([s.original_name for s in sections[:10]])
        
        # Create chain (JSON mode already set in LLM)
        chain = self.inference_prompt | self.llm
        
        try:
            result = chain.invoke({
                "title": title,
                "abstract": abstract,
                "sections": sections_str
            })
            
            # Parse JSON response
            inference_data = json.loads(result.content)
            
            return PaperInference(
                paper_type=inference_data.get("paper_type", "Unknown"),
                difficulty=inference_data.get("difficulty", "medium"),
                math_heavy=inference_data.get("math_heavy", False)
            )
        
        except Exception as e:
            print(f"⚠️  Warning: Inference failed: {e}")
            # Return default inference
            return PaperInference(
                paper_type="Unknown",
                difficulty="medium",
                math_heavy=False
            )
