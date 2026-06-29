# Intelligent Log Analysis Platform

Production-oriented AI log analysis platform for uploading logs, indexing chunks, semantic search, and root-cause investigations.

## Capabilities

- Upload multiple log files and index them automatically.
- Auto-load built-in demo logs when no user logs exist.
- Parse Nginx, Apache-style, PostgreSQL, Redis, Docker, Linux, Kubernetes, Spring Boot, Node.js, and general application logs.
- Generate embeddings and store them in FAISS.
- Ask natural-language questions such as "Why are users getting 502?" or "Why was memory high?"
- Run a LangGraph investigation pipeline: Planner, Search, Root Cause Agent, Summary Agent.
- View incident summary, root cause, recommendations, confidence, and highlighted evidence.
- Collect logs from local Docker containers with `POST /api/v1/docker/{container}`.

## Local Development

Backend defaults to SQLite and deterministic embeddings so it works without external services.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --reload
```

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Docker Compose

```bash
docker compose up --build
```

Frontend: `http://localhost:8080`  
Backend docs: `http://localhost:8000/docs`

Compose runs PostgreSQL, the FastAPI backend, and the Vite-built frontend.

PostgreSQL is exposed only inside the Compose network to avoid conflicts with an existing local database on port `5432`.
If you need host access for debugging, temporarily add a port mapping such as `"5433:5432"` to the `postgres` service.

## Configuration

Important environment variables:

- `DATABASE_URL`: SQLAlchemy async URL. Defaults to local SQLite. Use `postgresql+asyncpg://...` for PostgreSQL.
- `EMBEDDING_PROVIDER`: `deterministic`, `local`, or `openai`.
- `LLM_PROVIDER`: `rule_based` or `openai`.
- `OPENAI_API_KEY`: required only for OpenAI embeddings or chat.
- `AUTO_LOAD_DEMO_DATA`: loads demo logs when the database is empty.
- `ENABLE_DOCKER_LOG_COLLECTION`: enables Docker log ingestion.

## API

- `POST /api/v1/upload`
- `POST /api/v1/index`
- `POST /api/v1/search`
- `POST /api/v1/questions`
- `POST /api/v1/questions/stream`
- `GET /api/v1/history`
- `GET /api/v1/files`
- `GET /api/v1/metrics`
- `POST /api/v1/docker/{container}`

## Tests

```bash
python -m ruff check backend
python -m black --check backend
python -m pytest
cd frontend && npm run build
```
