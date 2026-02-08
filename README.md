# Voice Summary Agent

## Overview
Voice Summary Agent is a monorepo application that captures short voice notes, processes them asynchronously, and emails a concise summary to the user.

Core flow:
1. User records audio in the web app.
2. Frontend uploads the file to the API.
3. API stores audio metadata and creates a processing request.
4. Worker claims due requests, transcribes audio, generates a summary, and sends email.
5. Request status is available via polling endpoint.

## What Is Used

### Languages and Frameworks
- TypeScript + React + Next.js (frontend)
- Python + FastAPI (backend)
- Python worker process (background jobs)

### Data and Infrastructure
- Supabase Postgres for relational data
- Supabase Storage for audio files
- Supabase RPC (`claim_due_requests`) for safe multi-worker claim logic

### Processing and Delivery
- `faster-whisper` for speech-to-text
- Deterministic summarizer (3-5 bullets + next step)
- Mailjet Send API v3.1 for outbound email

### Operational Tooling
- Docker and Docker Compose for service orchestration
- `structlog` JSON logging for backend and worker
- Pytest test suites for backend and worker modules

## Services and Apps

### Frontend (`frontend/`)
- Next.js application for:
  - microphone recording
  - previewing recorded audio
  - submitting summary requests
  - polling request status and rendering summary state

### Backend API (`backend/`)
- FastAPI service exposing:
  - health/readiness endpoints
  - audio upload endpoint
  - summary request creation endpoint
  - request status retrieval endpoint
- Persists audio metadata and request records in Supabase.

### Worker (`worker/`)
- Background processor that:
  - atomically claims pending/due requests
  - resolves transcript (existing/raw/new transcription)
  - generates summary payload
  - sends summary email
  - writes success/failure state back to database

### Infra (`infra/`)
- `docker-compose.yml` for backend + worker runtime
- `supabase_schema.sql` with tables and RPC function

## Repository Layout
- `frontend/` web app
- `backend/` API service
- `worker/` async processing service
- `infra/` compose + SQL schema
- `.env.example` sample environment contract

## How to Run
This section assumes required environment variables are already set.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Runs at `http://localhost:3000`.

### Backend
```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Runs at `http://localhost:8000`.

### Worker
```bash
cd worker
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python worker.py
```

### Docker (backend + worker)
```bash
cd infra
docker compose up --build
```

## API Surface
- `GET /healthz`
- `GET /readyz`
- `POST /v1/audio`
- `POST /v1/requests`
- `GET /v1/requests/{id}`

Standard error shape:
```json
{
  "error": {
    "code": "...",
    "message": "...",
    "request_id": "..."
  }
}
```
