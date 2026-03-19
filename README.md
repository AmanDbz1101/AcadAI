# ResearchAgent

ResearchAgent is a full-stack research paper workflow that:

- extracts structured paper data from PDFs (Docling + Groq-assisted metadata),
- stores extracted artifacts in PostgreSQL with deduplication,
- serves stored data through a backend API,
- renders papers and extracted insights in a React frontend.

## What This Project Does

Given a PDF, the extraction pipeline produces and stores:

- paper metadata (title, abstract, inferred properties),
- section hierarchy,
- text blocks,
- tables,
- images (PNG assets + metadata),
- full text and JSON outputs for downstream use.

Data is persisted in PostgreSQL and linked to a single paper record so you can fetch content by paper whenever needed.

## Architecture

### Backend

- Extraction pipeline: `backend/extraction/`
- Persistence layer: `backend/extraction/persistence/`
- API server: `backend/api/app.py`

### Frontend

- React + Vite app: `frontend/`
- Calls backend endpoints to list papers and fetch paper bundles.

### Database

- PostgreSQL
- Main dedup rule: skip duplicate paper by `pdf_hash` or case-insensitive `paper_name`.

## Backend API Endpoints

Base URL (local): `http://127.0.0.1:8000`

- `GET /health`
  - Service and database health.
- `GET /api/papers`
  - List stored papers.
- `GET /api/papers/{paper_id}/bundle`
  - Returns paper + sections + text blocks + tables + images.

## Prerequisites

- Python 3.12+
- Node.js + npm
- PostgreSQL 14+
- macOS/Linux shell

## 1. Environment Setup

From project root:

```bash
# Create venv (if not already created)
python3.12 -m venv .venv

# Activate
source .venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

## 2. PostgreSQL Setup

Create database (one-time):

```bash
createdb research_agent
```

If `createdb` is not available, use your PostgreSQL tooling (`psql`, pgAdmin, Docker, etc.) to create the same DB.

## 3. `.env` Configuration

Create/update `.env` at the project root.

Minimum recommended keys:

```env
# Required for Groq-based metadata/inference
GROQ_API_KEY=your_groq_api_key

# Required for PostgreSQL persistence
POSTGRES_DSN=postgresql://<user>:<password>@localhost:5432/research_agent

# Optional (for frontend if different backend URL)
# VITE_API_BASE_URL=http://127.0.0.1:8000

# Optional existing integrations
QDRANT_URL=...
QDRANT_API_KEY=...
QDRANT_COLLECTION_NAME=research_papers
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=ResearchAgent
```

Notes:

- Do not commit real secrets.
- If your PostgreSQL user has no password locally, DSN can be:
  `postgresql://<user>@localhost:5432/research_agent`

## 4. Run Extraction (Populate Database)

Run extraction on a paper:

```bash
POSTGRES_DSN=postgresql://<user>:<password>@localhost:5432/research_agent \
PYTHONPATH=$(pwd) \
.venv/bin/python backend/extraction/extraction.py input/attention.pdf
```

This will:

- generate JSON/TXT outputs in `input/`,
- export image assets to `output/images/<paper_name>/`,
- persist paper + linked sections/text blocks/tables/images to PostgreSQL.

## 5. Run Backend API

```bash
POSTGRES_DSN=postgresql://<user>:<password>@localhost:5432/research_agent \
PYTHONPATH=$(pwd) \
.venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/papers
```

## 6. Run Frontend

In a new terminal:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 8080
```

Open:

- Frontend: `http://127.0.0.1:8080`
- Backend API: `http://127.0.0.1:8000`

## Frontend Behavior

The frontend now fetches real backend data:

- loads paper list from `/api/papers`,
- loads selected paper from `/api/papers/{id}/bundle`,
- renders real sections in the center viewer,
- shows extracted figures/tables in the right panel.

## Database Model (Persistence Layer)

Core tables created automatically by persistence code include:

- `papers`
- `sections`
- `text_blocks`
- `tables_data`
- `images`
- link tables: `section_text_blocks`, `section_tables`, `section_images`

This design is extensible. Adding formulas follows the same pattern:

1. create a `formulas` table,
2. create `section_formulas` link table,
3. add insert/query methods in persistence store,
4. expose through API and frontend as needed.

## Common Workflows

### Ingest a new paper

1. Place PDF in `input/`
2. Run extraction command
3. Verify `GET /api/papers`

### Fetch stored data for one paper

Use:

- `GET /api/papers`
- `GET /api/papers/{paper_id}/bundle`

### Query via CLI helper

```bash
POSTGRES_DSN=postgresql://<user>:<password>@localhost:5432/research_agent \
PYTHONPATH=$(pwd) \
.venv/bin/python backend/extraction/persistence/query_paper.py "Attention Is All You Need" --summary
```

## Troubleshooting

- `database "research_agent" does not exist`
  - Create it: `createdb research_agent`

- `psycopg2` missing
  - Install dependencies: `pip install -r requirements.txt`

- Frontend cannot load data
  - Ensure backend is running on port 8000
  - Set `VITE_API_BASE_URL` if backend URL differs

- `RequestsDependencyWarning` (urllib3/chardet/charset_normalizer)
  - Non-fatal warning; project still runs.

## Repository Layout (Key Paths)

- `backend/api/app.py` - FastAPI server for frontend
- `backend/extraction/extraction.py` - extraction orchestrator
- `backend/extraction/app/metadata_extractor.py` - Docling/Groq metadata extraction
- `backend/extraction/persistence/postgres_store.py` - PostgreSQL schema + CRUD
- `backend/extraction/persistence/query_paper.py` - CLI query helper
- `frontend/src/pages/Index.tsx` - main frontend page wiring
- `frontend/src/lib/api.ts` - frontend API client
