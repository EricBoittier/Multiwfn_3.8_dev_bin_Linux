"""Helpers for extracting atomic charge information via Multiwfn."""

from __future__ import annotations

from dataclasses import dataclass
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

from ._multiwfn import compose_script, run_multiwfn

SUPPORTED_METHODS: Tuple[str, ...] = (
    "hirshfeld",
    "vdd",
    "becke",
    "adch",
    "chelpg",
    "mk",
    "cm5",
    "mbis",
)


_METHOD_SCRIPTS: Dict[str, List[str]] = {
    "hirshfeld": ["7", "1", "1", "y", "0", "q"],
    "vdd": ["7", "2", "1", "y", "0", "q"],
    "becke": ["7", "10", "0", "y", "0", "q"],
    "adch": ["7", "11", "1", "y", "0", "q"],
    "chelpg": ["7", "12", "1", "y", "0", "0", "q"],
    "mk": ["7", "13", "1", "y", "0", "0", "q"],
    "cm5": ["7", "16", "1", "y", "0", "q"],
    "mbis": ["7", "20", "-3", "-4", "1", "n", "y", "y", "0", "0", "q"],
}


@dataclass
class MBISMultipoles:
    charges_raw: np.ndarray
    dipoles: np.ndarray
    quadrupole_cartesian: np.ndarray
    quadrupole_traceless: np.ndarray


def _build_script(method: str, wavefunction: Path) -> str:
    if method not in _METHOD_SCRIPTS:
        raise ValueError(f"Unsupported method '{method}'.")
    lines = [str(wavefunction.resolve())]
    lines.extend(_METHOD_SCRIPTS[method])
    return compose_script(lines)


def _parse_chg(path: Path) -> Tuple[List[str], np.ndarray, np.ndarray]:
    atoms: List[str] = []
    coords: List[Tuple[float, float, float]] = []
    charges: List[float] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            atoms.append(parts[0])
            x, y, z, q = map(float, parts[1:5])
            coords.append((x, y, z))
            charges.append(q)
    if not atoms:
        raise ValueError(f"Charge file '{path}' did not contain any data.")
    return atoms, np.asarray(coords, dtype=float), np.asarray(charges, dtype=float)


def _parse_mbis_multipoles(path: Path, atom_count: int) -> MBISMultipoles:
    charges_raw: List[float] = []
    dipoles: List[Tuple[float, float, float]] = []
    quad_cart: List[Tuple[float, float, float, float, float, float]] = []
    quad_traceless: List[Tuple[float, float, float, float, float, float]] = []

    section = None
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("Atomic charges"):
                section = "charges"
                continue
            if line.startswith("Atomic dipoles"):
                section = "dipoles"
                continue
            if line.startswith("Atomic quadrupoles, Cartesian"):
                section = "cartesian"
                continue
            if line.startswith("Atomic quadrupoles, Traceless"):
                section = "traceless"
                continue
            if line.startswith("Atomic to molecular condensed"):
                break
            if section == "charges":
                parts = line.split()
                if len(parts) >= 2:
                    charges_raw.append(float(parts[1]))
            elif section == "dipoles":
                parts = line.split()
                if len(parts) >= 4:
                    dipoles.append(tuple(map(float, parts[1:4])))
            elif section == "cartesian":
                parts = line.split()
                if len(parts) >= 7:
                    quad_cart.append(tuple(map(float, parts[1:7])))
            elif section == "traceless":
                parts = line.split()
                if len(parts) >= 7:
                    quad_traceless.append(tuple(map(float, parts[1:7])))

    if len(charges_raw) != atom_count:
        raise ValueError("Unexpected number of MBIS charges parsed from multipole file.")
    if len(dipoles) != atom_count:
        raise ValueError("Unexpected number of MBIS dipoles in multipole file.")
    if len(quad_cart) != atom_count:
        raise ValueError("Unexpected number of MBIS Cartesian quadrupoles in multipole file.")
    if len(quad_traceless) != atom_count:
        raise ValueError("Unexpected number of MBIS traceless quadrupoles in multipole file.")

    return MBISMultipoles(
        charges_raw=np.asarray(charges_raw, dtype=float),
        dipoles=np.asarray(dipoles, dtype=float),
        quadrupole_cartesian=np.asarray(quad_cart, dtype=float),
        quadrupole_traceless=np.asarray(quad_traceless, dtype=float),
    )


def run_charges_to_npz(
    *,
    multiwfn_path: Path,
    wavefunction_path: Path,
    output_path: Path | None,
    methods: Iterable[str],
) -> Path:
    resolved_wavefunction = wavefunction_path.expanduser().resolve(strict=True)
    if not resolved_wavefunction.is_file():
        raise FileNotFoundError(f"Wavefunction file not found: {resolved_wavefunction}")

    if output_path is None:
        output_path = resolved_wavefunction.with_name(f"{resolved_wavefunction.stem}_charges.npz")
    output_path = output_path.expanduser().resolve()

    selected_methods = []
    for method in methods:
        if method not in SUPPORTED_METHODS:
            raise ValueError(f"Unsupported method '{method}'. Supported: {', '.join(SUPPORTED_METHODS)}")
        selected_methods.append(method)

    if not selected_methods:
        raise ValueError("No charge analysis methods specified.")

    atoms: List[str] | None = None
    coordinates: np.ndarray | None = None
    charges: Dict[str, np.ndarray] = {}
    mbis_data: MBISMultipoles | None = None

    with tempfile.TemporaryDirectory(prefix="multiwfn-charges-") as tmp:
        tmp_path = Path(tmp)

        for method in selected_methods:
            script = _build_script(method, resolved_wavefunction)
            run_multiwfn(multiwfn_path, script, tmp_path)

            base_name = resolved_wavefunction.stem
            chg_source = tmp_path / f"{base_name}.chg"
            if not chg_source.exists():
                raise FileNotFoundError(
                    f"Multiwfn did not produce the expected charge file for method '{method}'."
                )
            chg_target = tmp_path / f"{method}.chg"
            chg_source.rename(chg_target)

            current_atoms, coords, method_charges = _parse_chg(chg_target)
            if atoms is None:
                atoms = current_atoms
                coordinates = coords
            else:
                if current_atoms != atoms:
                    raise ValueError(
                        "Atomic ordering mismatch encountered while parsing charge files."
                    )
            charges[method] = method_charges

            if method == "mbis":
                mpl_source = tmp_path / f"{base_name}.mbis_mpl"
                if not mpl_source.exists():
                    raise FileNotFoundError(
                        "MBIS multipole file was not generated."
                    )
                mpl_target = tmp_path / "mbis.mpl"
                mpl_source.rename(mpl_target)
                mbis_data = _parse_mbis_multipoles(mpl_target, len(atoms))

    if atoms is None or coordinates is None:
        raise RuntimeError("Charge extraction failed; no atomic data collected.")

    payload: Dict[str, np.ndarray] = {
        "atoms": np.asarray(atoms, dtype="U10"),
        "coordinates_angstrom": coordinates,
    }

    for method, values in charges.items():
        payload[f"charges_{method}"] = values

    if mbis_data is not None:
        payload["mbis_charges_raw"] = mbis_data.charges_raw
        payload["mbis_dipoles"] = mbis_data.dipoles
        payload["mbis_quadrupole_cartesian"] = mbis_data.quadrupole_cartesian
        payload["mbis_quadrupole_traceless"] = mbis_data.quadrupole_traceless

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path, **payload)
    return output_path


