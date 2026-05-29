from fastapi import FastAPI
from app.api import router

app = FastAPI(title="LangGraph Travel Planner")
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {"status": "ok", "service": "langgraph_travel_planner"}
