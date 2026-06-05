import pytest
from fastapi.testclient import TestClient
from main import app
from service.verify_token import verify_token
from unittest.mock import patch


app.dependency_overrides[verify_token] = lambda: {"id": "test_user"}

client = TestClient(app)

def test_health_check():
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["backend"] == "active"
    assert "models" in data

@patch("main.create_conversation")
def test_create_conversation(mock_create_convo):
    """Test conversation creation with mocked DB"""
    mock_create_convo.return_value = "mock_convo_id_123"
    
    response = client.post("/create_conversation", json={
        "user_id": "test_user",
        "title": "Test Trip to Paris"
    })
    
    assert response.status_code == 200
    assert response.json()["conversation_id"] == "mock_convo_id_123"

@patch("main.query_helper")
def test_query_response_format(mock_query_helper):
    """Test that /query returns the unified API response envelope."""
    async def fake_query_helper(query):
        return {"reply": "Final Itinerary Plan", "trace_id": "req_test"}

    mock_query_helper.side_effect = fake_query_helper
    
    response = client.post("/query", json={
        "question": "Plan a trip to London",
        "user_id": "test_user_123",
        "conversation_id": "convo_999"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["reply"] == "Final Itinerary Plan"
    assert data["trace_id"] == "req_test"

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
