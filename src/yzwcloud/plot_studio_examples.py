from __future__ import annotations

import csv
import hashlib
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from yzwcloud.config import DATA_DIR
from yzwcloud.plot_studio_presets import PLOT_PRESETS


PLOT_STUDIO_EXAMPLES_DIR = DATA_DIR / "plot_studio_examples"
DEFAULT_PLOT_STUDIO_EXAMPLE_ID = "scatter"

EXAMPLE_PLOT_IDS = {str(preset["id"]) for preset in PLOT_PRESETS}

SAMPLE_COLUMNS = [f"sample_{index:02d}" for index in range(1, 9)]

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
    "abundance",
    "score",
    "count",
    "gene_ratio",
    "ratio",
    "adjusted_p",
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
    "concentration",
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
    *SAMPLE_COLUMNS,
]

PLOT_COLUMN_PRIORITY = {
    "scatter": ["x", "y", "group", "gene", "size", "score"],
    "bubble": ["x", "y", "size", "group", "gene", "score"],
    "density_contour": ["x", "y", "group", "gene", "size"],
    "scatter_3d": ["x", "y", "z", "group", "gene", "size"],
    "boxplot": ["condition", "value", "group", "subject", "gene"],
    "grouped_dotplot": ["condition", "value", "group", "subject", "gene"],
    "raincloud": ["condition", "value", "group", "subject", "gene"],
    "violin": ["condition", "value", "group", "subject", "gene"],
    "ridgeline": ["value", "condition", "group", "subject", "gene"],
    "bar": ["condition", "value", "group", "subject", "gene"],
    "histogram": ["value", "condition", "group", "subject"],
    "density_curve": ["value", "condition", "group", "subject"],
    "ecdf": ["value", "condition", "group", "subject"],
    "line": ["time", "value", "group", "sample", "condition"],
    "calendar_heatmap": ["date", "value", "group", "sample"],
    "radar": ["group", *SAMPLE_COLUMNS, "condition", "gene"],
    "parallel_coordinates": ["group", *SAMPLE_COLUMNS, "condition", "gene"],
    "heatmap": ["gene", *SAMPLE_COLUMNS, "group", "condition", "value"],
    "surface_3d": ["gene", *SAMPLE_COLUMNS, "group", "condition", "value"],
    "correlation": [*SAMPLE_COLUMNS, "group", "condition", "gene"],
    "volcano": ["gene", "log2fc", "p_value", "adjusted_p", "padj", "baseMean", "group"],
    "waterfall": ["gene", "log2fc", "p_value", "adjusted_p", "group"],
    "lollipop": ["gene", "score", "log2fc", "p_value", "group"],
    "ma_plot": ["gene", "baseMean", "log2fc", "p_value", "adjusted_p"],
    "qq_plot": ["gene", "p_value", "group", "score"],
    "forest_plot": ["term", "effect", "ci_low", "ci_high", "p_value", "group"],
    "roc_curve": ["score", "label", "group", "subject"],
    "pr_curve": ["score", "label", "group", "subject"],
    "kaplan_meier": ["time", "event", "group", "subject", "survival_time"],
    "bland_altman": ["actual", "predicted", "group", "gene"],
    "dose_response": ["concentration", "response", "group", "dose", "gene"],
    "paired_dot": ["value", "condition", "subject", "group", "before", "after"],
    "dumbbell": ["gene", "before", "after", "group", "value"],
    "upset": ["gene", "set_a", "set_b", "set_c", "set_d", "group", "category"],
    "venn": ["gene", "set_a", "set_b", "set_c", "set_d", "group", "category"],
    "enrichment_dot": ["term", "gene_ratio", "count", "adjusted_p", "padj", "p_value", "category"],
    "enrichment_bar": ["term", "gene_ratio", "count", "adjusted_p", "padj", "p_value", "category"],
    "treemap": ["term", "category", "count", "adjusted_p", "padj", "parent"],
    "sunburst": ["term", "category", "count", "adjusted_p", "padj", "parent"],
    "wordcloud": ["term", "count", "adjusted_p", "padj", "category"],
    "sankey": ["source", "target", "value", "group", "category"],
    "composition_bar": ["sample", "category", "abundance", "group", "value"],
    "donut": ["category", "abundance", "group", "value"],
}

