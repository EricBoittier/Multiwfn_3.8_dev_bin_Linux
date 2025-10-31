"""Utilities for culling grid points based on distance or value thresholds."""

from __future__ import annotations

from dataclasses import dataclass
import tempfile
from pathlib import Path
from typing import Dict, Iterable

import numpy as np

from ._multiwfn import compose_script, run_multiwfn


# Covalent radii in Angstrom (Cordero et al., 2008) with fallback for unknown elements.
_COVALENT_RADII: Dict[str, float] = {
    "H": 0.31,
    "He": 0.28,
    "Li": 1.28,
    "Be": 0.96,
    "B": 0.84,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "F": 0.57,
    "Ne": 0.58,
    "Na": 1.66,
    "Mg": 1.41,
    "Al": 1.21,
    "Si": 1.11,
    "P": 1.07,
    "S": 1.05,
    "Cl": 1.02,
    "Ar": 1.06,
    "K": 2.03,
    "Ca": 1.76,
    "Sc": 1.70,
    "Ti": 1.60,
    "V": 1.53,
    "Cr": 1.39,
    "Mn": 1.39,
    "Fe": 1.32,
    "Co": 1.26,
    "Ni": 1.24,
    "Cu": 1.32,
    "Zn": 1.22,
    "Ga": 1.22,
    "Ge": 1.20,
    "As": 1.19,
    "Se": 1.20,
    "Br": 1.20,
    "Kr": 1.16,
    "Rb": 2.20,
    "Sr": 1.95,
    "Y": 1.90,
    "Zr": 1.75,
    "Nb": 1.64,
    "Mo": 1.54,
    "Tc": 1.47,
    "Ru": 1.46,
    "Rh": 1.42,
    "Pd": 1.39,
    "Ag": 1.45,
    "Cd": 1.44,
    "In": 1.42,
    "Sn": 1.39,
    "Sb": 1.39,
    "Te": 1.38,
    "I": 1.39,
    "Xe": 1.40,
}


@dataclass(slots=True)
class AtomRecord:
    element: str
    coord: np.ndarray


class GridFilterError(RuntimeError):
    """Raised when grid filtering fails."""


def _export_structure_as_pdb(
    multiwfn_path: Path,
    wavefunction_path: Path,
    cwd: Path,
) -> Path:
    commands: Iterable[str] = [
        str(wavefunction_path),
        "100",  # Other functions (Part 1)
        "2",  # Export various files menu
        "1",  # Output structure as PDB
        "",  # Accept default filename
        "0",  # Return to export menu
        "0",  # Return to main menu
        "q",  # Exit
    ]
    script = compose_script(commands)
    run_multiwfn(multiwfn_path, script, cwd)

    pdb_path = cwd / f"{wavefunction_path.stem}.pdb"
    if not pdb_path.exists():
        raise GridFilterError(
            "Multiwfn did not emit the expected PDB when exporting geometry." "\n"
            "Ensure the wavefunction file contains geometry information."
        )
    return pdb_path


