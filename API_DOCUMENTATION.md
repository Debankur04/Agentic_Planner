# Agentic Planner API Documentation

This documentation outlines the RESTful endpoints available in the **Agentic Planner** built using FastAPI.

## Base URL
All endpoints are relative to the root URL (e.g., `http://localhost:8000`).

---

## 0. System Health

### `GET /health`
Returns the operational status of the backend API, Redis connection, and detailed routing health metrics for all configured language models.
*   **Response**: JSON object outlining system functionality, including granular stats per model (circuit statuses, latencies, etc).

---

## 1. Authentication
Endpoints for handling user registration and login.

### `POST /signup`
Registers a new user in the system.
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
*   **Request Body (`RefreshRequest`)**:
    ```json
    {
        "refresh_token": "string"
    }
    ```
*   **Response (`AuthResponse`)**: Returns `{"access_token": "...", "refresh_token": "...", "user_id": "..."}`.

### `POST /signout`
Ends the current user's authenticated session.
*   **Response (`SignOutResponse`/`SimpleMessage`)**: `{"message": "Signed out successfully"}`

---

## 2. Conversations
Manage multiple threaded chat sessions for users.

### `POST /create_conversation`
Creates a brand new conversation thread.
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
*   **Request Body (`ConversationDelete`)**:
    ```json
    {
        "conversation_id": "string"
    }
    ```
*   **Response (`SimpleMessage`)**: `{"message": "Conversation deleted successfully"}`

### `GET /see_conversation`
Retrieves all accessible conversations for a given user.
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
Performs an entire LangGraph execution pipeline: saving user prompts, extracting recent limited message history (last 8 limits), combining user preferences, fetching conversational memory blocks, tracking state, and committing agent outputs to memory limits.
*   **Request Body (`QueryRequest`)**:
    ```json
    {
        "question": "What's the best time to visit Kyoto?",
        "user_id": "string",
        "conversation_id": "string"
    }
    ```
*   **Response (`QueryResponse`)**:
    ```json
    {
        "answer": "The best time to visit Kyoto is..."
    }
    ```

---

## 5. Preferences
Endpoints meant to manage dynamic user preferences.

### `POST /add_preference`
Adds complex serialized preference strings to a user's DB.
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
*   **Request Body (`UpdatePreferenceRequest`)**: Same schema as add_preference.
*   **Response (`SimpleResponse`)**: Success message.

### `POST /see_preference`
Retrieves a specific user's saved preferences.
*   **Request Body (`SeePreferenceRequest`)**:
    ```json
    {
        "user_id": "string"
    }
    ```
*   **Response**: Dictionary of the database preference contents.

### `DELETE /delete_preference`
Clears a specified user's preference record.
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
*   **Path Parameters**:
    *   `request_id` (string): The generated request trace ID.
*   **Response**: Complex JSON dictionary outlining nested execution spans, latencies, agent state, and responses.
