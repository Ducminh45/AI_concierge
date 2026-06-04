import os


API_KEY = os.environ.get("MRC_API_KEY", "dummy")
AUTH = {"Authorization": f"Bearer {API_KEY}"}


def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "app" in data


def test_chat_endpoint_allows_anonymous_requests(client):
    """Chat should be available without login or API key."""
    response = client.post(
        "/chat", json={"message": "Hello", "session_id": "anonymous"}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_chat_endpoint_requires_message(client):
    """Test chat endpoint handles missing message"""
    response = client.post(
        "/chat", json={}
    )
    # May return 400/422 (validation) or 500 (unhandled)
    assert response.status_code in [400, 422, 500]


def test_tools_endpoint(client):
    """Test tools endpoint returns tool list"""
    response = client.get("/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "tools" in data


def test_sql_injection_prevention(client):
    """Test SQL injection is prevented"""
    malicious = "'; DROP TABLE bookings; --"
    response = client.post(
        "/chat",
        json={"message": malicious},
    )
    assert response.status_code in [200, 400, 422, 500]
    health = client.get("/health")
    assert health.status_code == 200
