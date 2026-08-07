# Cluster Zero (Terraform / Azure AKS) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision the regional "cluster zero" — an Azure AKS cluster with ArgoCD installed — via dedicated Terraform, outside the GitOps cycle, so that all subsequent provisioning can become GitOps-driven.

**Architecture:** A single Terraform root at `infra/terraform/cluster-zero/` creates a resource group and an AKS cluster (SystemAssigned identity, OIDC issuer + workload identity enabled), then installs ArgoCD onto it via the `helm` provider wired to the cluster's kubeconfig output. Crossplane and everything else are intentionally **not** installed here — they arrive later via GitOps (app-of-apps), matching the design spec's minimal cluster-zero boundary. This mirrors the already-validated local k3d exercise (`scripts/cluster-zero/`) but targets real Azure.

**Tech Stack:** Terraform 1.14.x, `hashicorp/azurerm` ~> 4.x, `hashicorp/helm` ~> 2.17, `hashicorp/kubernetes` ~> 2.35, Azure CLI 2.89, tflint. ArgoCD Helm chart `argo/argo-cd` v10.2.1 (same version as the local exercise).

## Global Constraints

- Terraform boundary is **AKS + ArgoCD only** — Crossplane and Azure providers are out of scope for this root (they come via GitOps). Copied verbatim from the design decision for this plan.
- Cluster zero is the **only** part of the system outside the GitOps cycle (design spec, "Riscos e pontos em aberto"). It must ship with a clear runbook and be applied manually with restricted access.
- **No `terraform apply` is run during plan execution** — no Azure subscription is available in this environment. The test cycle for every task is `terraform fmt -check`, `terraform init -backend=false`, `terraform validate`, and `tflint`. Real `apply` is documented in the runbook for when credentials exist.
- Follow the naming conventions established in the `azure-*-foundation` repos: `${platform_name}-${instance}` base names, lowercase, tags carrying `platform_name` / `platform_instance_name`.
- Backend is `azurerm` (remote tfstate), declared empty (`backend "azurerm" {}`) and supplied via `-backend-config` at init time — same pattern as `azure-platform-foundation/src/provider.tf`. During local validation always use `-backend=false`.
- Bash/script conventions (user global rules): long-form CLI flags, 2-space indent, always-quoted variables, no file extension on executables.

---

## File Structure

All files live under `infra/terraform/cluster-zero/`:

| File | Responsibility |
|------|----------------|
| `versions.tf` | `terraform` block: required_version, azurerm/helm/kubernetes provider pins, empty `azurerm` backend |
| `providers.tf` | `provider "azurerm"` (features), and `helm`/`kubernetes` providers wired to the AKS kubeconfig outputs |
| `variables.tf` | All input variables (platform name, instance name, region, node config, argocd chart version) |
| `main.tf` | Resource group + AKS cluster resource |
| `argocd.tf` | `helm_release` installing ArgoCD into the cluster |
| `outputs.tf` | Cluster name, kubeconfig (sensitive), OIDC issuer URL, ArgoCD namespace |
| `terraform.tfvars.example` | Example values documenting every variable |
| `.tflint.hcl` | tflint config enabling the azurerm ruleset |
| `README.md` | Runbook: prerequisites, backend init, plan/apply, ArgoCD access, teardown |

Repo-level docs touched: `CLAUDE.md` (Scripts/infra table row), `README.md` (cluster-zero section note pointing local → real).

---

### Task 1: Terraform scaffold, provider pins, and validation harness

**Files:**
- Create: `infra/terraform/cluster-zero/versions.tf`
- Create: `infra/terraform/cluster-zero/providers.tf`
- Create: `infra/terraform/cluster-zero/.tflint.hcl`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a validating Terraform root with providers `azurerm` (~> 4.0), `helm` (~> 2.17), `kubernetes` (~> 2.35) and an empty `azurerm` backend. Later tasks reference `azurerm_kubernetes_cluster.default` for the helm/kubernetes provider wiring already declared here.

- [ ] **Step 1: Write `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  backend "azurerm" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.35"
    }
  }
}
```

- [ ] **Step 2: Write `providers.tf`**

The `helm` and `kubernetes` providers read the AKS cluster's kubeconfig directly from the cluster resource created in Task 2. Referencing a not-yet-created resource is valid HCL — `terraform validate` resolves it as long as the resource exists in the module by the time all tasks are done. To keep Task 1 independently validatable, this file is written now but the resource it references is added in Task 2; validate at the end of Task 2 confirms the wiring.

