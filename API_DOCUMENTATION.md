# Agentic Planner API Documentation

This documentation outlines the RESTful endpoints available in the **Agentic Planner** built using FastAPI.

## Base URL
All endpoints are relative to the root URL (e.g., `http://localhost:8000`).

---

## Rate Limiting

The API implements rate limiting using **slowapi** to protect against abuse and ensure fair resource allocation. All endpoints are protected with specific rate limits based on their usage patterns.

### Rate Limit Headers
All API responses include the following headers:
- `X-RateLimit-Limit`: Maximum requests allowed in the current window
- `X-RateLimit-Remaining`: Number of requests remaining in the current window
- `X-RateLimit-Reset`: Unix timestamp when the current limit window resets

### Rate Limit Strategy by Endpoint Category

#### Authentication Endpoints
- **Signup & Signin**: **5 requests per minute**
  - These endpoints are strictly rate limited to prevent brute force attacks
  - Applies per client IP address
  
- **Token Refresh & Signout**: **10 requests per minute**
  - Moderate limit for session management

#### Core Agent Query
- **Query Endpoint** (`POST /query`): **30 requests per minute**
  - Protects against resource-intensive LLM processing
  - Applies per client IP address

#### Conversation Management
- **Create/Delete/View Conversations**: **50 requests per minute**
- **View Messages**: **50 requests per minute**

#### Preferences Management
- **Add/Edit/View/Delete Preferences**: **50 requests per minute**

#### System Endpoints
- **Health Check & Root**: **100 requests per minute**
- **Debug Trace**: **100 requests per minute**

### Rate Limit Error Response
When a rate limit is exceeded, the API returns a `429 Too Many Requests` response:

```json
{
  "error": "Rate limit exceeded. Please try again later."
}
```

### Best Practices
1. **Check remaining requests**: Monitor the `X-RateLimit-Remaining` header to avoid hitting limits
2. **Implement exponential backoff**: If rate limited, wait before retrying
3. **Batch requests when possible**: Combine multiple queries into fewer requests
4. **Cache results**: Store responses locally to reduce API calls
5. **Distribute requests**: Spread requests over time rather than in bursts

### Handling Rate Limits in Client Code

Example implementation (Python with exponential backoff):
```python
import time
import requests

def call_with_retry(url, data, max_retries=3):
    for attempt in range(max_retries):
        response = requests.post(url, json=data)
        
        if response.status_code == 429:
            # Extract retry delay from headers if available
            retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
            print(f"Rate limited. Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
            continue
            
        return response
    
    raise Exception("Max retries exceeded")
```

---

## 0. System Health

### `GET /health`
Returns the operational status of the backend API, Redis connection, and detailed routing health metrics for all configured language models.
*   **Rate Limit**: 100 requests per minute
*   **Response**: JSON object outlining system functionality, including granular stats per model (circuit statuses, latencies, etc).

---

## 1. Authentication
Endpoints for handling user registration and login.

### `POST /signup`
Registers a new user in the system.
*   **Rate Limit**: 5 requests per minute
*   **Request Body (`AuthRequest`)**:
    ```json
    {
        "email": "user@example.com",
        "password": "securepassword123"
    }
    ```
*   **Response (`SignupResponse`)**: returns a simple validation message (e.g., success).

### `POST /signin`
Authenticates an existing user.
*   **Rate Limit**: 5 requests per minute
*   **Request Body (`AuthRequest`)**:
    ```json
    {
        "email": "user@example.com",
        "password": "securepassword123"
    }
    ```
*   **Response (`AuthResponse`)**: Returns `{"access_token": "...", "refresh_token": "...", "user_id": "..."}`.

### `POST /refresh`
Refreshes an access token using a valid refresh token.
*   **Rate Limit**: 10 requests per minute
*   **Request Body (`RefreshRequest`)**:
    ```json
    {
        "refresh_token": "string"
    }
    ```
*   **Response (`AuthResponse`)**: Returns `{"access_token": "...", "refresh_token": "...", "user_id": "..."}`.

### `POST /signout`
Ends the current user's authenticated session.
*   **Rate Limit**: 10 requests per minute
*   **Response (`SignOutResponse`/`SimpleMessage`)**: `{"message": "Signed out successfully"}`

---

## 2. Conversations
Manage multiple threaded chat sessions for users.

### `POST /create_conversation`
Creates a brand new conversation thread.
*   **Rate Limit**: 50 requests per minute
*   **Request Body (`ConversationCreate`)**:
    ```json
    {
        "user_id": "string",
        "title": "Trip to Japan"
    }
    ```
*   **Response (`SimpleMessage`)**: Acknowledges creation with the newly generated `convo_id`.

