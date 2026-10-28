"""Dependency-graph risk propagation: the structural half of Layer 2.

Layer-1 rules and the probe reasoner both judge one resource at a time. Real
incidents are usually *combinations*: a firewall opened to the internet is
tolerable until a database with a plaintext password sits behind it. A rule
cannot see that, because the two facts live on different resources.

This reasoner works on the plan's dependency graph instead:

  1. Nodes are the planned resources; edges come from the references in the
     Terraform configuration (a NIC that references a subnet, a database
     that references a security group, a firewall rule that references a
     server). Shared "hub" objects such as resource groups are dropped so
     that everything does not look connected to everything.
  2. Evidence is *reused from Layer 1*, not recomputed. A finding from an
     exposure rule (open ingress, anonymous access, public network access,
     public IP) becomes an exposure signal e; every other finding becomes
     weakness evidence whose weight depends on its severity.
  3. Exposure is propagated along the graph with distance decay. Node j's
     reachable exposure is the noisy-OR of its neighbours' exposure,
     attenuated by delta^distance:

         E_j = 1 - prod_i (1 - e_i * delta^d(i, j))        d(i, j) <= max_hops

  4. Weakness is the noisy-OR of the severity weights of j's own findings,
     W_j. The asset value A_j depends on the kind (a database outranks a
     log workspace) and on the environment tag (prod raises it, dev lowers
     it). Risk is R_j = E_j * W_j * A_j.
  5. Only the *uplift from the graph* is reported. R_j is compared with the
     risk the node would have from its own exposure alone; a finding is
     raised only if the graph adds at least `min_uplift`, so this layer never
     repeats what the single-resource layers already said.

Every number is derived from evidence in the plan, nothing is a fixed
per-probe constant, and the explanation names the actual path.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..models import Finding, Kind, Resource, Severity
from .base import make_finding

# Layer-1 rule ids that describe *exposure* (how reachable a resource is),
# with the strength of that exposure.
EXPOSURE_RULES: Dict[str, float] = {
    "WAF-SEC-004": 0.90,   # port open to the internet
    "WAF-SEC-003": 0.90,   # anonymous / public-read access
    "CAF-LZ-002": 0.60,    # public network access enabled
    "CAF-LZ-003": 0.55,    # workload-owned public IP
}

# Weight of one piece of weakness evidence, by the severity of the finding.
SEVERITY_WEIGHT: Dict[Severity, float] = {
    Severity.CRITICAL: 0.80,
    Severity.HIGH: 0.60,
    Severity.MEDIUM: 0.35,
    Severity.LOW: 0.15,
    Severity.INFO: 0.0,
}

# How much it matters if this kind of resource is compromised.
ASSET_VALUE: Dict[Kind, float] = {
    Kind.MANAGED_DATABASE: 1.00,
    Kind.SECRET_STORE: 1.00,
    Kind.IAM_BINDING: 0.90,
    Kind.OBJECT_STORAGE: 0.90,
    Kind.COMPUTE_INSTANCE: 0.80,
    Kind.CONTAINER_PLATFORM: 0.80,
    Kind.APP_HOSTING: 0.70,
}
_DEFAULT_ASSET = 0.20
_ENV_FACTOR = {"prod": 1.15, "production": 1.15, "dev": 0.80, "test": 0.80,
               "sandbox": 0.70, "stage": 0.90, "staging": 0.90}

_HUB_KINDS = (Kind.RESOURCE_GROUP,)

# Only findings that make a resource easier to compromise or harder to
# recover count as weakness. Missing tags, naming and region choices are
# governance concerns, not exploitability.
WEAKNESS_PILLARS = ("WAF:Security", "CAF:Identity", "WAF:Reliability")


def _noisy_or(weights: Iterable[float]) -> float:
    prod = 1.0
    for w in weights:
        prod *= 1.0 - max(0.0, min(1.0, w))
    return 1.0 - prod


def _attribute_exposure(resource: Resource) -> float:
    """Exposure that no Layer-1 rule reports but the plan states directly."""
    a = resource.after
    if str(a.get("start_ip_address", "")) == "0.0.0.0" and str(
        a.get("end_ip_address", "")
    ) in ("255.255.255.255", "0.0.0.0"):
        return 0.95            # database firewall rule spanning all of IPv4
    if a.get("publicly_accessible") is True:
        return 0.70
    return 0.0


class GraphReasoner:
    """Risk propagation over the plan's dependency graph."""

    name = "graph"

    def __init__(
        self,
        edges: Dict[str, List[str]],
        decay: float = 0.75,
        max_hops: int = 3,
        min_risk: float = 0.35,
        min_uplift: float = 0.10,
    ) -> None:
        self.edges = edges
        self.decay = decay
        self.max_hops = max_hops
        self.min_risk = min_risk
        self.min_uplift = min_uplift
        self.nodes_seen = 0
        self.edges_used = 0
        # Everything the visualisation needs, filled in by analyse_graph().
        self.model: Dict[str, object] = {"nodes": [], "edges": [], "flagged_paths": [], "params": {}}

    # ---- graph ------------------------------------------------------
    def _adjacency(self, resources: Sequence[Resource]) -> Dict[str, List[str]]:
        by_addr = {r.address: r for r in resources}
        adj: Dict[str, List[str]] = {a: [] for a in by_addr}
        used = 0
        for src, targets in self.edges.items():
            if src not in by_addr or by_addr[src].kind in _HUB_KINDS:
                continue
            for dst in targets:
                if dst not in by_addr or by_addr[dst].kind in _HUB_KINDS:
                    continue
                if dst not in adj[src]:
                    adj[src].append(dst)
                    adj[dst].append(src)   # exposure flows both ways along a link
                    used += 1
        self.edges_used = used
        return adj

    def _bfs(self, adj: Dict[str, List[str]], start: str) -> Dict[str, Tuple[int, List[str]]]:
        """address -> (distance, path) for every node within max_hops of start."""
        seen: Dict[str, Tuple[int, List[str]]] = {start: (0, [start])}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            dist, path = seen[cur]
            if dist == self.max_hops:
                continue
            for nxt in adj.get(cur, []):
                if nxt not in seen:
                    seen[nxt] = (dist + 1, path + [nxt])
                    queue.append(nxt)
        return seen

    # ---- evidence ----------------------------------------------------
    def _signals(
        self, resources: Sequence[Resource], findings: Sequence[Finding]
    ) -> Tuple[Dict[str, float], Dict[str, List[Finding]], Dict[str, List[str]]]:
        exposure: Dict[str, float] = {}
        evidence: Dict[str, List[Finding]] = {r.address: [] for r in resources}
        exposure_why: Dict[str, List[str]] = {r.address: [] for r in resources}
        for f in findings:
            if f.waived or f.resource_address not in evidence:
                continue
            if f.rule_id in EXPOSURE_RULES:
                w = EXPOSURE_RULES[f.rule_id]
                exposure[f.resource_address] = _noisy_or(
                    [exposure.get(f.resource_address, 0.0), w]
                )
                exposure_why[f.resource_address].append(f.title)
            elif f.pillar.value in WEAKNESS_PILLARS:
                evidence[f.resource_address].append(f)
        for r in resources:
            extra = _attribute_exposure(r)
            if extra:
                exposure[r.address] = _noisy_or([exposure.get(r.address, 0.0), extra])
                exposure_why[r.address].append("internet-wide firewall range or public endpoint")
        return exposure, evidence, exposure_why

    @staticmethod
    def _asset(resource: Resource) -> float:
        value = ASSET_VALUE.get(resource.kind, _DEFAULT_ASSET)
        env = str(resource.tags.get("environment", "")).lower()
        return min(1.0, value * _ENV_FACTOR.get(env, 1.0))

    # ---- main ----------------------------------------------------------
    def analyse_graph(
        self, resources: Sequence[Resource], findings: Sequence[Finding]
    ) -> List[Finding]:
        adj = self._adjacency(resources)
        self.nodes_seen = len(adj)
        exposure, evidence, why = self._signals(resources, findings)
        out: List[Finding] = []
        model_nodes: List[Dict[str, object]] = []
        flagged_paths: List[Dict[str, object]] = []

        for target in resources:
            if target.kind in _HUB_KINDS:
                continue
            tid = target.address
            weakness_items = evidence[tid]
            weakness = _noisy_or(SEVERITY_WEIGHT[f.severity] for f in weakness_items)
            asset = self._asset(target)

            reach = self._bfs(adj, tid)
            contributions: List[Tuple[float, str, int, List[str]]] = []
            for src, (dist, path) in reach.items():
                e = exposure.get(src, 0.0)
                if e <= 0.0:
                    continue
                contributions.append((e * (self.decay ** dist), src, dist, path))

            e_total = _noisy_or(c[0] for c in contributions)
            e_self = _noisy_or(c[0] for c in contributions if c[1] == tid)
            risk = e_total * weakness * asset
            risk_alone = e_self * weakness * asset
            ranked = sorted(weakness_items, key=lambda f: -SEVERITY_WEIGHT[f.severity])
            weak_titles_all = list(dict.fromkeys(f.title for f in ranked))

            node = {
                "id": tid,
                "label": target.name,
                "type": target.type,
                "kind": target.kind.value,
                "cloud": target.provider.value,
                "exposure_self": round(exposure.get(tid, 0.0), 3),
                "exposure_reach": round(e_total, 3),
                "weakness": round(weakness, 3),
                "asset": round(asset, 3),
                "risk": round(risk, 3),
                "risk_alone": round(risk_alone, 3),
                "weaknesses": weak_titles_all[:4],
                "exposure_why": why.get(tid, [])[:2],
                "flagged": False,
            }
            model_nodes.append(node)

            # --- the decision: report only what the connection adds ------
            if not weakness_items or not contributions:
                continue
            if risk < self.min_risk or risk - risk_alone < self.min_uplift:
                continue
            others = sorted((c for c in contributions if c[1] != tid), reverse=True)
            if not others:
                continue
            strength, src, dist, path = others[0]
            weak_titles = "; ".join(weak_titles_all[:3])
            chain = " -> ".join(reversed(path))
            severity = "high" if risk >= 0.60 else "medium" if risk >= 0.45 else "low"
            exposure_text = "; ".join(why[src][:2]) or "exposure"
            explanation = (
                "Exposure path {chain} ({dist} hop{s}). {src} carries exposure "
                "({etext}) that reaches {tgt}, which already has these weaknesses: "
                "{weak}. Propagated risk is {risk:.2f} (reachable exposure "
                "{et:.2f} x weakness {w:.2f} x asset value {a:.2f}); on its own "
                "{tgt} would score {alone:.2f}, so the connection adds "
                "{up:.2f}."
            ).format(
                chain=chain, dist=dist, s="" if dist == 1 else "s", src=src,
                etext=exposure_text, tgt=tid, weak=weak_titles, risk=risk,
                et=e_total, w=weakness, a=asset, alone=risk_alone,
                up=risk - risk_alone,
            )
            finding = make_finding(
                resource_address=tid,
                title="Compound risk: exposed path reaches a weak resource",
                pillar_name="WAF:Security",
                severity_name=severity,
                explanation=explanation,
                remediation=(
                    "Cut the path (restrict or remove {src}'s exposure, or place {tgt} "
                    "behind a private endpoint) or fix the listed weaknesses on {tgt}. "
                    "Either one removes most of the propagated risk.".format(src=src, tgt=tid)
                ),
                confidence=min(0.95, round(risk + 0.15, 2)),
                source="reasoner",
                rule_id="REASON-GRAPH",
            )
            if finding:
                out.append(finding)
                node["flagged"] = True
                flagged_paths.append({
                    "target": tid, "source": src, "path": list(reversed(path)),
                    "hops": dist, "risk": round(risk, 3),
                    "uplift": round(risk - risk_alone, 3), "severity": severity,
                })

        pairs = sorted({tuple(sorted((a, b))) for a, ns in adj.items() for b in ns})
        self.model = {
            "nodes": model_nodes,
            "edges": [list(p) for p in pairs],
            "flagged_paths": flagged_paths,
            "params": {
                "decay": self.decay, "max_hops": self.max_hops,
                "min_risk": self.min_risk, "min_uplift": self.min_uplift,
            },
        }
        return out
