# Agent SecOps -- Benchmark Results

Measured against the seeded misconfiguration test set in `examples/plans/`, with ground truth labelled in `scripts/benchmark.py`.

## Headline numbers

| Metric | Value |
|---|---|
| Seeded violations across all three clouds | 42 |
| Detected by deterministic rules alone | 37 (88.1%) |
| Detected with the reasoning layer | 42 (100.0%) |
| **Violations recovered by reasoning alone** | **5** |
| False positives on the compliant plan | 0 |
| Total evaluation wall-clock | 0.07 s |

The uplift row is the research claim in one number: those violations are visible in framework guidance but are not expressed by any hand-written rule, which is exactly the class a static scanner misses.

## Per-plan breakdown

| Plan | Seeded | Rules only | + Reasoning | Verdict | Time |
|---|---|---|---|---|---|
| `azure_noncompliant.plan.json` | 28 | 25 | 28 | BLOCK | 10 ms |
| `aws_noncompliant.plan.json` | 8 | 7 | 8 | BLOCK | 9 ms |
| `gcp_noncompliant.plan.json` | 6 | 5 | 6 | BLOCK | 9 ms |

## What the reasoning layer recovered

- `azure_noncompliant.plan.json`: firewall spans all IPv4
- `azure_noncompliant.plan.json`: no availability zone
- `azure_noncompliant.plan.json`: access policies not RBAC
- `aws_noncompliant.plan.json`: versioning disabled
- `gcp_noncompliant.plan.json`: versioning disabled

## Known gaps (not yet detected)

_All seeded violations are currently detected._

## False positives on the compliant module

- `azure_compliant.plan.json`: 0 false positive(s), verdict PASS

A gate that fails clean code gets disabled by the team that owns it, so this number matters as much as the detection rate.