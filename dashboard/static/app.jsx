/* ---------------------------------------------------------------------
   Agent SecOps dashboard.

   A presentation layer over the same engine the CLI drives. Nothing here
   makes a compliance decision -- it renders one. Every number on screen
   comes from `agent/engine.py` through `dashboard/server.py`.

   Charts are hand-rolled inline SVG rather than a charting library, for
   the same reason the agent has almost no dependencies: fewer moving
   parts to install, and nothing to explain away in a viva.
   --------------------------------------------------------------------- */

const { useState, useEffect, useMemo, useCallback, useRef } = React;

/* --- small helpers --------------------------------------------------- */

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];
const SEV_VAR = {
  critical: "var(--sev-critical)",
  high: "var(--sev-high)",
  medium: "var(--sev-medium)",
  low: "var(--sev-low)",
  info: "var(--sev-info)",
};

const VERDICT_COPY = {
  pass: {
    icon: "✓",
    label: "PASS",
    detail: "Deployment approved — terraform apply may proceed.",
    exit: 0,
  },
  remediate: {
    icon: "⚠",
    label: "REMEDIATE",
    detail: "Allowed with required follow-up — fix the findings below.",
    exit: 1,
  },
  block: {
    icon: "✕",
    label: "BLOCK",
    detail: "Deployment halted — nothing reaches the cloud until this is fixed.",
    exit: 2,
  },
};

function useTheme() {
  const [theme, setTheme] = useState(() => {
    // A blocked/private context throws on access, so never read it bare.
    try { return localStorage.getItem("secops-theme") || "system"; }
    catch (e) { return "system"; }
  });
  useEffect(() => {
    if (theme === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("secops-theme", theme); } catch (e) { /* private mode */ }
  }, [theme]);
  return [theme, setTheme];
}

/* Shared tooltip: an HTML chart is interactive by default, so every chart
   ships hover rather than relying on axis reading alone. */
function useTooltip() {
  const [tip, setTip] = useState(null);
  const show = useCallback((evt, content) => {
    setTip({ x: evt.clientX, y: evt.clientY, content });
  }, []);
  const hide = useCallback(() => setTip(null), []);
  const node = tip
    ? <div className="tooltip" style={{ left: tip.x + 14, top: tip.y + 14 }}>{tip.content}</div>
    : null;
  return { show, hide, node };
}

/* --- charts ---------------------------------------------------------- */

