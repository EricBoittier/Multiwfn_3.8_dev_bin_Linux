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
python -m multiwfn_cli convert --input input.molden --output input.mwfn
python -m multiwfn_cli gridfilter --grid-npz examples/benzene_grid.npz --wavefunction examples/benzene.mwfn
python -m multiwfn_cli gridfilter --grid-npz examples/benzene_grid.npz --wavefunction examples/benzene.mwfn --max-value 5 --target-count 3000 --sampling-method farthest
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
- Use `convert` to let Multiwfn export a loaded wavefunction (e.g. `.molden`) as
  an `.mwfn` file that downstream tooling can read without additional prompts.
  The source format must contain basis function information; otherwise Multiwfn
  cannot produce an `.mwfn` export.
- Use `gridfilter` to remove grid points that are too close to nuclei or exceed
  a chosen ESP threshold (e.g. to eliminate large positive spikes near atoms).
  You can also down-sample to a fixed count (e.g. `--target-count 3000 --sampling-method farthest`).

## Slurm Batch Scripts

Three helper scripts under the repository root wrap the CLI commands for batch
processing on Slurm clusters. Each script honours the `SUBSET_COUNT` environment
variable so you can keep the array size manageable.

- `slurm_convert_charges.sbatch` – convert `~/carb/jobs/*.molden` to `.mwfn` and
  run `charges2npz`. Optional environment variables:
  - `SUBSET_COUNT`: number of files processed by each array task (default: all).
  - `GRID_OVERWRITE_CONVERT=1`: force regeneration of the `.mwfn` file.
- `slurm_convert_grids.sbatch` – similar loop that runs `grid2npz` (and, if
  `GRID_FILTER_ENABLE=1`, follows up with `gridfilter`). Additional options:
  - `GRID_MODE` (default `1`) and `GRID_PROPERTIES` (default `"esp vdw"`).
  - `GRID_FILTER_MAX_VALUE`, `GRID_FILTER_TARGET_COUNT`, `GRID_FILTER_SAMPLING`,
    etc. mirror the CLI flags; any variable left unset is skipped.
- `slurm_cp2npz.sbatch` – processes `~/carb/jobs/*CPprop.txt` with `cp2npz`.
  Set `CP_NO_COMPRESS=1` if you prefer uncompressed NPZ output.

Submit as a modest array, for example:

```bash
export SUBSET_COUNT=10
sbatch --array=0-9 slurm_convert_charges.sbatch
```

Adjust the array range so it covers the number of chunks you need
(`ceil(total_files / SUBSET_COUNT)` jobs). Each task picks up the appropriate
segment and skips gracefully when no matching files exist.

## Conda Environment

Multiwfn depends on the OpenMotif runtime library (`libXm.so.4`). The provided
`conda-environment.yml` file installs `openmotif` alongside Python and NumPy so
that scripted runs (including the CLI helpers) work on systems where the
library is not available globally.

Create and activate the environment with:

```bash
conda env create -f conda-environment.yml
conda activate multiwfn-cli
```

Support for shell, batch, VMD, and plotting scripts is planned; at the moment
the `run` command is limited to numerical Multiwfn scripts.


