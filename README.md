---
name: starterlab
type: lab
display_name: LEAP Starter Lab
description: Example experiments demonstrating LEAP2 features
icons: [/assets/icon.png, /assets/usc-viterbi.svg]
repository: https://github.com/leaplive/starterlab
experiments:
- name: default
- name: gradient-descent-2d
- name: graph-search
- name: monte-carlo
- name: quizlab
- name: talk
- name: benchmark
authors: Sampad Mohanty
tags:
- leap
- example
- starter
organizations: University of Southern California
---

# LEAP Starter Lab

A collection of example experiments for [LEAP2](https://github.com/leaplive/LEAP2).

## Quick start

```bash
git clone https://github.com/leaplive/starterlab.git
cd starterlab
leap init
leap run
```

## Experiments

| Name | Description |
|------|-------------|
| **default** | Starter experiment demonstrating RPC, logging, decorators, and registration |
| **gradient-descent-2d** | Optimize a 2D function with two local minima using gradient descent |
| **graph-search** | Explore graphs using BFS or DFS — grids, trees, and custom graphs |
| **monte-carlo** | Estimate pi by sampling random points inside the unit circle |
| **quizlab** | Markdown-based quizzes with auto-grading and score tracking |
| **talk** | Lightning talk slides — SIGCSE TS 2026 |
| **benchmark** | Stress-test LEAP2 — measure RPC throughput and latency across decorator combinations. Includes a live browser dashboard and an offline pytest benchmark with results viewer |

## Benchmarks

Run the server-side benchmark suite to measure RPC pipeline throughput:

```bash
python -m pytest tests/test_benchmark.py -v
```

Results are saved to `experiments/benchmark/ui/benchmark-results.json` and viewable in the offline results page when the server is running.

## Tests

```bash
pip install pytest
pytest tests/
```
