# Cluster Zero (Local k3d Exercise) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a local, disposable k3d cluster with 3 server nodes running ArgoCD and Crossplane (core + Azure provider family), as a hands-on proxy for the "cluster zero" bootstrap described in the multi-tenant IDP design — before that bootstrap is reimplemented for real in Terraform against Azure AKS.

**Architecture:** A set of small, single-purpose bash scripts under `scripts/cluster-zero/` in the `backstage` repo, each doing exactly one step (prereqs check, cluster create/delete, ArgoCD install, Crossplane install), plus a vendored local Helm chart that renders Crossplane `Provider`/`Function` packages from a `values.yaml` list. An `up` script orchestrates all steps in order; a `verify` script inspects the resulting cluster state. This mirrors the recipe already proven in the `kubernetes` Claude skill (`~/git/linux/claude/skills/kubernetes`), vendored here so the `backstage` repo has no path dependency on another repo.

**Tech Stack:** k3d, kubectl, Helm 3, ArgoCD (Helm chart `argo/argo-cd`), Crossplane (Helm chart `crossplane-stable/crossplane`), Crossplane Azure provider family (Upbound), bash.

## Global Constraints

- No file extension on executables (per user's global bash-scripts convention) — new scripts under `scripts/cluster-zero/` have no `.sh` suffix, matching this plan's own scripts (existing `scripts/install.sh` / `scripts/configure.sh` predate this convention and are left untouched).
- Long-form CLI options only (`--namespace`, not `-n`).
- 2-space indent in all bash scripts.
- `do`/`then` on the same line as `while`/`if`.
- Lowercase locals; uppercase only for environment variables.
- Always quote variable expansions: `"${variable}"`.
- Use `set -e` only in scripts whose steps must all succeed sequentially (install/create scripts); omit it from read-only scripts (`verify`, `check-prereqs`) so they can report full status even when something is missing.
- A script's own directory is added to `${PATH}` when it needs to call sibling scripts by name.
- ArgoCD Helm chart pinned to version `10.2.1` (chart `argo/argo-cd`).
- Crossplane core Helm chart pinned to version `2.3.4` (chart `crossplane-stable/crossplane`).
- Crossplane Azure provider family pinned to version `v2.6.2` (all `upbound-provider-azure-*` packages plus `upbound-provider-family-azure`).
- k3d cluster name defaults to `idp-cluster-zero`, overridable via first script argument, to avoid colliding with an unrelated `k3s-default` cluster on the same machine.
- This is a **local, disposable exercise**, not the production cluster-zero implementation. The real bootstrap (Terraform + Azure AKS) is out of scope for this plan — see the design's "Bootstrap do cluster regional" section for the target architecture this exercise stands in for.

---

## File Structure

```
scripts/cluster-zero/
├── check-prereqs                          # verify k3d, kubectl, helm, docker are installed
├── cluster-create                         # k3d cluster create, 3 servers, waits for Ready
├── cluster-delete                         # k3d cluster delete
├── install-argocd                         # helm install ArgoCD into the `argocd` namespace
├── install-crossplane                     # helm install Crossplane core + Azure provider family
├── verify                                 # inspect ArgoCD + Crossplane health, read-only
├── up                                     # orchestrates all of the above in order
└── assets/
    ├── argocd-values.yaml                 # ArgoCD Helm values (LoadBalancer service)
    └── crossplane-packages/               # vendored local chart rendering Provider/Function CRs
        ├── Chart.yaml
        ├── templates/
        │   └── packages.yaml
        └── values-azure.yaml
```

Each script has one responsibility and can be run standalone; `up` is the only script that sequences the others.

---

### Task 1: Prerequisites check script

**Files:**
- Create: `scripts/cluster-zero/check-prereqs`

**Interfaces:**
- Consumes: nothing (first task, no dependencies)
- Produces: an executable script exit-0 when `k3d`, `kubectl`, `helm`, `docker` are all present on `PATH`; exit-1 and a list of missing tools otherwise. No other task depends on parsing its output — later tasks just need it invocable by name.

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
# Validate the CLI tools needed to bring up the local cluster-zero exercise.
#
# No `set -e`: the checker must keep going after a missing tool to report the
# full list in a single run.

required_tools="k3d kubectl helm docker"

missing=""

version_for() {
  local tool="${1?}"
  case "${tool}" in
    k3d)
      k3d version | head --lines 1
      ;;
    kubectl)
      kubectl version --client 2> /dev/null | head --lines 1
      ;;
    helm)
      helm version --short
      ;;
    docker)
      docker --version
      ;;
  esac
}

