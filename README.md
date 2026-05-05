# 🌍 AI Travel Planner (Agentic Planner)

Welcome to the **AI Travel Planner**, an intelligent, agent-based application that helps users plan comprehensive and deeply personalized trips to any destination worldwide. 

This project utilizes cutting-edge AI technologies, leveraging **LangGraph** to create a sophisticated workflow capable of reasoning, recalling user preferences, and securely interacting with external booking tools. The application provides a highly performant and responsive user experience through a **Next.js** frontend and a robust **FastAPI** backend integrated with a scalable database architecture.

## 🌟 Key Features

- **Personalized Itinerary Generation**: Day-by-day travel plans customized for standard tourists or those seeking off-beat locations.
- **Context-Aware User Memory**: Maintains a long-term memory of individual user preferences from past interactions (e.g., flight seat preferences, favorite hotel chains, dietary restrictions) to tailor every new recommendation perfectly.
- **Advanced Human-in-the-Loop (HITL)**: Utilizes strict LangGraph interrupts to pause execution when critical details are missing, requesting user clarification to prevent API token waste and hallucinations.
- **Real-Time Streaming Output**: The `/query` API delivers responses using Server-Sent Events (SSE), streaming the agent's thoughts and final plan character-by-character for a highly responsive UI.
- **Smart Booking Assistance & Action Capabilities**: The agent leverages different platform APIs alongside the **AP2 (Agent Protocol 2)** by Google to actively assist in booking flights, reserving restaurants, and securing hotel rooms securely.
- **Multi-Tenant System & Authentication**: A complete multi-user system featuring secure authentication workflows, ensuring that every user's travel history, favorites, and billing details securely persist across sessions via a robust database.
- **Support for Top-Tier LLMs**: Configurable to use Groq (`deepseek-r1-distill-llama-70b`) or OpenAI (`o4-mini`).
- **Professional Web UI**: A beautiful, modern, and SEO-optimized web interface built on **Next.js**.

## 🏗️ Architecture Overview

The system operates on an advanced multi-tier architecture:
1. **Frontend (`Next.js`)**: A responsive UI utilizing React Server Components for optimal performance and secure session management. It connects exclusively via RESTful JSON APIs to the backend.
2. **Backend (`main.py` - FastAPI & DB)**: A scalable server handling API requests, JWT/OAuth authentication, and database connections (e.g., PostgreSQL or MongoDB). It features decoupled resources for Threads (Conversations) vs. Messages. **For full API details, see [API_DOCUMENTATION.md](./API_DOCUMENTATION.md).**
3. **Agentic Workflow (`agent/agentic_workflow.py`)**: The brain of the application utilizing `LangGraph`. 
   - Uses strict **Context Trace Limits** (only the last 8 messages) to maintain token safety.
   - Extracts and maintains a continuously running, string-based **Memory Track** (truncated at 2000 chars to avoid memory explosion), overriding relying entirely on large history arrays.
   - Leverages live tool integration (Weather, Place Search, Expense Calculation) before generating the final plan or executing AP2-compliant commands.

## 🚀 Setup & Installation

### Prerequisites
- Python 3.10+ & Node.js 18+
- `uv` package manager (recommended) and `npm` or `yarn`
- Optional: PostgreSQL or MongoDB instance
- API Keys: `GROQ_API_KEY`, `OPENAI_API_KEY`, `GPLACES_API_KEY`, `TAVILY_API_KEY`.

### Backend Installation

1. **Create Python environment** and activate:
   ```bash
   uv venv env --python cpython-3.10.18-windows-x86_64-none
   .\env\Scripts\activate
   ```
2. **Install dependencies**:
   ```bash
   uv pip install -r backend/requirements.txt
   ```
3. **Configure Environment (`backend/.env`)**:
   ```env
   DATABASE_URL=postgres://user:pass@localhost:5432/travel_db
   JWT_SECRET=your_auth_secret
   GROQ_API_KEY=your_groq_api_key
   # ... other keys
   ```

### Frontend Installation

1. **Navigate to the frontend module**:
   ```bash
   cd frontend
   ```
2. **Install node modules**:
   ```bash
   npm install
   ```
3. **Configure Environment (`frontend/.env.local`)**:
   ```env
   NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

## 🛠️ Running the Application

You will need to run the backend and frontend in separate terminals.

**1. Start the FastAPI Backend**:
```bash
cd backend
uvicorn main:app --reload --port 8000
```
*The API interacts at `http://localhost:8000`.*

**2. Start the Next.js Frontend**:
```bash
cd frontend
npm run dev
```
*The web app will open at `http://localhost:3000`.*