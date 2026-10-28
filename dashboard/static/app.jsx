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
    const forced = new URLSearchParams(window.location.search).get("theme");
    if (forced === "light" || forced === "dark") return forced;
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

/* Stages shown while the display is paced. Timings are the engine's own
   measurements, read from the finished result. */
function stageList(d) {
  const st = d.stats || {};
  const ms = st.stage_ms || {};
  const reasoningOn = st.graph_nodes !== undefined;
  return [
    { name: "Parse plan", note: d.resources_evaluated + " resource(s) mapped to canonical kinds", ms: null },
    { name: "Layer 1 · deterministic rules",
      note: (st.rules_evaluated || 0) + " rules checked → " + (st.findings_from_rules || 0) + " finding(s)",
      ms: ms.layer1_rules },
    { name: "Layer 2 · reasoning probes",
      note: reasoningOn
        ? ((st.findings_from_reasoner || 0) - (st.findings_from_graph || 0)) + " finding(s)"
        : "switched off",
      ms: ms.layer2_reasoning },
    { name: "Layer 2b · dependency-graph risk propagation",
      note: reasoningOn
        ? st.graph_nodes + " nodes, " + st.graph_edges + " edges → " + (st.findings_from_graph || 0) + " compound-risk finding(s)"
        : "switched off", ms: null },
    { name: "Layer 3 · policy & waivers", note: "thresholds and expiring waivers applied", ms: ms.layer3_policy },
    { name: "Verdict", note: String(d.verdict).toUpperCase(), ms: null },
  ];
}

/* Reveal the stages one by one (about 1 s each). Resolves when finished. */
function stepThrough(d, setPacing, stillCurrent) {
  const stages = stageList(d);
  return new Promise((resolve) => {
    let step = 0;
    setPacing({ step, stages, d });
    const tick = () => {
      if (!stillCurrent()) return resolve();
      step += 1;
      setPacing({ step, stages, d });
      if (step >= stages.length) setTimeout(resolve, 600);
      else setTimeout(tick, 1000);
    };
    setTimeout(tick, 900);
  });
}

