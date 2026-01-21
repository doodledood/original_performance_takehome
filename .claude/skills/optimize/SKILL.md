---
name: optimize
description: Run genetic algorithm optimization on the kernel
disable-model-invocation: true
---

# Genetic Algorithm Optimization

Optimize `build_kernel()` using genetic algorithm with mutate and crossover agents.

## Parameters (from $ARGUMENTS, format: --key=value)

- `--population=10` - number of candidates
- `--generations=10` - number of generations
- `--elite=3` - top candidates preserved unchanged
- `--crossover-rate=0.8` - probability of crossover
- `--mutation-rate=0.2` - probability of mutation

## Progress File

Log to `optimization_progress.txt` in root directory. This file enables resumption after interruption.

### State Detection on Start

Check these in order:

1. **Read `optimization_progress.txt`** if it exists
2. **Check for existing candidates** via `ls candidates/`
3. **Determine resume point** based on log contents:
   - No log file → fresh start
   - Log exists with `=== Generation N COMPLETE ===` → resume from generation N+1
   - Log exists without COMPLETE marker → resume mid-generation (re-evaluate and continue)
   - Candidates exist but no log → evaluate existing candidates, treat as generation 0 complete

## Helper Scripts

All scripts are in `./scripts/`:

| Script | Purpose | Usage |
|--------|---------|-------|
| `init_candidate.sh {id}` | Create candidate folder | Creates `candidates/CAND_{id}/` |
| `eval_candidate.sh {id}` | Evaluate single candidate | Returns cycle count |
| `eval_all.sh` | Evaluate all candidates | Saves to `candidates/scores.txt`, outputs sorted |
| `save_best.sh {id}` | Save best to `best/` folder | Keeps only `perf_takehome.py` |
| `get_elite.sh {n}` | Get top N candidate IDs | One ID per line |
| `get_non_elite.sh {n}` | Get non-elite IDs | One ID per line |
| `select_parents.sh {seed}` | Tournament selection | Returns `{parent1} {parent2}` |
| `should_crossover.sh {rate} {seed}` | Decide crossover | Exit 0=yes, 1=no |
| `should_mutate.sh {rate} {seed}` | Decide mutation | Exit 0=yes, 1=no |
| `parents_identical.sh {p1} {p2}` | Check if parents identical | Exit 0=identical, 1=different |

## Workflow

### 1. Resume Check

- Read `optimization_progress.txt` if exists
- Run `ls candidates/` to check for existing candidates
- Determine resume point (see State Detection above)
- Log: `[RESUME] Starting from generation N` or `[START] Fresh optimization run`

### 2. Initialize (skip if candidates exist)

```bash
# Initialize all candidates
for id in 001 002 ... 00N; do
  ./scripts/init_candidate.sh $id
done
# Create __init__.py for Python imports
touch candidates/__init__.py
for id in 001 002 ... 00N; do
  touch candidates/CAND_$id/__init__.py
done
```
Log: `[INIT] Created N candidates`

### 3. Initial Evaluation (Generation 0)

```bash
# Evaluate all - saves to candidates/scores.txt
./scripts/eval_all.sh

# Save best candidate
BEST=$(./scripts/get_elite.sh 1)
./scripts/save_best.sh $BEST
```

Note: Since all candidates start as baseline copies, only ONE eval is needed for Gen 0 (all have same score). Log baseline cycles once.

### 4. Per Generation Loop

For each generation 1 to N:

#### 4a. Determine Operations (deterministic)

```bash
# Get candidates to modify
ELITE=$(./scripts/get_elite.sh 3)           # These stay unchanged
NON_ELITE=$(./scripts/get_non_elite.sh 3)   # These get replaced

# For each non-elite slot, decide operation using deterministic seeds
# Seed format: {generation}_{slot} for reproducibility
for SLOT in $NON_ELITE; do
  SEED="${GEN}_${SLOT}"
  if ./scripts/should_crossover.sh 0.8 $SEED; then
    PARENTS=$(./scripts/select_parents.sh $SEED)
    P1=$(echo $PARENTS | cut -d' ' -f1)
    P2=$(echo $PARENTS | cut -d' ' -f2)
    # Skip crossover if parents are identical (would be pointless)
    if ! ./scripts/parents_identical.sh $P1 $P2; then
      # Queue crossover: $PARENTS -> $SLOT
    fi
  fi

  MUTATE_SEED="${GEN}_${SLOT}_m"
  if ./scripts/should_mutate.sh 0.2 $MUTATE_SEED; then
    # Queue mutation: $SLOT
  fi
done
```

