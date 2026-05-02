from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URL"))

# 🔥 test connection
try:
    client.admin.command("ping")
    print("✅ Mongo connected")
except Exception as e:
    print("❌ Connection failed:", e)

db = client["agent_db"]
trace_collection = db["traces"]
intent_collection = db['intent']

def save_trace(trace_dict):
    print("🔥 CALLED save_trace")
    result = trace_collection.insert_one(trace_dict)
    print("✅ Inserted:", result.inserted_id)
def get_trace_from_db(trace_id): 
    return trace_collection.find_one({"request_id": trace_id})

def save_intent(query,intent):
    intent_trace = {query: intent}
    result = intent_collection.insert_one(intent_trace)
    print("✅ Inserted:", result.inserted_id)