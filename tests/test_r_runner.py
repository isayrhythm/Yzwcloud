from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yzwcloud.analyses import r_runner  # noqa: E402


def test_find_rscript_uses_configured_environment(monkeypatch: Any, tmp_path: Path) -> None:
    configured = tmp_path / "Rscript.exe"
    configured.write_text("", encoding="utf-8")

    monkeypatch.setenv("YZWCLOUD_RSCRIPT", str(configured))
    monkeypatch.setattr(r_runner.shutil, "which", lambda _: None)

    assert r_runner.find_rscript() == configured


def test_run_r_script_writes_log_and_raises_on_failure(monkeypatch: Any, tmp_path: Path) -> None:
    rscript = tmp_path / "Rscript.exe"
    script = tmp_path / "script.R"
    log_path = tmp_path / "r.log"
    rscript.write_text("", encoding="utf-8")
    script.write_text("stop('boom')", encoding="utf-8")

    monkeypatch.setattr(r_runner, "find_rscript", lambda: rscript)

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert command == [str(rscript), str(script), "arg1"]
        return subprocess.CompletedProcess(command, 1, stdout="first\nsecond", stderr="err1\nerr2")

    monkeypatch.setattr(r_runner.subprocess, "run", fake_run)

    try:
        r_runner.run_r_script(
            script_path=script,
            args=["arg1"],
            cwd=tmp_path,
            log_path=log_path,
            timeout=5,
            failure_hint="R failed",
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("run_r_script should raise on non-zero exit")

    assert "R failed" in message
    assert "err1 | err2" in message
    log_text = log_path.read_text(encoding="utf-8")
    assert "COMMAND:" in log_text
    assert "STDOUT:" in log_text
    assert "first\nsecond" in log_text
    assert "STDERR:" in log_text
    assert "err1\nerr2" in log_text
