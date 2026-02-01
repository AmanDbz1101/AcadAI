"""
Agentic RAG API Endpoints
Provides orchestration for multiagent reading system
"""
import os
import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import sys

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'agentic_rag'))

from src.agentic_rag.planner_agent import PlannerAgent
from src.agentic_rag.executor_agent import ExecutorAgent
from src.agentic_rag.schemas import (
    AgenticReadingGuide,
    ExecutionSession,
    StepOutput,
    AgentMemory
)

# Initialize router
router = APIRouter(prefix="/agentic", tags=["Agentic RAG"])

# Initialize agents
planner_agent = PlannerAgent()
executor_agent = ExecutorAgent()

# In-memory session storage (replace with Redis/DB in production)
active_sessions: Dict[str, ExecutionSession] = {}


# Request/Response Models
class GenerateGuideRequest(BaseModel):
    """Request to generate reading guide"""
    metadata_path: str = Field(..., description="Path to metadata JSON file")
    document_id: str = Field(..., description="Document ID in Qdrant")
    session_id: Optional[str] = Field(None, description="Optional session ID")


class GenerateGuideResponse(BaseModel):
    """Response with generated guide"""
    session_id: str
    paper_id: str
    total_steps: int
    guide: Dict[str, Any]
    message: str = "Reading guide generated successfully"


class ExecuteStepRequest(BaseModel):
    """Request to execute a single step"""
    session_id: str = Field(..., description="Session ID")
    step_id: Optional[str] = Field(None, description="Specific step ID (None for next step)")


class ExecuteStepResponse(BaseModel):
    """Response from step execution"""
    session_id: str
    step_id: str
    step_name: str
    insights: str
    key_findings: list
    sections_covered: list
    elements_analyzed: list
    progress: str
    next_step_id: Optional[str] = None
    completed: bool = False


class SessionStatusResponse(BaseModel):
    """Session status and progress"""
    session_id: str
    paper_id: str
    status: str
    current_pass: str
    completed_steps: int
    total_steps: int
    progress_percentage: float
    last_updated: str
    completed_step_summaries: list


# Endpoints

