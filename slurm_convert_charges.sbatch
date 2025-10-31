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

BATCH_SIZE=${SUBSET_COUNT:-0}

# Discover target Molden files once when the job starts.
mapfile -t MOLDEN_FILES < <(ls -1 ~/carb/jobs/*.molden 2>/dev/null)

if [[ ${#MOLDEN_FILES[@]} -eq 0 ]]; then
    echo "No *.molden files found under ~/carb/jobs/." >&2
    exit 0
fi

TOTAL=${#MOLDEN_FILES[@]}

if [[ ${BATCH_SIZE} -eq 0 ]]; then
    BATCH_SIZE=${TOTAL}
fi

BATCH_START=${SLURM_ARRAY_TASK_ID:-0}
BATCH_END=$((BATCH_START + BATCH_SIZE))

for ((idx=BATCH_START; idx < BATCH_END && idx < TOTAL; idx++)); do
    INPUT=${MOLDEN_FILES[$idx]}
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

done

