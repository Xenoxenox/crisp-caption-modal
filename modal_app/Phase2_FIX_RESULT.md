# Phase 2 Translation Throughput Fix Result

Status: PASS. The v2 realtime evaluation reduced translation queue latency below the 15s p95 target.

## Build

- git_head: `5d823af1dfd48fc373f62874bd32b78eeb12fa7d`
- Modal deploy: passed
- Local compile: passed

## Runtime Changes

- llama-server `-np`: `1 -> 4`
- llama-server `-c`: `8192 -> 32768`
- realtime translation workers: `1 -> 4`

## Comparison

| Metric | v1 (before) | v2 (after) | Change |
|---|---:|---:|---:|
| final count | 26 | 26 | unchanged |
| translation_error | 0 | 0 | unchanged |
| first_final_elapsed_sec | 5.247 | 5.165 | -0.082s |
| translation p50 | 36.453 | 1.182 | -96.8% |
| translation p95 | 71.798 | 2.060 | -97.1% |
| translation max | 75.932 | 2.571 | -96.6% |
| WS close_code | 1006 | 1006 | unchanged |
| LRC near + exact | 15 | 15 | unchanged |

## Acceptance

PASS: v2 translation p95 is `2.060s`, below the `15s` target.

ASR latency did not regress: first final was `5.165s`, below the `10s` target.

## Known Issues

- None newly introduced by this throughput fix.