echo "Checking cluster-zero prerequisites..."
echo ""

for tool in ${required_tools}; do
  if command -v "${tool}" &> /dev/null; then
    version="$(version_for "${tool}")"
    printf '  ok      %-8s %s\n' "${tool}" "${version}"
  else
    printf '  MISSING %-8s\n' "${tool}"
    missing="${missing} ${tool}"
  fi
done

echo ""

if [ -n "${missing}" ]; then
  echo "Missing required tools:${missing}"
  echo "Install them before creating a cluster."
  exit 1
fi

echo "All prerequisites present."
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/cluster-zero/check-prereqs
```

- [ ] **Step 3: Run it and verify it reports the installed tools**

Run: `scripts/cluster-zero/check-prereqs`
Expected: exit code `0`, one `ok` line per tool (`k3d`, `kubectl`, `helm`, `docker`), final line `All prerequisites present.`

If any tool is missing, expected: exit code `1`, a `MISSING` line for that tool, and a summary line `Missing required tools: <name>`. Install the missing tool and re-run before proceeding.

- [ ] **Step 4: Commit**

```bash
git add scripts/cluster-zero/check-prereqs
git commit -m "feat: add cluster-zero prerequisites check script"
```

---

### Task 2: k3d cluster lifecycle scripts

**Files:**
- Create: `scripts/cluster-zero/cluster-create`
- Create: `scripts/cluster-zero/cluster-delete`

**Interfaces:**
- Consumes: nothing directly (assumes Task 1's tools are present; does not call `check-prereqs` itself — that's `up`'s job in Task 6)
- Produces: a running k3d cluster named `idp-cluster-zero` (or the name passed as `$1`) with 3 server nodes, `kube-system` metrics-server `Available`, and all nodes `Ready`. `kubectl`'s current context points at this cluster afterward (k3d does this automatically). Later tasks (3, 4, 5) run `helm`/`kubectl` commands assuming this context is active — they take no explicit cluster argument.

- [ ] **Step 1: Write `cluster-create`**

```bash
#!/bin/bash
set -e

cluster_name="${1:-idp-cluster-zero}"

echo ""
echo "Creating k3d cluster '${cluster_name}' (3 servers)..."

k3d cluster create \
  "${cluster_name}" \
  --api-port 6550 \
  --port "9080:80@loadbalancer" \
  --port "9443:443@loadbalancer" \
  --servers 3 \
  --k3s-arg '--disable=traefik@server:*' \
  --wait \
  --timeout 360s

kubectl wait node \
  --selector kubernetes.io/os=linux \
  --for condition=Ready \
  --timeout=360s

kubectl wait deployment metrics-server \
  --namespace kube-system \
  --for condition=Available \
  --timeout=360s

sleep 2

kubectl wait pods \
  --namespace kube-system \
  --selector k8s-app=metrics-server \
  --for condition=Ready \
  --timeout=360s

echo ""
echo "Cluster '${cluster_name}' ready."
```

- [ ] **Step 2: Write `cluster-delete`**

```bash
#!/bin/bash

cluster_name="${1:-idp-cluster-zero}"

echo ""
echo "Deleting k3d cluster '${cluster_name}'..."

k3d cluster delete \
  "${cluster_name}"

echo ""

k3d cluster list
```

- [ ] **Step 3: Make both executable**

```bash
chmod +x scripts/cluster-zero/cluster-create scripts/cluster-zero/cluster-delete
```

- [ ] **Step 4: Run `cluster-create` and verify the cluster is healthy**

Run: `scripts/cluster-zero/cluster-create`
Expected: script exits `0`, prints `Cluster 'idp-cluster-zero' ready.`

Verify node count and readiness:

Run: `kubectl get nodes`
Expected: 3 nodes with names containing `idp-cluster-zero-server-*`, all in `Ready` status (`server-0` is the initializing node so it may also carry the control-plane role, that's expected for k3d).

- [ ] **Step 5: Run `cluster-delete` and verify cleanup, then recreate for later tasks**

Run: `scripts/cluster-zero/cluster-delete`
Expected: output confirms deletion, `k3d cluster list` no longer shows `idp-cluster-zero`.

Recreate it since Tasks 3–5 need a live cluster:

Run: `scripts/cluster-zero/cluster-create`
Expected: same as Step 4.

- [ ] **Step 6: Commit**

```bash
git add scripts/cluster-zero/cluster-create scripts/cluster-zero/cluster-delete
git commit -m "feat: add k3d cluster lifecycle scripts for cluster-zero"
```

---

### Task 3: ArgoCD install

**Files:**
- Create: `scripts/cluster-zero/assets/argocd-values.yaml`
- Create: `scripts/cluster-zero/install-argocd`

**Interfaces:**
- Consumes: a live k3d cluster with current `kubectl` context pointing at it (Task 2)
- Produces: ArgoCD Helm release named `argocd` in the `argocd` namespace, all its Deployments `Available`. The `argocd-initial-admin-secret` Secret exists in that namespace — Task 6's `verify` script checks for it but does not decode/print it.

- [ ] **Step 1: Write the Helm values file**

```yaml
server:
  service:
    type: LoadBalancer
    servicePortHttp: 80
    servicePortHttps: 443
    servicePortHttpName: http
    servicePortHttpsName: https
    namedTargetPort: true
