# Voice Agent Monorepo

Production-ready monorepo for a voice agent flow:

1. User records audio in Next.js frontend.
2. Frontend uploads audio to FastAPI backend.
3. Backend stores audio in Supabase Storage (`voice-audio`) and metadata in Postgres.
4. Backend creates a summary request (immediate or scheduled).
5. Worker atomically claims due requests via Supabase RPC.
6. Worker resolves transcript (raw/existing/transcribed), summarizes into 3-5 bullets + next step, emails user via Mailjet Send API v3.1, and updates DB status.

## Repository Layout

- `frontend/` Next.js UI (Vercel-ready)
- `backend/` FastAPI API service
- `worker/` Python background worker
- `infra/` Docker Compose + Supabase SQL schema
- `README.md`
- `.env.example`

## Architecture and Tradeoffs

- Supabase is used for both object storage and relational data to keep ops simple on free tier.
- Worker claiming is done server-side via `claim_due_requests(batch_size int)` with `FOR UPDATE SKIP LOCKED` for reliable multi-worker safety.
- Transcription defaults to `faster-whisper` CPU (`small` model), avoiding paid APIs.
- Summarization is deterministic/extractive (no external LLM dependency), which improves consistency and cost control at the expense of abstractive fluency.
- Logging uses structured JSON with `structlog` + `QueueHandler/QueueListener` in backend and worker to avoid blocking request/job execution.

## Step-by-Step Setup

### 1) Create Supabase project and storage bucket

1. Create a Supabase project.
2. In **Storage**, create bucket `voice-audio`.
3. Recommended: keep bucket **private** (worker/backend access via service-role key).
4. Copy:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

### 2) Apply database schema

1. Open Supabase SQL Editor.
2. Paste and run `infra/supabase_schema.sql`.
3. Confirm tables exist: `audio_assets`, `transcripts`, `summary_requests`, `email_deliveries`.
4. Confirm RPC exists: `claim_due_requests`.

### 3) Fill environment variables

1. Copy `.env.example` to `.env` at repo root.
2. Fill Supabase and Mailjet values.
3. For frontend local dev, either:
   - keep root `.env` and export values manually, or
   - create `frontend/.env.local` with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.

### 4) Run locally

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs on `http://localhost:3000`.

#### Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Runs on `http://localhost:8000`.

#### Worker

```bash
cd worker
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python worker.py
```

#### Docker (backend + worker)

```bash
cd infra
docker compose up --build
```

Frontend is intentionally not dockerized (deploy to Vercel).

### 5) Run tests

#### Backend tests

```bash
cd backend
pytest -q
```

#### Worker tests

```bash
cd worker
pytest -q
```

## API Endpoints

- `GET /healthz`
- `GET /readyz`
- `POST /v1/audio` (multipart file)
- `POST /v1/requests` (`email`, `audio_id`, optional `send_at`)
- `GET /v1/requests/{id}`

Error format:

```json
{
  "error": {
    "code": "...",
    "message": "...",
    "request_id": "..."
  }
}
```

## Deployment

### Frontend on Vercel

1. Import `frontend/` as Vercel project.
2. Set env var:
   - `NEXT_PUBLIC_API_BASE_URL=https://<your-backend-domain>`
3. Deploy.

### Backend + Worker on Render/Railway (Docker)

Create two services from this repo:

1. Backend service
   - Root: `backend`
   - Dockerfile: `backend/Dockerfile`
   - Expose port `8000`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

2. Worker service
   - Root: `worker`
   - Dockerfile: `worker/Dockerfile`
   - Start command: `python worker.py`

Set same env vars (Supabase + Mailjet + worker settings) on both where applicable.

## Troubleshooting

- Microphone permission denied:
  - Check browser microphone permission and HTTPS requirement in production.
- CORS errors:
  - Ensure `CORS_ORIGINS` includes frontend URL (e.g. `https://your-app.vercel.app`).
- Supabase upload fails:
  - Confirm bucket name is exactly `voice-audio` and service role key is correct.
- Mailjet API errors:
  - Verify MAILJET_API_KEY/MAILJET_API_SECRET, sender identity, and Mailjet account restrictions.
  - Use Mailjet Send API keys (API Key + Secret Key), not SMTP credentials.
- Worker not transcribing:
  - First run downloads whisper model files; ensure network access and enough disk.
- Requests stuck in `pending`:
  - Confirm worker is running and RPC `claim_due_requests` exists.
