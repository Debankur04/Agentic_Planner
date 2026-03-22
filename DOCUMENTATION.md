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

## 2. Agentic Workflow with Persistent Memory

The LangGraph implementation (`agentic_workflow.py`) has been advanced to support persistent state and context retrieval.

- **Class `GraphBuilder` Framework**: 
  - **Memory Injection**: Before interpreting the current user input, the graph queries the user's database entry to retrieve their `Preference Context`. This context is seamlessly injected into the `SYSTEM_PROMPT` to guide output logic (e.g., dynamically prioritizing window seats or vegan-friendly restaurants).
  - **State Maintenance**: Langgraph handles thread-level persistence, saving each step of the conversation into an underlying SQL/NoSQL storage so sessions can be resumed.
  - **Workflow**: 
    1. Retrieve User Context.
    2. Route to Agent.
    3. Loop through necessary custom Tools.
    4. Compile Final Plan or Commit AP2 Command.

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
