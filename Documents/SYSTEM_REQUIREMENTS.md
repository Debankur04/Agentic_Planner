# 📋 System Requirement Document (SRD)

**Project Name**: AI Travel Planner (Agentic Planner)
**Version**: 2.0 (Advanced Multi-User Architecture)

## 1. Introduction
The next-generation AI Travel Planner is a sophisticated travel assistant merging autonomous agent logic with secure, scalable web development standards. It aims to not only generate custom trip itineraries but uniquely personalize those itineraries based on long-term user memory and assist in actionable travel bookings autonomously via standardized HTTP protocols.

---

## 2. System Architecture Requirements
The system comprises four logical tiers:
1. **Presentation Layer**: A responsive Next.js frontend built for high SEO and performance.
2. **Application Layer**: A REST API backend built with FastAPI handling business logic, graph workflows, and user sessions.
3. **Data Layer**: A scalable database (e.g. Postgres) mitigating auth boundaries and enforcing multi-tenant isolation for persistent user histories.
4. **Agent & Integration Layer**: The LangGraph engine and execution environment running AP2 actions and third-party API tool calls dynamically.

---

## 3. Functional Requirements

**FR1: Multi-User Authentication & Account Management**
- The system must provide secure sign-up/login functionality enforcing password hashing and JWT/OAuth protocols.
- The system must securely isolate chat history and generated itineraries per user.

**FR2: Intelligent User Memory & Preferences**
- The system must allow users to continuously refine their preferences (e.g., specific airlines, hotel brands, accessibility requirements, dietary constraints).
- The agent must implicitly utilize these preferences stored in the database as base context for every generation to perfectly tailor output without explicitly asking the user every time.

**FR3: Automated Booking via Google AP2**
- The system must feature autonomous "Booking Assistance" workflows.
- Upon finalizing an itinerary, the agent must be able to securely invoke Google AP2 (Agent Protocol 2) wrappers to reserve spots on compatible ticketing platforms, hotels, and airlines.
- The system must never auto-execute a financial transaction without surfacing a final user confirmation UI on the frontend.

**FR4: Itinerary Generation & Discovery**
- The system must generate a cohesive day-by-day sequence.
- Include recommendations aligned with the user's historical context DB.
- Use native API tools (Google Places) or fallback search systems (Tavily) to gather precise costs and constraints.

---

## 4. Non-Functional Requirements

**NFR1: Performance & Scalability**
- The Next.js frontend must serve static/prerendered components where possible to minimize time-to-first-byte (TTFB).
- The FastAPI backend must rely on async DB drivers and non-blocking asynchronous loops to allow a high simultaneous concurrency limit.

**NFR2: Security & Privacy**
- User data (especially historical booking intent and location preferences) must be stored encrypted at rest.
- LLM prompt context injection layers must enforce a strict boundary to prevent prompt leakages impacting the SQL datastore (SQL injection prevention).

**NFR3: Reliability & Fallbacks**
- Complex tool executions (like multi-step booking AP2 hooks) must rely on clear timeout mechanisms and return graceful failure summaries identifying to the user what went wrong (e.g. "The hotel is sold out for these dates").

---

## 5. Software Interfaces & Dependencies

### Core Technologies
- **Frontend Core**: `Next.js`, `React`, `TailwindCSS`, `NextAuth`.
- **Backend Framework**: `FastAPI` (Python).
- **AI/LLM Core**: `langgraph` (for stateful routing), `langchain-core`.
- **Database**: `PostgreSQL` or `MongoDB` (with an ORM such as SQLAlchemy/Prisma).

### External API Dependencies
- **LLM Inferencing**: Groq API or OpenAI API.
- **Search Integrations**: Google Places API, Tavily Search API.
- **Booking Integrations**: Endpoints conforming to the AP2 specification.
