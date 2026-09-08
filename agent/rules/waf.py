"""Well-Architected Framework rules -- workload-level design quality.

WAF asks "is this specific resource built well?" across its pillars:
Security, Reliability, Cost Optimization, Operational Excellence and
Performance Efficiency.
"""
from __future__ import annotations

from typing import List, Optional

from ..models import Kind, Pillar, Resource, Severity
from .base import Rule, is_open_cidr, register, truthy


def _tls_value(resource: Resource) -> Optional[str]:
    for key in ("min_tls_version", "minimum_tls_version", "ssl_minimum_version"):
        val = resource.after.get(key)
        if isinstance(val, str) and val:
            return val
    return None


# ======================================================================
# Security
# ======================================================================


@register
class StorageHttpsOnly(Rule):
    id = "WAF-SEC-001"
    title = "Storage accepts unencrypted transport"
    pillar = Pillar.WAF_SECURITY
    severity = Severity.HIGH
    kinds = (Kind.OBJECT_STORAGE,)
    rationale = (
        "WAF Security requires encryption in transit; allowing plain HTTP "
        "exposes data and shared-access tokens to network interception."
    )
    remediation = "Force HTTPS-only traffic on the storage account or bucket."
    terraform_fix = "https_traffic_only_enabled = true"

    def check(self, resource: Resource) -> Optional[str]:
        for key in ("https_traffic_only_enabled", "enable_https_traffic_only"):
            if key in resource.after and not truthy(resource.after[key]):
                return "{} is false, so the account accepts plain HTTP.".format(key)
        return None


@register
class MinimumTlsVersion(Rule):
    id = "WAF-SEC-002"
    title = "Deprecated TLS version permitted"
    pillar = Pillar.WAF_SECURITY
    severity = Severity.MEDIUM
    kinds = (Kind.OBJECT_STORAGE, Kind.MANAGED_DATABASE, Kind.APP_HOSTING)
    rationale = (
        "WAF Security expects TLS 1.2 or newer; TLS 1.0 and 1.1 are "
        "deprecated and vulnerable to downgrade attacks."
    )
    remediation = "Set the minimum TLS version to 1.2 or higher."
    terraform_fix = 'min_tls_version = "TLS1_2"'
    params = {"minimum": 1.2}

    def check(self, resource: Resource) -> Optional[str]:
        raw = _tls_value(resource)
        if raw is None:
            return None
        digits = raw.upper().replace("TLS", "").replace("_", ".").replace("V", "").strip()
        try:
            version = float(digits)
        except ValueError:
            return None
        minimum = float(self.param("minimum", 1.2))
        if version >= minimum:
            return None
        return "Minimum TLS version is {}, below the required {}.".format(raw, minimum)


@register
class PublicBlobAccess(Rule):
    id = "WAF-SEC-003"
    title = "Storage allows anonymous public read access"
    pillar = Pillar.WAF_SECURITY
    severity = Severity.CRITICAL
    kinds = (Kind.OBJECT_STORAGE,)
    rationale = (
        "Anonymous container/bucket access is the single most common cause of "
        "cloud data leaks; WAF Security requires authenticated access by "
        "default."
    )
    remediation = "Disable anonymous access and grant reads through RBAC or SAS."
    terraform_fix = "allow_nested_items_to_be_public = false"

    def check(self, resource: Resource) -> Optional[str]:
        for key in ("allow_nested_items_to_be_public", "allow_blob_public_access"):
            if key in resource.after and truthy(resource.after[key]):
                return "{} is true, permitting anonymous reads.".format(key)
        access = resource.after.get("container_access_type")
        if isinstance(access, str) and access.lower() in ("blob", "container"):
            return (
                'container_access_type = "{}" exposes the container contents '
                "anonymously.".format(access)
            )
        acl = resource.after.get("acl")
        if isinstance(acl, str) and acl in ("public-read", "public-read-write"):
            return 'Bucket ACL "{}" makes objects world-readable.'.format(acl)
        return None


