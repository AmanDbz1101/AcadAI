# Agentic RAG System

A multiagent system for intelligent research paper reading using iterative step execution with memory and tool-based retrieval.

## Quick Start

1. **Install dependencies** (if not already installed):
```bash
pip install langchain-groq qdrant-client fastapi uvicorn pydantic
```

2. **Start API server**:
```bash
python app.py
```

3. **Run test workflow** (in separate terminal):
```bash
python test_agentic_rag.py
```

## What It Does

### Planner Agent
- Generates structured 3-pass reading guide from paper metadata
- Includes retrieval hints for each step (what to search, where to look)
- Uses three-pass methodology: Overview → Thorough → Deep dive

### Executor Agent
- Executes guide steps **one at a time** (iterative, not batch)
- Retrieves content from Qdrant using tools
- Synthesizes insights with proper citations (page, section, element ID)
- Maintains memory of completed steps
- Saves progress after each step

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agentic/generate-guide` | POST | Generate reading guide |
| `/agentic/execute-step` | POST | Execute one step |
| `/agentic/session/{id}` | GET | Get progress status |
| `/agentic/session/{id}/outputs` | GET | Get all outputs |
| `/agentic/sessions` | GET | List all sessions |
| `/agentic/session/{id}` | DELETE | Delete session |

## Example Usage

```python
import requests

# 1. Generate guide
response = requests.post(
    "http://localhost:8000/agentic/generate-guide",
    json={
        "metadata_path": "output_Gated Attention_metadata.json",
        "document_id": "2206.01062v1.pdf"
    }
)
session_id = response.json()["session_id"]

# 2. Execute first step
response = requests.post(
    "http://localhost:8000/agentic/execute-step",
    json={"session_id": session_id}
)
print(response.json()["insights"])

# 3. Execute next step
response = requests.post(
    "http://localhost:8000/agentic/execute-step",
    json={"session_id": session_id}
)
# Continue until all steps completed...
```

## Tools Available

1. **document_search**: Semantic search with category/section filters
2. **get_element_by_id**: Retrieve specific figures/tables/formulas
3. **diagram_explainer**: Analyze visual elements with context

## Memory System

- **Short-term**: Last 3 steps in LLM context
- **Long-term**: Compact summaries of all steps
- **Persistent**: JSON files in `output/agentic_sessions/`

## File Structure

```
src/agentic_rag/
├── schemas.py           # Data models
├── tools.py             # Retrieval tools
├── planner_agent.py     # Guide generation
├── executor_agent.py    # Step execution
└── api.py               # API endpoints

test_agentic_rag.py      # Test script
Documentation/AGENTIC_RAG_GUIDE.md  # Full guide
```

## Documentation

- **Full Guide**: [Documentation/AGENTIC_RAG_GUIDE.md](Documentation/AGENTIC_RAG_GUIDE.md)
- **Plan**: [plans/agentic_rag_IMPLEMENTED.md](plans/agentic_rag_IMPLEMENTED.md)

## Key Features

✅ Iterative step-by-step execution  
✅ Memory-based context maintenance  
✅ Tool-based content retrieval  
✅ Proper source citations  
✅ Persistent session storage  
✅ Progress tracking API  
✅ Three-pass methodology  
