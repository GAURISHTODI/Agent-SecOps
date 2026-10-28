# Agent SecOps -- Benchmark Results

Ground truth is labelled in `scripts/benchmark.py`. A seeded violation counts as detected only when the specific rule or reasoning probe named for it fires on the right resource.

## Hand-written fixtures

Plans in `examples/plans/`, written by hand to mirror the seeded modules.

| Metric | Value |
|---|---|
| Seeded violations across all three clouds | 42 |
| Detected by deterministic rules alone | 33 (78.6%) |
| Detected with the reasoning layer | 42 (100.0%) |
| **Violations recovered by reasoning alone** | **9** |
| False positives on the compliant plan (verdict-affecting) | 0 |
| Low-severity advisories on the compliant plan | 0 |

| Plan | Seeded | Rules only | + Reasoning | Verdict | Time |
|---|---|---|---|---|---|
| `azure_noncompliant.plan.json` | 28 | 21 | 28 | BLOCK | 9 ms |
| `aws_noncompliant.plan.json` | 8 | 7 | 8 | BLOCK | 9 ms |
| `gcp_noncompliant.plan.json` | 6 | 5 | 6 | BLOCK | 8 ms |

**Recovered by the reasoning layer:**

- `azure_noncompliant.plan.json`: network default allow
- `azure_noncompliant.plan.json`: shared keys enabled
- `azure_noncompliant.plan.json`: versioning disabled
- `azure_noncompliant.plan.json`: firewall spans all IPv4
- `azure_noncompliant.plan.json`: password auth enabled
- `azure_noncompliant.plan.json`: no availability zone
- `azure_noncompliant.plan.json`: access policies not RBAC
- `aws_noncompliant.plan.json`: versioning disabled
- `gcp_noncompliant.plan.json`: versioning disabled

**Known gaps (not yet detected):**

_All seeded violations are currently detected._

**Compliant module:**

- `azure_compliant.plan.json`: verdict PASS, 0 verdict-affecting false positive(s), 0 low-severity advisory finding(s)

## Real terraform plan output

Plans in `examples/plans/real/`, produced by `terraform plan` + `terraform show -json` on the seeded modules in `examples/terraform/` and the compliant module in `infra/demo/`. This is the input shape the CI pipeline gives the gate.

| Metric | Value |
|---|---|
| Seeded violations across all three clouds | 42 |
| Detected by deterministic rules alone | 33 (78.6%) |
| Detected with the reasoning layer | 42 (100.0%) |
| **Violations recovered by reasoning alone** | **9** |
| False positives on the compliant plan (verdict-affecting) | 0 |
| Low-severity advisories on the compliant plan | 1 |

| Plan | Seeded | Rules only | + Reasoning | Verdict | Time |
|---|---|---|---|---|---|
| `azure_noncompliant.plan.json` | 28 | 21 | 28 | BLOCK | 9 ms |
| `aws_noncompliant.plan.json` | 8 | 7 | 8 | BLOCK | 11 ms |
| `gcp_noncompliant.plan.json` | 6 | 5 | 6 | BLOCK | 8 ms |

**Recovered by the reasoning layer:**

- `azure_noncompliant.plan.json`: network default allow
- `azure_noncompliant.plan.json`: shared keys enabled
- `azure_noncompliant.plan.json`: versioning disabled
- `azure_noncompliant.plan.json`: firewall spans all IPv4
- `azure_noncompliant.plan.json`: password auth enabled
- `azure_noncompliant.plan.json`: no availability zone
- `azure_noncompliant.plan.json`: access policies not RBAC
- `aws_noncompliant.plan.json`: versioning disabled
- `gcp_noncompliant.plan.json`: versioning disabled

**Known gaps (not yet detected):**

_All seeded violations are currently detected._

**Compliant module:**

- `azure_compliant.plan.json`: verdict PASS, 0 verdict-affecting false positive(s), 1 low-severity advisory finding(s)
  - WAF-SEC-005 on azurerm_storage_account.data (low)

## Reading these numbers

- The offline reasoning layer is a set of deterministic, hand-written probes derived from the framework knowledge base. "Recovered by reasoning" therefore means "caught by a framework-intent probe that no Layer-1 rule implements", not "discovered by a language model".
- The seeded modules were written by the same team that wrote the rules and probes, so recall on them is an upper bound. An independent test set is the obvious next step.
- Total evaluation wall-clock: 0.16 s.
