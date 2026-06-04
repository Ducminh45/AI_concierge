"""Prompt Loader — loads and caches prompt templates from YAML files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


@lru_cache(maxsize=64)
def _load_yaml(file_path: str) -> dict[str, Any]:
    """Read and parse a YAML file, cached by absolute path."""
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt(name: str, **kwargs: str) -> str:
    """Return a prompt template resolved by dot-notation name, with optional variable substitution."""
    parts = name.split(".")
    file_name = parts[0]
    yaml_path = str(_PROMPTS_DIR / f"{file_name}.yaml")

    if not Path(yaml_path).exists():
        raise FileNotFoundError(f"Prompt file not found: {yaml_path}")

    data = _load_yaml(yaml_path)

    node = data
    for key in parts[1:]:
        if not isinstance(node, dict) or key not in node:
            raise KeyError(
                f"Prompt key '{key}' not found in {file_name}.yaml"  # noqa: E713
            )
        node = node[key]

    if isinstance(node, dict):
        template = node.get("prompt")
        if template is None:
            raise KeyError(f"No 'prompt' key in {name}")
    elif isinstance(node, str):
        template = node
    else:
        raise TypeError(f"Unexpected type for prompt '{name}': {type(node)}")

    template = template.strip()

    if kwargs:
        return template.format_map(kwargs)
    return template
