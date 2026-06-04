"""Mock Vinpearl event data and search function for the search_events tool."""

from __future__ import annotations

from datetime import datetime
from typing import Any

VALID_EVENT_TYPES = {
    "full_moon_festival",
    "beach_bbq",
    "sunset_cruise",
    "cooking_class",
    "lantern_workshop",
    "trekking",
    "coffee_masterclass",
    "wellness",
}

VALID_TAGS = {
    "family-friendly",
    "adults-only",
    "outdoor",
    "dining",
    "wellness",
    "music",
    "seasonal",
    "cultural",
}

VALID_SORT_FIELDS = {"date", "popularity", "price"}

MOCK_EVENTS: list[dict] = [
    {
        "id": "vp-evt-001",
        "name": "VinWonders Nha Trang Family Discovery",
        "hotel_name": "Vinpearl Nha Trang",
        "event_type": "wellness",
        "starts_at": "2026-06-08T09:00:00Z",
        "price": 0.0,
        "popularity": 94,
        "has_availability": True,
        "capacity": 80,
        "available_tickets": 24,
        "tags": ["family-friendly", "outdoor"],
        "description": "Guided resort orientation and family-friendly VinWonders planning for guests staying on Hon Tre Island.",
    },
    {
        "id": "vp-evt-002",
        "name": "Nha Trang Beach Seafood Dinner",
        "hotel_name": "Vinpearl Nha Trang",
        "event_type": "beach_bbq",
        "starts_at": "2026-06-13T18:30:00Z",
        "price": 1500000.0,
        "popularity": 91,
        "has_availability": True,
        "capacity": 120,
        "available_tickets": 18,
        "tags": ["dining", "outdoor", "music"],
        "description": "Beachside seafood dinner recommendation with resort dining reservation support.",
    },
    {
        "id": "vp-evt-003",
        "name": "Nam Hoi An River Safari Morning",
        "hotel_name": "Vinpearl Nam Hội An (Vinpearl Resort & Golf Nam Hội An)",
        "event_type": "trekking",
        "starts_at": "2026-06-10T09:00:00Z",
        "price": 0.0,
        "popularity": 93,
        "has_availability": True,
        "capacity": 90,
        "available_tickets": 31,
        "tags": ["family-friendly", "outdoor", "cultural"],
        "description": "Concierge-planned morning route through VinWonders Nam Hoi An with river safari and folk island highlights.",
    },
    {
        "id": "vp-evt-004",
        "name": "Hoi An Full Moon Lantern Evening",
        "hotel_name": "Vinpearl Nam Hội An (Vinpearl Resort & Golf Nam Hội An)",
        "event_type": "full_moon_festival",
        "starts_at": "2026-06-14T15:00:00Z",
        "price": 350000.0,
        "popularity": 86,
        "has_availability": True,
        "capacity": 35,
        "available_tickets": 9,
        "tags": ["family-friendly", "cultural"],
        "description": "Mock lantern workshop and old-town planning support for guests combining resort stay with Hoi An.",
    },
    {
        "id": "vp-evt-005",
        "name": "Phu Quoc Safari and VinWonders Day Plan",
        "hotel_name": "Vinpearl Phú Quốc",
        "event_type": "trekking",
        "starts_at": "2026-06-11T09:00:00Z",
        "price": 0.0,
        "popularity": 98,
        "has_availability": True,
        "capacity": 150,
        "available_tickets": 46,
        "tags": ["family-friendly", "outdoor"],
        "description": "Concierge route for Safari in the morning and VinWonders in the afternoon, with show-time reminders.",
    },
    {
        "id": "vp-evt-006",
        "name": "Grand World Sunset Dining Support",
        "hotel_name": "Vinpearl Phú Quốc",
        "event_type": "sunset_cruise",
        "starts_at": "2026-06-15T17:30:00Z",
        "price": 0.0,
        "popularity": 89,
        "has_availability": True,
        "capacity": 70,
        "available_tickets": 20,
        "tags": ["dining", "music", "outdoor"],
        "description": "Reservation and shuttle planning for sunset dinner or evening activities near Grand World.",
    },
    {
        "id": "vp-evt-007",
        "name": "Cua Sot Quiet Villa Wellness Morning",
        "hotel_name": "Melia Vinpearl Cửa Sót Beach Resort (Hà Tĩnh)",
        "event_type": "wellness",
        "starts_at": "2026-06-09T07:00:00Z",
        "price": 0.0,
        "popularity": 84,
        "has_availability": True,
        "capacity": 40,
        "available_tickets": 13,
        "tags": ["wellness", "outdoor", "family-friendly"],
        "description": "Quiet pool, beach, and villa-day itinerary for guests who want a slower Ha Tinh resort stay.",
    },
    {
        "id": "vp-evt-008",
        "name": "Cua Sot Water Park Family Slot",
        "hotel_name": "Melia Vinpearl Cửa Sót Beach Resort (Hà Tĩnh)",
        "event_type": "wellness",
        "starts_at": "2026-06-16T15:00:00Z",
        "price": 0.0,
        "popularity": 82,
        "has_availability": True,
        "capacity": 100,
        "available_tickets": 34,
        "tags": ["family-friendly", "outdoor"],
        "description": "Mock family slot for the internal water park and pool area, subject to weather and safety checks.",
    },
    {
        "id": "vp-evt-009",
        "name": "Bac Ninh Business Lounge Evening",
        "hotel_name": "Vinpearl Hotel Bắc Ninh",
        "event_type": "wellness",
        "starts_at": "2026-06-12T18:00:00Z",
        "price": 0.0,
        "popularity": 80,
        "has_availability": True,
        "capacity": 45,
        "available_tickets": 16,
        "tags": ["adults-only", "dining"],
        "description": "Business-traveler lounge and dining reservation support after meetings in Bac Ninh.",
    },
    {
        "id": "vp-evt-010",
        "name": "Kinh Bac Cultural Half-Day Planning",
        "hotel_name": "Vinpearl Hotel Bắc Ninh",
        "event_type": "lantern_workshop",
        "starts_at": "2026-06-18T09:00:00Z",
        "price": 0.0,
        "popularity": 78,
        "has_availability": True,
        "capacity": 30,
        "available_tickets": 7,
        "tags": ["cultural", "family-friendly"],
        "description": "Concierge planning for temples, Quan Ho heritage, and local dining near central Bac Ninh.",
    },
    {
        "id": "vp-evt-011",
        "name": "Cua Hoi Beach and Pool Morning",
        "hotel_name": "Melia Vinpearl Cửa Hội Beach Resort (Nghệ An)",
        "event_type": "wellness",
        "starts_at": "2026-06-17T07:30:00Z",
        "price": 0.0,
        "popularity": 88,
        "has_availability": True,
        "capacity": 80,
        "available_tickets": 29,
        "tags": ["wellness", "family-friendly", "outdoor"],
        "description": "Beach, pool, and quiet resort schedule for guests staying near Cua Lo and Cua Hoi.",
    },
    {
        "id": "vp-evt-012",
        "name": "Nghe An Local Seafood Dinner",
        "hotel_name": "Melia Vinpearl Cửa Hội Beach Resort (Nghệ An)",
        "event_type": "beach_bbq",
        "starts_at": "2026-06-20T18:00:00Z",
        "price": 900000.0,
        "popularity": 83,
        "has_availability": False,
        "capacity": 60,
        "available_tickets": 0,
        "tags": ["dining", "outdoor"],
        "description": "Seafood dinner planning near Cua Hoi; this mock event is currently fully booked.",
    },
    {
        "id": "vp-evt-013",
        "name": "Ha Long Island Resort Orientation",
        "hotel_name": "Vinpearl Resort & Spa Hạ Long",
        "event_type": "wellness",
        "starts_at": "2026-06-19T09:00:00Z",
        "price": 0.0,
        "popularity": 90,
        "has_availability": True,
        "capacity": 75,
        "available_tickets": 21,
        "tags": ["family-friendly", "outdoor"],
        "description": "Orientation for Dao Reu facilities, island transfers, pool, beach, and Bay-facing resort areas.",
    },
    {
        "id": "vp-evt-014",
        "name": "Ha Long Bay Sunset Dining Reservation",
        "hotel_name": "Vinpearl Resort & Spa Hạ Long",
        "event_type": "sunset_cruise",
        "starts_at": "2026-06-22T17:30:00Z",
        "price": 0.0,
        "popularity": 92,
        "has_availability": True,
        "capacity": 50,
        "available_tickets": 12,
        "tags": ["dining", "outdoor", "music"],
        "description": "Concierge support for dinner and sunset-view timing at the island resort, subject to transfer conditions.",
    },
]

