from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ------------------ COMMON ------------------ #

class QueryRequest(BaseModel):
    question: str
    user_id: str
    conversation_id: str

class SimpleMessage(BaseModel):
    message: str


class QueryResponse(BaseModel):
    answer: str
    
# ------------------ AUTH ------------------ #

class AuthRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    user_id: str


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


class ConversationDelete(BaseModel):
    conversation_id: str


class ConversationResponse(BaseModel):
    id: str
    user_id: str


# ------------------ MESSAGES ------------------ #

class MessageCreate(BaseModel):
    user_id: str
    conversation_id: str
    role: str  # "user" | "assistant"
    content: str


class MessageResponse(BaseModel):
    id: str
    user_id: str
    conversation_id: str
    role: str
    content: str
    created_at: Optional[datetime]

class MessageRequest(BaseModel):
    conversation_id: str

class MessageListResponse(BaseModel):
    messages: List[MessageResponse]