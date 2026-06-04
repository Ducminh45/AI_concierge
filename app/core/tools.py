from __future__ import annotations
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict
from time import time
import uuid

from ..database.db import DatabaseManager
from ..services.pdf_generator import PDFGenerator
from ..monitoring.logging_utils import logger, MonsterResortError
from ..monitoring.metrics import Counter

logger.info("tool_module_initialized")

TOOL_TIMEOUT = 10.0  # seconds — max wall-clock time per tool call
RATE_LIMIT_MAX = 50   # max calls per tool in the rate window
RATE_LIMIT_WINDOW = 60  # seconds

# Per-tool rate tracking: tool_name -> list of timestamps
_tool_call_timestamps: dict[str, list[float]] = defaultdict(list)

# Defense 1: Authoritative hotel registry — single source of truth
VALID_HOTELS = {
    "Azure Bay Resort & Spa (Đà Nẵng)",
    "Hội An Pearl Resort (Hội An)",
    "Phú Quốc Paradise (Phú Quốc)",
    "Sapa Highland Lodge (Sapa)",
    "Nha Trang Coral Bay (Nha Trang)",
    "Đà Lạt Pine Valley (Đà Lạt)",
    "Vampire Manor: Eternal Night Inn",  # For testing compatibility
}

TOOL_CALL_COUNT = Counter("mrc_tool_calls_total", "Total tool calls", ["tool"])

