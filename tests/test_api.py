import pytest
from fastapi.testclient import TestClient
from main import app
from unittest.mock import patch, AsyncMock
import json

client = TestClient(app)

def test_health_check():
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "routing" in data

@patch("service.supabase_service.create_conversation")
def test_create_conversation(mock_create_convo):
    """Test conversation creation with mocked DB"""
    mock_create_convo.return_value = "mock_convo_id_123"
    
    response = client.post("/create_conversation", json={
        "user_id": "test_user",
        "title": "Test Trip to Paris"
    })
    
    assert response.status_code == 200
    assert response.json()["message"] == "Conversation created successfully"

@patch("backend.controller.query_controller.travel_engine.process_query")
def test_query_streaming_format(mock_process_query):
    """Test that the /query endpoint streams using SSE correctly"""
    # Mock the process query to return immediately
    # We must mock it correctly based on the return type in query_controller
    mock_process_query.return_value = ("Final Itinerary Plan", "test_pref", "test_history")
    
    response = client.post("/query", json={
        "question": "Plan a trip to London",
        "user_id": "test_user_123",
        "conversation_id": "convo_999"
    })
    
    # Check if the response is a streaming response
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    content = response.text
    # Check if it adheres to SSE format
    assert content.startswith("data: ")
    assert "final_reply" in content
    assert "Final Itinerary Plan" in content

def test_auth_signup_validation():
    """Test that auth endpoints validate payloads correctly"""
    response = client.post("/signup", json={
        # Missing required fields like email and password
        "username": "test"
    })
    # Should throw a 422 Unprocessable Entity
    assert response.status_code == 422

@pytest.mark.skip(reason="Planned Architecture Feature - V2.0")
def test_download_itinerary():
    """Test the planned download itinerary endpoint"""
    response = client.get("/download_itinerary/test_convo_id")
    assert response.status_code == 200
    assert response.headers["content-type"] in ["application/pdf", "text/markdown"]
