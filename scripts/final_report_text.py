"""Text of the final BCSE497J Project-I report.

Kept apart from the layout code so the wording can be edited without touching
the document builder. Block types understood by build_final_report.py:

    ("chapter", "CHAPTER 1", "INTRODUCTION")
    ("h2", "1.1 Background")      ("h3", "3.1.1 Functional")
    ("p", text)                   ("bul", [items])   ("num", [items])
    ("table", caption, header, rows, col_widths_in_inches)
    ("fig", image_key, caption)   ("code", text)
"""

TITLE = "SECOPS AGENT FOR CAFWAF COMPLIANT CLOUD DEPLOYMENTS IN CICD"
TITLE_PLAIN = "SecOps Agent for CAFWAF compliant Cloud Deployments in CICD"
PROGRAMME = "Computer Science and Engineering with Specialization in Information Security"

TEAM = [  # sorted by register number, as the template asks
    ("23BCE0196", "BHUMIKA SINGH"),
    ("23BCE0958", "AKSHAT GUPTA"),
    ("23BCI0262", "GAURISH TODI"),
]
GUIDE = ("Dr. S. M. Farooq", "Associate Professor Grade-1")
HOD = "Rajeshkannan R"
HOD_DEPT = "Computer Science and Engineering with Specialization in Information Security"

ABSTRACT = [
    "Infrastructure as Code has made cloud deployment fast, but it has also made "
    "misconfiguration fast. A storage bucket left open to the internet, a database "
    "with no backups, or a role that can do everything now reaches production "
    "through a pull request, usually without a person ever looking at the "
    "resulting cloud resources. Static scanners such as Checkov and tfsec help, "
    "but they only enforce rules somebody has already written down. Microsoft's "
    "Cloud Adoption Framework (CAF) and Well-Architected Framework (WAF) are "
    "mostly narrative guidance, and most of that guidance has never been turned "
    "into a rule.",

    "This project builds an agent that sits between terraform plan and terraform "
    "apply in a GitHub Actions pipeline. It reads the plan as JSON, maps every "
    "proposed resource onto a cloud-neutral model, and returns one of three "
    "verdicts: pass, remediate or block. The decision comes from three layers. "
    "The first is a set of 22 deterministic rules, each tied to a CAF or WAF "
    "pillar. The second is a reasoning layer that retrieves only the framework "
    "guidance relevant to a resource kind and looks for violations of intent "
    "that no rule covers; its output is verified mechanically before it is "
    "allowed to influence anything. The third is an organisational policy layer "
    "with severity thresholds and waivers that expire.",

    "The agent was exercised on hand-written plans for Azure, AWS and GCP, on "
    "real terraform plan output for all three clouds, and on a live Azure "
    "deployment that cost a few rupees a month. On a benchmark of 42 seeded "
    "violations the rules alone detected 37 (88.1 per cent); adding the "
    "reasoning layer raised this to 42 with no false positive on the compliant "
    "module. We are careful about what that number means: the labels were "
    "written by the same team that wrote the rules, so it works as a regression "
    "suite rather than as independent proof of accuracy. A knowledge audit "
    "against Microsoft's own documentation also uncovered and fixed seven "
    "inaccuracies in our first version. A browser dashboard drives the same "
    "engine, can run a real terraform plan, and exports reports as PDF, JSON, "
    "Markdown and SARIF.",

    "The main contribution is not a new model but a way of using an unreliable "
    "component safely on a control path: retrieval keyed on resource type, "
    "output that cannot invent resources or duplicate a rule, and a default "
    "that keeps reasoning advisory until a team has measured its precision.",
]

KEYWORDS = ("Infrastructure as Code, Terraform, Cloud Adoption Framework, "
            "Well-Architected Framework, DevSecOps, policy as code, "
            "retrieval-augmented reasoning, GitHub Actions")

ABBREVIATIONS = [
    ("AKS", "Azure Kubernetes Service"),
    ("ALZ", "Azure Landing Zone"),
    ("ARM", "Azure Resource Manager"),
    ("CAF", "Cloud Adoption Framework"),
    ("CD", "Continuous Delivery / Deployment"),
    ("CI", "Continuous Integration"),
    ("CLI", "Command-Line Interface"),
    ("CMK", "Customer-Managed Key"),
    ("DFD", "Data Flow Diagram"),
    ("GCP", "Google Cloud Platform"),
    ("HCL", "HashiCorp Configuration Language"),
    ("IaC", "Infrastructure as Code"),
    ("IAM", "Identity and Access Management"),
    ("JSON", "JavaScript Object Notation"),
    ("LLM", "Large Language Model"),
    ("OIDC", "OpenID Connect"),
    ("PR", "Pull Request"),
    ("RAG", "Retrieval-Augmented Generation"),
    ("RBAC", "Role-Based Access Control"),
    ("SARIF", "Static Analysis Results Interchange Format"),
    ("SDG", "Sustainable Development Goal"),
    ("TLS", "Transport Layer Security"),
    ("TRL", "Technology Readiness Level"),
    ("WAF", "Well-Architected Framework"),
]

SYMBOLS = [
    ("R", "Set of resources proposed by one Terraform plan"),
    ("k(r)", "Canonical kind assigned to resource r"),
    ("F₁(r)", "Findings produced for r by the deterministic rules"),
    ("F₂(r)", "Findings produced for r by the reasoning layer"),
    ("c", "Confidence of a finding, between 0 and 1"),
    ("τ", "Minimum confidence a reasoner finding needs (0.6)"),
    ("A(r)", "Titles already reported for r, passed to the reasoner"),
    ("θ", "Severity at which the gate blocks (high)"),
]

CH = []  # list of blocks, filled below


def add(*blocks):
    CH.extend(blocks)


