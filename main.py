from fastapi import FastAPI, Query, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from Schema import *
import logging
import uuid
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
)
logger = logging.getLogger("agentic_planner")


def build_api_response(success: bool, data: dict | None = None, trace_id: str = "", errors: list[str] | None = None, warnings: list[str] | None = None):
    return {
        "success": success,
        "data": data or {},
        "trace_id": trace_id or "",
        "errors": errors or [],
        "warnings": warnings or []
    }


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# ------------------ RATE LIMITING SETUP (SLOWAPI) ------------------ #
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
    status_code=429,
    content={"error": "Rate limit exceeded. Please try again later."}
))

# ------------------ INIT GRAPH ONCE ------------------ #
token_tracker = TokenTracker(redis_client= redis_client)

# ------------------ CORS ------------------ #
# Rate limiting middleware
app.add_middleware(SlowAPIMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception while processing request", exc_info=exc, extra={"request_id": getattr(request.state, "request_id", "")})
    payload = build_api_response(
        success=False,
        data={},
        trace_id=getattr(request.state, "request_id", ""),
        errors=[str(exc)],
        warnings=[]
    )
    return JSONResponse(status_code=500, content=jsonable_encoder(payload))


# ------------------ APIS------------------ #
@app.get('/')
@limiter.limit("100/minute")
async def default(request: Request):
    return {'message':'Server started'}

@app.get('/health', tags=["System Health"])
@limiter.limit("100/minute")
async def health_check(request: Request):
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
@limiter.limit("5/minute")
async def signup_api(request: Request, query: AuthRequest):
    return signup(query.email, query.password)


@app.post('/signin', response_model=AuthResponse)
@limiter.limit("5/minute")
async def signin_api(request: Request, query: AuthRequest):
    print(query.email, query.password)
    return signin(query.email, query.password)


@app.post('/refresh', response_model=AuthResponse)
@limiter.limit("10/minute")
async def refresh_api(request: Request, query: RefreshRequest):
    try:
        return refresh_session(query.refresh_token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post('/signout', response_model=SimpleMessage)
@limiter.limit("10/minute")
async def signout_api(request: Request):
    signout()
    return {"message": "Signed out successfully"}


# ------------------ CONVERSATIONS ------------------ #

@app.post('/create_conversation', response_model=ConversationCreateResponse)
@limiter.limit("50/minute")
async def create_conversation_api(request: Request, query: ConversationCreate, user=Depends(verify_token)):
    convo_id = create_conversation(query.user_id, query.title)
    return {"conversation_id": convo_id}


@app.delete('/delete_conversation', response_model=SimpleMessage)
@limiter.limit("50/minute")
async def delete_conversation_api(request: Request, query: ConversationDelete, user=Depends(verify_token)):
    delete_conversation(query.conversation_id)
    return {"message": "Conversation deleted successfully"}

@app.get('/see_conversation', response_model= ConversationListResponse)
@limiter.limit("50/minute")
async def see_conversation_api(request: Request, user_id:str = Query(...), user=Depends(verify_token)):
    response = see_conversation(user_id)
    return {"conversations": response}


# ------------------ MESSAGES ------------------ #

@app.get('/see_message', response_model=MessageListResponse)
@limiter.limit("50/minute")
async def see_message_api(request: Request, conversation_id: str = Query(...), user=Depends(verify_token)):
    messages = see_message(conversation_id)
    return {"messages": messages}


# ------------------ AGENT QUERY ------------------ #

@app.post("/query")
@limiter.limit("30/minute")
async def query_travel_agent(request: Request, query: QueryRequest, user=Depends(verify_token)):
    result = await query_helper(query)
    trace_id = getattr(request.state, "request_id", "")

    if isinstance(result, dict) and "error" in result:
        errors = [result["error"].get("message", str(result["error"]))] if isinstance(result["error"], dict) else [str(result["error"]) ]
        payload = build_api_response(
            success=False,
            data={},
            trace_id=result.get("trace_id", trace_id),
            errors=errors,
            warnings=[]
        )
        return JSONResponse(status_code=200, content=jsonable_encoder(payload))

    if isinstance(result, dict) and "reply" in result:
        payload = build_api_response(
            success=True,
            data={"reply": result["reply"]},
            trace_id=result.get("trace_id", trace_id)
        )
        return JSONResponse(status_code=200, content=jsonable_encoder(payload))

    payload = build_api_response(
        success=False,
        data={},
        trace_id=trace_id,
        errors=["Unexpected result shape from query helper."],
        warnings=[]
    )
    return JSONResponse(status_code=200, content=jsonable_encoder(payload))

# ------------------ PREFERENCES ------------------ #

@app.post('/add_preference', response_model=SimpleResponse)
@limiter.limit("50/minute")
async def add_preference_api(request: Request, query: AddPreferenceRequest, user=Depends(verify_token)):
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
@limiter.limit("50/minute")
async def edit_preference_api(request: Request, query: UpdatePreferenceRequest, user=Depends(verify_token)):
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
@limiter.limit("50/minute")
async def see_preference_api(request: Request, query: SeePreferenceRequest, user=Depends(verify_token)):
    try:
        data = get_preference(query.user_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete('/delete_preference', response_model=SimpleResponse)
@limiter.limit("50/minute")
async def delete_preference_api(request: Request, query: DeletePreferenceRequest, user=Depends(verify_token)):
    try:
        result = remove_preference(query.user_id)
        return {"message": result["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/debug/trace/{request_id}")
@limiter.limit("100/minute")
async def get_trace(request: Request, request_id: str):
    raw = redis_client.get(f"trace:{request_id}")
    if raw:
        return json.loads(raw)
    trace = get_trace_from_db(request_id)

    if not trace:
        raise HTTPException(404, "Trace not found")

    trace["_id"] = str(trace["_id"])

    return trace


