"""Tests for _validate_tool_call tool argument validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.orchestrator import ConciergeOrchestrator  # noqa: E402

_validate_tool_call = ConciergeOrchestrator._validate_tool_call


class TestSearchAmenities:
    def test_valid_query(self):
        ok, reason = _validate_tool_call("search_amenities", {
            "query": "swimming pool",
        })
        assert ok is True

    def test_empty_query(self):
        ok, reason = _validate_tool_call("search_amenities", {
            "query": "",
        })
        assert ok is False
        assert "empty" in reason.lower()

    def test_whitespace_query(self):
        ok, reason = _validate_tool_call("search_amenities", {
            "query": "   ",
        })
        assert ok is False

    def test_query_too_long(self):
        ok, reason = _validate_tool_call("search_amenities", {
            "query": "x" * 501,
        })
        assert ok is False
        assert "500" in reason

    def test_query_at_limit(self):
        ok, reason = _validate_tool_call("search_amenities", {
            "query": "x" * 500,
        })
        assert ok is True


class TestUnknownTool:
    def test_unknown_tool_passes(self):
        ok, reason = _validate_tool_call("nonexistent_tool", {})
        assert ok is True
