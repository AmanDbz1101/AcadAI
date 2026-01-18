"""
LLM-based inference using LangChain + Groq.

This module performs inference on paper type, difficulty, and mathematical content.
It receives aggregated statistics and section information for analysis.
"""

import os
from typing import Dict, Any, List
from langchain_groq import ChatGroq
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from .models import PaperInference, GlobalStats, SectionMetadata


class PaperInferenceEngine:
    """LLM-based inference engine for paper characteristics."""
    
    # Default model to use
    DEFAULT_MODEL = "openai/gpt-oss-120b"
    
    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize inference engine.
        
        Args:
            api_key: Groq API key (defaults to env GROQ_API_KEY)
            model: Model name to use (defaults to openai/gpt-oss-120b)
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment")
        
        self.model_name = model or self.DEFAULT_MODEL
        
        self.llm = ChatGroq(
            api_key=self.api_key,
            model=self.model_name,
            temperature=0.1  # Low temperature for consistent inference
        )
        
        # Initialize output parser
        self.parser = PydanticOutputParser(pydantic_object=PaperInference)
        
        # Create prompt template for inference
        self.inference_prompt = PromptTemplate(
            template="""You are an expert at analyzing research paper metadata to classify papers and assess their properties.

Based on the provided statistics and section structure, infer THREE properties:

1. **paper_type**: Classify the paper into one of these categories:
   - Survey: Comprehensive overview of a research area
   - System: Description of a new system, tool, or implementation
   - Theoretical: Mathematical proofs, formal analysis, theoretical foundations
   - Empirical: Data-driven analysis, user studies, experiments with real-world data
   - Experimental: Controlled experiments, benchmarking, performance evaluation
   - Position Paper: Opinion piece, vision statement, or position on an issue
   - Tool Paper: Presentation of a new tool or software
   - Case Study: Detailed analysis of a specific case or application
   - Other: If none of the above categories fit

2. **difficulty**: Reading difficulty level (easy, medium, hard):
   - Easy: Few formulas (<5), shallow structure (max depth ≤2), many figures, accessible content
   - Medium: Moderate formulas (5-15), moderate depth (2-3 levels), balanced content
   - Hard: Many formulas (>15 or >2 per page), deep structure (>3 levels), heavy mathematical content

3. **math_heavy**: Whether the paper is mathematically intensive (true/false):
   - True if: High formula density (>2 per page) OR formula ratio > 0.4 OR total formulas > 20
   - False otherwise

## Paper Statistics

{stats_summary}

## Classification Guidelines

**Paper Type:**
- Look at section names: "Related Work" or "Survey" → Survey; "Implementation", "Architecture" → System
- High formula count + theoretical sections → Theoretical
- "Experiments", "Evaluation", "Results" with data → Empirical/Experimental
- "Case Study" in sections → Case Study

**Difficulty:**
- Consider formula density, section depth, and figure-to-formula ratio
- Many figures often indicate easier, more visual papers
- Deep nesting and many formulas indicate harder papers

**Math Heavy:**
- CalculaPaperInference:
        
        Infer paper characteristics from statistics.
        
        Args:
            global_stats: Global document statistics
            sections: List of section metadata
            
        Returns:
            Paper inference result with paper_type, difficulty, and math_heavy
{format_instructions}""",
            input_variables=["stats_summary"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            }
        )
        
        # Create chain
        self.inference_chain = self.inference_prompt | self.llm | self.parser
    
    def infer(
        self,
        global_stats: GlobalStats,
        sections: list[SectionMetadata]
    ) -> PaperInference:
        """
        Infer paper characteristics from statistics.
        
        Args:
            global_stats: Global document statistics
            sections: List of section metadata
            
        Returns:
            Inference result
        """
        # Build statistical summary
        stats_dict = self._build_stats_summary(global_stats, sections)
        
        # Format stats as readable text
        stats_summary = self._format_stats_for_prompt(stats_dict)
        
        try:
            # Invoke chain with template
            result = self.inference_chain.invoke({
                "stats_summary": stats_summary
            })
            return result
            
        except Exception as e:
            # Fallback to heuristic defaults
            print(f"LLM inference failed: {e}")
            return self._fallback_inference(global_stats, sections)
    
    def _build_stats_summary(
        self,
        global_stats: GlobalStats,
        sections: list[SectionMetadata]
    ) -> Dict[str, Any]:
        """Build statistical summary for LLM."""
        # Calculate ratios and distributions
        total_elements = (
            global_stats.total_formulas +
            global_stats.total_tables +
            global_stats.total_figures
        )
        
        formula_ratio = (
            global_stats.total_formulas / max(total_elements, 1)
        )
        
        # Detect special sections
        has_appendix = any(
            'appendix' in s.original_name.lower()
            for s in sections
        )
        
        # Calculate section depth
        max_level = max((s.level for s in sections), default=1)
        
        # Formula density (formulas per page)
        formula_density = (
            global_stats.total_formulas / max(global_stats.total_pages, 1)
        )
        
        # Section-level stats for LLM
        section_stats = [
            {
                "section_name": s.original_name,
                "level": s.level,
                "formulas": s.stats.formulas,
                "tables": s.stats.tables,
                "figures": s.stats.figures,
                "text_blocks": s.stats.text_blocks
            }
            for s in sections[:10]  # Top 10 sections
        ]
        
        return {
            "total_sections": global_stats.total_sections,
            "total_formulas": global_stats.total_formulas,
            "total_tables": global_stats.total_tables,
            "total_figures": global_stats.total_figures,
            "total_pages": global_stats.total_pages,
            "total_text_blocks": global_stats.total_text_blocks,
            "formula_ratio": formula_ratio,
            "formula_density": formula_density,
            "max_section_depth": max_level,
            "has_appendix": has_appendix,
            "section_stats": section_stats
        }
    
    def _format_stats_for_prompt(self, stats: Dict[str, Any]) -> str:
        """Format statistics dictionary as readable text for prompt."""
        lines = []
        
        # Global stats
        lines.append("Global Statistics:")
        lines.append(f"- Total Sections: {stats['total_sections']}")
        lines.append(f"- Total Formulas: {stats['total_formulas']}")
        lines.append(f"- Total Tables: {stats['total_tables']}")
        lines.append(f"- Total Figures: {stats['total_figures']}")
        lines.append(f"- Total Pages: {stats['total_pages']}")
        lines.append(f"- Total Text Blocks: {stats['total_text_blocks']}")
        lines.append(f"- Formula Ratio: {stats['formula_ratio']:.2f} (formulas / total visual elements)")
        lines.append(f"- Formula Density: {stats['formula_density']:.2f} formulas per page")
        lines.append(f"- Max Section Depth: {stats['max_section_depth']}")
        lines.append(f"- Has Appendix: {stats['has_appendix']}")
        
        # Section names for context
        if stats['section_stats']:
            lines.append(f"\nTotal Detected Sections: {len(stats['section_stats'])}")
            lines.append("\nSection Structure (showing hierarchy and content distribution):")
            for i, section in enumerate(stats['section_stats'], 1):
                indent = "  " * (section['level'] - 1)
                lines.append(
                    f"{indent}{section['section_name']}: "
                    f"{section['formulas']} formulas, {section['tables']} tables, "
                    f"{section['figures']} figures, {section['text_blocks']} text blocks"
                )
        
        return "\n".join(lines)
    
    def _fallback_inference(
        self,
        global_stats: GlobalStats,
        sections: list[SectionMetadata]
    ) -> PaperInference:
        """Heuristic fallback when LLM fails."""
        # Calculate formula density
        formula_density = (
            global_stats.total_formulas / max(global_stats.total_pages, 1)
        )
        
        # Determine math_heavy
        math_heavy = formula_density > 2.0 or (
            global_stats.total_formulas > 20
        )
        
        # Determine difficulty
        max_level = max((s.level for s in sections), default=1)
        has_appendix = any(
            'appendix' in s.original_name.lower()
            for s in sections
        )
        
        if math_heavy and max_level > 3 and has_appendix:
            difficulty = "hard"
        elif formula_density < 1.0 and max_level <= 2:
            difficulty = "easy"
        else:
            difficulty = "medium"
        
        # Determine paper type based on section names
        section_names_lower = [s.original_name.lower() for s in sections]
        
        if any('survey' in name or 'related work' in name for name in section_names_lower):
            paper_type = "Survey"
        elif any('implementation' in name or 'architecture' in name or 'system' in name for name in section_names_lower):
            paper_type = "System"
        elif any('theorem' in name or 'proof' in name for name in section_names_lower) or math_heavy:
            paper_type = "Theoretical"
        elif any('experiment' in name or 'evaluation' in name for name in section_names_lower):
            paper_type = "Experimental"
        elif any('case study' in name for name in section_names_lower):
            paper_type = "Case Study"
        else:
            paper_type = "Other"
        
        return PaperInference(
            paper_type=paper_type,
            math_heavy=math_heavy,
            difficulty=difficulty
        )
        
