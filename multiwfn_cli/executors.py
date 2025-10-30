"""Execution helpers for Multiwfn and related tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import List, Optional, Sequence

from .scripts import ExecutorType, ScriptDefinition


class ExecutorError(RuntimeError):
    """Raised when an executor cannot complete its task."""


@dataclass(slots=True)
class RunResult:
    command: List[str]
    returncode: Optional[int]
    dry_run: bool = False


@dataclass(slots=True)
class MultiwfnOptions:
    wavefunction: Optional[Path] = None
    working_dir: Optional[Path] = None
    dry_run: bool = False
    extra_args: Sequence[str] = field(default_factory=list)


class MultiwfnExecutor:
    """Runs textual scripts by feeding them to the Multiwfn binary."""

    def __init__(self, executable: Path):
        self.executable = executable

    def run(self, script: ScriptDefinition, options: MultiwfnOptions) -> RunResult:
        if script.executor is not ExecutorType.MULTIWFN:
            raise ExecutorError(
                f"Script '{script.identifier}' is not configured for Multiwfn execution"
            )

        script_text = script.path.read_text(encoding="utf-8")

        command = [str(self.executable)]
        if options.wavefunction:
            command.append(str(options.wavefunction))

        command.extend(str(arg) for arg in options.extra_args)

        if options.dry_run:
            return RunResult(command=command, returncode=None, dry_run=True)

        if not options.wavefunction:
            raise ExecutorError("A wavefunction file path is required to run Multiwfn.")

        run_cwd = options.working_dir or script.path.parent

        process = subprocess.run(  # noqa: S603
            command,
            input=script_text,
            text=True,
            cwd=str(run_cwd),
            capture_output=False,
            check=False,
        )

        if process.returncode not in {0, None}:
            raise ExecutorError(
                f"Multiwfn exited with code {process.returncode}. "
                "Re-run with --dry-run to inspect the command."
            )

        return RunResult(command=command, returncode=process.returncode)