```hcl
provider "azurerm" {
  features {}
}

provider "helm" {
  kubernetes {
    host                   = azurerm_kubernetes_cluster.default.kube_config.0.host
    client_certificate     = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.client_certificate)
    client_key             = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.client_key)
    cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.cluster_ca_certificate)
  }
}

provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.default.kube_config.0.host
  client_certificate     = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.default.kube_config.0.cluster_ca_certificate)
}
```

- [ ] **Step 3: Write `.tflint.hcl`**

```hcl
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "azurerm" {
  enabled = true
  version = "0.28.0"
  source  = "github.com/terraform-linters/tflint-ruleset-azurerm"
}
```

- [ ] **Step 4: Install tflint (once, if missing) and init it**

Run:
```bash
command -v tflint || curl --silent --location https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash
cd infra/terraform/cluster-zero && tflint --init
```
Expected: `tflint --version` prints a version; `tflint --init` reports the azurerm ruleset installed.

- [ ] **Step 5: Validate the scaffold**

Because `providers.tf` references `azurerm_kubernetes_cluster.default` (added in Task 2), `terraform validate` will fail here with a "Reference to undeclared resource" error. That is expected at this step — the scaffold is confirmed instead by a successful provider install:

Run:
```bash
cd infra/terraform/cluster-zero && terraform init -backend=false
```
Expected: PASS — "Terraform has been successfully initialized!", all three providers downloaded matching the pins.

- [ ] **Step 6: Check formatting**

Run: `cd infra/terraform/cluster-zero && terraform fmt -check`
Expected: PASS (no files reformatted).

- [ ] **Step 7: Commit**

```bash
git add infra/terraform/cluster-zero/versions.tf infra/terraform/cluster-zero/providers.tf infra/terraform/cluster-zero/.tflint.hcl
git commit -m "feat: scaffold cluster-zero terraform root with provider pins"
```

---

### Task 2: Resource group and AKS cluster

**Files:**
- Create: `infra/terraform/cluster-zero/variables.tf`
- Create: `infra/terraform/cluster-zero/main.tf`
- Create: `infra/terraform/cluster-zero/outputs.tf`

**Interfaces:**
- Consumes: providers from Task 1.
- Produces:
  - `azurerm_kubernetes_cluster.default` — referenced by the helm/kubernetes providers (Task 1) and by `argocd.tf` (Task 3).
  - Variables `platform_name` (string), `platform_instance_name` (string), `region` (string), `node_count` (number), `node_vm_size` (string), `kubernetes_version` (string), `argocd_chart_version` (string).
  - Outputs `cluster_name`, `oidc_issuer_url`, `kube_config_raw` (sensitive).

- [ ] **Step 1: Write `variables.tf`**

```hcl
variable "platform_name" {
  type        = string
  description = "Platform name, used as the resource name prefix (e.g. 'idp')."
}

variable "platform_instance_name" {
  type        = string
  description = "Regional instance name appended to the platform name (e.g. 'eus2')."
}

variable "region" {
  type        = string
  description = "Azure region for the resource group and AKS cluster (e.g. 'eastus2')."
}

variable "node_count" {
  type        = number
  description = "Number of nodes in the default AKS node pool."
  default     = 3
}

variable "node_vm_size" {
  type        = string
  description = "VM size for the default AKS node pool."
  default     = "Standard_D2s_v5"
}

variable "kubernetes_version" {
  type        = string
  description = "AKS Kubernetes version. Null uses the region default."
  default     = null
}

variable "argocd_chart_version" {
  type        = string
  description = "Version of the argo/argo-cd Helm chart to install."
  default     = "10.2.1"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags merged onto every resource."
  default     = {}
}
```

- [ ] **Step 2: Write `main.tf`**

```hcl
locals {
  base_name = "${var.platform_name}-${var.platform_instance_name}"

  common_tags = merge(
    {
      platform_name          = var.platform_name
      platform_instance_name = local.base_name
      managed_by             = "terraform"
      component              = "cluster-zero"
    },
    var.tags,
  )
}

resource "azurerm_resource_group" "default" {
  name     = "${local.base_name}-cluster-zero"
  location = var.region
  tags     = local.common_tags
}

resource "azurerm_kubernetes_cluster" "default" {
  name                = "${local.base_name}-cluster-zero"
  location            = azurerm_resource_group.default.location
  resource_group_name = azurerm_resource_group.default.name
  dns_prefix          = "${local.base_name}-cz"
  kubernetes_version  = var.kubernetes_version

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  default_node_pool {
    name       = "system"
    node_count = var.node_count
    vm_size    = var.node_vm_size
  }

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags
}
```