# ----------------------------------------------------------------------
# CHAPTER 1
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 1", "INTRODUCTION"),
    ("h2", "1.1 Background"),
    ("p",
     "A few years ago infrastructure was deployed using a portal interface. Now most teams "
     "deploy using a pull request process to a file written in Terraform. This ensures "
     "consistency, however, any mis-typing in a single line will cause 40 resources to be "
     "created in a single minute. This is due to Terraform providing a natural place to "
     "pause. When you run terraform plan all variables, modules and loops are resolved, "
     "giving a full list of all resources that will be created, updated and deleted. At this "
     "point nothing has actually been created and can be exported as JSON using terraform "
     "show -json [12]. This is the first time we know what changes are being made and the "
     "last time we can freely prevent changes."),
    ("p",
     "Microsoft provide two frameworks to help guide what good looks like. The Cloud Adoption "
     "Framework (CAF) provides guidance on how to successfully adopt Azure within an "
     "organisation. It takes us through Strategy, Plan, Ready, Adopt, Govern, Secure and "
     "Manage [9]. Within the Ready section Azure landing zones are provided. The Azure Well "
     "Architected Framework (WAF) provides guidance on building an individual workload well. "
     "It has 5 pillars of guidance: Reliability, Security, Cost Optimization, Operational "
     "Excellence, Performance Efficiency [10]. Both frameworks are written as prose."),
    ("h2", "1.2 Motivations"),
    ("p",
     "Our motivation began from a dull but costly insight. In previous coursework we had "
     "deployed storage accounts which were accessible from anywhere. This was only found out "
     "because one of our classmates highlighted it. Whilst there was no malicious activity, "
     "none of the tools we had in our pipeline would have mentioned anything."),
    ("p",
     "Current tools for scanning such as Checkov, tfsec and Open Policy Agent are great but "
     "all have one limitation. They enforce rules that have been written by humans. The CAF "
     "and WAF provide thousands of lines of guidance. For example \"Data-tier services should "
     "be accessible from the platform network, and not the public internet\". Trying to "
     "enforce rules for every sentence becomes an endless task."),
    ("p",
     "We also wanted to save some cost. Resources will never be billed if they are blocked at "
     "plan time. As our team was a group of students with a limited amount of Azure credits "
     "this was very important to us and influenced many design decisions."),
    ("h2", "1.3 Scope of the Project"),
    ("p", "This project will cover the following:"),
    ("bul", [
        "Parsing Terraform plan JSON for Azure (azurerm) AWS and Google Cloud. Mapping "
        "resources to a neutral type.",
        "A library of 22 deterministic rules that cover the CAF aligned control areas and WAF "
        "pillars with a rationale written for each rule.",
        "A reasoner to find any violations of framework intent. Along with guardrails to keep "
        "safe on the build path.",
        "Policy layer for the organisation. Thresholds for severity, override rules and "
        "expiry rules.",
        "GitHub Actions workflow that includes the gate. Live deployment on Azure with the gate.",
        "Browser dashboard, reports (PDF, JSON, Markdown, SARIF) and evaluation harness.",
    ]),
    ("p", "This project will not cover:"),
    ("bul", [
        "After deployment scanning of cloud environments. This is covered by Azure Policy and "
        "Defender. We make no claims to replace these.",
        "Machine learning models. There is no labelled corpus available to train on. The gate "
        "needs to be explainable.",
        "Cloud native guidance for both AWS and GCP. The CAF and WAF were written for Azure. "
        "We are applying the intent to AWS and GCP resources and are upfront about this "
        "(Section 7.5).",
    ]),
    ("h3", "Target Users and Deliverables"),
    ("p",
     "The agent is targeted at platform and DevOps engineers looking to have consistency "
     "within their pull request review process. Developers will see the outcome as a comment "
     "on their PR. Platform engineers can configure the behaviour of the agent using a single "
     "policy file. Reviewers will see a clear outcome of blocked or passed."),
    ("p",
     "Deliverables from this project include the agent (CLI and library), GitHub Actions "
     "workflow, Terraform modules, browser dashboard, evaluation harness and documentation. "
     "This includes documentation to show where each piece of framework knowledge came from."),
    ("h3", "Assumptions and Limitations"),
    ("p",
     "Assumptions include that the team use Terraform and can export the plan as JSON. As the "
     "agent reads from the JSON file only. We assume the plan is what matters. As the gate "
     "checks what is going to be created, not what has been created. Our findings are only as "
     "good as the information within the plan. If there is a value that is calculated by "
     "Terraform at apply time (such as a generated resource ID) we won’t be able to "
     "evaluate it so will treat it as unknown."),
    ("p",
     "This is a working prototype. We have validated it with a small live Azure footprint and "
     "plan only modules for AWS and GCP. We have not run it on a large production repo and do "
     "not claim it is ready to be the sole control within a company."),
)

