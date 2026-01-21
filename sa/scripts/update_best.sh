#!/bin/bash
# Update best solution if current/neighbor is better
# Usage: sa/scripts/update_best.sh <new_score>
# Compares with current best and updates if better

if [ -z "$1" ]; then
    echo "Usage: $0 <new_score>"
    exit 1
fi

NEW_SCORE="$1"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SA_DIR="$(dirname "$SCRIPT_DIR")"
CURRENT_DIR="$SA_DIR/candidates/CAND_CURRENT"
BEST_DIR="$SA_DIR/candidates/CAND_BEST"
STATE_FILE="$SA_DIR/candidates/state.txt"

if [ ! -f "$STATE_FILE" ]; then
    echo "ERROR: state.txt not found"
    exit 1
fi

BEST_SCORE=$(grep "^BEST_SCORE=" "$STATE_FILE" | cut -d'=' -f2)

# Check if new score is better (lower)
if python3 -c "exit(0 if $NEW_SCORE < $BEST_SCORE else 1)"; then
    # New best found
    rm -rf "$BEST_DIR"
    cp -r "$CURRENT_DIR" "$BEST_DIR"

    # Update import path
    sed -i "s|from sa.candidates.CAND_CURRENT.perf_takehome import|from sa.candidates.CAND_BEST.perf_takehome import|" "$BEST_DIR/submission_tests.py"

    # Update state
    sed -i "s|^BEST_SCORE=.*|BEST_SCORE=$NEW_SCORE|" "$STATE_FILE"

    echo "NEW_BEST: $NEW_SCORE (was $BEST_SCORE)"
else
    echo "NO_CHANGE: $NEW_SCORE >= $BEST_SCORE"
fi
