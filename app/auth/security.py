from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
import hashlib
from fastapi import Request

from ..config import Settings
from ..monitoring.logging_utils import logger


class APIKeyManager:
    """Manage API keys with rotation and audit logging"""

    def __init__(self, db):
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self):
        is_pg = getattr(self.db, '_is_postgres', False)
        with self.db.session() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    last_used_at TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """
            )
            if is_pg:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_key_usage (
                        id SERIAL PRIMARY KEY,
                        key_hash TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        success INTEGER NOT NULL
                    )
                """
                )
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_key_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key_hash TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        success INTEGER NOT NULL
                    )
                """
                )

    def create_key(self, user_id: str, expires_days: int = 90) -> str:
        """Create new API key"""
        key = f"mr_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=expires_days)
        with self.db.session() as conn:
            conn.execute(
                "INSERT INTO api_keys (key_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (key_hash, user_id, now.isoformat(), expires.isoformat()),
            )
        logger.info(f"Created API key for user {user_id}")
        return key  # Return once, never stored in plain text

    def verify_key(self, key: str) -> Optional[str]:
        """Verify API key and return user_id"""
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        with self.db.session() as conn:
            row = conn.execute(
                """SELECT user_id, expires_at, is_active
                   FROM api_keys
                   WHERE key_hash = ?""",
                (key_hash,),
            ).fetchone()
            if not row:
                return None
            # Check expiration
            if row["expires_at"]:
                expires = datetime.fromisoformat(row["expires_at"])
                if datetime.now(timezone.utc) > expires:
                    logger.warning(f"Expired key used by {row['user_id']}")
                    return None
            # Check if active
            if not row["is_active"]:
                logger.warning(f"Inactive key used by {row['user_id']}")
                return None
            # Update last used
            conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?",
                (datetime.now(timezone.utc).isoformat(), key_hash),
            )
            return row["user_id"]

    def log_usage(self, key: str, endpoint: str, success: bool):
        """Log API key usage"""
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        with self.db.session() as conn:
            conn.execute(
                "INSERT INTO api_key_usage (key_hash, endpoint, timestamp, success) VALUES (?, ?, ?, ?)",
                (key_hash, endpoint, datetime.now(timezone.utc).isoformat(), int(success)),
            )

    def list_keys(self, user_id: Optional[str] = None) -> list[dict]:
        """List key metadata. Never exposes full hash."""
        with self.db.session() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT key_hash, user_id, created_at, expires_at, last_used_at, is_active "
                    "FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key_hash, user_id, created_at, expires_at, last_used_at, is_active "
                    "FROM api_keys ORDER BY created_at DESC"
                ).fetchall()
            return [
                {
                    "key_id": row["key_hash"][:12],
                    "user_id": row["user_id"],
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "last_used_at": row["last_used_at"],
                    "is_active": bool(row["is_active"]),
                }
                for row in rows
            ]

    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key by full hash or truncated key_id prefix."""
        with self.db.session() as conn:
            # Try exact match first, then prefix match
            row = conn.execute(
                "SELECT key_hash FROM api_keys WHERE key_hash = ? OR key_hash LIKE ?",
                (key_id, f"{key_id}%"),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_hash = ?",
                (row["key_hash"],),
            )
            logger.info(f"Revoked API key: {row['key_hash'][:12]}...")
            return True

    def get_usage(self, key_hash: Optional[str] = None, limit: int = 100) -> list[dict]:
        """Return audit log entries with user_id from api_keys."""
        with self.db.session() as conn:
            if key_hash:
                rows = conn.execute(
                    "SELECT u.id, u.key_hash, u.endpoint, u.timestamp, u.success, k.user_id "
                    "FROM api_key_usage u LEFT JOIN api_keys k ON u.key_hash = k.key_hash "
                    "WHERE u.key_hash = ? OR u.key_hash LIKE ? "
                    "ORDER BY u.timestamp DESC LIMIT ?",
                    (key_hash, f"{key_hash}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT u.id, u.key_hash, u.endpoint, u.timestamp, u.success, k.user_id "
                    "FROM api_key_usage u LEFT JOIN api_keys k ON u.key_hash = k.key_hash "
                    "ORDER BY u.timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {
                    "id": row["id"],
                    "key_id": row["key_hash"][:12],
                    "user_id": row["user_id"],
                    "endpoint": row["endpoint"],
                    "timestamp": row["timestamp"],
                    "success": bool(row["success"]),
                }
                for row in rows
            ]


def install_rate_limiter(app, settings: Settings) -> None:
    """Attach rate limiting middleware using slowapi."""
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded
    except ImportError:
        logger.warning("slowapi not installed, rate limiting disabled")
        return

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # Rate limiting is handled by slowapi's decorator on individual routes
        # This middleware is just a placeholder for future custom rate limit logic
        response = await call_next(request)
        return response
