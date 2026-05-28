from __future__ import annotations

import os
from pathlib import Path

import pytest

from yzwcloud.dev_server import cleanup_server_logs, matching_server_logs


def _touch(path: Path, mtime: int) -> None:
    path.write_text("log", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_cleanup_server_logs_keeps_latest_matching_port(tmp_path: Path) -> None:
    old_out = tmp_path / "server-8010-20260527-120000.out.log"
    old_err = tmp_path / "server-8010-20260527-120000.err.log"
    latest = tmp_path / "server-8010-20260528-120000.out.log"
    other_port = tmp_path / "server-9000.out.log"
    gitkeep = tmp_path / ".gitkeep"
    for index, path in enumerate([old_out, old_err, latest, other_port, gitkeep], start=1):
        _touch(path, index)

    removed = cleanup_server_logs(tmp_path, port=8010, keep_latest=1)

    assert removed == [old_out, old_err]
    assert latest.exists()
    assert other_port.exists()
    assert gitkeep.exists()


def test_matching_server_logs_can_target_all_ports(tmp_path: Path) -> None:
    first = tmp_path / "server-8010.out.log"
    second = tmp_path / "server-9000.err.log"
    ignored = tmp_path / "worker-8010.log"
    _touch(first, 1)
    _touch(second, 2)
    _touch(ignored, 3)

    assert matching_server_logs(tmp_path, port=None) == [first, second]


def test_cleanup_server_logs_rejects_negative_retention(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="keep_latest"):
        cleanup_server_logs(tmp_path, keep_latest=-1)
