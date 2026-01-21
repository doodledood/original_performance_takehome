# Performance Engineering Take-Home Challenge

This is Anthropic's kernel optimization challenge. The goal is to optimize `KernelBuilder.build_kernel()` to minimize execution cycles on a custom VLIW SIMD machine simulator.

## Key Commands

```bash
# Run all tests
python perf_takehome.py

# Measure cycle count (primary benchmark)
python perf_takehome.py Tests.test_kernel_cycles

# Run with trace visualization
python perf_takehome.py Tests.test_kernel_trace

# Start trace viewer server (then open http://localhost:8000)
python watch_trace.py

# Run submission tests (uses frozen kernel)
python tests/submission_tests.py
```

## Project Structure

- `perf_takehome.py` - Main file with `KernelBuilder` class to optimize
- `problem.py` - Simulator, machine architecture, and reference implementations
- `watch_trace.py` - Development server for Perfetto trace visualization
- `tests/submission_tests.py` - Correctness and speedup benchmarks

## Architecture

The simulator implements a VLIW SIMD machine with these execution engines:
- `alu` (12 slots): Scalar arithmetic
- `valu` (6 slots): Vector operations (VLEN=8)
- `load` (2 slots): Memory reads
- `store` (2 slots): Memory writes
- `flow` (1 slot): Control flow, halt
- `debug` (64 slots): Debugging/tracing

## Optimization Target

Edit `KernelBuilder.build_kernel()` in `perf_takehome.py` (lines 85-171). Key methods:
- `add()`: Add instructions to stream
- `build()`: Pack instructions into VLIW bundles
- `alloc_scratch()`: Allocate register space
- `scratch_const()`: Allocate constants (with deduplication)
- `build_hash()`: Generate hash operation instructions

## Performance Benchmarks

- Baseline: 147,734 cycles
- Best known: 1,363 cycles (99.1% improvement)

## Development Workflow

1. Edit `build_kernel()` in `perf_takehome.py`
2. Run `python perf_takehome.py Tests.test_kernel_trace` to generate trace
3. Run `python watch_trace.py` in another terminal
4. Open http://localhost:8000 to visualize in Perfetto UI
5. Iterate on optimizations

## Important Notes

- IMPORTANT: Always verify correctness before optimizing - run `python tests/submission_tests.py`
- The kernel implements parallel tree traversal with XOR hashing
- Maximize instruction-level parallelism within VLIW bundles
- Respect slot limits per engine type (defined in `SLOT_LIMITS`)
