#!/usr/bin/env bash
# Calculate mutation step size category based on temperature
# Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>
#
# Maps temperature linearly to a 1-10 scale, then returns a textual category:
#   T = initial_temp → scale 10 → "extensive"
#   T = final_temp   → scale 1  → "minimal"
#
# Categories (higher = bolder changes allowed):
#   1-2: minimal     - single tweaks
#   3-4: small       - local changes
#   5-6: moderate    - focused optimizations
#   7-8: substantial - restructuring
#   9-10: extensive  - major approach changes

set -euo pipefail

CURRENT_TEMP="${1:?Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>}"
INITIAL_TEMP="${2:?Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>}"
FINAL_TEMP="${3:?Usage: calc_step_size.sh <current_temp> <initial_temp> <final_temp>}"

# Calculate scale (1-10) and map to textual category
python3 -c "
import math

current = float('$CURRENT_TEMP')
initial = float('$INITIAL_TEMP')
final = float('$FINAL_TEMP')

# Handle edge case where initial == final
if initial <= final:
    scale = 5  # default to middle
else:
    # Linear interpolation: maps [final, initial] → [1, 10]
    ratio = (current - final) / (initial - final)
    scale = 1 + 9 * ratio

# Clamp to [1, 10] and round
scale = max(1, min(10, round(scale)))

# Map scale to textual category
if scale <= 2:
    category = 'minimal'
elif scale <= 4:
    category = 'small'
elif scale <= 6:
    category = 'moderate'
elif scale <= 8:
    category = 'substantial'
else:
    category = 'extensive'

print(category)
"
