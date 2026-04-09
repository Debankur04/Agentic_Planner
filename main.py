from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import os
import tiktoken
import json
from Schema import *
from backend.supabase_client.auth import *
from backend.supabase_client.db_operations import (
    create_conversation, delete_conversation, see_conversation,
    add_message, see_message,
    upsert_preference, remove_preference, get_preference,
    get_conversation_memory, update_conversation_memory
)
from llmops.guardrails import *
from llmops.token_tracker import TokenTracker
from agent_file.agent.agentic_workflow import AgentRunner, TravelEngine

from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

encoding = tiktoken.encoding_for_model("gpt-4")

# ------------------ INIT GRAPH ONCE ------------------ #
runner = AgentRunner()
travel_engine = TravelEngine(runner)

token_tracker = TokenTracker()

# ------------------ CORS ------------------ #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get('/')
async def default():
    return {'message':'Server started'}

# ------------------ AUTH ------------------ #

@app.post('/signup', response_model=SignupResponse)
async def signup_api(query: AuthRequest):
    return signup(query.email, query.password)


@app.post('/signin', response_model=AuthResponse)
async def signin_api(query: AuthRequest):
    print(query.email, query.password)
    return signin(query.email, query.password)


@app.post('/signout', response_model=SimpleMessage)
async def signout_api():
    signout()
    return {"message": "Signed out successfully"}


# ------------------ CONVERSATIONS ------------------ #

@app.post('/create_conversation', response_model=ConversationCreateResponse)
async def create_conversation_api(query: ConversationCreate):
    convo_id = create_conversation(query.user_id, query.title)
    return {"conversation_id": convo_id}


@app.delete('/delete_conversation', response_model=SimpleMessage)
async def delete_conversation_api(query: ConversationDelete):
    delete_conversation(query.conversation_id)
    return {"message": "Conversation deleted successfully"}

@app.get('/see_conversation', response_model= ConversationListResponse)
async def see_conversation_api(user_id:str = Query(...)):
    response = see_conversation(user_id)
    return {"conversations": response}


# ------------------ MESSAGES ------------------ #

@app.get('/see_message', response_model=MessageListResponse)
async def see_message_api(conversation_id: str = Query(...)):
    messages = see_message(conversation_id)
    return {"messages": messages}


# ------------------ AGENT QUERY ------------------ #

@app.post("/query", response_model=QueryResponse)
async def query_travel_agent(query: QueryRequest):
    try:
        if not token_tracker.check_budget(user_id= query.user_id):
            return {'message': 'Daily Limit Exceeded. Try again tomorrow.'}

        user_query, violation = sanitize_input(query.question)
        if violation:
            return {'message': 'Message violation detected'}
        # 1. Save user message
        add_message(
            user_id=query.user_id,
            conversation_id=query.conversation_id,
            role='user',
            content=user_query
        )
        # 2. Get recent history (OPTION: limit later)
        past_messages = see_message(query.conversation_id)
        history_str = ""

        for msg in past_messages[-8:]:  # 🔥 limit history (important)
            history_str += f"{msg['role']}: {msg['content']}\n"

        # 3. Get preference
        try:
            pref_data = get_preference(query.user_id)
            if isinstance(pref_data, list) and len(pref_data) > 0:
                preference = json.dumps({
                    "dietary": pref_data[0].get("dietary_preference"),
                    "custom": pref_data[0].get("custom_preference")
                })
            else:
                preference = ""
        except:
            preference = ""

        # 4. 🔥 GET MEMORY
        try:
            memory = get_conversation_memory(query.conversation_id)
        except:
            memory = ""

        # 5. 🔥 Run agent (with memory)
        reply, new_pref, new_history = travel_engine.process_query(
            user_input=user_query,
            preference=preference,
            history=history_str,
            memory=memory,   # ✅ NEW
            user_id=query.user_id
        )
        reply = validate_llm_output(reply)

        final_output = str(reply)

        # 6. Save assistant response
        add_message(
            user_id=query.user_id,
            conversation_id=query.conversation_id,
            role='assistant',
            content=final_output
        )

        # input_tokens = len(tokenizer.encode(prompt))

        # output_tokens = len(tokenizer.encode(response_text))

        # 7. 🔥 UPDATE MEMORY (IMPORTANT)
        try:
            # Simple version (you can upgrade later)
            updated_memory = f"{memory}\nUser: {user_query}\nAssistant: {final_output}"

            # limit memory size
            updated_memory = updated_memory[-2000:]  # prevent explosion

            update_conversation_memory(query.conversation_id, updated_memory)

        except Exception as e:
            print("Memory update failed:", e)

        return {"answer": final_output}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    


# ------------------ PREFERENCES ------------------ #

@app.post('/add_preference', response_model=SimpleResponse)
async def add_preference_api(query: AddPreferenceRequest):
    try:
        result = upsert_preference(
            user_id=query.user_id,
            dietary_preference=query.dietary_preference,
            custom_preference=query.custom_preference
        )
        return {"message": result["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/edit_preference', response_model=SimpleResponse)
async def edit_preference_api(query: UpdatePreferenceRequest):
    try:
        result = upsert_preference(
            user_id=query.user_id,
            dietary_preference=query.dietary_preference,
            custom_preference=query.custom_preference
        )
        return {"message": result["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/see_preference')
async def see_preference_api(query: SeePreferenceRequest):
    try:
        data = get_preference(query.user_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/delete_preference', response_model=SimpleResponse)
async def delete_preference_api(query: DeletePreferenceRequest):
    try:
        result = remove_preference(query.user_id)
        return {"message": result["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))