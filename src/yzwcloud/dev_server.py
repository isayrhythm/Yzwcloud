from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_PORT = 8010
LOG_DIR_NAME = "logs"


@dataclass(frozen=True)
class LogCleanupResult:
    removed: list[Path]
    skipped: list[Path]


@dataclass(frozen=True)
class ServerStartResult:
    pid: int | None
    log_path: Path | None
    pid_path: Path
    already_running: bool


@dataclass(frozen=True)
class ServerStopResult:
    pid: int | None
    pid_path: Path
    stopped: bool
    was_running: bool


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_log_dir() -> Path:
    return project_root() / LOG_DIR_NAME


def server_pid_path(log_dir: Path, *, port: int = DEFAULT_PORT) -> Path:
    return log_dir / f"server-{port}.pid"


def server_log_path(log_dir: Path, *, port: int = DEFAULT_PORT) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return log_dir / f"server-{port}-{timestamp}.log"


def matching_server_logs(log_dir: Path, *, port: int | None = DEFAULT_PORT) -> list[Path]:
    """Return generated server log files sorted from oldest to newest."""
    if not log_dir.exists():
        return []
    pattern = f"server-{port}*.log" if port else "server-*.log"
    return sorted(
        (path for path in log_dir.glob(pattern) if path.is_file() and path.name != ".gitkeep"),
        key=lambda path: (path.stat().st_mtime, path.name),
    )


def cleanup_server_logs(
    log_dir: Path | None = None,
    *,
    port: int | None = DEFAULT_PORT,
    keep_latest: int = 0,
) -> list[Path]:
    """Delete old generated server logs and return the paths that were removed."""
    return cleanup_server_logs_detailed(log_dir, port=port, keep_latest=keep_latest).removed


def cleanup_server_logs_detailed(
    log_dir: Path | None = None,
    *,
    port: int | None = DEFAULT_PORT,
    keep_latest: int = 0,
) -> LogCleanupResult:
    """Delete generated server logs and report locked files that could not be removed."""
    resolved_dir = log_dir or default_log_dir()
    if keep_latest < 0:
        raise ValueError("keep_latest must be non-negative")
    candidates = matching_server_logs(resolved_dir, port=port)
    removable = candidates if keep_latest == 0 else candidates[:-keep_latest]
    removed: list[Path] = []
    skipped: list[Path] = []
    for path in removable:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except PermissionError:
            skipped.append(path)
            continue
        removed.append(path)
    return LogCleanupResult(removed=removed, skipped=skipped)


