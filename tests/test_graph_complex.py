"""Layer 2b on complicated dependency graphs.

Two kinds of test:

* The seeded module examples/terraform/aws_mesh, planned by real terraform
  (examples/plans/real/aws_mesh.plan.json): count and for_each instances, a
  reference cycle, a diamond with two exposure sources, a path longer than the
  hop limit, a one-rule shortcut, a child module and a clean island. Each
  scenario is isolated by deleting resources from the plan before parsing.
* Synthetic graphs that no one would write by hand: long chains, rings,
  a complete graph and a large hub, to pin down the hop limit, the noisy-OR
  arithmetic and termination on cycles.
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

from agent.config import Waiver, load_policy
from agent.engine import evaluate_plan
from agent.models import Action, Finding, Pillar, Resource, Severity, Verdict
from agent.plan_parser import classify, detect_provider, parse_plan
from agent.reasoner.graph import GraphReasoner

ROOT = Path(__file__).resolve().parent.parent
MESH = ROOT / "examples" / "plans" / "real" / "aws_mesh.plan.json"
POLICY = ROOT / "policies" / "policy.yaml"

ORDERS = "aws_db_instance.orders"
ANALYTICS = "aws_db_instance.analytics"
SHORTCUT = "aws_security_group_rule.debug_shortcut"


def mesh(drop=()):
    """The real mesh plan, optionally with some resources removed."""
    data = json.loads(MESH.read_text(encoding="utf-8"))
    data = copy.deepcopy(data)
    data["resource_changes"] = [
        rc for rc in data["resource_changes"] if rc["address"] not in drop
    ]
    root = data["configuration"]["root_module"]
    root["resources"] = [r for r in root["resources"] if r["address"] not in drop]
    return parse_plan(data)


def run(plan, policy=None):
    return evaluate_plan(plan, policy or load_policy(str(POLICY)))


def graph_findings(result):
    return [f for f in result.findings if f.rule_id == "REASON-GRAPH" and not f.waived]


def node(result, address):
    return next(n for n in result.stats["graph_model"]["nodes"] if n["id"] == address)


# --- the real mesh plan -----------------------------------------------------

def test_mesh_is_blocked_and_parsed_completely():
    plan = mesh()
    assert len(plan.resources) == 22
    assert run(plan).verdict is Verdict.BLOCK


def test_count_and_for_each_instances_each_get_their_edge():
    edges = mesh().edges
    for i in range(3):
        assert edges["aws_instance.web[{}]".format(i)] == ["aws_security_group.web"]
    for key in ("api", "worker"):
        assert edges['aws_instance.app["{}"]'.format(key)] == ["aws_security_group.app"]


def test_child_module_edges_keep_their_prefix():
    edges = mesh().edges
    assert set(edges["module.reporting.aws_lambda_function.report"]) == {
        "module.reporting.aws_iam_role.report",
        "module.reporting.aws_security_group.lambda",
    }


def test_reference_cycle_is_present_and_terminates():
    edges = mesh().edges
    # web SG <- app SG, and the rule links both: a cycle once undirected.
    assert edges["aws_security_group.app"] == ["aws_security_group.web"]
    assert set(edges["aws_security_group_rule.app_to_web"]) == {
        "aws_security_group.web", "aws_security_group.app",
    }
    started = time.perf_counter()
    run(mesh())
    assert time.perf_counter() - started < 2.0


def test_diamond_combines_both_exposure_sources_with_noisy_or():
    result = run(mesh())
    # The debug rule is a connector with no findings of its own, so it counts
    # as a direct link: edge SG -> db SG -> orders is 2 hops.
    via_shortcut = 0.90 * 0.75 ** 2
    via_key = 0.70 * 0.75 ** 2          # analytics -> KMS key -> orders
    expected = 1 - (1 - via_shortcut) * (1 - via_key)
    assert node(result, ORDERS)["exposure_reach"] == pytest.approx(expected, abs=0.002)
    flagged = [f.resource_address for f in graph_findings(result)]
    assert flagged == [ORDERS]


def test_shortcut_alone_creates_the_compound_risk():
    # Without the analytics database, only the debugging rule connects the
    # internet-facing group to the orders database.
    result = run(mesh(drop={ANALYTICS}))
    findings = graph_findings(result)
    assert [f.resource_address for f in findings] == [ORDERS]
    assert SHORTCUT in findings[0].explanation


def test_without_the_shortcut_the_database_is_out_of_reach():
    # Through the tiers the database is 4 hops from the edge: beyond max_hops.
    result = run(mesh(drop={ANALYTICS, SHORTCUT}))
    assert graph_findings(result) == []
    assert node(result, ORDERS)["exposure_reach"] == 0.0


def test_public_database_alone_reaches_its_neighbour_through_the_shared_key():
    result = run(mesh(drop={SHORTCUT}))
    findings = graph_findings(result)
    assert [f.resource_address for f in findings] == [ORDERS]
    assert "aws_kms_key.data" in findings[0].explanation


def test_waiving_the_exposure_removes_the_compound_finding():
    policy = load_policy(str(POLICY))
    policy.waivers = [Waiver(rule_id="WAF-SEC-004", resource="aws_security_group.edge",
                             reason="edge reviewed")]
    assert graph_findings(run(mesh(drop={ANALYTICS}), policy)) == []


def test_clean_island_stays_quiet():
    result = run(mesh())
    island = [f for f in result.active if f.resource_address.endswith(".audit")]
    # Versioning and encryption are folded on from their own resources, so
    # the bucket is judged compliant on both; only diagnostics remain.
    assert {f.rule_id for f in island} <= {"WAF-OPS-001"}
    assert node(result, "aws_s3_bucket.audit")["exposure_reach"] == 0.0


def test_exposed_but_healthy_instances_are_not_flagged():
    result = run(mesh())
    for i in range(3):
        n = node(result, "aws_instance.web[{}]".format(i))
        assert n["exposure_reach"] > 0.4 and not n["flagged"]


def test_unknown_policy_document_is_a_documented_blind_spot():
    """The wildcard policy depends on an apply-time ARN, so the plan hides it."""
    plan = mesh()
    policy = next(r for r in plan.resources
                  if r.address == "module.reporting.aws_iam_role_policy.report")
    assert "policy" not in policy.after
    assert not [f for f in run(plan).active if f.resource_address == policy.address]


def test_mesh_results_are_deterministic():
    first = [(f.rule_id, f.resource_address, f.explanation) for f in run(mesh()).findings]
    second = [(f.rule_id, f.resource_address, f.explanation) for f in run(mesh()).findings]
    assert first == second


# --- harmless alone, dangerous together -----------------------------------
#
# Both modules are built so that no resource is a risk on its own (the graph
# scores the database 0.00 alone) while the combination is HIGH.

REAL = ROOT / "examples" / "plans" / "real"
BILLING = "aws_db_instance.billing"
PAYMENTS = "module.ledger.aws_db_instance.payments"


def real_plan(name, keep=None, drop=(), edit=None):
    """Load a committed real plan, keeping/dropping resources by address prefix."""
    data = json.loads((REAL / name).read_text(encoding="utf-8"))

    def wanted(address):
        if any(address.startswith(p) for p in drop):
            return False
        return keep is None or any(address.startswith(p) for p in keep)

    data["resource_changes"] = [rc for rc in data["resource_changes"] if wanted(rc["address"])]
    if edit:
        edit(data)
    return parse_plan(data)


def compound(result, address):
    return next((f for f in graph_findings(result) if f.resource_address == address), None)


def test_thousand_cuts_six_small_doors_make_a_high_risk():
    result = run(real_plan("aws_thousand_cuts.plan.json"))
    f = compound(result, BILLING)
    assert f is not None and f.severity is Severity.HIGH
    db = node(result, BILLING)
    assert db["risk_alone"] == 0.0
    assert db["exposure_reach"] == pytest.approx(1 - (1 - 0.55 * 0.75 ** 3) ** 6, abs=0.002)
    assert db["risk"] == pytest.approx(0.66, abs=0.01)


def test_thousand_cuts_each_door_on_its_own_is_only_a_medium_note():
    result = run(real_plan("aws_thousand_cuts.plan.json"))
    for i in range(6):
        own = {(f.rule_id, f.severity) for f in result.active
               if f.resource_address == "aws_eip.web[{}]".format(i)}
        assert own == {("CAF-LZ-003", Severity.MEDIUM)}
    # The web servers have no rule findings at all.
    assert not [f for f in result.active
                if f.resource_address.startswith("aws_instance.web") and f.source == "rules"]


@pytest.mark.parametrize("doors,expected", [
    (1, None), (2, None), (3, Severity.MEDIUM), (4, Severity.MEDIUM),
    (5, Severity.HIGH), (6, Severity.HIGH),
])
def test_thousand_cuts_risk_grows_with_the_number_of_doors(doors, expected):
    removed = tuple("aws_eip.web[{}]".format(i) for i in range(doors, 6))
    f = compound(run(real_plan("aws_thousand_cuts.plan.json", drop=removed)), BILLING)
    assert (f.severity if f else None) is expected


def test_thousand_cuts_fix_is_a_separate_security_group():
    def own_group(data):
        for res in data["configuration"]["root_module"]["resources"]:
            if res["address"] == BILLING:
                res["expressions"].pop("vpc_security_group_ids", None)

    result = run(real_plan("aws_thousand_cuts.plan.json", edit=own_group))
    assert compound(result, BILLING) is None


def test_shared_trust_three_teams_combine_into_a_high_risk():
    result = run(real_plan("aws_shared_trust.plan.json"))
    f = compound(result, PAYMENTS)
    assert f is not None and f.severity is Severity.HIGH
    assert node(result, PAYMENTS)["risk_alone"] == 0.0
    assert [g.resource_address for g in graph_findings(result)] == [PAYMENTS]


def test_shared_trust_edges_cross_module_boundaries():
    edges = real_plan("aws_shared_trust.plan.json").edges
    assert set(edges[PAYMENTS]) == {"aws_kms_key.shared", "aws_security_group.internal"}
    assert edges["module.analytics.aws_db_instance.reporting"] == ["aws_kms_key.shared"]
    for i in range(3):
        assert edges["module.storefront.aws_instance.web[{}]".format(i)] == [
            "aws_security_group.internal"]


SHARED = ("aws_kms_key.shared", "aws_security_group.internal")


@pytest.mark.parametrize("teams,expected", [
    (("module.storefront.",), None),
    (("module.analytics.",), None),
    (("module.ledger.",), None),
    (("module.analytics.", "module.ledger."), Severity.LOW),
    (("module.storefront.", "module.ledger."), Severity.MEDIUM),
    (("module.storefront.", "module.analytics.", "module.ledger."), Severity.HIGH),
])
def test_shared_trust_each_team_alone_is_fine(teams, expected):
    result = run(real_plan("aws_shared_trust.plan.json", keep=SHARED + teams))
    f = compound(result, PAYMENTS)
    assert (f.severity if f else None) is expected


def test_key_taken_from_another_resource_counts_as_customer_managed():
    result = run(real_plan("aws_shared_trust.plan.json"))
    assert not [f for f in result.active if f.rule_id == "WAF-SEC-005"]


def test_shared_trust_graph_has_links_even_though_all_are_inside_modules():
    """Regression: every link in this plan lives inside a child module.

    A parser that only reads the root module sees no edges at all, which left
    the dashboard's "Simulate exposure spread" button disabled for this plan.
    """
    result = run(real_plan("aws_shared_trust.plan.json"))
    assert len(result.stats["graph_model"]["edges"]) >= 10


# --- the risk spectrum: every level in one plan -----------------------------

SPECTRUM = "aws_risk_spectrum.plan.json"


def spectrum_node(result, name):
    return node(result, "aws_db_instance." + name)


def test_spectrum_has_every_level_in_one_plan():
    result = run(real_plan(SPECTRUM))
    model = result.stats["graph_model"]
    assert len(model["nodes"]) >= 10
    graded = {f.resource_address: f.severity for f in graph_findings(result)}
    assert graded == {
        "aws_db_instance.payments": Severity.HIGH,
        "aws_db_instance.orders": Severity.MEDIUM,
        "aws_db_instance.reports": Severity.LOW,
    }


@pytest.mark.parametrize("name,hops,weakness,risk", [
    ("payments", 1, 0.932, 0.629),   # HIGH
    ("orders", 2, 0.932, 0.472),     # MEDIUM
    ("reports", 2, 0.830, 0.420),    # LOW
    ("archive", 3, 0.830, 0.315),    # scored, below the 0.35 threshold
])
def test_spectrum_risk_follows_distance_and_weakness(name, hops, weakness, risk):
    n = spectrum_node(run(real_plan(SPECTRUM)), name)
    assert n["exposure_reach"] == pytest.approx(0.9 * 0.75 ** hops, abs=0.002)
    assert n["weakness"] == pytest.approx(weakness, abs=0.002)
    assert n["risk"] == pytest.approx(risk, abs=0.002)


def test_spectrum_four_hops_is_out_of_reach():
    result = run(real_plan(SPECTRUM))
    vault = spectrum_node(result, "vault")
    assert vault["weakness"] > 0.9 and vault["exposure_reach"] == 0.0 and vault["risk"] == 0.0


def test_spectrum_exposed_and_reachable_but_healthy_nodes_stay_quiet():
    result = run(real_plan(SPECTRUM))
    analytics = spectrum_node(result, "analytics")
    assert analytics["exposure_self"] == pytest.approx(0.70) and analytics["risk"] == 0.0
    for i in range(3):
        web = node(result, "aws_instance.web[{}]".format(i))
        assert web["exposure_reach"] == pytest.approx(0.675, abs=0.002) and not web["flagged"]
    assert node(result, "aws_s3_bucket.audit")["exposure_reach"] == 0.0


# --- synthetic graphs ---------------------------------------------------------

def res(address_name, rtype="aws_db_instance", **after):
    return Resource(
        address="{}.{}".format(rtype, address_name), type=rtype, name=address_name,
        provider=detect_provider(rtype), kind=classify(rtype),
        action=Action.CREATE, after=dict(after),
    )


def exposed(address):
    return Finding(rule_id="WAF-SEC-004", title="open", pillar=Pillar.WAF_SECURITY,
                   severity=Severity.CRITICAL, resource_address=address,
                   explanation="x", remediation="y")


def weak(address):
    return Finding(rule_id="WAF-SEC-006", title="plaintext", pillar=Pillar.WAF_SECURITY,
                   severity=Severity.CRITICAL, resource_address=address,
                   explanation="x", remediation="y")


def chain(length):
    """sg -> n1 -> n2 -> ... ; every database is weak, only the sg is exposed."""
    sg = res("edge", "aws_security_group")
    dbs = [res("n{}".format(i)) for i in range(1, length + 1)]
    edges = {dbs[0].address: [sg.address]}
    for prev, cur in zip(dbs, dbs[1:]):
        edges[cur.address] = [prev.address]
    findings = [exposed(sg.address)] + [weak(d.address) for d in dbs]
    return [sg] + dbs, edges, findings


def test_hop_limit_is_exact_on_a_long_chain():
    resources, edges, findings = chain(8)
    graph = GraphReasoner(edges)
    graph.analyse_graph(resources, findings)
    reach = {n["id"]: n["exposure_reach"] for n in graph.model["nodes"]}
    # Each database also exposes nothing itself, so reach is 0.9 * 0.75^hops.
    for hops in range(1, 9):
        expected = 0.9 * 0.75 ** hops if hops <= 3 else 0.0
        assert reach["aws_db_instance.n{}".format(hops)] == pytest.approx(expected, abs=1e-3)


def test_decay_and_threshold_decide_how_far_a_finding_reaches():
    resources, edges, findings = chain(8)
    out = GraphReasoner(edges).analyse_graph(resources, findings)
    # risk = 0.9 * 0.75^h * 0.8 (one critical) * 1.0 (database): >= 0.35 only
    # for h = 1 (0.54) and h = 2 (0.405); h = 3 gives 0.30.
    assert sorted(f.resource_address for f in out) == [
        "aws_db_instance.n1", "aws_db_instance.n2",
    ]


def test_large_ring_terminates_and_is_symmetric():
    size = 300
    nodes = [res("r{}".format(i)) for i in range(size)]
    sg = res("edge", "aws_security_group")
    edges = {nodes[i].address: [nodes[(i + 1) % size].address] for i in range(size)}
    edges[nodes[0].address].append(sg.address)
    findings = [exposed(sg.address)] + [weak(n.address) for n in nodes]
    started = time.perf_counter()
    graph = GraphReasoner(edges)
    out = graph.analyse_graph([sg] + nodes, findings)
    assert time.perf_counter() - started < 5.0
    flagged = {f.resource_address for f in out}
    # r0 is 1 hop from the edge; r1 and r299 are 2 hops, one each way round.
    assert flagged == {"aws_db_instance.r0", "aws_db_instance.r1", "aws_db_instance.r299"}


def test_complete_graph_counts_each_edge_once():
    size = 30
    nodes = [res("k{}".format(i)) for i in range(size)]
    edges = {a.address: [b.address for b in nodes if b is not a] for a in nodes}
    graph = GraphReasoner(edges)
    graph.analyse_graph(nodes, [])
    assert graph.edges_used == size * (size - 1) // 2
    assert len(graph.model["edges"]) == size * (size - 1) // 2


def test_many_weak_neighbours_do_not_amplify_each_other():
    """Weakness is a property of the target alone; neighbours only carry exposure."""
    sg = res("edge", "aws_security_group")
    target = res("target")
    others = [res("o{}".format(i)) for i in range(50)]
    edges = {target.address: [sg.address] + [o.address for o in others]}
    findings = [exposed(sg.address), weak(target.address)] + [weak(o.address) for o in others]
    graph = GraphReasoner(edges)
    graph.analyse_graph([sg, target] + others, findings)
    t = next(n for n in graph.model["nodes"] if n["id"] == target.address)
    assert t["weakness"] == pytest.approx(0.80)
    assert t["exposure_reach"] == pytest.approx(0.9 * 0.75)


def test_connector_is_a_link_unless_it_carries_findings_itself():
    a = res("a", "aws_security_group")
    b = res("b", "aws_security_group")
    rule = res("r", "aws_security_group_rule")
    edges = {rule.address: [a.address, b.address]}

    quiet = GraphReasoner(edges)
    quiet.analyse_graph([a, b, rule], [])
    assert {n["id"] for n in quiet.model["nodes"]} == {a.address, b.address}
    assert quiet.model["edges"] == [sorted([a.address, b.address])]

    loud = GraphReasoner(edges)
    loud.analyse_graph([a, b, rule], [exposed(rule.address)])
    assert rule.address in {n["id"] for n in loud.model["nodes"]}


def test_resource_group_hub_with_hundreds_of_members_connects_nothing():
    rg = res("rg", "azurerm_resource_group")
    sg = res("edge", "aws_security_group")
    members = [res("m{}".format(i)) for i in range(200)]
    edges = {m.address: [rg.address] for m in members}
    edges[sg.address] = [rg.address]
    findings = [exposed(sg.address)] + [weak(m.address) for m in members]
    graph = GraphReasoner(edges)
    assert graph.analyse_graph([rg, sg] + members, findings) == []
    assert graph.edges_used == 0
