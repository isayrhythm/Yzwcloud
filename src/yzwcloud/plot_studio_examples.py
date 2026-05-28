from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from yzwcloud.config import DATA_DIR
from yzwcloud.plot_studio_presets import PLOT_PRESETS


PLOT_STUDIO_EXAMPLES_DIR = DATA_DIR / "plot_studio_examples"

EXAMPLE_PLOT_IDS = {str(preset["id"]) for preset in PLOT_PRESETS}

BASE_COLUMNS = [
    "gene",
    "sample",
    "subject",
    "group",
    "condition",
    "label",
    "category",
    "term",
    "parent",
    "source",
    "target",
    "date",
    "time",
    "x",
    "y",
    "z",
    "size",
    "value",
    "score",
    "count",
    "gene_ratio",
    "ratio",
    "padj",
    "p_value",
    "log2fc",
    "baseMean",
    "effect",
    "ci_low",
    "ci_high",
    "estimate",
    "lower",
    "upper",
    "actual",
    "predicted",
    "dose",
    "response",
    "before",
    "after",
    "start",
    "end",
    "survival_time",
    "event",
    "set_a",
    "set_b",
    "set_c",
    "set_d",
]

PLOT_COLUMN_PRIORITY = {
    "upset": ["gene", "set_a", "set_b", "set_c", "set_d", "group", "category", "value"],
    "venn": ["gene", "set_a", "set_b", "set_c", "set_d", "group", "category", "value"],
    "sankey": ["source", "target", "value", "group", "category", "term", "count"],
    "composition_bar": ["sample", "category", "value", "group", "count", "term"],
    "donut": ["category", "value", "group", "sample", "count", "term"],
    "treemap": ["term", "parent", "count", "padj", "category", "value"],
    "sunburst": ["term", "parent", "count", "padj", "category", "value"],
    "wordcloud": ["term", "count", "padj", "category", "value"],
    "enrichment_dot": ["term", "gene_ratio", "count", "padj", "p_value", "category"],
    "enrichment_bar": ["term", "gene_ratio", "count", "padj", "p_value", "category"],
    "roc_curve": ["score", "label", "group", "gene", "value"],
    "pr_curve": ["score", "label", "group", "gene", "value"],
    "kaplan_meier": ["survival_time", "event", "group", "subject", "value"],
    "paired_dot": ["value", "condition", "subject", "group", "gene"],
    "dumbbell": ["gene", "before", "after", "group", "value"],
    "dose_response": ["dose", "response", "group", "gene", "value"],
    "forest_plot": ["term", "effect", "ci_low", "ci_high", "group", "p_value"],
    "bland_altman": ["actual", "predicted", "group", "gene", "value"],
    "calendar_heatmap": ["date", "value", "group", "sample", "term"],
    "surface_3d": ["x", "y", "z", "group", "gene"],
    "scatter_3d": ["x", "y", "z", "group", "gene"],
    "heatmap": ["gene", "sample", "value", "score", "x", "y", "z", "count"],
    "correlation": ["x", "y", "z", "value", "score", "count", "response", "gene"],
}


def example_source_for_plot(plot_id: str) -> dict[str, Any]:
    normalized_plot_id = str(plot_id or "").strip()
    if normalized_plot_id not in EXAMPLE_PLOT_IDS:
        raise ValueError(f"Unknown Plot Studio plot type: {plot_id}")

    path = _ensure_example_table(normalized_plot_id)
    return {
        "sourceKind": "plot_studio_example",
        "taskId": "",
        "taskName": "Plot Studio examples",
        "nodeId": f"example_{normalized_plot_id}",
        "name": path.name,
        "status": "ready",
        "type": "example_table",
        "summary": f"Built-in example table for {normalized_plot_id.replace('_', ' ')}.",
        "dataPath": str(path),
        "previewUrl": "",
        "htmlUrl": "",
        "meta": {
            "plot_id": normalized_plot_id,
            "example": True,
        },
    }


def _ensure_example_table(plot_id: str) -> Path:
    PLOT_STUDIO_EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    path = PLOT_STUDIO_EXAMPLES_DIR / f"{plot_id}_example.csv"
    rows = _example_rows()
    columns = _columns_for_plot(plot_id)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _columns_for_plot(plot_id: str) -> list[str]:
    priority = PLOT_COLUMN_PRIORITY.get(plot_id, [])
    seen = set(priority)
    return priority + [column for column in BASE_COLUMNS if column not in seen]


