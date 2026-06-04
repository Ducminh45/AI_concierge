"""Tests for tool sandboxing: timeout and rate limiting."""

import asyncio
import pytest

from app.core.tools import (
    ToolRegistry,
    Tool,
    TOOL_TIMEOUT,
    RATE_LIMIT_MAX,
    _tool_call_timestamps,
)


@pytest.fixture(autouse=True)
def _clear_rate_state():
    """Reset rate-limit state between tests."""
    _tool_call_timestamps.clear()
    yield
    _tool_call_timestamps.clear()


def _make_registry_with(name: str, fn):
    """Build a ToolRegistry with a single tool."""
    reg = ToolRegistry()
    reg.tools[name] = Tool(name=name, description="test", fn=fn)
    return reg


# ---- Timeout tests ----

@pytest.mark.asyncio
async def test_tool_timeout_returns_error():
    async def slow_tool(**kwargs):
        await asyncio.sleep(TOOL_TIMEOUT + 5)
        return {"ok": True}

    reg = _make_registry_with("slow", slow_tool)
    result = await reg.async_execute_with_timing("slow", request_id="r1")

    assert result["ok"] is False
    assert "timed out" in result["error"]
    assert result["request_id"] == "r1"


@pytest.mark.asyncio
async def test_fast_tool_succeeds():
    async def fast_tool(**kwargs):
        return {"ok": True, "data": 42}

    reg = _make_registry_with("fast", fast_tool)
    result = await reg.async_execute_with_timing("fast", request_id="r2")

    assert result["ok"] is True
    assert result["data"] == 42


# ---- Rate-limit tests ----

@pytest.mark.asyncio
async def test_rate_limit_rejects_after_threshold():
    async def echo(**kwargs):
        return {"ok": True}

    reg = _make_registry_with("echo", echo)

    for i in range(RATE_LIMIT_MAX):
        result = await reg.async_execute_with_timing("echo", request_id=f"r{i}")
        assert result["ok"] is True

    result = await reg.async_execute_with_timing("echo", request_id="over")
    assert result["ok"] is False
    assert "Rate limit" in result["error"]


@pytest.mark.asyncio
async def test_rate_limit_different_tools_independent():
    async def noop(**kwargs):
        return {"ok": True}

    reg = ToolRegistry()
    reg.tools["tool_a"] = Tool(name="tool_a", description="a", fn=noop)
    reg.tools["tool_b"] = Tool(name="tool_b", description="b", fn=noop)

    for i in range(RATE_LIMIT_MAX):
        await reg.async_execute_with_timing("tool_a", request_id=f"a{i}")

    result = await reg.async_execute_with_timing("tool_b", request_id="b0")
    assert result["ok"] is True
