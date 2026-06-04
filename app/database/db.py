from __future__ import annotations

import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, List
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..monitoring.logging_utils import logger, DatabaseError

# Incremented to 4 to support users and service_requests tables
SCHEMA_VERSION = 4

DDL = [
    # --- System & Migration Tracking ---
    """CREATE TABLE IF NOT EXISTS schema_migrations (
        version    INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )""",
    # --- Conversation State & Memory ---
    """CREATE TABLE IF NOT EXISTS sessions (
        session_id    TEXT PRIMARY KEY,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        summary       TEXT,
        metadata_json TEXT
    )""",
    # --- Performance Optimization ---
    """CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)""",
    """CREATE INDEX IF NOT EXISTS idx_bookings_session_id ON bookings(session_id)""",
    """CREATE INDEX IF NOT EXISTS idx_bookings_reference  ON bookings(booking_reference)""",
    """CREATE INDEX IF NOT EXISTS idx_service_requests_session_id ON service_requests(session_id)""",
]

DDL_MESSAGES_SQLITE = """CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
)"""

DDL_MESSAGES_POSTGRES = """CREATE TABLE IF NOT EXISTS messages (
    id         SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
)"""

DDL_BOOKINGS_SQLITE = """CREATE TABLE IF NOT EXISTS bookings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_reference TEXT UNIQUE NOT NULL,
    session_id        TEXT,
    guest_name        TEXT NOT NULL,
    hotel_name        TEXT,
    room_type         TEXT NOT NULL,
    check_in          TEXT NOT NULL,
    check_out         TEXT NOT NULL,
    guests            INTEGER NOT NULL,
    special_requests  TEXT,
    status            TEXT NOT NULL DEFAULT 'confirmed',
    created_at        TEXT NOT NULL
)"""

DDL_BOOKINGS_POSTGRES = """CREATE TABLE IF NOT EXISTS bookings (
    id                SERIAL PRIMARY KEY,
    booking_reference TEXT UNIQUE NOT NULL,
    session_id        TEXT,
    guest_name        TEXT NOT NULL,
    hotel_name        TEXT,
    room_type         TEXT NOT NULL,
    check_in          TEXT NOT NULL,
    check_out         TEXT NOT NULL,
    guests            INTEGER NOT NULL,
    special_requests  TEXT,
    status            TEXT NOT NULL DEFAULT 'confirmed',
    created_at        TEXT NOT NULL
)"""

# --- New Tables for User Management and Service Requests ---
DDL_USERS_SQLITE = """CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email         TEXT,
    full_name     TEXT,
    role          TEXT NOT NULL DEFAULT 'guest',
    created_at    TEXT NOT NULL
)"""

DDL_USERS_POSTGRES = """CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email         TEXT,
    full_name     TEXT,
    role          TEXT NOT NULL DEFAULT 'guest',
    created_at    TEXT NOT NULL
)"""

DDL_SERVICE_REQUESTS_SQLITE = """CREATE TABLE IF NOT EXISTS service_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT,
    room_number  TEXT,
    guest_name   TEXT,
    resort_name  TEXT,
    service_type TEXT NOT NULL,
    details      TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)"""

DDL_SERVICE_REQUESTS_POSTGRES = """CREATE TABLE IF NOT EXISTS service_requests (
    id           SERIAL PRIMARY KEY,
    session_id   TEXT,
    room_number  TEXT,
    guest_name   TEXT,
    resort_name  TEXT,
    service_type TEXT NOT NULL,
    details      TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)"""

UPSERT_MIGRATION_SQLITE = (
    "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES(:version, :applied_at)"
)
UPSERT_MIGRATION_POSTGRES = (
    "INSERT INTO schema_migrations(version, applied_at) VALUES(:version, :applied_at) "
    "ON CONFLICT (version) DO UPDATE SET applied_at = EXCLUDED.applied_at"
)


def _convert_qmarks(sql: str):
    if "?" not in sql:
        return sql, False
    parts = sql.split("?")
    new_parts = [parts[0]]
    for i, part in enumerate(parts[1:]):
        new_parts.append(f":p{i}")  # noqa: E231
        new_parts.append(part)
    return "".join(new_parts), True


