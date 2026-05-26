# Agentic Planner Backend

A technical reference for the Agentic Planner server: a FastAPI-based travel assistant backend built around a LangGraph-driven agent engine, Redis caching, Supabase authentication, and MongoDB trace persistence.

## What this repository contains

- `main.py` — FastAPI application entrypoint
- `backend/` — database and auth integration utilities
- `agent_file/` — LangGraph workflow, tool bindings, prompt library, and agent orchestration
- `service/` — shared services such as Redis cache and token verification
- `API_DOCUMENTATION.md` — complete endpoint and rate-limit documentation
- `Dockerfile` / `docker-compose.yml` — containerized deployment configuration

## Architecture Overview

### 1. HTTP API Layer

The backend is implemented as a FastAPI app in `main.py`.
- Global CORS support for frontend/API communication
- Rate limiting using `slowapi`
- Structured request validation with Pydantic models from `Schema.py`
- Central `/query` endpoint as the core agent interaction interface
- Health, authentication, conversation, message, preference, and debug trace endpoints

### 2. Authentication & Session Management

Auth is handled through Supabase client wrappers in `backend/supabase_client/`:
- `auth.py` — signup, signin, refresh, and signout flows
- `db_operations.py` — conversation and preference persistence
- Uses Supabase JWT/OAuth for secure access control

User routes require `verify_token` dependency from `service/verify_token.py`.

### 3. Agent Pipeline and LLM Orchestration

The agent workflow lives in `agent_file/agent/agentic_workflow.py`.
- Uses `langchain-groq`, `langchain-openai`, `langgraph`, and `llmops`
- Builds a tool-enabled agent with strict execution control
- Supports streaming and HITL interruption behavior
- Records execution traces and detailed metrics via `llmops.trace_service`
- Includes a low-memory, token-aware prompt strategy that limits history and preserves the latest state

### 4. Tool Integration

The agent is enriched with domain-specific tools:
- `flight_search.py` — flight finding and routing
- `hotel_search.py` — hotel discovery
- `place_search_tool.py` — attractions, restaurants, and local activities
- `weather_info_tool.py` — weather forecast and current conditions
- `railway_search.py` — real-time train schedule lookups

Each tool is annotated with LangChain `@tool` wrappers and bound dynamically during runtime.

### 5. Caching, Tracing, and Persistence

- Redis cache is initialized in `service/cache_service.py`
- MongoDB trace persistence is implemented in `backend/mongo.py`
- Trace retrieval endpoint: `GET /debug/trace/{request_id}`
- The backend optionally falls back from Redis to MongoDB when trace cache misses occur

### 6. Database and Preference Storage

- Supabase acts as the main user and conversation store
- Preferences are maintained per user via `upsert_preference`, `see_preference`, and `remove_preference`
- Conversation history and messages are managed through Supabase controllers

## Environment & Configuration

Required environment variables are defined in `.env.name`:

```text
GROQ_API_KEY=
TAVILY_API_KEY=
OPENWEATHERMAP_API_KEY=
EXCHANGE_RATE_API_KEY=
ANON_KEY=
SERVICE_ROLE_KEY=
SUPABASE_URL=
SERP_API_KEY=
MONGO_URL=
GEMINI_API_KEY=
RAILWAY_RADAR_API_KEY=
```

The project also expects:
- `SUPABASE_URL` and service role credentials
- `MONGO_URL` for MongoDB access
- API keys for Groq, OpenAI, Google Places, weather, exchange rates, SERP, Gemini, and Railway Radar

## Dependency Stack

This project is pinned in `pyproject.toml` and includes:
- `fastapi`
- `uvicorn`
- `langchain`, `langchain-groq`, `langchain-openai`, `langchain-google-community`, `langgraph`
- `pymongo`
- `redis`
- `supabase`
- `slowapi`
- `pydantic`
- `pytest`, `httpx`

## Running Locally

### 1. Install Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> If you use the provided `pyproject.toml`, prefer `uv sync --frozen` with `uv`.

### 2. Start the API server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Verify health endpoint

```bash
curl http://localhost:8000/health
```

## Docker / Container Deployment

Build and run with Docker:

```bash
docker build -t agentic-planner .
docker run -e PORT=10000 -p 10000:10000 agentic-planner
```

Or use the existing `docker-compose.yml` for local orchestration.

## API Documentation

The project ships full API documentation in `API_DOCUMENTATION.md`, including:
- Authentication routes
- Conversation management
- Message retrieval
- Agent query streaming
- Preference management
- Health and trace endpoints

## Development Notes

- The core agent is intended to run as a backend service; the UI is not bundled here.
- `main.py` exposes rate-limited endpoints to protect expensive LLM calls.
- `agent_file/prompt_library` holds system prompt versions and prompt construction logic.
- The backend supports incremental model health tracking and circuit breaker-style resiliency through `query_router` metrics.

## Repository Links

- **GitHub:** https://github.com/Debankur04/Agentic_Planner

## Recommended Next Steps

1. Populate `.env` with production API keys and database URLs.
2. Start Redis and MongoDB before running the backend.
3. Review `API_DOCUMENTATION.md` when integrating a frontend or external client.
4. Monitor `GET /health` and `GET /debug/trace/{request_id}` for operational visibility.
