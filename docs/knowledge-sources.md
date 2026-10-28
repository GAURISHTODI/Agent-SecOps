# Knowledge sources and accuracy audit

What the agent's "CAF/WAF knowledge" is actually based on, what was checked
against Microsoft's own documentation, and where it is the project's own
judgement. Audited 2026-10-27. Read this before presenting a claim to faculty.

## 1. What the frameworks really say (verified on Microsoft Learn)

| Claim | Verified fact | Source |
|---|---|---|
| Azure WAF pillars | **Exactly five**: Reliability, Security, Cost Optimization, Operational Excellence, Performance Efficiency. | learn.microsoft.com/azure/well-architected/pillars |
| CAF structure | **Seven phases**: Strategy, Plan, Ready, Adopt, Govern, Secure, Manage. | learn.microsoft.com/azure/cloud-adoption-framework/overview |
| Landing zones | Belong to the **Ready** phase (platform landing zone + workload landing zones, governed by management-group policy). | .../ready/landing-zone/ |
| Key Vault soft-delete | On by default, **cannot be disabled**, retention 7-90 days. **Purge protection is optional and off by default.** | learn.microsoft.com/azure/key-vault/general/soft-delete-overview |

## 2. Corrections made because of this audit

1. **Sustainability is not an Azure WAF pillar.** It is a pillar of the *AWS*
   Well-Architected Framework. The KB previously implied it was part of the
   Microsoft framework. It is now labelled as an extra lens from AWS/Green
   Software Foundation (`caf_waf_kb.yaml`, `WAF:Sustainability.maps_to`).
2. **"CAF pillars" do not exist.** The four labels `CAF:Governance`,
   `CAF:LandingZone`, `CAF:CostManagement`, `CAF:Identity` are this project's
   own control areas. Each now carries a `maps_to` line naming the CAF phase it
   draws on (Govern, Ready, Govern/Manage, Secure). Say "CAF-aligned control
   areas", not "the CAF pillars".
3. **`WAF-REL-003`** claimed to detect "soft delete disabled". Soft-delete can
   no longer be disabled, so the rule is now titled and explained as *purge
   protection disabled*, with the real behaviour described.
4. **`WAF-SEC-003`** said anonymous access is "the single most common cause of
   cloud data leaks". That statistic was unsupported; reworded.
5. **`CAF-LZ-001` (approved region)** only knew Azure region names, so a
   perfectly compliant AWS `us-east-1` or GCP `asia-south1` deployment would
   have been flagged. It now has per-cloud lists (`approved`, `approved_aws`,
   `approved_gcp`) in the rule and in `policies/policy.yaml`.
6. **`CAF-IAM-001` (wildcard grant)** matched the text `"*"` anywhere in an IAM
   policy, so `Action: s3:GetObject, Resource: "*"` was reported as a wildcard
   *action*. It now parses the JSON and flags only an `Allow` statement whose
   `Action` is `*`. It also flagged `Contributor` at resource-group scope, which
   is exactly how this project's own CI identity is granted; `Contributor` is
   now flagged only at subscription/management-group scope (`Owner` and
   `User Access Administrator` are flagged at any scope).
7. **Provider region.** In real `terraform show -json` output the AWS/GCP
   region lives on the provider block, not the resource, so the region rule
   silently never fired on real plans. The parser now inherits it.

Each correction has a regression test (`tests/test_rules.py`,
`tests/test_plan_parser.py`).

## 3. What is the project's own judgement (say so honestly)

- **Thresholds and lists are organisational policy, not Microsoft guidance:**
  7-day minimum backup, the approved-region lists, the mandatory tags
  (`owner`, `environment`, `costcenter`), the `<workload>-<env>-<region>-<type>`
  naming regex, the premium-SKU markers. They are tunable in `policies/policy.yaml`.
- **Applying CAF/WAF to AWS and GCP is an extrapolation.** Microsoft wrote these
  frameworks for Azure. The *intent* (least privilege, encryption, backups,
  no public data) transfers to S3 or Cloud Storage; the citation does not.
  AWS and Google publish their own frameworks.
- **The "reasoning layer" findings are not Microsoft rules either.** The offline
  reasoner is 12 hand-written probes, each tied to a `watch_for` line in the KB.

## 4. Known limitations (not fixed, disclose if asked)

- `WAF-OPS-001` is satisfied by a `monitoring` tag. A tag does not ship logs.
- Cross-resource diagnostic linking (`engine._link_diagnostics`) matches on
  names because `target_resource_id` is unknown at plan time; it is a
  heuristic and can miss a real link.
- `WAF-SEC-006` flags any literal in a credential field, even one that came from
  a CI-injected variable (the value is still in plan and state, so the warning
  is accurate, but it cannot tell a vault reference from a literal).
- `CAF-COST-001` is titled "expensive SKU" but fires on any billable resource
  missing a `costcenter` tag. `WAF-SUS-001` depends on a project-invented
  `dataclass` tag.
- The benchmark's ground truth was written by the same authors as the rules and
  the probes. It is a regression suite, not independent accuracy evidence.

## 5. Literature cited in the report

Recognised, real publications (checked from memory, not re-fetched): Rahman,
Parnin & Williams, *The Seven Sins: Security Smells in IaC Scripts* (ICSE 2019);
Saavedra & Ferreira, *GLITCH* (ASE 2022); Chiari et al., *Static analysis of
infrastructure as code: a survey* (ICSA-C 2022); Lewis et al., *Retrieval-
Augmented Generation* (NeurIPS 2020); Pearce et al., *Asleep at the Keyboard?*
(IEEE S&P 2022); Malul et al., *GenKubeSec* (2024). **Not independently
verified:** the Vo et al. COMPSAC 2025 citation (it came from the Review-1 PDF).
Check the exact titles and venues against the paper before final submission.