@register
class OpenIngress(Rule):
    id = "WAF-SEC-004"
    title = "Firewall rule exposes a port to the entire internet"
    pillar = Pillar.WAF_SECURITY
    severity = Severity.CRITICAL
    kinds = (Kind.NETWORK_FIREWALL,)
    rationale = (
        "WAF Security requires minimal network exposure. Opening a management "
        "or database port to 0.0.0.0/0 gives every host on the internet a "
        "direct path to the workload."
    )
    remediation = (
        "Restrict the source prefix to a corporate range or private endpoint, "
        "and reach management ports through a bastion instead."
    )
    terraform_fix = 'source_address_prefix = "10.0.0.0/16"  # not "*"'
    params = {"sensitive_ports": [22, 3389, 3306, 5432, 1433, 27017, 6379]}

    def _cidrs(self, resource: Resource) -> List[str]:
        found: List[str] = []
        for key in ("source_address_prefix", "source_address_prefixes"):
            val = resource.after.get(key)
            if isinstance(val, str):
                found.append(val)
            elif isinstance(val, list):
                found.extend(str(v) for v in val)
        for block_name in ("ingress", "allow"):
            blocks = resource.after.get(block_name)
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict):
                        found.extend(str(c) for c in (b.get("cidr_blocks") or []))
        for key in ("source_ranges",):
            val = resource.after.get(key)
            if isinstance(val, list):
                found.extend(str(v) for v in val)
        return found

    def _ports(self, resource: Resource) -> List[int]:
        ports: List[int] = []

        def add(value: object) -> None:
            text = str(value)
            if text.isdigit():
                ports.append(int(text))
            elif "-" in text:
                head = text.split("-")[0]
                if head.isdigit():
                    ports.append(int(head))

        for key in ("destination_port_range", "to_port", "from_port"):
            if key in resource.after:
                add(resource.after[key])
        for key in ("destination_port_ranges",):
            val = resource.after.get(key)
            if isinstance(val, list):
                for v in val:
                    add(v)
        for block_name in ("ingress", "allow"):
            blocks = resource.after.get(block_name)
            if isinstance(blocks, list):
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    add(b.get("from_port"))
                    for p in b.get("ports") or []:
                        add(p)
        return ports

    def check(self, resource: Resource) -> Optional[str]:
        direction = str(resource.after.get("direction", "Inbound")).lower()
        if direction not in ("inbound", "ingress"):
            return None
        access = str(resource.after.get("access", "Allow")).lower()
        if access == "deny":
            return None

        open_cidrs = [c for c in self._cidrs(resource) if is_open_cidr(c)]
        if not open_cidrs:
            return None

        sensitive = {int(p) for p in self.param("sensitive_ports", [])}
        ports = self._ports(resource)
        hit = sorted(set(ports) & sensitive)
        port_range = str(resource.after.get("destination_port_range", ""))
        wide_open = port_range in ("*", "0-65535")

        if hit:
            return (
                "Allows inbound traffic from {} to sensitive port(s) {}.".format(
                    ", ".join(sorted(set(open_cidrs))), ", ".join(str(p) for p in hit)
                )
            )
        if wide_open:
            return (
                "Allows inbound traffic from {} to every port.".format(
                    ", ".join(sorted(set(open_cidrs)))
                )
            )
        return None


@register
class EncryptionAtRest(Rule):
    id = "WAF-SEC-005"
    title = "Data service not encrypted with a customer-managed key"
    pillar = Pillar.WAF_SECURITY
    severity = Severity.MEDIUM
    kinds = (Kind.OBJECT_STORAGE, Kind.MANAGED_DATABASE)
    rationale = (
        "WAF Security recommends customer-managed keys for regulated data so "
        "key rotation and revocation stay under the workload owner's control."
    )
    remediation = "Attach a Key Vault customer-managed key to the service."
    terraform_fix = (
        "customer_managed_key {\n"
        "  key_vault_key_id = azurerm_key_vault_key.data.id\n"
        "}"
    )

    def check(self, resource: Resource) -> Optional[str]:
        explicit_off = resource.after.get("infrastructure_encryption_enabled")
        if explicit_off is not None and not truthy(explicit_off):
            return "infrastructure_encryption_enabled is false."
        has_cmk = any(
            resource.after.get(k)
            for k in (
                "customer_managed_key",
                "kms_key_id",
                "kms_master_key_id",
                "key_vault_key_id",
                "encryption",
            )
        )
        if has_cmk:
            return None
        return (
            "No customer-managed key is configured; the service falls back to "
            "platform-managed keys only."
        )


