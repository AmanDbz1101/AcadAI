"""
Pydantic models for structured reading guide generation.
"""

from typing import List
from pydantic import BaseModel, Field


class ReadingStep(BaseModel):
    """A single step in the reading process."""
    step_number: int = Field(description="Sequential step number")
    section_to_read: List[str] = Field(description="List of sections to read in this step")
    objective: str = Field(description="What the reader should achieve in this step")
    questions_to_answer: List[str] = Field(description="Specific questions to guide the reading")
    expected_output: str = Field(description="What understanding or output the reader should have")


class ReadingPass(BaseModel):
    """A reading pass with multiple steps."""
    goal: str = Field(description="Overall goal of this pass")
    estimated_time: str = Field(description="Estimated time for this pass (e.g., '5-10 minutes')")
    steps: List[ReadingStep] = Field(description="Sequential steps for this pass")


class ReadingStrategy(BaseModel):
    """Overall reading strategy metadata."""
    method: str = Field(default="three_pass_method", description="Reading method being used")
    paper_type: str = Field(default="applied", description="Type of paper")
    estimated_total_time: str = Field(description="Total estimated time for all passes")


class FinalTask(BaseModel):
    """Final tasks after completing all reading passes."""
    summary_task: str = Field(description="Task to consolidate understanding")
    reflection_questions: List[str] = Field(description="Questions for critical reflection")


class AppliedReadingGuide(BaseModel):
    """Complete Three-Pass Method reading guide for an APPLIED paper.

    Covers original research, system engineering, benchmark/dataset papers,
    and experimental papers — anything where authors built, implemented, or
    experimentally validated something.
    """
    paper_title: str = Field(description="Title of the research paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_quick_scan: ReadingPass = Field(description="First pass: quick scan — abstract, conclusion, figures, introduction")
    pass2_method_understanding: ReadingPass = Field(description="Second pass: methodology, key figures, evaluation/results setup")
    pass3_deep_analysis: ReadingPass = Field(description="Third pass: equations/algorithms, ablations, limitations")
    final_user_task: FinalTask = Field(description="Final consolidation tasks")


class TheoreticalReadingGuide(BaseModel):
    """Complete Three-Pass Method reading guide for a THEORETICAL paper.

    Covers papers that formally prove or derive something: proofs, theorems,
    lemmas, complexity analysis, convergence analysis, formal methods, and
    mathematical derivations.
    """
    paper_title: str = Field(description="Title of the theoretical paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_quick_scan: ReadingPass = Field(
        description="First pass: abstract, introduction, theorem/lemma statements only — skip all proofs"
    )
    pass2_proof_strategy: ReadingPass = Field(
        description="Second pass: definitions and assumptions, theorem statements with implications, applications/examples"
    )
    pass3_deep_mathematical_analysis: ReadingPass = Field(
        description="Third pass: proof details, complexity analysis, connection to related theoretical work"
    )
    final_user_task: FinalTask = Field(description="Final consolidation tasks")


class SurveyReadingGuide(BaseModel):
    """Complete Three-Pass Method reading guide for a SURVEY paper.

    Covers surveys, reviews, literature reviews, meta-analyses, and overview papers.
    """
    paper_title: str = Field(description="Title of the survey/review paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_field_overview: ReadingPass = Field(
        description="First pass: abstract, introduction, taxonomy/categorization headings, research gaps/future directions"
    )
    pass2_taxonomy_understanding: ReadingPass = Field(
        description="Second pass: taxonomy section in full, key findings per category, comparison tables"
    )
    pass3_research_landscape_analysis: ReadingPass = Field(
        description="Third pass: individual paper summaries for relevant topics, reference list as curated reading list"
    )
    final_user_task: FinalTask = Field(description="Final consolidation tasks")
