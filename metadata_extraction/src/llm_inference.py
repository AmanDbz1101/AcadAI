"""
LLM inference for paper properties using Groq.

This module uses a SINGLE LLM call to infer paper properties.
"""

import os
import json
from typing import Optional
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser
from langchain_core.prompts import PromptTemplate
from metadata_extraction.src.models import PaperInference, SectionMetadata

# Load environment variables from .env file
load_dotenv()


class PaperInferenceEngine:
    """Infers paper properties using LLM (Groq)."""
    
    # Default model to use
    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    
    # Prompt template for inference
    INFERENCE_PROMPT = """You are an expert research paper analyst. Based on the provided paper information, infer the following properties:

1. **paper_type**: Classify the paper as one of: Survey, System, Theoretical, Empirical, Experimental, Position Paper, Tool Paper, Case Study, or Other
2. **difficulty**: Rate the reading difficulty as: easy, medium, or hard
3. **math_heavy**: Determine if the paper contains heavy mathematical content (true/false)

## Paper Information

**Title:** {title}

**Abstract:** {abstract}

**Sections:** {sections}

## Instructions

- Be concise and precise
- Base your analysis ONLY on the provided information
- If you cannot determine a property confidently, make your best inference

{format_instructions}
"""
    
    def __init__(self, model_name: Optional[str] = None):
        """Initialize the inference engine.
        
        Args:
            model_name: Groq model name (defaults to llama-3.3-70b-versatile)
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.api_key = os.getenv("GROQ_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Groq API key not found. Make sure GROQ_API_KEY is set in your .env file."
            )
        
        # Initialize LLM
        self.llm = ChatGroq(
            model=self.model_name,
            api_key=self.api_key,
            temperature=0.1,  # Low temperature for consistent inference
        )
        
        # Initialize output parser
        self.parser = PydanticOutputParser(pydantic_object=PaperInference)
        
        # Create prompt template
        self.prompt = PromptTemplate(
            template=self.INFERENCE_PROMPT,
            input_variables=["title", "abstract", "sections"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            }
        )
        
        # Create chain
        self.chain = self.prompt | self.llm | self.parser
    
    def infer(
        self,
        title: str,
        abstract: str,
        section_names: list[str]
    ) -> PaperInference:
        """Infer paper properties using LLM.
        
        This makes ONE LLM call to infer all properties.
        
        Args:
            title: Paper title
            abstract: Paper abstract
            section_names: List of normalized section names
            
        Returns:
            PaperInference object with inferred properties
            
        Raises:
            Exception: If LLM call fails or output parsing fails
        """
        try:
            # Prepare sections string
            sections_str = ", ".join(section_names) if section_names else "None detected"
            
            # Make LLM call
            result = self.chain.invoke({
                "title": title,
                "abstract": abstract,
                "sections": sections_str
            })
            
            return result
            
        except Exception as e:
            raise Exception(f"Error during LLM inference: {str(e)}")


class SectionRefinementEngine:
    """Refines detected sections using LLM to filter out non-section headings."""
    
    # Default model to use
    DEFAULT_MODEL = "openai/gpt-oss-120b"
    
    # One-shot prompt template for section refinement
    REFINEMENT_PROMPT = """You are an expert at identifying research paper section structures. Given a list of detected section headings (which may include false positives like bold text, page numbers, or fragments that aren't actually sections), identify and extract ONLY the actual section headings in their proper hierarchical order.

**IMPORTANT:** Research papers typically have fewer than 30 main sections and subsections. Sections are usually numbered sequentially (1., 2., 3., etc.) with subsections following a hierarchical pattern (2.1, 2.2, 3.1, etc.).

## Guidelines for Identifying Valid Sections:

**INCLUDE:**
- Numbered sections (1., 2., 2.1, etc.)
- Standard paper sections (Abstract, Introduction, Methods, Results, Discussion, Conclusion, References, etc.)
- Subsections that follow a clear numbering scheme
- Sections with descriptive names following numbers

**EXCLUDE:**
- Paper titles or subtitles (usually appear once at the beginning)
- Author names or affiliations
- Single letters, numbers, or unclear fragments (X, 4, i, v, arXiv, etc.)
- Dates or timestamps
- Page numbers
- Alert messages or UI text
- Long paragraphs of text (section headings are concise)
- Code snippets or variable names
- URLs or file paths
- Topic words without section numbers (unless clearly a standard section like "Abstract")

## Example

Input sections (may contain non-sections):
- Abstract
- MemGPT: Towards LLMs as Operating Systems
- 1. Introduction
- X
- Background
- RAG
- Charles Packer 1 Sarah Wooders
- 4
- 2. Methods
- 2.1 Models
- 2.2 Retriever: DPR
- 2.3 Generator: BART
- 2.4 Training
- 2.5 Decoding
- 3. Experiments
- 3.1 Open-domain Question Answering
- 3.2 Abstractive Question Answering
- 3.3 Jeopardy Question Generation
- 3.4 Fact Verification
- 4. Results
- 4.1 Open-domain Question Answering
- 4.2 Abstractive Question Answering
- 4.3 Jeopardy Question Generation
- 4.4 Fact Verification
- 4.5 Additional Results
- 5. Related Work
- 6. Discussion
- Broader Impact
- Acknowledgments
- References

Expected output (only actual sections in sequential order):
Abstract
1. Introduction
2. Methods
2.1 Models
2.2 Retriever: DPR
2.3 Generator: BART
2.4 Training
2.5 Decoding
3. Experiments
3.1 Open-domain Question Answering
3.2 Abstractive Question Answering
3.3 Jeopardy Question Generation
3.4 Fact Verification
4. Results
4.1 Open-domain Question Answering
4.2 Abstractive Question Answering
4.3 Jeopardy Question Generation
4.4 Fact Verification
4.5 Additional Results
5. Related Work
6. Discussion
Broader Impact
Acknowledgments
References

## Your Task

Input sections (may contain non-sections):
{sections_list}

Analyze the above list and return ONLY the actual section headings in their proper sequential order. Apply the guidelines above to filter out false positives.

Return your answer as a JSON object with a single key "sections" containing an array of the refined section names in order.

Example output format:
{{"sections": ["Abstract", "1. Introduction", "2. Methods", "2.1 Subsection", ...]}}
"""
    
    def __init__(self, model_name: Optional[str] = None):
        """Initialize the refinement engine.
        
        Args:
            model_name: Groq model name (defaults to llama-3.3-70b-versatile)
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.api_key = os.getenv("GROQ_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Groq API key not found. Make sure GROQ_API_KEY is set in your .env file."
            )
        
        # Initialize LLM
        self.llm = ChatGroq(
            model=self.model_name,
            api_key=self.api_key,
            temperature=0.1,  # Low temperature for consistent output
        )
        
        # Initialize output parser for JSON
        self.parser = JsonOutputParser()
        
        # Create prompt template
        self.prompt = PromptTemplate(
            template=self.REFINEMENT_PROMPT,
            input_variables=["sections_list"]
        )
        
        # Create chain
        self.chain = self.prompt | self.llm | self.parser
    
    def refine_sections(
        self,
        section_metadata: list[SectionMetadata]
    ) -> list[SectionMetadata]:
        """Refine section metadata by filtering out non-section headings.
        
        Args:
            section_metadata: List of detected section metadata (may contain false positives)
            
        Returns:
            Refined list of section metadata with only actual sections
            
        Raises:
            Exception: If LLM call fails or output parsing fails
        """
        try:
            # Sort sections by page number to ensure sequential order
            sorted_sections = sorted(section_metadata, key=lambda s: s.page_start)
            
            # Prepare sections list as a bulleted string
            sections_list = "\n".join([
                f"- {s.original_name}" for s in sorted_sections
            ])
            
            # Make LLM call
            result = self.chain.invoke({
                "sections_list": sections_list
            })
            
            # Extract refined section names
            refined_names = result.get("sections", [])
            
            if not refined_names:
                # If LLM returns empty, return original sections
                return section_metadata
            
            # Create a mapping from original names to section metadata
            name_to_metadata = {
                s.original_name: s for s in sorted_sections
            }
            
            # Build refined section list maintaining original metadata
            refined_sections = []
            for refined_name in refined_names:
                # Try exact match first
                if refined_name in name_to_metadata:
                    refined_sections.append(name_to_metadata[refined_name])
                else:
                    # Try case-insensitive match
                    for original_name, metadata in name_to_metadata.items():
                        if original_name.lower() == refined_name.lower():
                            refined_sections.append(metadata)
                            break
            
            print(f"Section refinement: {len(section_metadata)} → {len(refined_sections)} sections")
            
            return refined_sections
            
        except Exception as e:
            print(f"Warning: Error during section refinement: {str(e)}")
            print("Returning original sections")
            return section_metadata
