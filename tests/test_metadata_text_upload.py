from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.main import app  # noqa: E402


def _request(client: TestClient, method: str, path: str, **kwargs: Any) -> Any:
    response = client.request(method, path, **kwargs)
    assert response.status_code < 400, f"{method} {path} failed: {response.status_code} {response.text}"
    if response.status_code == 204:
        return None
    return response.json()


def _upload_node(detail: dict[str, Any]) -> dict[str, Any]:
    return next(node for node in detail["graph"]["nodes"] if node["id"] == "upload_expression")


def test_sample_metadata_text_upload_preserves_path_when_matrix_arrives_later() -> None:
    client = TestClient(app)
    created = _request(client, "POST", "/api/tasks", json={"name": "metadata-text-test"})
    task_id = created["task"]["task_id"]

    metadata_detail = _request(
        client,
        "POST",
        f"/api/tasks/{task_id}/inputs/sample_metadata/text",
        json={
            "filename": "sample_metadata.csv",
            "content": "sample,group,condition\nS1,A,case\nS2,A,case\nS3,B,control\nS4,B,control",
        },
    )
    metadata_path = _upload_node(metadata_detail)["params"]["sample_metadata_path"]
    assert metadata_path.endswith("sample_metadata.csv")

    matrix = "\n".join(
        [
            "gene_short_name,gene_id,biotype,strand,locus,Length,S1,S2,S3,S4",
            "GENE_A,ENSGA,protein_coding,+,chr1:1-10,10,10,11,2,3",
        ]
    ).encode("utf-8")
    matrix_detail = _request(
        client,
        "POST",
        f"/api/tasks/{task_id}/inputs/expression_matrix",
        params={"filename": "matrix.csv"},
        content=matrix,
        headers={"Content-Type": "application/octet-stream"},
    )

    upload_node = _upload_node(matrix_detail)
    assert upload_node["params"]["sample_metadata_path"] == metadata_path
    assert upload_node["params"]["source_path"].endswith("matrix.csv")
