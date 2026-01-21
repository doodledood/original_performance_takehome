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

## Helper Scripts

- `./scripts/should_crossover.sh {rate}` - exits 0 if should crossover, 1 if not
- `./scripts/should_mutate.sh {rate}` - exits 0 if should mutate, 1 if not

## Workflow

1. **Initialize**: Run `./scripts/init_candidate.sh {id}` for candidates 001..N
2. **Evaluate**: Run `python candidates/{id}/submission_tests.py` to get cycle counts
3. **Per generation**:
   - Rank candidates by cycles (lower = better)
   - Keep top `elite` unchanged
   - For each non-elite slot:
     - Use `./scripts/should_crossover.sh {rate}` to decide crossover vs copy
     - If crossover: select two parents from top half, create child
     - Use `./scripts/should_mutate.sh {rate}` to decide mutation
     - If mutate: apply mutation to candidate
4. **Finish**: Copy best `perf_takehome.py` to root, report improvement

## Critical Rules

- IMPORTANT: Launch ALL crossover agents in ONE message (parallel Task calls)
- IMPORTANT: Launch ALL mutate agents in ONE message (parallel Task calls)
- IMPORTANT: Pass ONLY candidate IDs to agents - no hints, no bias
  - mutate: `{id}`
  - crossover: `{parent1} {parent2} {child}`

## Logging

Write to `/tmp/optimize-${CLAUDE_SESSION_ID}.log`:
```
Gen N: best=XXXX avg=XXXX [001:XXXX, 002:XXXX, ...]
```
