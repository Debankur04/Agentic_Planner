#!/usr/bin/env python
"""
Test script to verify that the /query endpoint returns direct JSON response
instead of streaming chunks.
"""
import requests
import json
import sys

# Test endpoint
QUERY_ENDPOINT = "http://localhost:8000/query"

# Sample test request (you'll need valid auth token)
test_payload = {
    "question": "What's the weather in Paris?",
    "user_id": "test_user_123",
    "conversation_id": "conv_123"
}

# Dummy token for testing (replace with actual token if needed)
headers = {
    "Authorization": "Bearer test_token"
}

print("=" * 60)
print("Testing Direct LLM Response (No Streaming)")
print("=" * 60)
print(f"\nEndpoint: POST {QUERY_ENDPOINT}")
print(f"Payload: {json.dumps(test_payload, indent=2)}")
print("\n" + "-" * 60)

try:
    response = requests.post(QUERY_ENDPOINT, json=test_payload, headers=headers, timeout=10)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print("\nResponse Body:")
    
    # Try to parse as JSON
    try:
        json_response = response.json()
        print(json.dumps(json_response, indent=2))
        
        # Check for streaming indicators
        if isinstance(json_response, dict):
            if "reply" in json_response:
                print("\n✅ SUCCESS: Direct JSON response received!")
                print(f"   - Reply length: {len(json_response['reply'])} chars")
            elif "error" in json_response:
                print(f"\n⚠️  Error in response: {json_response['error']}")
            else:
                print(f"\n⚠️  Unexpected response format: {list(json_response.keys())}")
    except json.JSONDecodeError:
        print("Raw response (not JSON):")
        print(response.text[:500])
        
        # Check if it's SSE format (streaming)
        if "data:" in response.text:
            print("\n❌ FAIL: Still receiving streaming format (data: chunks)")
        else:
            print("\n⚠️  Response is not JSON or streaming")
            
except requests.exceptions.ConnectionError:
    print("❌ FAIL: Could not connect to server at localhost:8000")
    print("   Make sure the server is running with: uvicorn main:app --reload")
except requests.exceptions.Timeout:
    print("❌ FAIL: Request timed out")
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}: {e}")

print("\n" + "=" * 60)
