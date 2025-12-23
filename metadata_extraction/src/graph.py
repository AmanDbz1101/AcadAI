"""
LangGraph orchestration for metadata extraction pipeline.

This module defines the state graph that orchestrates all extraction steps.
"""

import os
from typing import TypedDict, Annotated, Sequence
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from metadata_extraction.src.models import SectionMetadata, PaperInference, PaperMetadata
from metadata_extraction.src.text_extraction import PDFTextExtractor, TextBlock
from metadata_extraction.src.section_detection import SectionDetector, SectionCandidate
from metadata_extraction.src.normalization import SectionNormalizer
from metadata_extraction.src.abstract_extraction import AbstractExtractor
from metadata_extraction.src.llm_inference import PaperInferenceEngine, SectionRefinementEngine

# Load environment variables from .env file
load_dotenv()


class ExtractionState(TypedDict):
    """State object passed between nodes in the graph.
    
    Attributes:
        pdf_path: Path to PDF file
        text_blocks: Extracted text blocks from PDF
        section_candidates: Detected section candidates
        sections: Final section metadata list
        title: Extracted paper title
        abstract: Extracted abstract
        inference: LLM-inferred paper properties
        metadata: Final paper metadata object
        error: Error message if any step fails
    """
    pdf_path: str
    text_blocks: list[TextBlock]
    section_candidates: list[SectionCandidate]
    sections: list[SectionMetadata]
    title: str
    abstract: str
    inference: PaperInference | None
    metadata: PaperMetadata | None
    error: str | None


