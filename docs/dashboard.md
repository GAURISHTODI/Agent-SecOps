# The Demo Dashboard

A local web UI for showing the project to a room. It is **not** part of the gate — in the pipeline the gate is a CLI whose exit code decides whether `terraform apply` runs. The dashboard exists because a verdict is easier to believe when you can see it change.

---

## Run it

```bash
python -m dashboard.server
```

Opens `http://localhost:8000` in your browser. `Ctrl+C` stops it.

| Flag | Use |
|---|---|
| `--port 8001` | Port 8000 is already taken |
| `--no-browser` | Do not open a browser automatically |
| `--host 0.0.0.0` | Let another device on the same wifi reach it (useful for a projector laptop) |

There is nothing else to install. It uses the same `requirements.txt` as the gate.

---

## How it is built, and why

| Half | Technology | File |
|---|---|---|
| Backend | Python standard library `http.server` | `dashboard/server.py` |
| Frontend | React 18 (from CDN) + JSX compiled in the browser | `dashboard/static/` |

**No `npm install`, no `node_modules`, no build step.** One command starts everything.

That is a deliberate trade-off, and it is worth being able to defend:

> "A production React app would use Vite and compile JSX ahead of time — it is faster and it works offline. We chose in-browser compilation because the dashboard is a demo artifact, and the cost of a build toolchain is one more thing that can break on an unfamiliar machine five minutes before a review. The gate itself, which is the actual deliverable, has no such dependency at all."

The backend adds **zero** dependencies to the project. It imports the same `agent.engine` the CLI imports, so every number on screen is produced by the code being assessed — the dashboard cannot show a result the CLI would not.

### API

| Endpoint | Returns |
|---|---|
| `GET /api/plans` | The fixture plans available in the dropdown |
| `GET /api/evaluate?plan=<file>&reasoner=<offline\|none>` | A full gate result |
| `POST /api/evaluate` | Same, for a plan JSON uploaded from the browser |
| `GET /api/benchmark` | The detection benchmark, run live |
| `GET /api/rules` | The rule catalogue with each rule's framework rationale |

The `plan` parameter is validated against the fixtures directory, so a crafted request cannot read arbitrary files off the machine.

---

## The three tabs

### Gate

The main view.

- **Verdict banner** — PASS / REMEDIATE / BLOCK, with the **exit code** shown beside it, because the exit code is what the pipeline actually acts on.
- **Stat tiles** — resources evaluated, active findings, how many came from rules, how many from reasoning, gate latency.
- **"Which layer found what"** — a single stacked bar. Blue is deterministic rules, orange is the reasoning layer.
- **Violations by framework pillar** — one bar per CAF/WAF pillar.
- **Findings by severity** — critical through info, in status colours.
- **Findings** — grouped by resource, expandable, each naming its pillar and carrying a copy-pasteable HCL fix.

You can also **upload your own `plan.json`** — generate one with `terraform show -json tf.plan > plan.json` and drop it in.

### Benchmark

Runs `scripts/benchmark.py` live and renders it: 42 seeded violations across three clouds, detection with rules alone versus rules plus reasoning, per plan, plus the false-positive count on the compliant module.

### Rules

All 22 rules with the framework rationale for each — the answer to "where does this rule come from?"

---

## The demo sequence

Rehearse this. It takes about 90 seconds and it makes the argument on its own.

**1. Start with a pass.**
Select *"Azure — compliant workload"*. Green **PASS**, exit code 0, no findings.

> "This is a well-built module. The gate lets it through, and the pipeline would proceed to `terraform apply`."

**2. Now break it.**
Select *"Azure — seeded misconfigurations"*. Red **BLOCK**, exit code 2, 48 findings across 9 pillars.

> "Exit code 2 stops the pipeline. Not one of these resources gets created — no cost, no exposure. Every finding names the pillar it violates and gives the fix."

Expand one finding — the hardcoded database password is a good one.

**3. The moment that matters: toggle the reasoning layer off.**

Watch the orange segment disappear from the layer chart, and the reasoning findings vanish from the list. Turn it back on and they return.

> "Everything orange is a violation that **no hand-written rule catches** — it comes from reasoning over CAF and WAF guidance that was never turned into a rule. That is what separates this from Checkov, and you are watching it appear and disappear."

**4. Prove it is cloud-agnostic.**
Switch to *AWS*, then *GCP*. Same rules, same verdict logic, different provider.

> "One rule is written against a canonical resource kind, so it works on all three clouds. We did not write three rule sets."

**5. Show the measurement.**
Open the **Benchmark** tab.

> "42 seeded violations, hand-labelled. Deterministic rules alone catch 88% — roughly what a static scanner gives you. With the reasoning layer, 100%. Five violations are recoverable only by reasoning. And zero false positives on the compliant module, which matters just as much: a gate that fails clean code gets switched off by the team that owns it."

---

## Design notes

Worth knowing if you are asked why it looks the way it does.

**Charts are hand-rolled inline SVG**, not a charting library — same reasoning as the rest of the project: fewer dependencies, nothing to explain away.

**Colour is assigned by the job it does, not by taste:**

- The **pillar chart** is one series over unordered categories, so every bar is the same blue. Colouring each bar differently would spend the only free visual channel on information the bar length already carries.
- The **severity chart** is a *status* encoding, so it uses reserved status colours (critical/serious/warning) that are never reused for anything else — and every bar carries a visible text label, so colour never carries the meaning alone. Same for the severity chips in the findings list.
- The **layer split** is two identities — rules and reasoning — so it uses the first two categorical slots, which are validated as distinguishable under colour-vision deficiency.

**Every chart has a "Show data table" fallback**, and the whole UI has a light and a dark theme with its own validated colour steps rather than an automatic inversion.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Could not load React from the CDN" | The page needs internet on first load. Connect and refresh; the browser caches it afterwards. The gate itself works offline — use the CLI. |
| `Could not start on port 8000` | Another program is using it. `python -m dashboard.server --port 8001` |
| Browser does not open | Open `http://localhost:8000` yourself, or drop `--no-browser`. |
| Blank page | Open the browser console (F12). Nine times out of ten it is the CDN. |
| Benchmark tab spins forever | Check the terminal running the server for a Python traceback. |
| Uploaded plan rejected | It must be `terraform show -json` output — the file needs a `resource_changes` key. A raw `.tfplan` will not work. |
