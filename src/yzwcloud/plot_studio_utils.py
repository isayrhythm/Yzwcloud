from __future__ import annotations

from typing import Any


def _normalize_plot_id(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _first_present(values: dict[str, int], *keys: str) -> int | None:
    for key in keys:
        if key in values:
            return values[key]
    return None


def _normalize_column_name(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _parse_float(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _round_number(value: float) -> float:
    if abs(value) >= 1000:
        return round(value, 2)
    return round(value, 4)
