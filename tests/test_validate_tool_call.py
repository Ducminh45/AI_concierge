"""Tests for _validate_tool_call tool argument validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.orchestrator import ConciergeOrchestrator  # noqa: E402

_validate_tool_call = ConciergeOrchestrator._validate_tool_call

_VALID_BOOK_ARGS = {
    "hotel_name": "Vampire Manor: Eternal Night Inn",
    "guest_name": "Count Dracula",
    "check_in": "2026-06-01",
    "check_out": "2026-06-05",
}


class TestBookRoom:
    def test_valid_hotel(self):
        ok, reason = _validate_tool_call("book_room", _VALID_BOOK_ARGS)
        assert ok is True

    def test_invalid_hotel(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "hotel_name": "Fake Hotel",
        })
        assert ok is False
        assert "Not in official registry" in reason

    def test_empty_hotel(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "hotel_name": "",
        })
        assert ok is False

    def test_missing_hotel_key(self):
        ok, reason = _validate_tool_call("book_room", {})
        assert ok is False

    def test_empty_guest_name(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "guest_name": "",
        })
        assert ok is False
        assert "guest_name" in reason

    def test_guest_name_too_long(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "guest_name": "A" * 101,
        })
        assert ok is False
        assert "100" in reason

    def test_guest_name_path_traversal(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "guest_name": "../../etc/passwd",
        })
        assert ok is False
        assert "invalid characters" in reason.lower()

    def test_guest_name_backslash(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "guest_name": "guest\\admin",
        })
        assert ok is False

    def test_guest_name_null_byte(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "guest_name": "guest\x00evil",
        })
        assert ok is False

    def test_invalid_check_in_date(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "check_in": "not-a-date",
        })
        assert ok is False
        assert "check_in" in reason

    def test_invalid_check_out_date(self):
        ok, reason = _validate_tool_call("book_room", {
            **_VALID_BOOK_ARGS,
            "check_out": "06/05/2026",
        })
        assert ok is False
        assert "check_out" in reason


class TestGetBooking:
    def test_valid_booking_id(self):
        ok, reason = _validate_tool_call("get_booking", {
            "booking_id": "abc-123",
        })
        assert ok is True

    def test_empty_booking_id(self):
        ok, reason = _validate_tool_call("get_booking", {
            "booking_id": "",
        })
        assert ok is False
        assert "empty" in reason.lower()

    def test_whitespace_booking_id(self):
        ok, reason = _validate_tool_call("get_booking", {
            "booking_id": "   ",
        })
        assert ok is False

    def test_missing_booking_id_key(self):
        ok, reason = _validate_tool_call("get_booking", {})
        assert ok is False


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

    def test_empty_args(self):
        ok, reason = _validate_tool_call("book_room", {})
        assert ok is False
