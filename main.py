from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import os

from Schema import *
from backend.supabase_client.auth import *
from backend.supabase_client.db_operations import *
from agent_file.agent.agentic_workflow import GraphBuilder

from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# ------------------ INIT GRAPH ONCE ------------------ #
graph_builder = GraphBuilder(model_provider="groq")
react_app = graph_builder()

# ------------------ CORS ------------------ #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ AUTH ------------------ #

@app.post('/signup', response_model=AuthResponse)
async def signup_api(query: AuthRequest):
    return signup(query.email, query.password)


@app.post('/signin', response_model=AuthResponse)
async def signin_api(query: AuthRequest):
    return signin(query.email, query.password)


@app.post('/signout', response_model=SimpleMessage)
async def signout_api():
    signout()
    return {"message": "Signed out successfully"}


# ------------------ CONVERSATIONS ------------------ #

@app.post('/create_conversation', response_model=SimpleMessage)
async def create_conversation_api(query: ConversationCreate):
    convo_id = create_conversation(query.user_id, query.title)
    return {"message": f"Conversation created with id {convo_id}"}


@app.delete('/delete_conversation', response_model=SimpleMessage)
async def delete_conversation_api(query: ConversationDelete):
    delete_conversation(query.conversation_id)
    return {"message": "Conversation deleted successfully"}


# ------------------ MESSAGES ------------------ #

@app.get('/see_message', response_model=MessageListResponse)
async def see_message_api(conversation_id: str = Query(...)):
    messages = see_message(conversation_id)
    return {"messages": messages}


# ------------------ AGENT QUERY ------------------ #

@app.post("/query", response_model=QueryResponse)
async def query_travel_agent(query: QueryRequest):
    try:
        # Save user message
        add_message(
            user_id=query.user_id,
            conversation_id=query.conversation_id,
            role='user',
            content=query.question
        )

        # Run agent
        messages = {"messages": [query.question]}
        output = react_app.invoke(messages)

        if isinstance(output, dict) and "messages" in output:
            final_output = output["messages"][-1].content
        else:
            final_output = str(output)

        # Save assistant response
        add_message(
            user_id=query.user_id,
            conversation_id=query.conversation_id,
            role='assistant',
            content=final_output
        )

        return {"answer": final_output}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})