GENES = [
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
    "AKT1",
    "BRCA1",
    "CCND1",
    "MYC",
    "PTEN",
    "SMAD4",
    "TGFB1",
    "TNF",
]

TERMS = [
    "Glycolysis",
    "Oxidative phosphorylation",
    "Immune activation",
    "Interferon response",
    "Cell cycle checkpoint",
    "Apoptosis regulation",
    "Hypoxia response",
    "MAPK signaling",
    "ECM organization",
    "Lipid metabolism",
    "Protein folding",
    "DNA repair",
    "T cell activation",
    "Cytokine signaling",
    "Mitochondrial translation",
    "Autophagy",
    "Ribosome biogenesis",
    "Angiogenesis",
    "Wound healing",
    "Cell adhesion",
]


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
    rows = _example_rows(plot_id)
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


def _example_rows(plot_id: str) -> list[dict[str, Any]]:
    rng = _rng_for_plot(plot_id)
    generator = _generator_for_plot(plot_id)
    return generator(rng)


def _generator_for_plot(plot_id: str) -> Callable[[random.Random], list[dict[str, Any]]]:
    if plot_id in {"scatter", "bubble", "density_contour", "scatter_3d", "bland_altman"}:
        return _scatter_rows
    if plot_id in {"boxplot", "grouped_dotplot", "raincloud", "violin", "ridgeline", "bar", "histogram", "density_curve", "ecdf"}:
        return _distribution_rows
    if plot_id == "line":
        return _line_rows
    if plot_id == "calendar_heatmap":
        return _calendar_rows
    if plot_id in {"radar", "parallel_coordinates", "heatmap", "surface_3d", "correlation"}:
        return _matrix_rows
    if plot_id in {"volcano", "waterfall", "lollipop", "ma_plot", "qq_plot"}:
        return _omics_rows
    if plot_id == "forest_plot":
        return _forest_rows
    if plot_id in {"roc_curve", "pr_curve"}:
        return _classification_rows
    if plot_id == "kaplan_meier":
        return _survival_rows
    if plot_id == "dose_response":
        return _dose_response_rows
    if plot_id == "paired_dot":
        return _paired_rows
    if plot_id == "dumbbell":
        return _dumbbell_rows
    if plot_id in {"upset", "venn"}:
        return _set_rows
    if plot_id in {"enrichment_dot", "enrichment_bar", "treemap", "sunburst", "wordcloud"}:
        return _enrichment_rows
    if plot_id in {"composition_bar", "donut"}:
        return _composition_rows
    if plot_id == "sankey":
        return _sankey_rows
    return _scatter_rows


