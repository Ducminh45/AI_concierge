"""Extracts valid JSON from raw LLM text."""

from __future__ import annotations

import json


class StructuredOutputParser:
    """Extracts JSON from messy LLM responses."""

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract the first valid JSON value from LLM text using raw_decode."""
        start_obj = text.find("{")
        start_arr = text.find("[")
        candidates = [s for s in (start_obj, start_arr) if s != -1]

        if not candidates:
            return text.strip()

        decoder = json.JSONDecoder()
        for i in range(min(candidates), len(text)):
            if text[i] not in ("{", "["):
                continue
            try:
                obj, end = decoder.raw_decode(text[i:])
                return json.dumps(obj)
            except json.JSONDecodeError:
                continue

        return text.strip()