```

Save as `scripts/cluster-zero/assets/argocd-values.yaml`.

- [ ] **Step 2: Write the install script**

```bash
#!/bin/bash
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

assets_directory="${this_script_directory}/assets"

helm repo \
  add argo https://argoproj.github.io/argo-helm > /dev/null

helm repo \
  update argo > /dev/null

echo ""
echo "Installing argo-cd..."

helm upgrade \
  --install \
  --namespace argocd \
  --create-namespace \
  argocd argo/argo-cd \
  --version 10.2.1 \
  --values "${assets_directory}/argocd-values.yaml" \
  --wait > /dev/null

echo ""

for deployment in $(
  kubectl \
    --namespace argocd \
    get deploy \
    --output name
); do
  kubectl \
    --namespace argocd \
    wait \
    --for condition=Available \
    --timeout=360s \
    "${deployment}" > /dev/null
done

echo ""
echo "ArgoCD installed."
echo "Retrieve the admin password with:"
echo "  kubectl --namespace argocd get secret argocd-initial-admin-secret --output jsonpath='{.data.password}' | base64 --decode"
```

- [ ] **Step 3: Make it executable**

```bash
chmod +x scripts/cluster-zero/install-argocd
```

- [ ] **Step 4: Run it and verify ArgoCD is healthy**

Run: `scripts/cluster-zero/install-argocd`
Expected: exits `0`, prints `ArgoCD installed.`

Run: `kubectl --namespace argocd get deployments`
Expected: every Deployment shows equal `READY`/`UP-TO-DATE`/`AVAILABLE` counts (e.g. `1/1`).

Run: `kubectl --namespace argocd get secret argocd-initial-admin-secret`
Expected: the Secret exists (no error).

- [ ] **Step 5: Commit**

```bash
git add scripts/cluster-zero/assets/argocd-values.yaml scripts/cluster-zero/install-argocd
git commit -m "feat: add ArgoCD install script for cluster-zero"
```

---

### Task 4: Vendor the Crossplane packages Helm chart

**Files:**
- Create: `scripts/cluster-zero/assets/crossplane-packages/Chart.yaml`
- Create: `scripts/cluster-zero/assets/crossplane-packages/templates/packages.yaml`
- Create: `scripts/cluster-zero/assets/crossplane-packages/values-azure.yaml`

**Interfaces:**
- Consumes: nothing (pure Helm chart, no cluster interaction yet)
- Produces: a local Helm chart that, given a `values.yaml` with an `items` list (each with `name`, `kind`, `package`, `version`), renders one Crossplane `Provider` or `Function` custom resource per item. Task 5's `install-crossplane` script installs this chart with `values-azure.yaml`.

- [ ] **Step 1: Write `Chart.yaml`**

```yaml
apiVersion: v2
name: crossplane-packages
description: Crossplane providers and functions, selectable and versioned via values.yaml
type: application
version: 0.1.0
```

- [ ] **Step 2: Write the template**

```yaml
{{- range .Values.items }}
{{- $enabled := true }}
{{- if hasKey . "enabled" }}{{- $enabled = .enabled }}{{- end }}
{{- if $enabled }}
---
apiVersion: {{ .apiVersion | default (ternary "pkg.crossplane.io/v1beta1" "pkg.crossplane.io/v1" (eq .kind "Function")) }}
kind: {{ required "each item needs a kind (Function or Provider)" .kind }}
metadata:
  name: {{ required "each item needs a name" .name }}
