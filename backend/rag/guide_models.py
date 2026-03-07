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
    paper_type: str = Field(default="original_research", description="Type of paper")
    estimated_total_time: str = Field(description="Total estimated time for all passes")


class FinalTask(BaseModel):
    """Final tasks after completing all reading passes."""
    summary_task: str = Field(description="Task to consolidate understanding")
    reflection_questions: List[str] = Field(description="Questions for critical reflection")


class ReadingGuide(BaseModel):
    """Complete Three-Pass Method reading guide for a research paper."""
    paper_title: str = Field(description="Title of the research paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_quick_scan: ReadingPass = Field(description="First pass: quick scan")
    pass2_method_understanding: ReadingPass = Field(description="Second pass: method understanding")
    pass3_deep_analysis: ReadingPass = Field(description="Third pass: deep analysis")
    final_user_task: FinalTask = Field(description="Final consolidation tasks")


class SurveyReadingGuide(BaseModel):
    """Complete Three-Pass Method reading guide for a SURVEY or REVIEW paper."""
    paper_title: str = Field(description="Title of the survey/review paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_field_overview: ReadingPass = Field(description="First pass: field overview and scope")
    pass2_taxonomy_understanding: ReadingPass = Field(description="Second pass: taxonomy and method categories")
    pass3_research_landscape_analysis: ReadingPass = Field(description="Third pass: research landscape, gaps, and future directions")
    final_user_task: FinalTask = Field(description="Final consolidation tasks")


class SystemEngineeringReadingGuide(BaseModel):
    """
    Three-Pass reading guide for SYSTEM_ENGINEERING papers.

    Tailored for papers describing the design and implementation of real-world
    systems — focused on architecture, engineering trade-offs, and deployment.
    """
    paper_title: str = Field(description="Title of the system engineering paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_system_overview: ReadingPass = Field(
        description="First pass: understand the system's purpose, problem, and high-level design"
    )
    pass2_architecture_deep_dive: ReadingPass = Field(
        description="Second pass: understand system components, data flow, and key design decisions"
    )
    pass3_engineering_evaluation: ReadingPass = Field(
        description="Third pass: critically evaluate trade-offs, performance results, and deployment lessons"
    )
    final_user_task: FinalTask = Field(description="Final consolidation tasks")


class TheoreticalReadingGuide(BaseModel):
    """
    Three-Pass reading guide for THEORETICAL papers.

    Tailored for papers presenting mathematical proofs, formal analysis,
    algorithm complexity, or theoretical frameworks.
    """
    paper_title: str = Field(description="Title of the theoretical paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_results_overview: ReadingPass = Field(
        description="First pass: understand what is being proved/analyzed and why it matters"
    )
    pass2_proof_strategy: ReadingPass = Field(
        description="Second pass: follow the mathematical argument, key lemmas, and proof techniques"
    )
    pass3_deep_mathematical_analysis: ReadingPass = Field(
        description="Third pass: verify proofs rigorously, assess assumptions, and connect to broader implications"
    )
    final_user_task: FinalTask = Field(description="Final consolidation tasks")


class BenchmarkDatasetReadingGuide(BaseModel):
    """
    Three-Pass reading guide for BENCHMARK_DATASET papers.

    Tailored for papers introducing a dataset, evaluation framework, or
    benchmark — focused on data quality, methodology, tasks, and baselines.
    """
    paper_title: str = Field(description="Title of the benchmark/dataset paper")
    reading_strategy: ReadingStrategy = Field(description="Overall strategy information")
    pass1_dataset_overview: ReadingPass = Field(
        description="First pass: understand what dataset is introduced, its scope, and intended use cases"
    )
    pass2_methodology_and_tasks: ReadingPass = Field(
        description="Second pass: understand collection process, annotation, benchmark tasks, and metrics"
    )
    pass3_benchmark_analysis: ReadingPass = Field(
        description="Third pass: critically evaluate baseline results, dataset quality, limitations, and gaps"
    )
    final_user_task: FinalTask = Field(description="Final consolidation tasks")
