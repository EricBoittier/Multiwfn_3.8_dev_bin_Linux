# Multiwfn CLI Helper

A Python-based command-line interface now ships with this workspace. It wraps
the example scripts provided with Multiwfn so that common workflows can be
discovered and executed without manually editing the numeric input files.

## Quick Start

```bash
python -m multiwfn_cli list
python -m multiwfn_cli show AIM --head 5
python -m multiwfn_cli run AIM --dry-run
python -m multiwfn_cli run AIM --wavefunction GC.wfn
python -m multiwfn_cli cp2npz examples/scripts/CPprop.txt
python -m multiwfn_cli charges2npz --wavefunction examples/benzene.wfn
python -m multiwfn_cli grid2npz --wavefunction examples/benzene.wfn --grid-mode 1
```

By default the CLI looks for scripts in `examples/scripts` and `examples/EDA`
relative to the current working directory. You can point it elsewhere with
`--scripts-dir`.

## Configuration

- `--multiwfn` overrides the path to the `Multiwfn` executable at runtime.
- A configuration file at `~/.config/multiwfn-cli/config.toml` is picked up
  automatically when present with keys `multiwfn_path` and `script_dirs`.
- Use `--dry-run` to review the commands and script content without launching
  Multiwfn.
- Use `cp2npz` to translate Multiwfn CP output (`CPprop.txt`) into a structured
  NumPy archive for downstream analysis.
- Use `charges2npz` to run a suite of population analyses (Hirshfeld, VDD,
  Becke, ADCH, CHELPG, MK, CM5, MBIS) and bundle the resulting atomic charges
  and MBIS multipoles into a single `.npz` file.
- Use `grid2npz` to evaluate grid-based properties (ESP, vdW potential). The
  resulting NPZ stores the grid point coordinates and property values in atomic
  units.

Support for shell, batch, VMD, and plotting scripts is planned; at the moment
the `run` command is limited to numerical Multiwfn scripts.