spec:
  package: {{ required "each item needs a package" .package }}:{{ .version | default "latest" }}
{{- end }}
{{- end }}
```

Save as `scripts/cluster-zero/assets/crossplane-packages/templates/packages.yaml`.

- [ ] **Step 3: Write the Azure provider family values**

```yaml
# Azure providers for the cluster-zero exercise.
items:
  - name: upbound-provider-family-azure
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-family-azure
    version: v2.6.2
  - name: upbound-provider-azure-authorization
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-authorization
    version: v2.6.2
  - name: upbound-provider-azure-containerservice
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-containerservice
    version: v2.6.2
  - name: upbound-provider-azure-dbforpostgresql
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-dbforpostgresql
    version: v2.6.2
  - name: upbound-provider-azure-eventhub
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-eventhub
    version: v2.6.2
  - name: upbound-provider-azure-keyvault
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-keyvault
    version: v2.6.2
  - name: upbound-provider-azure-managedidentity
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-managedidentity
    version: v2.6.2
  - name: upbound-provider-azure-management
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-management
    version: v2.6.2
  - name: upbound-provider-azure-network
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-network
    version: v2.6.2
  - name: upbound-provider-azure-storage
    kind: Provider
    package: xpkg.upbound.io/upbound/provider-azure-storage
    version: v2.6.2
```

Save as `scripts/cluster-zero/assets/crossplane-packages/values-azure.yaml`.

These providers cover the building blocks the design's Platform Library will need later: `containerservice` (AKS clusters), `management` (Resource Groups), `keyvault` (secrets), `authorization`/`managedidentity` (RBAC for workload identity), `network`, `storage`, `dbforpostgresql`, `eventhub`.

- [ ] **Step 4: Verify the chart renders without a live cluster**

Run:
```bash
helm template crossplane-azure scripts/cluster-zero/assets/crossplane-packages \
  --values scripts/cluster-zero/assets/crossplane-packages/values-azure.yaml
```
Expected: 10 YAML documents printed, each with `kind: Provider` and a `spec.package` ending in `:v2.6.2`, one per entry in `values-azure.yaml`.

- [ ] **Step 5: Commit**

```bash
git add scripts/cluster-zero/assets/crossplane-packages
git commit -m "feat: vendor crossplane packages chart for cluster-zero"
```

---

### Task 5: Crossplane core + Azure provider install

**Files:**
- Create: `scripts/cluster-zero/install-crossplane`

**Interfaces:**
- Consumes: a live k3d cluster (Task 2), the vendored chart from Task 4 at `scripts/cluster-zero/assets/crossplane-packages`
- Produces: Crossplane core Helm release named `crossplane` in `crossplane-system`, Deployment `Available`; a second Helm release named `crossplane-azure` in the same namespace applying the 10 `Provider` resources from Task 4's chart, all reaching `INSTALLED=True` and `HEALTHY=True`.

- [ ] **Step 1: Write the script**

```bash
#!/bin/bash
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

assets_directory="${this_script_directory}/assets"

helm repo \
  add crossplane-stable https://charts.crossplane.io/stable > /dev/null

helm repo \
  update crossplane-stable > /dev/null

echo ""
echo "Installing crossplane core..."

helm upgrade \
  --install \
  --create-namespace \
  --namespace crossplane-system \
  crossplane crossplane-stable/crossplane \
  --version 2.3.4 \
  --wait > /dev/null

kubectl \
  wait deployment \
    --namespace crossplane-system \
    --selector release=crossplane \
    --for condition=Available \
    --timeout=360s > /dev/null

echo ""
echo "Installing Azure provider family..."

helm upgrade \
  --install \
  --namespace crossplane-system \
  crossplane-azure "${assets_directory}/crossplane-packages" \
  --values "${assets_directory}/crossplane-packages/values-azure.yaml" \
  --wait > /dev/null

echo ""
echo "Waiting for providers to become healthy..."

kubectl wait provider \
  --all \
  --for condition=Healthy \
  --timeout=360s

