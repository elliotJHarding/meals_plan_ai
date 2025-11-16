#!/usr/bin/env python3
"""
Test script to verify OAuth authentication is working correctly.

This script demonstrates how to:
1. Make a request without authentication (should get 401)
2. Make a request with invalid token (should get 401)
3. Make a request with valid token format (will fail at Google API if token is invalid)

To get a real OAuth token for testing:
1. Go to https://developers.google.com/oauthplayground/
2. Select "Google AI Platform API v1" or relevant API
3. Authorize and get the access token
4. Use that token in the test below
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"


def test_no_auth():
    """Test request without authentication - should get 401"""
    print("\n=== Test 1: No Authentication ===")
    response = requests.post(
        f"{BASE_URL}/ingredient-metadata",
        json={"ingredient_name": "flour"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 401, "Should return 401 without auth"
    print("✓ Correctly rejected request without authentication")


def test_invalid_auth_format():
    """Test request with invalid auth format - should get 401"""
    print("\n=== Test 2: Invalid Auth Format ===")
    response = requests.post(
        f"{BASE_URL}/ingredient-metadata",
        headers={"Authorization": "InvalidFormat"},
        json={"ingredient_name": "flour"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 401, "Should return 401 with invalid format"
    print("✓ Correctly rejected request with invalid auth format")


def test_with_bearer_token(token: str):
    """Test request with Bearer token"""
    print("\n=== Test 3: With Bearer Token ===")
    print(f"Using token: {token[:20]}...")

    response = requests.post(
        f"{BASE_URL}/ingredient-metadata",
        headers={"Authorization": f"Bearer {token}"},
        json={"ingredient_name": "flour"}
    )
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print("✓ Successfully authenticated and got response")
    elif response.status_code == 401:
        print(f"Response: {response.json()}")
        print("✗ Token was rejected (expired or invalid)")
    else:
        print(f"Response: {response.text}")
        print(f"✗ Unexpected status code: {response.status_code}")


def test_chat_endpoint(token: str):
    """Test the chat endpoint with authentication"""
    print("\n=== Test 4: Chat Endpoint ===")
    print(f"Using token: {token[:20]}...")

    request_data = {
        "dayOfWeek": 1735689600000,
        "calendarEvents": [],
        "availableMeals": [
            {
                "name": "Spaghetti Carbonara",
                "effort": "MEDIUM",
                "serves": 4,
                "prepTimeMinutes": 30
            }
        ],
        "recentMealPlans": [],
        "conversationHistory": []
    }

    response = requests.post(
        f"{BASE_URL}/chat-meal-plan-day",
        headers={"Authorization": f"Bearer {token}"},
        json=request_data
    )
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Got {len(data['suggestions'])} suggestions")
        print(f"Reasoning: {data['reasoning'][:100]}...")
        print("✓ Successfully authenticated and got meal suggestions")
    elif response.status_code == 401:
        print(f"Response: {response.json()}")
        print("✗ Token was rejected (expired or invalid)")
    else:
        print(f"Response: {response.text[:200]}")
        print(f"✗ Unexpected status code: {response.status_code}")


if __name__ == "__main__":
    print("OAuth Authentication Test Suite")
    print("=" * 50)

    # Test 1 & 2: Should always work
    test_no_auth()
    test_invalid_auth_format()

    # Test 3 & 4: Requires a real OAuth token
    print("\n" + "=" * 50)
    print("For Tests 3 & 4, you need a real Google OAuth token.")
    print("Get one from: https://developers.google.com/oauthplayground/")
    print("=" * 50)

    # Example token (you need to replace this with a real one)
    # To run the full test:
    # 1. Get a token from OAuth Playground
    # 2. Uncomment the lines below and paste your token
    # 3. Run the script

    # YOUR_OAUTH_TOKEN = "paste_your_token_here"
    # test_with_bearer_token(YOUR_OAUTH_TOKEN)
    # test_chat_endpoint(YOUR_OAUTH_TOKEN)

    print("\n" + "=" * 50)
    print("Basic authentication tests passed!")
    print("To test with a real token, uncomment the test calls above.")
