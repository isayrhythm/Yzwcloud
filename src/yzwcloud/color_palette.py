from __future__ import annotations

from collections.abc import Iterable, Mapping


CONDITION_PALETTE = [
    "#0052d9",
    "#2b74d6",
    "#315fd6",
    "#244ba8",
    "#7a4fb3",
    "#475467",
    "#98a2b3",
    "#d54941",
    "#b33d7a",
]


def condition_color_map(
    conditions: Iterable[str],
    existing: Mapping[str, str] | None = None,
) -> dict[str, str]:
    existing = existing or {}
    ordered = sorted({str(condition).strip() for condition in conditions if str(condition).strip()})
    colors: dict[str, str] = {}
    used = set()

    for condition in ordered:
        color = str(existing.get(condition) or "").strip()
        if color:
            colors[condition] = color
            used.add(color.lower())

    palette_index = 0
    for condition in ordered:
        if condition in colors:
            continue
        while CONDITION_PALETTE[palette_index % len(CONDITION_PALETTE)].lower() in used:
            palette_index += 1
        color = CONDITION_PALETTE[palette_index % len(CONDITION_PALETTE)]
        colors[condition] = color
        used.add(color.lower())
        palette_index += 1

    return colors
