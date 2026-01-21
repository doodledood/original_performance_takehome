#!/bin/bash
# Randomly decide if crossover should occur
# Usage: scripts/should_crossover.sh <probability>
# Returns: exit code 0 if yes, 1 if no

PROB="${1:-0.8}"
RAND=$(python3 -c "import random; print(1 if random.random() < $PROB else 0)")
exit $((1 - RAND))
