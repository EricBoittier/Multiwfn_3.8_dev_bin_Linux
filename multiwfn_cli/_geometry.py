"""Shared helpers for obtaining molecular geometry from Multiwfn."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Dict, Iterable, Tuple

import numpy as np

from ._multiwfn import compose_script, run_multiwfn


@dataclass(slots=True)
class AtomRecord:
    element: str
    coord: np.ndarray


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


def export_geometry(
    *,
    multiwfn_path: Path,
    wavefunction_path: Path,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return atomic symbols and coordinates (Å) by exporting a PDB via Multiwfn."""

    with tempfile.TemporaryDirectory(prefix="multiwfn-geom-") as tmp:
        tmp_path = Path(tmp)
        script = compose_script(
            [
                str(wavefunction_path),
                "100",
                "2",
                "1",
                "",
                "0",
                "0",
                "q",
            ]
        )
        run_multiwfn(multiwfn_path, script, tmp_path)

        pdb_path = tmp_path / f"{wavefunction_path.stem}.pdb"
        if not pdb_path.exists():
            raise RuntimeError(
                "Multiwfn did not emit the expected PDB when exporting geometry."
            )

        records = _parse_pdb(pdb_path)
        symbols = np.asarray([record.element for record in records], dtype="U4")
        coords = np.vstack([record.coord for record in records])
        return symbols, coords


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
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
            atoms.append(AtomRecord(element=element, coord=np.array([x, y, z], dtype=float)))
    if not atoms:
        raise RuntimeError("No atom records parsed from exported PDB.")
    return atoms


def lookup_covalent_radii(elements: Iterable[str], fallback: float) -> np.ndarray:
    radii = []
    for symbol in elements:
        radii.append(_COVALENT_RADII.get(symbol, fallback))
    return np.asarray(radii, dtype=float)


