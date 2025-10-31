"""Utilities for discovering and describing Multiwfn-related scripts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
from typing import Iterable, List, Optional


class ExecutorType(str, Enum):
    """Represents how a script should be executed."""

    MULTIWFN = "multiwfn"
    SHELL = "shell"
    BATCH = "batch"
    VMD = "vmd"
    TCL = "tcl"
    GNUPLOT = "gnuplot"
    DATA = "data"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class ScriptDefinition:
    """Describes a script or helper file that ships with Multiwfn examples."""

    identifier: str
    path: Path
    executor: ExecutorType
    category: str
    description: str = ""

    @property
    def stem(self) -> str:
        return self.path.stem


_ALNUM_TOKEN = re.compile(r"^[A-Za-z0-9+\-_.]+$")


def _detect_executor(path: Path) -> ExecutorType:
    suffix = path.suffix.lower()
    if suffix in {".sh", ".bash"}:
        return ExecutorType.SHELL
    if suffix == ".bat":
        return ExecutorType.BATCH
    if suffix == ".vmd":
        return ExecutorType.VMD
    if suffix == ".tcl":
        return ExecutorType.TCL
    if suffix == ".gnu":
        return ExecutorType.GNUPLOT
    if suffix == ".txt":
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ExecutorType.UNKNOWN
        tokens = [line.strip() for line in text.splitlines() if line.strip()]
        if not tokens:
            return ExecutorType.UNKNOWN
        simple_tokens = sum(1 for token in tokens if _ALNUM_TOKEN.match(token))
        ratio = simple_tokens / len(tokens)
        if ratio >= 0.7:
            return ExecutorType.MULTIWFN
        return ExecutorType.DATA
    return ExecutorType.UNKNOWN


def discover_scripts(script_dirs: Iterable[Path]) -> List[ScriptDefinition]:
    """Return a list of known scripts under the provided directories."""

    definitions: List[ScriptDefinition] = []
    for base in script_dirs:
        if not base.exists():
            continue
        base = base.resolve()
        for root, _, files in os.walk(base):
            root_path = Path(root)
            category = root_path.relative_to(base).as_posix() or "."
            for filename in sorted(files):
                path = root_path / filename
                executor = _detect_executor(path)
                relative_id = path.relative_to(base).as_posix()
                definitions.append(
                    ScriptDefinition(
                        identifier=f"{base.name}:{relative_id}",
                        path=path,
                        executor=executor,
                        category=category,
                    )
                )
    definitions.sort(key=lambda item: item.identifier.lower())
    return definitions


def find_script(
    scripts: Iterable[ScriptDefinition], query: str
) -> Optional[ScriptDefinition]:
    """Locate a script definition by identifier, relative path, or stem."""

    normalized = query.strip().lower()
    if not normalized:
        return None

    priority_order = {
        ExecutorType.MULTIWFN: 0,
        ExecutorType.SHELL: 1,
        ExecutorType.BATCH: 2,
        ExecutorType.VMD: 3,
        ExecutorType.TCL: 4,
        ExecutorType.GNUPLOT: 5,
        ExecutorType.DATA: 6,
        ExecutorType.UNKNOWN: 7,
    }

    exact_matches: List[ScriptDefinition] = []
    suffix_matches: List[ScriptDefinition] = []

    for script in scripts:
        identifier = script.identifier.lower()
        relative = identifier.split(":", 1)[-1]
        name = script.path.name.lower()
        stem = script.path.stem.lower()

        if normalized in {identifier, relative, name, stem}:
            exact_matches.append(script)
            continue

        if identifier.endswith(normalized) or relative.endswith(normalized) or name.endswith(normalized):
            suffix_matches.append(script)

    def _sort_key(item: ScriptDefinition) -> tuple[int, str]:
        return (priority_order.get(item.executor, 99), item.identifier)

    if exact_matches:
        exact_matches.sort(key=_sort_key)
        return exact_matches[0]

    if suffix_matches:
        suffix_matches.sort(key=_sort_key)
        if len(suffix_matches) == 1:
            return suffix_matches[0]

    return None

