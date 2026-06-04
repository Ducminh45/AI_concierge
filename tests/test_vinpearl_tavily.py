from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from app.core.llm_providers import LLMResponse
from app.core.orchestrator import ConciergeOrchestrator, IntentType, Plan
from app.core.vinpearl_search import VinpearlTavilySearch


@pytest.mark.asyncio
async def test_tavily_search_is_skipped_for_non_vinpearl_queries():
    post = AsyncMock()
    searcher = VinpearlTavilySearch(api_key="tvly-test", post_json=post)

    result = await searcher.search("What time does the Azure Bay pool close?")

    assert result["ok"] is False
    assert result["reason"] == "not_vinpearl_query"
    post.assert_not_called()


@pytest.mark.asyncio
async def test_tavily_search_restricts_query_to_vinpearl_domain():
    calls = []

    async def post_json(url, *, headers, json, timeout):
        calls.append({
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return {
            "results": [
                {
                    "title": "Vinpearl Resort Nha Trang",
                    "url": "https://vinpearl.com/en/hotels/vinpearl-resort-nha-trang",
                    "content": "Vinpearl Resort Nha Trang has beachfront rooms and resort services.",
                }
            ]
        }

    searcher = VinpearlTavilySearch(api_key="tvly-test", post_json=post_json)

    result = await searcher.search("Vinpearl Nha Trang có gì?")

    assert result["ok"] is True
    assert calls[0]["url"] == "https://api.tavily.com/search"
    assert calls[0]["headers"]["Authorization"] == "Bearer tvly-test"
    assert calls[0]["json"]["include_domains"] == ["vinpearl.com"]
    assert "Vinpearl" in calls[0]["json"]["query"]
    assert result["results"] == [
        {
            "text": (
                "Vinpearl Resort Nha Trang\n"
                "Vinpearl Resort Nha Trang has beachfront rooms and resort services."
            ),
            "source": "https://vinpearl.com/en/hotels/vinpearl-resort-nha-trang",
        }
    ]


@pytest.mark.asyncio
async def test_tavily_search_filters_non_vinpearl_sources():
    async def post_json(url, *, headers, json, timeout):
        return {
            "results": [
                {
                    "title": "Travel blog",
                    "url": "https://example.com/vinpearl-rumors",
                    "content": "Vinpearl has a secret discount that is not official.",
                },
                {
                    "title": "Vinpearl official",
                    "url": "https://www.vinpearl.com/vi/uu-dai",
                    "content": "Vinpearl publishes official promotions on its website.",
                },
            ]
        }

    searcher = VinpearlTavilySearch(api_key="tvly-test", post_json=post_json)

    result = await searcher.search("Vinpearl đang có ưu đãi gì?")

    assert result["ok"] is True
    assert [item["source"] for item in result["results"]] == [
        "https://www.vinpearl.com/vi/uu-dai"
    ]


@pytest.mark.asyncio
async def test_orchestrator_uses_vinpearl_web_search_when_local_rag_is_not_relevant():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(content="Vinpearl answer", usage={})

    rag = Mock()
    rag.search.return_value = {
        "ok": True,
        "results": [
            {
                "text": "Azure Bay Resort has a spa and a family pool.",
                "meta": {"source": "amenities.txt"},
                "score": 0.92,
            }
        ],
    }
    memory = Mock()
    memory.get_messages.return_value = []
    tools = Mock()
    tools.list.return_value = []
    web_search = AsyncMock()
    web_search.search.return_value = {
        "ok": True,
        "results": [
            {
                "text": "Vinpearl Safari Phu Quoc is a wildlife conservation park.",
                "source": "https://vinpearl.com/en/vinpearl-safari-phu-quoc",
            }
        ],
    }

    orch = ConciergeOrchestrator(
        llm_provider=llm,
        rag=rag,
        tool_registry=tools,
        memory_store=memory,
        web_search=web_search,
    )

    result = await orch._execute_knowledge(
        Plan(intent=IntentType.KNOWLEDGE, search_query="Vinpearl Safari Phu Quoc"),
        "Vinpearl Safari Phu Quoc có gì?",
        "session-1",
    )

    web_search.search.assert_awaited_once_with("Vinpearl Safari Phu Quoc")
    assert result.sources == ["https://vinpearl.com/en/vinpearl-safari-phu-quoc"]
    assert result.rag_contexts == [
        "Vinpearl Safari Phu Quoc is a wildlife conservation park."
    ]


@pytest.mark.asyncio
async def test_orchestrator_does_not_treat_local_location_match_as_vinpearl_answer():
    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(content="Vinpearl answer", usage={})

    rag = Mock()
    rag.search.return_value = {
        "ok": True,
        "results": [
            {
                "text": "Nha Trang Coral Bay has family pools and spa services.",
                "meta": {"source": "amenities.txt"},
                "score": 0.31,
            }
        ],
    }
    memory = Mock()
    memory.get_messages.return_value = []
    tools = Mock()
    tools.list.return_value = []
    web_search = AsyncMock()
    web_search.search.return_value = {
        "ok": True,
        "results": [
            {
                "text": "Vinpearl Nha Trang has beachfront resort services.",
                "source": "https://vinpearl.com/en/hotels/vinpearl-nha-trang",
            }
        ],
    }

    orch = ConciergeOrchestrator(
        llm_provider=llm,
        rag=rag,
        tool_registry=tools,
        memory_store=memory,
        web_search=web_search,
    )

    result = await orch._execute_knowledge(
        Plan(intent=IntentType.KNOWLEDGE, search_query="Vinpearl Nha Trang"),
        "Vinpearl Nha Trang có gì?",
        "session-1",
    )

    web_search.search.assert_awaited_once_with("Vinpearl Nha Trang")
    assert result.rag_contexts == [
        "Vinpearl Nha Trang has beachfront resort services."
    ]
