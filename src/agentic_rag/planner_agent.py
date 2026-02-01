"""
Planner Agent - Generates enhanced reading guides with retrieval hints
Extends existing guide generation with agentic capabilities
"""
import json
import os
from typing import Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from .schemas import (
    AgenticReadingGuide,
    AgenticReadingPass,
    AgenticReadingStep,
    RetrievalHint
)

load_dotenv()


class PlannerAgent:
    """
    Planner Agent generates structured reading guides with retrieval hints.
    Uses three-pass methodology and paper metadata to create actionable steps.
    """
    
    def __init__(self, model: str = "llama-3.3-70b-versatile", temperature: float = 0.1):
        self.llm = ChatGroq(model=model, temperature=temperature)
        self.structured_llm = self.llm.with_structured_output(AgenticReadingGuide)
        
    def generate_guide(self, metadata: Dict[str, Any], document_id: str) -> AgenticReadingGuide:
        """
        Generate an agentic reading guide from paper metadata.
        
        Args:
            metadata: Paper metadata dictionary with structure, stats, and inference
            document_id: Document ID for Qdrant queries
            
        Returns:
            AgenticReadingGuide with retrieval hints for executor agent
        """
        paper_title = metadata['paper_title']
        paper_id = metadata.get('paper_id', document_id)
        global_stats = metadata['global_stats']
        inference = metadata['inference']
        sections = metadata['sections']
        
        # Format sections with statistics for prompt
        sections_formatted = []
        for section in sections:
            sec_name = section['original_name']
            stats = section['stats']
            sections_formatted.append({
                "name": sec_name,
                "figures": stats['figures'],
                "tables": stats['tables'],
                "formulas": stats['formulas'],
                "figure_ids": stats.get('figure_ids', []),
                "table_ids": stats.get('table_ids', []),
                "formula_ids": stats.get('formula_ids', [])
            })
        
        prompt = self._create_prompt()
        chain = prompt | self.structured_llm
        
        result = chain.invoke({
            "paper_title": paper_title,
            "paper_id": paper_id,
            "document_id": document_id,
            "sections": json.dumps(sections_formatted, indent=2),
            "total_pages": global_stats['total_pages'],
            "total_sections": global_stats['total_sections'],
            "total_figures": global_stats['total_figures'],
            "total_tables": global_stats['total_tables'],
            "total_formulas": global_stats['total_formulas'],
            "paper_type": inference['paper_type'],
            "difficulty": inference['difficulty'],
            "math_heavy": inference['math_heavy'],
            "abstract": metadata.get('abstract', '')
        })
        
        return result
    
    def _create_prompt(self) -> ChatPromptTemplate:
        """Create the prompt template for guide generation"""
        return ChatPromptTemplate.from_messages([
            ("system", """You are a research paper reading strategist. Generate a detailed 3-pass reading guide for an executor agent that will retrieve and analyze content.

**Three-Pass Method:**
- **First Pass (5-10 min)**: Quick overview - title, abstract, intro, section headings, conclusion. Skim figures/tables.
- **Second Pass (45-90 min)**: Careful reading - understand main thrust, note figures/tables/formulas. Can skip complex proofs.
- **Third Pass (3-5 hours)**: Deep dive - virtually re-implement the work. Analyze every detail, formula, figure, table.

**Your Task:**
Generate actionable steps with:
1. **Clear instructions**: What specifically to read/analyze
2. **Reading objectives**: What insights to gain
3. **Retrieval hints**: Guide the executor on what to fetch from Qdrant
   - `categories`: NarrativeText (text), FigureCaption (figure descriptions), Table, Formula, Image
   - `sections`: Specific section names to search
   - `element_ids`: Specific figure/table/formula IDs when available
   - `search_keywords`: Key concepts to search for

**Prioritization:**
- First pass: Overview, structure understanding
- Second pass: Focus on sections with high figure/table counts, methodology, results
- Third pass: Deep dive into formulas (if math-heavy), detailed figure analysis, theoretical foundations

**Step Naming:** 3-7 words, action-oriented (e.g., "Read Abstract and Introduction", "Analyze Key Figures")

**Focus Types:**
- overview: Quick scan, structure
- figures_tables: Visual content analysis
- formulas: Mathematical derivations
- methodology: Technical approach
- results: Findings and experiments
- deep_analysis: Detailed re-implementation level

Generate First Pass (3-4 steps), Second Pass (5-7 steps), Third Pass (4-6 steps)."""),
            ("human", """**Paper:** {paper_title}
**Document ID:** {document_id}
**Paper ID:** {paper_id}

**Abstract:** {abstract}

**Structure & Statistics:**
{sections}

**Global Stats:** {total_pages} pages, {total_sections} sections, {total_figures} figures, {total_tables} tables, {total_formulas} formulas

**Classification:** {paper_type}, Difficulty: {difficulty}, Math-heavy: {math_heavy}

Generate the complete agentic reading guide.""")
        ])
    
    def save_guide(self, guide: AgenticReadingGuide, output_path: str) -> None:
        """Save guide to JSON file"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(guide.model_dump(), f, indent=2)
    
    def load_guide(self, guide_path: str) -> AgenticReadingGuide:
        """Load guide from JSON file"""
        with open(guide_path, 'r') as f:
            data = json.load(f)
        return AgenticReadingGuide(**data)


def generate_agentic_guide(metadata_path: str, document_id: str, output_path: str) -> AgenticReadingGuide:
    """
    Convenience function to generate agentic guide from metadata file.
    
    Args:
        metadata_path: Path to metadata JSON file
        document_id: Document ID for Qdrant
        output_path: Where to save the generated guide
        
    Returns:
        Generated AgenticReadingGuide
    """
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    
    planner = PlannerAgent()
    guide = planner.generate_guide(metadata, document_id)
    planner.save_guide(guide, output_path)
    
    return guide


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) != 4:
        print("Usage: python planner_agent.py <metadata_path> <document_id> <output_path>")
        sys.exit(1)
    
    metadata_path = sys.argv[1]
    document_id = sys.argv[2]
    output_path = sys.argv[3]
    
    guide = generate_agentic_guide(metadata_path, document_id, output_path)
    print(f"✓ Generated agentic reading guide: {output_path}")
    print(f"  Total steps: {sum(len(p.steps) for p in guide.passes)}")
