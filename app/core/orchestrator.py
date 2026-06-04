"""Multi-Agent Orchestrator: Planner classifies intent, Executor acts on it."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from .cost_tracker import CostAccumulator
from .guardrails import InputGuard, OutputGuard
from .llm_providers import LLMMessage, LLMProvider, LLMResponse
from .memory import MemoryStore
from .prompt_loader import load_prompt
from .structured_output import StructuredOutputParser
from .tools import ToolRegistry
from .vinpearl_search import VinpearlTavilySearch, is_vinpearl_query
from ..validation.hallucination import (
    ConfidenceLevel,
    HallucinationDetector,
)

logger = logging.getLogger(__name__)

_VINPEARL_TRAVEL_REFUSAL_VI = (
    "Xin lỗi, mình chỉ có thể hỗ trợ các câu hỏi liên quan đến Vinpearl Travel "
    "như điểm đến, khách sạn/resort, phòng, combo, lịch trình, dịch vụ và đặt "
    "phòng. Bạn đang muốn tư vấn chuyến đi Vinpearl nào?"
)
_VINPEARL_TRAVEL_REFUSAL_EN = (
    "Sorry, I can only help with Vinpearl Travel questions such as destinations, "
    "hotels/resorts, rooms, packages, itineraries, services, and booking support. "
    "Which Vinpearl trip would you like help with?"
)
_LIVE_WEB_KEYWORDS = (
    "availability",
    "available",
    "con phong",
    "contact",
    "current",
    "dat phong",
    "deal",
    "bang gia",
    "bao nhieu tien",
    "gia bao nhieu",
    "gia phong",
    "gia ve",
    "hien tai",
    "hom nay",
    "hotline",
    "khuyen mai",
    "latest",
    "lien he",
    "live",
    "moi nhat",
    "offer",
    "phone",
    "price",
    "promotion",
    "rate",
    "so dien thoai",
    "uu dai",
)
_VIETNAMESE_SIGNAL_RE = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    r"ùúụủũưừứựửữỳýỵỷỹđ]",
    re.IGNORECASE,
)
_GREETING_KEYWORDS = ("chao", "hello", "hi ", "hey", "xin chao")
_VECTOR_EVIDENCE_GROUPS = (
    (
        ("cancel", "cancellation", "huy", "huy phong"),
        ("cancel", "cancellation", "huy", "huy phong", "hoan huy"),
    ),
    (
        ("airport", "dua don", "san bay", "shuttle", "xe bus"),
        ("airport", "dua don", "san bay", "shuttle", "vinbus", "xe bus"),
    ),
)


def _normalize_query_text(text: str) -> str:
    lowered = (text or "").lower().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", lowered)
    return "".join(
        char for char in normalized
        if unicodedata.category(char) != "Mn"
    )


def _looks_vietnamese(text: str) -> bool:
    normalized = f" {_normalize_query_text(text)} "
    return bool(_VIETNAMESE_SIGNAL_RE.search(text)) or any(
        marker in normalized
        for marker in (
            " ban ",
            " cho minh ",
            " giup ",
            " khach san ",
            " lich trinh ",
            " minh ",
            " phong ",
            " toi ",
        )
    )


def _vinpearl_travel_refusal(text: str) -> str:
    return (
        _VINPEARL_TRAVEL_REFUSAL_VI
        if _looks_vietnamese(text)
        else _VINPEARL_TRAVEL_REFUSAL_EN
    )


def _should_try_vector_before_web(query: str) -> bool:
    if not is_vinpearl_query(query):
        return False

    normalized = f" {_normalize_query_text(query)} "
    return not any(f" {keyword} " in normalized for keyword in _LIVE_WEB_KEYWORDS)


def _should_force_vinpearl_overview(message: str) -> bool:
    if not is_vinpearl_query(message):
        return False

    normalized = f" {_normalize_query_text(message)} "
    return not any(f" {keyword} " in normalized for keyword in _GREETING_KEYWORDS)


def _vector_result_missing_expected_evidence(
    query: str,
    result: dict,
) -> bool:
    normalized_query = _normalize_query_text(query)
    expected_keywords: tuple[str, ...] = ()
    for triggers, evidence_keywords in _VECTOR_EVIDENCE_GROUPS:
        if any(trigger in normalized_query for trigger in triggers):
            expected_keywords = evidence_keywords
            break

    if not expected_keywords:
        return False

    result_text_parts = []
    for item in result.get("results", []):
        if isinstance(item, dict):
            result_text_parts.append(str(item.get("text", "")))
            result_text_parts.append(str(item.get("meta", "")))
    normalized_result_text = _normalize_query_text(" ".join(result_text_parts))
    return not any(
        keyword in normalized_result_text
        for keyword in expected_keywords
    )


class IntentType(str, Enum):
    KNOWLEDGE = "knowledge"
    TOOL = "tool"
    CLARIFY = "clarify"
    CHITCHAT = "chitchat"


class Plan(BaseModel):
    """The planner's decision."""

    intent: IntentType
    tool_name: str | None = None
    tool_args: dict = Field(default_factory=dict)
    search_query: str | None = None
    reasoning: str = ""

    @field_validator("intent", mode="before")
    @classmethod
    def normalize_intent(cls, v):
        if isinstance(v, str):
            try:
                return IntentType(v.lower())
            except ValueError:
                return IntentType.CHITCHAT
        return v


