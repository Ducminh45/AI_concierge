import os
import pytest
from datetime import datetime, timedelta, timezone

from app.auth.security import APIKeyManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeSession:
    """Context manager that mimics DatabaseManager.session()."""

    def __init__(self, db_path: str):
        self._path = db_path

    def __enter__(self):
        import sqlite3

        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        return self._conn

    def __exit__(self, *exc):
        self._conn.commit()
        self._conn.close()


class _FakeDB:
    """Minimal DB wrapper that mimics DatabaseManager for unit tests."""

    def __init__(self, db_path: str):
        import sqlite3

        self._path = db_path
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.close()

    def session(self):
        return _FakeSession(self._path)


@pytest.fixture()
def manager(tmp_path):
    db_path = str(tmp_path / "test_keys.db")
    db = _FakeDB(db_path)
    return APIKeyManager(db)


# ---------------------------------------------------------------------------
# Unit tests — pure Python, no FastAPI
# ---------------------------------------------------------------------------


class TestCreateKey:
    def test_returns_mr_prefix(self, manager):
        key = manager.create_key("alice")
        assert key.startswith("mr_")

    def test_key_is_unique(self, manager):
        k1 = manager.create_key("alice")
        k2 = manager.create_key("alice")
        assert k1 != k2


class TestVerifyKey:
    def test_valid_key_returns_user_id(self, manager):
        key = manager.create_key("bob")
        assert manager.verify_key(key) == "bob"

    def test_invalid_key_returns_none(self, manager):
        assert manager.verify_key("mr_invalid_garbage_key") is None

    def test_expired_key_returns_none(self, manager):
        key = manager.create_key("carol", expires_days=0)
        # Key created with 0-day expiry → already expired (expires_at == now)
        # Force expiration by backdating
        import hashlib

        key_hash = hashlib.sha256(key.encode()).hexdigest()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with manager.db.session() as conn:
            conn.execute(
                "UPDATE api_keys SET expires_at = ? WHERE key_hash = ?",
                (past, key_hash),
            )
        assert manager.verify_key(key) is None


class TestRevokeKey:
    def test_revoke_prevents_verification(self, manager):
        key = manager.create_key("dave")
        assert manager.verify_key(key) == "dave"
        # Revoke via truncated key_id
        keys = manager.list_keys(user_id="dave")
        assert manager.revoke_key(keys[0]["key_id"])
        assert manager.verify_key(key) is None

    def test_revoke_nonexistent_returns_false(self, manager):
        assert manager.revoke_key("does_not_exist") is False


class TestListKeys:
    def test_lists_all_keys(self, manager):
        manager.create_key("alice")
        manager.create_key("bob")
        keys = manager.list_keys()
        assert len(keys) == 2

    def test_filter_by_user_id(self, manager):
        manager.create_key("alice")
        manager.create_key("bob")
        manager.create_key("alice")
        keys = manager.list_keys(user_id="alice")
        assert len(keys) == 2
        assert all(k["user_id"] == "alice" for k in keys)

    def test_key_id_is_truncated(self, manager):
        manager.create_key("alice")
        keys = manager.list_keys()
        assert len(keys[0]["key_id"]) == 12


class TestUsageLogging:
    def test_log_and_get_usage(self, manager):
        key = manager.create_key("eve")
        manager.log_usage(key, "/chat", True)
        manager.log_usage(key, "/admin/api-keys", False)
        usage = manager.get_usage()
        assert len(usage) == 2
        assert usage[0]["endpoint"] == "/admin/api-keys"  # most recent first
        assert usage[0]["success"] is False
        assert usage[1]["endpoint"] == "/chat"
        assert usage[1]["success"] is True
        assert usage[0]["user_id"] == "eve"


# ---------------------------------------------------------------------------
# Integration tests — FastAPI TestClient
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Isolated TestClient with fresh DB."""
    db_path = str(tmp_path / "integration.db")
    rag_path = str(tmp_path / ".rag_store")
    monkeypatch.setenv(
        "MRC_DATABASE_URL", "sqlite:///" + db_path
    )
    monkeypatch.setenv("MRC_RAG_PERSIST_DIR", rag_path)
    monkeypatch.setenv("MRC_ENABLE_GRADIO", "false")

    # Also set RC_ prefix equivalents for settings
    monkeypatch.setenv("RC_DATABASE_URL", "sqlite:///" + db_path)
    monkeypatch.setenv("RC_RAG_PERSIST_DIR", rag_path)
    monkeypatch.setenv("RC_ENABLE_GRADIO", "false")

    from app.config import get_settings
    get_settings.cache_clear()

    if not os.getenv("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-placeholder")

    from app.main import build_app
    from fastapi.testclient import TestClient

    app = build_app()
    return TestClient(app)


@pytest.fixture()
def api_key_header():
    """Returns auth header dict using the static MRC_API_KEY."""
    from app.config import get_settings

    settings = get_settings()
    return {"Authorization": f"Bearer {settings.api_key}"}


class TestAdminEndpoints:
    def test_create_requires_auth(self, client):
        resp = client.post("/admin/api-keys", json={"user_id": "test"})
        assert resp.status_code == 401

    def test_create_and_list_keys(self, client, api_key_header):
        # Create
        resp = client.post(
            "/admin/api-keys",
            json={"user_id": "integration_user", "expires_days": 30},
            headers=api_key_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["raw_key"].startswith("mr_")
        assert data["user_id"] == "integration_user"

        # List
        resp = client.get("/admin/api-keys", headers=api_key_header)
        assert resp.status_code == 200
        keys = resp.json()
        assert any(k["user_id"] == "integration_user" for k in keys)

    def test_managed_key_authenticates_protected_endpoint(self, client, api_key_header):
        # Create a managed key
        resp = client.post(
            "/admin/api-keys",
            json={"user_id": "chat_user"},
            headers=api_key_header,
        )
        managed_key = resp.json()["raw_key"]

        # Use it to call a protected admin endpoint
        resp = client.get("/admin/api-keys", headers={"X-API-Key": managed_key})
        assert resp.status_code == 200

    def test_revoke_key_blocks_access(self, client, api_key_header):
        # Create
        resp = client.post(
            "/admin/api-keys",
            json={"user_id": "revoke_user"},
            headers=api_key_header,
        )
        managed_key = resp.json()["raw_key"]

        # List to get key_id
        resp = client.get(
            "/admin/api-keys?user_id=revoke_user", headers=api_key_header
        )
        key_id = resp.json()[0]["key_id"]

        # Revoke
        resp = client.delete(
            f"/admin/api-keys/{key_id}", headers=api_key_header
        )
        assert resp.status_code == 200

        # Try using revoked key on a protected endpoint
        resp = client.get("/admin/api-keys", headers={"X-API-Key": managed_key})
        assert resp.status_code == 401

    def test_usage_log_populated(self, client, api_key_header):
        # Create and use a managed key
        resp = client.post(
            "/admin/api-keys",
            json={"user_id": "usage_user"},
            headers=api_key_header,
        )
        managed_key = resp.json()["raw_key"]

        # Use it on a protected endpoint so usage is logged
        client.get("/admin/api-keys", headers={"X-API-Key": managed_key})

        # Check usage
        resp = client.get("/admin/api-keys/usage", headers=api_key_header)
        assert resp.status_code == 200
        usage = resp.json()
        assert len(usage) > 0
        assert any(e["user_id"] == "usage_user" for e in usage)
