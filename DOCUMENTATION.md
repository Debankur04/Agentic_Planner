# 📚 Technical Documentation

This document provides an in-depth look at the internal components and architecture of the **AI Travel Planner** codebase, inclusive of the modern multi-user paradigm.

## 1. System Architecture

The project follows an advanced full-stack microservice architecture capable of securely serving multiple users concurrently, backed by persistent data storage.

### 1.1 Frontend (Next.js)
- **Directory**: `frontend/`
- **Description**: The Next.js application replaces the prototype Streamlit UI. It implements the App Router for robust navigation.
- **Core Integrations**:
  - **NextAuth.js**: Handles user login, state, and secure session tokens via OAuth providers or credentials.
  - **Tailwind CSS**: Establishes a highly polished, responsive aesthetic.
  - **State Management**: Manages chat state, active booking sessions, and user profiles locally.

### 1.2 Backend & Data Layer (FastAPI + Database)
- **Core File**: `backend/main.py`
- **Description**: The REST server acting as the gateway to the LangGraph engine and the database.
- **Multi-Tenant DB Integration**: Uses an ORM (like SQLAlchemy or Prisma) connected to a relational (PostgreSQL) or document (MongoDB) store. It stores:
  - User profiles and credentials.
  - Chat session histories.
  - Individual preference vectors (flight preferences, loyalties, dietary restrictions).
- **Endpoints**:
  - `POST /auth/...`: Handles authentication workflows.
  - `POST /query`: Primary endpoint processing authenticated user queries and triggering the agent.
  - `GET /user/history`: Retrieves past generated itineraries or active bookings.

---

## 2. Agentic Workflow, Persistent Memory, & Scaling Decisions

The central processing architecture (`agentic_workflow.py` and the main query pipeline) has been heavily refactored for scaling optimization and context precision:

### 2.1 Context Limits & Safety Bounds
To avoid exponential token scaling issues and catastrophic memory blow-outs during long-running travel planning sessions, several explicit constraint decisions have been baked into the pipeline:
- **Hard Window for Chat History**: Only the last 8 messages (`past_messages[-8:]`) are injected into the context trace per query. This isolates the LLM's operational attention strictly to the current conversational locus.
- **Dedicated Memory Block**: Instead of relying solely on the chat history array, a serialized `memory` block tracks conversational facts. 
- **Memory String Limits**: The overarching memory tracker string is aggressively truncated to retaining only the last 2,000 characters (`updated_memory[-2000:]`). This ensures that context sizes do not eventually overwhelm the inference token limits and guarantees reliable API operations.

### 2.2 Framework & Graph Builder Options
- **Memory Injection (Agentic Loop)**: The graph queries the database entry to retrieve an overarching `Preference JSON` and the newly updated running `memory` string. Both variables directly contextualize the `SYSTEM_PROMPT` allowing the groq-backed architecture to process "vegan-friendly" logic accurately without requiring parsing history.
- **Decoupled API Schemas**: The backend explicitly separates `Conversations` (Thread Headers/Titles) from `Messages` (Iterative content). State maintenance allows frontend UX patterns to easily swap contexts without reloading huge arrays.
  
- **Workflow Execution**: 
  1. Retrieve explicit Contexts (Preferences + Memory Track + Last 8 Messages).
  2. Synthesize Graph State and route to Language Agent.
  3. Loop through tools logic securely.
  4. Post Process: Return Response, update local memory block, and commit string updates back to Database (e.g., `update_conversation_memory`).

---

## 3. High-Level Tool Ecosystem & AP2 Integration

The agent integrates a suite of advanced tools, including booking automation mechanisms using Google AP2.

- **Booking Assistance (AP2 Protocol)**:
  - Enables the system to translate high-level requests (e.g., "Book that hotel for 3 nights") into low-level operational schema executed on partner platforms via Google AP2 standards.
  - Requires specific tool-calling validations and secure transactional handoffs (returning an explicit authorization URL to the user whenever payments are finalized).
- **Place Search Tool & APIs**:
  - Leverages Google Places API and Tavily to source attractions and hotels.
- **Math & Finance Tools**:
  - Expense calculations and currency conversions for cross-border pricing.

---

## 4. Configuration & Prompts

- **System Prompt (`prompt_library/prompt.py`)**: Uses a dynamic prompt template capable of reading user preference JSON data. It dictates the behavior for drafting complex itinerary plans and invoking booking tools.
- **Model Config (`config/config.yaml`)**: Supports `groq` (`deepseek-r1-distill-llama-70b`) for rapid chain-of-thought routing and `openai` (`o4-mini`) for stable tool calling logic.

---

## 5. Extending the Codebase

### Adding New AP2 Integrations
1. Use Google AP2 specifications to form the request and response models inside `utils/`.
2. Wrap the API logic in a new file (e.g., `tools/booking_tool.py`) decorated by `@tool`, ensuring that sensitive payload signatures align with user authorization thresholds.
3. Append the new tool to the `GraphBuilder.tools` array.
