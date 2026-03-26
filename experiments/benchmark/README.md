---
name: benchmark
type: experiment
display_name: Benchmark
description: Stress-test LEAP2 — measure RPC throughput and latency across decorator combinations
entry_point: dashboard.html
require_registration: true
authors: Sampad Mohanty
organizations: University of Southern California
tags: [benchmark, performance, stress-test]
version: "1.0.0"
leap_version: ">=1.0"
---

# Benchmark

Stress-test LEAP2's RPC pipeline from the browser. Fires concurrent requests against functions with different decorator combinations and measures throughput (requests/second) and latency (median, P95, P99) in real time.

## Scenarios

| Scenario | Decorators | What It Measures |
|---|---|---|
| **noop_minimal** | `@nolog @noregcheck @ratelimit(False)` | Baseline: network + dispatch only |
| **noop_regcheck** | `@nolog @ratelimit(False)` | Adds DB registration lookup |
| **noop_logged** | `@noregcheck @ratelimit(False)` | Adds DuckDB log write |
| **noop_rate_limited** | `@nolog @noregcheck` | Adds rate limit check (120/min) |
| **noop_full** | *(none)* | Full pipeline: reg check + rate limit + logging |
| **noop_adminonly** | `@adminonly @nolog @ratelimit(False)` | Admin session check |

## Usage

### Live dashboard (browser)

1. Open the benchmark dashboard
2. Log in as admin (required for student registration and admin-only tests)
3. Choose concurrency level and duration
4. Select scenarios and click **Run**
5. Watch real-time RPS chart and latency table update

> **Note:** Browsers limit concurrent connections to ~6 per origin, capping throughput at ~60 RPS regardless of server capacity. Use the offline benchmark for true throughput numbers.

### Offline benchmark (pytest)

The offline benchmark uses FastAPI's `TestClient` to bypass browser connection limits and measure true server-side pipeline throughput. Results are saved to a JSON file and displayed in the offline results page.

```bash
cd starterlab
python -m pytest tests/test_benchmark.py -v
```

Results are saved to `experiments/benchmark/ui/benchmark-results.json`. Start the server and visit the offline results page to view charts, tables, and analysis:

```bash
leap run
# then open http://localhost:8000/exp/benchmark/ui/offline.html
```

## Technical Details

### What the benchmark measures

Each scenario function does trivial work (`return True`). The latency you see is **framework overhead only**: network round-trip, JSON parsing, decorator checks, and database I/O — not your experiment code.

### How concurrency works

LEAP2 runs on a single uvicorn process. API handlers are dispatched to FastAPI's thread pool (~40 threads). Each incoming request gets its own thread, so concurrent requests are handled in parallel. A slow or blocking function only blocks its own thread, not the entire server.

This means:
- **Concurrency 1** measures per-request latency with zero contention
- **Concurrency 10-20** shows realistic classroom load (students calling functions simultaneously)
- **Concurrency 50** saturates the thread pool and reveals the throughput ceiling

### Per-experiment database isolation

Each experiment has its own DuckDB file (`db/experiment.db`). Writes to one experiment never contend with another. The `noop_logged` scenario writes to the benchmark experiment's DB — in a real deployment, those writes wouldn't affect other experiments' performance.

### Why `noop_rate_limited` shows errors

The default rate limit is 120 calls/minute per student per function. At any concurrency above 1, the benchmark hits this limit within seconds. Every subsequent call returns HTTP 429. This is intentional — it demonstrates why `@ratelimit(False)` is important for high-frequency functions (polling, real-time game state, UI updates).

### DuckDB write characteristics

DuckDB uses a process-level write lock. Within a single process, multiple threads can read concurrently, but writes are serialized. The `noop_logged` vs `noop_minimal` comparison shows this cost — each logged call does a synchronous `INSERT` + `COMMIT` to DuckDB. Use `@nolog` on high-frequency functions to avoid this overhead.

**Configuration:** LEAP2 sets `preserve_insertion_order = false` on the DuckDB engine to reduce write overhead. This disables internal bookkeeping that tracks row insertion order — unnecessary since network requests arrive in nondeterministic order and all queries use explicit `ORDER BY`. See `plans/duckdb-performance-improvements.md` in the LEAP2 repo for additional optimization strategies.

### Server tuning

LEAP2 uses uvloop (faster event loop) and httptools (faster HTTP parser) by default. Access logs are disabled for throughput — run `leap run -v` to re-enable them for debugging.

### Scaling notes

A single LEAP2 process with thread-pool dispatch can handle ~2,000-4,000 req/s depending on hardware. For a classroom of 200 students, this provides 10-20x headroom. Multi-worker scaling is not currently supported due to DuckDB's single-process file locking — see the performance plan in `plans/performance-production-plan.md` for details.