@router.post("/generate-guide", response_model=GenerateGuideResponse)
async def generate_reading_guide(request: GenerateGuideRequest):
    """
    Generate an agentic reading guide from paper metadata.
    Initializes a new execution session.
    """
    try:
        # Load metadata
        if not os.path.exists(request.metadata_path):
            raise HTTPException(status_code=404, detail="Metadata file not found")
        
        with open(request.metadata_path, 'r') as f:
            metadata = json.load(f)
        
        # Generate guide
        guide = planner_agent.generate_guide(metadata, request.document_id)
        
        # Initialize session
        session = executor_agent.initialize_session(
            guide=guide,
            document_id=request.document_id,
            session_id=request.session_id
        )
        
        # Store session
        active_sessions[session.session_id] = session
        
        # Save session to disk
        output_dir = os.path.join("output", "agentic_sessions")
        session_path = executor_agent.save_session(session, output_dir)
        
        return GenerateGuideResponse(
            session_id=session.session_id,
            paper_id=session.paper_id,
            total_steps=session.memory.total_steps,
            guide=guide.model_dump()
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate guide: {str(e)}")


@router.post("/execute-step", response_model=ExecuteStepResponse)
async def execute_reading_step(request: ExecuteStepRequest):
    """
    Execute a single reading step.
    Retrieves content, analyzes it, and updates session state.
    """
    try:
        # Get session
        if request.session_id not in active_sessions:
            # Try loading from disk
            session_path = os.path.join("output", "agentic_sessions", f"{request.session_id}.json")
            if os.path.exists(session_path):
                session = executor_agent.load_session(session_path)
                active_sessions[request.session_id] = session
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        
        session = active_sessions[request.session_id]
        
        # Get step to execute
        if request.step_id:
            # Find specific step
            step = None
            for reading_pass in session.guide.passes:
                for s in reading_pass.steps:
                    if s.step_id == request.step_id:
                        step = s
                        break
                if step:
                    break
            
            if not step:
                raise HTTPException(status_code=404, detail="Step not found")
        else:
            # Get next step
            step = executor_agent.get_next_step(session)
            if not step:
                return ExecuteStepResponse(
                    session_id=session.session_id,
                    step_id="",
                    step_name="All steps completed",
                    insights="Reading guide execution completed!",
                    key_findings=["All steps have been executed"],
                    sections_covered=[],
                    elements_analyzed=[],
                    progress=f"{session.memory.completed_count}/{session.memory.total_steps}",
                    completed=True
                )
        
        # Execute step
        step_output = executor_agent.execute_step(session, step)
        
        # Save session
        output_dir = os.path.join("output", "agentic_sessions")
        executor_agent.save_session(session, output_dir)
        
        # Get next step
        next_step = executor_agent.get_next_step(session)
        next_step_id = next_step.step_id if next_step else None
        
        # Check if completed
        all_completed = (next_step is None)
        if all_completed:
            session.status = "completed"
        
        return ExecuteStepResponse(
            session_id=session.session_id,
            step_id=step.step_id,
            step_name=step.name,
            insights=step_output.insights,
            key_findings=step_output.key_findings,
            sections_covered=step_output.sections_covered,
            elements_analyzed=step_output.elements_analyzed,
            progress=f"{session.memory.completed_count}/{session.memory.total_steps}",
            next_step_id=next_step_id,
            completed=all_completed
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute step: {str(e)}")


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """
    Get current status and progress of an execution session.
    """
    try:
        # Get session
        if session_id not in active_sessions:
            session_path = os.path.join("output", "agentic_sessions", f"{session_id}.json")
            if os.path.exists(session_path):
                session = executor_agent.load_session(session_path)
                active_sessions[session_id] = session
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        
        session = active_sessions[session_id]
        memory = session.memory
        
        progress_pct = (memory.completed_count / memory.total_steps * 100) if memory.total_steps > 0 else 0
        
        # Format completed steps
        completed_summaries = []
        for summary in memory.completed_steps:
            completed_summaries.append({
                "step_id": summary.step_id,
                "key_findings": summary.key_findings,
                "sections": summary.sections_covered
            })
        
        return SessionStatusResponse(
            session_id=session.session_id,
            paper_id=session.paper_id,
            status=session.status,
            current_pass=memory.current_pass,
            completed_steps=memory.completed_count,
            total_steps=memory.total_steps,
            progress_percentage=round(progress_pct, 2),
            last_updated=memory.last_updated_at,
            completed_step_summaries=completed_summaries
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session status: {str(e)}")


@router.get("/session/{session_id}/outputs")
async def get_step_outputs(session_id: str):
    """
    Get all step outputs for a session.
    Returns detailed outputs from each completed step.
    """
    try:
        if session_id not in active_sessions:
            session_path = os.path.join("output", "agentic_sessions", f"{session_id}.json")
            if os.path.exists(session_path):
                session = executor_agent.load_session(session_path)
                active_sessions[session_id] = session
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        
        session = active_sessions[session_id]
        
        return {
            "session_id": session.session_id,
            "paper_id": session.paper_id,
            "outputs": session.step_outputs
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get outputs: {str(e)}")


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    Delete an execution session.
    """
    try:
        # Remove from memory
        if session_id in active_sessions:
            del active_sessions[session_id]
        
        # Remove from disk
        session_path = os.path.join("output", "agentic_sessions", f"{session_id}.json")
        if os.path.exists(session_path):
            os.remove(session_path)
        
        return {"message": f"Session {session_id} deleted successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


@router.get("/sessions")
async def list_sessions():
    """
    List all available sessions.
    """
    try:
        sessions_dir = os.path.join("output", "agentic_sessions")
        
        if not os.path.exists(sessions_dir):
            return {"sessions": []}
        
        session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]
        
        sessions_info = []
        for session_file in session_files:
            session_path = os.path.join(sessions_dir, session_file)
            with open(session_path, 'r') as f:
                session_data = json.load(f)
            
            sessions_info.append({
                "session_id": session_data['session_id'],
                "paper_id": session_data['paper_id'],
                "status": session_data['status'],
                "progress": f"{session_data['memory']['completed_count']}/{session_data['memory']['total_steps']}"
            })
        
        return {"sessions": sessions_info}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")