ToolFn = Callable[..., Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: ToolFn

    def to_openai_schema(self) -> dict:
        logger.debug("generating_openai_schema", extra={"tool": self.name})

        if self.name == "book_room":
            return {
                "name": "book_room",
                "description": "Book a room at one of our official Monster Resort properties.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "guest_name": {"type": "string"},
                        "hotel_name": {
                            "type": "string",
                            "enum": list(VALID_HOTELS),
                        },
                        "room_type": {"type": "string"},
                        "check_in": {"type": "string"},
                        "check_out": {"type": "string"},
                    },
                    "required": [
                        "session_id",
                        "guest_name",
                        "hotel_name",
                        "room_type",
                        "check_in",
                        "check_out",
                    ],
                },
            }

        elif self.name == "get_booking":
            return {
                "name": "get_booking",
                "description": "Retrieve details for an existing booking.",
                "parameters": {
                    "type": "object",
                    "properties": {"booking_id": {"type": "string"}},
                    "required": ["booking_id"],
                },
            }

        elif self.name == "search_amenities":
            return {
                "name": "search_amenities",
                "description": "Search resort knowledge base for amenities and info.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }

        elif self.name == "search_events":
            return {
                "name": "search_events",
                "description": (
                    "Search for events across all Monster Resort "
                    "properties. Supports filtering by hotel, event "
                    "type, date range, availability, and tags. "
                    "Returns paginated results with sorting."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hotel_name": {
                            "type": "string",
                            "enum": list(VALID_HOTELS),
                            "description": "Filter by resort name",
                        },
                        "event_type": {
                            "type": "string",
                            "enum": [
                                "full_moon_festival",
                                "beach_bbq",
                                "sunset_cruise",
                                "cooking_class",
                                "lantern_workshop",
                                "trekking",
                                "coffee_masterclass",
                                "wellness",
                            ],
                            "description": (
                                "Official event category. Must be "
                                "one of the enum values. Do NOT "
                                "put audience tags like "
                                "'adults-only', 'family-friendly',"
                                " 'outdoor' here — those go in "
                                "the tags parameter."
                            ),
                        },
                        "start_after": {
                            "type": "string",
                            "description": (
                                "ISO date (YYYY-MM-DD) — only events "
                                "starting after this date. Use "
                                "today's date context to convert "
                                "relative references like 'this "
                                "May', 'next weekend', 'tonight' "
                                "to YYYY-MM-DD format."
                            ),
                        },
                        "start_before": {
                            "type": "string",
                            "description": (
                                "ISO date (YYYY-MM-DD) — only events "
                                "starting before this date. Use "
                                "today's date context to convert "
                                "relative references like 'this "
                                "May', 'next weekend', 'tonight' "
                                "to YYYY-MM-DD format."
                            ),
                        },
                        "has_availability": {
                            "type": "boolean",
                            "description": (
                                "Set to true when the user wants "
                                "events they can still book "
                                "('still available', 'tickets "
                                "left', 'can I attend'). Set to "
                                "false ONLY when the user "
                                "explicitly asks for sold-out "
                                "events ('sold out', 'fully "
                                "booked', 'what did I miss')."
                            ),
                        },
                        "tags": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "family-friendly",
                                    "adults-only",
                                    "outdoor",
                                    "dining",
                                    "wellness",
                                    "music",
                                    "seasonal",
                                ],
                            },
                            "description": (
                                "Audience and theme tags. Use "
                                "this for: adults-only, "
                                "family-friendly, outdoor, dining,"
                                " wellness, music, seasonal. "
                                "These are NOT event types — they "
                                "describe who the event is for or "
                                "what kind of experience it is."
                            ),
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["date", "popularity", "price"],
                            "description": "Field to sort results by",
                            "default": "date",
                        },
                        "sort_order": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "description": "Sort direction",
                            "default": "asc",
                        },
                        "limit": {
                            "type": "integer",
                            "description": (
                                "Maximum number of results to return "
                                "(default 10, max 50)"
                            ),
                            "default": 10,
                        },
                        "offset": {
                            "type": "integer",
                            "description": (
                                "Number of results to skip for "
                                "pagination (default 0)"
                            ),
                            "default": 0,
                        },
                    },
                    "required": [],
                },
            }

        logger.warning("no_schema_for_tool", extra={"tool": self.name})
        return {}


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        logger.info("tool_registry_initialized")

    def register(self, name: str, description: str):
        logger.debug("registering_tool", extra={"tool": name})

        def decorator(fn: ToolFn):
            self.tools[name] = Tool(name=name, description=description, fn=fn)
            logger.info("tool_registered", extra={"tool": name})
            return fn

        return decorator

    def get_openai_tool_schemas(self) -> list[dict]:
        logger.info("building_openai_tool_schemas")

        schemas = []
        for tool in self.tools.values():
            schema = tool.to_openai_schema()
            if schema:
                schemas.append({"type": "function", "function": schema})

        logger.info("openai_tool_schemas_ready", extra={"count": len(schemas)})
        return schemas

    def list(self) -> list[Tool]:
        """Return list of all registered tools (for testing)"""
        return list(self.tools.values())

    def get(self, name: str) -> Tool | None:
        """Get a tool by name (for testing)"""
        return self.tools.get(name)

    async def async_execute_with_timing(self, name: str, **kwargs) -> Any:
        request_id = kwargs.pop("request_id", str(uuid.uuid4()))

        logger.info(
            "tool_execution_started",
            extra={
                "tool": name,
                "request_id": request_id,
                "raw_kwargs": kwargs,
            },
        )

        if name not in self.tools:
            logger.error(
                "tool_not_found", extra={"tool": name, "request_id": request_id}
            )
            raise MonsterResortError(f"Tool {name} not found")

        # --- Rate-limit check ---
        now = time()
        timestamps = _tool_call_timestamps[name]
        cutoff = now - RATE_LIMIT_WINDOW
        _tool_call_timestamps[name] = [t for t in timestamps if t > cutoff]
        if len(_tool_call_timestamps[name]) >= RATE_LIMIT_MAX:
            logger.warning(
                "tool_rate_limited",
                extra={"tool": name, "request_id": request_id},
            )
            return {
                "ok": False,
                "error": (
                    f"Rate limit exceeded for tool '{name}' "
                    f"({RATE_LIMIT_MAX} calls per {RATE_LIMIT_WINDOW}s)"
                ),
                "request_id": request_id,
            }
        _tool_call_timestamps[name].append(now)

        clean_kwargs = {k.rstrip(":"): v for k, v in kwargs.items()}

        start = time()

        try:
            TOOL_CALL_COUNT.labels(tool=name).inc()

            result = await asyncio.wait_for(
                self.tools[name].fn(**clean_kwargs, request_id=request_id),
                timeout=TOOL_TIMEOUT,
            )

            elapsed_ms = round((time() - start) * 1000, 2)

            logger.info(
                "tool_execution_succeeded",
                extra={
                    "tool": name,
                    "request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                    "result": result,
                },
            )

            return result

        except asyncio.TimeoutError:
            elapsed_ms = round((time() - start) * 1000, 2)
            logger.warning(
                "tool_execution_timed_out",
                extra={
                    "tool": name,
                    "request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                    "timeout_s": TOOL_TIMEOUT,
                },
            )
            return {
                "ok": False,
                "error": f"Tool execution timed out after {TOOL_TIMEOUT:.0f}s",  # noqa: E231
                "request_id": request_id,
            }

        except Exception as e:
            elapsed_ms = round((time() - start) * 1000, 2)

            logger.exception(
                "tool_execution_failed",
                extra={
                    "tool": name,
                    "request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                    "error": str(e),
                },
            )

            return {"ok": False, "error": str(e), "request_id": request_id}


