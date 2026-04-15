from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from typing import Union

# ------------------ COMMON ------------------ #

class QueryRequest(BaseModel):
    question: str
    user_id: str
    conversation_id: str

class SimpleMessage(BaseModel):
    message: str


class QueryResponse(BaseModel):
    reply: str  # The plain-text markdown reply from the AI agent
    
# ------------------ AUTH ------------------ #

class AuthRequest(BaseModel):
    email: EmailStr
    password: str

class SignupResponse(BaseModel):
    message: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str

class RefreshRequest(BaseModel):
    refresh_token: str



class SignOutResponse(BaseModel):
    message: str


# ------------------ PREFERENCES ------------------ #

class PreferenceCreate(BaseModel):
    user_id: str
    dietary_preference: str
    preference_id: str


class PreferenceUpdate(BaseModel):
    user_id: str
    dietary_preference: str


class PreferenceDelete(BaseModel):
    user_id: str


class PreferenceResponse(BaseModel):
    id: str
    user_id: str
    dietary_preference: str
    preference_id: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# ------------------ CONVERSATIONS ------------------ #

class ConversationCreate(BaseModel):
    user_id: str
    title: str

class ConversationCreateResponse(BaseModel):
    conversation_id: str

class ConversationDelete(BaseModel):
    conversation_id: str


class ConversationResponse(BaseModel):
    id: str
    user_id: str

class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: Optional[datetime]

class ConversationRequest(BaseModel):
    user_id: str

class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]


# ------------------ MESSAGES ------------------ #

class MessageCreate(BaseModel):
    user_id: str
    conversation_id: str
    role: str  # "user" | "assistant"
    content: str

# MessageContent is no longer needed — the controller now always stores
# a plain string in the DB instead of a dict, so content is always str.
class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str  # Always a plain string (markdown text)
    created_at: Optional[datetime]

class MessageRequest(BaseModel):
    conversation_id: str

class MessageListResponse(BaseModel):
    messages: List[MessageResponse]



  # ------------------ PREFERENCES ------------------ #  
class AddPreferenceRequest(BaseModel):
    user_id: str
    dietary_preference: Dict[str, Any] = {}
    custom_preference: Optional[str] = ""

class UpdatePreferenceRequest(BaseModel):
    user_id: str
    dietary_preference: Dict[str, Any] = {}
    custom_preference: Optional[str] = ""

class DeletePreferenceRequest(BaseModel):
    user_id: str

class SimpleResponse(BaseModel):
    message: str

class SeePreferenceRequest(BaseModel):
    user_id: str