"""Server-side benchmark tests for LEAP2 RPC pipeline.

Measures throughput and latency by calling /exp/benchmark/call directly
via FastAPI's TestClient — no browser, no network, no connection limits.

Results are saved to experiments/benchmark/ui/benchmark-results.json
for display in the offline benchmark dashboard.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from leap.core import storage
from leap.main import create_app

# Do NOT disable rate limiting — we test it explicitly
os.environ.pop("LEAP_RATE_LIMIT", None)

EXP = "benchmark"
STUDENT_ID = "bench-001"
CALL_URL = f"/exp/{EXP}/call"
STARTERLAB_ROOT = Path(__file__).resolve().parent.parent

SCENARIO_META = {
    "noop_minimal":      {"label": "Minimal",       "color": "bright_blue",  "hex": "#3b82f6"},
    "noop_regcheck":     {"label": "Reg Check",     "color": "bright_cyan",  "hex": "#06b6d4"},
    "noop_logged":       {"label": "Logged",        "color": "yellow",       "hex": "#f59e0b"},
    "noop_rate_limited": {"label": "Rate Limited",  "color": "bright_red",   "hex": "#ef4444"},
    "noop_full":         {"label": "Full Pipeline", "color": "bright_magenta", "hex": "#8b5cf6"},
    "noop_adminonly":    {"label": "Admin Only",    "color": "bright_green", "hex": "#10b981"},
}

# Module-level results accumulator
_collected_results: dict[str, dict] = {}
_bench_config = {"concurrency": 20, "duration_s": 3}


# ── Fixtures ──


@pytest.fixture(scope="module")
def bench_client(starterlab_root):
    """TestClient with admin session and registered benchmark student."""
    app = create_app(root=starterlab_root)
    with TestClient(app) as c:
        resp = c.post("/login", json={"password": "benchtest"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"

        c.post(
            f"/exp/{EXP}/admin/add-student",
            json={"student_id": STUDENT_ID, "name": "Benchmark Bot"},
        )
        yield c
    storage.close_all_engines()


# ── Helpers ──


def run_benchmark(
    client: TestClient,
    func_name: str,
    concurrency: int = 20,
    duration_s: float = 3,
) -> dict:
    """Run a benchmark scenario and return stats."""
    latencies: list[float] = []
    errors = 0
    lock = threading.Lock()

    payload = {
        "student_id": STUDENT_ID,
        "func_name": func_name,
        "args": [],
        "kwargs": {},
    }

    start = time.monotonic()
    deadline = start + duration_s

    def worker():
        nonlocal errors
        local_lats = []
        local_errs = 0
        while time.monotonic() < deadline:
            t0 = time.perf_counter()
            resp = client.post(CALL_URL, json=payload)
            lat = (time.perf_counter() - t0) * 1000  # ms
            local_lats.append(lat)
            if resp.status_code != 200:
                local_errs += 1
        with lock:
            latencies.extend(local_lats)
            errors += local_errs

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(concurrency)]
        for f in futures:
            f.result()

    elapsed = time.monotonic() - start
    total = len(latencies)

    if not latencies:
        return {
            "total": 0, "rps": 0.0, "errors": 0,
            "median_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0,
        }

    sorted_lats = sorted(latencies)

    def pct(p):
        idx = max(0, int(p / 100 * len(sorted_lats)) - 1)
        return sorted_lats[idx]

    return {
        "total": total,
        "rps": round(total / elapsed, 1) if elapsed > 0 else 0.0,
        "errors": errors,
        "median_ms": round(pct(50), 2),
        "p95_ms": round(pct(95), 2),
        "p99_ms": round(pct(99), 2),
    }


def _collect(name: str, stats: dict):
    """Store results for the final summary."""
    _collected_results[name] = stats


def _lat_color(ms: float) -> str:
    if ms < 5:
        return "green"
    if ms < 20:
        return "yellow"
    return "red"


# ── Tests ──


class TestBenchmarkScenarios:
    """Individual scenario throughput tests."""

    def test_noop_minimal(self, bench_client):
        """Baseline: no logging, no reg check, no rate limit."""
        stats = run_benchmark(bench_client, "noop_minimal")
        _collect("noop_minimal", stats)
        assert stats["total"] > 0
        assert stats["errors"] == 0
        assert stats["rps"] > 100

    def test_noop_regcheck(self, bench_client):
        """Registration check adds a DB lookup."""
        stats = run_benchmark(bench_client, "noop_regcheck")
        _collect("noop_regcheck", stats)
        assert stats["total"] > 0
        assert stats["errors"] == 0

    def test_noop_logged(self, bench_client):
        """DuckDB INSERT per call — measures write overhead."""
        stats = run_benchmark(bench_client, "noop_logged")
        _collect("noop_logged", stats)
        assert stats["total"] > 0
        assert stats["errors"] == 0

    def test_noop_rate_limited(self, bench_client):
        """Rate limiter triggers 429 after 120 calls/min."""
        stats = run_benchmark(bench_client, "noop_rate_limited", concurrency=10)
        _collect("noop_rate_limited", stats)
        assert stats["total"] > 0
        assert stats["errors"] > 0, "Expected 429 errors from rate limiting"

    def test_noop_full(self, bench_client):
        """Full pipeline: reg check + rate limit + logging."""
        stats = run_benchmark(bench_client, "noop_full", concurrency=10)
        _collect("noop_full", stats)
        assert stats["total"] > 0

    def test_noop_adminonly(self, bench_client):
        """Admin session check."""
        stats = run_benchmark(bench_client, "noop_adminonly")
        _collect("noop_adminonly", stats)
        assert stats["total"] > 0
        assert stats["errors"] == 0


class TestBenchmarkComparisons:
    """Cross-scenario comparisons to validate overhead expectations."""

    def test_logging_adds_overhead(self, bench_client):
        """DuckDB logging should be measurably slower than minimal."""
        minimal = run_benchmark(bench_client, "noop_minimal", concurrency=10, duration_s=2)
        logged = run_benchmark(bench_client, "noop_logged", concurrency=10, duration_s=2)
        assert logged["median_ms"] > minimal["median_ms"], (
            f"Expected logged ({logged['median_ms']:.1f}ms) > minimal ({minimal['median_ms']:.1f}ms)"
        )

    def test_minimal_fastest(self, bench_client):
        """Minimal (no decorators) should have highest RPS."""
        minimal = run_benchmark(bench_client, "noop_minimal", concurrency=10, duration_s=2)
        regcheck = run_benchmark(bench_client, "noop_regcheck", concurrency=10, duration_s=2)
        assert minimal["rps"] > regcheck["rps"], (
            f"Expected minimal ({minimal['rps']:.0f}) > regcheck ({regcheck['rps']:.0f}) RPS"
        )


class TestBenchmarkSummary:
    """Print rich summary and save results JSON. Runs last."""

    def test_zz_summary(self, bench_client):
        """Print rich summary table and save results to JSON."""
        if not _collected_results:
            pytest.skip("No benchmark results collected")

        import sys
        # Write directly to terminal, bypassing pytest's capture
        try:
            terminal = open("/dev/tty", "w")
        except OSError:
            terminal = sys.stderr
        console = Console(file=terminal)
        console.print()

        # ── Rich table ──
        table = Table(
            title="Benchmark Results",
            title_style="bold",
            border_style="dim",
            show_lines=True,
            padding=(0, 1),
        )
        table.add_column("Scenario", style="bold", min_width=14)
        table.add_column("Requests", justify="right")
        table.add_column("RPS", justify="right", style="bold")
        table.add_column("Median", justify="right")
        table.add_column("P95", justify="right")
        table.add_column("P99", justify="right")
        table.add_column("Errors", justify="right")

        for key in SCENARIO_META:
            if key not in _collected_results:
                continue
            s = _collected_results[key]
            meta = SCENARIO_META[key]

            med_text = Text(f"{s['median_ms']:.1f} ms", style=_lat_color(s["median_ms"]))
            p95_text = Text(f"{s['p95_ms']:.1f} ms", style=_lat_color(s["p95_ms"]))
            p99_text = Text(f"{s['p99_ms']:.1f} ms", style=_lat_color(s["p99_ms"]))
            err_text = Text(str(s["errors"]), style="red" if s["errors"] > 0 else "dim")

            table.add_row(
                Text(meta["label"], style=meta["color"]),
                f"{s['total']:,}",
                f"{s['rps']:.0f}",
                med_text,
                p95_text,
                p99_text,
                err_text,
            )

        console.print(table)

        # ── Insights panel ──
        insights = []
        base = _collected_results.get("noop_minimal")
        if base:
            for key, label in [
                ("noop_regcheck", "Registration check"),
                ("noop_logged", "DuckDB logging"),
                ("noop_adminonly", "Admin auth"),
            ]:
                other = _collected_results.get(key)
                if other:
                    diff = other["median_ms"] - base["median_ms"]
                    if diff > 0.1:
                        insights.append(f"[bold]{label}[/] adds [yellow]+{diff:.1f} ms[/] per call")
                    else:
                        insights.append(f"[bold]{label}[/] is within baseline ([dim]{diff:+.1f} ms[/])")

            total_reqs = sum(s["total"] for s in _collected_results.values())
            insights.append(f"[bold]{total_reqs:,}[/] total requests across {len(_collected_results)} scenarios")

        if insights:
            console.print(Panel(
                "\n".join(f"  {i}" for i in insights),
                title="Key Findings",
                border_style="bright_blue",
                padding=(1, 2),
            ))

        # ── Save JSON ──
        results_json = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": _bench_config,
            "scenarios": {},
        }
        for key, stats in _collected_results.items():
            meta = SCENARIO_META.get(key, {})
            results_json["scenarios"][key] = {
                **stats,
                "label": meta.get("label", key),
                "color": meta.get("hex", "#888"),
            }

        out_path = STARTERLAB_ROOT / "experiments" / "benchmark" / "ui" / "benchmark-results.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results_json, f, indent=2)

        console.print(f"\n  [dim]Results saved to {out_path.relative_to(STARTERLAB_ROOT)}[/]\n")
