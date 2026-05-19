# Rate Limiting Guide - Agentic Planner

## Overview

The Agentic Planner API implements **rate limiting** using **slowapi**, a rate limiting library for FastAPI. This guide explains how rate limiting works, how to modify limits, and best practices for handling rate-limited requests.

---

## How Rate Limiting Works

### Implementation Details

Rate limiting is implemented using slowapi's `Limiter` class with the following configuration:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

limiter = Limiter(key_func=get_remote_address)
app.add_middleware(SlowAPIMiddleware)
```

### Key Mechanism

- **Key Function**: `get_remote_address` - Rate limits are applied per client IP address
- **Middleware**: `SlowAPIMiddleware` - Processes rate limit decorators on endpoints
- **Exception Handler**: Catches `RateLimitExceeded` exceptions and returns HTTP 429 status

### Rate Limit Format

Rate limits are specified in the format: `"<requests>/<time_window>"`

Examples:
- `"5/minute"` - 5 requests per minute
- `"30/minute"` - 30 requests per minute
- `"100/minute"` - 100 requests per minute

---

## Current Rate Limit Configuration

### By Endpoint Category

| Category | Endpoint | Limit | Reason |
|----------|----------|-------|--------|
| **System** | `GET /` | 100/min | Low-priority endpoint |
| **System** | `GET /health` | 100/min | Health checks allowed frequently |
| **Authentication** | `POST /signup` | 5/min | Prevent brute-force registration |
| **Authentication** | `POST /signin` | 5/min | Prevent brute-force login attempts |
| **Authentication** | `POST /refresh` | 10/min | Session token refresh |
| **Authentication** | `POST /signout` | 10/min | Session termination |
| **Conversations** | `POST /create_conversation` | 50/min | Create conversation threads |
| **Conversations** | `DELETE /delete_conversation` | 50/min | Delete conversation threads |
| **Conversations** | `GET /see_conversation` | 50/min | List user conversations |
| **Messages** | `GET /see_message` | 50/min | Fetch conversation messages |
| **Agent Query** | `POST /query` | 30/min | **Critical LLM processing** |
| **Preferences** | `POST /add_preference` | 50/min | Create user preferences |
| **Preferences** | `POST /edit_preference` | 50/min | Update user preferences |
| **Preferences** | `POST /see_preference` | 50/min | View user preferences |
| **Preferences** | `DELETE /delete_preference` | 50/min | Delete user preferences |
| **Debug** | `GET /debug/trace/{request_id}` | 100/min | Trace inspection |

---

## Modifying Rate Limits

### Step 1: Update the Decorator

Find the endpoint in `main.py` and modify the `@limiter.limit()` decorator:

**Before:**
```python
@app.post("/query")
@limiter.limit("30/minute")
async def query_travel_agent(request: Request, query: QueryRequest, user=Depends(verify_token)):
    ...
```

**After (increased to 50/min):**
```python
@app.post("/query")
@limiter.limit("50/minute")
async def query_travel_agent(request: Request, query: QueryRequest, user=Depends(verify_token)):
    ...
```

### Step 2: Add Request Parameter

**Important**: All decorated endpoints must accept a `Request` parameter as the first argument:

```python
async def endpoint_name(request: Request, ...other_params):
    # request parameter is required for slowapi to work
```

### Step 3: Update Documentation

Update `API_DOCUMENTATION.md` to reflect the new rate limit in the endpoint description.

### Example: Increasing Query Endpoint Limit

```python
# In main.py
@app.post("/query")
@limiter.limit("50/minute")  # Changed from 30/minute
async def query_travel_agent(request: Request, query: QueryRequest, user=Depends(verify_token)):
    try:
        result = await query_helper(query)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
```

---

## Response Headers

Every API response includes rate limiting information in HTTP headers:

```
X-RateLimit-Limit: 30          # Maximum requests allowed
X-RateLimit-Remaining: 28      # Requests remaining in current window
X-RateLimit-Reset: 1726579560  # Unix timestamp of window reset
```

### Client-Side Implementation

```python
import requests
import time

def check_rate_limits(response):
    """Extract rate limit info from response headers"""
    limit = response.headers.get('X-RateLimit-Limit')
    remaining = response.headers.get('X-RateLimit-Remaining')
    reset_time = response.headers.get('X-RateLimit-Reset')
    
    print(f"Rate Limit: {limit}")
    print(f"Remaining: {remaining}")
    print(f"Reset at: {reset_time}")
    
    return {
        'limit': int(limit) if limit else None,
        'remaining': int(remaining) if remaining else None,
        'reset': int(reset_time) if reset_time else None
    }
