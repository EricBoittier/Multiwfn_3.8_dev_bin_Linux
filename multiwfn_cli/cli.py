"""Command-line interface entry point for Multiwfn helper scripts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Sequence

from .config import load_config
from .executors import MultiwfnExecutor, MultiwfnOptions, ExecutorError
from .scripts import ExecutorType, ScriptDefinition, discover_scripts, find_script


def _iterable_or_none(values: Sequence[str] | None) -> Iterable[Path] | None:
    if values is None:
        return None
    return [Path(value) for value in values]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multiwfn-cli",
        description="Wrapper CLI around the example scripts shipped with Multiwfn.",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (defaults to ~/.config/multiwfn-cli/config.toml)",
    )
    parser.add_argument(
        "--multiwfn",
        type=Path,
        help="Path to the Multiwfn executable (overrides config).",
    )
    parser.add_argument(
        "--scripts-dir",
        action="append",
        dest="script_dirs",
        metavar="PATH",
        help="Additional directories that contain scripts to expose via the CLI.",
    )

    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List available scripts.")
    list_parser.add_argument(
        "--executor",
        choices=[executor.value for executor in ExecutorType],
        help="Filter scripts by executor type.",
    )

    show_parser = subparsers.add_parser("show", help="Print the contents of a script.")
    show_parser.add_argument("script", help="Script identifier or name.")
    show_parser.add_argument(
        "--head",
        type=int,
        help="Only show the first N lines.",
    )

    run_parser = subparsers.add_parser("run", help="Execute a Multiwfn script.")
    run_parser.add_argument("script", help="Script identifier or name.")
    run_parser.add_argument(
        "--wavefunction",
        type=Path,
        help="Path to the wavefunction file passed to Multiwfn.",
    )
    run_parser.add_argument(
        "--cwd",
        type=Path,
        help="Working directory for the execution (defaults to the script's directory).",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command that would run without invoking Multiwfn.",
    )
    run_parser.add_argument(
        "--extra-arg",
        action="append",
        dest="extra_args",
        default=[],
        help="Additional arguments passed through to Multiwfn.",
    )

    return parser


def _print_script_listing(scripts: List[ScriptDefinition]) -> None:
    if not scripts:
        print("No scripts found. Adjust --scripts-dir or check your configuration.")
        return

    header = f"{'IDENTIFIER':40}  {'EXECUTOR':12}  CATEGORY"
    print(header)
    print("-" * len(header))
    for script in scripts:
        identifier = script.identifier[:40]
        executor = script.executor.value
        category = script.category
        print(f"{identifier:40}  {executor:12}  {category}")


def _print_script(script: ScriptDefinition, head: int | None = None) -> None:
    text = script.path.read_text(encoding="utf-8", errors="replace")
    if head is not None and head > 0:
        lines = text.splitlines()
        text = "\n".join(lines[:head])
    print(text)


def _handle_run(
    script: ScriptDefinition,
    multiwfn_path: Path,
    wavefunction: Path | None,
    working_dir: Path | None,
    dry_run: bool,
    extra_args: Sequence[str],
) -> int:
    executor = MultiwfnExecutor(multiwfn_path)
    options = MultiwfnOptions(
        wavefunction=wavefunction,
        working_dir=working_dir,
        dry_run=dry_run,
        extra_args=extra_args,
    )
    result = executor.run(script, options)
    if result.dry_run:
        print("Command:", " ".join(result.command))
        print("Input script:")
        _print_script(script)
        return 0
    if result.note:
        print(result.note)
    print(f"Multiwfn completed with exit code {result.returncode}.")
    return result.returncode or 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    config = load_config(
        config_path=args.config,
        multiwfn_path=args.multiwfn,
        script_dirs=_iterable_or_none(args.script_dirs),
    )

    scripts = discover_scripts(config.script_dirs)

    if args.command == "list":
        if args.executor:
            filtered = [
                script for script in scripts if script.executor.value == args.executor
            ]
        else:
            filtered = scripts
        _print_script_listing(filtered)
        return 0

    if args.command == "show":
        script = find_script(scripts, args.script)
        if script is None:
            parser.error(f"Unknown script: {args.script}")
        _print_script(script, head=args.head)
        return 0

    if args.command == "run":
        script = find_script(scripts, args.script)
        if script is None:
            parser.error(f"Unknown script: {args.script}")
        if script.executor is not ExecutorType.MULTIWFN:
            parser.error(
                f"Script '{script.identifier}' uses executor '{script.executor.value}' "
                "which is not yet supported by the run command."
            )
        try:
            return _handle_run(
                script=script,
                multiwfn_path=config.multiwfn_path,
                wavefunction=args.wavefunction,
                working_dir=args.cwd,
                dry_run=args.dry_run,
                extra_args=args.extra_args,
            )
        except ExecutorError as exc:
            parser.error(str(exc))

    parser.error(f"Unknown command: {args.command}")
    return 1

