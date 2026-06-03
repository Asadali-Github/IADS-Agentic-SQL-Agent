#!/usr/bin/env python3
"""Benchmark: score a (mock) agent against the golden set and print the report.

Swap MockOrchestrator() for the real orchestrator when it lands - nothing else
changes.

    python examples/benchmark_example.py
"""
import _path  # noqa: F401

from evaluation.benchmark import MockOrchestrator, format_report, load_golden, run_benchmark

golden = load_golden()  # evaluation/datasets/golden_queries.jsonl
print(f"loaded {len(golden)} golden questions\n")

result = run_benchmark(MockOrchestrator(seed=7, accuracy=0.85), golden=golden)
print(format_report(result))
