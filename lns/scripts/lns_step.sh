#!/bin/bash
# LNS Step - Single iteration handler for Large Neighborhood Search
# Usage: ./lns/scripts/lns_step.sh [--agent-output="<output from previous agent>"]
#
# This script handles the LNS state machine:
# - kick phase: Select operator, output KICK_ARGS
# - refine phase: After kick completes, output REFINE_ARGS
# - post-refine: Accept result, check termination, go to kick
#
# Output format:
#   [STATUS] iter=N phase=P current=C best=B
#   KICK_ARGS: lns CURRENT NEIGHBOR <operator>
# Or:
#   REFINE_ARGS: lns NEIGHBOR NEIGHBOR
# Or:
#   DONE: <reason> (best=B)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LNS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$LNS_DIR")"

# Source config
if [ -f "$SCRIPT_DIR/lns_config.sh" ]; then
    source "$SCRIPT_DIR/lns_config.sh"
else
    MAX_ITERATIONS=100
fi

STATE_FILE="$LNS_DIR/candidates/state.txt"
OPERATORS_FILE="$LNS_DIR/operators.txt"

# Parse arguments
AGENT_OUTPUT=""
for arg in "$@"; do
    case $arg in
        --agent-output=*)
            AGENT_OUTPUT="${arg#*=}"
            ;;
    esac
done

# Helper: read state variable
get_state() {
    grep "^$1=" "$STATE_FILE" 2>/dev/null | cut -d'=' -f2
}

# Helper: update state variable (portable across macOS and Linux)
set_state() {
    if grep -q "^$1=" "$STATE_FILE" 2>/dev/null; then
        local tmp=$(mktemp)
        sed "s|^$1=.*|$1=$2|" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
    else
        echo "$1=$2" >> "$STATE_FILE"
    fi
}

# Helper: select operator - novel with min probability, else random from file
# NOVEL_PROB_PCT: minimum probability of selecting "novel" (default 20%)
NOVEL_PROB_PCT=${NOVEL_PROB_PCT:-20}

select_operator() {
    local roll=$((RANDOM % 100))
    if [ "$roll" -lt "$NOVEL_PROB_PCT" ]; then
        echo "novel"
    else
        shuf -n 1 "$OPERATORS_FILE"
    fi
}

# Helper: add operator with name-only dedup
add_operator_if_new() {
    local name="$1"
    local desc="$2"
    # Check if name already exists (grep for name at start of line before |)
    if grep -q "^${name} |" "$OPERATORS_FILE" 2>/dev/null; then
        echo "[OPERATOR] '$name' already exists, skipping"
        return 0
    fi
    echo "${name} | ${desc}" >> "$OPERATORS_FILE"
    echo "[OPERATOR] Added: ${name} | ${desc}"
}

# Helper: parse NOVEL output from agent
parse_novel_output() {
    local output="$1"
    # Extract "NOVEL: name | description" line
    local novel_line=$(echo "$output" | grep "^NOVEL:" | head -1)
    if [ -n "$novel_line" ]; then
        # Remove "NOVEL: " prefix
        local content="${novel_line#NOVEL: }"
        # Split by " | "
        local name=$(echo "$content" | cut -d'|' -f1 | xargs)
        local desc=$(echo "$content" | cut -d'|' -f2- | xargs)
        add_operator_if_new "$name" "$desc"
    fi
}

# ============================================================
# PHASE 1: Initialize if needed
# ============================================================
if [ ! -f "$STATE_FILE" ]; then
    echo "[INIT] No state found, initializing..."
    mkdir -p "$LNS_DIR/candidates"

    # Copy initial solution from project root
    if [ -f "$PROJECT_ROOT/perf_takehome.py" ]; then
        mkdir -p "$LNS_DIR/candidates/CAND_CURRENT"
        cp "$PROJECT_ROOT/perf_takehome.py" "$LNS_DIR/candidates/CAND_CURRENT/"
        cp "$PROJECT_ROOT/tests/submission_tests.py" "$LNS_DIR/candidates/CAND_CURRENT/"
        cp "$PROJECT_ROOT/tests/frozen_problem.py" "$LNS_DIR/candidates/CAND_CURRENT/"
        cp "$PROJECT_ROOT/problem.py" "$LNS_DIR/candidates/CAND_CURRENT/"
    fi

    # Evaluate initial solution
    INITIAL_SCORE=$("$PROJECT_ROOT/scripts/eval_candidate.sh" lns CURRENT 2>/dev/null || echo "ERROR")
    if [ "$INITIAL_SCORE" = "ERROR" ]; then
        INITIAL_SCORE=999999
    fi

    # Initialize state
    cat > "$STATE_FILE" << EOF
