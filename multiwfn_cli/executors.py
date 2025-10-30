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
    note: Optional[str] = None


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

        run_cwd_candidate = (options.working_dir or script.path.parent).expanduser()
        run_cwd = run_cwd_candidate.resolve(strict=False)
        if not run_cwd.exists():
            raise ExecutorError(
                f"Working directory '{run_cwd}' does not exist."
            )

        script_text = script.path.read_text(encoding="utf-8")

        command = [str(self.executable)]

        resolved_wavefunction: Optional[Path] = None
        if options.wavefunction:
            resolved_wavefunction = self._resolve_wavefunction_path(
                options.wavefunction, run_cwd
            )
            if not resolved_wavefunction.exists():
                raise ExecutorError(
                    "Wavefunction file:\n"
                    f"  {resolved_wavefunction}\n"
                    "was not found. Provide a valid path via --wavefunction."
                )
            command.append(str(resolved_wavefunction))
        elif not options.dry_run:
            raise ExecutorError("A wavefunction file path is required to run Multiwfn.")

        command.extend(str(arg) for arg in options.extra_args)

        if options.dry_run:
            return RunResult(command=command, returncode=None, dry_run=True)

        process = subprocess.run(  # noqa: S603
            command,
            input=script_text,
            text=True,
            cwd=str(run_cwd),
            capture_output=False,
            check=False,
        )

        if process.returncode in {0, None}:
            return RunResult(command=command, returncode=process.returncode)

        if process.returncode == 24:
            return RunResult(
                command=command,
                returncode=0,
                note=(
                    "Multiwfn reported an end-of-file condition (exit code 24) "
                    "after consuming the scripted input. This is common when the "
                    "script finishes without sending the final quit command."
                ),
            )

        raise ExecutorError(
            f"Multiwfn exited with code {process.returncode}. "
            "Re-run with --dry-run to inspect the command."
        )

    @staticmethod
    def _resolve_wavefunction_path(raw_path: Path, run_cwd: Path) -> Path:
        expanded = raw_path.expanduser()
        candidates: List[Path] = []

        if expanded.is_absolute():
            candidates.append(expanded)
        else:
            candidates.append(Path.cwd() / expanded)
            if run_cwd != Path.cwd():
                candidates.append(run_cwd / expanded)

        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()

        # Fall back to the first candidate to provide a helpful absolute path.
        try:
            return candidates[0].resolve(strict=False)
        except FileNotFoundError:
            return candidates[0]