class _ConnectionProxy:
    def __init__(self, sa_conn):
        self._conn = sa_conn

    def execute(self, sql: str, params=None):
        converted_sql, was_converted = _convert_qmarks(sql)
        if params is not None:
            if was_converted and isinstance(params, (tuple, list)):
                params = {f"p{i}": v for i, v in enumerate(params)}
            elif isinstance(params, (tuple, list)) and not was_converted:
                pass
        else:
            params = {}

        result = self._conn.execute(text(converted_sql), params)
        return _ResultProxy(result)


class _ResultProxy:
    def __init__(self, result):
        self._result = result

    def fetchone(self):
        row = self._result.fetchone()
        if row is None:
            return None
        return _RowProxy(row._mapping)

    def fetchall(self):
        rows = self._result.fetchall()
        return [_RowProxy(r._mapping) for r in rows]


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


class _RowProxy(dict):
    def __init__(self, mapping):
        super().__init__(mapping)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class DatabaseManager:
    def __init__(self, settings: Settings):
        self._db_url = getattr(settings, "database_url", "sqlite:///./resort_concierge.db")
        if self._db_url.startswith("postgres://"):
            self._db_url = self._db_url.replace("postgres://", "postgresql://", 1)
        self._is_postgres = _is_postgres(self._db_url)
        self._engine = self._create_engine()
        self._init_db()

    def _create_engine(self) -> Engine:
        if self._is_postgres:
            return create_engine(
                self._db_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
        else:
            db_path_str = self._db_url.replace("sqlite:///", "")
            if db_path_str:
                Path(db_path_str).parent.mkdir(parents=True, exist_ok=True)
            return create_engine(self._db_url)

    @contextmanager
    def get_connection(self) -> Iterator[_ConnectionProxy]:
        conn = self._engine.connect()
        proxy = _ConnectionProxy(conn)
        try:
            yield proxy
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Database transaction failed: {e}")
        finally:
            conn.close()

    @contextmanager
    def session(self) -> Iterator[_ConnectionProxy]:
        with self.get_connection() as conn:
            yield conn

    def _init_db(self):
        try:
            with self.get_connection() as conn:
                all_ddl = list(DDL)
                if self._is_postgres:
                    all_ddl.insert(1, DDL_MESSAGES_POSTGRES)
                    all_ddl.insert(2, DDL_BOOKINGS_POSTGRES)
                    all_ddl.insert(3, DDL_USERS_POSTGRES)
                    all_ddl.insert(4, DDL_SERVICE_REQUESTS_POSTGRES)
                else:
                    all_ddl.insert(1, DDL_MESSAGES_SQLITE)
                    all_ddl.insert(2, DDL_BOOKINGS_SQLITE)
                    all_ddl.insert(3, DDL_USERS_SQLITE)
                    all_ddl.insert(4, DDL_SERVICE_REQUESTS_SQLITE)

                for stmt in all_ddl:
                    conn.execute(stmt)

                cur = conn.execute("SELECT MAX(version) AS v FROM schema_migrations")
                row = cur.fetchone()
                current = int(row["v"] or 0) if row["v"] is not None else 0

                if current < SCHEMA_VERSION:
                    logger.info("Upgrading schema from %s to %s", current, SCHEMA_VERSION)
                    upsert_sql = (
                        UPSERT_MIGRATION_POSTGRES if self._is_postgres
                        else UPSERT_MIGRATION_SQLITE
                    )
                    conn.execute(
                        upsert_sql,
                        {"version": SCHEMA_VERSION, "applied_at": datetime.now(timezone.utc).isoformat()},
                    )
            logger.info("Database initialized (%s)", "PostgreSQL" if self._is_postgres else "SQLite")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Database initialization failed: {e}")

    # --- User Management Methods ---
    def create_user(self, username: str, password_hash: str, email: str | None = None, full_name: str | None = None, role: str = "guest") -> dict:
        now = datetime.now(timezone.utc).isoformat()
        query = "INSERT INTO users (username, password_hash, email, full_name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)"
        try:
            with self.get_connection() as conn:
                conn.execute(query, (username.lower(), password_hash, email, full_name, role, now))
            logger.info("User %s created with role %s", username, role)
            return {"username": username, "email": email, "full_name": full_name, "role": role}
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise DatabaseError(f"Failed to create user: {e}")

    def get_user(self, username: str) -> Optional[dict]:
        query = "SELECT * FROM users WHERE username = ?"
        try:
            with self.get_connection() as conn:
                cur = conn.execute(query, (username.lower(),))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            raise DatabaseError(f"Failed to get user: {e}")

    def get_all_users(self) -> List[dict]:
        query = "SELECT id, username, email, full_name, role, created_at FROM users ORDER BY id DESC"
        try:
            with self.get_connection() as conn:
                cur = conn.execute(query)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get all users: {e}")
            raise DatabaseError(f"Failed to get all users: {e}")

    def update_user_role(self, username: str, role: str) -> bool:
        query = "UPDATE users SET role = ? WHERE username = ?"
        try:
            with self.get_connection() as conn:
                conn.execute(query, (role, username.lower()))
            logger.info("Updated role of user %s to %s", username, role)
            return True
        except Exception as e:
            logger.error(f"Failed to update user role: {e}")
            raise DatabaseError(f"Failed to update user role: {e}")

    # --- Service Request Methods ---
    def create_service_request(self, session_id: str | None, room_number: str | None, guest_name: str | None, resort_name: str | None, service_type: str, details: str | None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        query = """
            INSERT INTO service_requests (session_id, room_number, guest_name, resort_name, service_type, details, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """
        try:
            with self.get_connection() as conn:
                conn.execute(query, (session_id, room_number, guest_name, resort_name, service_type, details, now, now))
                # Get the last inserted ID
                if self._is_postgres:
                    cur = conn.execute("SELECT LASTVAL() as id")
                else:
                    cur = conn.execute("SELECT last_insert_rowid() as id")
                row = cur.fetchone()
                request_id = row["id"] if row else None

            logger.info("Service request %s of type %s created", request_id, service_type)
            return {
                "id": request_id,
                "session_id": session_id,
                "room_number": room_number,
                "guest_name": guest_name,
                "resort_name": resort_name,
                "service_type": service_type,
                "details": details,
                "status": "pending",
                "created_at": now,
            }
        except Exception as e:
            logger.error(f"Failed to create service request: {e}")
            raise DatabaseError(f"Failed to create service request: {e}")

    def get_service_requests(self, session_id: str | None = None, all_requests: bool = False) -> List[dict]:
        if all_requests:
            query = "SELECT * FROM service_requests ORDER BY id DESC"
            params = ()
        else:
            query = "SELECT * FROM service_requests WHERE session_id = ? ORDER BY id DESC"
            params = (session_id,)
        try:
            with self.get_connection() as conn:
                cur = conn.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get service requests: {e}")
            raise DatabaseError(f"Failed to get service requests: {e}")

    def update_service_request_status(self, request_id: int, status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        query = "UPDATE service_requests SET status = ?, updated_at = ? WHERE id = ?"
        try:
            with self.get_connection() as conn:
                conn.execute(query, (status, now, request_id))
            logger.info("Service request %s updated to status %s", request_id, status)
            return True
        except Exception as e:
            logger.error(f"Failed to update service request status: {e}")
            raise DatabaseError(f"Failed to update service request status: {e}")

    # --- Existing Booking Methods ---
    def create_booking(
        self,
        session_id: str,
        guest_name: str,
        hotel_name: str,
        room_type: str,
        check_in: str,
        check_out: str,
        guests: int = 1,
        special_requests: str = "",
    ) -> dict:
        booking_ref = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()

        query = """
            INSERT INTO bookings (
                booking_reference, session_id, guest_name, hotel_name,
                room_type, check_in, check_out, guests, special_requests, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        try:
            with self.get_connection() as conn:
                conn.execute(
                    query,
                    (
                        booking_ref,
                        session_id,
                        guest_name,
                        hotel_name,
                        room_type,
                        check_in,
                        check_out,
                        guests,
                        special_requests,
                        now,
                    ),
                )

            logger.info("Booking %s saved to database", booking_ref)
            return {
                "booking_id": booking_ref,
                "guest_name": guest_name,
                "hotel_name": hotel_name,
                "room_type": room_type,
                "check_in": check_in,
                "check_out": check_out,
                "status": "confirmed",
            }
        except Exception as e:
            logger.error(f"Failed to create booking: {e}")
            raise DatabaseError(f"Failed to create booking: {e}")

    def get_booking(self, booking_id: str) -> Optional[dict]:
        query = "SELECT * FROM bookings WHERE booking_reference = ? OR session_id = ?"
        try:
            with self.get_connection() as conn:
                cur = conn.execute(query, (booking_id, booking_id))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get booking: {e}")
            raise DatabaseError(f"Failed to get booking: {e}")
