"""
Schemas for Agentic RAG System
Enhanced reading guide with retrieval hints for executor agent
"""
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
from datetime import datetime


class RetrievalHint(BaseModel):
    """Hints for what content to retrieve for this step"""
    categories: List[str] = Field(
        default_factory=list,
        description="Qdrant categories to focus on: NarrativeText, Table, FigureCaption, Formula, etc."
    )
    sections: List[str] = Field(
        default_factory=list,
        description="Section names to search within"
    )
    element_ids: List[str] = Field(
        default_factory=list,
        description="Specific element IDs to fetch (from metadata)"
    )
    search_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords/phrases to guide semantic search"
    )


class AgenticReadingStep(BaseModel):
    """Enhanced step with retrieval hints for executor agent"""
    step_id: str = Field(..., description="Step ID: FP-1, SP-2, TP-3")
    name: str = Field(..., description="Step name (3-7 words)")
    target_sections: List[str] = Field(..., description="Sections to focus on")
    focus_type: Literal["overview", "figures_tables", "formulas", "methodology", "results", "deep_analysis"]
    instruction: str = Field(..., description="What to do in this step")
    reading_objective: str = Field(..., description="What to learn/understand from this step")
    retrieval_hints: RetrievalHint = Field(
        default_factory=RetrievalHint,
        description="Hints for content retrieval"
    )
    completed: bool = Field(default=False, description="Execution status")


class AgenticReadingPass(BaseModel):
    """Enhanced pass for agentic execution"""
    pass_id: Literal["first_pass", "second_pass", "third_pass"]
    pass_name: str
    objective: str
    estimated_time_minutes: int
    steps: List[AgenticReadingStep]


class AgenticReadingGuide(BaseModel):
    """Complete agentic reading guide"""
    paper_id: str
    reading_strategy: str = "three-pass-agentic"
    passes: List[AgenticReadingPass]
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StepOutput(BaseModel):
    """Output from executing a single reading step"""
    step_id: str
    content_retrieved: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Retrieved content with sources"
    )
    insights: str = Field(..., description="Synthesized insights from this step")
    key_findings: List[str] = Field(
        default_factory=list,
        description="Bullet points of main findings"
    )
    sections_covered: List[str] = Field(
        default_factory=list,
        description="Which sections were actually read"
    )
    elements_analyzed: List[str] = Field(
        default_factory=list,
        description="IDs of figures/tables/formulas analyzed"
    )
    completed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StepSummary(BaseModel):
    """Compact summary for agent memory"""
    step_id: str
    key_findings: List[str]
    sections_covered: List[str]
    status: Literal["completed", "in-progress", "pending"] = "completed"


class AgentMemory(BaseModel):
    """Memory state for executor agent"""
    paper_id: str
    current_step_id: Optional[str] = None
    completed_steps: List[StepSummary] = Field(default_factory=list)
    current_pass: Literal["first_pass", "second_pass", "third_pass"] = "first_pass"
    total_steps: int = 0
    completed_count: int = 0
    session_started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ExecutionSession(BaseModel):
    """Complete execution session state"""
    session_id: str
    paper_id: str
    document_id: str  # For Qdrant queries
    collection_name: str = "research_papers_main"
    guide: AgenticReadingGuide
    memory: AgentMemory
    step_outputs: Dict[str, StepOutput] = Field(default_factory=dict)
    status: Literal["active", "completed", "paused"] = "active"