# ----------------------------------------------------------------------
# CHAPTER 2
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 2", "PROJECT DESCRIPTION AND GOALS"),
    ("h2", "2.1 Literature Review"),
    ("p",
     "Research has been done into securing infrastructure as code. Rahman, Parnin and "
     "Williams analysed Puppet scripts and found 7 security smells that appear repeatedly. "
     "These include hard coded secrets and default credentials [1]. Sharma et al previously "
     "showed that there are measurable and prevalent configuration smells within Puppet [8]. "
     "We learnt from this that these issues are commonly seen and mostly simple to fix. "
     "Saavedra and Ferreira expanded on the idea by creating GLITCH, a tool that can detect "
     "smells in multiple IaC languages using a common intermediate representation [2]. We "
     "took inspiration from this. If all tools can be normalised into one model, a single "
     "rule can be applied. Our canonical types do exactly this for cloud providers."),
    ("p",
     "Chiari, De Pascalis and Pradella did a survey on static analysis for IaC. They found "
     "that most tools are rule based and very few look at anything beyond a single resource "
     "[3]. A systematic mapping study was carried out by Rahman et al and came to a similar "
     "conclusion, finding that most work is centred around predicting defects and detecting "
     "smells [4]. Recently Malul et al have used large language models to detect and explain "
     "Kubernetes configurations. This shows the model can reason about intent [5]."),
    ("p",
     "When using a model on the build path we can run into issues of trust. Pearce et al "
     "showed that code generated by an AI assistant often contains vulnerabilities [6]. A "
     "good reason to never trust the output of a model. Lewis et al Retrieval Augmented "
     "Generation provides a practical solution to this issue. By retrieving the relevant "
     "knowledge first and allowing the model to reason over this [7]."),
    ("table", "Table 2.1 Summary of Related Work",
     ["Work", "Description", "Limitation"],
     [
         ["Rahman et al (2019)[1]", "7 security smells for Puppet scripts",
          "Single language and fixed list of smells."],
         ["Saavedra and Ferreira (2022)[2]", "Polyglot smell detection (GLITCH)",
          "Rules only, no framework reasoning."],
         ["Chiari et al (2022)[3]", "Survey of static analysis for IaC",
          "Shows the gap but nothing built."],
         ["Malul et al (2024)[5]", "Detection and remediation of Kubernetes using LLMs",
          "Only works for Kubernetes and model output not verified."],
         ["Checkov, tfsec, OPA", "Rule and policy engines for Terraform", "Only enforces rules."],
         ["Azure Policy, Defender", "Post deployment compliance and posture.",
          "After resource creation and billing."],
     ],
     [1.9, 2.4, 2.0]),
    ("h2", "2.2 Research Gap"),
    ("p",
     "From the above we can see there are three main gaps. Firstly, rule engines cannot "
     "evaluate guidance that hasn’t been encoded. This means a large portion of CAF and "
     "WAF cannot be enforced. Secondly, tools that use language models rarely explain how to "
     "prevent this part causing issues within the pipeline. There is nothing to prevent a "
     "model creating a new resource, repeating a rule or blocking a release based on "
     "guessing. Finally, most work looks at a single cloud. If a team are using both Azure "
     "and AWS they need to run and maintain two sets of checks."),
    ("h2", "2.3 Objectives"),
    ("num", [
        "Create a gate that evaluates the Terraform plan and gives an outcome of pass, "
        "remediate or blocked using a simple exit code.",
        "Have a single rule that can be applied to Azure, AWS and GCP by normalising resources "
        "to a canonical type.",
        "Ensure coverage of CAF aligned governance and WAF pillars by having at least 20 "
        "deterministic rules with a rationale from the framework.",
        "Add a reasoner to handle unencoded intent. With guardrails to ensure it is advisory, "
        "cost effective and cannot break or trick the pipeline.",
        "Quantify the benefit of having a reasoner by evaluating the same plans with and "
        "without. False positives should be carefully reported.",
        "Prove the concept using real infrastructure. Have a live deployment in Azure with the "
        "gate. This was done with a very small budget.",
        "Provide a dashboard and reports so results can be viewed by those who would never "
        "open a terminal.",
    ]),
    ("p",
     "This work aligns with Sustainable Development Goal 9 (Industry, Innovation and "
     "Infrastructure). Target 9.5 looks to improve technological capabilities in industrial "
     "sectors. The project has progressed from TRL 3 (Review 1) to TRL 4 (components "
     "validated in lab environment such as live Azure subscription)."),
    ("h2", "2.4 Problem Statement"),
    ("p",
     "Given a Terraform plan in JSON format for one or more cloud providers, decide if the "
     "proposed resources follow CAF aligned governance and WAF pillars. Provide a clear "
     "explanation for all violations in plain English with a recommended fix. This must be "
     "fast, cost effective and deterministic to run on all pull requests."),
    ("h2", "2.5 Project Plan"),
    ("p",
     "The project was planned over 8 overlapping phases. The timeline ran fairly well, "
     "however the CI integration took longer than expected (see Section 5.2)."),
    ("table", "Table 2.2 Project Phases",
     ["Phase", "Weeks", "Main Owner"],
     [
         ["Problem Formulation and Literature Review", "1-3", "All"],
         ["Architecture Design and Canonical Model", "3-5", "Gaurish, Akshat"],
         ["Plan Parser and Deterministic Rules", "5-8", "Akshat"],
         ["Knowledge Base, Reasoner and Policy Layer", "8-11", "Gaurish"],
         ["CI/CD Integration and Terraform modules", "11-13", "Bhumika"],
         ["Azure Deployment and OIDC Federation", "13-14", "Bhumika"],
         ["Evaluation Harness and Benchmarking", "14-16", "Gaurish"],
         ["Dashboard, Documentation and Reporting", "16-18", "Gaurish, Bhumika"],
     ],
     [3.4, 1.0, 1.9]),
    ("fig", "gantt", "Figure 2.1 Project Timeline"),
    ("h3", "Milestones and Risk Mitigation"),
    ("p", "The project was split into 3 main milestones."),
    ("p",
     "By Review 1 we had completed the problem statement, literature review and initial "
     "design of our system. This put us at TRL 3."),
    ("p",
     "By Review 2 we had a functioning parser, rule engine and reasoner. We had also "
     "completed our first live Azure deployment."),
    ("p",
     "Our Final Review was focused on validating the full framework using real Terraform "
     "plans for all 3 cloud platforms. We had also validated our CI/CD pipeline, added a "
     "dashboard and cross checked our framework’s claims of security and compliance with "
     "Microsoft’s official documentation."),
    ("p",
     "There were 3 main risks that impacted our timeline. Costs of the cloud were kept low by "
     "using free or nearly free resources, setting daily limits on logs ingested and budget "
     "alerts for the month."),
    ("p",
     "Unpredictable nature of language models was mitigated by defaulting to the offline "
     "reasoner and not trusting the output."),
    ("p",
     "Integration issues were the biggest issue. For example setting up authentication "
     "between GitHub Actions and Azure caused several failed pipeline runs before we realised "
     "the issue and solved it."),
    ("p",
     "Extra time was allocated in the final weeks to troubleshoot, integrate and do end to "
     "end testing to ensure our framework was ready for our final demonstration."),
)

# ----------------------------------------------------------------------
# CHAPTER 3
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 3", "TECHNICAL SPECIFICATION"),
    ("h2", "3.1 Requirements"),
    ("h3", "3.1.1 Functional"),
    ("table", "Table 3.1 Functional Requirements",
     ["Requirement ID", "Requirement"],
     [
         ["FR1", "Accept Terraform plan as JSON (using the terraform show -json command). "
                 "Includes handling of byte order mark."],
         ["FR2", "Normalise Azure/AWS/GCP resources into canonical resource types. Force "
                 "replacement = create."],
         ["FR3", "Check all new/updated resources against all rules that are enabled."],
         ["FR4", "Optional reasoning layer to reason about any concerns that aren’t "
                 "covered by rules. No duplicate findings."],
         ["FR5", "Enforce policy based on organisation. Thresholds, rule overrides, expiry "
                 "waivers."],
         ["FR6", "Return pass, remediate or block using exit codes. Return 3 on bad input."],
         ["FR7", "Output Markdown, JSON and SARIF files. Each finding has a fix."],
         ["FR8", "Upload report to pull request. Update in place when pushed again."],
         ["FR9", "Provide dashboard to choose, upload or paste plan. Run real terraform "
                 "plan. Download results."],
     ],
     [1.3, 5.0]),
    ("h3", "3.1.2 Non-Functional"),
    ("bul", [
        "Speed – Typical plan should be evaluated in well under a second. This ensures "
        "gate is never the slowest stage in the pipeline. 16-20ms/fixture.",
        "Cost – Default path is totally free. Language model path is optional but limited "
        "and cached.",
        "Deterministic – Same plan and policy will always produce the same result.",
        "Resilient – If there is a problem with the model, or malformed attributes in the "
        "plan, the report will be degraded but the gate won’t fail.",
        "Explainable – All findings will include the pillar, severity and reason.",
        "Portable – Only uses Python and PyYAML in the core. Can be installed on any runner.",
        "Secure – No long lived credentials stored. Secrets are redacted before any text is "
        "sent from the runner.",
    ]),
    ("h2", "3.2 Feasibility Study"),
    ("h3", "3.2.1 Technical Feasibility"),
    ("p",
     "All the required components exist and are mature. Terraform provides the plan in a "
     "documented format of JSON. GitHub Actions allows any command to be run between stages. "
     "OpenID Connect allows a token to be obtained from Azure for the workflow with no "
     "secrets stored [13]. The reasoning layer communicates with the model endpoint using "
     "normal HTTP. So no new dependencies. One concern we had early on was that the actual "
     "plan output would differ to the manually written fixtures we were initially using. "
     "This was true and highlighted two bugs in reality (5.2). Therefore we added real "
     "Terraform modules for all 3 clouds."),
    ("h3", "3.2.2 Economic Feasibility"),
    ("p",
     "The project was created using a small amount of Azure credits. Cost was a constraint in "
     "the design. The resources required are a resource group, storage account (Kilobytes), "
     "Log Analytics workspace (Hard limit of 0.1GB/day) and diagnostic setting. We avoided "
     "using any virtual machines, Kubernetes clusters, managed SQL, App Service plans or "
     "private endpoints as these are what drain student subscriptions. These are tested using "
     "plan files which are free to use as they are never enacted. A budget alert was added to "
     "notify us when we hit ₹500/month. We have alerts at 50, 80 and 100% (7.4)."),
    ("h3", "3.2.3 Social Feasibility"),
    ("p",
     "A gate can only be useful if teams keep it turned on. We ensured that there were no "
     "common reasons for turning off tools. The report explains all findings with a fix. The "
     "reasoning layer is advisory by default. Soft fail means teams can introduce the tool "
     "gradually if they have a backlog. Waivers have an expiry meaning exceptions aren’t "
     "silently made permanent."),
    ("h2", "3.3 System Specification"),
    ("h3", "3.3.1 Hardware Specification"),
    ("table", "Table 3.2 Hardware",
     ["Item", "Specification"],
     [
         ["Development laptops", "Team members’ personal laptops using Windows 11"],
         ["CI Runner", "GitHub hosted ubuntu-latest runner (Free tier)"],
         ["Cloud", "Azure Subscription with Central India region. No compute resources"],
         ["Minimum requirement", "Any device running Python 3.11 with ~100MB free space."],
     ],
     [2.2, 4.1]),
    ("h3", "3.3.2 Software Specification"),
    ("table", "Table 3.3 Software",
     ["Component", "Version/Choice", "Purpose"],
     [
         ["Python", "3.11 (CI), 3.13 (Local)", "Agent, CLI, Dashboard Backend"],
         ["PyYAML, pytest", "6.0+, 7.4+", "Policy, Knowledge Base, Testing"],
         ["Terraform", "1.9.5 (CI)", "Used to generate plan JSON"],
         ["Providers", "Azurerm 4, Aws 5, Google 5", "Resources Being Tested"],
         ["GitHub Actions", "Setup-terraform v3, Azure/login v2", "Pipeline"],
         ["React 18, Babel", "Loaded from CDN", "Dashboard Front-end"],
         ["Azure OpenAI/Anthropic", "Optional, Default gpt-4o-mini", "LLM Reasoner"],
     ],
     [1.7, 2.2, 2.4]),
)

