from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._multiwfn import compose_script, run_multiwfn


class ConversionError(RuntimeError):
    """Raised when Multiwfn fails to emit the expected converted file."""


@dataclass(slots=True)
class ConversionResult:
    """Holds the output path produced by a conversion helper."""

    output_path: Path


def convert_to_mwfn(
    *,
    multiwfn_path: Path,
    input_path: Path,
    output_path: Path | None,
    overwrite: bool = False,
) -> ConversionResult:
    """Convert the supplied wavefunction to the `.mwfn` format.

    Parameters
    ----------
    multiwfn_path
        Path to the Multiwfn executable.
    input_path
        Wavefunction to load (any Multiwfn-supported format).
    output_path
        Destination file. When omitted, the input stem with an `.mwfn`
        suffix is created alongside the source file.
    overwrite
        If False (default) and the destination already exists, raise
        :class:`FileExistsError`.
    """

    resolved_multiwfn = multiwfn_path.expanduser().resolve(strict=True)
    resolved_input = input_path.expanduser().resolve(strict=True)

    if output_path is None:
        destination = resolved_input.with_suffix(".mwfn")
    else:
        destination = output_path.expanduser().resolve()

    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"The destination '{destination}' already exists. Use --overwrite to replace it."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    commands = [
        str(resolved_input),
        "100",  # Other functions (Part 1)
        "2",  # Export various files menu
        "32",  # Export as .mwfn
        str(destination),
        "0",  # Return to export menu
        "0",  # Return to main menu
        "q",  # Exit
    ]

    script = compose_script(commands)
    process = run_multiwfn(resolved_multiwfn, script, destination.parent)

    if not destination.exists():
        raise ConversionError(
            "Multiwfn did not create the expected .mwfn file. "
            "Check the input file for completeness (basis set information) "
            "and review Multiwfn's console output for hints.\n"
            f"Multiwfn output (truncated):\n{process.stdout.strip()}"
        )

    return ConversionResult(output_path=destination)