def make_registry(
    db: DatabaseManager,
    pdf: PDFGenerator,
    rag_search_fn: Callable,
) -> ToolRegistry:
    logger.info("initializing_tool_registry")

    registry = ToolRegistry()

    @registry.register("book_room", "Create a new booking")
    async def book_room(
        session_id: str,
        guest_name: str,
        hotel_name: str,
        room_type: str,
        check_in: str,
        check_out: str,
        request_id: str,
    ):
        logger.info(
            "book_room_called",
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "guest_name": guest_name,
                "hotel_name": hotel_name,
            },
        )

        # Defense 1: Reject bookings for unknown hotels
        if hotel_name not in VALID_HOTELS:
            logger.warning(
                "book_room_rejected_invalid_hotel",
                extra={"hotel_name": hotel_name, "request_id": request_id},
            )
            return {
                "ok": False,
                "error": f"Invalid hotel: '{hotel_name}'. Must be one of our official properties.",
                "request_id": request_id,
            }

        try:
            booking = db.create_booking(
                session_id=session_id,
                guest_name=guest_name,
                hotel_name=hotel_name,
                room_type=room_type,
                check_in=check_in,
                check_out=check_out,
            )

            booking_id = booking.get("booking_id")

            logger.info(
                "booking_created",
                extra={
                    "request_id": request_id,
                    "booking_id": booking_id,
                },
            )

            invoice_url = None
            try:
                items = [(f"{room_type} at {hotel_name}", 299.99)]

                pdf.create_receipt(
                    guest_name=guest_name,
                    booking_id=booking_id,
                    items=items,
                )

                invoice_url = (
                    f"/invoices/receipt_{booking_id}_"
                    f"{guest_name.replace(' ', '_')}.pdf"
                )

                logger.info(
                    "receipt_generated",
                    extra={
                        "request_id": request_id,
                        "invoice_url": invoice_url,
                    },
                )

            except Exception as pdf_err:
                logger.warning(
                    "receipt_generation_failed",
                    extra={
                        "request_id": request_id,
                        "error": str(pdf_err),
                    },
                )

            return {
                "ok": True,
                "booking_id": booking_id,
                "message": f"Stay confirmed at {hotel_name}!",
                "invoice_url": invoice_url,
                "request_id": request_id,
            }

        except Exception as e:
            logger.exception(
                "book_room_failed",
                extra={
                    "request_id": request_id,
                    "error": str(e),
                },
            )
            return {"ok": False, "error": str(e), "request_id": request_id}

    @registry.register("get_booking", "Look up a booking")
    async def get_booking(booking_id: str, request_id: str):
        logger.info(
            "get_booking_called",
            extra={
                "request_id": request_id,
                "booking_id": booking_id,
            },
        )

        booking = db.get_booking(booking_id)

        result = (
            {"ok": True, "booking": booking, "request_id": request_id}
            if booking
            else {"ok": False, "error": "Not found", "request_id": request_id}
        )

        logger.info(
            "get_booking_completed",
            extra={
                "request_id": request_id,
                "found": bool(booking),
            },
        )

        return result

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        logger.info(
            "search_amenities_called",
            extra={
                "request_id": request_id,
                "query": query,
            },
        )

        result = rag_search_fn(query)

        logger.info(
            "search_amenities_completed",
            extra={
                "request_id": request_id,
                "result_count": len(result) if hasattr(result, "__len__") else None,
            },
        )

        return result

    from ..data.events import search_events as _search_events_fn

    # --- Normalisation maps for search_events wrapper ---
    _TAG_ALIASES: dict[str, str] = {
        "kid friendly": "family-friendly",
        "kid-friendly": "family-friendly",
        "adult": "adults-only",
        "adult only": "adults-only",
        "adult-only": "adults-only",
        "outdoors": "outdoor",
        "food": "dining",
    }
    _SORT_ORDER_ALIASES: dict[str, str] = {
        "ascending": "asc",
        "descending": "desc",
    }

    def _normalise_tag(tag: str) -> str:
        """Normalise a single tag: apply aliases, then space->hyphen + lower."""
        t = tag.strip().lower()
        if t in _TAG_ALIASES:
            return _TAG_ALIASES[t]
        return t.replace(" ", "-")

    @registry.register(
        "search_events",
        "Search for events across all Monster Resort properties. "
        "Supports filtering by hotel, event type, date range, "
        "availability, and tags. Returns paginated results with sorting.",
    )
    async def search_events_tool(request_id: str, **kwargs):
        logger.info(
            "search_events_called",
            extra={"request_id": request_id, "kwargs": kwargs},
        )

        # Map common LLM parameter name variants to our function signature
        _PARAM_ALIASES = {
            "hotel": "hotel_name",
            "availability": "has_availability",
            "type": "event_type",
            "sort": "sort_by",
            "order": "sort_order",
            "tag": "tags",
        }
        _VALID_PARAMS = {
            "hotel_name", "event_type", "start_after", "start_before",
            "has_availability", "tags", "sort_by", "sort_order",
            "limit", "offset",
        }
        cleaned = {}
        for k, v in kwargs.items():
            key = _PARAM_ALIASES.get(k, k)
            if key in _VALID_PARAMS:
                cleaned[key] = v
        # Fuzzy-match hotel_name if LLM sends a partial name
        if "hotel_name" in cleaned and cleaned["hotel_name"]:
            from ..data.events import MOCK_EVENTS
            known_hotels = {e["hotel_name"] for e in MOCK_EVENTS}
            given = cleaned["hotel_name"].lower()
            for full_name in known_hotels:
                if given in full_name.lower():
                    cleaned["hotel_name"] = full_name
                    break

        # Normalise event_type: "full moon party" -> "full_moon_party"
        if "event_type" in cleaned and cleaned["event_type"]:
            cleaned["event_type"] = (
                cleaned["event_type"].strip().lower().replace(" ", "_")
            )

        # Normalise tags: aliases + space->hyphen
        if "tags" in cleaned and cleaned["tags"]:
            cleaned["tags"] = [_normalise_tag(t) for t in cleaned["tags"]]

        # Normalise sort_by: lowercase
        if "sort_by" in cleaned and cleaned["sort_by"]:
            cleaned["sort_by"] = cleaned["sort_by"].strip().lower()

        # Normalise sort_order: "ascending"->"asc", "descending"->"desc"
        if "sort_order" in cleaned and cleaned["sort_order"]:
            raw = cleaned["sort_order"].strip().lower()
            cleaned["sort_order"] = _SORT_ORDER_ALIASES.get(raw, raw)

        # Coerce has_availability string to bool
        if "has_availability" in cleaned:
            v = cleaned["has_availability"]
            if isinstance(v, str):
                cleaned["has_availability"] = v.strip().lower() == "true"

        # Coerce limit/offset to int
        for int_field in ("limit", "offset"):
            if int_field in cleaned:
                try:
                    cleaned[int_field] = int(cleaned[int_field])
                except (ValueError, TypeError):
                    del cleaned[int_field]

        # Wrap single tag string in a list
        if "tags" in cleaned and isinstance(cleaned["tags"], str):
            cleaned["tags"] = [cleaned["tags"]]

        # --- Post-normalisation validation ---
        # Tag bleed detection: if event_type is actually a tag, move it
        if "event_type" in cleaned and cleaned["event_type"]:
            from ..data.events import VALID_TAGS, VALID_EVENT_TYPES
            et = cleaned["event_type"]
            if et in VALID_TAGS or et.replace("_", "-") in VALID_TAGS:
                tags = cleaned.get("tags", [])
                tags.append(et.replace("_", "-"))
                cleaned["tags"] = tags
                del cleaned["event_type"]
                logger.info(
                    f"search_events: moved '{et}' from event_type to tags"
                )
            # Ensure event_type is valid; drop unknown values silently
            elif et not in VALID_EVENT_TYPES:
                logger.warning(
                    "search_events: unknown event_type "
                    f"'{et}', removing"
                )
                del cleaned["event_type"]

        result = _search_events_fn(**cleaned)

        logger.info(
            "search_events_completed",
            extra={
                "request_id": request_id,
                "result_count": (
                    len(result.get("results", []))
                    if isinstance(result, dict)
                    else None
                ),
            },
        )

        return result

    logger.info("tool_registry_ready")
    return registry
