from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.main import app  # noqa: E402


DATA_FILE = ROOT / "expression_matrix.csv"


def _request(client: TestClient, method: str, path: str, **kwargs: Any) -> Any:
    response = client.request(method, path, **kwargs)
    assert response.status_code < 400, f"{method} {path} failed: {response.status_code} {response.text}"
    if response.status_code == 204:
        return None
    return response.json()


def _node(detail: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in detail["graph"]["nodes"]:
        if node["id"] == node_id:
            return node
    raise AssertionError(f"Node not found: {node_id}")


def _wait_node(
    client: TestClient,
    task_id: str,
    node_id: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout if timeout is not None else None
    last_node: dict[str, Any] | None = None
    while deadline is None or time.monotonic() < deadline:
        detail = _request(client, "GET", f"/api/tasks/{task_id}")
        last_node = _node(detail, node_id)
        if last_node["status"] in {"completed", "failed"}:
            break
        time.sleep(0.5)
    assert last_node is not None, f"Node never appeared: {node_id}"
    assert last_node["status"] == "completed", f"{node_id} ended as {last_node['status']}: {last_node.get('error')}"
    assert last_node.get("output"), f"{node_id} completed without output"
    return last_node


def _create_analysis_node(client: TestClient, task_id: str, source_node_id: str, analysis_type: str) -> dict[str, Any]:
    return _request(
        client,
        "POST",
        f"/api/tasks/{task_id}/analysis-nodes",
        json={"source_node_id": source_node_id, "analysis_type": analysis_type},
    )


def _run_node(client: TestClient, task_id: str, node_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return _request(
        client,
        "POST",
        f"/api/tasks/{task_id}/nodes/{node_id}/run",
        json={"params": params or {}},
    )


def _assert_output_file(node: dict[str, Any], meta_key: str) -> None:
    path = Path(str(node["output"]["meta"][meta_key]))
    assert path.exists(), f"Missing output file for {node['id']}: {path}"
    assert path.stat().st_size > 0, f"Empty output file for {node['id']}: {path}"


def _choose_comparison(options: dict[str, Any]) -> tuple[str, str]:
    conditions = [str(item) for item in options["conditions"]]
    control = "normal" if "normal" in conditions else conditions[0]
    case = "cancer" if "cancer" in conditions and control != "cancer" else next(
        item for item in conditions if item != control
    )
    return case, control


def _first_gene_name() -> str:
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader)
        for row in reader:
            if row and (row[0] or row[1]):
                return row[0] or row[1]
    raise AssertionError("No gene name found in expression matrix")


def test_transcriptome_workflow() -> None:
    assert DATA_FILE.exists(), f"Missing transcriptome demo matrix: {DATA_FILE}"

    client = TestClient(app)
    created = _request(client, "POST", "/api/tasks", json={"name": "transcriptome-e2e-test"})
    task_id = created["task"]["task_id"]

    try:
        _request(
            client,
            "POST",
            f"/api/tasks/{task_id}/inputs/expression_matrix",
            params={"filename": DATA_FILE.name},
            content=DATA_FILE.read_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )

        _run_node(client, task_id, "upload_expression")
        upload_node = _wait_node(client, task_id, "upload_expression")
        assert upload_node["output"]["type"] == "expression_matrix"
        upload_meta = upload_node["output"]["meta"]
        assert upload_meta["sample_count"] > 0
        assert upload_meta["gene_count"] > 0
        assert "qc" in upload_meta["capabilities"]

        group_payload = _request(client, "GET", f"/api/tasks/{task_id}/sample-groups")
        assignments = {
            item["sample"]: item["condition"]
            for item in group_payload["samples"]
            if item.get("sample") and item.get("condition")
        }
        colors = {
            condition: color
            for condition, color in zip(
                sorted({item["condition"] for item in group_payload["samples"] if item.get("condition")}),
                ["#0f8a8f", "#c44f3a", "#315fd6", "#20804f"],
                strict=False,
            )
        }
        _request(
            client,
            "PUT",
            f"/api/tasks/{task_id}/sample-groups",
            json={"assignments": assignments, "condition_colors": colors},
        )
        upload_node = _node(_request(client, "GET", f"/api/tasks/{task_id}"), "upload_expression")
        for condition, color in colors.items():
            assert upload_node["output"]["meta"]["condition_colors"][condition].lower() == color.lower()

        _create_analysis_node(client, task_id, "upload_expression", "qc")
        _run_node(
            client,
            task_id,
            "qc__expression",
            {
                "qc_preset": "loose",
                "min_total_ratio": 0.15,
                "max_zero_ratio": 0.7,
                "min_detected_genes": 500,
                "max_distribution_mad": 5,
                "max_value_iqr_multiplier": 3,
            },
        )
        qc_node = _wait_node(client, task_id, "qc__expression")
        assert qc_node["output"]["type"] == "qc_report"
        _assert_output_file(qc_node, "html_file")
        _assert_output_file(qc_node, "preview_file")

        downstream_expectations = [
            ("pca", "pca__expression", "pca_plot", {}),
            ("sample_correlation", "correlation__expression", "sample_correlation_plot", {}),
            (
                "expression_heatmap",
                "expression_heatmap__expression",
                "expression_heatmap_plot",
                {"top_genes": 30, "selected_conditions": []},
            ),
            ("gene_expression", "gene_expression__expression", "gene_expression_plot", {"gene": _first_gene_name()}),
            (
                "wgcna",
                "wgcna__expression",
                "wgcna_result",
                {
                    "max_genes": 80,
                    "min_module_size": 4,
                    "soft_power": 6,
                    "merge_cut_height": 0.25,
                    "network_type": "signed",
                },
            ),
        ]
        for analysis_type, node_id, output_type, params in downstream_expectations:
            _create_analysis_node(client, task_id, "qc__expression", analysis_type)
            _run_node(client, task_id, node_id, params)
            result_node = _wait_node(client, task_id, node_id)
            assert result_node["output"]["type"] == output_type
            _assert_output_file(result_node, "html_file")
            _assert_output_file(result_node, "preview_file")
            if output_type == "wgcna_result":
                assert result_node["output"]["meta"]["module_count"] > 0
                _assert_output_file(result_node, "module_file")

        _create_analysis_node(client, task_id, "qc__expression", "diff_analysis")
        comparison_options = _request(client, "GET", f"/api/tasks/{task_id}/comparison-options")
        case_condition, control_condition = _choose_comparison(comparison_options)
        diff_payload = _request(
            client,
            "POST",
            f"/api/tasks/{task_id}/diff-analyses",
            json={
                "case_condition": case_condition,
                "control_condition": control_condition,
                "method": "r_transcriptomics",
                "p_value": 0.05,
                "log2fc": 1.0,
            },
        )
        diff_node_id = next(
            node["id"]
            for node in diff_payload["graph"]["nodes"]
            if node["id"].startswith("diff_analysis__")
        )
        diff_node = _wait_node(client, task_id, diff_node_id)
        assert diff_node["output"]["type"] == "diff_result"
        _assert_output_file(diff_node, "diff_result_file")

        for analysis_type, output_type in [
            ("volcano", "volcano_plot"),
            ("heatmap", "heatmap_plot"),
            ("diff_export", "diff_export"),
        ]:
            _create_analysis_node(client, task_id, diff_node_id, analysis_type)
            detail = _request(client, "GET", f"/api/tasks/{task_id}")
            created_node_id = next(
                node["id"]
                for node in detail["graph"]["nodes"]
                if node["depends_on"] == [diff_node_id] and node["output_type"] == output_type
            )
            _run_node(client, task_id, created_node_id)
            result_node = _wait_node(client, task_id, created_node_id)
            assert result_node["output"]["type"] == output_type
            _assert_output_file(result_node, "html_file")
            _assert_output_file(result_node, "preview_file")

    finally:
        print(f"Kept transcriptome test task: {task_id}")


if __name__ == "__main__":
    test_transcriptome_workflow()
    print("Transcriptome workflow test passed.")