@register
class HardcodedSecret(Rule):
    id = "WAF-SEC-006"
    title = "Credential written in plain text into the plan"
    pillar = Pillar.WAF_SECURITY
    severity = Severity.CRITICAL
    rationale = (
        "WAF Security requires secrets to come from a secret store at runtime. "
        "A literal password in Terraform ends up in state, in the plan file and "
        "in CI logs."
    )
    remediation = (
        "Move the value into Key Vault and reference it with a data source, "
        "or inject it from a CI secret."
    )
    terraform_fix = (
        "administrator_login_password = "
        "data.azurerm_key_vault_secret.db_password.value"
    )
    params = {
        "fields": [
            "administrator_login_password",
            "admin_password",
            "password",
            "secret_value",
            "value",
            "client_secret",
            "access_key",
        ]
    }

    def check(self, resource: Resource) -> Optional[str]:
        hits: List[str] = []
        for field in self.param("fields", []):
            val = resource.after.get(str(field))
            if isinstance(val, str) and val and not val.startswith("${"):
                # A real literal, not an unresolved reference.
                hits.append(str(field))
        if not hits:
            return None
        return (
            "Plain-text credential supplied in field(s): {}. The value is now "
            "in the plan JSON and in Terraform state.".format(", ".join(hits))
        )


# ======================================================================
# Reliability
# ======================================================================


@register
class StorageRedundancy(Rule):
    id = "WAF-REL-001"
    title = "Production storage uses non-redundant replication"
    pillar = Pillar.WAF_RELIABILITY
    severity = Severity.HIGH
    kinds = (Kind.OBJECT_STORAGE,)
    rationale = (
        "WAF Reliability expects production data to survive the loss of a "
        "datacentre. LRS keeps all three copies in one facility."
    )
    remediation = "Use ZRS or GRS replication for production data."
    terraform_fix = 'account_replication_type = "ZRS"'
    params = {"weak": ["LRS"], "prod_tag_values": ["prod", "production"]}

    def check(self, resource: Resource) -> Optional[str]:
        repl = resource.after.get("account_replication_type")
        if not isinstance(repl, str):
            return None
        if repl.upper() not in [str(w).upper() for w in self.param("weak", [])]:
            return None
        env = str(resource.tags.get("environment", "")).lower()
        prod_values = [str(v).lower() for v in self.param("prod_tag_values", [])]
        if env and env not in prod_values:
            return None  # non-prod may legitimately choose the cheapest tier
        qualifier = "production" if env else "an environment-untagged"
        return (
            "Replication is {} (single datacentre) on {} storage account; a "
            "zone outage would make the data unavailable.".format(repl, qualifier)
        )


@register
class BackupRetention(Rule):
    id = "WAF-REL-002"
    title = "Database has no or insufficient backup retention"
    pillar = Pillar.WAF_RELIABILITY
    severity = Severity.HIGH
    kinds = (Kind.MANAGED_DATABASE,)
    rationale = (
        "WAF Reliability requires a tested recovery path. A database with no "
        "retained backups cannot meet any recovery point objective."
    )
    remediation = "Set backup retention to at least the configured minimum days."
    terraform_fix = "backup_retention_days = 7"
    params = {"minimum_days": 7}

    def check(self, resource: Resource) -> Optional[str]:
        minimum = int(self.param("minimum_days", 7))
        for key in ("backup_retention_days", "backup_retention_period"):
            if key in resource.after:
                try:
                    days = int(resource.after[key])
                except (TypeError, ValueError):
                    continue
                if days < minimum:
                    return (
                        "{} is {} day(s), below the required minimum of {}.".format(
                            key, days, minimum
                        )
                    )
                return None
        return None


@register
class SoftDeleteProtection(Rule):
    id = "WAF-REL-003"
    title = "Secret store has purge protection or soft delete disabled"
    pillar = Pillar.WAF_RELIABILITY
    severity = Severity.HIGH
    kinds = (Kind.SECRET_STORE,)
    rationale = (
        "WAF Reliability treats key material as unrecoverable state: without "
        "soft delete and purge protection, one accidental delete permanently "
        "destroys every secret encrypted under that key."
    )
    remediation = "Enable soft delete retention and purge protection."
    terraform_fix = (
        "soft_delete_retention_days = 7\n"
        "purge_protection_enabled   = true"
    )

    def check(self, resource: Resource) -> Optional[str]:
        problems: List[str] = []
        purge = resource.after.get("purge_protection_enabled")
        if purge is not None and not truthy(purge):
            problems.append("purge protection is disabled")
        retention = resource.after.get("soft_delete_retention_days")
        if retention is not None:
            try:
                if int(retention) < 7:
                    problems.append(
                        "soft-delete retention is only {} day(s)".format(retention)
                    )
            except (TypeError, ValueError):
                pass
        if not problems:
            return None
        return "Key material is destructible: {}.".format(" and ".join(problems))


