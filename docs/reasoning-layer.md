# Layer 2: how the reasoning layer works

Layer 2 has **three cooperating parts**. Only the third is structural; the
first two are what the project had before, described honestly.

| Part | File | What it really is |
|---|---|---|
| 2a. Probe reasoner (offline) | `agent/reasoner/offline.py` | A table of 12 hand-written probes. Each = resource-kind filter + a pillar gate from the knowledge base + a yes/no test + a fixed confidence. It is *rule-like*; its value is the KB gating and being the control arm of the experiment. |
| 2a'. LLM reasoner (optional) | `agent/reasoner/llm.py` | Retrieval-augmented prompting with mechanical verification. Built and unit tested, **not benchmarked**. |
| **2b. Dependency-graph risk propagation** | `agent/reasoner/graph.py` | **The algorithmic contribution.** Described below. |

---

## Why a graph?

Rules and probes judge **one resource at a time**. Real incidents are
**combinations**: an internet-open security group is a finding; a database with
a plaintext password is a finding; but the *database behind that security
group* is a different and worse thing, and no single-resource check can see it
because the two facts live on different resources.

Terraform plans already contain the structure: the `configuration` section
records which resource references which (`vpc_security_group_ids`, `subnet_id`,
`bucket`, ...). The project previously ignored it.

## The algorithm

Input: the planned resources, the dependency edges from the plan, and the
**Layer-1 findings** (used as evidence, not recomputed).

1. **Build the graph.** Nodes = resources; edges = references; undirected
   (exposure flows both ways along a link). Shared hubs (resource groups) are
   removed, otherwise everything looks connected to everything.
2. **Turn evidence into signals.**
   - *Exposure* `e` comes from findings of exposure rules:
     open ingress 0.90, anonymous access 0.90, public network access 0.60,
     public IP 0.55; plus attribute signals such as an all-IPv4 database
     firewall range (0.95).
   - *Weakness* `W` of a node = noisy-OR of its own findings' severity weights
     (critical 0.80, high 0.60, medium 0.35, low 0.15), counting only security,
     identity and reliability pillars (missing tags are not exploitability).
   - *Asset value* `A` by kind (database/secret store 1.0, storage 0.9,
     compute 0.8, ...) and environment tag (prod x1.15, dev x0.8).
3. **Propagate exposure with distance decay** (BFS, at most 3 hops):

   `E_j = 1 - prod_i (1 - e_i * 0.75^d(i, j))`

4. **Score risk:** `R_j = E_j * W_j * A_j`.
5. **Report only the uplift from the graph.** Compute the risk the node would
   have from its own exposure alone, `R_alone`. A finding is raised only if
   `R_j >= 0.35` **and** `R_j - R_alone >= 0.10`, so Layer 2b never repeats
   what single-resource layers already said.
6. **Explain with the actual path**, the contributing evidence and the numbers.
   Confidence is derived from the score (not a constant). Severity comes from
   the score (>= 0.60 high, >= 0.45 medium).

## Example (real plan, AWS module, no mocks)

```
Exposure path aws_security_group.web -> aws_db_instance.main (1 hop).
aws_security_group.web carries exposure (Firewall rule exposes a port to the
entire internet) that reaches aws_db_instance.main, which already has these
weaknesses: Credential written in plain text; Database has no backup
retention; Data service not encrypted with a customer-managed key.
Propagated risk is 0.67 (reachable exposure 0.90 x weakness 0.93 x asset
value 0.80); on its own aws_db_instance.main would score 0.52, so the
connection adds 0.15.
```

The Azure module gives the analogous result: the all-IPv4 SQL firewall rule
reaches the SQL server (risk 0.79, connection adds 0.25).

## Properties worth stating

- **Evidence-based, not mapped:** numbers are derived from plan evidence and
  graph distance; nothing is a fixed per-check constant.
- **Compositional:** it consumes Layer-1 output, so every new rule
  automatically strengthens the graph reasoning.
- **Explainable and deterministic:** same plan, same score; the path is shown.
- **Cheap:** pure Python, milliseconds, no model, no cost.
- **Guardrailed like the rest of Layer 2:** advisory by default, never invents
  a resource, never repeats a rule, switched off with the reasoning layer.
- **Side benefit:** the same edges now link diagnostic settings to the
  resources they cover exactly, replacing the name-matching heuristic.

## Honest limits (say these first)

- **Weights and thresholds are design choices** (a documented prior), not
  learned from data. They are tunable in `graph.py` and should be calibrated
  on an independent set.
- **It needs a real plan.** Hand-written fixtures carry no `configuration`
  block, so they have no edges and Layer 2b stays silent on them. The
  benchmark numbers (37/42 -> 42/42) therefore do not include it. Its evidence
  is the real-plan runs, which is a small sample (AWS: 1 compound finding;
  Azure: 1; GCP: 0, because that module has no linked resources).
- **Only references Terraform records are edges.** Network reachability that
  is not expressed as a reference (e.g. same VPC by convention) is invisible.
- **Not yet evaluated for precision on independent code.**

Tests: `tests/test_graph.py` (9 tests) cover propagation, no-edge silence,
hub removal, distance decay, clean targets, governance-noise exclusion, the
uplift gate, edge extraction and engine integration.
