from __future__ import annotations

import os
from pathlib import Path

import pytest

import yzwcloud.dev_server as dev_server
from yzwcloud.dev_server import (
    DEFAULT_PORT,
    LOG_DIR_NAME,
    cleanup_server_logs,
    cleanup_server_logs_detailed,
    default_log_dir,
    main,
    matching_server_logs,
    normalized_process_env,
    server_log_path,
    server_pid_path,
    restart_server,
    start_server,
    stop_server,
)


def _touch(path: Path, mtime: int) -> None:
    path.write_text("log", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_default_server_runtime_uses_8010_and_logs_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev_server, "project_root", lambda: tmp_path)

    assert DEFAULT_PORT == 8010
    assert DEFAULT_PORT != 5174
    assert LOG_DIR_NAME == "logs"
    assert default_log_dir() == tmp_path / "logs"
    assert server_pid_path(default_log_dir()).name == "server-8010.pid"
    assert server_log_path(default_log_dir()).parent == tmp_path / "logs"
    assert server_log_path(default_log_dir()).name.startswith("server-8010-")


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


def test_normalized_process_env_deduplicates_windows_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev_server.os, "name", "nt")

    normalized = normalized_process_env({"PATH": "upper", "Path": "title", "HOME": "x"})

    assert normalized["Path"] == "title"
    assert "PATH" not in normalized
    assert normalized["HOME"] == "x"


def test_start_server_spawns_uvicorn_and_records_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []
    port_checks = iter([False, True])

    class FakeProcess:
        pid = 12345

        def poll(self) -> None:
            return None

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        calls.append({"command": command, **kwargs})
        return FakeProcess()

    def fake_port_open(host: str, port: int, *, timeout: float = 0.35) -> bool:
        return next(port_checks)

    monkeypatch.setattr(dev_server, "is_port_open", fake_port_open)
    monkeypatch.setattr(dev_server.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(dev_server, "project_root", lambda: tmp_path)

    result = start_server(tmp_path, port=8123, wait_seconds=1, python_executable="python-test")

    assert result.pid == 12345
    assert result.already_running is False
    assert result.pid_path.read_text(encoding="utf-8") == "12345"
    assert result.log_path is not None
    assert result.log_path.name.startswith("server-8123-")
    assert calls[0]["command"] == [
        "python-test",
        "-m",
        "uvicorn",
        "yzwcloud.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8123",
    ]
    assert calls[0]["cwd"] == tmp_path


def test_stop_server_terminates_pid_and_removes_pid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "server-8123.pid"
    pid_path.write_text("12345", encoding="utf-8")
    port_checks = iter([True, False])
    terminated: list[int] = []

    def fake_port_open(host: str, port: int, *, timeout: float = 0.35) -> bool:
        return next(port_checks)

    monkeypatch.setattr(dev_server, "is_port_open", fake_port_open)
    monkeypatch.setattr(dev_server, "_terminate_pid", lambda pid: terminated.append(pid) or True)

    result = stop_server(tmp_path, port=8123, wait_seconds=1)

    assert result.stopped is True
    assert result.was_running is True
    assert result.pid == 12345
    assert terminated == [12345]
    assert not pid_path.exists()


def test_restart_server_cleans_legacy_logs_before_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "server-8123.pid"
    pid_path.write_text("12345", encoding="utf-8")
    current_log = tmp_path / "server-8123-old.log"
    legacy_log = tmp_path / "server-9000-old.log"
    _touch(current_log, 1)
    _touch(legacy_log, 2)
    port_checks = iter([True, False, False, True])

    class FakeProcess:
        pid = 777

        def poll(self) -> None:
            return None

    def fake_port_open(host: str, port: int, *, timeout: float = 0.35) -> bool:
        return next(port_checks)

    monkeypatch.setattr(dev_server, "is_port_open", fake_port_open)
    monkeypatch.setattr(dev_server, "_terminate_pid", lambda pid: True)
    monkeypatch.setattr(dev_server.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(dev_server, "project_root", lambda: tmp_path)

    result = restart_server(tmp_path, port=8123, wait_seconds=1)

    assert result.pid == 777
    assert result.already_running is False
    assert not current_log.exists()
    assert not legacy_log.exists()
    assert (tmp_path / "server-8123.pid").read_text(encoding="utf-8") == "777"


def test_restart_server_rejects_unknown_running_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev_server, "is_port_open", lambda *args, **kwargs: True)

    with pytest.raises(RuntimeError, match="no usable pid file"):
        restart_server(tmp_path, port=8123, wait_seconds=0)


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


def test_clean_logs_cli_can_clean_all_server_ports(tmp_path: Path) -> None:
    current_port = tmp_path / "server-8010-current.out.log"
    legacy_port = tmp_path / "server-9000-legacy.out.log"
    worker = tmp_path / "worker-9000.log"
    for index, path in enumerate([current_port, legacy_port, worker], start=1):
        _touch(path, index)

    exit_code = main(["clean-logs", "--log-dir", str(tmp_path), "--all-ports"])

    assert exit_code == 0
    assert not current_port.exists()
    assert not legacy_port.exists()
    assert worker.exists()