#### 4b. Execute Crossovers (PARALLEL)

**CRITICAL: Launch ALL crossover agents in ONE message with multiple Task calls**

```
Task(crossover, "CAND_001 CAND_002 CAND_004")
Task(crossover, "CAND_003 CAND_001 CAND_005")
Task(crossover, "CAND_002 CAND_003 CAND_006")
... all in ONE message
```

#### 4c. Execute Mutations (PARALLEL)

**CRITICAL: Launch ALL mutate agents in ONE message with multiple Task calls**

```
Task(mutate, "CAND_004")
Task(mutate, "CAND_007")
Task(mutate, "CAND_008")
... all in ONE message
```

#### 4d. Re-evaluate Modified Candidates (PARALLEL)

**CRITICAL: Run evaluations in parallel using multiple Bash tool calls in ONE message**

Only re-evaluate candidates that were modified (crossover or mutation targets). Elite candidates keep their cached scores.

```
Bash("./scripts/eval_candidate.sh 004")
Bash("./scripts/eval_candidate.sh 005")
Bash("./scripts/eval_candidate.sh 006")
... all in ONE message
```

After evals complete, update `candidates/scores.txt` with new scores.

#### 4e. Update Best & Log

```bash
# Save best candidate
BEST=$(./scripts/get_elite.sh 1)
./scripts/save_best.sh $BEST
```

Log generation summary and write `=== Generation N COMPLETE ===` marker.

### 5. Finish

- Best kernel is in `best/perf_takehome.py`
- Report: initial cycles vs final cycles, improvement percentage

## Critical Rules

1. **PARALLEL CROSSOVERS**: Launch ALL crossover agents in ONE message
2. **PARALLEL MUTATIONS**: Launch ALL mutate agents in ONE message
3. **PARALLEL EVALS**: Use multiple Bash tool calls in ONE message for evaluations
4. **DETERMINISM**: Use `{generation}_{slot}` seeds for reproducible decisions
5. **AGENT ARGS**: Pass ONLY candidate IDs to agents - no hints, no bias
   - mutate: `CAND_{id}`
   - crossover: `CAND_{parent1} CAND_{parent2} CAND_{child}`

## Log Format

```
[START] Fresh optimization run | pop=10, gen=10, elite=3
[INIT] Created 10 candidates

=== Generation 0 ===
Baseline: 147734 cycles
Best: 147734 cycles | Avg: 147734 cycles
=== Generation 0 COMPLETE ===

=== Generation 1 ===
[PLAN] Crossovers: 004=001x002, 005=001x003, 006=002x003
[PLAN] Mutations: 004, 007, 008, 009, 010
[CROSSOVER] 004 = 001 x 002: combined loop unrolling with memory layout
[CROSSOVER] 005 = 001 x 003: merged instruction ordering
[MUTATE] 004: reordered memory accesses
[MUTATE] 007: unrolled inner loop
[EVAL] 004: 142000 cycles
[EVAL] 005: 145000 cycles
[EVAL] 007: 148000 cycles

Best: 142000 cycles | Avg: 145234 cycles
Improvement: 3.9% over baseline

Candidates (sorted):
  004: 142000 cycles - crossover+mutate
  005: 145000 cycles - crossover
  001: 147734 cycles - elite
  ...
=== Generation 1 COMPLETE ===
```

**Key markers for resumption:**
- `=== Generation N COMPLETE ===` - signals generation fully finished
- `[EVAL] {id}:` - individual evaluations (allows mid-generation recovery)

Record the one-line summary returned by each agent (mutation or crossover description).
