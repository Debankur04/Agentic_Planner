from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import json
from Schema import *
from backend.supabase_client.auth import *
from backend.supabase_client.db_operations import (
    create_conversation, delete_conversation, see_conversation,see_message,
    upsert_preference, remove_preference, get_preference)
from llmops.guardrails import *
from llmops.token_tracker import TokenTracker
from dotenv import load_dotenv
from service.cache_service import redis_client
from service.verify_token import verify_token
from backend.mongo import get_trace_from_db
from backend.controller.query_controller import query_helper, router as query_router

load_dotenv()

app = FastAPI()

# ------------------ INIT GRAPH ONCE ------------------ #
token_tracker = TokenTracker(redis_client= redis_client)

# ------------------ CORS ------------------ #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------ APIS------------------ #
@app.get('/')
async def default():
    return {'message':'Server started'}

@app.get('/health', tags=["System Health"])
async def health_check():
    status = {"backend": "active"}

    # Check redis
    try:
        if redis_client.ping():
            status["redis"] = "active"
        else:
            status["redis"] = "inactive"
    except Exception as e:
        status["redis"] = f"inactive: {str(e)}"

    # Check models and pull all metrics
    models_info = {}
    for model_key, health_obj in query_router.health.items():
        cfg = query_router.config["models"].get(model_key, {})
        models_info[model_key] = {
            "provider": cfg.get("provider"),
            "model_name": cfg.get("model_name"),
            "tier": cfg.get("tier"),
            "cost_per_1k_input": cfg.get("cost_per_1k_input"),
            "cost_per_1k_output": cfg.get("cost_per_1k_output"),
            "avg_latency_ms": cfg.get("avg_latency_ms"),
            "max_tokens": cfg.get("max_tokens"),
            "error_count": health_obj.error_count,
            "total_calls": health_obj.total_calls,
            "error_rate": health_obj.error_rate,
            "p99_latency": health_obj.p99_latency,
            "circuit_open": health_obj.circuit_open,
            "circuit_open_until": health_obj.circuit_open_until,
            "is_healthy": health_obj.is_healthy()
        }
        
    status["models"] = models_info
    return status

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
        return await query_helper(query)
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


