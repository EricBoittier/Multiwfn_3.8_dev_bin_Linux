#!/bin/bash
#SBATCH --job-name=multiwfn_chg
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --mem=4G
#SBATCH --output=multiwfn_chg_%A_%a.out
#SBATCH --error=multiwfn_chg_%A_%a.err

set -euo pipefail

# Discover target Molden files once when the job starts.
mapfile -t MOLDEN_FILES < <(ls -1 ~/carb/jobs/*.molden)

if [[ ${#MOLDEN_FILES[@]} -eq 0 ]]; then
    echo "No *.molden files found under ~/carb/jobs/." >&2
    exit 1
fi

if [[ -z "${SLURM_ARRAY_TASK_ID:-}" ]]; then
    echo "This script is intended to run as a Slurm array." >&2
    echo "Submit with: sbatch --array=0-$(( ${#MOLDEN_FILES[@]} - 1 )) slurm_convert_charges.sbatch" >&2
    exit 1
fi

INPUT=${MOLDEN_FILES[$SLURM_ARRAY_TASK_ID]}
BASENAME=${INPUT%.molden}

source "${HOME}/miniforge3/etc/profile.d/conda.sh"
conda activate multiwfn-cli

export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"

python -m multiwfn_cli convert \
    --input "$INPUT" \
    --output "${BASENAME}.mwfn" \
    --overwrite

python -m multiwfn_cli charges2npz \
    --wavefunction "${BASENAME}.mwfn" \
    --output "${BASENAME}_charges.npz"

