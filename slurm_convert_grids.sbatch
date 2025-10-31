#!/bin/bash
#SBATCH --job-name=multiwfn_grid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=03:00:00
#SBATCH --mem=6G
#SBATCH --output=multiwfn_grid_%A_%a.out
#SBATCH --error=multiwfn_grid_%A_%a.err

set -euo pipefail
shopt -s nullglob

MOLDEN_FILES=(~/carb/jobs/*.molden)
TOTAL=${#MOLDEN_FILES[@]}

if (( TOTAL == 0 )); then
    echo "No *.molden files found under ~/carb/jobs/. Nothing to do." >&2
    exit 0
fi

BATCH_SIZE=${SUBSET_COUNT:-$TOTAL}
START=${SLURM_ARRAY_TASK_ID:-0}
END=$((START + BATCH_SIZE))

source "${HOME}/miniforge3/etc/profile.d/conda.sh"
conda activate multiwfn-cli

export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"

IFS=' ' read -r -a GRID_PROPS <<< "${GRID_PROPERTIES:-esp vdw}"
GRID_MODE=${GRID_MODE:-1}
OVERWRITE_CONVERT=${GRID_OVERWRITE_CONVERT:-0}
GRID_OUTPUT_SUFFIX=${GRID_OUTPUT_SUFFIX:-_grid.npz}
FILTER_ENABLED=${GRID_FILTER_ENABLE:-0}
FILTER_SUFFIX=${GRID_FILTER_OUTPUT_SUFFIX:-_grid_filtered.npz}

for ((idx=START; idx<END && idx<TOTAL; idx++)); do
    INPUT=${MOLDEN_FILES[$idx]}
    BASENAME=${INPUT%.molden}
    MWFN_PATH="${BASENAME}.mwfn"
    GRID_OUTPUT="${BASENAME}${GRID_OUTPUT_SUFFIX}"

    if [[ ! -f "$MWFN_PATH" || $OVERWRITE_CONVERT -eq 1 ]]; then
        python -m multiwfn_cli convert \
            --input "$INPUT" \
            --output "$MWFN_PATH" \
            --overwrite
    else
        echo "Skipping conversion for $INPUT (existing $MWFN_PATH)" >&2
    fi

    python -m multiwfn_cli grid2npz \
        --wavefunction "$MWFN_PATH" \
        --output "$GRID_OUTPUT" \
        --grid-mode "$GRID_MODE" \
        --properties "${GRID_PROPS[@]}"

    if [[ $FILTER_ENABLED -eq 1 ]]; then
        FILTER_ARGS=(
            --grid-npz "$GRID_OUTPUT"
            --wavefunction "$MWFN_PATH"
        )
        [[ -n ${GRID_FILTER_MAX_VALUE:-} ]] && FILTER_ARGS+=(--max-value "$GRID_FILTER_MAX_VALUE")
        [[ -n ${GRID_FILTER_MAX_ABS_VALUE:-} ]] && FILTER_ARGS+=(--max-abs-value "$GRID_FILTER_MAX_ABS_VALUE")
        [[ -n ${GRID_FILTER_MIN_DISTANCE:-} ]] && FILTER_ARGS+=(--min-distance "$GRID_FILTER_MIN_DISTANCE")
        [[ -n ${GRID_FILTER_RADIUS_SCALE:-} ]] && FILTER_ARGS+=(--radius-scale "$GRID_FILTER_RADIUS_SCALE")
        [[ -n ${GRID_FILTER_TARGET_COUNT:-} ]] && FILTER_ARGS+=(--target-count "$GRID_FILTER_TARGET_COUNT")
        [[ -n ${GRID_FILTER_SAMPLING:-} ]] && FILTER_ARGS+=(--sampling-method "$GRID_FILTER_SAMPLING")
        [[ -n ${GRID_FILTER_SEED:-} ]] && FILTER_ARGS+=(--seed "$GRID_FILTER_SEED")
        [[ -n ${GRID_FILTER_PROPERTY:-} ]] && FILTER_ARGS+=(--property "$GRID_FILTER_PROPERTY")

        python -m multiwfn_cli gridfilter "${FILTER_ARGS[@]}" --output "${BASENAME}${FILTER_SUFFIX}"
    fi
done