ITERATION=0
PHASE=kick
CURRENT_SCORE=$INITIAL_SCORE
BEST_SCORE=$INITIAL_SCORE
EOF

    # Copy to BEST
    mkdir -p "$LNS_DIR/candidates/CAND_BEST"
    cp "$LNS_DIR/candidates/CAND_CURRENT/"* "$LNS_DIR/candidates/CAND_BEST/"

    echo "[INIT] Initial score: $INITIAL_SCORE cycles"
fi

# ============================================================
# PHASE 2: Process previous agent output if provided
# ============================================================
PHASE=$(get_state PHASE)
ITERATION=$(get_state ITERATION)

if [ -n "$AGENT_OUTPUT" ]; then
    if [ "$PHASE" = "kick" ]; then
        # Kick just finished - check for NOVEL and transition to refine
        parse_novel_output "$AGENT_OUTPUT"
        set_state PHASE "refine"
        PHASE="refine"
        echo "[KICK] Complete, transitioning to refine"
    elif [ "$PHASE" = "refine" ]; then
        # Refine just finished - evaluate and accept
        NEIGHBOR_SCORE=$("$PROJECT_ROOT/scripts/eval_candidate.sh" lns NEIGHBOR 2>/dev/null || echo "ERROR")
        CURRENT_SCORE=$(get_state CURRENT_SCORE)
        BEST_SCORE=$(get_state BEST_SCORE)

        # Validate NEIGHBOR_SCORE is a valid integer
        if [ "$NEIGHBOR_SCORE" != "ERROR" ] && [[ "$NEIGHBOR_SCORE" =~ ^[0-9]+$ ]]; then
            # Accept neighbor as new current
            rm -rf "$LNS_DIR/candidates/CAND_CURRENT"
            mv "$LNS_DIR/candidates/CAND_NEIGHBOR" "$LNS_DIR/candidates/CAND_CURRENT"
            set_state CURRENT_SCORE "$NEIGHBOR_SCORE"
            echo "[ACCEPT] New current: $NEIGHBOR_SCORE cycles"

            # Update best if improved
            if [ "$NEIGHBOR_SCORE" -lt "$BEST_SCORE" ]; then
                rm -rf "$LNS_DIR/candidates/CAND_BEST"
                cp -r "$LNS_DIR/candidates/CAND_CURRENT" "$LNS_DIR/candidates/CAND_BEST"
                set_state BEST_SCORE "$NEIGHBOR_SCORE"
                echo "[BEST] New best: $NEIGHBOR_SCORE cycles"
            fi
        else
            # Evaluation failed - discard neighbor
            rm -rf "$LNS_DIR/candidates/CAND_NEIGHBOR"
            echo "[REJECT] Evaluation failed, keeping current"
        fi

        # Increment iteration and go back to kick
        NEW_ITERATION=$((ITERATION + 1))
        set_state ITERATION "$NEW_ITERATION"
        set_state PHASE "kick"
        PHASE="kick"
        ITERATION="$NEW_ITERATION"
    fi
fi

# ============================================================
# PHASE 3: Check termination conditions
# ============================================================
ITERATION=$(get_state ITERATION)
CURRENT_SCORE=$(get_state CURRENT_SCORE)
BEST_SCORE=$(get_state BEST_SCORE)
PHASE=$(get_state PHASE)

echo "[STATUS] iter=$ITERATION phase=$PHASE current=$CURRENT_SCORE best=$BEST_SCORE"

# Check if done
if [ "$ITERATION" -ge "$MAX_ITERATIONS" ]; then
    echo "DONE: Reached max iterations (best=$BEST_SCORE)"
    exit 0
fi

# ============================================================
# PHASE 4: Output next action
# ============================================================
if [ "$PHASE" = "kick" ]; then
    # Clean up any leftover neighbor
    rm -rf "$LNS_DIR/candidates/CAND_NEIGHBOR" 2>/dev/null || true

    # Select random operator
    OPERATOR=$(select_operator)
    echo "KICK_ARGS: lns CURRENT NEIGHBOR $OPERATOR"
elif [ "$PHASE" = "refine" ]; then
    echo "REFINE_ARGS: lns NEIGHBOR NEIGHBOR"
fi
