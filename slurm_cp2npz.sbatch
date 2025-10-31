#!/bin/bash
#SBATCH --job-name=multiwfn_cp
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --mem=2G
#SBATCH --output=multiwfn_cp_%A_%a.out
#SBATCH --error=multiwfn_cp_%A_%a.err

set -euo pipefail
shopt -s nullglob

CP_FILES=(~/carb/jobs/*CPprop.txt)
TOTAL=${#CP_FILES[@]}

if (( TOTAL == 0 )); then
    echo "No CPprop.txt files found under ~/carb/jobs/." >&2
    exit 0
fi

BATCH_SIZE=${SUBSET_COUNT:-$TOTAL}
START=${SLURM_ARRAY_TASK_ID:-0}
END=$((START + BATCH_SIZE))

source "${HOME}/miniforge3/etc/profile.d/conda.sh"
conda activate multiwfn-cli

export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"

NO_COMPRESS=${CP_NO_COMPRESS:-0}

for ((idx=START; idx<END && idx<TOTAL; idx++)); do
    INPUT=${CP_FILES[$idx]}
    BASENAME=${INPUT%CPprop.txt}
    OUTPUT="${BASENAME}CPprop.npz"

    CMD=(python -m multiwfn_cli cp2npz "$INPUT" --output "$OUTPUT")
    if [[ $NO_COMPRESS -eq 1 ]]; then
        CMD+=(--no-compress)
    fi
    "${CMD[@]}"

done

