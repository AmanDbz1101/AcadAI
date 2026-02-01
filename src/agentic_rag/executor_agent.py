"""
Executor Agent - Processes reading guide steps iteratively using tools
Maintains memory and executes one step at a time
"""
import json
import os
from typing import Dict, Any, Optional, List
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from dotenv import load_dotenv
from datetime import datetime

from .schemas import (
    AgenticReadingGuide,
    AgenticReadingStep,
    StepOutput,
    StepSummary,
    AgentMemory,
    ExecutionSession
)
from .tools import AgenticTools

load_dotenv()


class ExecutorAgent:
    """
    Executor Agent processes reading guide steps one at a time.
    Uses tools to retrieve content and generates insights with proper citations.
    """
    
    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.3,
        collection_name: str = "research_papers_main"
    ):
        self.llm = ChatGroq(model=model, temperature=temperature)
        self.tools = AgenticTools(collection_name=collection_name)
        self.conversation_history: List[Any] = []
        
    def initialize_session(
        self,
        guide: AgenticReadingGuide,
        document_id: str,
        session_id: Optional[str] = None
    ) -> ExecutionSession:
        """
        Initialize a new execution session.
        
        Args:
            guide: Reading guide to execute
            document_id: Document ID for Qdrant queries
            session_id: Optional session ID (generated if not provided)
            
        Returns:
            ExecutionSession with initialized state
        """
        if session_id is None:
            session_id = f"{guide.paper_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        total_steps = sum(len(p.steps) for p in guide.passes)
        
        memory = AgentMemory(
            paper_id=guide.paper_id,
            total_steps=total_steps,
            completed_count=0
        )
        
        session = ExecutionSession(
            session_id=session_id,
            paper_id=guide.paper_id,
            document_id=document_id,
            guide=guide,
            memory=memory
        )
        
        return session
    
    def execute_step(
        self,
        session: ExecutionSession,
        step: AgenticReadingStep
    ) -> StepOutput:
        """
        Execute a single reading step using tools and LLM.
        
        Args:
            session: Current execution session
            step: Step to execute
            
        Returns:
            StepOutput with insights and retrieved content
        """
        # Build context from memory
        memory_context = self._build_memory_context(session.memory)
        
        # Build step execution prompt
        prompt = self._create_execution_prompt(step, memory_context)
        
        # Execute with tool calling
        step_output = self._execute_with_tools(
            prompt=prompt,
            step=step,
            document_id=session.document_id
        )
        
        # Update session
        session.step_outputs[step.step_id] = step_output
        session.memory.completed_count += 1
        session.memory.current_step_id = step.step_id
        session.memory.last_updated_at = datetime.now().isoformat()
        
        # Add to memory
        summary = StepSummary(
            step_id=step.step_id,
            key_findings=step_output.key_findings,
            sections_covered=step_output.sections_covered,
            status="completed"
        )
        session.memory.completed_steps.append(summary)
        
        return step_output
    
    def _execute_with_tools(
        self,
        prompt: str,
        step: AgenticReadingStep,
        document_id: str
    ) -> StepOutput:
        """
        Execute step with tool calling capability.
        
        Uses the LLM to decide which tools to call and synthesizes results.
        """
        # System message with tool instructions
        system_msg = """You are an expert research paper reader. Your task is to execute a reading step by:

1. **Retrieve relevant content** using the available tools:
   - `document_search`: Search for content by query, optionally filter by categories/sections
   - `get_element_by_id`: Get specific figures/tables/formulas by ID
   - `diagram_explainer`: Get detailed analysis of visual elements

2. **Analyze the retrieved content** to extract insights relevant to the step objective

3. **Synthesize findings** with proper citations (page numbers, section names, element IDs)

**Output Format:**
- **Insights**: Detailed paragraph explaining what you learned
- **Key Findings**: 3-5 bullet points of main takeaways
- **Sections Covered**: List of section names you read
- **Elements Analyzed**: List of element IDs for figures/tables/formulas

**Citation Format:** Always mention "on page X" or "in Section Y" or "Figure/Table Z (element_id: ...)"

Be thorough but concise. Focus on the step's reading objective."""

        # Prepare retrieval hints
        hints_text = ""
        if step.retrieval_hints:
            hints = step.retrieval_hints
            if hints.categories:
                hints_text += f"\n**Suggested categories:** {', '.join(hints.categories)}"
            if hints.sections:
                hints_text += f"\n**Suggested sections:** {', '.join(hints.sections)}"
            if hints.element_ids:
                hints_text += f"\n**Specific elements:** {', '.join(hints.element_ids[:5])}"
            if hints.search_keywords:
                hints_text += f"\n**Search keywords:** {', '.join(hints.search_keywords)}"
        
        user_msg = f"""{prompt}

**Step Details:**
- **Instruction:** {step.instruction}
- **Objective:** {step.reading_objective}
- **Target Sections:** {', '.join(step.target_sections)}
- **Focus:** {step.focus_type}
{hints_text}

**Document ID:** {document_id}

Now execute this step. First, decide what content to retrieve, then analyze and synthesize your findings."""

        # For now, implement a simplified version without full tool calling
        # In production, you'd use proper tool calling with the LLM
        retrieved_content = []
        
        # Execute retrievals based on hints
        if step.retrieval_hints:
            hints = step.retrieval_hints
            
            # Search with keywords
            if hints.search_keywords:
                for keyword in hints.search_keywords[:3]:  # Limit to 3 searches
                    results = self.tools.document_search(
                        query=keyword,
                        document_id=document_id,
                        categories=hints.categories if hints.categories else None,
                        limit=3
                    )
                    retrieved_content.extend(results)
            
            # Get specific elements
            if hints.element_ids:
                for elem_id in hints.element_ids[:5]:  # Limit to 5 elements
                    elem = self.tools.get_element_by_id(elem_id, document_id)
                    if elem:
                        retrieved_content.append(elem)
            
            # If no specific hints, do a general search
            if not hints.search_keywords and not hints.element_ids:
                query = f"{step.name} {step.instruction}"
                results = self.tools.document_search(
                    query=query,
                    document_id=document_id,
                    categories=hints.categories if hints.categories else None,
                    limit=5
                )
                retrieved_content.extend(results)
        
        # Fallback: search based on step name
        if not retrieved_content:
            results = self.tools.document_search(
                query=step.name,
                document_id=document_id,
                limit=5
            )
            retrieved_content = results
        
        # Synthesize insights using LLM
        full_prompt = user_msg + f"\n\n**Retrieved Content:**\n{json.dumps(retrieved_content[:10], indent=2)}\n\nNow provide your analysis."
        
        synthesis_prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", "{content}")
        ])
        
        chain = synthesis_prompt | self.llm
        response = chain.invoke({"content": full_prompt})
        
        # Parse LLM response into structured output
        insights_text = response.content
        
        # Extract key findings (simple heuristic - look for bullet points)
        key_findings = []
        lines = insights_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                key_findings.append(line.lstrip('-•* '))
        
        # If no bullet points found, create some from first sentences
        if not key_findings:
            sentences = insights_text.split('. ')[:3]
            key_findings = [s.strip() + '.' for s in sentences if s.strip()]
        
        # Extract sections and elements from retrieved content
        sections_covered = list(set(step.target_sections))
        elements_analyzed = []
        for item in retrieved_content:
            if 'metadata' in item:
                elem_id = item['metadata'].get('element_id')
                if elem_id:
                    elements_analyzed.append(elem_id)
        
        elements_analyzed = list(set(elements_analyzed))[:10]  # Limit to 10
        
        return StepOutput(
            step_id=step.step_id,
            content_retrieved=retrieved_content[:20],  # Limit stored content
            insights=insights_text,
            key_findings=key_findings[:5],
            sections_covered=sections_covered,
            elements_analyzed=elements_analyzed
        )
    
    def _build_memory_context(self, memory: AgentMemory) -> str:
        """Build context string from agent memory"""
        if not memory.completed_steps:
            return "This is the first step. No previous context."
        
        context = f"**Progress:** {memory.completed_count}/{memory.total_steps} steps completed\n\n"
        context += "**Previous Steps Summary:**\n"
        
        for summary in memory.completed_steps[-3:]:  # Last 3 steps
            context += f"\n**{summary.step_id}:**\n"
            for finding in summary.key_findings[:2]:  # Top 2 findings
                context += f"  - {finding}\n"
        
        return context
    
    def _create_execution_prompt(self, step: AgenticReadingStep, memory_context: str) -> str:
        """Create prompt for step execution"""
        return f"""**Current Step:** {step.step_id} - {step.name}

**Context from Previous Steps:**
{memory_context}

**Your Task:**
Execute this reading step according to the three-pass methodology."""
    
    def get_next_step(self, session: ExecutionSession) -> Optional[AgenticReadingStep]:
        """
        Get the next step to execute from the guide.
        
        Returns:
            Next uncompleted step, or None if all steps are completed
        """
        for reading_pass in session.guide.passes:
            for step in reading_pass.steps:
                if step.step_id not in session.step_outputs:
                    session.memory.current_pass = reading_pass.pass_id
                    return step
        return None
    
    def save_session(self, session: ExecutionSession, output_dir: str) -> str:
        """
        Save execution session to disk.
        
        Args:
            session: Session to save
            output_dir: Directory to save to
            
        Returns:
            Path to saved session file
        """
        os.makedirs(output_dir, exist_ok=True)
        session_path = os.path.join(output_dir, f"{session.session_id}.json")
        
        with open(session_path, 'w') as f:
            json.dump(session.model_dump(), f, indent=2)
        
        return session_path
    
    def load_session(self, session_path: str) -> ExecutionSession:
        """Load execution session from disk"""
        with open(session_path, 'r') as f:
            data = json.load(f)
        return ExecutionSession(**data)


if __name__ == "__main__":
    print("Executor Agent - Use via API or import as module")
