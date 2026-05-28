from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_PORT = 8010
LOG_DIR_NAME = "logs"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_log_dir() -> Path:
    return project_root() / LOG_DIR_NAME


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
    resolved_dir = log_dir or default_log_dir()
    if keep_latest < 0:
        raise ValueError("keep_latest must be non-negative")
    candidates = matching_server_logs(resolved_dir, port=port)
    removable = candidates if keep_latest == 0 else candidates[:-keep_latest]
    removed: list[Path] = []
    for path in removable:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(path)
    return removed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YZW BioCloud local server helpers")
    subcommands = parser.add_subparsers(dest="command", required=True)
    cleanup = subcommands.add_parser("clean-logs", help="remove generated local server logs")
    cleanup.add_argument("--port", type=int, default=DEFAULT_PORT)
    cleanup.add_argument("--keep-latest", type=int, default=0)
    cleanup.add_argument("--log-dir", type=Path, default=default_log_dir())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "clean-logs":
        removed = cleanup_server_logs(args.log_dir, port=args.port, keep_latest=args.keep_latest)
        for path in removed:
            print(path)
        print(f"removed={len(removed)}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