/*
  One horizontal bar chart component, used for both "by pillar" and
  "by severity".

  Colour rule applied here: the pillar chart is ONE series over nominal
  categories, so every bar takes categorical slot 1 -- colouring each bar
  differently would burn the only free channel on information the bar
  length already carries. The severity chart is a *status* encoding, so it
  uses the reserved status tokens, and every bar is directly labelled so
  the colour never carries the meaning alone.
*/
function BarChart({ rows, colorOf, tooltip, valueSuffix }) {
  const rowH = 26;
  const gap = 7;
  const labelW = 168;
  const padR = 46;
  const height = rows.length * (rowH + gap);
  const max = Math.max(1, ...rows.map((r) => r.value));
  const [w, setW] = useState(560);
  const box = useRef(null);

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver((entries) => {
      setW(Math.max(360, entries[0].contentRect.width));
    });
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const plotW = Math.max(60, w - labelW - padR);

  if (!rows.length) return <div className="empty">No findings to chart.</div>;

  return (
    <div className="chart" ref={box}>
      <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} role="img">
        {/* Recessive hairline grid at quarter steps -- no dashes. */}
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line
            key={f}
            className="gridline"
            x1={labelW + plotW * f} x2={labelW + plotW * f}
            y1={0} y2={height - gap}
          />
        ))}
        <line className="baseline" x1={labelW} x2={labelW} y1={0} y2={height - gap} />

        {rows.map((r, i) => {
          const y = i * (rowH + gap);
          const bw = Math.max(2, (r.value / max) * plotW);
          return (
            <g key={r.label}
               onMouseMove={(e) => tooltip.show(e,
                 <React.Fragment>
                   <div className="t-title">{r.label}</div>
                   <div className="t-row">{r.value} {valueSuffix || "finding(s)"}</div>
                   {r.note && <div className="t-row">{r.note}</div>}
                 </React.Fragment>)}
               onMouseLeave={tooltip.hide}>
              {/* full-width hit target, bigger than the mark itself */}
              <rect x={0} y={y} width={w} height={rowH} fill="transparent" />
              <text className="cat-label" x={labelW - 10} y={y + rowH / 2 + 4} textAnchor="end">
                {r.label}
              </text>
              {/* 4px rounded data-end, anchored flat to the baseline */}
              <path
                className="bar"
                d={roundedRightBar(labelW, y + 4, bw, rowH - 8, 4)}
                fill={colorOf(r)}
              />
              <text className="value-label" x={labelW + bw + 8} y={y + rowH / 2 + 4}>
                {r.value}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* Bar path with only the far end rounded, so the bar stays visually
   anchored to the axis instead of floating. */
function roundedRightBar(x, y, w, h, r) {
  const rr = Math.min(r, w, h / 2);
  return [
    `M ${x} ${y}`,
    `H ${x + w - rr}`,
    `A ${rr} ${rr} 0 0 1 ${x + w} ${y + rr}`,
    `V ${y + h - rr}`,
    `A ${rr} ${rr} 0 0 1 ${x + w - rr} ${y + h}`,
    `H ${x}`,
    "Z",
  ].join(" ");
}

/* A single stacked bar showing which layer produced the findings.
   Two segments separated by a 2px surface gap. This is the research
   claim rendered: everything orange is a finding no deterministic rule
   made. */
function LayerSplit({ rules, reasoning, tooltip }) {
  // Every hook runs before any early return: a compliant plan has zero
  // findings, and bailing out above the hooks would change hook order
  // between renders and crash React.
  const h = 30;
  const [w, setW] = useState(520);
  const box = useRef(null);
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver((e) => setW(Math.max(260, e[0].contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const total = rules + reasoning;
  if (!total) return <div className="empty">No findings in this plan.</div>;

  const gapPx = 2;
  const rw = Math.max(0, (rules / total) * (w - gapPx));
  const ew = Math.max(0, (reasoning / total) * (w - gapPx));

  return (
    <div className="chart" ref={box}>
      <svg width="100%" height={h + 22} viewBox={`0 0 ${w} ${h + 22}`} role="img">
        {rules > 0 && (
          <g onMouseMove={(e) => tooltip.show(e,
              <React.Fragment>
                <div className="t-title">Deterministic rules</div>
                <div className="t-row">{rules} finding(s) &middot; confidence 1.0</div>
              </React.Fragment>)}
             onMouseLeave={tooltip.hide}>
            <path d={roundedBothEnds(0, 0, rw, h, 4)} fill="var(--series-1)" />
            {rw > 42 && <text className="value-label" x={10} y={h / 2 + 4} fill="#fff">{rules}</text>}
          </g>
        )}
        {reasoning > 0 && (
          <g onMouseMove={(e) => tooltip.show(e,
              <React.Fragment>
                <div className="t-title">Reasoning layer</div>
                <div className="t-row">{reasoning} finding(s) no rule encodes</div>
              </React.Fragment>)}
             onMouseLeave={tooltip.hide}>
            <path d={roundedBothEnds(rw + gapPx, 0, ew, h, 4)} fill="var(--series-2)" />
            {ew > 42 && <text className="value-label" x={rw + gapPx + 10} y={h / 2 + 4} fill="#fff">{reasoning}</text>}
          </g>
        )}
      </svg>
      <div className="legend">
        <span className="item">
          <span className="swatch" style={{ background: "var(--series-1)" }} />
          Deterministic rules &mdash; {rules}
        </span>
        <span className="item">
          <span className="swatch" style={{ background: "var(--series-2)" }} />
          Reasoning layer &mdash; {reasoning}
        </span>
      </div>
    </div>
  );
}

function roundedBothEnds(x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  if (w <= 0) return "";
  return [
    `M ${x + rr} ${y}`, `H ${x + w - rr}`,
    `A ${rr} ${rr} 0 0 1 ${x + w} ${y + rr}`,
    `V ${y + h - rr}`,
    `A ${rr} ${rr} 0 0 1 ${x + w - rr} ${y + h}`,
    `H ${x + rr}`,
    `A ${rr} ${rr} 0 0 1 ${x} ${y + h - rr}`,
    `V ${y + rr}`,
    `A ${rr} ${rr} 0 0 1 ${x + rr} ${y}`, "Z",
  ].join(" ");
}

/* Every chart has a table equivalent -- the accessibility fallback. */
function TableView({ rows, headers, valueSuffix }) {
  const [open, setOpen] = useState(false);
  return (
    <React.Fragment>
      <button className="table-toggle" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Show"} data table
      </button>
      {open && (
        <table className="data">
          <thead>
            <tr>{headers.map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td>{r.label}</td>
                <td className="num">{r.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </React.Fragment>
  );
}

/* --- findings -------------------------------------------------------- */

function Finding({ f }) {
  return (
    <details className="finding">
      <summary>
        <span className="chevron">&#9654;</span>
        <span className={"chip " + f.severity}>{f.severity}</span>
        <span className="f-title">
          <div>{f.title}</div>
          <div className="f-meta">
            <code>{f.rule_id}</code> &middot; {f.pillar}
            {f.source === "reasoner" &&
              ` · confidence ${Math.round(f.confidence * 100)}%`}
          </div>
        </span>
        <span className={"tag " + (f.source === "rules" ? "rules" : "reasoner")}>
          {f.source === "rules" ? "rule" : "reasoning"}
        </span>
      </summary>
      <div className="body">
        <p>{f.explanation}</p>
        <p><strong>Fix:</strong> {f.remediation}</p>
        {f.terraform_fix && (
          <React.Fragment>
            <div className="fix-label">Terraform</div>
            <pre className="hcl">{f.terraform_fix}</pre>
          </React.Fragment>
        )}
      </div>
    </details>
  );
}

function FindingsPanel({ result }) {
  const active = result.findings.filter((f) => !f.waived);
  const waived = result.findings.filter((f) => f.waived);
  const kindOf = useMemo(() => {
    const m = {};
    (result.resources || []).forEach((r) => { m[r.address] = r; });
    return m;
  }, [result]);

  const grouped = useMemo(() => {
    const g = {};
    active.forEach((f) => {
      (g[f.resource] = g[f.resource] || []).push(f);
    });
    return Object.entries(g);
  }, [result]);

  return (
    <div className="panel">
      <h2>Findings</h2>
      <p className="panel-sub">
        Grouped by resource, worst first. Each names the CAF or WAF pillar it
        violates and carries a copy-pasteable fix.
      </p>

      {!active.length && (
        <div className="empty">
          No CAF or WAF violations in this plan. This is what a passing gate
          looks like.
        </div>
      )}

      {grouped.map(([address, items]) => (
        <div className="finding-group" key={address}>
          <div className="addr">
            {address}
            {kindOf[address] && (
              <span className="kindtag">
                {kindOf[address].cloud} &middot; {kindOf[address].kind} &middot;{" "}
                {kindOf[address].action}
              </span>
            )}
          </div>
          {items.map((f, i) => <Finding key={f.rule_id + i} f={f} />)}
        </div>
      ))}

      {waived.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: "pointer", color: "var(--text-secondary)", fontSize: 13 }}>
            {waived.length} waived finding(s)
          </summary>
          <div style={{ marginTop: 10 }}>
            {waived.map((f, i) => (
              <div key={i} style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 5 }}>
                <code>{f.rule_id}</code> on <code>{f.resource}</code> &mdash;{" "}
                {f.waiver_reason}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/* --- benchmark tab --------------------------------------------------- */

function BenchmarkTab({ tooltip }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch("/api/benchmark")
      .then((r) => r.json())
      .then((d) => (d.error ? setErr(d.error) : setData(d)))
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="error-box"><strong>Benchmark failed.</strong> {err}</div>;
  if (!data) return <div className="spinner">Running the benchmark&hellip;</div>;

  const t = data.totals;

  return (
    <React.Fragment>
      <div className="tiles">
        <div className="tile">
          <div className="value">{t.seeded_violations}</div>
          <div className="name">Seeded violations</div>
          <div className="note">Azure + AWS + GCP, hand-labelled</div>
        </div>
        <div className="tile accent-1">
          <div className="value">{Math.round(t.recall_rules_only * 100)}%</div>
          <div className="name">Rules alone</div>
          <div className="note">{t.detected_rules_only} detected</div>
        </div>
        <div className="tile accent-2">
          <div className="value">{Math.round(t.recall_with_reasoning * 100)}%</div>
          <div className="name">With reasoning</div>
          <div className="note">{t.detected_with_reasoning} detected</div>
        </div>
        <div className="tile accent-2">
          <div className="value">+{t.reasoning_uplift}</div>
          <div className="name">Recovered by reasoning</div>
          <div className="note">the research claim</div>
        </div>
        <div className="tile">
          <div className="value">{t.false_positives_on_clean_plan}</div>
          <div className="name">False positives</div>
          <div className="note">on the compliant module</div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <h2>Detection per plan</h2>
        <p className="panel-sub">
          Same fixtures, run twice: once with the reasoning layer disabled, once
          with it on. The gap between the two bars is what no hand-written rule
          catches.
        </p>
        {data.suites.map((s) => (
          <div key={s.plan} style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12.5, marginBottom: 6, color: "var(--text-secondary)" }}>
              <code>{s.plan}</code> &mdash; {s.seeded} seeded &middot; verdict{" "}
              <strong style={{ color: s.verdict_correct ? "var(--status-good)" : "var(--status-critical)" }}>
                {s.verdict.toUpperCase()}
              </strong>
            </div>
            <BarChart
              rows={[
                { label: "Rules only", value: s.detected_rules_only, series: 1 },
                { label: "With reasoning", value: s.detected_with_reasoning, series: 2 },
              ]}
              colorOf={(r) => (r.series === 1 ? "var(--series-1)" : "var(--series-2)")}
              tooltip={tooltip}
              valueSuffix={"of " + s.seeded + " detected"}
            />
          </div>
        ))}
        <div className="legend">
          <span className="item">
            <span className="swatch" style={{ background: "var(--series-1)" }} />
            Deterministic rules only
          </span>
          <span className="item">
            <span className="swatch" style={{ background: "var(--series-2)" }} />
            Rules + reasoning layer
          </span>
        </div>
      </div>

      <div className="panel">
        <h2>What the reasoning layer recovered</h2>
        <p className="panel-sub">
          Violations visible in CAF/WAF guidance that no deterministic rule
          encodes &mdash; exactly the class a static scanner misses.
        </p>
        {data.suites.every((s) => !s.recovered_by_reasoning.length) ? (
          <div className="empty">Nothing recovered in this run.</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {data.suites.flatMap((s) =>
              s.recovered_by_reasoning.map((issue, i) => (
                <li key={s.plan + i} style={{ marginBottom: 4 }}>
                  {issue}{" "}
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    ({s.plan.replace(".plan.json", "")})
                  </span>
                </li>
              ))
            )}
          </ul>
        )}
      </div>
    </React.Fragment>
  );
}

/* --- rules tab ------------------------------------------------------- */

function RulesTab() {
  const [rules, setRules] = useState(null);
  useEffect(() => {
    fetch("/api/rules").then((r) => r.json()).then((d) => setRules(d.rules));
  }, []);
  if (!rules) return <div className="spinner">Loading the catalogue&hellip;</div>;

  return (
    <div className="panel">
      <h2>Rule catalogue &mdash; {rules.length} rules</h2>
      <p className="panel-sub">
        Every rule names the framework pillar it enforces and states, in prose,
        why the framework requires it. That text is tested: no rule ships
        without it.
      </p>
      {rules.map((r) => (
        <div className="rule-row" key={r.id}>
          <div><code>{r.id}</code></div>
          <div>
            <div>{r.title}</div>
            <div className="why">{r.rationale}</div>
          </div>
          <div style={{ color: "var(--text-secondary)", fontSize: 12 }}>{r.pillar}</div>
          <div><span className={"chip " + r.severity}>{r.severity}</span></div>
        </div>
      ))}
    </div>
  );
}

/* --- gate tab -------------------------------------------------------- */

function GateTab({ result, loading, tooltip }) {
  if (loading) return <div className="spinner">Evaluating the plan&hellip;</div>;
  if (!result) return null;

  const v = VERDICT_COPY[result.verdict];
  const stats = result.stats || {};
  const active = result.findings.filter((f) => !f.waived);

  const pillarRows = Object.entries(stats.by_pillar || {})
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));

  const sevRows = SEVERITY_ORDER
    .filter((s) => (stats.by_severity || {})[s])
    .map((s) => ({ label: s, value: stats.by_severity[s] }));

  return (
    <React.Fragment>
      <div className={"verdict " + result.verdict}>
        <span className="icon" aria-hidden="true">{v.icon}</span>
        <span>
          <div className="label">{v.label}</div>
          <div className="detail">{v.detail}</div>
        </span>
        <span className="exit-code">
          exit code
          <code>{v.exit}</code>
        </span>
      </div>

      <div className="tiles">
        <div className="tile">
          <div className="value">{result.resources_evaluated}</div>
          <div className="name">Resources evaluated</div>
          <div className="note">{(stats.providers || []).join(", ") || "—"}</div>
        </div>
        <div className="tile">
          <div className="value">{active.length}</div>
          <div className="name">Active findings</div>
          <div className="note">{stats.findings_waived || 0} waived</div>
        </div>
        <div className="tile accent-1">
          <div className="value">{stats.findings_from_rules || 0}</div>
          <div className="name">From rules</div>
          <div className="note">confidence 1.0</div>
        </div>
        <div className="tile accent-2">
          <div className="value">{stats.findings_from_reasoner || 0}</div>
          <div className="name">From reasoning</div>
          <div className="note">{result.reasoner} layer</div>
        </div>
        <div className="tile">
          <div className="value">{result.duration_ms}<span style={{ fontSize: 15 }}>ms</span></div>
          <div className="name">Gate latency</div>
          <div className="note">{stats.rules_evaluated || 0} rules run</div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <h2>Which layer found what</h2>
        <p className="panel-sub">
          Turn the reasoning layer off in the controls above and watch the
          orange segment disappear &mdash; those are findings no hand-written
          rule produces.
        </p>
        <LayerSplit
          rules={stats.findings_from_rules || 0}
          reasoning={stats.findings_from_reasoner || 0}
          tooltip={tooltip}
        />
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>Violations by framework pillar</h2>
          <p className="panel-sub">
            Every finding maps to exactly one CAF or WAF pillar &mdash; enforced
            by the type system, not by convention.
          </p>
          <BarChart
            rows={pillarRows}
            colorOf={() => "var(--series-1)"}
            tooltip={tooltip}
          />
          <TableView rows={pillarRows} headers={["Pillar", "Findings"]} />
        </div>

        <div className="panel">
          <h2>Findings by severity</h2>
          <p className="panel-sub">
            Anything at or above <strong>high</strong> blocks the pipeline, per{" "}
            <code>policies/policy.yaml</code>.
          </p>
          <BarChart
            rows={sevRows}
            colorOf={(r) => SEV_VAR[r.label]}
            tooltip={tooltip}
          />
          <TableView rows={sevRows} headers={["Severity", "Findings"]} />
        </div>
      </div>

      <FindingsPanel result={result} />
    </React.Fragment>
  );
}

/* --- app shell ------------------------------------------------------- */

function App() {
  const [theme, setTheme] = useTheme();
  const [plans, setPlans] = useState([]);
  const [plan, setPlan] = useState("azure_noncompliant.plan.json");
  const [reasoning, setReasoning] = useState(true);
  const [tab, setTab] = useState("gate");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const tooltip = useTooltip();

  useEffect(() => {
    fetch("/api/plans")
      .then((r) => r.json())
      .then((d) => setPlans(d.plans || []))
      .catch(() => setPlans([]));
  }, []);

  const evaluate = useCallback(() => {
    setLoading(true);
    setError(null);
    const reasoner = reasoning ? "offline" : "none";
    fetch(`/api/evaluate?plan=${encodeURIComponent(plan)}&reasoner=${reasoner}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.error) { setError(d.error); setResult(null); }
        else setResult(d);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [plan, reasoning]);

  useEffect(() => { if (tab === "gate") evaluate(); }, [evaluate, tab]);

  const onUpload = (evt) => {
    const file = evt.target.files && evt.target.files[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    file.text().then((text) =>
      fetch(`/api/evaluate?reasoner=${reasoning ? "offline" : "none"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: text,
      })
        .then((r) => r.json())
        .then((d) => {
          if (d.error) { setError(d.error); setResult(null); }
          else { setResult(d); setTab("gate"); }
        })
    ).catch((e) => setError(String(e))).finally(() => setLoading(false));
    evt.target.value = "";
  };

  return (
    <div className="shell">
      <div className="masthead">
        <h1>Agent SecOps</h1>
        <span className="sub">CAF/WAF compliance gate for Terraform in CI/CD</span>
        <span className="spacer" />
        <button
          className="theme-toggle"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </div>
      <p className="tagline">
        This is the same engine the pipeline runs. It reads a <code>terraform plan</code>{" "}
        JSON file, judges every proposed resource against Cloud Adoption Framework
        governance and Well-Architected Framework pillars, and returns a verdict
        &mdash; before any resource is created.
      </p>

      <div className="controls">
        <div className="control">
          <label htmlFor="plan-select">Plan</label>
          <select
            id="plan-select"
            value={plan}
            onChange={(e) => { setPlan(e.target.value); setTab("gate"); }}
          >
            {plans.map((p) => (
              <option key={p.file} value={p.file}>{p.label}</option>
            ))}
          </select>
        </div>

        <label className="switch">
          <input
            type="checkbox"
            checked={reasoning}
            onChange={(e) => setReasoning(e.target.checked)}
          />
          <span className="track"><span className="thumb" /></span>
          <span className="switch-label">Reasoning layer</span>
        </label>

        <label className="file-btn">
          Upload a plan.json
          <input type="file" accept=".json,application/json" onChange={onUpload} />
        </label>

        <div className="tabs" role="tablist">
          {[["gate", "Gate"], ["benchmark", "Benchmark"], ["rules", "Rules"]].map(
            ([id, label]) => (
              <button
                key={id}
                className="tab"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            )
          )}
        </div>
      </div>

      {error && (
        <div className="error-box">
          <strong>Could not evaluate that plan.</strong>
          <div style={{ marginTop: 4 }}>{error}</div>
        </div>
      )}

      {tab === "gate" && <GateTab result={result} loading={loading} tooltip={tooltip} />}
      {tab === "benchmark" && <BenchmarkTab tooltip={tooltip} />}
      {tab === "rules" && <RulesTab />}

      <p className="footnote">
        Agent SecOps &middot; Project 19727UG01 &middot; The dashboard is a
        presentation layer; in the real pipeline the gate is a CLI whose exit
        code decides whether <code>terraform apply</code> runs.
      </p>

      {tooltip.node}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