# ----------------------------------------------------------------------
# CHAPTER 4
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 4", "DESIGN APPROACH AND DETAILS"),
    ("h2", "4.1 System Architecture"),
    ("p",
     "The agent is one stage of the pipeline. The plan is generated using terraform plan. The "
     "workflow then saves the plan as JSON and runs the agents command line. The agent parses "
     "the JSON file into normalised resources. The agent then processes the resources through "
     "3 layers. The exit code determines whether terraform apply can be run."),
    ("fig", "arch", "Figure 4.1 System Architecture & Position in Pipeline"),
    ("p",
     "We considered other options for where to run the check. However we decided not to. "
     "Scanning .tf files wouldn’t give us resolved variables as we’re not looking at "
     "real resources. Scanning after apply using Azure Policy or Defender means we’ve "
     "already spent money and had exposure. Manually reviewing isn’t scalable for numerous "
     "pull requests across 3 clouds. We have a normaliser (layer 0). Using a table to map "
     "resources to canonical resource types. For example, azurerm_storage_account, "
     "aws_s3_bucket and google_storage_bucket would all become object_storage. If the "
     "resource type is unknown we use heuristics based on the substring. The order of these "
     "heuristics is important. If the resource name contains sql then we need to check for "
     "firewalls before databases. This bug was encountered and is covered by a regression "
     "test."),
    ("table", "Table 4.1 Canonical Resource Types and Examples",
     ["Canonical Type", "Azure", "AWS", "GCP"],
     [
         ["object_storage", "azurerm_storage_account", "aws_s3_bucket", "google_storage_bucket"],
         ["managed_database", "azurerm_mssql_server", "aws_db_instance", "google_sql_database_instance"],
         ["network_firewall", "azurerm_network_security_rule", "aws_security_group", "google_compute_firewall"],
         ["iam_binding", "azurerm_role_assignment", "aws_iam_role_policy", "google_project_iam_member"],
         ["secret_store", "azurerm_key_vault", "aws_kms_key", "google_kms_crypto_key"],
         ["compute_instance", "azurerm_linux_virtual_machine", "aws_instance", "google_compute_instance"],
     ],
     [1.4, 1.8, 1.4, 1.7]),
    ("p",
     "Rules (Layer 1). Rules are small classes with an id, mandatory pillar, severity, "
     "resource types to check, check method and reason. As pillar is a mandatory piece of "
     "information in a finding we can’t have un categorised findings. Reasoner (Layer 2) "
     "(5.1). Policy (Layer 3)."),
    ("h2", "4.2 Design"),
    ("h3", "4.2.1 Data Flow Diagram"),
    ("fig", "dfd", "Figure 4.2 Data Flow Diagram (Level 1)"),
    ("p",
     "Data is inputted as plan JSON and policy YAML. The parser outputs resources. The rules "
     "engine and reasoner output findings. Findings are filtered & categorised by the policy. "
     "The renderers output the 3 reports. The knowledge base is a read only store for the "
     "reasoner."),
    ("h3", "4.2.2 Use Case Diagram"),
    ("fig", "usecase", "Figure 4.3 Use Case Diagram"),
    ("p",
     "We have 4 types of users. Developers who open pull requests, Platform Engineers who own "
     "the policy file, Reviewers who approve deployment to production and Evaluators who run "
     "the benchmark."),
    ("h3", "4.2.3 Class Diagram"),
    ("fig", "class", "Figure 4.4 Class Diagram"),
    ("p",
     "The data model consists of Resource, Finding and GateResult. Rules are the base class "
     "for our 22 rule classes. Reasoner is the base class for our offline, LLM and disabled "
     "versions. Having the reasoner behind an interface means we can use the offline version "
     "as an experimental control for the LLM version."),
    ("h3", "4.2.4 Sequence Diagram"),
    ("fig", "sequence", "Figure 4.5 Sequence of One Run of the Gate"),
    ("p",
     "3 Layers – There are 3 layers due to the previous layers not being able to do "
     "something. Rules are fast, free and precise but only for what has been written down. "
     "The reasoner covers intentions but can be incorrect and therefore can’t be trusted "
     "to make the decision. The policy takes the findings and provides a decision that can be "
     "tuned by the organisation. Thresholds for the findings can be set to match their risk "
     "appetite and exceptions have a reason and expiry. If these were all combined into one "
     "component we wouldn’t be able to tell why the build was blocked."),
    ("p",
     "Safe Defaults – There were several decisions made to ensure the agent fails safely. "
     "A finding can’t be created without a framework pillar as this field is mandatory in "
     "our data model. No findings will ever be raised for missing or unknown values. If the "
     "reasoner can’t be reached the gate will still provide the result from the rules and "
     "provide a note. Reasoner findings are advisory and can be turned off by an organisation "
     "once their precision has been measured. The exit code is the only agreement we have "
     "with the pipeline. The agent can be easily integrated into another CI system by running "
     "one command and reading one number."),
    ("p",
     "Security & Cost – No long lived credentials are stored. Short lived credentials are "
     "obtained from Azure using OpenID Connect in the pipeline. Before any resource "
     "descriptions are sent to a language model any sensitive fields are removed and long "
     "values are truncated. This protects data but also keeps the prompt small (cost). "
     "Responses are cached using a hash of the prompt so we’ll never pay twice for an "
     "unchanged plan."),
)

