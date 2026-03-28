# Run Frontend and Backend (Local)

This quick guide matches your current project setup and verified commands.

## 1) Prerequisites

- Python venv available at venv/
- Node.js and npm installed (v24.5.0 and 11.5.1 verified)
- Frontend dependencies installed in frontend/node_modules

Check versions:

```bash
node -v
npm -v
venv/bin/python -V
```

## 2) Install dependencies

Backend (if needed):

```bash
venv/bin/python -m pip install -r requirements.txt
```

Frontend:

```bash
cd frontend
npm install
cd ..
```

## 3) Run backend

```bash
venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001 --reload
```

Health check:

```bash
curl http://127.0.0.1:8001/health
```

## 4) Run frontend

In a second terminal:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 8080
```

Open:

- Frontend: http://127.0.0.1:8080
- Backend health: http://127.0.0.1:8001/health

## 5) Stop services

- In each running terminal, press Ctrl+C

## Notes

- If backend startup fails with syntax errors in backend/api/app.py, check for accidental merge markers (`<<<<<<<`, `=======`, `>>>>>>>`) and remove them.
- If frontend fails due missing packages, rerun npm install in frontend/.
- Python environment: 3.14.0
- Node.js environment verified on 3/26/2026
