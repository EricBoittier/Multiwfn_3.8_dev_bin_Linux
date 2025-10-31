"""Command-line interface entry point for Multiwfn helper scripts."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Iterable, List, Sequence

from .charges import SUPPORTED_METHODS, run_charges_to_npz
from .config import load_config
from .grids import SUPPORTED_GRID_PROPERTIES, run_grid_to_npz
from .cp_parser import aggregate_cp_records, parse_cp_file
from .executors import ExecutorError, MultiwfnExecutor, MultiwfnOptions
from .scripts import ExecutorType, ScriptDefinition, discover_scripts, find_script
from .convert import convert_to_mwfn
from .grid_filter import filter_grid_to_npz


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

    cp_parser = subparsers.add_parser(
        "cp2npz", help="Convert a CPprop.txt-style file into a NumPy .npz archive."
    )
    cp_parser.add_argument("input", type=Path, help="Critical point output file to parse.")
    cp_parser.add_argument(
        "-o",
        "--output",
        dest="output",
        type=Path,
        help="Destination .npz file (defaults to replacing input suffix with .npz).",
    )
    cp_parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Use numpy.savez instead of numpy.savez_compressed.",
    )

    charges_parser = subparsers.add_parser(
        "charges2npz",
        help="Run common charge analyses and bundle the results into an NPZ archive.",
    )
    charges_parser.add_argument(
        "--wavefunction",
        required=True,
        type=Path,
        help="Path to the wavefunction file analysed by Multiwfn.",
    )
    charges_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination NPZ file (defaults to <wavefunction>_charges.npz).",
    )
    charges_parser.add_argument(
        "--methods",
        nargs="+",
        choices=SUPPORTED_METHODS,
        help=(
            "Subset of charge methods to include. Default: "
            + ", ".join(SUPPORTED_METHODS)
        ),
    )

    grids_parser = subparsers.add_parser(
        "grid2npz",
        help="Evaluate grid-based properties (ESP, vdW potential) and store them in an NPZ archive.",
    )
    grids_parser.add_argument(
        "--wavefunction",
        required=True,
        type=Path,
        help="Path to the wavefunction file analysed by Multiwfn.",
    )
    grids_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination NPZ file (defaults to <wavefunction>_grid.npz).",
    )
    grids_parser.add_argument(
        "--properties",
        nargs="+",
        choices=SUPPORTED_GRID_PROPERTIES,
        help=(
            "Grid properties to include. Default: "
            + ", ".join(SUPPORTED_GRID_PROPERTIES)
        ),
    )
    grids_parser.add_argument(
        "--grid-mode",
        choices=["1", "2", "3"],
        default="1",
        help=(
            "Grid density preset used by Multiwfn (1=low, 2=medium, 3=high). "
            "Default: 1."
        ),
    )

    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert wavefunction files to other supported formats (currently .mwfn).",
    )
    convert_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Wavefunction file to convert (any Multiwfn-supported input).",
    )
    convert_parser.add_argument(
        "--output",
        type=Path,
        help="Destination file (defaults to <input>.mwfn).",
    )
    convert_parser.add_argument(
        "--format",
        choices=["mwfn"],
        default="mwfn",
        help="Target format. Only 'mwfn' is currently supported.",
    )
    convert_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting an existing destination file.",
    )

    filter_parser = subparsers.add_parser(
        "gridfilter",
        help="Cull grid points from an NPZ based on atomic distances or value thresholds.",
    )
    filter_parser.add_argument(
        "--grid-npz",
        required=True,
        type=Path,
        help="Input NPZ created by grid2npz.",
    )
    filter_parser.add_argument(
        "--wavefunction",
        required=True,
        type=Path,
        help="Wavefunction file containing atomic coordinates (e.g. converted .mwfn).",
    )
    filter_parser.add_argument(
        "--output",
        type=Path,
        help="Destination NPZ (defaults to <grid>_filtered.npz).",
    )
    filter_parser.add_argument(
        "--property",
        default="esp_au",
        help="Grid property key to use when applying value thresholds (default: esp_au).",
    )
    filter_parser.add_argument(
        "--radius-scale",
        type=float,
        default=1.2,
        help="Scale factor applied to covalent radii when removing near-atomic points (default: 1.2).",
    )
    filter_parser.add_argument(
        "--min-distance",
        type=float,
        help="Absolute minimum distance (Angstrom) from any atom; overrides radius-based filtering when provided.",
    )
    filter_parser.add_argument(
        "--max-value",
        type=float,
        help="Drop grid points where the chosen property exceeds this value (a.u.).",
    )
    filter_parser.add_argument(
        "--max-abs-value",
        type=float,
        help="Drop grid points where the absolute property value exceeds this threshold (a.u.).",
    )
    filter_parser.add_argument(
        "--fallback-radius",
        type=float,
        default=1.5,
        help="Covalent radius (Angstrom) used for elements not in the reference table (default: 1.5).",
    )
    filter_parser.add_argument(
        "--target-count",
        type=int,
        help="Down-sample the filtered grid to approximately this many points.",
    )
    filter_parser.add_argument(
        "--sampling-method",
        choices=["random", "farthest"],
        default="random",
        help="Sampling method when reducing point count (default: random).",
    )
    filter_parser.add_argument(
        "--seed",
        type=int,
        help="Random seed used when sampling (for reproducibility).",
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


def _handle_cp_to_npz(input_path: Path, output_path: Path | None, compress: bool) -> int:
    try:
        np = importlib.import_module("numpy")
    except ModuleNotFoundError as exc:  # pragma: no cover - handled at runtime
        raise SystemExit(
            "numpy is required for the cp2npz command; install it via pip first."
        ) from exc

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    records = parse_cp_file(input_path)
    if not records:
        print("No critical points found in the provided file.")
        return 1

    payload = aggregate_cp_records(records)
    destination = output_path or input_path.with_suffix(".npz")
    destination.parent.mkdir(parents=True, exist_ok=True)

    saver = np.savez if not compress else np.savez_compressed
    saver(destination, **payload)
    print(
        f"Wrote {len(records)} critical points and {len(payload)} fields to {destination}."
    )
    return 0


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

    if args.command == "cp2npz":
        return _handle_cp_to_npz(
            input_path=args.input,
            output_path=args.output,
            compress=not args.no_compress,
        )

    if args.command == "charges2npz":
        methods = args.methods or SUPPORTED_METHODS
        destination = run_charges_to_npz(
            multiwfn_path=config.multiwfn_path,
            wavefunction_path=args.wavefunction,
            output_path=args.output,
            methods=methods,
        )
        print(
            "Wrote charge analyses ("
            + ", ".join(methods)
            + f") to {destination}."
        )
        return 0

    if args.command == "grid2npz":
        properties = args.properties or SUPPORTED_GRID_PROPERTIES
        destination = run_grid_to_npz(
            multiwfn_path=config.multiwfn_path,
            wavefunction_path=args.wavefunction,
            output_path=args.output,
            properties=properties,
            grid_mode=args.grid_mode,
        )
        print(
            "Wrote grid analyses ("
            + ", ".join(properties)
            + f") to {destination}."
        )
        return 0

    if args.command == "convert":
        if args.format != "mwfn":  # pragma: no cover - guarded by argparse choices
            parser.error("Unsupported target format. Choose mwfn.")
        result = convert_to_mwfn(
            multiwfn_path=config.multiwfn_path,
            input_path=args.input,
            output_path=args.output,
            overwrite=args.overwrite,
        )
        print(f"Converted {args.input} to {result.output_path}.")
        return 0

    if args.command == "gridfilter":
        destination = filter_grid_to_npz(
            multiwfn_path=config.multiwfn_path,
            wavefunction_path=args.wavefunction,
            grid_path=args.grid_npz,
            output_path=args.output,
            property_key=args.property,
            radius_scale=args.radius_scale,
            min_distance=args.min_distance,
            max_value=args.max_value,
            max_abs_value=args.max_abs_value,
            fallback_radius=args.fallback_radius,
            target_point_count=args.target_count,
            sampling_method=args.sampling_method,
            random_seed=args.seed,
        )
        print(f"Filtered grid written to {destination}.")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 1

