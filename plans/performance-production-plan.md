# LEAP2 Production Performance Plan

## Context

LEAP2 runs on a single-process async FastAPI/uvicorn server. The core bottleneck: all API
handlers are declared `async def` but call synchronous code (DB writes, function execution)
directly on the event loop. This **serializes all requests** — only one can run at a time,
regardless of how many students are connected. Effective concurrency right now: **1**.

The architecture is already designed for parallelism (each experiment has its own DuckDB file,
separate engines, separate session factories), but the `async def` handler blocks the single
event loop thread, preventing any of that from paying off.

## The Core Problem: `async def` vs `def` Handlers

FastAPI dispatches handlers differently based on their signature:

- **`async def`** (current) — runs directly on the event loop thread. If you call synchronous
  blocking code (like `execute_rpc()` → DuckDB commit), the entire event loop freezes. No other
  request can even begin parsing until your function returns.

- **`def`** (proposed fix) — FastAPI auto-dispatches to its thread pool (~40 threads). A blocking
  call only blocks its own thread. 39 other threads continue serving requests.

This is the single most important fix. It changes effective concurrency from 1 to ~40 with a
one-word change.

## Why Not Multiple Processes (Workers)?

DuckDB uses a **file-level lock** for write access. One process opens the file read-write,
every other process trying to connect gets a hard error (not a timeout — an error). With 4
uvicorn workers, 3 of them would crash on any experiment DB access.

Workarounds exist but add significant complexity:
- **PostgreSQL**: requires running a separate database server, breaks LEAP2's zero-config
  file-based philosophy
- **SQLite WAL mode**: handles multi-process better, but requires a storage layer migration
  and loses DuckDB's columnar analytics advantage
- **Write queue**: decouple log writes into a background process via multiprocessing.Queue —
  significant new architecture (queue management, crash recovery, background process)

**This is premature optimization for LEAP2's use case.** After the `def` handler fix:

```
1 worker × 40 threads = 40 concurrent requests
Each request ≈ 5ms (function + DB write)
Throughput ≈ ~2,000-4,000 req/s realistically
```

A classroom of 200 students each clicking once per second is 200 req/s. That leaves
**10-20x headroom** on a single process. Multi-process only becomes worth the complexity
if LEAP2 hits classrooms of thousands of simultaneous users — revisit then, not now.

## Instructor Functions: Sync Only (For Now)

Instructor-defined experiment functions (in `funcs/*.py`) are called at `rpc.py:168`:
```python
result = func(*args, **kwargs)
```

No `await`, no `asyncio.iscoroutinefunction()` check. If an instructor writes `async def`,
the coroutine object gets returned as the "result" — silently broken.

With the `def` handler approach, instructor async functions aren't needed. Each sync function
runs in its own thread. A slow/blocking function only blocks that one student's request,
not the whole server.

Supporting `async def` instructor functions is **not recommended** — it requires `execute_rpc`
to become async, and a CPU-heavy `async def` without `await` would block the event loop just
like the current problem. Instructors are not Python async experts. Threads are predictable
and safe.

## Recommended Changes (Priority Order)

### 1. `def` Handler Fix — `call.py` (1-word change)

Change the RPC call handler from `async def` to `def`. FastAPI will auto-dispatch it to the
thread pool. All synchronous code in `execute_rpc()` (registration check, function call, DB
log write) runs on a worker thread instead of blocking the event loop.

This is the **highest impact, lowest effort** change. Effective concurrency goes from 1 to ~40.

Also apply to any other `async def` handlers that call synchronous storage/rpc code (log
endpoints, admin endpoints, experiment list).

**File:** `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/api/call.py` (line ~28)

### 2. Uvicorn Tuning — `cli.py` (~3 lines)

Currently: `uvicorn.run(the_app, host=host, port=port)` — no tuning at all.

- `access_log=False` by default — removes per-request log line, ~10-15% throughput gain.
  Add a `--verbose` / `-v` CLI flag on `leap run` that re-enables access logs (and could
  enable other verbose output in the future). Most instructors just run `leap run` and
  expect good performance out of the box; the ones debugging will use `leap run -v`.
- `loop="uvloop"` — faster event loop implementation, ~20-30% gain on Linux
- `http="httptools"` — faster HTTP parser

Both uvloop and httptools are already bundled with the `uvicorn[standard]` dependency in
pyproject.toml. No new dependencies needed.

**File:** `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/cli.py` (line ~1554)

### 3. Rate Limiter Efficiency — `rpc.py` (~10 lines)

`_check_rate_limit` rebuilds a filtered list on every call:
```python
_rate_windows[key] = [t for t in timestamps if t > cutoff]  # O(N)
```

Replace with `collections.deque` and pop stale entries from the left — O(1) per check.

**File:** `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/core/rpc.py` (lines 52-70)

### 4. N+1 in /api/experiments — `experiments.py` (~10 lines)

The experiments list endpoint creates a separate DB session per experiment to count students.
Reuse one session for all counts, or batch the queries.

**File:** `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/api/experiments.py` (lines 21-37)

### 5. Middleware Review — `main.py`

- `SessionMiddleware` parses/validates sessions on every request including static files
- `slowapi.Limiter` does per-IP rate limiting globally
- Consider scoping these to API routes only
- Consider removing global slowapi if the per-function rate limiter in rpc.py is sufficient