# ----------------------------------------------------------------------
# CHAPTER 5
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 5", "METHODOLOGY AND TESTING"),
    ("h2", "5.1 Module Description"),
    ("h3", "Module 1: Parse and Create Canonical Model (Akshat)"),
    ("p",
     "This module will parse the resource_changes section of plan. It will ignore the noops "
     "and read-only resources and just log an action. If there is a delete and create change "
     "within the resource it will log this as a replace to allow the create rules to still "
     "trigger. Nested blocks in Terraform are represented as lists with only 1 element. The "
     "helper function has been created to abstract away this complexity. This means all rules "
     "check for ‘network_rules.default_action’. The module will parse the provider "
     "block to allow resources to inherit the region in AWS/GCP. The region would not be "
     "shown in a real plan."),
    ("h3", "Module 2: Deterministic Rules (Akshat)"),
    ("p",
     "There are 22 rules in total. With 7 relating to CAF and 15 relating to WAF. These have "
     "been grouped into categories as shown below in Table 5.1. All of the rules include "
     "reasoning that has been validated through testing. The thresholds for approved regions, "
     "mandatory tags, minimum back up time etc. are all taken from the policy file."),
    ("table", "Table 5.1 Catalogue of Rules",
     ["Category", "Number of Rules", "Example"],
     [
         ["CAF Governance", "2", "Mandatory Tags; Naming Convention"],
         ["CAF Landing Zone", "3", "Approved Region; Public Network Access; Unjustified Public IP"],
         ["CAF Cost Management", "1", "Billable Resource Not Tagged With Cost Centre"],
         ["CAF Identity", "1", "Owner/Wildcard Grants"],
         ["WAF Security", "6", "HTTPS Only; TLS 1.2; No Anonymous Access; Open Ports; Keys; Hardcoded Secrets"],
         ["WAF Reliability", "3", "Replication; Backup Retention; Key Vault Purge Protection"],
         ["WAF Cost Optimisation", "2", "Premium SKU (Non Prod); Always On Allocations"],
         ["WAF Operational Excellence", "2", "Diagnostic Logs; Deletion Protection"],
         ["WAF Performance Efficiency", "1", "Autoscaling On Node Pools"],
         ["WAF Sustainability", "1", "Hot Tier Archive Data (AWS WAF Lens)"],
     ],
     [2.0, 1.1, 3.2]),
    ("h3", "Module 3: Reasoning (Gaurish)"),
    ("p",
     "These rules determine if any of the rules have been broken. This determines if any "
     "rules have been broken based on the intention of the framework. It follows this "
     "algorithm:"),
    ("num", [
        "Lookups: The canonical kind of the resource is looked up in the knowledge base. This "
        "tells us which pillars to look at and gives us a quick list of what to look for. This "
        "lookup is done from the type system so is deterministic and can be audited.",
        "Deduplication: Remove rules with the same title as rules already reported from the "
        "rule engine.",
        "Reasoning: The offline reasoning will perform some manually created probes. These "
        "probes are specific to the kind of resource and pillars from step 1. The LLM will "
        "create a redacted/summary of the resource description. This along with the guidance "
        "from step 1 and titles already reported will be sent to the model. The model will be "
        "run at temp=0 and only return JSON. The responses will be cached depending on the "
        "model name and prompt meaning there will never be a cost for the same plan.",
        "Validating: Any findings for resources not in the plan are removed. Any findings "
        "below the confidence threshold of τ = 0.6 are removed. Any unknown "
        "pillars/severities will be changed to safe defaults. No resources will be created by "
        "a model.",
        "Governance: Any findings from the reasoner will be advisory in the policy. The "
        "reasoner findings will only be enforced if fail_on_reasoner_findings is set to true "
        "in the organisation.",
    ]),
    ("p",
     "The knowledge base is a YAML file containing the principles of the frameworks per "
     "pillar. After auditing (Section 7.5), all pillars have a note indicating where they "
     "come from in the CAF/WAF. It clearly states that Sustainability is an AWS pillar, and "
     "the 4 CAF labels are our own control areas."),
    ("h3", "Module 4: Policy (Gaurish)"),
    ("p",
     "The severity of the gate is stated as High. The severity of the warnings is Medium. "
     "Rules can be turned off/tuned. Waivers will have a reason, pattern and expiry. When a "
     "waiver has expired the finding will be returned and the report will say ‘reasoner "
     "found an expired waiver’."),
    ("h3", "Module 5: Reporting & CLI (Bhumika)"),
    ("p",
     "A single result object is returned. This has been formatted into Markdown for pull "
     "requests, JSON for tools and SARIF 2.1.0 for the Security Tab on GitHub [14]. An exit "
     "code will also be returned. The exit code could be 0, 1, 2 or 3. This is the full "
     "integration with CI. There is also a soft fail flag for onboarding a repo with "
     "violations."),
    ("h3", "Module 6: CI/CD & Infrastructure (Bhumika)"),
    ("p",
     "The workflow will run the unit tests first. We cannot trust the gate if it fails its "
     "own tests. 4 modules are run in a matrix. The first module is the compliant Azure "
     "workload. This module must pass. The next 3 modules are seeded with misconfigurations. "
     "These modules must be blocked. If any of the seeded modules are not blocked then the "
     "build will fail. This can also be seen as a regression test for the gate. Apply will "
     "only be run on the main branch. This is protected as it is a production environment so "
     "requires human approval."),
    ("h3", "Module 7: Dashboard & Evaluation (Gaurish)"),
    ("p",
     "The dashboard is a simple web server made using the standard library. It uses a React "
     "page. This will evaluate a selected plan that has been uploaded, dropped or pasted. It "
     "will show the result, how long each layer took, a table of resources and any findings "
     "with fixes. It can also run a real terraform init, plan and show on the example "
     "modules. The report can be downloaded in PDF, JSON, Markdown or SARIF. The evaluation "
     "harness will run all labelled plans twice. Once without the reasoner and once with."),
    ("h2", "5.2 Testing"),
    ("p",
     "There are 69 automated tests. All tests passed. The parser tests ensure the providers "
     "are being detected, mapping of kinds, firewall to database mistake and replaces. All "
     "rules have been tested. They should trigger when violated and not trigger when "
     "compliant. We don’t want the gate to cry wolf. The engine tests ensure the result "
     "is correct, waivers expire, thresholds are changed, the 2 layers work together with no "
     "duplication, 3 reports are returned, exit codes and malformed input."),
    ("p",
     "Most of our learning was done through running the code. Table 5.2 shows the errors that "
     "were only raised when using real tools and infrastructure."),
    ("table", "Table 5.2 Errors encountered when using real system",
     ["Error", "Cause", "Fix"],
     [
         ["Byte Order Mark in Plan File", "Plans created using PowerShell were being rejected "
          "due to invalid JSON.", "Read with utf-8-sig."],
         ["Shared Keys Disabled", "403 error when refreshing storage account in Azure.",
          "Enable Azure AD auth in provider."],
         ["Gitignore Comments", "terraform.tfvars wasn’t being ignored.",
          "Comments added to new line."],
         ["Empty NIC List", "terraform validate failed in CI when running seeded module.",
          "Added minimal network and NIC."],
         ["Provider Schema Drift", "Diagnostic setting was different between live and code.",
          "Used enabled_metric. No changes in plan."],
         ["OIDC Subject Mismatch", "Azure login failed in runs 1-6. Error AADSTS700213.",
          "Added Federated Credentials for repositories ID based subject."],
         ["Region Only in Provider", "Region rule never triggered on real AWS/GCP plans.",
          "Parser will use region from provider."],
     ],
     [1.6, 2.7, 2.0]),
    ("p",
     "The OIDC error took the longest to fix. We assumed the repository secrets were wrong "
     "but they were not. From looking at the workflow logs we realised GitHub were now "
     "creating a token with a numeric subject using the repo and owners IDs. Our Federated "
     "Credentials in Azure were created using name based subject. Adding 3 Federated "
     "Credentials for ID based subjects fixed the login issue for both compliant and seeded "
     "Azure jobs."),
    ("h3", "Evaluation:"),
    ("p",
     "An ablation test was performed. Each labelled plan was run twice with the same policy. "
     "Once without the reasoner and once with. This means any difference in detection can be "
     "attributed to the reasoner. We only count the violation as detected if the correct "
     "pillar has been found on the correct resource. This means any noisy engine will not "
     "score highly as it will report everything."),
    ("p",
     "False positives were counted separately on the compliant module. If the gate is "
     "blocking good code it will be turned off by the team who own it. The harness will also "
     "record how long each run took."),
    ("p",
     "Results can be replicated from the repository by running a few commands. The test suite "
     "can be run using python -m pytest tests -q. The benchmark can be run using python "
     "scripts/benchmark.py. A single plan can be evaluated using python -m agent.cli evaluate "
     "--plan. The dashboard can be run using python -m dashboard.server."),
    ("p",
     "The real plan results were achieved by running Terraform on the example modules. As we "
     "are using dummy credentials and just planning we do not need a cloud account for "
     "AWS/GCP. All checks are automatically applied to every push in GitHub Actions so our "
     "results are verified."),
    ("p",
     "This taught us the importance of checking the claims of the token and ensuring "
     "federated identity configurations are correct. It also showed us how changes to the "
     "GitHub token subjects can cause an Azure pipeline to fail despite being correctly "
     "configured. Diagnosing and configuring using identities is very important to ensure a "
     "reliable integration."),
)