def _example_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    genes = [
        "ALDH2",
        "BRAF",
        "CDK2",
        "EGFR",
        "FOXO3",
        "GATA3",
        "HIF1A",
        "IL6",
        "JUN",
        "KRAS",
        "MAPK1",
        "NFKB1",
        "PIK3CA",
        "STAT3",
        "TP53",
        "VEGFA",
    ]
    terms = [
        "Glycolysis",
        "Immune activation",
        "Cell cycle",
        "Apoptosis",
        "Hypoxia",
        "MAPK signaling",
        "ECM organization",
        "Lipid metabolism",
    ]
    parents = ["Metabolism", "Immunity", "Growth", "Stress"]
    categories = ["Pathway A", "Pathway B", "Pathway C", "Pathway D"]
    conditions = ["Control", "Treatment"]
    groups = ["Case", "Control"]

    for index in range(32):
        gene = genes[index % len(genes)]
        sample = f"S{index // 4 + 1:02d}"
        subject = f"P{index // 2 + 1:02d}"
        group = groups[index % len(groups)]
        condition = conditions[(index // 2) % len(conditions)]
        category = categories[index % len(categories)]
        term = terms[index % len(terms)]
        parent = parents[index % len(parents)]
        x = index + 1
        y = round(4.5 + (index % 8) * 0.9 + (index // 8) * 0.35, 3)
        z = round((index % 4) * 1.2 + (index // 4) * 0.18 + 1.0, 3)
        value = round(20 + (index % 6) * 7 + (index // 6) * 2.5, 3)
        score = round(0.08 + (index % 16) / 18, 4)
        log2fc = round(((index % 9) - 4) * 0.55, 3)
        p_value = round(0.002 + (index % 12) * 0.007, 5)
        before = round(35 + (index % 7) * 2.2, 3)
        after = round(before + ((index % 5) - 1) * 2.8 + 4.0, 3)
        count = 8 + (index % 13)
        dose = 0.05 * (2 ** (index % 8))
        response = round(92 - (index % 8) * 8.5 + (index // 8) * 2.0, 3)
        set_memberships = {
            "set_a": "1" if index % 2 == 0 else "",
            "set_b": "1" if index % 3 != 0 else "",
            "set_c": "1" if index % 4 in {0, 1} else "",
            "set_d": "1" if index % 5 in {0, 2} else "",
        }
        rows.append(
            {
                "gene": gene,
                "sample": sample,
                "subject": subject,
                "group": group,
                "condition": condition,
                "label": "positive" if index % 3 == 0 else "negative",
                "category": category,
                "term": term,
                "parent": parent,
                "source": parent,
                "target": term,
                "date": f"2026-01-{index % 28 + 1:02d}",
                "time": index + 1,
                "x": x,
                "y": y,
                "z": z,
                "size": count,
                "value": value,
                "score": score,
                "count": count,
                "gene_ratio": round(0.04 + (index % 10) * 0.025, 4),
                "ratio": round(0.06 + (index % 8) * 0.03, 4),
                "padj": round(min(p_value * 1.8, 0.25), 5),
                "p_value": p_value,
                "log2fc": log2fc,
                "baseMean": round(80 + index * 9.5, 3),
                "effect": round(0.55 + (index % 8) * 0.12, 3),
                "ci_low": round(0.35 + (index % 8) * 0.1, 3),
                "ci_high": round(0.78 + (index % 8) * 0.14, 3),
                "estimate": round(0.55 + (index % 8) * 0.12, 3),
                "lower": round(0.35 + (index % 8) * 0.1, 3),
                "upper": round(0.78 + (index % 8) * 0.14, 3),
                "actual": round(value + (index % 4) * 1.1, 3),
                "predicted": round(value + ((index % 5) - 2) * 1.4, 3),
                "dose": round(dose, 5),
                "response": response,
                "before": before,
                "after": after,
                "start": before,
                "end": after,
                "survival_time": 35 + index * 9,
                "event": "1" if index % 4 != 0 else "0",
                **set_memberships,
            }
        )
    return rows
