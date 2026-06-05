from fastapi import FastAPI, Query, HTTPException, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, StreamingResponse
import json
import asyncio
import re
from contextvars import ContextVar
from agent_file.agent.agentic_workflow import GraphBuilder
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from Schema import *
import logging
import uuid
from backend.supabase_client.auth import *
from backend.supabase_client.db_operations import (create_conversation, delete_conversation, see_conversation,see_message,upsert_preference, remove_preference, get_preference)
from llmops.guardrails import *
from llmops.token_tracker import TokenTracker
from dotenv import load_dotenv
from service.cache_service import redis_client
from service.verify_token import verify_token
from backend.mongo import get_trace_from_db
from backend.controller.query_controller import query_helper, router as query_router
from backend.controller.query_controller import quota_service
from service.billing_service import BillingService
from service.emperor import emperor_key

load_dotenv()

app = FastAPI()

class SafeRequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = ""
        return True

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
handler.addFilter(SafeRequestIdFilter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
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
billing_service = BillingService()

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
            data=result["error"].get("quota", {}) if isinstance(result["error"], dict) else {},
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


current_sse_context = ContextVar("current_sse_context", default=None)
original_log_node = GraphBuilder._log_node_entry

def patched_log_node(self, node_name: str, state):
    original_log_node(self, node_name, state)
    ctx = current_sse_context.get()
    if ctx:
        q, loop = ctx
        if node_name in ["intake", "research", "validator", "writer"]:
            try:
                loop.call_soon_threadsafe(q.put_nowait, {"agent": node_name})
            except Exception:
                pass

GraphBuilder._log_node_entry = patched_log_node

async def sse_query_helper(query: QueryRequest):
    q = asyncio.Queue()
    loop = asyncio.get_running_loop()
    token = current_sse_context.set((q, loop))
    
    async def run_query():
        try:
            res = await query_helper(query)
            await q.put({"final": res})
        except Exception as e:
            await q.put({"error": str(e)})
            
    task = asyncio.create_task(run_query())
    
    try:
        while True:
            item = await q.get()
            if "agent" in item:
                yield f"data: {json.dumps({'type': 'phase', 'phase': item['agent']})}\n\n"
            elif "final" in item:
                res = item["final"]
                if "error" in res:
                    yield f"data: {json.dumps(res)}\n\n"
                else:
                    reply = res.get("reply", "")
                    # Stream by chunking word by word, preserving whitespaces
                    chunks = re.split(r'(\s+)', reply)
                    for chunk in chunks:
                        if chunk:
                            yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chunk})}\n\n"
                            if not chunk.isspace():
                                await asyncio.sleep(0.005)
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                break
            elif "error" in item:
                yield f"data: {json.dumps({'error': item['error']})}\n\n"
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"
                break
    finally:
        current_sse_context.reset(token)
        if not task.done():
            task.cancel()

@app.post("/sse_query")
@limiter.limit("30/minute")
async def sse_query_travel_agent(request: Request, query: QueryRequest, user=Depends(verify_token)):
    return StreamingResponse(sse_query_helper(query), media_type="text/event-stream")


# ------------------ QUOTA / BILLING ------------------ #

@app.get("/quota/status", response_model=QuotaStatusResponse)
@limiter.limit("50/minute")
async def quota_status_api(request: Request, user_id: str = Query(...), user=Depends(verify_token)):
    return quota_service.get_status(user_id).to_dict()


@app.post("/billing/razorpay/order")
@limiter.limit("20/minute")
async def create_razorpay_order_api(request: Request, query: BillingOrderRequest, user=Depends(verify_token)):
    try:
        return billing_service.create_warlord_order(query.user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/billing/razorpay/verify")
@limiter.limit("20/minute")
async def verify_razorpay_payment_api(request: Request, query: BillingVerifyRequest, user=Depends(verify_token)):
    try:
        return billing_service.verify_warlord_payment(
            user_id=query.user_id,
            order_id=query.razorpay_order_id or "",
            payment_id=query.razorpay_payment_id,
            signature=query.razorpay_signature,
            subscription_id=query.razorpay_subscription_id or "",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/billing/razorpay/webhook")
@limiter.limit("100/minute")
async def razorpay_webhook_api(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not billing_service.verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON")
    return billing_service.handle_webhook_event(payload)


@app.post("/billing/emperor/request", response_model=SimpleResponse)
@limiter.limit("10/minute")
async def emperor_request_api(request: Request, query: EmperorRequest, user=Depends(verify_token)):
    result = billing_service.create_emperor_request(query.user_id, query.message or "")
    return {"message": result["message"]}

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


#------- Emperor APIS -------#
@app.get("/emperor_set")
@limiter.limit("10/minute")
async def emperor_set(request:Request, query: Emperor_Key ,user=Depends(verify_token)):
    return emperor_key(email= query.email,amount= query.amount,password= query.password)