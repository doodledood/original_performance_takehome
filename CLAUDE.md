# Kernel Optimization Challenge

Optimize `KernelBuilder.build_kernel()` in `perf_takehome.py` to minimize execution cycles.

## Commands

```bash
# Measure cycle count (primary metric)
python perf_takehome.py Tests.test_kernel_cycles

# Run correctness + performance tests
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
