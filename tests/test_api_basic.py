from fastapi.testclient import TestClient
from app.main import build_app


def test_health_endpoint():
    app = build_app()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "app" in data


def test_tools_endpoint_auth():
    app = build_app()
    client = TestClient(app)
    r = client.get("/tools")
    assert r.status_code == 200
    tool_names = {tool["name"] for tool in r.json()["tools"]}
    assert "book_room" not in tool_names
    assert "get_booking" not in tool_names
