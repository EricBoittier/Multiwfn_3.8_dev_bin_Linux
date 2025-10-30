"""Configuration helpers for the Multiwfn CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "multiwfn-cli" / "config.toml"


@dataclass(slots=True)
class Config:
    multiwfn_path: Path
    script_dirs: List[Path]
    config_file: Optional[Path] = None

    def resolved_script_dirs(self) -> List[Path]:
        return [p.resolve() for p in self.script_dirs if p.exists()]


def _default_multiwfn_path() -> Path:
    local_candidate = Path.cwd() / "Multiwfn"
    if local_candidate.exists():
        return local_candidate.resolve()
    return Path("Multiwfn")


def _default_script_dirs() -> List[Path]:
    root = Path.cwd()
    return [
        root / "examples" / "scripts",
        root / "examples" / "EDA",
    ]


def _read_config_file(path: Path) -> dict:
    data: dict = {}
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return data
    try:
        data = tomllib.loads(content.decode("utf-8"))
    except Exception:
        return {}
    return data


def load_config(
    config_path: Path | None = None,
    *,
    multiwfn_path: Path | None = None,
    script_dirs: Iterable[Path] | None = None,
) -> Config:
    path = config_path or DEFAULT_CONFIG_PATH
    raw = _read_config_file(path)

    configured_multiwfn = raw.get("multiwfn_path") if isinstance(raw, dict) else None
    configured_dirs = raw.get("script_dirs") if isinstance(raw, dict) else None

    resolved_multiwfn = (
        Path(multiwfn_path)
        if multiwfn_path
        else Path(configured_multiwfn)
        if configured_multiwfn
        else _default_multiwfn_path()
    )

    if script_dirs is not None:
        dirs = [Path(p) for p in script_dirs]
    elif isinstance(configured_dirs, list):
        dirs = [Path(p) for p in configured_dirs]
    else:
        dirs = _default_script_dirs()

    return Config(
        multiwfn_path=resolved_multiwfn,
        script_dirs=dirs,
        config_file=path if path.exists() else None,
    )


def ensure_config_dir(path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Ensure the configuration directory exists."""

    path.parent.mkdir(parents=True, exist_ok=True)