function PacingPanel({ pacing }) {
  const { step, stages, d } = pacing;
  return (
    <div className="panel">
      <h2>Running the gate&hellip;</h2>
      <p className="panel-sub">
        <strong>Presentation pacing is on:</strong> the display steps through the
        stages slowly so each one can be explained. The engine itself finished
        in <strong>{d.duration_ms} ms</strong>; each stage's real measured time
        appears as it completes. Switch pacing off above to see it at full speed.
      </p>
      <ol className="trace">
        {stages.map((st, i) => {
          const done = i < step;
          const active = i === step;
          return (
            <li key={i} className={done ? "ok" : active ? "active" : "pending"}>
              <span className="dot">{done ? "✓" : active ? "…" : "·"}</span>
              <span className="t-name">{st.name}</span>
              <span className="t-note">{done || active ? st.note : ""}</span>
              <span className="t-ms">{done && st.ms != null ? st.ms + " ms" : ""}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function GateTab({ result, loading, tooltip, steps, pacing }) {
  if (loading && pacing) return <PacingPanel pacing={pacing} />;
  if (loading) return <div className="spinner">Evaluating the plan&hellip;</div>;
  if (!result) {
    return (
      <div className="empty">
        Choose a plan above, upload or drop a <code>plan.json</code>, paste one, or
        run a real <code>terraform plan</code>.
      </div>
    );
  }

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

      <SourceBar result={result} />
      <ExportBar result={result} />
      <PipelineSteps steps={steps} />
      <PipelineTrace result={result} steps={steps} />
      <GraphPanel key={result.generated_at + result.plan_name} result={result} />

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

      <ResourceTable result={result} />
      <FindingsPanel result={result} />
    </React.Fragment>
  );
}

/* --- evidence panels: proof that the plan was really processed --------- */

function shortHash(h) { return h ? h.slice(0, 12) : "n/a"; }

/* Where the result came from, and when. Without this a result looks
   identical whether it was just computed or preloaded. */
function SourceBar({ result }) {
  return (
    <div className="source-bar">
      <span><strong>Plan</strong> <code>{result.plan_name}</code></span>
      <span><strong>Source</strong> {result.source}</span>
      <span title="SHA-256 of the exact bytes that were evaluated">
        <strong>SHA-256</strong> <code>{shortHash(result.plan_sha256)}</code>
      </span>
      <span><strong>Evaluated</strong> {new Date(result.generated_at).toLocaleTimeString()}</span>
      <span><strong>Terraform</strong> {result.terraform_version || "n/a"}</span>
    </div>
  );
}

/* Measured wall time per layer, straight from the engine. */
function PipelineTrace({ result, steps }) {
  const s = (result.stats || {}).stage_ms || {};
  const stages = [
    ...(steps || []).filter((x) => x.name !== "agent gate").map((x) => ({
      name: x.name, ms: x.ms, ok: x.ok, note: "real terraform CLI",
    })),
    { name: "Parse plan", ms: null, ok: true,
      note: result.resources_evaluated + " resource(s) normalised" },
    { name: "Layer 1 · deterministic rules", ms: s.layer1_rules, ok: true,
      note: ((result.stats || {}).rules_evaluated || 0) + " rules → " +
            ((result.stats || {}).findings_from_rules || 0) + " findings" },
    { name: "Layer 2 · reasoning (" + result.reasoner + ")", ms: s.layer2_reasoning, ok: true,
      note: (((result.stats || {}).findings_from_reasoner || 0) -
             ((result.stats || {}).findings_from_graph || 0)) + " findings" },
    ...((result.stats || {}).graph_nodes === undefined ? [] : [{
      name: "Layer 2b · dependency-graph risk propagation", ms: null, ok: true,
      note: (result.stats.graph_nodes) + " nodes, " + (result.stats.graph_edges) +
            " edges → " + (result.stats.findings_from_graph || 0) + " compound-risk finding(s)",
    }]),
    { name: "Layer 3 · policy & waivers", ms: s.layer3_policy, ok: true,
      note: "verdict " + result.verdict.toUpperCase() },
  ];
  return (
    <div className="panel" style={{ marginBottom: 14 }}>
      <h2>Processing trace</h2>
      <p className="panel-sub">
        Every stage this plan went through, with measured time. These are real
        timings from the engine, not an animation.
      </p>
      <ol className="trace">
        {stages.map((st, i) => (
          <li key={i} className={st.ok ? "ok" : "bad"}>
            <span className="dot">{st.ok ? "✓" : "✕"}</span>
            <span className="t-name">{st.name}</span>
            <span className="t-note">{st.note}</span>
            <span className="t-ms">{st.ms == null ? "" : st.ms + " ms"}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/* Every resource that was parsed, with its canonical kind. Shows the
   multi-cloud normalisation and how many findings each one drew. */
function ResourceTable({ result }) {
  const rows = result.resources || [];
  return (
    <div className="panel" style={{ marginBottom: 14 }}>
      <h2>Resources parsed from the plan</h2>
      <p className="panel-sub">
        Each Terraform resource is mapped to a cloud-agnostic kind, so one rule
        covers Azure, AWS and GCP.
      </p>
      <table className="data">
        <thead>
          <tr><th>Resource</th><th>Cloud</th><th>Canonical kind</th><th>Action</th><th>Findings</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.address}>
              <td><code>{r.address}</code></td>
              <td>{r.cloud}</td>
              <td>{r.kind}</td>
              <td>{r.action}</td>
              <td className="num">{r.findings}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* --- dependency-graph visualisation ------------------------------------ */

const KIND_GLYPH = {
  object_storage: "\u{1FAA3}", managed_database: "\u{1F5C4}️", network_firewall: "\u{1F525}",
  network_public_ip: "\u{1F310}", secret_store: "\u{1F511}", iam_binding: "\u{1F6E1}️",
  compute_instance: "\u{1F5A5}️", container_platform: "☸️", app_hosting: "\u{1F9E9}",
  log_workspace: "\u{1F4C8}", other: "◆",
};
const riskColor = (r) => (r >= 0.45 ? "#ff4d6d" : r >= 0.2 ? "#ffc857" : "#3ddc97");
const GW = 960, GH = 540;

/* Small deterministic force layout: repulsion between all nodes, springs on
   edges, gentle gravity to the centre. No library, no randomness. */
function forceLayout(nodes, edges) {
  const n = nodes.length;
  const idx = {}; nodes.forEach((nd, i) => { idx[nd.id] = i; });
  const p = nodes.map((_, i) => ({
    x: GW / 2 + Math.cos((2 * Math.PI * i) / n) * GH * 0.32,
    y: GH / 2 + Math.sin((2 * Math.PI * i) / n) * GH * 0.32, vx: 0, vy: 0,
  }));
  for (let it = 0; it < 420; it++) {
    const cool = 1 - it / 420;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let dx = p[i].x - p[j].x, dy = p[i].y - p[j].y;
      const d2 = Math.max(dx * dx + dy * dy, 60);
      const f = 52000 / d2, d = Math.sqrt(d2);
      dx = (dx / d) * f; dy = (dy / d) * f;
      p[i].vx += dx; p[i].vy += dy; p[j].vx -= dx; p[j].vy -= dy;
    }
    edges.forEach(([a, b]) => {
      const i = idx[a], j = idx[b];
      if (i === undefined || j === undefined) return;
      const dx = p[j].x - p[i].x, dy = p[j].y - p[i].y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const f = (d - 170) * 0.035;
      p[i].vx += (dx / d) * f; p[i].vy += (dy / d) * f;
      p[j].vx -= (dx / d) * f; p[j].vy -= (dy / d) * f;
    });
    p.forEach((q) => {
      q.vx += (GW / 2 - q.x) * 0.012; q.vy += (GH / 2 - q.y) * 0.012;
      q.x += q.vx * 0.5 * cool; q.y += q.vy * 0.5 * cool; q.vx *= 0.6; q.vy *= 0.6;
      q.x = Math.min(GW - 90, Math.max(90, q.x)); q.y = Math.min(GH - 100, Math.max(80, q.y));
    });
  }
  return p;
}

function GraphPanel({ result }) {
  const model = (result.stats || {}).graph_model;
  const qs = new URLSearchParams(window.location.search);
  // Open by default whenever the plan actually has links to show.
  const [open, setOpen] = useState(
    qs.get("graph") === "open" || qs.get("graph") !== "closed" && !!model && model.edges.length > 0
  );
  const [step, setStep] = useState(parseInt(qs.get("gstep") || "0", 10) || 0);  // 0 = idle
  const [sel, setSel] = useState(null);
  const timer = useRef(null);

  const g = useMemo(() => {
    if (!model || !model.nodes.length) return null;
    const pos = forceLayout(model.nodes, model.edges);
    const idx = {}; model.nodes.forEach((nd, i) => { idx[nd.id] = i; });
    const adj = model.nodes.map(() => []);
    model.edges.forEach(([a, b]) => {
      if (idx[a] !== undefined && idx[b] !== undefined) { adj[idx[a]].push(idx[b]); adj[idx[b]].push(idx[a]); }
    });
    // multi-source BFS: hop distance from the nearest exposure source
    const decay = (model.params || {}).decay || 0.75;
    const dist = model.nodes.map(() => Infinity);
    const arriving = model.nodes.map(() => 0);
    const queue = [];
    model.nodes.forEach((nd, i) => { if (nd.exposure_self >= 0.3) { dist[i] = 0; arriving[i] = nd.exposure_self; queue.push(i); } });
    for (let h = 0; h < queue.length; h++) {
      const u = queue[h];
      adj[u].forEach((v) => {
        if (dist[v] === Infinity) { dist[v] = dist[u] + 1; arriving[v] = arriving[u] * decay; queue.push(v); }
      });
    }
    const maxDist = Math.max(0, ...dist.filter((d) => d !== Infinity));
    const flaggedEdge = {};
    (model.flagged_paths || []).forEach((fp) => {
      for (let i = 0; i + 1 < fp.path.length; i++) flaggedEdge[fp.path[i] + ">" + fp.path[i + 1]] = true;
    });
    return { pos, idx, dist, arriving, maxDist, total: maxDist + 2, flaggedEdge };
  }, [model]);

  useEffect(() => () => clearInterval(timer.current), []);
  if (!model || !g) return null;

  const simulate = () => {
    clearInterval(timer.current);
    setSel(null); setStep(1);
    let s = 1;
    timer.current = setInterval(() => {
      s += 1; setStep(s);
      if (s >= g.total) clearInterval(timer.current);
    }, 1300);
  };
  const reset = () => { clearInterval(timer.current); setStep(0); setSel(null); };

  const hasEdges = model.edges.length > 0;
  const live = step === 0;                       // idle view: flagged paths pulse
  const shown = (i) => step > 0 && g.dist[i] !== Infinity && g.dist[i] + 1 <= step;
  const final = step >= g.total;
  const focus = sel !== null ? model.nodes[g.idx[sel]] : null;
  const short = (nd) => nd.type.replace(/^(azurerm|aws|google)_/, "");

  return (
    <div className="panel graph-panel-wrap">
      <div className="gp-head">
        <div>
          <h2 style={{ margin: 0 }}>Dependency graph &mdash; how risk travels</h2>
          <p className="panel-sub" style={{ margin: "4px 0 0" }}>
            Nodes are the planned resources, links are Terraform references. Exposure spreads along
            the links, weaker at every hop; a node lights up red when the connection adds risk.
          </p>
        </div>
        <button className="primary" onClick={() => setOpen(!open)}>
          {open ? "Hide graph" : "\u{1F578} Show dependency graph"}
        </button>
      </div>

      {!hasEdges && (
        <div className="gp-nolinks">
          <strong>This plan has no resource links to draw.</strong> Hand-written example files carry
          no Terraform configuration block, so there is nothing connected. Choose{" "}
          <em>Real terraform plan &ndash; aws_noncompliant</em> (or <em>noncompliant</em>) in the
          Plan dropdown, or click <em>terraform plan &rarr; gate</em>, to see the graph.
        </div>
      )}

      {open && (
        <div className="graph-stage">
          <div className="gp-bar">
            <button className="primary" onClick={simulate} disabled={!hasEdges}>
              {"▶"} Simulate exposure spread
            </button>
            <button className="gp-ghost" onClick={reset}>{"↺"} Reset</button>
            <span className="gp-step">
              {step === 0 ? "idle: flagged paths pulse" :
               final ? "done: risk scores shown" :
               step === 1 ? "step 1: exposure sources ignite" :
               "step " + step + ": exposure reaches hop " + (step - 1)}
            </span>
            <span className="gp-legend">
              <i style={{ background: "#ff9f1c" }} /> exposed
              <i style={{ background: "#3ddc97" }} /> low risk
              <i style={{ background: "#ffc857" }} /> medium
              <i style={{ background: "#ff4d6d" }} /> high
            </span>
          </div>

          <svg viewBox={"0 0 " + GW + " " + GH} className="gp-svg" role="img">
            <defs>
              <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="5" result="b" />
                <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
              <pattern id="dots" width="28" height="28" patternUnits="userSpaceOnUse">
                <circle cx="2" cy="2" r="1" fill="#1d2747" />
              </pattern>
              <radialGradient id="bgfade" cx="50%" cy="45%" r="75%">
                <stop offset="0%" stopColor="#101a3a" /><stop offset="100%" stopColor="#04060d" />
              </radialGradient>
            </defs>
            <rect width={GW} height={GH} fill="url(#bgfade)" />
            <rect width={GW} height={GH} fill="url(#dots)" />

            {!hasEdges && (
              <text x={GW / 2} y={GH - 22} textAnchor="middle" fill="#8aa0d6" fontSize="14">
                No dependency edges in this plan. Hand-written fixtures carry no configuration
                block; run the real pipeline to see links.
              </text>
            )}

            {model.edges.map(([a, b], k) => {
              const A = g.pos[g.idx[a]], B = g.pos[g.idx[b]];
              if (!A || !B) return null;
              const fwd = g.flaggedEdge[a + ">" + b], back = g.flaggedEdge[b + ">" + a];
              const hot = fwd || back;
              const [s, t] = back ? [B, A] : [A, B];
              const ia = g.idx[a], ib = g.idx[b];
              const simHot = step > 0 && shown(ia) && shown(ib);
              const path = "M" + s.x + " " + s.y + " L" + t.x + " " + t.y;
              return (
                <g key={k}>
                  <line x1={A.x} y1={A.y} x2={B.x} y2={B.y}
                        stroke={hot && live ? "#ff4d6d" : simHot ? "#ff9f1c" : "#34406b"}
                        strokeWidth={hot ? 2.6 : 1.6} opacity={hot || simHot ? 0.95 : 0.7}
                        className={(hot && live) || simHot ? "gp-flow" : ""} />
                  {((hot && live) || simHot) && [0, 0.55, 1.1].map((d) => (
                    <circle key={d} r="4.5" fill={hot ? "#ff8fa3" : "#ffd29a"} filter="url(#glow)">
                      <animateMotion dur="1.7s" begin={d + "s"} repeatCount="indefinite" path={path} />
                    </circle>
                  ))}
                </g>
              );
            })}

            {model.nodes.map((nd, i) => {
              const q = g.pos[i];
              const r = 18 + nd.asset * 13;
              const src = nd.exposure_self >= 0.3;
              const col = riskColor(nd.risk);
              const lit = live ? true : shown(i);
              const ring = nd.flagged && (live || final) ? "#ff4d6d" : col;
              return (
                <g key={nd.id} transform={"translate(" + q.x + "," + q.y + ")"}
                   style={{ cursor: "pointer" }} onClick={() => setSel(nd.id)}
                   opacity={live || lit || g.dist[i] === Infinity ? 1 : 0.55}>
                  {src && lit && <circle r={r + 6} fill="none" stroke="#ff9f1c" strokeWidth="2" className="gp-radar" />}
                  {nd.flagged && (live || final) && <circle r={r + 8} fill="none" stroke="#ff4d6d" strokeWidth="3" className="gp-alarm" />}
                  <circle r={r} fill="#0a1128" stroke={live || final ? ring : lit && src ? "#ff9f1c" : "#46557f"}
                          strokeWidth="3" filter={(live || lit) ? "url(#glow)" : undefined} />
                  <text textAnchor="middle" dy="0.35em" fontSize={r * 0.95}>{KIND_GLYPH[nd.kind] || "◆"}</text>
                  <text y={r + 24} textAnchor="middle" fill="#e6ecff" fontSize="13" fontWeight="600">{nd.label}</text>
                  <text y={r + 38} textAnchor="middle" fill="#7f90c4" fontSize="10.5">{short(nd)}</text>
                  {step > 0 && lit && !final && g.dist[i] !== Infinity && (
                    <g transform={"translate(0," + (-r - 14) + ")"}>
                      <rect x="-34" y="-12" width="68" height="20" rx="10" fill="#2a1a05" stroke="#ff9f1c" />
                      <text textAnchor="middle" dy="0.3em" fill="#ffc46b" fontSize="12">
                        {"exp " + (g.arriving[i]).toFixed(2)}
                      </text>
                    </g>
                  )}
                  {final && (
                    <g transform={"translate(0," + (-r - 14) + ")"}>
                      <rect x="-30" y="-12" width="60" height="20" rx="10" fill="#0a1128" stroke={ring} />
                      <text textAnchor="middle" dy="0.3em" fill={ring} fontSize="12" fontWeight="700">
                        {"R " + nd.risk.toFixed(2)}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>

          <div className="gp-info">
            {focus ? (
              <div className="gp-card">
                <div className="gp-card-title">
                  {(KIND_GLYPH[focus.kind] || "") + " " + focus.id}
                  <span className="gp-tag">{focus.cloud + " · " + focus.kind}</span>
                  {focus.flagged && <span className="gp-tag bad">compound risk</span>}
                </div>
                <div className="gp-metrics">
                  <span>exposure (own) <b>{focus.exposure_self.toFixed(2)}</b></span>
                  <span>exposure (reaching) <b>{focus.exposure_reach.toFixed(2)}</b></span>
                  <span>weakness <b>{focus.weakness.toFixed(2)}</b></span>
                  <span>asset value <b>{focus.asset.toFixed(2)}</b></span>
                  <span>risk <b style={{ color: riskColor(focus.risk) }}>{focus.risk.toFixed(2)}</b></span>
                  <span>risk alone <b>{focus.risk_alone.toFixed(2)}</b></span>
                </div>
                {focus.weaknesses.length > 0 && <div className="gp-line">weaknesses: {focus.weaknesses.join(" · ")}</div>}
                {focus.exposure_why.length > 0 && <div className="gp-line">exposure: {focus.exposure_why.join(" · ")}</div>}
              </div>
            ) : (
              <div className="gp-hint">
                Click any node for its numbers. Risk = reachable exposure {"×"} weakness {"×"} asset value.
                A red ring is high risk on its own (a rule already reports it); only the
                <strong> pulsing alarm ring</strong> marks a compound path the graph found.
              </div>
            )}
            {(model.flagged_paths || []).map((fp, k) => (
              <div className="gp-path" key={k}>
                <span className={"chip " + fp.severity}>{fp.severity}</span>
                <code>{fp.path.join("  →  ")}</code>
                <span>risk {fp.risk.toFixed(2)}, connection adds {fp.uplift.toFixed(2)}</span>
              </div>
            ))}
            {(model.flagged_paths || []).length === 0 && hasEdges && (
              <div className="gp-hint">No compound path in this plan: the links add no extra risk.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* --- exports ---------------------------------------------------------- */

function download(filename, text, mime) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/* A print-optimised report in a new window. The browser's own "Save as PDF"
   produces the file, so there is no PDF library to install. */
function openPrintReport(result) {
  const v = VERDICT_COPY[result.verdict];
  const active = result.findings.filter((f) => !f.waived);
  const stats = result.stats || {};
  const sevColor = { critical: "#a4121b", high: "#c2410c", medium: "#a16207", low: "#1d4ed8", info: "#475569" };
  const rows = active.map((f) => `
    <tr>
      <td><b style="color:${sevColor[f.severity] || "#000"}">${esc(f.severity.toUpperCase())}</b></td>
      <td><code>${esc(f.rule_id)}</code><br>${esc(f.pillar)}</td>
      <td><code>${esc(f.resource)}</code></td>
      <td><b>${esc(f.title)}</b><br>${esc(f.explanation)}<br>
          <i>Fix:</i> ${esc(f.remediation)}
          ${f.terraform_fix ? `<pre>${esc(f.terraform_fix)}</pre>` : ""}</td>
      <td>${f.source === "rules" ? "rule" : "reasoning " + Math.round(f.confidence * 100) + "%"}</td>
    </tr>`).join("");
  const pillars = Object.entries(stats.by_pillar || {})
    .map(([k, n]) => `<li>${esc(k)}: <b>${n}</b></li>`).join("");

  const html = `<!doctype html><html><head><meta charset="utf-8">
<title>Agent SecOps report - ${esc(result.plan_name)}</title>
<style>
  body{font:13px/1.45 system-ui,Segoe UI,Arial,sans-serif;color:#111;margin:28px}
  h1{font-size:20px;margin:0 0 2px} h2{font-size:15px;margin:22px 0 6px}
  .verdict{display:inline-block;padding:6px 14px;border-radius:6px;color:#fff;font-weight:700;
           background:${result.verdict === "block" ? "#a4121b" : result.verdict === "remediate" ? "#a16207" : "#15803d"}}
  .meta{color:#444;margin:8px 0} .meta span{margin-right:16px}
  table{border-collapse:collapse;width:100%} th,td{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left}
  th{background:#f1f1ef} pre{background:#f6f6f4;padding:6px;margin:6px 0 0;white-space:pre-wrap}
  code{font-family:Consolas,monospace;font-size:12px} ul{margin:4px 0;padding-left:18px}
  .foot{margin-top:24px;color:#555;font-size:11px}
  @media print{body{margin:12mm} tr{page-break-inside:avoid}}
</style></head><body>
<h1>Agent SecOps - CAF/WAF compliance report</h1>
<div class="verdict">${v.label} &nbsp;(exit code ${v.exit})</div>
<div class="meta">
  <span><b>Plan:</b> ${esc(result.plan_name)}</span>
  <span><b>Source:</b> ${esc(result.source)}</span>
  <span><b>SHA-256:</b> ${esc(shortHash(result.plan_sha256))}</span>
  <span><b>Generated:</b> ${esc(result.generated_at)}</span>
  <span><b>Reasoning layer:</b> ${esc(result.reasoner)}</span>
</div>
<div class="meta">
  <span><b>${result.resources_evaluated}</b> resources</span>
  <span><b>${active.length}</b> active findings</span>
  <span><b>${stats.findings_from_rules || 0}</b> from rules</span>
  <span><b>${stats.findings_from_reasoner || 0}</b> from reasoning</span>
  <span><b>${stats.findings_waived || 0}</b> waived</span>
</div>
<h2>Findings by framework pillar</h2><ul>${pillars || "<li>None</li>"}</ul>
<h2>Findings</h2>
${active.length ? `<table><thead><tr><th>Severity</th><th>Rule / pillar</th><th>Resource</th><th>Detail and fix</th><th>Source</th></tr></thead><tbody>${rows}</tbody></table>`
                : "<p>No CAF or WAF violations in this plan.</p>"}
<p class="foot">Generated by Agent SecOps (Project 19727UG01). Rules are mapped to the Microsoft
Cloud Adoption Framework and Azure Well-Architected Framework; applying them to AWS and GCP resources
extends the intent of those frameworks to equivalent resource kinds.</p>
<script>window.addEventListener("load",function(){setTimeout(function(){window.print()},250)})</script>
</body></html>`;

  const w = window.open("", "_blank");
  if (!w) { alert("Allow pop-ups for this page to open the printable report."); return; }
  w.document.open(); w.document.write(html); w.document.close();
}

/* Real PDF file, built by the server from the result already on screen.
   Falls back to the browser print view if the request fails. */
function downloadPdf(result, base) {
  fetch("/api/report/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      verdict: result.verdict, plan_name: result.plan_name, source: result.source,
      plan_sha256: result.plan_sha256, generated_at: result.generated_at,
      reasoner: result.reasoner, resources_evaluated: result.resources_evaluated,
      stats: result.stats, findings: result.findings,
    }),
  })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.blob(); })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = base + ".pdf";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    })
    .catch(() => openPrintReport(result));
}

function ExportBar({ result }) {
  const base = "secops-" + result.plan_name.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "");
  return (
    <div className="export-bar">
      <span className="export-label">Download report</span>
      <button onClick={() => downloadPdf(result, base)}>PDF</button>
      <button onClick={() => download(base + ".json", result.report_json, "application/json")}>JSON</button>
      <button onClick={() => download(base + ".md", result.markdown, "text/markdown")}>Markdown</button>
      <button onClick={() => download(base + ".sarif", result.sarif, "application/json")}>SARIF</button>
    </div>
  );
}

/* --- real terraform runner ------------------------------------------- */

function PipelineSteps({ steps }) {
  if (!steps || !steps.length) return null;
  return (
    <div className="panel" style={{ marginBottom: 14 }}>
      <h2>Real pipeline run</h2>
      <p className="panel-sub">
        Output of the actual Terraform CLI on this machine, followed by the gate.
      </p>
      {steps.map((st, i) => (
        <details key={i} className="finding" open={!st.ok}>
          <summary>
            <span className="chevron">&#9654;</span>
            <span className={"chip " + (st.ok ? "low" : "critical")}>{st.ok ? "ok" : "failed"}</span>
            <span className="f-title">
              <div>{st.name}</div>
              <div className="f-meta"><code>{st.cmd}</code> &middot; {st.ms} ms</div>
            </span>
          </summary>
          <div className="body"><pre className="hcl">{(st.tail || []).join("\n")}</pre></div>
        </details>
      ))}
    </div>
  );
}

/* --- app shell ------------------------------------------------------- */

function App() {
  const [theme, setTheme] = useTheme();
  const [catalog, setCatalog] = useState({ plans: [], terraform_modules: [], terraform_available: false });
  // `source` is the single thing being evaluated: a catalogued plan or text
  // the user supplied. Toggling the reasoning layer re-evaluates THIS, so an
  // uploaded plan is never silently swapped for a preloaded one.
  // Optional deep links, handy for demos and screenshots:
  //   /?plan=team_demo.plan.json&tab=benchmark&reasoning=off&run=aws_noncompliant
  const query = useMemo(() => new URLSearchParams(window.location.search), []);
  const [source, setSource] = useState({
    type: "catalog",
    key: query.get("plan") || "azure_noncompliant.plan.json",
  });
  const [reasoning, setReasoning] = useState(query.get("reasoning") !== "off");
  const [tab, setTab] = useState(query.get("tab") || "gate");
  const [result, setResult] = useState(null);
  const [steps, setSteps] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState(null);
  const [errorSteps, setErrorSteps] = useState(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasted, setPasted] = useState("");
  const [tfModule, setTfModule] = useState("");
  const [dragging, setDragging] = useState(false);
  const skipRef = useRef(false);
  const runId = useRef(0);
  const [pace, setPace] = useState(query.get("pace") !== "off");
  const [pacing, setPacing] = useState(null);
  const tooltip = useTooltip();

  const loadCatalog = useCallback(() => {
    return fetch("/api/plans")
      .then((r) => r.json())
      .then((d) => {
        setCatalog(d);
        setTfModule((cur) => cur || (d.terraform_modules || [])[0] || "");
      })
      .catch(() => {});
  }, []);
  useEffect(() => { loadCatalog(); }, [loadCatalog]);

  const reasoner = reasoning ? "offline" : "none";

  const evaluate = useCallback(() => {
    setLoading(true);
    setError(null);
    setErrorSteps(null);
    const req = source.type === "catalog"
      ? fetch(`/api/evaluate?plan=${encodeURIComponent(source.key)}&reasoner=${reasoner}`)
      : fetch(`/api/evaluate?reasoner=${reasoner}&name=${encodeURIComponent(source.name)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: source.text,
        });
    const myRun = ++runId.current;
    req.then((r) => r.json())
      .then((d) => {
        if (myRun !== runId.current) return;          // a newer request took over
        if (d.error) { setError(d.error); setResult(null); return; }
        if (!pace) { setResult(d); return; }
        // Presentation pacing: step through the stages so each can be explained.
        return stepThrough(d, setPacing, () => myRun === runId.current).then(() => {
          if (myRun === runId.current) setResult(d);
        });
      })
      .catch((e) => setError(String(e)))
      .finally(() => { if (myRun === runId.current) { setPacing(null); setLoading(false); } });
  }, [source, reasoner, pace]);

  useEffect(() => {
    if (tab !== "gate") return;
    if (skipRef.current) { skipRef.current = false; setLoading(false); return; }
    evaluate();
  }, [evaluate, tab]);

  const useText = (text, name) => {
    setSteps(null);
    setSource({ type: "text", text, name });
    setTab("gate");
  };

  const readFile = (file) => {
    if (!file) return;
    file.text().then((text) => useText(text, file.name));
  };

  const onUpload = (evt) => {
    readFile(evt.target.files && evt.target.files[0]);
    evt.target.value = "";
  };

  const onDrop = (evt) => {
    evt.preventDefault();
    setDragging(false);
    readFile(evt.dataTransfer.files && evt.dataTransfer.files[0]);
  };

  const runTerraform = (named) => {
    const mod = typeof named === "string" ? named : tfModule;
    if (!mod) return;
    setBusy("Running terraform init → plan → show → gate on examples/terraform/" + mod + " …");
    setError(null);
    setErrorSteps(null);
    setTab("gate");
    fetch(`/api/terraform/run?module=${encodeURIComponent(mod)}&reasoner=${reasoner}`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => {
        if (d.error) { setError(d.error); setErrorSteps(d.pipeline || null); return; }
        setResult(d);
        setSteps(d.pipeline || null);
        const key = "terraform/" + mod;
        if (!(source.type === "catalog" && source.key === key)) skipRef.current = true;
        setSource({ type: "catalog", key });
        loadCatalog();
      })
      .catch((e) => setError(String(e)))
      .finally(() => { setBusy(""); setLoading(false); });
  };

  const autoRun = useRef(false);
  useEffect(() => {
    const want = query.get("run");
    if (want && !autoRun.current && (catalog.terraform_modules || []).includes(want)) {
      autoRun.current = true;
      setTfModule(want);
      setTimeout(() => runTerraform(want), 0);
    }
  });

  const groups = {};
  (catalog.plans || []).forEach((p) => { (groups[p.group] = groups[p.group] || []).push(p); });
  const selectValue = source.type === "catalog" ? source.key : "__custom";

  return (
    <div
      className={"shell" + (dragging ? " dragging" : "")}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
      onDrop={onDrop}
    >
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
        This is the same engine the pipeline runs. Give it a <code>terraform plan</code>{" "}
        JSON file (choose one, upload, drop or paste it, or run a real{" "}
        <code>terraform plan</code> below) and it judges every proposed resource against
        CAF governance and Well-Architected pillars &mdash; before anything is created.
      </p>

      <div className="controls">
        <div className="control">
          <label htmlFor="plan-select">Plan</label>
          <select
            id="plan-select"
            value={selectValue}
            onChange={(e) => {
              setSteps(null);
              setSource({ type: "catalog", key: e.target.value });
              setTab("gate");
            }}
          >
            {source.type === "text" && <option value="__custom">{source.name} (supplied)</option>}
            {Object.entries(groups).map(([g, items]) => (
              <optgroup key={g} label={g}>
                {items.map((p) => <option key={p.file} value={p.file}>{p.label}</option>)}
              </optgroup>
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

        <label className="switch" title="Slows the on-screen reveal so each stage can be explained. It does not change the engine or its measured times.">
          <input
            type="checkbox"
            checked={pace}
            onChange={(e) => setPace(e.target.checked)}
          />
          <span className="track"><span className="thumb" /></span>
          <span className="switch-label">Presentation pacing</span>
        </label>

        <label className="file-btn">
          Upload plan.json
          <input type="file" accept=".json,application/json" onChange={onUpload} />
        </label>
        <button className="file-btn" onClick={() => setPasteOpen(!pasteOpen)}>
          {pasteOpen ? "Close paste box" : "Paste JSON"}
        </button>

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

      {pasteOpen && (
        <div className="panel paste-box">
          <textarea
            placeholder="Paste the output of: terraform show -json tf.plan"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            rows={8}
          />
          <button
            className="primary"
            disabled={!pasted.trim()}
            onClick={() => { useText(pasted, "pasted plan"); setPasteOpen(false); }}
          >
            Evaluate pasted plan
          </button>
        </div>
      )}

      <div className="tf-runner">
        <strong>Run the real pipeline</strong>
        {catalog.terraform_available && (catalog.terraform_modules || []).length ? (
          <React.Fragment>
            <select value={tfModule} onChange={(e) => setTfModule(e.target.value)}>
              {(catalog.terraform_modules || []).map((m) => (
                <option key={m} value={m}>examples/terraform/{m}</option>
              ))}
            </select>
            <button className="primary" disabled={!!busy} onClick={() => runTerraform()}>
              {busy ? "Running…" : "terraform plan → gate"}
            </button>
            <span className="hint">
              Plan-only, never applies. First run downloads the provider (about a minute).
            </span>
          </React.Fragment>
        ) : (
          <span className="hint">
            Terraform was not found on PATH, so only pre-generated plans are available.
          </span>
        )}
      </div>
      {busy && <div className="spinner">{busy}</div>}

      {error && (
        <div className="error-box">
          <strong>Could not evaluate that plan.</strong>
          <div style={{ marginTop: 4 }}>{error}</div>
        </div>
      )}
      {errorSteps && <PipelineSteps steps={errorSteps} />}

      {tab === "gate" && (
        <GateTab result={result} loading={loading} tooltip={tooltip} steps={steps} pacing={pacing} />
      )}
      {tab === "benchmark" && <BenchmarkTab tooltip={tooltip} />}
      {tab === "rules" && <RulesTab />}

      <p className="footnote">
        Agent SecOps &middot; Project 19727UG01 &middot; In the real pipeline the gate is a
        CLI whose exit code decides whether <code>terraform apply</code> runs; this
        dashboard drives the same engine.
      </p>

      {tooltip.node}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