# ----------------------------------------------------------------------
# CHAPTER 6
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 6", "PROJECT DEMONSTRATION"),
    ("p",
     "This section will guide you through the demonstration. Throughout this we have 3 "
     "resources. One from each team member and one from each cloud. gaurish_s_resourceA is a "
     "storage account in Azure with TLS 1.0, anonymous access and local redundancy in "
     "production. akshat_s_resourceB is a bucket in AWS with public-read ACL in an unapproved "
     "region. bhumika_s_resourceC is a firewall rule in GCP allowing SSH access to the "
     "internet."),
    ("h3", "Case 1: Compliant Plan"),
    ("p",
     "The compliant Azure workload is sent to the dashboard. We get a result of PASS with an "
     "exit code of 0 and no findings. We can also see how long each layer took to process."),
    ("fig", "shot_pass", "Figure 6.1 Dashboard: Compliant workload = PASS"),
    ("h3", "Case 2: 3 Resources 3 Clouds 1 Gate"),
    ("p",
     "Our team demonstration plan returned a result of BLOCK with 14 findings. 12 from rules "
     "and 2 from reasoner. We can see that there are 3 different providers but 2 canonical "
     "kinds."),
    ("fig", "shot_team_top", "Figure 6.2 Dashboard: Results, Trace & Summary for 3 Cloud Plan"),
    ("fig", "shot_team_findings", "Figure 6.3 Dashboard: Findings split by resource with source tags"),
    ("h3", "Case 3: Reasoning Layer"),
    ("p",
     "If we turn off the reasoning layer we can see the orange section is gone and 2 "
     "findings. (ResourceB versioning disabled, ResourceA Shared Keys Enabled). The result is "
     "still BLOCK as the rules are finding critical issues. The reasoner adds extra "
     "coverage."),
    ("fig", "shot_off", "Figure 6.4 Dashboard: Reasoning Layer Off"),
    ("h3", "Case 4: Real terraform plan"),
    ("p",
     "By clicking 1 button on the dashboard terraform will be initialised, planned and shown "
     "on the AWS example module. It will also be sent to the gate."),
    ("p",
     "As we are using dummy credentials and just planning we are not using any AWS account."),
    ("p",
     "This took around 10 seconds to run. The gate found 21 issues across 6 resources. The "
     "reasoner did not contribute any findings. This is an honest result and discussed in "
     "Section 7.2."),
    ("fig", "shot_tf", "Figure 6.5 Dashboard: Real Pipeline Run on AWS Module"),
    ("h3", "Case 5: Continuous Integration (GitHub)"),
    ("p",
     "Every push will run the workflow. In Figure 6.6 we can see run 7. All jobs have passed "
     "including the unit test job and all 4 plan/gate jobs. The colour of the seeded job is "
     "green this means that the gate blocked it correctly. The apply job is waiting for a "
     "reviewer. This is the second point of control."),
    ("fig", "gh_run", "Figure 6.6 GitHub Actions: Gate Jobs Passed, Apply Waiting For Review"),
    ("fig", "gh_approve", "Figure 6.7 Approval Needed From Reviewer For Production Environment"),
    ("h3", "Case 6: Live Azure Footprint"),
    ("p",
     "The compliant module was applied once. After passing the plan through the gate we can "
     "see in the portal that there are 2 resource groups (state-backend and workload) in "
     "Central India."),
    ("fig", "azure_rg", "Figure 6.8 Resource Groups Used In Project From Azure Portal"),
    ("h3", "Case 7: Download Report"),
    ("p",
     "All results can be downloaded as a PDF using the print function in the browser. They "
     "can also be downloaded as JSON, Markdown or SARIF. The Markdown is the exact text we "
     "posted on the pull request. The SARIF file is what gets ingested into GitHub Security "
     "Tab."),
)

