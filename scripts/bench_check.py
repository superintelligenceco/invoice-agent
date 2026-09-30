"""Run the benchmarks and fail when one is more than twice as slow as the committed baseline.

Usage:
    python scripts/bench_check.py            # compare with benchmarks/baseline.json
    python scripts/bench_check.py --update   # write a new baseline from this machine

The baseline stores the median time of each benchmark in seconds, measured on a GitHub-hosted
ubuntu-latest runner. Write a new one from the `bench` job's artifact when the hot path changes
on purpose.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "benchmarks" / "baseline.json"
MAX_RATIO = 2.0


def run_benchmarks(out: Path) -> dict[str, float]:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "benchmarks",
            "-q",
            "-p",
            "no:cacheprovider",
            "--benchmark-only",
            f"--benchmark-json={out}",
        ],
        check=True,
        cwd=ROOT,
    )
    data = json.loads(out.read_text())
    return {b["name"]: b["stats"]["median"] for b in data["benchmarks"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="write a new baseline")
    parser.add_argument("--json", type=Path, help="also keep the raw pytest-benchmark JSON here")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        raw = args.json or Path(tmp) / "bench.json"
        medians = run_benchmarks(raw)

    if args.update:
        BASELINE.write_text(json.dumps(medians, indent=2, sort_keys=True) + "\n")
        print(f"Wrote {BASELINE.relative_to(ROOT)}")
        return 0

    baseline: dict[str, float] = json.loads(BASELINE.read_text())
    rows = ["| Benchmark | Baseline (ms) | Now (ms) | Ratio |", "| --- | ---: | ---: | ---: |"]
    failed = []
    for name, now in sorted(medians.items()):
        base = baseline.get(name)
        if base is None:
            rows.append(f"| `{name}` | new | {now * 1000:.2f} | |")
            continue
        ratio = now / base
        rows.append(f"| `{name}` | {base * 1000:.2f} | {now * 1000:.2f} | {ratio:.2f}x |")
        if ratio > MAX_RATIO:
            failed.append(name)
    table = "\n".join(rows)
    print(table)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Benchmarks\n\nFails above {MAX_RATIO:.0f}x the baseline.\n\n{table}\n")
    if failed:
        print(f"More than {MAX_RATIO:.0f}x slower than the baseline: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
