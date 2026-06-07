from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from yzwcloud.models import DataObject


GENE_INFO_COLUMNS = 6


@dataclass
class SampleColumn:
    index: int
    name: str
    condition: str
    group: str


def load_sample_columns(matrix_path: Path, metadata_path: Path) -> list[SampleColumn]:
    with matrix_path.open(encoding="utf-8-sig", newline="") as matrix_file:
        header = next(csv.reader(matrix_file))
    with metadata_path.open(encoding="utf-8-sig", newline="") as metadata_file:
        metadata = list(csv.DictReader(metadata_file))

    header_indexes: dict[str, list[int]] = {}
    for index, name in enumerate(header[GENE_INFO_COLUMNS:], start=GENE_INFO_COLUMNS):
        header_indexes.setdefault(name, []).append(index)

    raw_columns = []
    for idx, meta in enumerate(metadata):
        fallback_index = GENE_INFO_COLUMNS + idx
        sample_name = meta["sample"]
        matched_indexes = header_indexes.get(sample_name) or []
        if matched_indexes:
            for matched_index in matched_indexes:
                raw_columns.append(
                    SampleColumn(
                        index=matched_index,
                        name=sample_name,
                        condition=meta["condition"],
                        group=meta.get("group", ""),
                    )
                )
        elif fallback_index < len(header):
            raw_columns.append(
                SampleColumn(
                    index=fallback_index,
                    name=sample_name,
                    condition=meta["condition"],
                    group=meta.get("group", ""),
                )
            )

    counts: dict[str, int] = {}
    for item in raw_columns:
        counts[item.name] = counts.get(item.name, 0) + 1
    if not any(count > 1 for count in counts.values()):
        return raw_columns

    # The demo CSV contains raw and normalized blocks with duplicate sample names.
    # Use the last occurrence for each sample, which corresponds to the normalized block.
    last_by_name = {item.name: item for item in raw_columns}
    return list(last_by_name.values())


def values_at(row: list[str], columns: list[SampleColumn]) -> list[float]:
    values = []
    for column in columns:
        if column.index >= len(row):
            continue
        try:
            values.append(float(row[column.index]))
        except ValueError:
            continue
    return values


def variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = fmean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def welch_p_value(a: list[float], b: list[float]) -> float:
    var_a = variance(a)
    var_b = variance(b)
    denom = math.sqrt(var_a / len(a) + var_b / len(b))
    if denom == 0:
        return 1.0
    t_stat = abs((fmean(a) - fmean(b)) / denom)
    return math.erfc(t_stat / math.sqrt(2))


def read_diff_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = []
        for row in csv.DictReader(file):
            gene = row.get("gene") or row.get("metabolite") or row.get("feature_name") or row.get("feature_id") or ""
            gene_id = row.get("gene_id") or row.get("feature_id") or gene
            p_value = _float_value(row.get("p_value"), row.get("pvalue"), row.get("p_adjust"), default=1.0)
            neg_log10_p = _float_value(row.get("neg_log10_p"), default=-math.log10(max(p_value, 1e-300)))
            rows.append(
                {
                    "gene": gene,
                    "gene_id": gene_id,
                    "log2fc": _float_value(row.get("log2fc"), row.get("log2_fc")),
                    "p_value": p_value,
                    "neg_log10_p": neg_log10_p,
                }
            )
        return rows


def _float_value(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if value in {None, ""}:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return default


def load_sample_series(matrix_path: Path, columns: list[SampleColumn]) -> list[list[float]]:
    series = [[] for _ in columns]
    with matrix_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        for row in reader:
            for index, column in enumerate(columns):
                if column.index >= len(row):
                    continue
                try:
                    series[index].append(float(row[column.index]))
                except ValueError:
                    continue
    return series


def quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return sorted_values[lower]
    weight = pos - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def pearson(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size < 2:
        return 0.0
    a = left[:size]
    b = right[:size]
    mean_a = fmean(a)
    mean_b = fmean(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=False))
    den_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    den_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


def safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def write_data_output(path: Path, output_type: str, meta: dict[str, Any]) -> DataObject:
    output = DataObject(type=output_type, data=str(path), meta=meta)
    path.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    return output


def write_json_detail(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
