import asyncio
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.graph.builder import TravelPlannerGraph
from app.schemas.outputs import WorkflowResult
from app.services.trace import StreamEvent

router = APIRouter()

planner_graph = TravelPlannerGraph()

@router.post("/plan")
async def plan_trip(request: Request):
    payload = await request.json()
    user_query = payload.get("user_query")
    if not user_query:
        raise HTTPException(status_code=400, detail="user_query is required")

    event_queue: asyncio.Queue = asyncio.Queue()

    async def producer():
        try:
            result = await planner_graph.run(user_query, event_queue)
            await event_queue.put({"type": "completion", "payload": result.dict()})
        except Exception as exc:
            await event_queue.put({"type": "error", "payload": {"message": str(exc)}})
        finally:
            await event_queue.put(None)

    asyncio.create_task(producer())

    async def event_generator():
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event['payload'])}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
