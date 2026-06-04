"""
Tests for the ConciergeOrchestrator, focusing on _parse_plan() and data types.
"""

import json
import pytest

from app.core.orchestrator import (
    ConciergeOrchestrator,
    ExecutionResult,
    IntentType,
    Plan,
)


# ---------------------------------------------------------------------------
# IntentType enum
# ---------------------------------------------------------------------------


class TestIntentType:
    def test_knowledge_value(self):
        assert IntentType.KNOWLEDGE.value == "knowledge"

    def test_tool_value(self):
        assert IntentType.TOOL.value == "tool"

    def test_clarify_value(self):
        assert IntentType.CLARIFY.value == "clarify"

    def test_chitchat_value(self):
        assert IntentType.CHITCHAT.value == "chitchat"

    def test_all_intents_are_strings(self):
        for intent in IntentType:
            assert isinstance(intent.value, str)


# ---------------------------------------------------------------------------
# Plan defaults
# ---------------------------------------------------------------------------


class TestPlanDefaults:
    def test_plan_defaults(self):
        plan = Plan(intent=IntentType.CHITCHAT)
        assert plan.tool_name is None
        assert plan.tool_args == {}
        assert plan.search_query is None
        assert plan.reasoning == ""

    def test_plan_with_all_fields(self):
        plan = Plan(
            intent=IntentType.TOOL,
            tool_name="book_room",
            tool_args={"guest": "Dracula"},
            search_query=None,
            reasoning="Booking request",
        )
        assert plan.tool_name == "book_room"
        assert plan.tool_args == {"guest": "Dracula"}


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_confidence_field_defaults_to_none(self):
        result = ExecutionResult(
            response="Hello",
            plan=Plan(intent=IntentType.CHITCHAT),
        )
        assert result.confidence is None

    def test_confidence_field_can_be_set(self):
        result = ExecutionResult(
            response="Hello",
            plan=Plan(intent=IntentType.CHITCHAT),
            confidence={"level": "HIGH", "score": 0.95},
        )
        assert result.confidence["level"] == "HIGH"


# ---------------------------------------------------------------------------
# _parse_plan — the core logic under test
# ---------------------------------------------------------------------------


class TestParsePlan:
    """Test _parse_plan as a bound method on a minimal orchestrator instance."""

    @pytest.fixture()
    def parse(self):
        """Return a callable that wraps _parse_plan without needing real deps."""
        # _parse_plan only uses self indirectly (logging), so we can create
        # a bare instance with None deps — it never touches them during parsing.
        orch = object.__new__(ConciergeOrchestrator)
        return orch._parse_plan

    # -- valid JSON ----------------------------------------------------------

    def test_valid_json(self, parse):
        raw = json.dumps({
            "intent": "knowledge",
            "tool_name": None,
            "tool_args": {},
            "search_query": "pool hours",
            "reasoning": "Guest wants pool info",
        })
        plan = parse(raw)
        assert plan.intent == IntentType.KNOWLEDGE
        assert plan.search_query == "pool hours"

    def test_tool_intent(self, parse):
        raw = json.dumps({
            "intent": "tool",
            "tool_name": "book_room",
            "tool_args": {"guest_name": "Dracula"},
            "search_query": None,
            "reasoning": "Booking",
        })
        plan = parse(raw)
        assert plan.intent == IntentType.TOOL
        assert plan.tool_name == "book_room"
        assert plan.tool_args == {"guest_name": "Dracula"}

    # -- markdown-wrapped JSON -----------------------------------------------

    def test_markdown_fenced_json(self, parse):
        raw = '```json\n{"intent": "clarify", "reasoning": "Need dates"}\n```'
        plan = parse(raw)
        assert plan.intent == IntentType.CLARIFY
        assert plan.reasoning == "Need dates"

    def test_markdown_fenced_no_lang(self, parse):
        raw = '```\n{"intent": "chitchat", "reasoning": "Hello"}\n```'
        plan = parse(raw)
        assert plan.intent == IntentType.CHITCHAT

    # -- JSON with surrounding prose -----------------------------------------

    def test_json_with_extra_text(self, parse):
        raw = 'Sure, here is the plan:\n{"intent": "knowledge", "search_query": "spa"}\nHope that helps!'
        plan = parse(raw)
        assert plan.intent == IntentType.KNOWLEDGE
        assert plan.search_query == "spa"

    # -- garbage / empty input -----------------------------------------------

    def test_garbage_input_falls_back_to_chitchat(self, parse):
        plan = parse("this is not json at all")
        assert plan.intent == IntentType.CHITCHAT
        assert "parse failed" in plan.reasoning.lower() or "defaulting" in plan.reasoning.lower()

    def test_empty_input_falls_back_to_chitchat(self, parse):
        plan = parse("")
        assert plan.intent == IntentType.CHITCHAT

    # -- keyword fallback heuristics -----------------------------------------

    def test_garbage_with_tool_keyword(self, parse):
        plan = parse("please book a room for me")
        assert plan.intent == IntentType.TOOL

    def test_garbage_with_knowledge_keyword(self, parse):
        plan = parse("tell me about the pool and spa")
        assert plan.intent == IntentType.KNOWLEDGE

    # -- unknown intent value ------------------------------------------------

    def test_unknown_intent_falls_back_to_chitchat(self, parse):
        raw = json.dumps({"intent": "nonexistent_intent", "reasoning": "test"})
        plan = parse(raw)
        assert plan.intent == IntentType.CHITCHAT
