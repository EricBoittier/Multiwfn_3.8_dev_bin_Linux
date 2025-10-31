"""Helpers for exporting grid-based properties (e.g. ESP) via Multiwfn."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np

from ._multiwfn import compose_script, run_multiwfn
from ._geometry import export_geometry


BOHR_TO_ANGSTROM = 0.529177210903

SUPPORTED_GRID_PROPERTIES: Tuple[str, ...] = (
    "esp",
    "vdw",
)

_PROPERTY_CODES: Dict[str, str] = {
    "esp": "12",  # Total electrostatic potential
    "vdw": "25",  # van der Waals potential (probe=C)
}


def _build_script(wavefunction: Path, property_code: str, grid_mode: str) -> str:
    lines = [
        str(wavefunction.resolve()),
        "5",  # Spatial grid analysis
        property_code,
        grid_mode,
        "3",  # Export grid data to output.txt
        "0",  # Return to main menu
        "q",  # Exit Multiwfn
    ]
    return compose_script(lines)


def _load_grid_file(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(path, dtype=float)
    if data.ndim != 2 or data.shape[1] != 4:
        raise ValueError(
            "Unexpected grid file format; expected four columns (x, y, z, value)."
        )
    coords = data[:, :3]
    values = data[:, 3]
    return coords, values


def _extract_metadata(stdout: str) -> Dict[str, np.ndarray]:
    def _match(pattern: str) -> Tuple[str, str, str]:
        match = re.search(pattern, stdout)
        if not match:
            raise ValueError(f"Failed to parse Multiwfn output with pattern: {pattern}")
        return match.group(1), match.group(2), match.group(3)

    origin = np.array(
        [float(x) for x in _match(r"Coordinate of origin in X,Y,Z is\s+([-0-9.E+]+)\s+([-0-9.E+]+)\s+([-0-9.E+]+)\s+Bohr")],
        dtype=float,
    )
    end = np.array(
        [float(x) for x in _match(r"Coordinate of end point in X,Y,Z is\s+([-0-9.E+]+)\s+([-0-9.E+]+)\s+([-0-9.E+]+)\s+Bohr")],
        dtype=float,
    )
    spacing = np.array(
        [float(x) for x in _match(r"Grid spacing in X,Y,Z is\s+([-0-9.E+]+)\s+([-0-9.E+]+)\s+([-0-9.E+]+)\s+Bohr")],
        dtype=float,
    )
    counts_match = re.search(
        r"Number of points in X,Y,Z is\s+(\d+)\s+(\d+)\s+(\d+)", stdout
    )
    if not counts_match:
        raise ValueError("Failed to parse grid point counts from Multiwfn output.")
    counts = np.array([int(counts_match.group(i)) for i in range(1, 4)], dtype=int)

    return {
        "origin_bohr": origin,
        "end_bohr": end,
        "spacing_bohr": spacing,
        "counts": counts,
    }


def _ensure_grid_consistency(expected: np.ndarray, candidate: np.ndarray, property_name: str) -> None:
    if expected.shape != candidate.shape or not np.allclose(expected, candidate):
        raise ValueError(
            "Grid mismatch detected when processing property "
            f"'{property_name}'. Ensure all properties use the same grid configuration."
        )


def run_grid_to_npz(
    *,
    multiwfn_path: Path,
    wavefunction_path: Path,
    output_path: Path | None,
    properties: Iterable[str],
    grid_mode: str,
) -> Path:
    resolved_wavefunction = wavefunction_path.expanduser().resolve(strict=True)
    if not resolved_wavefunction.is_file():
        raise FileNotFoundError(f"Wavefunction file not found: {resolved_wavefunction}")

    resolved_multiwfn = multiwfn_path.expanduser().resolve(strict=True)
    if not resolved_multiwfn.is_file():
        raise FileNotFoundError(f"Multiwfn executable not found: {resolved_multiwfn}")

    if grid_mode not in {"1", "2", "3"}:
        raise ValueError("Grid mode must be one of '1', '2', or '3'.")

    selected_properties = []
    for prop in properties:
        if prop not in SUPPORTED_GRID_PROPERTIES:
            raise ValueError(
                f"Unsupported property '{prop}'. Supported: {', '.join(SUPPORTED_GRID_PROPERTIES)}"
            )
        selected_properties.append(prop)

    if not selected_properties:
        raise ValueError("No grid properties specified.")

    if output_path is None:
        output_path = resolved_wavefunction.with_name(f"{resolved_wavefunction.stem}_grid.npz")
    output_path = output_path.expanduser().resolve()

    grid_points: np.ndarray | None = None
    metadata: Dict[str, np.ndarray] | None = None
    payload: Dict[str, np.ndarray] = {}

    with tempfile.TemporaryDirectory(prefix="multiwfn-grid-") as tmp:
        tmp_path = Path(tmp)

        for prop in selected_properties:
            property_code = _PROPERTY_CODES[prop]
            script = _build_script(resolved_wavefunction, property_code, grid_mode)
            process = run_multiwfn(resolved_multiwfn, script, tmp_path)

            info = _extract_metadata(process.stdout)
            file_path = tmp_path / "output.txt"
            if not file_path.exists():
                raise FileNotFoundError(
                    "Multiwfn did not produce the expected 'output.txt' grid file."
                )

            coords, values = _load_grid_file(file_path)
            file_path.unlink()

            if grid_points is None:
                grid_points = coords
                metadata = info
            else:
                _ensure_grid_consistency(grid_points, coords, prop)
                if metadata is not None:
                    for key in ("origin_bohr", "end_bohr", "spacing_bohr"):
                        if not np.allclose(metadata[key], info[key]):
                            raise ValueError(
                                "Grid metadata mismatch detected across properties; ensure "
                                "consistent grid settings."
                            )
                    if not np.array_equal(metadata["counts"], info["counts"]):
                        raise ValueError(
                            "Grid point counts mismatch detected across properties; ensure "
                            "consistent grid settings."
                        )

            payload[f"{prop}_au"] = values

    if grid_points is None or metadata is None:
        raise RuntimeError("Grid extraction failed; no data collected.")

    symbols, coords = export_geometry(
        multiwfn_path=resolved_multiwfn,
        wavefunction_path=resolved_wavefunction,
    )

    payload["grid_points_angstrom"] = grid_points
    payload["grid_shape"] = metadata["counts"].astype(int)
    payload["grid_origin_bohr"] = metadata["origin_bohr"]
    payload["grid_end_bohr"] = metadata["end_bohr"]
    payload["grid_spacing_bohr"] = metadata["spacing_bohr"]
    payload["grid_origin_angstrom"] = metadata["origin_bohr"] * BOHR_TO_ANGSTROM
    payload["grid_end_angstrom"] = metadata["end_bohr"] * BOHR_TO_ANGSTROM
    payload["grid_spacing_angstrom"] = metadata["spacing_bohr"] * BOHR_TO_ANGSTROM
    payload["atom_symbols"] = symbols
    payload["atom_coords_angstrom"] = coords

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path, **payload)
    return output_path


