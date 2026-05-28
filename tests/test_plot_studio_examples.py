from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from yzwcloud.main import app
from yzwcloud.plot_studio_examples import example_source_for_plot
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