_SORT_KEY_MAP = {
    "date": "starts_at",
    "popularity": "popularity",
    "price": "price",
}


def _parse_iso_date(date_str: str | None) -> datetime | None:
    """Parse an ISO date string into a naive-UTC datetime for comparison."""
    if not date_str:
        return None
    try:
        cleaned = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def search_events(
    *,
    hotel_name: str | None = None,
    event_type: str | None = None,
    start_after: str | None = None,
    start_before: str | None = None,
    has_availability: bool | None = None,
    tags: list[str] | None = None,
    sort_by: str = "date",
    sort_order: str = "asc",
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter, sort, and paginate mock resort events."""
    results = list(MOCK_EVENTS)

    if sort_by not in VALID_SORT_FIELDS:
        sort_by = "date"
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"
    if limit < 1:
        limit = 10
    if offset < 0:
        offset = 0

    if hotel_name:
        results = [e for e in results if e["hotel_name"] == hotel_name]

    if event_type:
        results = [e for e in results if e["event_type"] == event_type]

    if start_after:
        start_dt = _parse_iso_date(start_after)
        if start_dt:
            results = [
                e
                for e in results
                if _parse_iso_date(e["starts_at"])
                and _parse_iso_date(e["starts_at"]) >= start_dt
            ]

    if start_before:
        end_dt = _parse_iso_date(start_before)
        if end_dt:
            results = [
                e
                for e in results
                if _parse_iso_date(e["starts_at"])
                and _parse_iso_date(e["starts_at"]) <= end_dt
            ]

    if has_availability is not None:
        results = [e for e in results if e["has_availability"] is has_availability]

    if tags:
        wanted = {t for t in tags if t in VALID_TAGS}
        if not wanted:
            results = []
        else:
            results = [e for e in results if wanted.intersection(set(e["tags"]))]

    reverse = sort_order == "desc"
    results.sort(key=lambda e: e[_SORT_KEY_MAP[sort_by]], reverse=reverse)

    total = len(results)
    page = results[offset: offset + limit]

    return {
        "ok": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": page,
        "results": page,
    }
