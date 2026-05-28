from __future__ import annotations

from collections.abc import Iterable, Mapping


CONDITION_PALETTE = [
    "#0f8a8f",
    "#315fd6",
    "#c44f3a",
    "#7b61b5",
    "#20804f",
    "#c27a18",
    "#8b5f4d",
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
