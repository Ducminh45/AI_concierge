"""Mock event data and search function for the search_events tool in Vietnam Luxury Resorts."""

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
    "full_moon_party",
    "haunted_tour",
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
    "indoor",
}

VALID_SORT_FIELDS = {"date", "popularity", "price"}

MOCK_EVENTS: list[dict] = [
    # --- Azure Bay Resort & Spa (Đà Nẵng) ---
    {
        "id": "evt-001",
        "name": "Lunar New Year Celebration (Lễ Hội Tết Nguyên Đán)",
        "hotel_name": "Azure Bay Resort & Spa (Đà Nẵng)",
        "event_type": "full_moon_festival",
        "starts_at": "2026-05-03T09:00:00Z",
        "price": 0.0,
        "popularity": 98,
        "has_availability": True,
        "capacity": 1000,
        "available_tickets": 250,
        "tags": ["cultural", "seasonal", "family-friendly"],
        "description": "Lion dancing, calligraphy markets, and Banh Chung making classes under open sky.",
    },
    {
        "id": "evt-002",
        "name": "Saturday Beach Seafood BBQ",
        "hotel_name": "Azure Bay Resort & Spa (Đà Nẵng)",
        "event_type": "beach_bbq",
        "starts_at": "2026-05-09T18:30:00Z",
        "price": 1500000.0,
        "popularity": 92,
        "has_availability": True,
        "capacity": 150,
        "available_tickets": 15,
        "tags": ["dining", "outdoor", "music"],
        "description": "Fresh lobsters, oysters, and fish caught daily, grilled live on the beach with fire dancing.",
    },
    {
        "id": "evt-003",
        "name": "Sun Sea Sand Yoga",
        "hotel_name": "Azure Bay Resort & Spa (Đà Nẵng)",
        "event_type": "wellness",
        "starts_at": "2026-05-15T06:30:00Z",
        "price": 0.0,
        "popularity": 85,
        "has_availability": True,
        "capacity": 50,
        "available_tickets": 18,
        "tags": ["wellness", "outdoor", "family-friendly"],
        "description": "Sunrise yoga session on the sandy shores of Da Nang led by our yoga masters.",
    },
    
    # --- Hội An Pearl Resort (Hội An) ---
    {
        "id": "evt-004",
        "name": "Full Moon Lantern Festival (Đêm Rằm Phố Cổ)",
        "hotel_name": "Hội An Pearl Resort (Hội An)",
        "event_type": "full_moon_festival",
        "starts_at": "2026-05-20T18:00:00Z",
        "price": 0.0,
        "popularity": 97,
        "has_availability": True,
        "capacity": 400,
        "available_tickets": 85,
        "tags": ["cultural", "seasonal", "family-friendly"],
        "description": "Traditional flower lanterns released on the river under starlight.",
    },
    {
        "id": "evt-005",
        "name": "Hoi An Lantern Making Workshop",
        "hotel_name": "Hội An Pearl Resort (Hội An)",
        "event_type": "lantern_workshop",
        "starts_at": "2026-05-22T15:00:00Z",
        "price": 0.0,
        "popularity": 88,
        "has_availability": True,
        "capacity": 30,
        "available_tickets": 5,
        "tags": ["cultural", "family-friendly"],
        "description": "Learn from local artisans how to construct bamboo lantern frames with colorful silk.",
    },
    {
        "id": "evt-006",
        "name": "Thu Bon River Sunset Wine Cruise",
        "hotel_name": "Hội An Pearl Resort (Hội An)",
        "event_type": "sunset_cruise",
        "starts_at": "2026-05-25T16:30:00Z",
        "price": 600000.0,
        "popularity": 90,
        "has_availability": False,
        "capacity": 40,
        "available_tickets": 0,
        "tags": ["adults-only", "dining", "outdoor"],
        "description": "A romantic sunset cruise along the Thu Bon River, serving premium wines and local delicacies.",
    },

    # --- Phú Quốc Paradise (Phú Quốc) ---
    {
        "id": "evt-007",
        "name": "SunsetHorizon Cocktail Masterclass",
        "hotel_name": "Phú Quốc Paradise (Phú Quốc)",
        "event_type": "coffee_masterclass",
        "starts_at": "2026-05-28T16:30:00Z",
        "price": 450000.0,
        "popularity": 78,
        "has_availability": True,
        "capacity": 25,
        "available_tickets": 8,
        "tags": ["adults-only", "dining"],
        "description": "Learn to mix tropical cocktails using Phú Quốc sim wine at our rooftop bar.",
    },
    {
        "id": "evt-008",
        "name": "Coral Reef Snorkeling Safari",
        "hotel_name": "Phú Quốc Paradise (Phú Quốc)",
        "event_type": "trekking",
        "starts_at": "2026-06-01T08:30:00Z",
        "price": 1200000.0,
        "popularity": 95,
        "has_availability": True,
        "capacity": 50,
        "available_tickets": 12,
        "tags": ["outdoor", "family-friendly"],
        "description": "Speedboat tour to the pristine coral reefs of Phu Quoc South Island.",
    },
    {
        "id": "evt-009",
        "name": "Night Squid Fishing Excursion",
        "hotel_name": "Phú Quốc Paradise (Phú Quốc)",
        "event_type": "sunset_cruise",
        "starts_at": "2026-06-04T17:00:00Z",
        "price": 750000.0,
        "popularity": 84,
        "has_availability": True,
        "capacity": 40,
        "available_tickets": 14,
        "tags": ["outdoor", "dining", "family-friendly"],
        "description": "Catch fresh squids under the starlight on a traditional wooden boat.",
    },

    # --- Sapa Highland Lodge (Sapa) ---
    {
        "id": "evt-010",
        "name": "Ta Van & Lao Chai Trekking Adventure",
        "hotel_name": "Sapa Highland Lodge (Sapa)",
        "event_type": "trekking",
        "starts_at": "2026-06-08T09:00:00Z",
        "price": 450000.0,
        "popularity": 94,
        "has_availability": True,
        "capacity": 30,
        "available_tickets": 11,
        "tags": ["outdoor", "cultural"],
        "description": "Trek through the breathtaking Muong Hoa valley and local ethnic villages.",
    },
    {
        "id": "evt-011",
        "name": "Ethnic Brocade Indigo Dyeing Class",
        "hotel_name": "Sapa Highland Lodge (Sapa)",
        "event_type": "lantern_workshop",
        "starts_at": "2026-06-11T14:00:00Z",
        "price": 350000.0,
        "popularity": 81,
        "has_availability": True,
        "capacity": 20,
        "available_tickets": 4,
        "tags": ["cultural", "family-friendly"],
        "description": "Learn batik and indigo dyeing techniques from local H'mong craftswomen.",
    },
    {
        "id": "evt-012",
        "name": "Red Dao Herbal Bath Detox",
        "hotel_name": "Sapa Highland Lodge (Sapa)",
        "event_type": "wellness",
        "starts_at": "2026-06-14T09:00:00Z",
        "price": 650000.0,
        "popularity": 89,
        "has_availability": False,
        "capacity": 15,
        "available_tickets": 0,
        "tags": ["wellness", "adults-only"],
        "description": "Soak in heated wooden tubs filled with Sapa forest medicinal herbs.",
    },

    # --- Nha Trang Coral Bay (Nha Trang) ---
    {
        "id": "evt-013",
        "name": "Coral Bay Scuba Diving Experience",
        "hotel_name": "Nha Trang Coral Bay (Nha Trang)",
        "event_type": "trekking",
        "starts_at": "2026-06-18T08:00:00Z",
        "price": 1800000.0,
        "popularity": 91,
        "has_availability": True,
        "capacity": 20,
        "available_tickets": 3,
        "tags": ["outdoor", "adults-only"],
        "description": "Explore the majestic marine reserve in Nha Trang with certified PADI divers.",
    },
    {
        "id": "evt-014",
        "name": "Catamaran Sunset Sailing",
        "hotel_name": "Nha Trang Coral Bay (Nha Trang)",
        "event_type": "sunset_cruise",
        "starts_at": "2026-06-21T16:30:00Z",
        "price": 1400000.0,
        "popularity": 87,
        "has_availability": True,
        "capacity": 30,
        "available_tickets": 10,
        "tags": ["outdoor", "dining", "music"],
        "description": "Sail across Nha Trang Bay with live saxophone tunes and champagne.",
    },

    # --- Đà Lạt Pine Valley (Đà Lạt) ---
    {
        "id": "evt-015",
        "name": "Premium Cau Dat Drip Coffee Masterclass",
        "hotel_name": "Đà Lạt Pine Valley (Đà Lạt)",
        "event_type": "coffee_masterclass",
        "starts_at": "2026-06-25T10:00:00Z",
        "price": 350000.0,
        "popularity": 86,
        "has_availability": True,
        "capacity": 25,
        "available_tickets": 9,
        "tags": ["cultural", "dining", "family-friendly"],
        "description": "Learn to brew iconic Vietnamese coffee types using Cau Dat Arabica beans.",
    },
    {
        "id": "evt-016",
        "name": "French Heritage Wine Soirée",
        "hotel_name": "Đà Lạt Pine Valley (Đà Lạt)",
        "event_type": "beach_bbq",
        "starts_at": "2026-06-28T19:00:00Z",
        "price": 950000.0,
        "popularity": 90,
        "has_availability": True,
        "capacity": 40,
        "available_tickets": 12,
        "tags": ["adults-only", "dining", "seasonal"],
        "description": "Sample French & local wines paired with artisan cheeses in a restored 1930s villa.",
    },
    {
        "id": "evt-017",
        "name": "Evening Bonfire & Acoustic Guitar",
        "hotel_name": "Đà Lạt Pine Valley (Đà Lạt)",
        "event_type": "wellness",
        "starts_at": "2026-07-02T19:30:00Z",
        "price": 0.0,
        "popularity": 93,
        "has_availability": True,
        "capacity": 100,
        "available_tickets": 45,
        "tags": ["music", "outdoor", "family-friendly"],
        "description": "Toast marshmallows and listen to soft guitar melodies under Dalat pine trees.",
    },
    # --- Original Mock Events for test suite compatibility ---
    {
        "id": "evt-old-1",
        "name": "Full Moon Party",
        "hotel_name": "The Werewolf Lodge: Moon & Moor",
        "event_type": "full_moon_party",
        "starts_at": "2026-05-15T20:00:00Z",
        "price": 50.0,
        "popularity": 80,
        "has_availability": True,
        "capacity": 200,
        "available_tickets": 50,
        "tags": ["music", "outdoor"],
        "description": "A spooky party.",
    },
    {
        "id": "evt-old-2",
        "name": "Haunted House Tour",
        "hotel_name": "Vampire Manor: Eternal Night Inn",
        "event_type": "haunted_tour",
        "starts_at": "2026-06-20T21:00:00Z",
        "price": 20.0,
        "popularity": 90,
        "has_availability": True,
        "capacity": 50,
        "available_tickets": 20,
        "tags": ["family-friendly", "indoor"],
        "description": "A spooky tour.",
    }
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

    # --- input validation ---
    if sort_by not in VALID_SORT_FIELDS:
        sort_by = "date"
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"
    if limit < 1:
        limit = 10
    if offset < 0:
        offset = 0

    # --- filters (only applied when provided) ---
    if hotel_name:
        results = [e for e in results if e["hotel_name"] == hotel_name]

    if event_type:
        results = [e for e in results if e["event_type"] == event_type]

    if start_after:
        start_dt = _parse_iso_date(start_after)
        if start_dt:
            results = [
                e for e in results
                if _parse_iso_date(e["starts_at"])
                and _parse_iso_date(e["starts_at"]) > start_dt
            ]

    if start_before:
        end_dt = _parse_iso_date(start_before)
        if end_dt:
            results = [
                e for e in results
                if _parse_iso_date(e["starts_at"])
                and _parse_iso_date(e["starts_at"]) < end_dt
            ]

    if has_availability is not None:
        results = [
            e for e in results
            if e["has_availability"] is has_availability
        ]

    if tags:
        tag_set = {t.lower() for t in tags}
        results = [
            e for e in results
            if tag_set & {t.lower() for t in e.get("tags", [])}
        ]

    # --- sort ---
    sort_key = _SORT_KEY_MAP.get(sort_by, "starts_at")
    reverse = sort_order == "desc"
    results.sort(key=lambda e: e[sort_key], reverse=reverse)

    # --- paginate ---
    total = len(results)
    page = results[offset: offset + limit]

    return {
        "ok": True,
        "events": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
