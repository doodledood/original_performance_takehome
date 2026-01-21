---
name: optimize
description: Run genetic algorithm optimization on the kernel
disable-model-invocation: true
---

# Genetic Algorithm Optimization

Optimize `build_kernel()` using genetic algorithm with mutate and crossover agents.

## Parameters (from $ARGUMENTS, format: --key=value)

- `--population=6` - number of candidates
- `--generations=10` - number of generations
- `--elite=2` - top candidates preserved unchanged
- `--mutation-rate=0.3` - probability of mutation

## Workflow

1. **Initialize**: Run `./scripts/init_candidate.sh {id}` for candidates 001..N
2. **Evaluate**: Run `python candidates/{id}/submission_tests.py` to get cycle counts
3. **Per generation**:
   - Rank candidates by cycles (lower = better)
   - Keep top `elite` unchanged
   - Fill remaining slots via crossover (select random parent pairs from top half)
   - Apply mutation to `mutation-rate` fraction of non-elite candidates
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
