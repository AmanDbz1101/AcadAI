"""
LangGraph orchestration for metadata extraction pipeline.

Pipeline: Fetch → Group → Heuristics → Stats → LLM → Assemble
"""

from typing import TypedDict, List
from langgraph.graph import StateGraph, END

from .models import (
    QdrantPoint,
    DocumentGroup,
    SectionMetadata,
    GlobalStats,
    PaperInference,
    PaperMetadata
)
from .database import QdrantFetcher
from .section_detection import SectionDetector
from .llm_inference import PaperInferenceEngine


class ExtractionState(TypedDict):
    """State passed through the extraction pipeline."""
    document_id: str
    points: List[QdrantPoint]
    paper_title: str
    abstract: str
    sections: List[SectionMetadata]
    global_stats: GlobalStats
    inference: PaperInference
    metadata: PaperMetadata


class MetadataExtractionGraph:
    """LangGraph-based orchestration of metadata extraction."""
    
    def __init__(
        self,
        fetcher: QdrantFetcher = None,
        detector: SectionDetector = None,
        inference_engine: PaperInferenceEngine = None
    ):
        """
        Initialize extraction graph.
        
        Args:
            fetcher: Qdrant data fetcher
            detector: Section detector
            inference_engine: LLM inference engine
        """
        self.fetcher = fetcher or QdrantFetcher()
        self.detector = detector or SectionDetector()
        self.inference_engine = inference_engine or PaperInferenceEngine()
        
        # Build graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph."""
        workflow = StateGraph(ExtractionState)
        
        # Add nodes
        workflow.add_node("fetch", self._fetch_node)
        workflow.add_node("detect_sections", self._detect_sections_node)
        workflow.add_node("compute_stats", self._compute_stats_node)
        workflow.add_node("extract_title", self._extract_title_node)
        workflow.add_node("extract_abstract", self._extract_abstract_node)
        workflow.add_node("infer", self._infer_node)
        workflow.add_node("assemble", self._assemble_node)
        
        # Define edges
        workflow.set_entry_point("fetch")
        workflow.add_edge("fetch", "detect_sections")
        workflow.add_edge("detect_sections", "compute_stats")
        workflow.add_edge("compute_stats", "extract_title")
        workflow.add_edge("extract_title", "extract_abstract")
        workflow.add_edge("extract_abstract", "infer")
        workflow.add_edge("infer", "assemble")
        workflow.add_edge("assemble", END)
        
        return workflow.compile()
    
    def _fetch_node(self, state: ExtractionState) -> ExtractionState:
        """Fetch data from Qdrant."""
        document_id = state["document_id"]
        
        # Fetch document
        doc_group = self.fetcher.fetch_document(document_id)
        
        if not doc_group:
            raise ValueError(f"Document {document_id} not found")
        
        # Sort points by page number
        points = doc_group.sorted_points
        
        state["points"] = points
        return state
    
    def _extract_title_node(self, state: ExtractionState) -> ExtractionState:
        """Extract title using heuristics from Title section text blocks."""
        points = state["points"]
        sections = state["sections"]
        
        # Find the Title section
        title_section = None
        for section in sections:
            if section.original_name == "Title":
                title_section = section
                break
        
        if not title_section or not title_section.stats.text_block_ids:
            state["paper_title"] = "Untitled Document"
            return state
        
        # Get text blocks from Title section
        title_element_ids = set(title_section.stats.text_block_ids)
        title_text_blocks = []
        
        for point in points:
            if (point.element_id in title_element_ids and
                point.category in ("NarrativeText", "CompositeElement", "Title", "UncategorizedText")):
                title_text_blocks.append(point)
        
        # Sort by page and y-coordinate (top to bottom)
        title_text_blocks.sort(key=lambda p: (
            p.page_number,
            self._get_y_min(p.coordinates) if p.coordinates else 0
        ))
        
        # Apply heuristics to find the title
        paper_title = self._find_title_with_heuristics(title_text_blocks)
        
        state["paper_title"] = paper_title
        return state
    
    def _find_title_with_heuristics(self, text_blocks: list) -> str:
        """Find paper title using heuristic rules.
        
        Heuristics:
        1. Title is usually the longest text block (in terms of character count)
        2. Title appears near the top of the page
        3. Title has multiple words (typically 5-20 words)
        4. Exclude blocks that look like author names (short, all caps, comma-separated)
        5. Exclude blocks with URLs, emails, or affiliations
        """
        if not text_blocks:
            return "Untitled Document"
        
        import re
        
        candidates = []
        
        for i, block in enumerate(text_blocks):
            text = block.page_content.strip()
            
            if not text:
                continue
            
            # Skip if it looks like metadata (email, URL, affiliation)
            if any(pattern in text.lower() for pattern in ['@', 'http', 'university', 'department', 'institute']):
                continue
            
            # Skip if it looks like author names (contains many capital letters, special chars, etc.)
            # Author lists typically have asterisks, superscripts, or lots of capital letters
            if text.count('*') > 2 or text.count('!') > 2 or text.count('?') > 2:
                continue
            
            # Skip if it has too many capital letter sequences (typical of author names)
            capital_sequences = len(re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', text))
            if capital_sequences > 5:
                continue
            
            # Skip if it's too short (likely not a title)
            word_count = len(text.split())
            if word_count < 3:
                continue
            
            # Skip if it's all caps and short (likely author names or section headers)
            if text.isupper() and word_count < 10:
                continue
            
            # Skip common section headers
            if text.lower() in ['abstract', 'introduction', 'conclusion', 'references']:
                continue
            
            # Calculate score based on heuristics
            score = 0
            
            # Longer titles are more likely (up to a point)
            char_count = len(text)
            if 30 <= char_count <= 200:
                score += 15
            elif 200 < char_count <= 300:
                score += 8
            elif char_count < 30:
                score -= 5  # Penalize very short text
            
            # Prefer titles with 5-20 words
            if 5 <= word_count <= 20:
                score += 15
            elif 3 <= word_count < 5:
                score += 5
            elif word_count > 30:
                score -= 10  # Penalize very long blocks (likely author lists)
            
            # Titles near the top get higher scores
            position_score = max(0, 10 - i * 2)  # Decreases with position
            score += position_score
            
            # Titles often start with capital letters
            if text[0].isupper():
                score += 3
            
            # Titles with colons or subtitles are common
            if ':' in text:
                score += 5
            
            # Penalize text with numbers at the end (likely references or affiliations)
            if re.search(r'\d+\s*$', text):
                score -= 5
            
            # Prefer text that looks like proper title case
            title_case_words = sum(1 for word in text.split() if word and word[0].isupper())
            title_case_ratio = title_case_words / word_count if word_count > 0 else 0
            if 0.5 <= title_case_ratio <= 1.0:
                score += 5
            
            candidates.append({
                'text': text,
                'score': score,
                'position': i,
                'word_count': word_count,
                'char_count': char_count
            })
        
        if not candidates:
            # Fallback: return first non-empty text block
            for block in text_blocks:
                text = block.page_content.strip()
                if text and len(text.split()) >= 3:
                    return text
            return "Untitled Document"
        
        # Select candidate with highest score
        candidates.sort(key=lambda x: (-x['score'], x['position']))
        return candidates[0]['text']
    
    def _detect_sections_node(self, state: ExtractionState) -> ExtractionState:
        """Detect sections using heuristics (includes Title section)."""
        points = state["points"]
        
        sections = self.detector.detect_sections(points)
        state["sections"] = sections
        
        return state
    
    def _compute_stats_node(self, state: ExtractionState) -> ExtractionState:
        """Compute statistics."""
        points = state["points"]
        sections = state["sections"]
        
        # Compute per-section stats
        sections = self.detector.compute_stats(sections, points)
        state["sections"] = sections
        
        # Compute global stats
        total_formulas = sum(p.category == "Formula" for p in points)
        total_tables = sum(p.category == "Table" for p in points)
        total_figures = sum(
            p.category in ("Image", "FigureCaption") for p in points
        )
        total_text_blocks = sum(
            p.category in ("NarrativeText", "CompositeElement") for p in points
        )
        total_pages = max(p.page_number for p in points)
        
        state["global_stats"] = GlobalStats(
            total_formulas=total_formulas,
            total_tables=total_tables,
            total_figures=total_figures,
            total_text_blocks=total_text_blocks,
            total_pages=total_pages,
            total_sections=len(sections)
        )
        
        return state
    
    def _extract_abstract_node(self, state: ExtractionState) -> ExtractionState:
        """Extract abstract using element IDs from abstract section."""
        points = state["points"]
        sections = state["sections"]
        
        # Find abstract section
        abstract_section = None
        for section in sections:
            if section.original_name.lower() == "abstract":
                abstract_section = section
                break
        
        if not abstract_section or not abstract_section.stats.text_block_ids:
            state["abstract"] = ""
            return state
        
        # Get text blocks with matching element IDs
        abstract_element_ids = set(abstract_section.stats.text_block_ids)
        abstract_blocks = []
        
        for point in points:
            if (point.element_id in abstract_element_ids and
                point.category in ("NarrativeText", "CompositeElement")):
                abstract_blocks.append(point)
        
        # Sort by page and y-coordinate
        abstract_blocks.sort(key=lambda p: (
            p.page_number,
            self._get_y_min(p.coordinates) if p.coordinates else 0
        ))
        
        # Combine text
        abstract_text = ' '.join(
            block.page_content.strip()
            for block in abstract_blocks
            if block.page_content.strip()
        )
        
        state["abstract"] = abstract_text
        return state
    
    def _get_y_min(self, coordinates: dict) -> float:
        """Get minimum y coordinate from points."""
        if not coordinates or 'points' not in coordinates:
            return 0.0
        points = coordinates['points']
        if not points:
            return 0.0
        return min(p[1] for p in points)
    
    def _infer_node(self, state: ExtractionState) -> ExtractionState:
        """Run LLM inference."""
        global_stats = state["global_stats"]
        sections = state["sections"]
        
        inference = self.inference_engine.infer(global_stats, sections)
        state["inference"] = inference
        
        return state
    
    def _assemble_node(self, state: ExtractionState) -> ExtractionState:
        """Assemble final metadata."""
        metadata = PaperMetadata(
            document_id=state["document_id"],
            paper_title=state["paper_title"],
            abstract=state["abstract"],
            sections=state["sections"],
            global_stats=state["global_stats"],
            inference=state["inference"]
        )
        
        state["metadata"] = metadata
        return state
    
    def extract(self, document_id: str) -> PaperMetadata:
        """
        Extract metadata for a document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Complete paper metadata
        """
        # Initialize state
        initial_state: ExtractionState = {
            "document_id": document_id,
            "points": [],
            "paper_title": "",
            "abstract": "",
            "sections": [],
            "global_stats": GlobalStats(),
            "inference": None,
            "metadata": None
        }
        
        # Run graph
        final_state = self.graph.invoke(initial_state)
        
        return final_state["metadata"]