- [ ] **Step 3: Write `outputs.tf`**

```hcl
output "resource_group_name" {
  value = azurerm_resource_group.default.name
}

output "cluster_name" {
  value = azurerm_kubernetes_cluster.default.name
}

output "oidc_issuer_url" {
  value = azurerm_kubernetes_cluster.default.oidc_issuer_url
}

output "kube_config_raw" {
  value     = azurerm_kubernetes_cluster.default.kube_config_raw
  sensitive = true
}
```

- [ ] **Step 4: Format**

Run: `cd infra/terraform/cluster-zero && terraform fmt`
Expected: files listed as reformatted (or nothing if already clean).

- [ ] **Step 5: Validate**

Run: `cd infra/terraform/cluster-zero && terraform init -backend=false && terraform validate`
Expected: PASS — "Success! The configuration is valid." The Task 1 provider references now resolve because `azurerm_kubernetes_cluster.default` exists.

- [ ] **Step 6: Lint**

Run: `cd infra/terraform/cluster-zero && tflint`
Expected: no errors. (Warnings about missing `kubernetes_version` default are acceptable — null means "region default" by design.)

- [ ] **Step 7: Commit**

```bash
git add infra/terraform/cluster-zero/variables.tf infra/terraform/cluster-zero/main.tf infra/terraform/cluster-zero/outputs.tf
git commit -m "feat: add resource group and AKS cluster to cluster-zero terraform"
```

---

### Task 3: Install ArgoCD via Helm

**Files:**
- Create: `infra/terraform/cluster-zero/argocd.tf`
- Modify: `infra/terraform/cluster-zero/outputs.tf` (append ArgoCD namespace output)

**Interfaces:**
- Consumes: `azurerm_kubernetes_cluster.default` (Task 2), `var.argocd_chart_version` (Task 2), helm provider (Task 1).
- Produces: `helm_release.argocd` in namespace `argocd`; output `argocd_namespace`.

- [ ] **Step 1: Write `argocd.tf`**

The chart repo, name, and version match the validated local exercise (`scripts/cluster-zero/install-argocd`). `depends_on` the cluster so Helm never runs before the API server exists.

```hcl
resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true

  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = var.argocd_chart_version

  wait    = true
  timeout = 900

  depends_on = [azurerm_kubernetes_cluster.default]
}
```

- [ ] **Step 2: Append the namespace output to `outputs.tf`**

```hcl
output "argocd_namespace" {
  value = helm_release.argocd.namespace
}
```

- [ ] **Step 3: Format**

Run: `cd infra/terraform/cluster-zero && terraform fmt`
Expected: clean.

- [ ] **Step 4: Validate**

Run: `cd infra/terraform/cluster-zero && terraform validate`
Expected: PASS — "Success! The configuration is valid."

- [ ] **Step 5: Lint**

Run: `cd infra/terraform/cluster-zero && tflint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add infra/terraform/cluster-zero/argocd.tf infra/terraform/cluster-zero/outputs.tf
git commit -m "feat: install argocd via helm in cluster-zero terraform"
```

---

### Task 4: Runbook, example vars, and repo docs

**Files:**
- Create: `infra/terraform/cluster-zero/terraform.tfvars.example`
- Create: `infra/terraform/cluster-zero/README.md`
- Modify: `CLAUDE.md` (Scripts table — add an infra row)
- Modify: `README.md` (cluster-zero section — link local exercise to the real Terraform)

**Interfaces:**
- Consumes: all variables and outputs from Tasks 1–3.
- Produces: documentation only; no new Terraform symbols.

- [ ] **Step 1: Write `terraform.tfvars.example`**

```hcl
platform_name          = "idp"
platform_instance_name = "eus2"
region                 = "eastus2"

node_count   = 3
node_vm_size = "Standard_D2s_v5"

# Leave null to use the region's default AKS version, or pin explicitly:
# kubernetes_version = "1.31"

argocd_chart_version = "10.2.1"

tags = {
  environment = "platform"
}
```

- [ ] **Step 2: Write `README.md` (runbook)**

````markdown
# Cluster Zero (Terraform / Azure AKS)

Provisions the regional platform cluster ("cluster zero") — an AKS cluster with
ArgoCD installed. This is the **only** part of the platform created outside the
GitOps cycle: GitOps needs a cluster running ArgoCD before it can manage
anything, so that cluster is bootstrapped here with Terraform.

Crossplane and all downstream infrastructure are intentionally **not** installed
here — they arrive via GitOps once ArgoCD is up. This root mirrors the local
`scripts/cluster-zero/` k3d exercise, but targets real Azure.