class MetadataExtractionGraph:
    """LangGraph-based orchestration for metadata extraction."""
    
    def __init__(self):
        """Initialize the extraction graph."""
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph.
        
        Returns:
            Compiled state graph
        """
        # Create graph
        workflow = StateGraph(ExtractionState)
        
        # Add nodes
        workflow.add_node("extract_text", self._extract_text_node)
        workflow.add_node("detect_sections", self._detect_sections_node)
        workflow.add_node("extract_title", self._extract_title_node)
        workflow.add_node("extract_abstract", self._extract_abstract_node)
        workflow.add_node("refine_sections", self._refine_sections_node)
        workflow.add_node("llm_inference", self._llm_inference_node)
        workflow.add_node("finalize_metadata", self._finalize_metadata_node)
        
        # Define edges (execution flow)
        workflow.set_entry_point("extract_text")
        workflow.add_edge("extract_text", "detect_sections")
        workflow.add_edge("detect_sections", "extract_title")
        workflow.add_edge("extract_title", "extract_abstract")
        workflow.add_edge("extract_abstract", "refine_sections")
        workflow.add_edge("refine_sections", "llm_inference")
        workflow.add_edge("llm_inference", "finalize_metadata")
        workflow.add_edge("finalize_metadata", END)
        
        # Compile graph
        return workflow.compile()
    
    def _extract_text_node(self, state: ExtractionState) -> ExtractionState:
        """Node: Extract text blocks from PDF.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with text_blocks
        """
        try:
            extractor = PDFTextExtractor(state["pdf_path"])
            text_blocks = extractor.extract()
            
            return {
                **state,
                "text_blocks": text_blocks,
            }
        except Exception as e:
            return {
                **state,
                "error": f"Text extraction failed: {str(e)}"
            }
    
    def _detect_sections_node(self, state: ExtractionState) -> ExtractionState:
        """Node: Detect section headings using heuristics and create section metadata.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with section_candidates and sections
        """
        try:
            detector = SectionDetector()
            candidates = detector.detect_sections(state["text_blocks"])
            
            # Create section metadata
            sections = []
            for candidate in candidates:
                section = SectionMetadata(
                    original_name=candidate.text,
                    page_start=candidate.page_number
                )
                sections.append(section)
            
            return {
                **state,
                "section_candidates": candidates,
                "sections": sections,
            }
        except Exception as e:
            return {
                **state,
                "error": f"Section detection failed: {str(e)}"
            }
    
    def _extract_title_node(self, state: ExtractionState) -> ExtractionState:
        """Node: Extract paper title.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with title
        """
        try:
            # Title is usually in first few blocks with Title type
            title = ""
            for block in state["text_blocks"][:10]:
                if block.element_type == "Title" and len(block.text.split()) > 2:
                    title = block.text.strip()
                    break
            
            # Fallback: first substantial text block
            if not title:
                for block in state["text_blocks"][:5]:
                    if len(block.text.split()) > 3:
                        title = block.text.strip()
                        break
            
            return {
                **state,
                "title": title or "Untitled Paper",
            }
        except Exception as e:
            return {
                **state,
                "title": "Untitled Paper",
                "error": f"Title extraction failed: {str(e)}"
            }
    
    def _extract_abstract_node(self, state: ExtractionState) -> ExtractionState:
        """Node: Extract abstract.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with abstract
        """
        try:
            extractor = AbstractExtractor()
            abstract = extractor.extract(
                state["text_blocks"],
                state["section_candidates"]
            )
            
            return {
                **state,
                "abstract": abstract or "No abstract found.",
            }
        except Exception as e:
            return {
                **state,
                "abstract": "No abstract found.",
                "error": f"Abstract extraction failed: {str(e)}"
            }
    
    def _refine_sections_node(self, state: ExtractionState) -> ExtractionState:
        """Node: Refine sections using LLM to remove false positives.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with refined sections
        """
        try:
            if not state["sections"]:
                return state
            
            # Create refinement engine
            refinement_engine = SectionRefinementEngine()
            
            # Refine sections
            refined_sections = refinement_engine.refine_sections(state["sections"])
            
            return {
                **state,
                "sections": refined_sections,
            }
        except Exception as e:
            print(f"Warning: Section refinement failed: {str(e)}")
            print("Continuing with original sections")
            return state
    
    def _llm_inference_node(self, state: ExtractionState) -> ExtractionState:
        """Node: Run LLM inference for paper properties.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with inference
        """
        try:
            # Get section names for LLM
            section_names = [s.original_name for s in state["sections"]]
            
            # Create inference engine
            engine = PaperInferenceEngine()
            
            # Run inference
            inference = engine.infer(
                title=state["title"],
                abstract=state["abstract"],
                section_names=section_names
            )
            
            return {
                **state,
                "inference": inference,
            }
        except Exception as e:
            # Create default inference if LLM fails
            default_inference = PaperInference(
                paper_type="Unknown",
                difficulty="medium",
                math_heavy=False
            )
            
            return {
                **state,
                "inference": default_inference,
                "error": f"LLM inference failed: {str(e)}"
            }
    
    def _finalize_metadata_node(self, state: ExtractionState) -> ExtractionState:
        """Node: Create final PaperMetadata object.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with metadata
        """
        try:
            metadata = PaperMetadata(
                title=state["title"],
                abstract=state["abstract"],
                sections=state["sections"],
                inference=state["inference"]
            )
            
            return {
                **state,
                "metadata": metadata,
            }
        except Exception as e:
            return {
                **state,
                "error": f"Metadata finalization failed: {str(e)}"
            }
    
    def extract(self, pdf_path: str) -> PaperMetadata:
        """Execute the extraction pipeline.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            PaperMetadata object
            
        Raises:
            Exception: If extraction fails
        """
        # Initialize state
        initial_state = ExtractionState(
            pdf_path=pdf_path,
            text_blocks=[],
            section_candidates=[],
            sections=[],
            title="",
            abstract="",
            inference=None,
            metadata=None,
            error=None
        )
        
        # Run graph
        final_state = self.graph.invoke(initial_state)
        
        # Check for errors
        if final_state.get("error"):
            print(f"Warning: {final_state['error']}")
        
        # Return metadata
        if final_state.get("metadata"):
            return final_state["metadata"]
        else:
            raise Exception("Metadata extraction failed")
