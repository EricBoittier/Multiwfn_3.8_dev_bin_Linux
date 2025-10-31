shopt -s nullglob
FILES=(~/carb/jobs/*.molden)
COUNT=${#FILES[@]}

if (( COUNT == 0 )); then
    echo "No *.molden files under ~/carb/jobs; aborting."
    exit 1
fi

echo $COUNT

sbatch --array=0-$((COUNT-1)) slurm_convert_charges.sbatch
