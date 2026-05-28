from __future__ import annotations

import os
from pathlib import Path

import pytest

from yzwcloud.dev_server import cleanup_server_logs, cleanup_server_logs_detailed, main, matching_server_logs


def _touch(path: Path, mtime: int) -> None:
    path.write_text("log", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_cleanup_server_logs_keeps_latest_matching_port(tmp_path: Path) -> None:
    old_out = tmp_path / "server-8010-20260527-120000.out.log"
    old_err = tmp_path / "server-8010-20260527-120000.err.log"
    latest = tmp_path / "server-8010-20260528-120000.out.log"
    unmatched_port = tmp_path / "server-9001-20260528-120000.out.log"
    other_port = tmp_path / "server-9000.out.log"
    gitkeep = tmp_path / ".gitkeep"
    for index, path in enumerate([old_out, old_err, latest, unmatched_port, other_port, gitkeep], start=1):
        _touch(path, index)

    removed = cleanup_server_logs(tmp_path, port=8010, keep_latest=1)

    assert removed == [old_out, old_err]
    assert latest.exists()
    assert unmatched_port.exists()
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


def test_cleanup_server_logs_skips_locked_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    locked = tmp_path / "server-8010-locked.err.log"
    removable = tmp_path / "server-8010-old.out.log"
    _touch(locked, 1)
    _touch(removable, 2)

    original_unlink = Path.unlink

    def fake_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == locked:
            raise PermissionError("file is in use")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    removed = cleanup_server_logs(tmp_path, port=8010)

    assert removed == [removable]
    assert locked.exists()
    assert not removable.exists()


def test_cleanup_server_logs_detailed_reports_locked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    locked = tmp_path / "server-8010-locked.err.log"
    removable = tmp_path / "server-8010-old.out.log"
    _touch(locked, 1)
    _touch(removable, 2)

    original_unlink = Path.unlink

    def fake_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == locked:
            raise PermissionError("file is in use")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    result = cleanup_server_logs_detailed(tmp_path, port=8010)

    assert result.removed == [removable]
    assert result.skipped == [locked]


def test_clean_logs_cli_prints_skipped_locked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    locked = tmp_path / "server-8010-locked.err.log"
    _touch(locked, 1)

    def fake_unlink(path: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError("file is in use")

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    exit_code = main(["clean-logs", "--log-dir", str(tmp_path), "--port", "8010"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "skipped=file-in-use:" in output
    assert "removed=0 skipped=1" in output
