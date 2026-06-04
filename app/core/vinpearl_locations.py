"""Vinpearl property geo-registry and detection for the map feature.

Coordinates are approximate property locations, accurate enough to centre
and zoom an OpenStreetMap view on the right destination.
"""

from __future__ import annotations

import unicodedata


def _normalize(text: str) -> str:
    lowered = (text or "").lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


# id, display name, latitude, longitude, default zoom, normalized aliases
VINPEARL_LOCATIONS: list[dict] = [
    {
        "id": "nha-trang",
        "name": "Vinpearl Nha Trang",
        "lat": 12.2145,
        "lng": 109.2962,
        "zoom": 14,
        "aliases": ("nha trang", "hon tre"),
    },
    {
        "id": "nam-hoi-an",
        "name": "Vinpearl Nam Hội An",
        "lat": 15.7016,
        "lng": 108.3735,
        "zoom": 14,
        "aliases": ("nam hoi an", "hoi an"),
    },
    {
        "id": "phu-quoc",
        "name": "Vinpearl Phú Quốc",
        "lat": 10.3247,
        "lng": 103.8540,
        "zoom": 13,
        "aliases": ("phu quoc", "bai dai"),
    },
    {
        "id": "cua-sot",
        "name": "Melia Vinpearl Cửa Sót (Hà Tĩnh)",
        "lat": 18.3530,
        "lng": 105.9090,
        "zoom": 13,
        "aliases": ("cua sot", "ha tinh"),
    },
    {
        "id": "bac-ninh",
        "name": "Vinpearl Hotel Bắc Ninh",
        "lat": 21.1845,
        "lng": 106.0750,
        "zoom": 14,
        "aliases": ("bac ninh",),
    },
    {
        "id": "cua-hoi",
        "name": "Melia Vinpearl Cửa Hội (Nghệ An)",
        "lat": 18.7820,
        "lng": 105.7090,
        "zoom": 13,
        "aliases": ("cua hoi", "cua lo", "nghe an"),
    },
    {
        "id": "ha-long",
        "name": "Vinpearl Resort & Spa Hạ Long",
        "lat": 20.9470,
        "lng": 107.0735,
        "zoom": 13,
        "aliases": ("ha long", "dao reu"),
    },
]


def _public(loc: dict) -> dict:
    return {
        "id": loc["id"],
        "name": loc["name"],
        "lat": loc["lat"],
        "lng": loc["lng"],
        "zoom": loc["zoom"],
    }


def detect_locations(text: str, limit: int = 3) -> list[dict]:
    """Return Vinpearl properties whose alias appears in the text, in order of
    first appearance, deduplicated, capped at ``limit``."""
    normalized = f" {_normalize(text)} "
    matched: list[tuple[int, dict]] = []
    for loc in VINPEARL_LOCATIONS:
        position = min(
            (normalized.find(f" {alias} ") for alias in loc["aliases"]
             if f" {alias} " in normalized),
            default=-1,
        )
        if position >= 0:
            matched.append((position, _public(loc)))

    matched.sort(key=lambda item: item[0])
    return [loc for _, loc in matched[:limit]]