# ----------------------------------------------------------------------
# CHAPTER 7
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 7", "RESULT AND DISCUSSION (COST ANALYSIS AS APPLICABLE)"),
    ("h2", "7.1 Detection Results"),
    ("p",
     "A data set of 42 violations was manually annotated. Both with and without the "
     "reasoning layer enabled, the Azure, AWS and GCP plans were run. Violations were counted "
     "if the correct pillar was identified on the correct resource."),
    ("table", "Table 7.1 Detection Results",
     ["Plan", "Seeded", "Rules only", "Rules + Reasoning", "Verdict"],
     [
         ["Azure", "28", "25", "28", "BLOCK"],
         ["AWS", "8", "7", "8", "BLOCK"],
         ["GCP", "6", "5", "6", "BLOCK"],
         ["Totals", "42", "37 (88.1%)", "42 (100%)", "—"],
         ["Compliant Azure (False Positives)", "0", "0", "0", "PASS"],
     ],
     [2.1, 0.8, 1.1, 1.5, 0.9]),
    ("fig", "bench", "Figure 7.1 Detection Results with and without reasoning layer"),
    ("p",
     "Across all clouds similar trends can be seen. All the plans have found the highest "
     "amount of violations when using just the deterministic rules (25/28 Azure, 7/8 AWS, "
     "5/6 GCP). This is expected as the rules are designed for the specific violations. The "
     "rest of the violations have been found when using the reasoning layer. All the plans "
     "have a verdict of BLOCK with and without the reasoning layer. This shows that the "
     "reasoning layer had no impact on the decision but has increased the percentage of the "
     "issue covered. This is how an advisory layer should work, so by default we do not "
     "allow it to decide to build."),
    ("p",
     "The missing violations were all related to the intent of decisions. Whether it is "
     "acceptable to have a database firewall set to 0.0.0.0 to 255.255.255.255, whether a "
     "virtual machine should have an availability construct and whether the vault should "
     "have role based access instead of access policies. All of these can be answered by the "
     "framework using text. They can be written as individual rules. The reasoning layer can "
     "cover these whilst the rules are being written."),
    ("p",
     "An important aspect to consider is the precision of the results. Any tool that flags "
     "all resources will always return 100%. However there were no false positives on the "
     "compliant module meaning the extra findings are not noise. Another important aspect is "
     "how fast the results are. Each plan took 16-20ms to run. This means there is no "
     "significant delay in the gate. Therefore there is no cost associated with using the "
     "gate on every pull request. This makes it cheaper to prevent issues."),
    ("fig", "shot_bench", "Figure 7.2 Benchmark Tab"),
    ("p",
     "The reasoning layer found 5 violations. These were an IPv4 database firewall rule, VM "
     "without availability construct, Key Vault using Access Policies instead of RBAC and no "
     "versioning on AWS and GCP buckets. This took 16-20ms to run on a Laptop, meaning "
     "nothing significant is added to the pipeline."),
    ("h2", "7.2 What the numbers mean"),
    ("p",
     "It is important to mention some key points. Firstly the annotations and rules were "
     "created by the same people. The 5 reasoning probes were also created knowing what "
     "violations were missed. This means getting 100% is purely down to regression. This "
     "does not mean that 100% of issues will be found in someone else's code. It means there "
     "were no issues. Secondly, the 5 violations found using the reasoning layer came from "
     "the offline reasoner with manual probes. The LLM path has been implemented, guard "
     "raied and unit tested but has not been benchmarked. Finally, the real terraform plans "
     "do not behave the same. The reasoning layer did not find any violations in the real "
     "AWS plans because the real provider does not expose the versioning attribute in the "
     "same way. However, the reasoning layer did find 5 findings in the real Azure module. "
     "This was useful to show why it was important to test using real plans."),
    ("table", "Table 7.2 Real terraform plan results",
     ["Module", "Resources", "Findings (Reasoning)", "Verdict", "Time"],
     [
         ["examples/terraform/aws_noncompliant", "6", "21 (0)", "BLOCK", "~10s"],
         ["examples/terraform/gcp_noncompliant", "4", "14 (0)", "BLOCK", "<30s"],
         ["examples/terraform/noncompliant (Azure)", "12", "47 (5)", "BLOCK", "~21s"],
     ],
     [2.6, 0.9, 1.5, 0.7, 0.9]),
    ("p", "Most of this time is spent running Terraform. The gate only takes tens of milliseconds."),
    ("h2", "7.3 Continuous Integration Results"),
    ("p",
     "The first 6 runs failed for the reasons shown in Table 5.2. After the issues were fixed "
     "and the AWS and GCP modules added to the matrix, Run 7 passed the unit test job and all "
     "4 plan/gate jobs. The apply job stopped at the production approval as intended."),
    ("h2", "7.4 Cost Analysis"),
    ("table", "Table 7.3 Cost of deployed artefacts",
     ["Resource", "Configuration", "Monthly Cost"],
     [
         ["Resource groups (2)", "State backend, workload", "Free"],
         ["Storage Account (State)", "Standard_LRS, versioned, KBs", "~₹2"],
         ["Storage Account (Workload)", "Standard_LRS, public access disabled", "~₹2"],
         ["Log Analytics Workspace", "PerGB2018, 0.1GB daily limit, 30 days", "Free tier"],
         ["Diagnostic Settings, App Registration, Role Assignments", "OIDC, no secret", "Free"],
         ["GitHub Actions", "Free tier runner", "Free"],
         ["Total", "", "~ ₹4"],
     ],
     [2.3, 2.5, 1.5]),
    ("p",
     "The artefacts the gate checks for (VMs, SQL servers, Kubernetes clusters) are never "
     "deployed. They are only in the plan files. If the plan is blocked nothing will be "
     "created. This means we are saving the full cost of the bad artefact. The subscription "
     "is also protected with a budget of ₹500 per month. Alerts are set at 50%, 80% and "
     "100%. This type of subscription would not accept the az consumption budget command so "
     "the budget had to be created using the same REST API."),
    ("h2", "7.5 Knowledge Accuracy"),
    ("p",
     "At the end of the project, the accuracy of our framework claims was checked against the "
     "Microsoft Learn documentation. Some of the claims were inaccurate. Below are the "
     "changes made. A full list can be found in the repo (docs/knowledge-sources.md)."),
    ("table", "Table 7.4 Changes made after checking Microsoft documents",
     ["Issue", "Change"],
     [
         ["Sustainability was claimed to be a pillar within Microsoft WAF.",
          "Azure WAF actually has 5 exact pillars. Claimed to be an AWS pillar and extra lens."],
         ["CAF pillars do not exist.",
          "CAF has 7 phases. Our 4 labels are documented as CAF aligned control areas. These "
          "map to the phases."],
         ["Key Vault rule claimed to look for soft-delete disable.",
          "This is no longer allowed on Azure. Now looks for purge protection [11]."],
         ["Region rule only knew Azure regions.",
          "Compliant AWS/GCP regions flagged. Approved lists for each cloud."],
         ["IAM rule looked for \"\" in policy.",
          "Policy is parsed and only Allow with Action flagged."],
         ["Contributor role flagged on resource group.",
          "This is how we have contributor in our own CI. Contributor role is only flagged on "
          "subscription/management group."],
         ["Unsupported stat for public buckets.", "Changed wording."],
     ],
     [3.2, 3.1]),
    ("p",
     "There are 2 things to note here. Using Microsoft's frameworks for AWS & GCP is an "
     "extrapolation of their intent. AWS & Google have their own. The thresholds (7 days "
     "backups, approved regions) are our choice and can be changed in the policy file. This "
     "is not a Microsoft requirement."),
    ("h2", "7.6 Limitations"),
    ("bul", [
        "Diagnostics rule can be satisfied by adding a tag. No logs are shipped. The resources "
        "and diagnostic settings are linked by name as we do not know what the id should be.",
        "Hardcoded secret rule cannot tell the difference between literal and injected from CI "
        "secret. Both are present in plan and state. This is the actual risk.",
        "Only the offline reasoner has been measured. We would need independent plans and a "
        "baseline such as Checkov to fairly evaluate the LLM path.",
        "Gate only sees one plan. Cannot detect violations that only appear in multiple "
        "Terraform states.",
    ]),
)

