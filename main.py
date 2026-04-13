from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import os
import asyncio
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
from llmops.model_router import ModelRouter
from agent_file.utils.config_loader import load_config
from dotenv import load_dotenv
from service.cache_service import redis_client
from backend.mongo import get_trace_from_db
from supabase_auth.errors import AuthApiError 
import uuid

load_dotenv()

app = FastAPI()

encoding = tiktoken.encoding_for_model("gpt-4")

# ------------------ INIT GRAPH ONCE ------------------ #
router = ModelRouter(load_config())
runner = AgentRunner(router)
travel_engine = TravelEngine(runner)
token_tracker = TokenTracker(redis_client= redis_client)

# ------------------ CORS ------------------ #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount our streaming routes
# app.include_router(stream_router, tags=["chat"])

# def should_cancel(request_id: str) -> bool:
#     return bool(redis_client.get(f"cancel:{request_id}"))

@app.get('/')
async def default():
    return {'message':'Server started'}

# ------------------ AUTH ------------------ #

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    
    if not auth_enabled:
        return None

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization token missing")

    token = credentials.credentials

    try:
        user = verify_access_token(token)
        return user

    except AuthApiError:
        # 👇 THIS is your actual case
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    except Exception:
        # fallback safety
        raise HTTPException(status_code=401, detail="Authentication failed")

def fallback_to_json(raw_output: str):
    return {
        "reply": raw_output.strip(),
        "preference": {
            "peaceful": False,
            "adventurous": False,
            "cultural": False
        },
        "confidence": 50
    }
def process_llm_output(raw_output: str):
    try:
        return validate_llm_output(raw_output)
    except Exception:
        # 🔥 fallback instead of crashing
        return fallback_to_json(raw_output)

@app.post('/signup', response_model=SignupResponse)
async def signup_api(query: AuthRequest):
    return signup(query.email, query.password)


@app.post('/signin', response_model=AuthResponse)
async def signin_api(query: AuthRequest):
    print(query.email, query.password)
    return signin(query.email, query.password)


@app.post('/refresh', response_model=AuthResponse)
async def refresh_api(query: RefreshRequest):
    try:
        return refresh_session(query.refresh_token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post('/signout', response_model=SimpleMessage)
async def signout_api():
    signout()
    return {"message": "Signed out successfully"}


# ------------------ CONVERSATIONS ------------------ #

@app.post('/create_conversation', response_model=ConversationCreateResponse)
async def create_conversation_api(query: ConversationCreate, user=Depends(verify_token)):
    convo_id = create_conversation(query.user_id, query.title)
    return {"conversation_id": convo_id}


@app.delete('/delete_conversation', response_model=SimpleMessage)
async def delete_conversation_api(query: ConversationDelete, user=Depends(verify_token)):
    delete_conversation(query.conversation_id)
    return {"message": "Conversation deleted successfully"}

@app.get('/see_conversation', response_model= ConversationListResponse)
async def see_conversation_api(user_id:str = Query(...), user=Depends(verify_token)):
    response = see_conversation(user_id)
    return {"conversations": response}


# ------------------ MESSAGES ------------------ #

@app.get('/see_message', response_model=MessageListResponse)
async def see_message_api(conversation_id: str = Query(...), user=Depends(verify_token)):
    messages = see_message(conversation_id)
    return {"messages": messages}


# ------------------ AGENT QUERY ------------------ #

@app.post("/query", response_model=QueryResponse)
async def query_travel_agent(query: QueryRequest, user=Depends(verify_token)):
    try:
        if not token_tracker.check_budget(user_id= query.user_id):
            return {'message': 'Daily Limit Exceeded. Try again tomorrow.'}

        user_query, violation = sanitize_input(query.question)
        if violation:
            return {'message': 'Message violation detected'}
        
        request_id = f"req_{uuid.uuid4().hex}"
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
        reply, new_pref, new_history = await asyncio.wait_for(
            asyncio.to_thread(
                travel_engine.process_query,
                user_input=user_query,
                preference=preference,
                history=history_str,
                memory=memory,
                user_id=query.user_id
            ),
            timeout=30
        )
        reply = process_llm_output(reply)

        final_output = reply

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

        return {"answer": final_output['reply']}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    


# ------------------ PREFERENCES ------------------ #

@app.post('/add_preference', response_model=SimpleResponse)
async def add_preference_api(query: AddPreferenceRequest, user=Depends(verify_token)):
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
async def edit_preference_api(query: UpdatePreferenceRequest, user=Depends(verify_token)):
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
async def see_preference_api(query: SeePreferenceRequest, user=Depends(verify_token)):
    try:
        data = get_preference(query.user_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/delete_preference', response_model=SimpleResponse)
async def delete_preference_api(query: DeletePreferenceRequest, user=Depends(verify_token)):
    try:
        result = remove_preference(query.user_id)
        return {"message": result["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/debug/trace/{request_id}")
async def get_trace(request_id: str):

    # 🔥 1. Try Redis (fast path)
    raw = redis_client.get(f"trace:{request_id}")
    if raw:
        return json.loads(raw)

    # 🔥 2. Fallback to Mongo
    trace = get_trace_from_db(request_id)

    if not trace:
        raise HTTPException(404, "Trace not found")

    # 🔥 3. Remove Mongo ObjectId (not JSON serializable)
    trace["_id"] = str(trace["_id"])

    return trace

# import asyncio

# async def fake_stream(text: str):
#     words = text.split(" ")

#     for word in words:
#         yield word + " "
#         await asyncio.sleep(0.02)

# @app.post("/query/stream")
# async def query_stream(query: QueryRequest):

#     request_id = f"req_{uuid.uuid4().hex}"

#     async def event_generator():
#         response = await travel_engine.query(query.question)

#         async for token in fake_stream(response):
#             if should_cancel(request_id):
#                 break

#             yield f"data: {json.dumps({'token': token})}\n\n"

#         yield "data: [DONE]\n\n"

#     return StreamingResponse(event_generator(), media_type="text/event-stream")

# @app.delete("/cancel/{request_id}")
# async def cancel_request(request_id: str):
#     redis_client.setex(f"cancel:{request_id}", 60, "1")
#     return {"status": "cancellation_requested"}

