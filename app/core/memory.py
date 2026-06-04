from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..database.db import DatabaseManager


@dataclass
class MemoryStore:
    db: DatabaseManager
    max_messages_before_summary: int = 12

    def ensure_session(self, session_id: str, metadata: Optional[dict] = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.session() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO sessions"
                    "(session_id, created_at, updated_at, summary, metadata_json)"
                    " VALUES(?, ?, ?, ?, ?)",
                    (session_id, now, now, None, json.dumps(metadata or {})),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                    (now, session_id),
                )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.ensure_session(session_id)
        with self.db.session() as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES(?, ?, ?, ?)",
                (session_id, role, content, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

        self._maybe_summarise(session_id)

    def get_messages(self, session_id: str, limit: int = 50) -> list[dict]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def _maybe_summarise(self, session_id: str) -> None:
        import os
        import logging

        try:
            import openai
        except ImportError:
            openai = None
        model = os.getenv("MRC_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o"
        with self.db.session() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()["c"]
            if int(count) < self.max_messages_before_summary:
                return
            rows = conn.execute(
                "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, int(self.max_messages_before_summary)),
            ).fetchall()
            if not rows:
                return
            lines = [f"{r['role']}: {r['content']}" for r in rows]
            openai_api_key = os.getenv("OPENAI_API_KEY")
            summary = None
            if openai and openai_api_key:
                try:
                    from .prompt_loader import load_prompt

                    client = openai.OpenAI(api_key=openai_api_key)
                    prompt = load_prompt(
                        "summarization",
                        conversation="\n".join(lines),
                    )
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a helpful assistant.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=128,
                        temperature=0.2,
                    )
                    summary = resp.choices[0].message.content.strip()
                except Exception as e:
                    logging.error(f"LLM summarization failed: {e}")
                    summary = None
            if not summary:
                summary = self._cheap_summary(lines)
            existing = conn.execute(
                "SELECT summary FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            prev = (existing["summary"] or "").strip() if existing else ""
            merged = (prev + "\n" + summary).strip() if prev else summary
            conn.execute(
                "UPDATE sessions SET summary = ? WHERE session_id = ?",
                (merged, session_id),
            )
            ids = [r["id"] for r in rows]
            if ids:
                placeholders = ",".join(["?"] * len(ids))
                conn.execute(
                    f"DELETE FROM messages WHERE id IN ({placeholders})",
                    tuple(ids),
                )

    def _cheap_summary(self, lines: list[str]) -> str:
        """Regex-based fallback when LLM summarization is unavailable."""
        import re

        intents = []
        entities = []
        for line in lines:
            if re.search(r"\b(book|reserve|cancel)\b", line, re.I):
                intents.append("booking")
            if re.search(r"\b(invoice|receipt|pdf)\b", line, re.I):
                intents.append("invoice")
            entities.extend(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", line))
        intent_summary = f"Intents: {', '.join(set(intents))}" if intents else ""
        entity_summary = (
            f"Mentioned: {', '.join(set(entities[:5]))}" if entities else ""
        )
        return f"{intent_summary}. {entity_summary}".strip()
