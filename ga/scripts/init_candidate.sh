#!/bin/bash
# Initialize a candidate folder for genetic algorithm optimization
# Usage: ga/scripts/init_candidate.sh <ID>

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <candidate_id>"
    exit 1
fi

ID="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GA_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$GA_DIR")"
CANDIDATE_DIR="$GA_DIR/candidates/CAND_$ID"

mkdir -p "$CANDIDATE_DIR"

# Copy files from project root
cp "$PROJECT_ROOT/perf_takehome.py" "$CANDIDATE_DIR/"
cp "$PROJECT_ROOT/tests/submission_tests.py" "$CANDIDATE_DIR/"

# Fix imports in test file (need to go up 3 levels: CAND_XXX -> candidates -> ga -> project root)
sed -i "s|parentdir = os.path.dirname(currentdir)|parentdir = os.path.dirname(os.path.dirname(os.path.dirname(currentdir)))|" "$CANDIDATE_DIR/submission_tests.py"
sed -i "s|from frozen_problem import|from problem import|" "$CANDIDATE_DIR/submission_tests.py"
sed -i "s|from perf_takehome import|from ga.candidates.CAND_$ID.perf_takehome import|" "$CANDIDATE_DIR/submission_tests.py"

echo "Initialized candidate $ID"
