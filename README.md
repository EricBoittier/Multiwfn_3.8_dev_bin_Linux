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

Support for shell, batch, VMD, and plotting scripts is planned; at the moment
the `run` command is limited to numerical Multiwfn scripts.