@dataclass
class ExecutionResult:
    """The executor's output."""

    response: str
    plan: Plan
    tool_result: Optional[dict] = None
    sources: list[str] = field(default_factory=list)
    rag_contexts: List[str] = field(default_factory=list)
    latency_ms: float = 0
    token_usage: dict = field(default_factory=dict)
    confidence: Optional[object] = None
    claim_verification: Optional[object] = None
    guardrail: Optional[str] = None
    pii_types: List[str] = field(default_factory=list)


class ConciergeOrchestrator:
    """Two-agent orchestrator: Planner decides, Executor acts."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        rag: Any,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore,
        detector: Optional[HallucinationDetector] = None,
        input_guard: Optional[InputGuard] = None,
        web_search: Optional[VinpearlTavilySearch] = None,
    ):
        self.llm = llm_provider
        self.rag = rag
        self.tools = tool_registry
        self.memory = memory_store
        self.detector = detector
        self.input_guard = input_guard
        self.web_search = web_search
        self._total_planner_tokens = 0
        self._total_executor_tokens = 0
        self._costs = CostAccumulator()

    async def plan(self, user_message: str, session_id: str) -> Plan:
        """Classify user intent and create an execution plan; falls back to chitchat on error."""
        start = time.monotonic()

        available_tools = self.tools.list()
        tool_descriptions = [f"{t.name}: {t.description}" for t in available_tools]
        tool_list = "; ".join(tool_descriptions) if tool_descriptions else "(none)"

        history = self.memory.get_messages(session_id, limit=5)
        history_text = self._format_history(history)

        from datetime import date
        today = date.today().isoformat()
        system_prompt = load_prompt(
            "planner", tool_list=tool_list, today_date=today,
        )

        user_content = user_message
        if history_text:
            user_content = (
                f"Recent conversation:\n{history_text}\n\nCurrent message: {user_message}"  # noqa: E231
            )

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_content),
        ]

        try:
            response_format = None
            if getattr(self.llm, "supports_response_format", False):
                response_format = {"type": "json_object"}

            response: LLMResponse = await self.llm.chat(
                messages, response_format=response_format
            )
            self._track_tokens("planner", response.usage, response)

            plan = self._parse_plan(response.content)
            plan = self._repair_vinpearl_overview_plan(plan, user_message)

            elapsed_ms = (time.monotonic() - start) * 1000
            logger.info(
                "planner_completed",
                extra={
                    "intent": plan.intent.value,
                    "tool_name": plan.tool_name,
                    "reasoning": plan.reasoning,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "tokens": response.usage,
                },
            )
            return plan

        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error(
                "planner_failed_falling_back_to_chitchat",
                extra={"error": str(exc), "elapsed_ms": round(elapsed_ms, 2)},
            )
            return Plan(
                intent=IntentType.CHITCHAT,
                reasoning=f"Planner failed ({exc}), falling back to chitchat",
            )

    def _repair_vinpearl_overview_plan(
        self,
        plan: Plan,
        user_message: str,
    ) -> Plan:
        if (
            plan.intent in (IntentType.CLARIFY, IntentType.CHITCHAT)
            and self.tools.get("search_amenities") is not None
            and _should_force_vinpearl_overview(user_message)
        ):
            return Plan(
                intent=IntentType.TOOL,
                tool_name="search_amenities",
                tool_args={"query": user_message},
                reasoning="Vinpearl entity mention should return a knowledge-base overview.",
            )
        return plan

    def _parse_plan(self, raw: str) -> Plan:
        """Parse planner JSON into a Plan; falls back to keyword heuristic."""
        data = None

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

        if data is None:
            try:
                extracted = StructuredOutputParser._extract_json(raw)
                data = json.loads(extracted)
            except json.JSONDecodeError:
                data = None

        if data is None:
            logger.warning(
                "planner_json_parse_failed",
                extra={"raw": raw[:200]},
            )
            # Heuristic fallback
            lower = raw.lower()
            if any(kw in lower for kw in ["amenities", "pool", "spa", "restaurant"]):
                return Plan(
                    intent=IntentType.KNOWLEDGE,
                    search_query=raw[:100],
                    reasoning="JSON parse failed; detected knowledge keywords",
                )
            return Plan(
                intent=IntentType.CHITCHAT,
                reasoning="JSON parse failed; defaulting to chitchat",
            )

        try:
            return Plan.model_validate(data)
        except ValidationError as exc:
            logger.warning(
                "planner_pydantic_validation_failed",
                extra={"error": str(exc), "raw_keys": list(data.keys())},
            )
            # Fall back to keyword heuristic
            lower = str(data).lower()
            if any(kw in lower for kw in ["amenities", "pool", "spa", "restaurant"]):
                return Plan(
                    intent=IntentType.KNOWLEDGE,
                    search_query=str(data)[:100],
                    reasoning="Pydantic validation failed; detected knowledge keywords",
                )
            return Plan(
                intent=IntentType.CHITCHAT,
                reasoning="Pydantic validation failed; defaulting to chitchat",
            )

    async def execute(
        self, plan: Plan, user_message: str, session_id: str
    ) -> ExecutionResult:
        """Agent 2: Execute the plan created by the planner."""
        start = time.monotonic()

        try:
            if plan.intent == IntentType.KNOWLEDGE:
                result = await self._execute_knowledge(plan, user_message, session_id)
            elif plan.intent == IntentType.TOOL:
                result = await self._execute_tool(plan, user_message, session_id)
            elif plan.intent == IntentType.CLARIFY:
                result = await self._execute_clarify(plan, user_message, session_id)
            else:
                result = await self._execute_chitchat(plan, user_message, session_id)
        except Exception as exc:
            logger.exception(
                "executor_failed",
                extra={"intent": plan.intent.value, "error": str(exc)},
            )
            result = ExecutionResult(
                response=(
                    "I'm terribly sorry, something went wrong on my end. "
                    "Could you try rephrasing your request?"
                ),
                plan=plan,
            )

        result.latency_ms = round((time.monotonic() - start) * 1000, 2)

        logger.info(
            "executor_completed",
            extra={
                "intent": plan.intent.value,
                "latency_ms": result.latency_ms,
                "sources_count": len(result.sources),
                "tokens": result.token_usage,
            },
        )
        return result

    async def _execute_knowledge(
        self, plan: Plan, user_message: str, session_id: str
    ) -> ExecutionResult:
        """Search RAG, build context, generate response."""
        query = plan.search_query or user_message
        rag_results = self.rag.search(query, k=5)

        docs = rag_results.get("results", [])
        context_parts = []
        sources = []
        for doc in docs:
            text = doc.get("text", "")
            source = doc.get("meta", {}).get("source", "unknown")
            if text:
                context_parts.append(text)
                sources.append(source)

        if not self._has_relevant_context(query, context_parts):
            context_parts = []
            sources = []
            if self.web_search is not None:
                web_results = await self.web_search.search(query)
                for item in web_results.get("results", []):
                    text = item.get("text", "")
                    source = item.get("source", "")
                    if text and source:
                        context_parts.append(text)
                        sources.append(source)

        context = "\n---\n".join(context_parts) if context_parts else "(no results found)"
        history = self.memory.get_messages(session_id, limit=5)

        prompt = load_prompt(
            "executor.knowledge",
            context=context,
            history=self._format_history(history),
            question=user_message,
        )

        response = await self.llm.chat(
            [
                LLMMessage(role="system", content=prompt),
                LLMMessage(role="user", content=user_message),
            ]
        )
        self._track_tokens("executor", response.usage, response)

        return ExecutionResult(
            response=response.content,
            plan=plan,
            sources=sources,
            rag_contexts=context_parts,
            token_usage=response.usage,
        )

    async def _execute_tool(
        self, plan: Plan, user_message: str, session_id: str
    ) -> ExecutionResult:
        """Run a small ReAct loop: model chooses tools, observes results, then answers."""
        tool_schemas = self.tools.get_openai_tool_schemas()
        tool_names = [tool.name for tool in self.tools.list()]
        history = self.memory.get_messages(session_id, limit=5)
        tool_list = ", ".join(tool_names) if tool_names else "(none)"
        prompt = load_prompt(
            "executor.agent",
            tools=tool_list,
            history=self._format_history(history),
            question=user_message,
        )

        messages = [
            LLMMessage(role="system", content=prompt),
            LLMMessage(role="user", content=user_message),
        ]
        observations: dict[str, Any] = {}
        observation_contexts: list[str] = []
        token_usage: dict[str, int] = {}
        final_response = ""

        for _ in range(3):
            response = await self.llm.chat(
                messages,
                tools=tool_schemas,
            )
            self._track_tokens("executor", response.usage, response)
            self._merge_token_usage(token_usage, response.usage)

            if not response.tool_calls:
                final_response = response.content
                break

            messages.append(
                LLMMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            for tool_call in response.tool_calls:
                tool_result = await self._run_react_tool_call(
                    tool_call,
                    user_message=user_message,
                )
                observations[tool_call.name] = tool_result
                observation_text = json.dumps(
                    tool_result,
                    ensure_ascii=False,
                    default=str,
                )
                observation_contexts.append(observation_text)
                messages.append(
                    LLMMessage(
                        role="tool",
                        content=observation_text,
                        tool_call_id=tool_call.id,
                    )
                )

        if not final_response:
            final_response = (
                "I do not have enough verified information to answer that "
                "confidently. I can connect you with a human concierge for "
                "confirmed assistance."
            )

        return ExecutionResult(
            response=final_response,
            plan=plan,
            tool_result=observations or None,
            rag_contexts=observation_contexts,
            token_usage=token_usage,
        )

    async def _execute_clarify(
        self, plan: Plan, user_message: str, session_id: str
    ) -> ExecutionResult:
        """Generate a clarification question."""
        history = self.memory.get_messages(session_id, limit=5)

        prompt = load_prompt(
            "executor.clarify",
            reasoning=plan.reasoning,
            history=self._format_history(history),
            question=user_message,
        )

        response = await self.llm.chat(
            [
                LLMMessage(role="system", content=prompt),
                LLMMessage(role="user", content=user_message),
            ]
        )
        self._track_tokens("executor", response.usage, response)

        return ExecutionResult(
            response=response.content,
            plan=plan,
            token_usage=response.usage,
        )

    async def _execute_chitchat(
        self, plan: Plan, user_message: str, session_id: str
    ) -> ExecutionResult:
        """Generate a direct conversational response."""
        history = self.memory.get_messages(session_id, limit=5)

        prompt = load_prompt(
            "executor.chitchat",
            history=self._format_history(history),
            question=user_message,
        )

        response = await self.llm.chat(
            [
                LLMMessage(role="system", content=prompt),
                LLMMessage(role="user", content=user_message),
            ]
        )
        self._track_tokens("executor", response.usage, response)

        return ExecutionResult(
            response=response.content,
            plan=plan,
            token_usage=response.usage,
        )

    # ------------------------------------------------------------------
    # Cheap intent classifier — bypass the planner LLM when obvious
    # ------------------------------------------------------------------

    _GREETING_WORDS = frozenset([
        "hello", "hi", "hey", "howdy", "greetings", "good morning",
        "good afternoon", "good evening", "good night", "yo", "sup",
        "hiya", "morning", "evening", "afternoon",
        "xin chào", "chào", "chào buổi sáng", "chào bạn",
    ])

    _TOOL_KEYWORDS = frozenset()

    # Temporal / filter phrases that signal an event query needs search_events
    _EVENT_FILTER_SIGNALS = re.compile(
        r"this\s+(week|weekend|month|may|june|july|august|september|october"
        r"|november|december|january|february|march|april)"
        r"|next\s+(week|weekend|month)"
        r"|in\s+(may|june|july|august|september|october|november|december"
        r"|january|february|march|april)"
        r"|tonight|today|tomorrow"
        r"|cheapest|most\s+popular|family[\s-]friendly|outdoor|indoor"
        r"|adults[\s-]only|available|upcoming|happening"
        r"|full\s+moon|beach\s+bbq|sunset\s+cruise|cooking\s+class"
        r"|lantern\s+workshop|trekking|coffee\s+masterclass|wellness"
        r"|lễ hội|tiệc nướng|du thuyền|học nấu ăn|làm đèn lồng|leo núi",
        re.IGNORECASE,
    )

    _BOOKING_ID_PATTERN = re.compile(r"$^")

    def _classify_intent_cheap(
        self, text: str,
    ) -> Optional[IntentType]:
        """Return an intent if obvious, or None to defer to the planner.

        Only returns CHITCHAT or KNOWLEDGE — never TOOL, because tool
        execution needs the planner to extract tool_name and tool_args.
        Conservative: returns None on any ambiguity.
        """
        lower = text.lower().strip()
        words = lower.split()

        # Chitchat: short greetings with no substantive content
        if len(words) <= 6:
            stripped = lower.rstrip("!?.,:;")
            if stripped in self._GREETING_WORDS:
                return IntentType.CHITCHAT
            if any(g in lower for g in self._GREETING_WORDS):
                if "?" not in text and len(words) <= 4:
                    return IntentType.CHITCHAT

        # Tool-related keywords → must use planner (needs arg extraction)
        if any(k in lower for k in self._TOOL_KEYWORDS):
            return None
        if self._BOOKING_ID_PATTERN.search(text):
            return None

        # Event queries with temporal/filter language → planner (needs search_events)
        if any(w in lower for w in ("event", "events")) and self._EVENT_FILTER_SIGNALS.search(text):
            return None

        # Resort questions should go through the planner/agent so the model
        # can use tools instead of answering as a plain chatbot.
        return None

    # ------------------------------------------------------------------
    # Guardrail helpers
    # ------------------------------------------------------------------

    def _apply_input_guardrails(
        self, text: str,
    ) -> tuple[str, list[str], Optional[ExecutionResult]]:
        """Run input guardrails. Returns (sanitised_text, pii_types, block).

        If ``block`` is not None the request was rejected and handle()
        should return it immediately.
        """
        if not self.input_guard:
            return text, [], None

        safe, reason = self.input_guard.check_prompt_injection(text)
        if not safe:
            logger.warning("input_guard_blocked", extra={"reason": reason})
            return text, [], ExecutionResult(
                response="I'm unable to process that request.",
                plan=Plan(intent=IntentType.CHITCHAT),
                guardrail="prompt_injection",
            )

        if not self.input_guard.check_topic_boundary(text):
            logger.info("input_guard_off_topic")
            return text, [], ExecutionResult(
                response=_vinpearl_travel_refusal(text),
                plan=Plan(intent=IntentType.CHITCHAT),
                guardrail="off_topic",
            )

        sanitised, pii_types = self.input_guard.check_pii(text)
        return sanitised, pii_types, None

    def _apply_output_guardrails(
        self, result: ExecutionResult, pii_types: list[str],
    ) -> None:
        """Check the response for leaked PII or character breaks."""
        if not self.input_guard:
            return

        output_guard = OutputGuard(input_pii_types=pii_types)
        out_safe, out_reason = output_guard.check_response(result.response)
        if not out_safe:
            logger.warning(
                "output_guard_blocked", extra={"reason": out_reason},
            )
            result.response = (
                "I must beg your pardon — let me rephrase. "
                "How else may I assist you with your stay?"
            )
            result.guardrail = "output_blocked"

    def _apply_hallucination_detection(
        self, result: ExecutionResult,
    ) -> None:
        """Score the response and run NLI if confidence is not HIGH."""
        if not self.detector or not result.rag_contexts:
            return

        try:
            result.confidence = self.detector.score_response(
                result.response, result.rag_contexts
            )
            if result.confidence.level != ConfidenceLevel.HIGH:
                result.claim_verification = (
                    self.detector.verify_claims(
                        result.response, result.rag_contexts
                    )
                )
        except Exception as exc:
            logger.warning(
                "hallucination_detection_failed",
                extra={"error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def handle(self, user_message: str, session_id: str) -> ExecutionResult:
        """Guardrails → plan → execute → validate → save."""
        overall_start = time.monotonic()

        user_message, pii_types, block = self._apply_input_guardrails(
            user_message,
        )
        if block is not None:
            return block

        cheap_intent = self._classify_intent_cheap(user_message)

        if cheap_intent is not None:
            plan = Plan(
                intent=cheap_intent,
                reasoning="cheap classifier (planner bypassed)",
            )
            logger.info(
                "orchestrator_plan_bypassed",
                extra={
                    "intent": plan.intent.value,
                    "session_id": session_id,
                },
            )
        else:
            plan = await self.plan(user_message, session_id)
            logger.info(
                "orchestrator_plan_decided",
                extra={
                    "intent": plan.intent.value,
                    "reasoning": plan.reasoning,
                    "session_id": session_id,
                },
            )

        result = await self.execute(plan, user_message, session_id)

        if plan.intent == IntentType.KNOWLEDGE:
            self._apply_hallucination_detection(result)

        self._apply_output_guardrails(result, pii_types)
        result.pii_types = pii_types

        self.memory.add_message(session_id, "user", user_message)
        self.memory.add_message(session_id, "assistant", result.response)

        total_ms = round((time.monotonic() - overall_start) * 1000, 2)
        logger.info(
            "orchestrator_handle_completed",
            extra={
                "session_id": session_id,
                "intent": plan.intent.value,
                "total_ms": total_ms,
                "planner_tokens_total": self._total_planner_tokens,
                "executor_tokens_total": self._total_executor_tokens,
                "estimated_cost_usd": self._costs.total_cost_usd,
            },
        )

        return result

    _DANGEROUS_PATH_RE = re.compile(r"\.\.|[/\\\x00\n\r;|&`$<>()]")
    _DATE_FORMAT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    @staticmethod
    def _validate_tool_call(
        tool_name: str, tool_args: dict
    ) -> tuple[bool, str]:
        """Validate tool call arguments before execution."""
        if tool_name in ("search_amenities", "search_vinpearl_web"):
            query = tool_args.get("query", "")
            if not query or not query.strip():
                return False, "Blocked: search query cannot be empty."
            if len(query) > 500:
                return (
                    False,
                    "Blocked: search query exceeds 500 character limit.",
                )
        elif tool_name == "search_events":
            date_re = re.compile(r"^\d{4}-\d{2}-\d{2}")
            for date_field in ("start_after", "start_before"):
                val = tool_args.get(date_field)
                if val is not None and not date_re.match(str(val)):
                    return (
                        False,
                        f"Blocked: {date_field} must start with "
                        f"YYYY-MM-DD format, got '{val}'.",
                    )
            limit = tool_args.get("limit")
            if limit is not None and (limit < 1 or limit > 50):
                return (
                    False,
                    "Blocked: limit must be between 1 and 50.",
                )
            offset = tool_args.get("offset")
            if offset is not None and offset < 0:
                return (
                    False,
                    "Blocked: offset must be >= 0.",
                )
        else:
            logger.warning(
                "validate_tool_call_unknown_tool",
                extra={"tool": tool_name},
            )
        return True, ""

    async def _run_react_tool_call(self, tool_call, user_message: str = "") -> dict:
        tool = self.tools.get(tool_call.name)
        if not tool:
            return {
                "ok": False,
                "error": f"Unknown tool: {tool_call.name}",
            }

        try:
            raw_args = json.loads(tool_call.arguments or "{}")
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "Tool arguments must be valid JSON.",
            }

        if not isinstance(raw_args, dict):
            return {
                "ok": False,
                "error": "Tool arguments must be a JSON object.",
            }

        valid, reason = self._validate_tool_call(tool_call.name, raw_args)
        if not valid:
            return {
                "ok": False,
                "error": reason,
            }

        if (
            tool_call.name == "search_vinpearl_web"
            and self.tools.get("search_amenities") is not None
        ):
            vector_query = user_message or str(raw_args.get("query", ""))
            if _should_try_vector_before_web(vector_query):
                local_result = await self.tools.async_execute_with_timing(
                    "search_amenities",
                    request_id=str(uuid.uuid4()),
                    query=vector_query,
                )
                if isinstance(local_result, dict) and local_result.get("results"):
                    local_result = dict(local_result)
                    local_result.setdefault("query", vector_query)
                    local_result["web_skipped"] = "vector_first"
                    return local_result

        result = await self.tools.async_execute_with_timing(
            tool_call.name,
            request_id=str(uuid.uuid4()),
            **raw_args,
        )
        if not isinstance(result, dict):
            return {"result": result}

        if (
            tool_call.name == "search_amenities"
            and self.web_search is not None
        ):
            fallback_query = user_message or str(raw_args.get("query", ""))
            should_fallback = (
                not result.get("results")
                or _vector_result_missing_expected_evidence(fallback_query, result)
            )
            if should_fallback and is_vinpearl_query(fallback_query):
                web_result = await self.web_search.search(fallback_query)
                web_docs = [
                    {
                        "text": item.get("text", ""),
                        "meta": {
                            "source": item.get("source", ""),
                            "retrieval": "tavily",
                        },
                        "score": 0.0,
                    }
                    for item in web_result.get("results", [])
                    if item.get("text") and item.get("source")
                ]
                if web_docs:
                    return {
                        "ok": True,
                        "query": fallback_query,
                        "results": web_docs,
                        "fallback": "tavily",
                    }

        return result

    def _format_history(self, messages: list[dict]) -> str:
        """Format conversation history for prompt injection."""
        if not messages:
            return "(no prior conversation)"
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _merge_token_usage(total: dict[str, int], usage: dict) -> None:
        for key, value in usage.items():
            if isinstance(value, int):
                total[key] = total.get(key, 0) + value

    _CONTEXT_STOPWORDS = frozenset(
        {
            "a", "an", "and", "are", "about", "can", "does", "for", "has",
            "how", "is", "it", "me", "of", "on", "or", "the", "there",
            "to", "what", "where", "with", "you", "có", "của", "gì",
            "không", "là", "ở", "và", "về",
        }
    )

    @classmethod
    def _content_tokens(cls, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"\w+", text.lower())
            if len(token) > 2 and token not in cls._CONTEXT_STOPWORDS
        }

    @classmethod
    def _has_relevant_context(cls, query: str, contexts: list[str]) -> bool:
        if not contexts:
            return False

        combined_text = " ".join(contexts)
        if is_vinpearl_query(query) and "vinpearl" not in combined_text.lower():
            return False

        query_tokens = cls._content_tokens(query)
        if not query_tokens:
            return True

        combined = cls._content_tokens(combined_text)
        return bool(query_tokens & combined)

    def _track_tokens(self, agent: str, usage: dict, response: LLMResponse | None = None) -> None:
        """Accumulate token counts and estimated cost."""
        total = usage.get("total_tokens", 0)
        if agent == "planner":
            self._total_planner_tokens += total
        else:
            self._total_executor_tokens += total

        model = response.model if response else ""
        if model:
            cost = self._costs.record(model, usage)
            logger.debug(
                "cost_tracked",
                extra={"agent": agent, "model": model, "cost_usd": cost},
            )

    def get_token_stats(self) -> dict:
        """Return cumulative token usage and estimated cost."""
        return {
            "planner_tokens": self._total_planner_tokens,
            "executor_tokens": self._total_executor_tokens,
            "total_tokens": self._total_planner_tokens + self._total_executor_tokens,
            "estimated_cost": self._costs.summary(),
        }