echo ""
echo "Crossplane and Azure providers installed."
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/cluster-zero/install-crossplane
```

- [ ] **Step 3: Run it and verify Crossplane + providers are healthy**

Run: `scripts/cluster-zero/install-crossplane`
Expected: exits `0`, prints `Crossplane and Azure providers installed.`

Run: `kubectl --namespace crossplane-system get pods`
Expected: `crossplane` and `crossplane-rbac-manager` pods `Running`.

Run: `kubectl get providers`
Expected: 10 providers listed (`upbound-provider-family-azure`, `upbound-provider-azure-authorization`, etc.), each with `INSTALLED=True` and `HEALTHY=True`.

- [ ] **Step 4: Commit**

```bash
git add scripts/cluster-zero/install-crossplane
git commit -m "feat: add crossplane + azure provider install script for cluster-zero"
```

---

### Task 6: Orchestration script, verify script, and docs

**Files:**
- Create: `scripts/cluster-zero/verify`
- Create: `scripts/cluster-zero/up`
- Modify: `CLAUDE.md` (append a "Cluster Zero (local exercise)" entry to the Scripts section)
- Modify: `README.md` (add a short "Local cluster-zero exercise" section)

**Interfaces:**
- Consumes: all scripts from Tasks 1–5, invoked by name via `PATH`
- Produces: a single command (`scripts/cluster-zero/up`) that stands up the full exercise from nothing, and a `verify` command that reports the health of every component. Nothing downstream in this plan depends on these — this task closes the plan out.

- [ ] **Step 1: Write `verify`**

```bash
#!/bin/bash
# Read-only health check for the cluster-zero exercise. No `set -e`: keep
# reporting every section even if one component is unhealthy.

echo "Nodes:"
kubectl get nodes

echo ""
echo "ArgoCD deployments:"
kubectl --namespace argocd get deployments

echo ""
echo "Crossplane deployments:"
kubectl --namespace crossplane-system get deployments

echo ""
echo "Crossplane providers:"
kubectl get providers

echo ""
echo "Crossplane functions:"
kubectl get functions 2> /dev/null || echo "  (none installed)"
```

- [ ] **Step 2: Write `up`**

```bash
#!/bin/bash
set -e

this_script_path="$(realpath "${0}")"
this_script_directory="${this_script_path%/*}"

PATH="${this_script_directory}:${PATH}"

check-prereqs
cluster-create "${1:-idp-cluster-zero}"
install-argocd
install-crossplane
verify
```

- [ ] **Step 3: Make both executable**

```bash
chmod +x scripts/cluster-zero/verify scripts/cluster-zero/up
```

- [ ] **Step 4: Tear down the cluster from earlier tasks and run `up` end to end**

```bash
scripts/cluster-zero/cluster-delete
scripts/cluster-zero/up
```

Expected: the command runs through all five stages (prereqs, cluster create, ArgoCD, Crossplane, verify) without stopping, and the final `verify` output shows 3 `Ready` nodes, ArgoCD deployments `Available`, Crossplane deployments `Available`, and 10 providers `INSTALLED=True`/`HEALTHY=True`.

- [ ] **Step 5: Update `CLAUDE.md`**

Add a row to the existing Scripts table (after the `scripts/configure.sh` row):

```markdown
| `scripts/cluster-zero/up` | Stands up a local k3d cluster (3 servers) with ArgoCD + Crossplane (Azure providers) — disposable exercise for the "cluster zero" bootstrap described in `docs/superpowers/specs/2026-08-07-multi-tenant-idp-design.md` |
```

- [ ] **Step 6: Update `README.md`**

Add a section:

```markdown
## Local cluster-zero exercise

A disposable k3d cluster (3 servers) with ArgoCD and Crossplane (Azure providers), used to exercise the "cluster zero" bootstrap from the multi-tenant IDP design before it's reimplemented in Terraform against real Azure AKS.

\`\`\`bash
scripts/cluster-zero/up      # stand up cluster + ArgoCD + Crossplane
scripts/cluster-zero/verify  # check health of everything
scripts/cluster-zero/cluster-delete  # tear down
\`\`\`
```

- [ ] **Step 7: Commit**

```bash
git add scripts/cluster-zero/verify scripts/cluster-zero/up CLAUDE.md README.md
git commit -m "feat: add cluster-zero orchestration script and docs"
```

---

## Self-Review Notes

- **Spec coverage:** this plan implements only the "Bootstrap do cluster regional" section of the design, as a local k3d exercise rather than the real Terraform/AKS implementation — consistent with what the user asked to start with. The remaining design sections (Helm chart per-project Backstage, Platform Library, GitOps-per-project automation, catalog bootstrap) are separate future plans, not covered here.
- **Placeholder scan:** no TBD/TODO; every step has literal script content and literal expected command output.
- **Type/name consistency:** `cluster-create`/`cluster-delete` both default to `idp-cluster-zero`; `install-argocd` and `install-crossplane` take no arguments and assume the current `kubectl` context (set by `cluster-create`); `up` passes its own `$1` through to `cluster-create` only. Chart name `crossplane-packages` and values file `values-azure.yaml` are referenced identically in Task 4 and Task 5.