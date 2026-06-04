from __future__ import annotations

import re
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from ..monitoring.logging_utils import logger

PostJson = Callable[..., Awaitable[dict[str, Any]]]

DEFAULT_TAVILY_URL = "https://api.tavily.com/search"
DEFAULT_VINPEARL_DOMAINS = ("vinpearl.com",)
_VINPEARL_RE = re.compile(r"\bvinpearl\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


async def _default_post_json(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=json)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


def is_vinpearl_query(query: str) -> bool:
    return bool(_VINPEARL_RE.search(query or ""))


class VinpearlTavilySearch:
    """Tavily-backed search constrained to official Vinpearl domains."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = DEFAULT_TAVILY_URL,
        include_domains: tuple[str, ...] = DEFAULT_VINPEARL_DOMAINS,
        max_results: int = 5,
        timeout_seconds: float = 8.0,
        post_json: PostJson = _default_post_json,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.include_domains = include_domains
        self.max_results = max(1, min(max_results, 10))
        self.timeout_seconds = timeout_seconds
        self._post_json = post_json

    async def search(self, query: str) -> dict[str, Any]:
        if not is_vinpearl_query(query):
            return {
                "ok": False,
                "reason": "not_vinpearl_query",
                "results": [],
            }

        if not self.api_key:
            logger.info("vinpearl_tavily_skipped_missing_api_key")
            return {
                "ok": False,
                "reason": "missing_api_key",
                "results": [],
            }

        payload = {
            "query": self._build_query(query),
            "search_depth": "basic",
            "max_results": self.max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_domains": list(self.include_domains),
        }

        try:
            data = await self._post_json(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "vinpearl_tavily_request_failed",
                extra={"error": str(exc)},
            )
            return {
                "ok": False,
                "reason": "request_failed",
                "results": [],
            }

        results = []
        for item in data.get("results", []):
            result = self._validate_result(item)
            if result:
                results.append(result)

        return {
            "ok": bool(results),
            "reason": "" if results else "no_valid_vinpearl_sources",
            "results": results,
        }

    def _build_query(self, query: str) -> str:
        clean_query = _WHITESPACE_RE.sub(" ", query).strip()
        domain_clause = " OR ".join(f"site:{domain}" for domain in self.include_domains)
        return f"{clean_query} Vinpearl ({domain_clause})"

    def _validate_result(self, item: Any) -> dict[str, str] | None:
        if not isinstance(item, dict):
            return None

        url = str(item.get("url") or "").strip()
        if not self._is_allowed_url(url):
            return None

        title = _WHITESPACE_RE.sub(" ", str(item.get("title") or "")).strip()
        content = _WHITESPACE_RE.sub(" ", str(item.get("content") or "")).strip()
        if not content:
            return None

        text = f"{title}\n{content}" if title else content
        if "vinpearl" not in text.lower() and "vinpearl" not in url.lower():
            return None

        return {
            "text": text,
            "source": url,
        }

    def _is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        host = (parsed.hostname or "").lower()
        return any(
            host == domain or host.endswith(f".{domain}")
            for domain in self.include_domains
        )