def is_port_open(host: str, port: int, *, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def normalized_process_env(env: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(env or os.environ)
    if os.name != "nt":
        return source

    path_value = None
    normalized: dict[str, str] = {}
    for key, value in source.items():
        if key.lower() == "path":
            if key == "Path" or path_value is None:
                path_value = value
            continue
        normalized[key] = value
    if path_value is not None:
        normalized["Path"] = path_value
    return normalized


def start_server(
    log_dir: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    reload: bool = False,
    keep_latest: int = 3,
    wait_seconds: float = 8.0,
    python_executable: str | None = None,
) -> ServerStartResult:
    resolved_dir = log_dir or default_log_dir()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    pid_path = server_pid_path(resolved_dir, port=port)
    if is_port_open(host, port):
        return ServerStartResult(
            pid=_read_pid(pid_path),
            log_path=None,
            pid_path=pid_path,
            already_running=True,
        )

    cleanup_server_logs_detailed(resolved_dir, port=port, keep_latest=keep_latest)
    log_path = server_log_path(resolved_dir, port=port)
    command = [
        python_executable or sys.executable,
        "-m",
        "uvicorn",
        "yzwcloud.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        command.append("--reload")

    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    with log_path.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(
            command,
            cwd=project_root(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=normalized_process_env(),
            close_fds=os.name != "nt",
            creationflags=flags,
        )
    pid_path.write_text(str(process.pid), encoding="utf-8")

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if is_port_open(host, port):
            return ServerStartResult(
                pid=process.pid,
                log_path=log_path,
                pid_path=pid_path,
                already_running=False,
            )
        if process.poll() is not None:
            raise RuntimeError(f"server exited immediately; see {log_path}")
        time.sleep(0.2)

    if wait_seconds > 0:
        raise RuntimeError(f"server did not listen on {host}:{port} within {wait_seconds:g}s; see {log_path}")
    return ServerStartResult(
        pid=process.pid,
        log_path=log_path,
        pid_path=pid_path,
        already_running=False,
    )


def stop_server(
    log_dir: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    wait_seconds: float = 8.0,
) -> ServerStopResult:
    resolved_dir = log_dir or default_log_dir()
    pid_path = server_pid_path(resolved_dir, port=port)
    pid = _read_pid(pid_path)
    port_was_open = is_port_open(host, port)

    if pid is None:
        return ServerStopResult(
            pid=None,
            pid_path=pid_path,
            stopped=False,
            was_running=port_was_open,
        )

    if not port_was_open:
        pid_path.unlink(missing_ok=True)
        return ServerStopResult(pid=pid, pid_path=pid_path, stopped=False, was_running=False)

    if not _terminate_pid(pid):
        raise RuntimeError(f"could not stop pid={pid}; remove {pid_path} only after checking the process")

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not is_port_open(host, port):
            pid_path.unlink(missing_ok=True)
            return ServerStopResult(pid=pid, pid_path=pid_path, stopped=True, was_running=True)
        time.sleep(0.2)

    raise RuntimeError(f"server pid={pid} did not stop listening on {host}:{port} within {wait_seconds:g}s")


def restart_server(
    log_dir: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    reload: bool = False,
    clean_all_ports: bool = True,
    keep_latest: int = 0,
    wait_seconds: float = 8.0,
) -> ServerStartResult:
    resolved_dir = log_dir or default_log_dir()
    stop_result = stop_server(resolved_dir, host=host, port=port, wait_seconds=wait_seconds)
    if stop_result.was_running and not stop_result.stopped:
        raise RuntimeError(
            f"port {port} is running but no usable pid file was found at {stop_result.pid_path}; "
            "stop it manually before restart"
        )
    cleanup_server_logs_detailed(
        resolved_dir,
        port=None if clean_all_ports else port,
        keep_latest=keep_latest,
    )
    return start_server(
        resolved_dir,
        host=host,
        port=port,
        reload=reload,
        keep_latest=keep_latest,
        wait_seconds=wait_seconds,
    )


def _read_pid(pid_path: Path) -> int | None:
    try:
        text = pid_path.read_text(encoding="utf-8").strip()
        return int(text) if text else None
    except (FileNotFoundError, ValueError):
        return None


def _terminate_pid(pid: int) -> bool:
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YZW BioCloud local server helpers")
    subcommands = parser.add_subparsers(dest="command", required=True)
    start = subcommands.add_parser("start", help="start the local API server in the background")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=DEFAULT_PORT)
    start.add_argument("--reload", action="store_true")
    start.add_argument("--keep-latest", type=int, default=3)
    start.add_argument("--wait-seconds", type=float, default=8.0)
    start.add_argument("--log-dir", type=Path, default=default_log_dir())
    stop = subcommands.add_parser("stop", help="stop the local API server started by this helper")
    stop.add_argument("--host", default="127.0.0.1")
    stop.add_argument("--port", type=int, default=DEFAULT_PORT)
    stop.add_argument("--wait-seconds", type=float, default=8.0)
    stop.add_argument("--log-dir", type=Path, default=default_log_dir())
    restart = subcommands.add_parser("restart", help="restart the local API server and clean generated logs")
    restart.add_argument("--host", default="127.0.0.1")
    restart.add_argument("--port", type=int, default=DEFAULT_PORT)
    restart.add_argument("--reload", action="store_true")
    restart.add_argument("--keep-latest", type=int, default=0)
    restart.add_argument("--wait-seconds", type=float, default=8.0)
    restart.add_argument("--log-dir", type=Path, default=default_log_dir())
    restart.add_argument(
        "--current-port-only",
        action="store_true",
        help="clean only logs for the restarted port instead of every server-*.log file",
    )
    cleanup = subcommands.add_parser("clean-logs", help="remove generated local server logs")
    cleanup.add_argument("--port", type=int, default=DEFAULT_PORT)
    cleanup.add_argument(
        "--all-ports",
        action="store_true",
        help="clean every server-*.log file in the log directory instead of only the default service port",
    )
    cleanup.add_argument("--keep-latest", type=int, default=0)
    cleanup.add_argument("--log-dir", type=Path, default=default_log_dir())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "start":
        result = start_server(
            args.log_dir,
            host=args.host,
            port=args.port,
            reload=args.reload,
            keep_latest=args.keep_latest,
            wait_seconds=args.wait_seconds,
        )
        if result.already_running:
            print(f"already-running port={args.port} pid={result.pid or 'unknown'}")
        else:
            print(f"started port={args.port} pid={result.pid} log={result.log_path}")
        print(f"pid-file={result.pid_path}")
        return 0
    if args.command == "stop":
        result = stop_server(
            args.log_dir,
            host=args.host,
            port=args.port,
            wait_seconds=args.wait_seconds,
        )
        if result.stopped:
            print(f"stopped port={args.port} pid={result.pid}")
        elif result.was_running:
            print(f"not-stopped port={args.port} pid=unknown pid-file={result.pid_path}")
        else:
            print(f"not-running port={args.port} pid={result.pid or 'unknown'}")
        return 0
    if args.command == "restart":
        result = restart_server(
            args.log_dir,
            host=args.host,
            port=args.port,
            reload=args.reload,
            clean_all_ports=not args.current_port_only,
            keep_latest=args.keep_latest,
            wait_seconds=args.wait_seconds,
        )
        print(f"started port={args.port} pid={result.pid} log={result.log_path}")
        print(f"pid-file={result.pid_path}")
        return 0
    if args.command == "clean-logs":
        port = None if args.all_ports else args.port
        result = cleanup_server_logs_detailed(args.log_dir, port=port, keep_latest=args.keep_latest)
        for path in result.removed:
            print(path)
        for path in result.skipped:
            print(f"skipped=file-in-use: {path}")
        print(f"removed={len(result.removed)} skipped={len(result.skipped)}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
