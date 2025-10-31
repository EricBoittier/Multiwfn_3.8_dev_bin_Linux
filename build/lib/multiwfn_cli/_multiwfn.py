"""Internal helpers for driving the Multiwfn executable."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable


class MultiwfnExecutionError(RuntimeError):
    """Raised when Multiwfn reports a non-successful exit status."""


def compose_script(lines: Iterable[str]) -> str:
    """Join an iterable of command strings into a Multiwfn input script."""

    return "\n".join(lines) + "\n"


def run_multiwfn(executable: Path, script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke Multiwfn with the provided scripted input.

    The Multiwfn process is expected to terminate with exit code 0 or 24 (EOF
    after consuming the script). Any other return code raises
    :class:`MultiwfnExecutionError` and includes stdout/stderr for debugging.
    """

    process = subprocess.run(  # noqa: S603
        [str(executable)],
        input=script,
        text=True,
        cwd=str(cwd),
        capture_output=True,
        check=False,
    )

    if process.returncode not in {0, 24}:
        raise MultiwfnExecutionError(
            "Multiwfn execution failed with exit code "
            f"{process.returncode}.\nSTDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
        )

    return process


