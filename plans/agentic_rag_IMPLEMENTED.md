# Agentic RAG System Plan

## ✅ IMPLEMENTATION COMPLETE

### System Overview
A multiagent system for intelligent research paper reading using the three-pass methodology with iterative step execution and memory management.

---

## Architecture

### Two-Agent Design

1. **Planner Agent** (`src/agentic_rag/planner_agent.py`)
   - Generates structured reading guide from paper metadata
   - Uses three-pass methodology (5-10min → 45-90min → 3-5hrs)
   - Includes retrieval hints (categories, sections, element IDs, keywords)
   - Output: AgenticReadingGuide JSON

2. **Executor Agent** (`src/agentic_rag/executor_agent.py`)
   - Processes ONE step at a time (not all at once)
   - Uses tools to retrieve content from Qdrant
   - Synthesizes insights with proper citations (page, section, element ID)
   - Maintains memory of completed steps
   - Saves output after each step
   - Continues iterating until all steps complete

---

## Implementation Details

### ✅ 1. Enhanced Guide Schema (`schemas.py`)

**AgenticReadingStep:**
- `step_id`: Unique identifier (FP-1, SP-2, TP-3)
- `name`: Brief action name (3-7 words)
- `target_sections`: Which sections to read
- `focus_type`: overview | figures_tables | formulas | methodology | results | deep_analysis
- `instruction`: What to do
- `reading_objective`: What to gain from this step
- `retrieval_hints`: Categories, sections, element_ids, search_keywords

**ExecutionSession:**
- Tracks paper_id, document_id, guide, memory, step_outputs
- Status: active | completed | paused
- Persisted to disk after each step

### ✅ 2. Tool Infrastructure (`tools.py`)

**Three Tools:**

1. **document_search(query, document_id, categories, sections, limit)**
   - Semantic search in Qdrant with filters
   - Returns: content + metadata + source (page, category, element_id)

2. **get_element_by_id(element_id, document_id)**
   - Retrieve specific figure/table/formula by ID
   - Returns: element content + coordinates + page

3. **diagram_explainer(element_id, element_type, document_id, context_query)**
   - Analyzes figures/tables/formulas with surrounding context
   - Returns: element + caption + nearby text + analysis

**Tool Schemas:** OpenAI function calling format for LLM

### ✅ 3. Executor Agent with Tool-Calling

**Iterative Execution Loop:**
```python
while next_step = get_next_step(session):
    1. Build memory context (last 3 steps)
    2. Execute step with tools:
       - Call tools based on retrieval hints
       - Retrieve content from Qdrant
       - Synthesize with LLM
    3. Generate StepOutput:
       - insights (detailed paragraph)
       - key_findings (3-5 bullets)
       - sections_covered
       - elements_analyzed (with IDs)
    4. Update session memory:
       - Add StepSummary (compact)
       - Increment completed_count
    5. Save session to disk
    6. Return output
```

**Memory Management:**
- **Short-term**: Last 3 steps in prompt
- **Long-term**: All step summaries (compact)
- **Persistent**: JSON files in `output/agentic_sessions/`

### ✅ 4. API Orchestration (`api.py`)

**Endpoints:**

- `POST /agentic/generate-guide` → Create guide + session
- `POST /agentic/execute-step` → Execute one step
- `GET /agentic/session/{id}` → Status + progress
- `GET /agentic/session/{id}/outputs` → All step outputs
- `GET /agentic/sessions` → List all sessions
- `DELETE /agentic/session/{id}` → Delete session

**Session Management:**
- In-memory cache + disk persistence
- Auto-resume from disk if not in memory
- Stateful execution tracking

### ✅ 5. Integration (`app.py`)

Added agentic router to main FastAPI app:
```python
from src.agentic_rag.api import router as agentic_router
app.include_router(agentic_router)
```

---

## Usage

### Command Line (Test Script)

```bash
# Start API server
python app.py

# Run test workflow (separate terminal)
python test_agentic_rag.py

# List sessions
python test_agentic_rag.py list
```

### API Usage

```bash
# 1. Generate guide
curl -X POST http://localhost:8000/agentic/generate-guide \
  -H "Content-Type: application/json" \
  -d '{
    "metadata_path": "output_Gated Attention_metadata.json",
    "document_id": "2206.01062v1.pdf"
  }'

# 2. Execute first step
curl -X POST http://localhost:8000/agentic/execute-step \
  -H "Content-Type: application/json" \
  -d '{"session_id": "YOUR_SESSION_ID"}'

# 3. Execute next step (iterative)
curl -X POST http://localhost:8000/agentic/execute-step \
  -H "Content-Type: application/json" \
  -d '{"session_id": "YOUR_SESSION_ID"}'

# 4. Check progress
curl http://localhost:8000/agentic/session/YOUR_SESSION_ID
```

---

## Key Features Implemented

✅ **One Step at a Time**: Executor processes steps sequentially, not in batch  
✅ **Memory System**: Compact summaries maintain context across steps  
✅ **Tool-Based Retrieval**: LLM decides which tools to call per step  
✅ **Proper Citations**: All insights include page/section/element_id references  
✅ **Persistent State**: Sessions saved to disk, can resume  
✅ **Progress Tracking**: Real-time status via API  
✅ **Retrieval Hints**: Planner guides executor on what to fetch  
✅ **Three-Pass Methodology**: Structured passes with different focus types  

---

## File Structure

```
src/agentic_rag/
├── __init__.py
├── schemas.py           # Pydantic models for guide, steps, memory, session
├── tools.py             # Three tools + Qdrant integration
├── planner_agent.py     # Guide generation with LLM
├── executor_agent.py    # Step execution with memory + tools
└── api.py               # FastAPI endpoints

test_agentic_rag.py      # Test workflow script
Documentation/
└── AGENTIC_RAG_GUIDE.md # Complete implementation guide
```

---

## Next Steps (Future Enhancements)

1. **Streaming**: Real-time step progress via WebSocket
2. **User Feedback**: Allow corrections mid-execution
3. **Advanced Diagram Analysis**: Integrate specialized chart models
4. **Multi-Paper**: Compare across multiple papers
5. **Annotated PDF**: Generate highlighted PDF with insights
6. **Adaptive Steps**: Adjust detail based on user expertise