# ======================================================================
# Cost optimization
# ======================================================================


@register
class OversizedSku(Rule):
    id = "WAF-COST-001"
    title = "Oversized SKU for a non-production workload"
    pillar = Pillar.WAF_COST
    severity = Severity.MEDIUM
    kinds = (Kind.COMPUTE_INSTANCE, Kind.APP_HOSTING, Kind.MANAGED_DATABASE)
    rationale = (
        "WAF Cost Optimization requires right-sizing: dev/test workloads on "
        "premium SKUs burn budget that delivers no production value."
    )
    remediation = "Drop to a burstable/basic SKU for non-production environments."
    terraform_fix = 'size = "Standard_B1s"'
    params = {
        "premium_markers": ["_D", "_E", "_F", "_M", "P1v3", "P2v3", "P3v3",
                            "Premium", "GP_Gen5_8", "xlarge", "2xlarge"],
        "nonprod_values": ["dev", "test", "stage", "staging", "sandbox"],
    }

    def check(self, resource: Resource) -> Optional[str]:
        env = str(resource.tags.get("environment", "")).lower()
        if env not in [str(v).lower() for v in self.param("nonprod_values", [])]:
            return None
        sku = str(
            resource.after.get("size")
            or resource.after.get("sku_name")
            or resource.after.get("instance_type")
            or resource.after.get("instance_class")   # AWS RDS
            or resource.after.get("machine_type")
            or resource.after.get("tier")             # GCP Cloud SQL
            or ""
        )
        if not sku:
            return None
        markers = [str(m) for m in self.param("premium_markers", [])]
        if not any(m.lower() in sku.lower() for m in markers):
            return None
        return (
            'Non-production ("{}") workload provisions the premium SKU "{}".'.format(
                env, sku
            )
        )


@register
class UnattachedOrIdleResource(Rule):
    id = "WAF-COST-002"
    title = "Resource provisioned in a permanently billed mode"
    pillar = Pillar.WAF_COST
    severity = Severity.LOW
    kinds = (Kind.NETWORK_PUBLIC_IP, Kind.APP_HOSTING)
    rationale = (
        "WAF Cost Optimization flags always-on allocations that bill whether "
        "or not they carry traffic; Static public IPs and always-on plans are "
        "the classic examples."
    )
    remediation = (
        "Use Dynamic allocation, or turn the always-on flag off for "
        "non-production workloads."
    )

    def check(self, resource: Resource) -> Optional[str]:
        alloc = str(resource.after.get("allocation_method", ""))
        env = str(resource.tags.get("environment", "")).lower()
        if alloc.lower() == "static" and env in ("dev", "test", "sandbox"):
            return (
                "Static public IP allocated for a {} workload; it bills "
                "continuously even while idle.".format(env)
            )
        if truthy(resource.after.get("always_on")) and env in ("dev", "test"):
            return "always_on is enabled on a {} app service plan.".format(env)
        return None


# ======================================================================
# Operational excellence
# ======================================================================


@register
class DiagnosticsEnabled(Rule):
    id = "WAF-OPS-001"
    title = "Resource ships no diagnostic logs"
    pillar = Pillar.WAF_OPERATIONS
    severity = Severity.MEDIUM
    kinds = (Kind.OBJECT_STORAGE, Kind.MANAGED_DATABASE, Kind.CONTAINER_PLATFORM,
             Kind.APP_HOSTING, Kind.SECRET_STORE)
    rationale = (
        "WAF Operational Excellence requires that every workload component be "
        "observable; a resource with no diagnostic destination cannot be "
        "investigated after an incident."
    )
    remediation = (
        "Attach an azurerm_monitor_diagnostic_setting pointing at the shared "
        "Log Analytics workspace."
    )
    terraform_fix = (
        'resource "azurerm_monitor_diagnostic_setting" "this" {\n'
        "  target_resource_id         = <resource>.id\n"
        "  log_analytics_workspace_id = var.law_id\n"
        "}"
    )
    params = {"observability_tag": "monitoring"}

    def check(self, resource: Resource) -> Optional[str]:
        # A diagnostic setting elsewhere in the plan satisfies this rule; the
        # engine performs that cross-resource check and marks the resource.
        if resource.after.get("_has_diagnostics"):
            return None
        tag = str(self.param("observability_tag", "monitoring"))
        if tag.lower() in {k.lower() for k in resource.tags}:
            return None
        return (
            "No diagnostic setting in this plan targets the resource, so its "
            "logs and metrics are not retained anywhere."
        )