## Prerequisites

- Terraform >= 1.9
- Azure CLI, logged in: `az login`
- A storage account + container for the remote tfstate backend (see
  `azure-subscription-foundation/src/tfstate-init`)
- Restricted access: applying this touches the platform's root of trust.

## Usage

```bash
# 1. Initialise with the remote backend
terraform init \
  -backend-config="resource_group_name=<rg>" \
  -backend-config="storage_account_name=<sa>" \
  -backend-config="container_name=tfstate" \
  -backend-config="key=cluster-zero.tfstate"

# 2. Copy and edit variables
cp terraform.tfvars.example terraform.tfvars

# 3. Review the plan
terraform plan

# 4. Apply
terraform apply

# 5. Fetch kubeconfig for the new cluster
az aks get-credentials \
  --resource-group "$(terraform output -raw resource_group_name)" \
  --name "$(terraform output -raw cluster_name)"

# 6. Get the initial ArgoCD admin password
kubectl --namespace argocd get secret argocd-initial-admin-secret \
  --output jsonpath='{.data.password}' | base64 --decode
```

## Teardown

```bash
terraform destroy
```

## Local validation (no Azure needed)

```bash
terraform fmt -check
terraform init -backend=false
terraform validate
tflint
```

## Next step

Once ArgoCD is running, bootstrap the app-of-apps that installs Crossplane and
the Azure provider family via GitOps — see the multi-tenant IDP design spec.
````

- [ ] **Step 3: Add the infra row to `CLAUDE.md`**

Find the Scripts table and add this row after the `scripts/cluster-zero/up` row:

```markdown
| `infra/terraform/cluster-zero/` | Terraform root that provisions the real regional cluster zero (Azure AKS + ArgoCD) — the production counterpart to the local `scripts/cluster-zero/` k3d exercise. See its `README.md` runbook. |
```

- [ ] **Step 4: Link the two in `README.md`**

In the "Local cluster-zero exercise" section, append:

```markdown
The real, Azure-targeted counterpart lives in
[`infra/terraform/cluster-zero/`](infra/terraform/cluster-zero/README.md) — same
AKS + ArgoCD boundary, provisioned with Terraform instead of k3d.
```

- [ ] **Step 5: Final full validation**

Run:
```bash
cd infra/terraform/cluster-zero && terraform fmt -check && terraform validate && tflint
```
Expected: all PASS — formatting clean, configuration valid, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add infra/terraform/cluster-zero/terraform.tfvars.example infra/terraform/cluster-zero/README.md CLAUDE.md README.md
git commit -m "docs: add cluster-zero terraform runbook and repo doc links"
```

---

## Self-Review Notes

**1. Spec coverage** (against `docs/superpowers/specs/2026-08-07-multi-tenant-idp-design.md`, "Bootstrap do cluster regional"):
- "criado por Terraform dedicado, fora do ciclo GitOps" → Tasks 1–3 create a dedicated Terraform root; runbook (Task 4) documents manual restricted apply. ✅
- "cluster que hospeda ArgoCD + Crossplane + instâncias Backstage" → cluster + ArgoCD covered here; Crossplane + Backstage instances are explicitly deferred to GitOps per this plan's agreed boundary (Global Constraints) and noted in the runbook's "Next step". ✅ (scoped-out on purpose, not a gap)
- "Após o Terraform aplicar o AKS regional e instalar ArgoCD, todo provisionamento subsequente passa a ser 100% GitOps" → boundary is exactly AKS + ArgoCD. ✅
- Location deviation from spec (spec said module inside `azure-platform-foundation`): resolved by user decision to place it at `infra/terraform/cluster-zero/` with modern azurerm, avoiding the legacy repo's `azurerm 2.72.0` pin. Documented here.
- "runbook claro e acesso restrito" (Riscos) → Task 4 README covers prerequisites, restricted-access note, apply/destroy. ✅

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". Every code step has literal content. ✅

**3. Type consistency:** `azurerm_kubernetes_cluster.default` referenced identically in `providers.tf` (Task 1), `main.tf` (Task 2), `argocd.tf` and `outputs.tf` (Task 3). `var.argocd_chart_version` defined in Task 2, consumed in Task 3. Output names (`resource_group_name`, `cluster_name`) match their use in the runbook's `terraform output -raw` calls. ✅

**Known intentional quirk:** Task 1 Step 5 cannot run `terraform validate` (it references a resource added in Task 2), so Task 1 is validated by a successful `terraform init` instead; full `validate` first passes at Task 2 Step 5. This is called out explicitly in both steps.
