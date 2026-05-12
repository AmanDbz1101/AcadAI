# Database Setup Guide (New Contributors)

This project uses PostgreSQL for paper storage, section hierarchy, text blocks, tables, figures, and auth data.

## 1. Prerequisites

- macOS with Homebrew
- Python environment for the project
- PostgreSQL client tools (`psql`)

Install PostgreSQL (if not installed):

```bash
brew install postgresql@16
brew services start postgresql@16
```

Verify PostgreSQL is running:

```bash
pg_isready
```

Expected output should include `accepting connections`.

## 2. Create Local Database and User

Use your current system user or create a dedicated DB user.

Option A (quick local setup using default `postgres` user):

```bash
createdb research_agent
```

Option B (dedicated user + database):

```bash
createuser research_agent_user --pwprompt
createdb research_agent -O research_agent_user
```

Confirm DB exists:

```bash
psql -l | grep research_agent
```

## 3. Install Backend Dependencies

From repository root:

```bash
pip install -r requirements.txt
```

If you work only in backend, this also works:

```bash
pip install -r backend/requirements.txt
```

## 4. Configure Environment Variables

Important: this repo currently has two DB env variable styles used by different modules.
To avoid confusion, set both styles in your local environment.

Create a `.env` file at repository root (or export these in your shell):

```env
# Style A (used by ingestion/connection utilities)
DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/research_agent
PG_HOST=localhost
PG_PORT=5432
PG_DB=research_agent
PG_USER=postgres
PG_PASSWORD=

# Style B (used by FastAPI app layer)
POSTGRES_DSN=postgresql://postgres@localhost:5432/research_agent
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=research_agent
POSTGRES_USER=postgres
POSTGRES_PASSWORD=
```

If your local PostgreSQL requires a password, include it in both DSNs.

## 5. Initialize Database Schema

The schema is auto-created when persistence runs (`Base.metadata.create_all(...)`).

Run one ingestion pass to create/verify tables:

```bash
python backend/run.py pdfs/<your-paper>.pdf --store-in-db
```

This will extract content and create required PostgreSQL tables if missing.

## 6. Start API and Verify DB Integration

Start backend API:

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

List papers (after at least one ingestion):

```bash
curl http://127.0.0.1:8000/api/papers
```

## 7. Inspect Stored Data

Use the project helper script to inspect one stored paper and its sections:

```bash
python query_intro.py
```

If no paper is found, ingest a PDF first (Step 5).

## 8. Common Issues

1. Connection refused

- Ensure PostgreSQL service is running: `brew services list | grep postgresql`

2. Authentication failed

- Check user/password in `DATABASE_URL` and `POSTGRES_DSN`

3. Missing tables

- Re-run ingestion with `--store-in-db` to trigger schema creation

4. API says PostgreSQL configuration missing

- Ensure `POSTGRES_DSN` or all of `POSTGRES_HOST/PORT/DB/USER` are set

## 9. Quick Contributor Smoke Test

From repo root:

```bash
pg_isready && \
curl -s http://127.0.0.1:8000/health && \
python query_intro.py
```

If all three commands succeed, your local database setup is good for development.
