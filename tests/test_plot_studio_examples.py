from __future__ import annotations

import csv

import pytest
from fastapi.testclient import TestClient

from yzwcloud.main import app
from yzwcloud.plot_studio_examples import DEFAULT_PLOT_STUDIO_EXAMPLE_ID, example_source_for_plot
from yzwcloud.plot_studio_presets import PLOT_PRESETS
from yzwcloud.plot_studio_specs import create_plot_studio_spec


def _default_params(preset: dict[str, object]) -> dict[str, object]:
    return dict(preset.get("default_params") or {})


@pytest.mark.parametrize("preset", PLOT_PRESETS, ids=lambda preset: str(preset["id"]))
def test_plot_studio_example_tables_render_every_plot_type(preset: dict[str, object]) -> None:
    plot_id = str(preset["id"])
    source = example_source_for_plot(plot_id)

    spec = create_plot_studio_spec(
        source,
        plot_type=plot_id,
        params=_default_params(preset),
    )

    assert source["sourceKind"] == "plot_studio_example"
    assert source["dataPath"].endswith(f"{plot_id}_example.csv")
    assert spec["plot_type"] == plot_id
    assert spec["data"], spec.get("warnings")
    assert spec["source"]["source_kind"] == "plot_studio_example"


def test_plot_studio_example_endpoint_returns_source() -> None:
    client = TestClient(app)

    response = client.get("/api/plot-studio/examples/scatter")

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["sourceKind"] == "plot_studio_example"
    assert source["nodeId"] == "example_scatter"
    assert source["type"] == "example_table"


def test_plot_studio_default_example_endpoint_returns_scatter_source() -> None:
    client = TestClient(app)

    response = client.get("/api/plot-studio/examples/default")

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["sourceKind"] == "plot_studio_example"
    assert source["meta"]["plot_id"] == DEFAULT_PLOT_STUDIO_EXAMPLE_ID
    assert source["nodeId"] == f"example_{DEFAULT_PLOT_STUDIO_EXAMPLE_ID}"


def test_plot_studio_example_endpoint_rejects_unknown_plot_type() -> None:
    client = TestClient(app)

    response = client.get("/api/plot-studio/examples/not_a_plot")

    assert response.status_code == 404


def test_upset_example_uses_membership_columns_not_metadata() -> None:
    source = example_source_for_plot("upset")

    spec = create_plot_studio_spec(source, plot_type="upset", params={})

    assert spec["plot_type"] == "upset"
    assert list(reversed(spec["layout"]["yaxis2"]["categoryarray"])) == ["set_a", "set_b", "set_c", "set_d"]
    assert all(str(label).startswith("I") for label in spec["data"][0]["x"])
    assert not any("sample" in str(item[0]) or "category" in str(item[0]) for item in spec["data"][0]["customdata"])


def test_scatter_example_uses_non_linear_targeted_values() -> None:
    source = example_source_for_plot("scatter")

    with open(source["dataPath"], encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))

    x_values = [float(row["x"]) for row in rows]
    y_values = [float(row["y"]) for row in rows]
    groups = {row["group"] for row in rows}
    assert len(rows) >= 90
    assert len(groups) >= 3
    assert x_values[:12] != list(range(1, 13))
    assert len({round(value, 1) for value in y_values}) > 20
    assert any(y_values[index + 1] < y_values[index] for index in range(len(y_values) - 1))


def test_distribution_example_has_grouped_normal_like_replicates() -> None:
    source = example_source_for_plot("boxplot")

    with open(source["dataPath"], encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))

    values_by_condition: dict[str, list[float]] = {}
    for row in rows:
        values_by_condition.setdefault(row["condition"], []).append(float(row["value"]))

    assert len(values_by_condition) == 4
    assert all(len(values) >= 20 for values in values_by_condition.values())
    assert all(max(values) - min(values) > 8 for values in values_by_condition.values())
    assert [round(float(row["value"])) for row in rows[:9]] != list(range(1, 10))
