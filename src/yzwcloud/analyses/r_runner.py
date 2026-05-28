from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_rscript() -> Path:
    configured = os.getenv("YZWCLOUD_RSCRIPT")
    candidates = [Path(configured)] if configured else []
    resolved = shutil.which("Rscript")
    if resolved:
        candidates.append(Path(resolved))

    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates.extend(sorted(program_files.glob("R/R-*/bin/Rscript.exe"), reverse=True))
    candidates.extend(sorted(program_files.glob("R/R-*/bin/x64/Rscript.exe"), reverse=True))

    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise ValueError("Rscript is not available. Install R, or set YZWCLOUD_RSCRIPT to Rscript.exe.")


def run_r_script(
    script_path: Path,
    args: list[str],
    cwd: Path,
    log_path: Path,
    timeout: int = 600,
    failure_hint: str = "R script failed",
) -> subprocess.CompletedProcess[str]:
    if not script_path.exists():
        raise ValueError(f"R script not found: {script_path}")

    command = [str(find_rscript()), str(script_path), *args]
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    log_path.write_text(
        "\n".join(
            [
                "COMMAND:",
                " ".join(command),
                "",
                "STDOUT:",
                completed.stdout,
                "",
                "STDERR:",
                completed.stderr,
            ]
        ),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-8:]
        raise ValueError(f"{failure_hint}. Log: {log_path}. Error: {' | '.join(tail)}")
    return completed
