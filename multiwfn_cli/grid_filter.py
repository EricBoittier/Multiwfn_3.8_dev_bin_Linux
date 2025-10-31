"""Helpers for culling grid points based on distance or value thresholds."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np

from ._geometry import export_geometry, lookup_covalent_radii


class GridFilterError(RuntimeError):
    """Raised when grid filtering fails."""


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
        atom_symbols = payload.get("atom_symbols")
        atom_coords = payload.get("atom_coords_angstrom")

    point_count = grid_points.shape[0]
    if property_values.shape[0] != point_count:
        raise GridFilterError(
            "Property array length does not match number of grid points."
        )

    mask = np.ones(point_count, dtype=bool)

    if atom_symbols is None or atom_coords is None:
        symbols, coords = export_geometry(
            multiwfn_path=resolved_multiwfn, wavefunction_path=resolved_wavefunction
        )
        atom_symbols = symbols
        atom_coords = coords
    else:
        atom_symbols = np.asarray(atom_symbols, dtype=str)
        atom_coords = np.asarray(atom_coords, dtype=float)

    radii = lookup_covalent_radii(atom_symbols, fallback_radius)

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


