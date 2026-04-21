"""
benchmark_retrieval.py — measure Pneuma retrieval performance.

Runs a set of representative queries and reports:
  - Query latency (ms)
  - Result count and relevance scores
  - Estimated token consumption per query
  - Chunk size distribution across the palace

Usage:
    python scripts/benchmark_retrieval.py
    python scripts/benchmark_retrieval.py --queries "auth" "rate limiting" "database schema"
    python scripts/benchmark_retrieval.py --top-k 10 --csv results.csv
"""

import argparse
import os
import sys
import time
import csv
import statistics
from pathlib import Path

# ── Bootstrap Pneuma path ────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

# ── Token estimation ─────────────────────────────────────────────────────────
# Rule of thumb: 1 token ≈ 4 chars (English/code mix)
# Closer to 1 token ≈ 3.5 chars for code-heavy content
CHARS_PER_TOKEN = 3.5


def _tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


# ── Default queries ───────────────────────────────────────────────────────────
DEFAULT_QUERIES = [
    "authentication and token validation",
    "database connection and query handling",
    "error handling and exception types",
    "configuration loading and environment variables",
    "API endpoint routing",
    "memory management and allocation",
    "logging and debugging utilities",
    "network protocol handling",
    "build system and compilation",
    "test setup and fixtures",
]


# ── Benchmark runner ──────────────────────────────────────────────────────────

def run_benchmark(queries: list[str], top_k: int = 5) -> dict:
    from core.palace import configure, search as palace_search, status, list_wings, list_rooms
    from core.registry import resolve_project

    proj = resolve_project()
    if not proj:
        print("ERROR: No project registered. Run `pneuma init /path/to/project` first.")
        sys.exit(1)

    configure()

    # ── Palace overview ──────────────────────────────────────────────────────
    s = status()
    total_entries = s.get("total_drawers", 0)
    wings = list_wings()

    print(f"\n{'='*60}")
    print(f"  Pneuma Retrieval Benchmark")
    print(f"{'='*60}")
    print(f"  Project : {proj['project_path']}")
    print(f"  Palace  : {proj['palace_path']}")
    print(f"  Entries : {total_entries:,}")
    print(f"  Wings   : {len(wings)}")
    print(f"  top_k   : {top_k}")
    print(f"{'='*60}\n")

    # ── Chunk size distribution ──────────────────────────────────────────────
    print("Sampling chunk sizes (up to 200 entries)...")
    sample_results = palace_search("function", top_k=200)
    chunk_sizes = [_tokens(r.content) for r in sample_results]
    if chunk_sizes:
        print(f"  Chunk tokens  min={min(chunk_sizes)}  "
              f"avg={statistics.mean(chunk_sizes):.0f}  "
              f"max={max(chunk_sizes)}  "
              f"p95={sorted(chunk_sizes)[int(len(chunk_sizes)*0.95)]}\n")
    else:
        print("  (no entries to sample)\n")
        chunk_sizes = [0]

    # ── Per-query benchmarks ─────────────────────────────────────────────────
    print(f"{'Query':<45} {'ms':>6} {'hits':>5} {'top_score':>10} {'tokens':>8} {'avg_chunk':>10}")
    print("-" * 90)

    rows = []
    latencies = []
    token_totals = []
    scores = []

    for query in queries:
        t0 = time.perf_counter()
        results = palace_search(query, top_k=top_k)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        hit_count = len(results)
        top_score = results[0].relevance_score if results else 0.0
        total_tokens = sum(_tokens(r.content) for r in results)
        avg_chunk = total_tokens // hit_count if hit_count else 0

        latencies.append(elapsed_ms)
        token_totals.append(total_tokens)
        if results:
            scores.append(top_score)

        q_display = query[:43] + ".." if len(query) > 43 else query
        print(f"  {q_display:<43} {elapsed_ms:>6.1f} {hit_count:>5} "
              f"{top_score:>10.3f} {total_tokens:>8} {avg_chunk:>10}")

        rows.append({
            "query": query,
            "latency_ms": round(elapsed_ms, 2),
            "hits": hit_count,
            "top_score": round(top_score, 4),
            "total_tokens": total_tokens,
            "avg_chunk_tokens": avg_chunk,
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    print("-" * 90)
    print(f"\nSummary ({len(queries)} queries, top_k={top_k}):")
    print(f"  Latency       avg={statistics.mean(latencies):.1f}ms  "
          f"p95={sorted(latencies)[int(len(latencies)*0.95)]:.1f}ms  "
          f"max={max(latencies):.1f}ms")
    print(f"  Relevance     avg={statistics.mean(scores):.3f}  "
          f"min={min(scores):.3f}  max={max(scores):.3f}")
    print(f"  Tokens/query  avg={statistics.mean(token_totals):.0f}  "
          f"min={min(token_totals)}  max={max(token_totals)}")

    # ── Comparison projection ─────────────────────────────────────────────────
    avg_tokens = statistics.mean(token_totals)
    avg_chunk_tok = statistics.mean(chunk_sizes)

    # Whole-file estimate: assume average file is 4–8× larger than a chunk
    whole_file_est = avg_chunk_tok * 6  # conservative 6× multiplier
    whole_file_query_est = whole_file_est * top_k

    print(f"\nProjected comparison (Pneuma chunks vs whole-file approach):")
    print(f"  Pneuma chunks    : ~{avg_tokens:.0f} tokens per query")
    print(f"  Whole-file est.  : ~{whole_file_query_est:.0f} tokens per query  "
          f"({whole_file_query_est/avg_tokens:.1f}× more)")

    sessions = [10, 50, 100]
    print(f"\n  Token budget over a session:")
    print(f"  {'Queries':>8}  {'Pneuma':>12}  {'Whole-file':>12}  {'Saved':>12}")
    for n in sessions:
        p = int(avg_tokens * n)
        w = int(whole_file_query_est * n)
        print(f"  {n:>8}  {p:>12,}  {w:>12,}  {w-p:>12,}")

    return {"rows": rows, "latencies": latencies, "tokens": token_totals, "scores": scores}


def main():
    parser = argparse.ArgumentParser(description="Benchmark Pneuma retrieval")
    parser.add_argument("--queries", nargs="+", default=None,
                        help="Queries to benchmark (default: built-in set)")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Results per query (default: 5)")
    parser.add_argument("--csv", default=None,
                        help="Write per-query results to CSV file")
    args = parser.parse_args()

    queries = args.queries or DEFAULT_QUERIES
    results = run_benchmark(queries, top_k=args.top_k)

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results["rows"][0].keys())
            writer.writeheader()
            writer.writerows(results["rows"])
        print(f"\nResults written to {args.csv}")


if __name__ == "__main__":
    main()
