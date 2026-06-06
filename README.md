
# Agentic Planner

**A production-grade AI travel planning backend powered by a multi-agent LangGraph pipeline, LLMOps control plane, and autonomous tool orchestration.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Latest-FF6B35?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![Redis](https://img.shields.io/badge/Redis-Cache%20%26%20Tracing-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![Supabase](https://img.shields.io/badge/Supabase-Auth%20%26%20Persistence-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)

[Architecture](#architecture) · [Multi-Agent System](#multi-agent-system) · [API Reference](#api-reference) · [Setup](#setup) · [Deployment](#deployment)

---

## Overview

Agentic Planner is a backend service for an AI-powered travel planning assistant. It replaces the traditional single-agent approach with a **three-phase multi-agent orchestration pipeline** — each agent specializes in one domain (intake, research, writing) and communicates through a shared state hub with full audit tracing.

Beyond the agent layer, the system implements a production LLMOps control plane with cost-aware model routing, per-user token budgets, circuit-breaker failover, structured execution tracing, and input/output guardrails — built to scale to thousands of concurrent users.

---

## Key Features

- **Multi-Agent Orchestration** — Three specialized agents run sequentially, passing structured state through a JSON communication hub with 45+ traced event types per workflow
- **Cost-Aware Model Router** — Dynamic LLM selection across Groq LLaMA 3.3-70B, Gemini Flash, Mistral Medium, and GPT OSS-120B with per-node routing configuration, circuit breakers, and automatic fallback chains
- **Human-in-the-Loop (HITL)** — LangGraph `MemorySaver` checkpoints freeze graph execution mid-run when the agent needs user clarification, resuming seamlessly on the same conversation thread
- **SSE Streaming** — A custom `QueueCallbackHandler` pushes LLM tokens to an `asyncio.Queue` and streams them to clients via Server-Sent Events
- **Per-User Token Budgeting** — Redis-backed daily cost tracking per user tier (Pirate / Warlord / Emperor) with anomaly alerting at 3× average spend
- **Execution Tracing** — Full request-scoped trace stored in Redis (24h TTL) with MongoDB fallback, retrievable via a debug endpoint
- **Input/Output Guardrails** — Three-layer input defence (blocklist, PII masking, injection detection) and JSON-schema output validation with hallucination heuristics
- **Rate Limiting** — `slowapi` middleware with per-endpoint limits; auth endpoints strictly limited to prevent brute-force
- **Containerized Deployment** — Dockerfile + docker-compose for local orchestration and cloud deployment

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     CLIENT / FRONTEND                         │
└───────────────────────────┬───────────────────────────────────┘
                            │  HTTPS + SSE (streaming)
┌───────────────────────────▼───────────────────────────────────┐
│              FastAPI Gateway  (main.py)                       │
│  Auth middleware · Rate limiter (slowapi) · Request ID        │
│  Input sanitizer · Schema validator · Budget gate             │
└────────────────────────────┬──────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────┐
│                   LLMOps Control Plane                        │
│                                                               │
│   Model Router ──── Prompt Registry ──── Token Tracker        │
│   (cost/latency)    (versioned)          (Redis quotas)       │
│                                                               │
│              Observability Bus (structured logs)              │
└────────────────────────────┬──────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────┐
│             Multi-Agent Execution Engine                      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Phase 1     │  │  Phase 2     │  │  Phase 3     │         │
│  │  Intake      │→ │  Research &  │→ │  Writer      │         │
│  │  Validator   │  │  Pricing     │  │  Agent       │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         └─────────────────┼─────────────────┘                 │
│                           ▼                                   │
│              CommunicationManager (target.js)                 │
│              TraceRecorder (45+ event types)                  │
└────────────────────────────┬──────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────┐
│                    Tool Ecosystem                             │
│  Flights · Hotels · Weather · Places · Railways               │
└────────────────────────────┬──────────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────────┐
│              Data & Persistence Layer                         │
│  Supabase (auth, conversations, preferences, memory)          │
│  Redis (cache, tracing, token budgets)                        │
│  MongoDB (trace fallback, long-term audit logs)               │
└───────────────────────────────────────────────────────────────┘
```

---

## Multi-Agent System

The core of the system is a **three-phase agentic pipeline** where each agent specializes in a distinct domain and passes structured data forward through a shared JSON state file (`target.js`).

```
User Query
    ↓
Phase 1 — Intake Validator
    ├─ Validates completeness and extracts requirements
    ├─ Calculates confidence score; requests clarification if < threshold
    ├─ Constructs initial trip plan
    └─ Writes structured output → target.js

Phase 2 — Research & Pricing Agent
    ├─ Reads initial plan from target.js
    ├─ Executes tool calls (flights, hotels, weather, places, rail)
    ├─ Cross-references sources and builds pricing summary
    ├─ Logs every tool call, cache hit, and decision to trace
    └─ Appends research results → target.js

Phase 3 — Writer Agent
    ├─ Reads full research from target.js
    ├─ Synthesizes and formats the final itinerary
    ├─ Validates output quality (word count, hallucination heuristics)
    ├─ Deletes target.js (automatic cleanup)
    └─ Returns final_output + complete trace logs

Result → { status, final_output, phases, trace, workflow_summary }
```

### Agent Communication

Agents communicate via a structured JSON file that is created at workflow start and deleted on completion. Every phase reads the previous phase's output and appends its own:

```json
{
  "workflow_id": "uuid",
  "intake_validation": { "status": "completed", "initial_plan": {}, "trace_logs": [] },
  "research_pricing":  { "status": "completed", "research_results": {}, "pricing_summary": {} },
  "writing":           { "status": "completed", "final_output": "..." }
}
```

### Tracing

Every agent action is recorded by `TraceRecorder` with 45+ event types including `llm_invoked`, `tool_called`, `tool_cache_hit`, `decision`, `clarification_needed`, `cleanup_completed`, and more. The full trace is returned alongside the result and stored in Redis for debugging.

```python
# Access the complete trace
result = engine.process_with_multi_agents(user_input="...", user_id="...")
trace = result["trace"]

print(f"Total events : {trace['total_events']}")
print(f"Total time   : {trace['total_duration_ms']}ms")
print(f"By agent     : {trace['events_by_agent']}")
```

---

## LLMOps Control Plane

### Model Router

The `ModelRouter` selects the optimal LLM for each pipeline node based on intent complexity, live latency percentiles, and circuit-breaker state.

| Node | Primary Model | Fallback |
|---|---|---|
| Intake | `mistral-medium-latest` | LLaMA 3.3-70B |
| Research | `llama-3.3-70b-versatile` | Mistral Medium |
| Validator | `llama-3.3-70b-versatile` | Mistral Medium |
| Writer | `gpt-oss-120b:free` | Mistral Medium |
| Memory | `llama-3.1-8b-instant` | Mistral Medium |

Circuit breakers open after >5% error rate and cool down for 60 seconds. The fallback chain for the top-level router is `groq_llama → groq_fast → gemini`.

### Token & Cost Budgeting

Daily spend is tracked per user in Redis with keys expiring at midnight UTC. Each tier enforces a hard budget cap:

| Tier | Weekly Query Limit |
|---|---|
| Pirate | 15 requests |
| Warlord | 50 requests |
| Emperor | Unlimited |

Anomaly detection fires when a user exceeds 3× their rolling 7-day average.

### Memory Architecture

| Tier | Scope | Limit | Storage |
|---|---|---|---|
| In-flight | Single request | Last 8 messages | LangGraph `MessagesState` |
| Session | Conversation | 2,000 chars | Supabase `conversation_memory` |
| Long-term | User lifetime | 100 entries/user | Supabase `user_profile_memory` |

---

## Tool Ecosystem

| Tool | Description |
|---|---|
| `flight_search` | Flight routing and pricing via SerpAPI Google Flights |
| `hotel_search` | Hotel discovery via Google Places + Tavily |
| `place_search_tool` | Attractions, restaurants, and activities |
| `weather_info_tool` | Current conditions and multi-day forecasts (OpenWeatherMap) |
| `railway_search` | Real-time train schedules via RailwayRadar API |

All tools are annotated with LangChain `@tool` decorators and bound to the agent graph at runtime. Tool inputs are validated against strict schemas (IATA codes, ISO dates) and checked for injection patterns before execution.

---

## API Reference

### Authentication

| Method | Endpoint | Rate Limit | Description |
|---|---|---|---|
| `POST` | `/signup` | 5/min | Register a new user |
| `POST` | `/signin` | 5/min | Authenticate and receive tokens |
| `POST` | `/refresh` | 10/min | Refresh access token |
| `POST` | `/signout` | 10/min | End user session |

### Core Agent

| Method | Endpoint | Rate Limit | Description |
|---|---|---|---|
| `POST` | `/query` | 30/min | Execute agent pipeline with SSE streaming + HITL support |

**Request:**
```json
{
  "question": "Plan a 10-day trip to Japan in April, budget $4000",
  "user_id": "string",
  "conversation_id": "string"
}
```

**Response** (`text/event-stream`):
```
data: {"type": "chunk", "content": "Here is your itinerary..."}
...
data: {"final_reply": "**Day 1 — Tokyo**\n..."}
```

### Conversations & Messages

| Method | Endpoint | Rate Limit | Description |
|---|---|---|---|
| `POST` | `/create_conversation` | 50/min | Create a new conversation thread |
| `DELETE` | `/delete_conversation` | 50/min | Delete a conversation |
| `GET` | `/see_conversation` | 50/min | List all conversations for a user |
| `GET` | `/see_message` | 50/min | Fetch messages in a conversation |

### Preferences

| Method | Endpoint | Rate Limit | Description |
|---|---|---|---|
| `POST` | `/add_preference` | 50/min | Add user preferences |
| `POST` | `/edit_preference` | 50/min | Update user preferences |
| `POST` | `/see_preference` | 50/min | Retrieve user preferences |
| `DELETE` | `/delete_preference` | 50/min | Remove user preferences |

### Observability

| Method | Endpoint | Rate Limit | Description |
|---|---|---|---|
| `GET` | `/health` | 100/min | System health + model router metrics |
| `GET` | `/debug/trace/{request_id}` | 100/min | Retrieve full execution trace |

All responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers. Rate-limited requests return `HTTP 429`.

---

## Project Structure

```
Agentic_Planner/
├── main.py                          # FastAPI application entrypoint
├── Schema.py                        # Pydantic request/response models
├── config/
│   └── config.yaml                  # Model registry and routing rules
├── agent_file/
│   ├── agent/
│   │   ├── agentic_workflow.py      # LangGraph graph, AgentRunner, MultiAgentEngine
│   │   └── multi_agents.py          # IntakeValidatorAgent, ResearchPricingAgent, WriterAgent
│   ├── tools/
│   │   ├── flight_search.py
│   │   ├── hotel_search.py
│   │   ├── place_search_tool.py
│   │   ├── weather_info_tool.py
│   │   └── railway_search.py
│   ├── utils/
│   │   ├── communication_manager.py # CommunicationManager + TraceRecorder
│   │   ├── multi_agent_config.py    # Per-phase configuration
│   │   ├── model_loader.py          # ModelRouter integration
│   │   ├── state_utils.py
│   │   └── station_resolver/        # Railway station data
│   └── prompt_library/
│       ├── multi_agent_prompts.py   # Phase-specific system prompts
│       └── prompt_maker.py          # Dynamic prompt assembly
├── backend/
│   ├── supabase_client/
│   │   ├── auth.py                  # Signup, signin, refresh, signout
│   │   └── db_operations.py         # Conversation and preference persistence
│   └── mongo.py                     # MongoDB trace storage
├── service/
│   ├── cache_service.py             # Redis initialization
│   └── verify_token.py              # JWT verification dependency
├── Dockerfile
└── docker-compose.yml
```

---

## Setup

### Prerequisites

- Python 3.11+
- Redis (local or hosted)
- MongoDB (for trace fallback)
- Supabase project

### Environment Variables

Copy `.env.name` to `.env` and populate:

```env
# LLM Providers
GROQ_API_KEY=
GEMINI_API_KEY=

# Search & Data APIs
TAVILY_API_KEY=
OPENWEATHERMAP_API_KEY=
SERP_API_KEY=
RAILWAY_RADAR_API_KEY=
EXCHANGE_RATE_API_KEY=

# Supabase
SUPABASE_URL=
ANON_KEY=
SERVICE_ROLE_KEY=

# MongoDB
MONGO_URL=
```

### Install & Run

```bash
# Install dependencies
pip install -r requirements.txt
# or with uv (recommended)
uv sync --frozen

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Verify
curl http://localhost:8000/health
```

---

## Deployment

### Docker

```bash
# Build
docker build -t agentic-planner .

# Run
docker run -e PORT=10000 -p 10000:10000 --env-file .env agentic-planner
```

### Docker Compose

```bash
docker compose up --build
```

The `docker-compose.yml` wires up the FastAPI app alongside Redis and any other required services.

---

## Roadmap

The project follows a versioned roadmap documented in `Documents/`:

**v1.0 (Current)**
- ✅ Multi-agent orchestration (3 phases, 45+ trace events)
- ✅ Cost-aware model router with circuit breakers
- ✅ SSE streaming + HITL interrupt/resume
- ✅ Per-user token budgets and daily quotas
- ✅ Full input/output guardrails (injection detection, PII masking, hallucination heuristics)
- ✅ Supabase auth, conversation memory, preference persistence
- ✅ Redis trace caching + MongoDB fallback
- ✅ Rate-limited FastAPI with structured health endpoint

**v2.0 (Planned)**
- 🔲 AP2 agentic payment protocol (mandate-based autonomous checkout)
- 🔲 Interactive booking pages (rich React cart component + HITL confirmation gate)
- 🔲 React Native mobile app (Android/iOS) with push notifications and biometric mandate signing
- 🔲 Global rail integration (Eurostar, Amtrak, JR Pass via SilverRail/Trainline)
- 🔲 Agent-to-Agent (A2A) discovery for merchant negotiation
- 🔲 Multi-modal input (document/voucher image reasoning)
- 🔲 pgvector long-term memory retrieval

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| Agent Orchestration | LangGraph + LangChain |
| Primary LLM | Groq LLaMA 3.3-70B |
| Fallback LLMs | Gemini 2.0 Flash, Mistral Medium, GPT-OSS-120B |
| Auth & DB | Supabase (PostgreSQL + JWT) |
| Caching & Tracing | Redis |
| Trace Fallback | MongoDB |
| Rate Limiting | slowapi |
| Data Validation | Pydantic |
| Containerization | Docker + Docker Compose |

---

## Repository

**GitHub:** [github.com/Debankur04/Agentic_Planner](https://github.com/Debankur04/Agentic_Planner)

For full API documentation see [`Documents/API_DOCUMENTATION.md`](Documents/API_DOCUMENTATION.md).  
For architecture deep-dive see [`Documents/ARCHITECTURE_AND_DATA_FLOW.md`](Documents/ARCHITECTURE_AND_DATA_FLOW.md).