def _rng_for_plot(plot_id: str) -> random.Random:
    digest = hashlib.sha256(f"yzw-plot-studio:{plot_id}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:12], 16))


def _r(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _bounded_p(value: float) -> float:
    return _r(min(max(value, 1e-6), 0.99), 6)


def _scatter_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    groups = [("Control", -0.8, 0.3), ("Treatment A", 0.25, 1.2), ("Treatment B", 1.05, -0.25)]
    for index in range(96):
        group, x_shift, y_shift = groups[index % len(groups)]
        latent = rng.gauss(0, 1)
        x = x_shift + latent + rng.gauss(0, 0.45)
        y = y_shift + 0.72 * latent + rng.gauss(0, 0.55)
        z = 0.55 * math.sin(latent * 1.6) + rng.gauss(0, 0.35) + (index % 5) * 0.08
        size = max(4.0, rng.lognormvariate(2.25, 0.32))
        actual = 36 + x * 5.0 + rng.gauss(0, 1.4)
        predicted = actual + rng.gauss(0.35, 2.0)
        rows.append(
            {
                "gene": GENES[index % len(GENES)],
                "sample": f"S{index % 12 + 1:02d}",
                "subject": f"P{index + 1:03d}",
                "group": group,
                "condition": group,
                "label": "responder" if y > 0.7 else "non-responder",
                "category": "Assay signal",
                "time": index % 16 + 1,
                "x": _r(x),
                "y": _r(y),
                "z": _r(z),
                "size": _r(size),
                "value": _r(y * 12 + 45),
                "score": _r(1 / (1 + math.exp(-1.2 * y))),
                "actual": _r(actual),
                "predicted": _r(predicted),
            }
        )
    return rows


def _distribution_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    groups = [("Control", 48, 5.8), ("Low dose", 53, 6.3), ("High dose", 61, 7.1), ("Recovery", 55, 5.2)]
    for group_index, (condition, mean, sd) in enumerate(groups):
        for replicate in range(26):
            value = rng.gauss(mean, sd) + 1.8 * math.sin(replicate / 3.5 + group_index)
            rows.append(
                {
                    "gene": GENES[(group_index * 7 + replicate) % len(GENES)],
                    "sample": f"{condition[:2].upper()}-{replicate + 1:02d}",
                    "subject": f"P{replicate + 1:02d}",
                    "group": condition,
                    "condition": condition,
                    "category": "Protein abundance",
                    "value": _r(value),
                    "score": _r((value - 40) / 30),
                    "count": max(1, int(round(value + rng.gauss(0, 3)))),
                }
            )
    return rows


def _line_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    groups = [("Control", 38, 0.7), ("Drug A", 42, 1.35), ("Drug B", 35, 1.05)]
    for group, baseline, slope in groups:
        for time in range(1, 13):
            for replicate in range(3):
                seasonal = 3.6 * math.sin(time / 2.4 + replicate * 0.35)
                value = baseline + slope * time + seasonal + rng.gauss(0, 1.6)
                rows.append(
                    {
                        "sample": f"{group.replace(' ', '')}-{replicate + 1}",
                        "subject": f"{group[:2]}-{replicate + 1:02d}",
                        "group": group,
                        "condition": group,
                        "time": time,
                        "date": str(date(2026, 1, 1) + timedelta(days=(time - 1) * 7)),
                        "value": _r(value),
                        "score": _r(value / 70),
                    }
                )
    return rows


def _calendar_rows(rng: random.Random) -> list[dict[str, Any]]:
    start_date = date(2026, 1, 1)
    rows = []
    for offset in range(180):
        day = start_date + timedelta(days=offset)
        weekly = 7.5 * math.sin(offset / 7 * 2 * math.pi)
        slow_trend = 0.035 * offset
        event_boost = 18 if offset in {38, 39, 40, 117, 118} else 0
        value = 52 + weekly + slow_trend + event_boost + rng.gauss(0, 4.5)
        rows.append(
            {
                "date": str(day),
                "time": offset + 1,
                "sample": f"D{offset + 1:03d}",
                "group": "Batch A" if offset < 90 else "Batch B",
                "value": _r(max(value, 0)),
                "count": max(0, int(round(value))),
            }
        )
    return rows


def _matrix_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    group_offsets = [-1.0, -0.8, -0.25, -0.1, 0.45, 0.65, 1.0, 1.15]
    for gene_index in range(36):
        module = gene_index % 4
        amplitude = rng.uniform(0.7, 1.8)
        row: dict[str, Any] = {
            "gene": GENES[gene_index % len(GENES)] if gene_index < len(GENES) else f"FEATURE_{gene_index + 1:03d}",
            "group": ["Metabolism", "Immune", "Growth", "Stress"][module],
            "condition": "Case" if module in {1, 3} else "Control",
            "category": ["Module A", "Module B", "Module C", "Module D"][module],
        }
        for sample_index, column in enumerate(SAMPLE_COLUMNS):
            block = group_offsets[sample_index]
            wave = math.sin(sample_index / 1.3 + module * 0.9)
            value = 10 + module * 1.8 + amplitude * (block + wave) + rng.gauss(0, 0.38)
            row[column] = _r(value)
        row["value"] = _r(sum(float(row[column]) for column in SAMPLE_COLUMNS) / len(SAMPLE_COLUMNS))
        row["score"] = _r(max(float(row[column]) for column in SAMPLE_COLUMNS) - min(float(row[column]) for column in SAMPLE_COLUMNS))
        rows.append(row)
    return rows


def _omics_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for index in range(180):
        signal = rng.gauss(0, 0.75)
        if index % 11 == 0:
            signal += rng.choice([-1, 1]) * rng.uniform(1.2, 2.8)
        base_mean = rng.lognormvariate(4.7, 0.72)
        p_value = _bounded_p(10 ** (-0.28 - abs(signal) * rng.uniform(0.55, 1.15)) + rng.uniform(0, 0.015))
        adjusted_p = _bounded_p(min(p_value * (1.8 + (index % 9) * 0.22), 0.95))
        rows.append(
            {
                "gene": GENES[index % len(GENES)] if index < len(GENES) else f"GENE_{index + 1:04d}",
                "group": "Up" if signal > 1 else "Down" if signal < -1 else "Stable",
                "category": "Differential feature",
                "log2fc": _r(signal),
                "p_value": p_value,
                "padj": adjusted_p,
                "adjusted_p": adjusted_p,
                "baseMean": _r(base_mean),
                "score": _r(signal * -math.log10(p_value)),
                "value": _r(signal),
                "count": max(1, int(round(base_mean / 10))),
            }
        )
    return rows


def _forest_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for index, term in enumerate(TERMS):
        effect = rng.gauss(0.18 if index % 3 else -0.12, 0.34)
        half_width = rng.uniform(0.12, 0.38)
        p_value = _bounded_p(10 ** (-0.45 - abs(effect) * 2.1) + rng.uniform(0, 0.02))
        rows.append(
            {
                "term": term,
                "group": ["Discovery", "Validation"][index % 2],
                "effect": _r(effect),
                "estimate": _r(effect),
                "ci_low": _r(effect - half_width),
                "ci_high": _r(effect + half_width),
                "lower": _r(effect - half_width),
                "upper": _r(effect + half_width),
                "p_value": p_value,
                "adjusted_p": _bounded_p(p_value * 1.6),
            }
        )
    return rows


def _classification_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for index in range(140):
        group = "Cohort A" if index < 70 else "Cohort B"
        positive = rng.random() < (0.42 if group == "Cohort A" else 0.55)
        score_center = 0.68 if positive else 0.28
        score = min(max(rng.gauss(score_center, 0.13), 0.01), 0.99)
        rows.append(
            {
                "subject": f"P{index + 1:03d}",
                "group": group,
                "label": "positive" if positive else "negative",
                "score": _r(score, 5),
                "value": _r(score),
            }
        )
    return rows


def _survival_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for index in range(96):
        group = "High risk" if index % 2 else "Low risk"
        scale = 115 if group == "High risk" else 190
        survival = max(12, int(rng.expovariate(1 / scale) + rng.gauss(28, 9)))
        censored = rng.random() < (0.22 if group == "High risk" else 0.34)
        rows.append(
            {
                "subject": f"P{index + 1:03d}",
                "group": group,
                "time": survival,
                "survival_time": survival,
                "event": "0" if censored else "1",
                "value": survival,
            }
        )
    return rows


def _dose_response_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    doses = [0.003, 0.01, 0.03, 0.1, 0.3, 1, 3, 10]
    configs = [("Compound A", 0.22, 88), ("Compound B", 0.75, 78)]
    for group, ic50, max_effect in configs:
        for dose in doses:
            for replicate in range(5):
                inhibition = max_effect * (dose / (dose + ic50))
                response = 100 - inhibition + rng.gauss(0, 3.2)
                rows.append(
                    {
                        "gene": f"{group}-{replicate + 1}",
                        "group": group,
                        "dose": dose,
                        "concentration": dose,
                        "response": _r(response),
                        "value": _r(response),
                    }
                )
    return rows


def _paired_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for index in range(42):
        group = "Responder" if index % 3 else "Partial"
        before = rng.gauss(54, 6.5)
        delta = rng.gauss(8.5 if group == "Responder" else 3.2, 3.0)
        after = before + delta
        subject = f"P{index + 1:03d}"
        rows.append({"subject": subject, "group": group, "condition": "Before", "value": _r(before), "before": _r(before), "after": _r(after)})
        rows.append({"subject": subject, "group": group, "condition": "After", "value": _r(after), "before": _r(before), "after": _r(after)})
    return rows


def _dumbbell_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for index in range(44):
        before = rng.gauss(42, 7)
        after = before + rng.gauss(5.5 if index % 4 else -2.0, 4.2)
        rows.append(
            {
                "gene": GENES[index % len(GENES)] if index < len(GENES) else f"FEATURE_{index + 1:03d}",
                "group": ["Set 1", "Set 2", "Set 3"][index % 3],
                "before": _r(before),
                "after": _r(after),
                "start": _r(before),
                "end": _r(after),
                "value": _r(after - before),
            }
        )
    return rows


def _set_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    for index in range(90):
        memberships = {
            "set_a": "1" if rng.random() < 0.52 else "",
            "set_b": "1" if rng.random() < 0.44 else "",
            "set_c": "1" if rng.random() < 0.36 else "",
            "set_d": "1" if rng.random() < 0.28 else "",
        }
        if not any(memberships.values()):
            memberships[rng.choice(list(memberships))] = "1"
        rows.append(
            {
                "gene": GENES[index % len(GENES)] if index < len(GENES) else f"ITEM_{index + 1:03d}",
                "group": ["RNA", "Protein", "Metabolite"][index % 3],
                "category": ["Screen hit", "Validated", "Candidate"][index % 3],
                "value": _r(rng.lognormvariate(2.8, 0.55)),
                **memberships,
            }
        )
    return rows


def _enrichment_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    categories = ["Metabolism", "Immunity", "Cell growth", "Stress response"]
    for index, term in enumerate(TERMS + [f"Pathway module {i}" for i in range(1, 21)]):
        count = max(4, int(rng.gauss(28 - index * 0.22, 6)))
        gene_ratio = min(max(rng.betavariate(2.2, 7.5) + (0.18 if index < 5 else 0), 0.025), 0.72)
        p_value = _bounded_p(10 ** (-0.7 - gene_ratio * 5.8) + rng.uniform(0, 0.012))
        adjusted_p = _bounded_p(min(p_value * (1.2 + index * 0.04), 0.95))
        category = categories[index % len(categories)]
        rows.append(
            {
                "term": term,
                "parent": category,
                "category": category,
                "count": count,
                "gene_ratio": _r(gene_ratio),
                "ratio": _r(gene_ratio),
                "p_value": p_value,
                "padj": adjusted_p,
                "adjusted_p": adjusted_p,
                "score": _r(-math.log10(adjusted_p)),
                "value": count,
            }
        )
    return rows


def _composition_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    categories = ["Firmicutes", "Bacteroidetes", "Proteobacteria", "Actinobacteria", "Verrucomicrobia", "Fusobacteria", "Other flora"]
    for sample_index in range(10):
        sample = f"S{sample_index + 1:02d}"
        group = "Control" if sample_index < 5 else "Treatment"
        weights = [rng.lognormvariate(1.8 + (0.35 if group == "Treatment" and item in {1, 3} else 0), 0.45) for item in range(len(categories))]
        total = sum(weights) or 1
        for category, weight in zip(categories, weights):
            abundance = weight / total * 100
            rows.append(
                {
                    "sample": sample,
                    "group": group,
                    "condition": group,
                    "category": category,
                    "abundance": _r(abundance),
                    "value": _r(abundance),
                    "count": int(round(abundance * 12 + rng.uniform(0, 20))),
                }
            )
    return rows


def _sankey_rows(rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    sources = ["Raw matrix", "QC passed", "Normalized", "Differential", "Enrichment"]
    targets = {
        "Raw matrix": ["QC passed", "Filtered out"],
        "QC passed": ["Normalized", "Batch flagged"],
        "Normalized": ["Differential", "Clustering"],
        "Differential": ["Enrichment", "Candidate markers"],
        "Enrichment": ["Report figures", "Interpretation"],
    }
    for source in sources:
        for target in targets[source]:
            value = rng.lognormvariate(3.0 if "out" not in target.lower() else 2.2, 0.32)
            rows.append(
                {
                    "source": source,
                    "target": target,
                    "group": source,
                    "category": "Workflow flow",
                    "value": _r(value),
                    "count": int(round(value)),
                }
            )
    return rows