def _parse_pdb(path: Path) -> list[AtomRecord]:
    atoms: list[AtomRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            element = line[76:78].strip()
            if not element:
                element = line[12:16].strip()
            element = element.capitalize()
            try:
                x = float(line[30:38])
                y = float(line[38:46])
                z = float(line[46:54])
            except ValueError as exc:  # pragma: no cover - defensive
                raise GridFilterError(
                    f"Failed to parse coordinates from PDB line: {line.strip()}"
                ) from exc
            atoms.append(AtomRecord(element=element, coord=np.array([x, y, z], dtype=float)))

    if not atoms:
        raise GridFilterError("No atom records were parsed from the exported PDB file.")
    return atoms


def _lookup_radii(elements: Iterable[str], fallback: float) -> np.ndarray:
    radii: list[float] = []
    for symbol in elements:
        radii.append(_COVALENT_RADII.get(symbol, fallback))
    return np.asarray(radii, dtype=float)


class SamplingMethod(str):
    RANDOM = "random"
    FARTHEST = "farthest"


def _farthest_point_sampling(points: np.ndarray, target_count: int, seed: int | None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    selected = [rng.integers(0, len(points))]
    distances = np.full(len(points), np.inf)

    while len(selected) < target_count:
        last_selected = points[selected[-1]]
        dist = np.linalg.norm(points - last_selected, axis=1)
        distances = np.minimum(distances, dist)
        next_idx = np.argmax(distances)
        selected.append(int(next_idx))

    return np.array(selected, dtype=int)


def filter_grid_to_npz(
    *,
    multiwfn_path: Path,
    wavefunction_path: Path,
    grid_path: Path,
    output_path: Path | None,
    property_key: str,
    radius_scale: float,
    min_distance: float | None,
    max_value: float | None,
    max_abs_value: float | None,
    fallback_radius: float = 1.5,
    target_point_count: int | None = None,
    sampling_method: str = SamplingMethod.RANDOM,
    random_seed: int | None = None,
) -> Path:
    resolved_multiwfn = multiwfn_path.expanduser().resolve(strict=True)
    resolved_wavefunction = wavefunction_path.expanduser().resolve(strict=True)
    resolved_grid = grid_path.expanduser().resolve(strict=True)

    with np.load(resolved_grid, allow_pickle=False) as npz:
        grid_points = npz["grid_points_angstrom"]
        if property_key not in npz:
            raise GridFilterError(
                f"Property '{property_key}' not found in {resolved_grid.name}. "
                f"Available keys: {', '.join(sorted(npz.files))}"
            )
        property_values = npz[property_key]
        payload = {key: npz[key] for key in npz.files}

    point_count = grid_points.shape[0]
    if property_values.shape[0] != point_count:
        raise GridFilterError(
            "Property array length does not match number of grid points."
        )

    mask = np.ones(point_count, dtype=bool)

    with tempfile.TemporaryDirectory(prefix="multiwfn-grid-filter-") as tmp:
        tmp_path = Path(tmp)
        pdb_path = _export_structure_as_pdb(
            resolved_multiwfn, resolved_wavefunction, tmp_path
        )
        atom_records = _parse_pdb(pdb_path)

    atom_coords = np.vstack([atom.coord for atom in atom_records])
    radii = _lookup_radii((atom.element for atom in atom_records), fallback_radius)

    diff = grid_points[:, None, :] - atom_coords[None, :, :]
    dist_sq = np.sum(diff**2, axis=2)

    if min_distance is not None:
        cut_sq = float(min_distance) ** 2
        mask &= np.all(dist_sq >= cut_sq, axis=1)
    else:
        threshold_sq = (radii * radius_scale) ** 2
        mask &= np.all(dist_sq >= threshold_sq, axis=1)

    if max_value is not None:
        mask &= property_values <= max_value

    if max_abs_value is not None:
        mask &= np.abs(property_values) <= max_abs_value

    if not np.any(mask):
        raise GridFilterError("All grid points were filtered; adjust thresholds.")

    filtered_points = grid_points[mask]

    if target_point_count is not None and target_point_count < filtered_points.shape[0]:
        if sampling_method == SamplingMethod.RANDOM:
            rng = np.random.default_rng(random_seed)
            sampled_idx = rng.choice(filtered_points.shape[0], target_point_count, replace=False)
        elif sampling_method == SamplingMethod.FARTHEST:
            sampled_idx = _farthest_point_sampling(filtered_points, target_point_count, random_seed)
        else:
            raise GridFilterError(
                f"Unsupported sampling method '{sampling_method}'. Choose 'random' or 'farthest'."
            )
        sampled_mask = np.zeros_like(mask)
        filtered_indices = np.flatnonzero(mask)
        sampled_indices = filtered_indices[sampled_idx]
        sampled_mask[sampled_indices] = True
        mask = sampled_mask
        filtered_points = grid_points[mask]

    filtered_payload: Dict[str, np.ndarray] = {}
    for key, array in payload.items():
        if isinstance(array, np.ndarray) and array.shape[0] == point_count:
            filtered_payload[key] = array[mask]
        else:
            filtered_payload[key] = array

    filtered_payload["filtered_point_count"] = np.array(mask.sum(), dtype=int)
    filtered_payload["original_point_count"] = np.array(point_count, dtype=int)

    destination = (
        resolved_grid.with_name(f"{resolved_grid.stem}_filtered.npz")
        if output_path is None
        else output_path.expanduser().resolve()
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination, **filtered_payload)
    return destination


