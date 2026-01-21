# Kernel Optimization Challenge

Optimize `KernelBuilder.build_kernel()` in `perf_takehome.py` to minimize execution cycles.

## Commands

```bash
# Run correctness + performance tests (outputs cycle count and speedup)
python tests/submission_tests.py
```

## Files

- `perf_takehome.py` - Your optimization target
- `problem.py` - Machine simulator and reference implementation

## Rules

- IMPORTANT: Always run `python tests/submission_tests.py` after changes to verify correctness
- IMPORTANT: Read `problem.py` to understand the machine architecture and instruction set
- IMPORTANT: Read the reference implementations in `problem.py` to understand what the kernel must compute
- Lower cycle count is better
- Correctness must be maintained - incorrect solutions are worthless

## Prompting Guidelines

Before creating or updating prompts, skills, or agent configurations, read `docs/PROMPTING.md`.
