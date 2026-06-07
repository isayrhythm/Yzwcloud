from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect all test data writes to a per-test temp directory."""
    test_data = tmp_path / "data"
    test_tasks = test_data / "tasks"
    test_tasks.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("YZWCLOUD_DATA_DIR", str(test_data))

    import yzwcloud.config as _cfg

    monkeypatch.setattr(_cfg, "DATA_DIR", test_data)
    monkeypatch.setattr(_cfg, "TASKS_DIR", test_tasks)

    import yzwcloud.task_store as _ts

    monkeypatch.setattr(_ts, "TASKS_DIR", test_tasks)