```

---

## Error Handling

### Rate Limit Exceeded Response

When a client exceeds the rate limit, they receive:

```
HTTP/1.1 429 Too Many Requests

{
  "error": "Rate limit exceeded. Please try again later."
}
```

### Retry Strategy (Recommended)

Implement exponential backoff with jitter:

```python
import time
import random
import requests

def call_with_backoff(url, data, max_retries=3):
    """Call API with exponential backoff retry strategy"""
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, timeout=10)
            
            if response.status_code == 429:
                # Rate limited
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Rate limited. Retrying in {wait_time:.2f}s...")
                time.sleep(wait_time)
                continue
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            if attempt == max_retries - 1:
                raise
            
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait_time)
    
    raise Exception("Max retries exceeded")

# Usage
result = call_with_backoff(
    "http://localhost:8000/query",
    {"question": "...", "user_id": "...", "conversation_id": "..."}
)
```

---

## Best Practices

### 1. Monitor Remaining Requests
```python
# Check X-RateLimit-Remaining before making requests
remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
if remaining < 5:
    print("Approaching rate limit. Consider backing off.")
```

### 2. Batch Requests When Possible
```python
# Instead of multiple /query calls, batch preferences
# Combine multiple operations into single requests
```

### 3. Cache Results Locally
```python
# Cache API responses to reduce duplicate requests
import functools
import time

@functools.lru_cache(maxsize=128)
def get_user_preferences(user_id):
    """Cached preference fetching"""
    response = requests.post(f"{API_URL}/see_preference", 
                           json={"user_id": user_id})
    return response.json()
```

### 4. Implement Client-Side Rate Limiting
```python
from datetime import datetime, timedelta
import time

class RateLimitedClient:
    def __init__(self, requests_per_minute=30):
        self.requests_per_minute = requests_per_minute
        self.requests = []
    
    def wait_if_needed(self):
        """Wait if we've exceeded our rate limit"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Remove old requests outside the window
        self.requests = [r for r in self.requests if r > minute_ago]
        
        if len(self.requests) >= self.requests_per_minute:
            sleep_time = 60 - (now - self.requests[0]).total_seconds()
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.requests.append(now)
```

### 5. Understand Your Quota
```python
# For authentication: 5 requests/min per IP
# For queries: 30 requests/min per IP  
# Plan your API calls accordingly
```

---

## Troubleshooting

### Issue: Getting 429 (Too Many Requests) Errors

**Causes:**
- Too many rapid requests to the same endpoint
- Multiple clients from same IP address (shared network)
- Polling endpoints too frequently

**Solutions:**
- Implement exponential backoff
- Add jitter to retry attempts
- Cache responses locally
- Increase time between requests
- Request rate limit increase if needed

### Issue: Rate Limits Don't Seem to Be Applied

**Check:**
1. Verify `@limiter.limit()` decorator is present
2. Verify `request: Request` parameter is in function signature
3. Ensure `SlowAPIMiddleware` is added to app
4. Check that endpoint is actually being called (add logging)

### Issue: Need Different Limits for Different Users

**Note:** Current implementation uses IP-based rate limiting. For user-based limits:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

def get_user_id(request: Request):
    # Extract user ID from request
    auth_header = request.headers.get("Authorization")
    # Parse and return user ID
    return user_id

limiter = Limiter(key_func=get_user_id)
```

---

## Performance Impact

Rate limiting adds minimal overhead:
- **Lookup Time**: ~1ms per request (in-memory storage)
- **Memory Usage**: Minimal (uses sliding window algorithm)
- **Latency Increase**: <1% typical impact

---

## Future Enhancements

Potential improvements to the rate limiting system:

1. **Dynamic Rate Limits**: Adjust limits based on server load
2. **Tier-Based Limits**: Different limits for premium vs free users
3. **Endpoint-Specific Strategies**: Unique algorithms per endpoint
4. **Distributed Rate Limiting**: Support for multi-server deployments using Redis
5. **Metrics & Monitoring**: Track rate limit violations and adjust accordingly

---

## Related Files

- **Main Implementation**: [`main.py`](main.py)
- **API Documentation**: [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)
- **Dependencies**: [`pyproject.toml`](pyproject.toml)
- **Slowapi Documentation**: https://slowapi.readthedocs.io/

---

## Support

For questions or issues with rate limiting:
1. Check the [slowapi documentation](https://slowapi.readthedocs.io/)
2. Review this guide's troubleshooting section
3. Examine the implementation in `main.py`
4. Check API response headers for rate limit information
