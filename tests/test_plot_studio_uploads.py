from __future__ import annotations

from fastapi.testclient import TestClient

from yzwcloud.main import app


def test_plot_studio_upload_accepts_raw_table_body() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/plot-studio/uploads?filename=example.csv",
        content=b"gene,value,group\nA,1,case\nB,2,control\n",
        headers={"content-type": "text/csv"},
    )

    assert response.status_code == 200
    source = response.json()["source"]
    assert source["sourceKind"] == "plot_studio_upload"
    assert source["name"] == "example.csv"
    assert source["type"] == "uploaded_table"
    assert source["dataPath"].endswith(".csv")
    assert source["meta"]["size"] > 0


def test_plot_studio_upload_rejects_unsupported_file_type() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/plot-studio/uploads?filename=example.pdf",
        content=b"%PDF",
        headers={"content-type": "application/pdf"},
    )

    assert response.status_code == 400
