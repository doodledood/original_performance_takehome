---
name: optimize_sa
description: Run simulated annealing optimization on the kernel
disable-model-invocation: true
---

# Simulated Annealing Optimization

Optimize `build_kernel()` using simulated annealing with the mutate agent.

## Workflow

The SA logic is handled by `sa_step.sh`. Your job is simple:

```
loop:
    result = Bash("./sa/scripts/sa_step.sh")
    if "DONE" in result:
        break
    args = extract MUTATE_ARGS from result
    Task(mutate, args)
```

### Step-by-Step

1. **Run sa_step.sh**
   ```bash
   ./sa/scripts/sa_step.sh
   ```

2. **Check output**:
   - If output contains `DONE:` → optimization complete, stop
   - If output contains `MUTATE_ARGS:` → extract the args

3. **Call mutate agent** with the args (everything after "MUTATE_ARGS: "):
   ```
   Task(mutate, "sa CURRENT NEIGHBOR <step_category>")
   ```

4. **Repeat** from step 1

### Example Session

```
Bash: ./sa/scripts/sa_step.sh
Output:
  [STATUS] iter=0 temp=5000 current=147734 best=147734
  MUTATE_ARGS: sa CURRENT NEIGHBOR extensive

Task(mutate, "sa CURRENT NEIGHBOR extensive")
  → Agent creates NEIGHBOR with mutation

Bash: ./sa/scripts/sa_step.sh
Output:
  [ACCEPT] 25677 (current was 147734)
  [STATUS] iter=1 temp=5000 current=25677 best=25677
  MUTATE_ARGS: sa CURRENT NEIGHBOR extensive

Task(mutate, "sa CURRENT NEIGHBOR extensive")
  → Agent creates NEIGHBOR with mutation

... repeat ...

Bash: ./sa/scripts/sa_step.sh
Output:
  [STATUS] iter=500 temp=8.5 current=3827 best=3827
  DONE: Reached final temperature (best=3827)

→ Stop, report final result
```

## What sa_step.sh Does

Each call handles:
1. **Post-process previous iteration** (if NEIGHBOR exists):
   - Evaluate NEIGHBOR
   - Update best (if better than all-time best)
   - Accept/reject decision (Metropolis criterion)
   - Log iteration, update state
   - Cool temperature (every 5 iterations)

2. **Check termination**:
   - Temperature < 10 → DONE
   - Iteration >= 500 → DONE

3. **Prepare next mutation**:
   - Calculate step category from temperature
   - Output MUTATE_ARGS

## Configuration

Edit `sa/scripts/sa_config.sh`:
```bash
INITIAL_TEMP=5000      # Starting temperature
FINAL_TEMP=10          # Stopping temperature
COOLING_RATE=0.95      # T' = T * rate
ITERATIONS_PER_TEMP=5  # Steps per temperature level
MAX_ITERATIONS=500     # Hard limit
```

## Fresh Start

To reset and start from scratch:
```bash
rm -rf sa/candidates/CAND_* sa/candidates/state.txt sa/candidates/history.txt
```

## Critical Rules

1. **NEUTRAL PROMPTS**: Pass ONLY what sa_step.sh gives you to the mutate agent
   - NO scores, NO hints, NO "try to improve"
   - The step category is all the guidance needed

2. **SEQUENTIAL**: Wait for mutate agent to finish before calling sa_step.sh again

3. **TRUST THE SCRIPT**: sa_step.sh handles all SA logic - acceptance, cooling, logging