### `DELETE /delete_conversation`
Removes an existing conversation thread entirely.
*   **Rate Limit**: 50 requests per minute
*   **Request Body (`ConversationDelete`)**:
    ```json
    {
        "conversation_id": "string"
    }
    ```
*   **Response (`SimpleMessage`)**: `{"message": "Conversation deleted successfully"}`

### `GET /see_conversation`
Retrieves all accessible conversations for a given user.
*   **Rate Limit**: 50 requests per minute
*   **Query Parameters**:
    *   `user_id` (string): The unique identifier of the user.
*   **Response (`ConversationListResponse`)**:
    ```json
    {
      "conversations": [
        {
          "id": "string",
          "user_id": "string",
          "title": "string",
          "created_at": "datetime"
        }
      ]
    }
    ```

---

## 3. Messages
Endpoints handling the explicit fetch of single conversation messages.

### `GET /see_message`
Retrieves past chat interactions from a specific conversation.
*   **Rate Limit**: 50 requests per minute
*   **Query Parameters**:
    *   `conversation_id` (string): The unique conversation ID.
*   **Response (`MessageListResponse`)**:
    ```json
    {
      "messages": [
        {
          "id": "string",
          "conversation_id": "string",
          "role": "user" | "assistant",
          "content": "string",
          "created_at": "datetime"
        }
      ]
    }
    ```

---

## 4. Query & Agent Interactions
The primary engine endpoint for the AI workflow.

### `POST /query`
Performs an entire LangGraph execution pipeline: saving user prompts, extracting recent limited message history, combining user preferences, fetching conversational memory blocks, tracking state, and committing agent outputs.

**Note:** This endpoint now supports **Server-Sent Events (SSE)** streaming and **Human-In-The-Loop (HITL)** interrupts. If the agent pauses to ask for clarification, it will stream the question. When the user replies with the same `conversation_id`, the agent resumes the graph exactly where it left off.

*   **Rate Limit**: 30 requests per minute (strictly limited to protect resource-intensive LLM processing)
*   **Request Body (`QueryRequest`)**:
    ```json
    {
        "question": "What's the best time to visit Kyoto?",
        "user_id": "string",
        "conversation_id": "string"
    }
    ```
*   **Response (`text/event-stream`)**:
    Streams token chunks continuously until completion.
    ```text
    data: {"type": "chunk", "content": "The"}
    
    data: {"type": "chunk", "content": " best"}
    
    ...
    
    data: {"final_reply": "The best time to visit Kyoto is..."}
    ```
    If an error or guardrail violation occurs, it streams:
    ```text
    data: {"error": "Message violation detected"}
    ```

### `GET /download_itinerary/{conversation_id}` (Planned Feature)
Generates a downloadable Markdown or PDF format of the final generated itinerary.
*   **Path Parameters**:
    *   `conversation_id` (string): The unique conversation ID.
*   **Response**: A `FileResponse` with the `text/markdown` or `application/pdf` MIME type.

---

## 5. Preferences
Endpoints meant to manage dynamic user preferences.

### `POST /add_preference`
Adds complex serialized preference strings to a user's DB.
*   **Rate Limit**: 50 requests per minute
*   **Request Body (`AddPreferenceRequest`)**:
    ```json
    {
        "user_id": "string",
        "dietary_preference": {"vegan": true},
        "custom_preference": "Likes window seats"
    }
    ```
*   **Response (`SimpleResponse`)**: Success message.

### `POST /edit_preference`
Modifies the specified user preferences.
*   **Rate Limit**: 50 requests per minute
*   **Request Body (`UpdatePreferenceRequest`)**: Same schema as add_preference.
*   **Response (`SimpleResponse`)**: Success message.

### `POST /see_preference`
Retrieves a specific user's saved preferences.
*   **Rate Limit**: 50 requests per minute
*   **Request Body (`SeePreferenceRequest`)**:
    ```json
    {
        "user_id": "string"
    }
    ```
*   **Response**: Dictionary of the database preference contents.

### `DELETE /delete_preference`
Clears a specified user's preference record.
*   **Rate Limit**: 50 requests per minute
*   **Request Body (`DeletePreferenceRequest`)**:
    ```json
    {
        "user_id": "string"
    }
    ```
*   **Response (`SimpleResponse`)**: Success message.

---

## 6. Observability & Debugging

### `GET /debug/trace/{request_id}`
Retrieves the execution trace generated during a complex LLM query. Attempts to fetch from Redis Cache initially before falling back to MongoDB traces.
*   **Rate Limit**: 100 requests per minute
*   **Path Parameters**:
    *   `request_id` (string): The generated request trace ID.
*   **Response**: Complex JSON dictionary outlining nested execution spans, latencies, agent state, and responses.
