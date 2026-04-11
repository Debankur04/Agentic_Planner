import os
import redis
import json
import hashlib

redis_url = os.getenv("REDIS_URL")

if redis_url:
    # 🔥 Render / production
    redis_client = redis.from_url(redis_url, decode_responses=True)
else:
    # 🧪 Local / docker-compose fallback
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))

    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        decode_responses=True
    )

def make_cache_key(tool_name: str, args: dict) -> str:
    raw = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
    return "tool_cache:" + hashlib.md5(raw.encode()).hexdigest()

def get_cache(key: str):
    data = redis_client.get(key)
    return json.loads(data) if data else None

def set_cache(key: str, value, ttl=300):
    redis_client.setex(key, ttl, json.dumps(value))
