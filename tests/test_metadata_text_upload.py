from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import csv


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


def _metadata_rows_from_path(path: str) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


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


def test_sample_metadata_text_and_file_inputs_are_merged() -> None:
    client = TestClient(app)
    created = _request(client, "POST", "/api/tasks", json={"name": "metadata-merge-test"})
    task_id = created["task"]["task_id"]

    text_detail = _request(
        client,
        "POST",
        f"/api/tasks/{task_id}/inputs/sample_metadata/text",
        json={
            "filename": "sample_metadata.csv",
            "content": "sample,group,condition\nS1,groupA,case\nS2,groupA,case",
        },
    )
    text_path = Path(_upload_node(text_detail)["params"]["sample_metadata_path"])
    rows_after_text = _metadata_rows_from_path(str(text_path))
    assert [row["sample"] for row in rows_after_text] == ["S1", "S2"]

    _request(
        client,
        "POST",
        f"/api/tasks/{task_id}/inputs/sample_metadata",
        params={"filename": "uploaded_meta.csv"},
        headers={"Content-Type": "application/octet-stream"},
        content="sample,group,condition\nS2,groupB,control\nS3,groupB,control".encode("utf-8"),
    )
    merged_detail = _request(client, "GET", f"/api/tasks/{task_id}")
    merged_path = Path(_upload_node(merged_detail)["params"]["sample_metadata_path"])
    rows_merged = _metadata_rows_from_path(str(merged_path))
    assert {row["sample"]: row["group"] for row in rows_merged} == {"S1": "groupA", "S2": "groupB", "S3": "groupB"}


def test_batch_upload_classifies_metadata_and_data_files() -> None:
    client = TestClient(app)
    created = _request(client, "POST", "/api/tasks", json={"name": "batch-upload-test"})
    task_id = created["task"]["task_id"]
    metadata = "sample,group,condition\nS1,A,case\nS2,A,case\nS3,B,control\nS4,B,control"
    matrix = "\n".join(
        [
            "gene_short_name,gene_id,biotype,strand,locus,Length,S1,S2,S3,S4",
            "GENE_A,ENSGA,protein_coding,+,chr1:1-10,10,10,11,2,3",
        ]
    )

    response = client.post(
        f"/api/tasks/{task_id}/inputs",
        files=[
            ("files", ("sample_metadata.csv", metadata.encode("utf-8"), "text/csv")),
            ("files", ("expression_matrix.csv", matrix.encode("utf-8"), "text/csv")),
        ],
    )

    assert response.status_code < 400, response.text
    detail = response.json()
    upload_node = _upload_node(detail)
    assert upload_node["params"]["sample_metadata_path"].endswith("sample_metadata.csv")
    assert upload_node["params"]["source_path"].endswith("expression_matrix.csv")
    batch = upload_node["params"]["uploaded_inputs"]["upload_batch"]
    assert batch["selected_data_file"] == "expression_matrix.csv"
    assert batch["metadata_files"] == ["sample_metadata.csv"]


def test_batch_upload_prefers_metabolights_maf_over_isa_support_files() -> None:
    fixture_dir = ROOT / "testdata" / "tmp_metabolomics_small"
    client = TestClient(app)
    created = _request(client, "POST", "/api/tasks", json={"name": "metabolights-batch-upload-test"})
    task_id = created["task"]["task_id"]

    files = [
        ("files", ("a_MTBLS1_metabolite_profiling_NMR_spectroscopy.txt", (fixture_dir / "a_MTBLS1_metabolite_profiling_NMR_spectroscopy.txt").read_bytes(), "text/plain")),
        ("files", ("i_Investigation.txt", (fixture_dir / "i_Investigation.txt").read_bytes(), "text/plain")),
        ("files", ("m_MTBLS1_metabolite_profiling_NMR_spectroscopy_v2_maf.tsv", (fixture_dir / "m_MTBLS1_metabolite_profiling_NMR_spectroscopy_v2_maf.tsv").read_bytes(), "text/tab-separated-values")),
        ("files", ("s_MTBLS1.txt", (fixture_dir / "s_MTBLS1.txt").read_bytes(), "text/plain")),
    ]
    response = client.post(f"/api/tasks/{task_id}/inputs", files=files)

    assert response.status_code < 400, response.text
    upload_node = _upload_node(response.json())
    assert upload_node["params"]["source_path"].endswith("m_MTBLS1_metabolite_profiling_NMR_spectroscopy_v2_maf.tsv")
    assert upload_node["params"]["sample_metadata_path"].endswith("s_MTBLS1.txt")
    batch = upload_node["params"]["uploaded_inputs"]["upload_batch"]
    assert batch["selected_data_file"] == "m_MTBLS1_metabolite_profiling_NMR_spectroscopy_v2_maf.tsv"
    assert batch["data_files"] == ["m_MTBLS1_metabolite_profiling_NMR_spectroscopy_v2_maf.tsv"]
    assert batch["metadata_files"] == ["s_MTBLS1.txt"]
    assert {item["filename"] for item in batch["ignored_files"]} == {
        "a_MTBLS1_metabolite_profiling_NMR_spectroscopy.txt",
        "i_Investigation.txt",
    }