# ----------------------------------------------------------------------
# CHAPTER 8
# ----------------------------------------------------------------------
add(
    ("chapter", "CHAPTER 8", "CONCLUSION"),
    ("p",
     "We aimed to create a framework aware reviewer in the only place we can stop a bad cloud "
     "resource for free. The gate works. It parses real terraform plans for Azure, AWS and "
     "GCP. 22 rules are applied as explained in this report. A bounded reasoning layer is "
     "also added. The gate enforces our organisations policy. It sits in the pipeline "
     "between plan and apply. The pipeline is green on GitHub. Protecting our live Azure "
     "deployment which costs ~ ₹4 per month."),
    ("p",
     "The most valuable lessons learnt were the practical ones. We found issues that our "
     "fixtures were not showing by testing against real tools. Issues such as byte order "
     "mark and regions that exist on the provider. Checking our knowledge against "
     "Microsoft's documentation showed some claims were simply wrong. Fixing these has "
     "increased trust in the project. The most successful design principle was treating the "
     "reasoning component as untrusted. We verified, bounded and made it advisory."),
    ("h2", "Future Work"),
    ("p",
     "Benchmark the LLM reasoner against the offline reasoner using independent set of "
     "vulnerable terraform repos. Report precision and recall. Add AWS & GCP native guidance "
     "(their own well architected frameworks). Create separate knowledge bases. Fix "
     "diagnostic settings to reference configuration from plan. Support Bicep & Pulumi plans "
     "by adding more parsers. Create a conference paper around using a model safely on a "
     "build path. The main result is the independent evaluation."),
)

REFERENCES = [
    "Rahman A, Parnin C, Williams L. (2019) The seven sins: security smells in infrastructure "
    "as code scripts. In: Proceedings of the 41st International Conference on Software "
    "Engineering (ICSE). IEEE/ACM.",
    "Saavedra N, Ferreira JF. (2022) GLITCH: automated polyglot security smell detection in "
    "infrastructure as code. In: Proceedings of the 37th IEEE/ACM International Conference on "
    "Automated Software Engineering (ASE). ACM.",
    "Chiari M, De Pascalis M, Pradella M. (2022) Static analysis of infrastructure as code: a "
    "survey. In: 2022 IEEE 19th International Conference on Software Architecture Companion "
    "(ICSA-C). IEEE.",
    "Rahman A, Mahdavi-Hezaveh R, Williams L. (2019) A systematic mapping study of "
    "infrastructure as code research. Information and Software Technology. 108, pp.65-77.",
    "Malul E, Meidan Y, Mirsky Y, Elovici Y. (2024) GenKubeSec: LLM-based Kubernetes "
    "misconfiguration detection, localization, reasoning, and remediation. arXiv preprint.",
    "Pearce H, Ahmad B, Tan B, Dolan-Gavitt B, Karri R. (2022) Asleep at the keyboard? "
    "Assessing the security of GitHub Copilot’s code contributions. In: 2022 IEEE "
    "Symposium on Security and Privacy (SP). IEEE.",
    "Lewis P, et al. (2020) Retrieval-augmented generation for knowledge intensive NLP tasks. "
    "Advances in Neural Information Processing Systems. 33.",
    "Sharma T, Fragkoulis M, Spinellis D. (2016) ‘Does your configuration code smell?’ "
    "In: Proceedings of the 13th International Conference on Mining Software Repositories "
    "(MSR). ACM.",
    "Microsoft. (2026) Cloud Adoption Framework for Azure - Overview and Azure Landing Zones. "
    "Microsoft Learn. Available from: https://learn.microsoft.com/azure/cloud-adoption-framework/ "
    "(Accessed 27 October 2026).",
    "Microsoft. (2026) Microsoft Azure Well-Architected Framework - Pillars. Microsoft Learn. "
    "Available from: https://learn.microsoft.com/azure/well-architected/pillars (Accessed 27 "
    "October 2026).",
    "Microsoft. (2026) Azure Key Vault soft-delete overview. Microsoft Learn. Available from: "
    "https://learn.microsoft.com/azure/key-vault/general/soft-delete-overview (Accessed 27 "
    "October 2026).",
    "HashiCorp. (2026) Terraform JSON Output Format. Available from: "
    "https://developer.hashicorp.com/terraform/internals/json-format (Accessed 27 October 2026).",
    "GitHub. (2026) About security hardening with OpenID Connect. GitHub Docs. Available from: "
    "https://docs.github.com/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect "
    "(Accessed 27 October 2026).",
]

APPENDIX_INTRO = (
    "The listings below are excerpts from the repository "
    "(github.com/GAURISHTODI/Agent-SecOps). The first is the orchestration core, the second "
    "is one deterministic rule after the audit fixes, and the third is the verification step "
    "of the LLM reasoner."
)

# List of figures: derived from the figure blocks so it always matches the captions.
FIGURES = [
    (b[2].split()[1], b[2].split(" ", 2)[2]) for b in CH if b[0] == "fig"
]
