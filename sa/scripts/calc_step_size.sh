#!/usr/bin/env bash
# Calculate mutation step size (1-5) based on temperature
# Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>
#
# Maps temperature linearly to step size:
#   T = initial_temp → step_size = 5 (large, exploration)
#   T = final_temp   → step_size = 1 (tiny, exploitation)

set -euo pipefail

CURRENT_TEMP="${1:?Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>}"
INITIAL_TEMP="${2:?Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>}"
FINAL_TEMP="${3:?Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>}"

# Calculate step size proportionally using Python for accurate math
# Formula: step = 1 + 4 * (T - T_final) / (T_initial - T_final)
# This gives: T=T_initial → 5, T=T_final → 1
python3 -c "
import math

current = float('$CURRENT_TEMP')
initial = float('$INITIAL_TEMP')
final = float('$FINAL_TEMP')

# Handle edge case where initial == final
if initial <= final:
    step = 3  # default
else:
    # Linear interpolation: maps [final, initial] → [1, 5]
    ratio = (current - final) / (initial - final)
    step = 1 + 4 * ratio

# Clamp to [1, 5] and round
step = max(1, min(5, round(step)))
print(int(step))
"