@register
class LockedProviderVersion(Rule):
    id = "WAF-OPS-002"
    title = "Deletion protection disabled on a stateful resource"
    pillar = Pillar.WAF_OPERATIONS
    severity = Severity.MEDIUM
    kinds = (Kind.MANAGED_DATABASE, Kind.OBJECT_STORAGE)
    rationale = (
        "WAF Operational Excellence expects guardrails against accidental "
        "destruction of stateful resources in an automated pipeline."
    )
    remediation = "Enable deletion/termination protection on the resource."
    terraform_fix = (
        "lifecycle {\n  prevent_destroy = true\n}"
    )

    def check(self, resource: Resource) -> Optional[str]:
        for key in ("deletion_protection", "deletion_protection_enabled",
                    "skip_final_snapshot"):
            if key not in resource.after:
                continue
            val = resource.after[key]
            if key == "skip_final_snapshot" and truthy(val):
                return (
                    "skip_final_snapshot is true: deleting this database keeps "
                    "no final snapshot."
                )
            if key != "skip_final_snapshot" and not truthy(val):
                return "{} is disabled on a stateful resource.".format(key)
        return None


# ======================================================================
# Performance efficiency
# ======================================================================


@register
class NoAutoscale(Rule):
    id = "WAF-PERF-001"
    title = "Fixed-capacity deployment with no scaling headroom"
    pillar = Pillar.WAF_PERFORMANCE
    severity = Severity.LOW
    kinds = (Kind.CONTAINER_PLATFORM, Kind.APP_HOSTING)
    rationale = (
        "WAF Performance Efficiency prefers elastic capacity so a workload "
        "meets demand without permanent over-provisioning."
    )
    remediation = "Enable autoscaling / auto scaler on the node pool or plan."
    terraform_fix = (
        "enable_auto_scaling = true\nmin_count = 1\nmax_count = 3"
    )

    def check(self, resource: Resource) -> Optional[str]:
        if resource.kind != Kind.CONTAINER_PLATFORM:
            return None
        pool = resource.get("default_node_pool") or {}
        if not isinstance(pool, dict) or not pool:
            return None
        if truthy(pool.get("enable_auto_scaling")) or truthy(
            pool.get("auto_scaling_enabled")
        ):
            return None
        return (
            "Default node pool runs at a fixed node count with autoscaling "
            "disabled."
        )


# ======================================================================
# Sustainability
# ======================================================================


@register
class LifecycleManagement(Rule):
    id = "WAF-SUS-001"
    title = "Stored data has no lifecycle/tiering policy"
    pillar = Pillar.WAF_SUSTAINABILITY
    severity = Severity.LOW
    kinds = (Kind.OBJECT_STORAGE,)
    rationale = (
        "WAF Sustainability asks that data not be kept hot forever: tiering "
        "cold data to cool/archive storage cuts both the bill and the energy "
        "footprint of the workload."
    )
    remediation = (
        "Set the account access tier to Cool for archival data, or attach a "
        "storage management (lifecycle) policy."
    )
    terraform_fix = 'access_tier = "Cool"'

    def check(self, resource: Resource) -> Optional[str]:
        if "account_tier" not in resource.after and "access_tier" not in resource.after:
            return None
        tier = str(resource.after.get("access_tier", "Hot"))
        purpose = str(resource.tags.get("dataclass", "")).lower()
        if tier.lower() != "hot":
            return None
        if purpose in ("archive", "backup", "cold"):
            return (
                'Data classified "{}" is kept in the Hot access tier, wasting '
                "capacity and energy on data that is rarely read.".format(purpose)
            )
        return None