**File:** `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/main.py` (lines 74-92)

## Postponed / Not Recommended

### Multi-Worker (`--workers` flag)

**WARNING: Do NOT enable multiple uvicorn workers while using DuckDB as the storage backend.**
DuckDB takes a process-level file lock on the database. The first worker acquires the lock;
every other worker that tries to connect gets a hard crash — not a timeout, not a queue, an
immediate `IOError: Could not set lock on file` on any DB operation. This means 3 out of 4
workers would fail on every RPC call, student registration check, and log query.

**The only two safe paths to multi-worker are:**
1. **Switch to SQLite with WAL mode** (see below) — SQLite handles multi-process gracefully
2. **Use a write queue** (see below) — funnel all DB writes through a single dedicated
   process, keeping DuckDB's single-writer constraint satisfied

The `def` handler fix + uvicorn tuning provides ~2,000-4,000 req/s on a single process,
which is 10-20x more than a 200-student classroom needs. **This is premature optimization
unless LEAP2 is deployed at a scale of thousands of simultaneous users**, which would also
warrant rethinking the storage layer entirely.

### SQLite as a Multi-Worker Path (Future Option)

If multi-worker ever becomes necessary, **switching from DuckDB to SQLite with WAL mode**
is the most practical path. SQLite WAL allows multiple processes to read concurrently and
handles write contention with a busy timeout (queues instead of crashing). This would
unlock the `--workers` flag without requiring a database server.

**What we'd lose from DuckDB:**
- Columnar storage (fast analytical scans over large datasets)
- Native Parquet/Arrow/CSV import/export
- Vectorized query execution
- Advanced analytical SQL (window functions, list types, etc.)

**What we actually use from DuckDB:** After auditing `storage.py`, LEAP2 uses **none of
these features**. The entire storage layer is standard SQLAlchemy ORM — `SELECT`, `INSERT`,
`DELETE`, `COUNT`, `CREATE INDEX`, basic `WHERE`/`ORDER BY`/`LIMIT` filtering. Every query
is portable SQL that works identically on SQLite. DuckDB is being used as a file-based
relational database, which is exactly what SQLite is purpose-built for.

**Migration effort:** Change `duckdb-engine` to `sqlite` in pyproject.toml, change the
connection URL from `duckdb:///path` to `sqlite:///path`, add `connect_args={"timeout": 10}`
for WAL busy timeout. The ORM models, queries, and session management stay identical.

**Decision:** Not needed now. The `def` fix provides massive headroom. But if we hit the
ceiling, the DuckDB → SQLite swap is a clean, low-risk migration that unlocks multi-process.

### Write Queue (Alternative Multi-Worker Path)

Another approach to unlocking multi-worker while keeping DuckDB: decouple log writes from
the request path entirely. Instead of each worker writing to DuckDB directly, workers push
log entries to a shared queue (e.g., `multiprocessing.Queue`), and a single dedicated
background process drains the queue and writes to DuckDB.

**Benefits:**
- RPC calls return immediately without waiting for DB commit — lower latency
- Only one process ever touches DuckDB — no file locking conflicts
- Multi-worker uvicorn becomes safe since workers only read from DB (for `is_registered`,
  `query_logs`, etc.) and queue writes instead of writing directly
- Keeps DuckDB (no migration needed)

**Drawbacks:**
- Significant new architecture — queue setup, background process lifecycle, graceful shutdown
- Log entries are eventually consistent (a log query immediately after an RPC call might
  not include it yet)
- Crash recovery: queued writes not yet flushed are lost unless persisted to disk first
- Read operations (`is_registered`, `query_logs`) still need direct DB access from workers,
  which means workers need read-only DuckDB connections — DuckDB supports this but it adds
  connection mode management

**Decision:** More complex than the SQLite swap for the same goal. Worth considering only
if DuckDB-specific features become important in the future (analytics, Parquet export, etc.)
and we can't migrate to SQLite. Not recommended as the first scaling step.

### Async Database Layer

Postponed. Switching to `create_async_engine()` + `AsyncSession` from SQLAlchemy 2.0 would
be the "correct" async approach, but it's a larger refactor and is mutually exclusive with
the `def` handler fix (you'd do one or the other, not both). The `def` fix achieves the
same concurrency benefit with zero risk and one word changed.

### Async Instructor Functions

Not recommended. Threads handle instructor function concurrency safely. Supporting
`async def` instructor functions adds complexity and a footgun (CPU-heavy async functions
without `await` would block the event loop).

## Files to Modify

1. `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/api/call.py` — `async def` → `def`
2. `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/cli.py` — uvicorn tuning params
3. `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/core/rpc.py` — deque rate limiter
4. `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/api/experiments.py` — N+1 fix
5. `/home/sampad/Desktop/Projects/LEAPALL/LEAP2/leap/main.py` — middleware scoping

## Verification

1. Run the benchmark experiment before and after changes
2. Compare RPS for `noop_minimal` at concurrency=10 — should see dramatic improvement
3. Compare `noop_logged` vs `noop_minimal` — logging overhead should be smaller since
   DB writes now run on parallel threads instead of serializing on the event loop
4. Verify `noop_rate_limited` still correctly returns 429s
5. Test with 2+ browser tabs running benchmarks simultaneously to confirm real concurrency
