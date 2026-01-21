#!/bin/bash
# Initialize the starting solution for simulated annealing
# Usage: sa/scripts/init_solution.sh [initial_temp]
# Creates CAND_CURRENT from baseline and evaluates it
# Output: "Initialized with X cycles at temperature T"

set -e

INITIAL_TEMP="${1:-1000}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SA_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$SA_DIR")"

# Create candidates directory with __init__.py
mkdir -p "$SA_DIR/candidates"
touch "$SA_DIR/candidates/__init__.py"

# Initialize CURRENT candidate from baseline
"$PROJECT_ROOT/scripts/init_candidate.sh" sa "CURRENT"
touch "$SA_DIR/candidates/CAND_CURRENT/__init__.py"

# Evaluate the initial solution
CYCLES=$("$PROJECT_ROOT/scripts/eval_candidate.sh" sa "CURRENT")

if [ "$CYCLES" = "ERROR" ]; then
    echo "ERROR: Failed to evaluate initial solution"
    exit 1
fi

# Copy CURRENT to BEST
cp -r "$SA_DIR/candidates/CAND_CURRENT" "$SA_DIR/candidates/CAND_BEST"
# Update import path for BEST
sed -i "s|from sa.candidates.CAND_CURRENT.perf_takehome import|from sa.candidates.CAND_BEST.perf_takehome import|" "$SA_DIR/candidates/CAND_BEST/submission_tests.py"
touch "$SA_DIR/candidates/CAND_BEST/__init__.py"

# Initialize state file
cat > "$SA_DIR/candidates/state.txt" << EOF
TEMPERATURE=$INITIAL_TEMP
ITERATION=0
CURRENT_SCORE=$CYCLES
BEST_SCORE=$CYCLES
ACCEPTED_COUNT=0
REJECTED_COUNT=0
EOF

# Initialize history file
echo "# iteration temperature current_score best_score accepted" > "$SA_DIR/candidates/history.txt"
echo "0 $INITIAL_TEMP $CYCLES $CYCLES INIT" >> "$SA_DIR/candidates/history.txt"

# Update scores.txt for compatibility
echo "CURRENT $CYCLES" > "$SA_DIR/candidates/scores.txt"
echo "BEST $CYCLES" >> "$SA_DIR/candidates/scores.txt"

echo "Initialized with $CYCLES cycles at temperature $INITIAL_TEMP"
