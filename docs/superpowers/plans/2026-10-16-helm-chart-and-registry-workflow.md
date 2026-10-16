# Control plane as a Helm chart, published by CI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the control plane's 16 Kubernetes manifests as one Helm chart, have `platform init --target local` render and apply from that chart instead of reading raw YAML with string replacement, and publish the chart plus its 8 images from a new CI workflow to GHCR — all without changing what gets installed, in what order, or how `local`'s step-by-step progress output looks.

**Architecture:** One umbrella chart (`platform/chart/platform-control-plane/`) with one template per existing manifest, a `registry` value (empty by default) and one `images.<key>` entry per image (each with its own independent `tag`), composed through a shared `_helpers.tpl` function. `local.py` keeps its 21-step task graph; each step that used to read a YAML file and string-replace the image now calls a new `_render()` helper that runs `helm template <chart> --show-only templates/<path>`, piping the result into the same `kubectl apply` the step already did. A new GitHub Actions workflow builds the 8 images and packages/publishes the chart on tag push.

**Tech Stack:** Python 3.11+ (`wasp_platform.bootstrap.local`), Helm 3 (chart templates, `helm template`/`helm push`), pytest (existing test suite in `cli/tests/`), GitHub Actions (new workflow, modeled on `platform/templates/python-service/content/.github/workflows/platform-build.yaml`).

**Spec:** `docs/superpowers/specs/2026-10-16-helm-chart-and-registry-workflow-design.md`

## Global Constraints

- The chart must cover all 16 manifests `init` applies today, not only the 8 whose image `_deploy()` substitutes (spec Objective 1).
- `init_tasks()`'s task graph, dependency ordering, step names, and per-step logging/progress card in `local.py` must not change (spec, "What does not change").
- `local` keeps building every image locally with Docker and importing into k3d; it never pulls from the registry this plan adds (spec Objective 3, "What does not change").
- `values.yaml` has one global `registry` field, empty by default (so a local install resolves every image to its bare short name, unchanged behavior); each `images.<key>` entry has its own independent `tag` (spec, "Each image versions independently").
- RBAC, namespaces, labels, container args, and every object the 16 manifests create today must be preserved verbatim in the chart templates — this is a repackaging, not a redesign (spec, "What does not change").
- Keycloak's dynamic setup in Python (`deploy_keycloak`/`render_realm`/`theme_configmap`/`_apply_theme`) stays as-is; only the static Keycloak Deployment/PVC/Service manifest moves into the chart (spec, "What does not change").
- GHCR is the registry, public (spec, "Registry: GHCR, public" — flagged to revisit later, not reopened here).

## Review Focus

- **Helm missing from `PATH`** — `install()`'s existing `for tool in ("docker", "k3d", "kubectl", ...)` check (`local.py:622`) must also refuse to start without `helm`, with the same `BootstrapError` message shape, or a user without Helm gets a confusing failure deep in the first chart-rendering step instead of the pre-flight message the other three tools already get.
- **A chart template renders no fewer objects than its source manifest** — a missed `---` separator or a mis-indented `{{ }}` silently drops a Role, Binding, or Service from the rendered output, which `kubectl apply` would then simply not create; every converted template needs its rendered object count checked against the original file's `---`-separated document count.
- **The registry-prefixed image reference must still be exactly `<host>/<namespace>/<name>:<tag>`** — a stray extra slash or a missing tag separator in the `_helpers.tpl` concatenation produces an image reference Docker/containerd rejects outright (not a soft failure), so the helper's output needs checking in both the empty-`registry` and set-`registry` cases, matching the spec's own validated example.
- **`_render()`'s `helm template --show-only` must fail loudly on a missing template path** — a typo in a `_render()` call site (e.g. `templates/providers/regsitry-provider.yaml`) should raise the same `BootstrapError` shape `_run` already raises for a non-zero exit, not silently apply an empty manifest and leave a step reporting success with nothing deployed.
- **The two optional providers (`aws_account`, `crossplane_aws`) must stay absent from the rendered output when their flag is unset** — `install_aws_account`/`install_crossplane` only call `_deploy` when a credential/flag says so today; the chart's `providers.awsAccount.enabled`/`providers.crossplaneAws.enabled` conditionals must reproduce that exact gating, not render a Deployment that then fails to pull/start because no credential exists.

---

## File Structure

```
platform/chart/platform-control-plane/
├── Chart.yaml                                   # new: chart name/version, separate from image tags
├── values.yaml                                    # new: registry (global, empty default), namespaces, images.*, providers.*.enabled
└── templates/
    ├── _helpers.tpl                                # new: platform-control-plane.image helper
    ├── api/
    │   └── platform-api.yaml                        # new: converted from platform/api/deploy/platform-api.yaml
    ├── keycloak/
    │   ├── keycloak.yaml                            # new: converted from platform/keycloak/deploy/keycloak.yaml
    │   └── realm-import.yaml                        # new: converted from platform/keycloak/deploy/realm-import.yaml
    ├── observability/
    │   └── prometheus.yaml                          # new: converted from platform/observability/deploy/prometheus.yaml
    └── providers/
        ├── local-vcluster-provider.yaml              # new: converted from platform/providers/local_vcluster/deploy/local-vcluster-provider.yaml
        ├── pod-security.yaml                          # new: converted from platform/providers/local_vcluster/deploy/pod-security.yaml
        ├── traefik.yaml                                # new: converted from platform/providers/local_vcluster/deploy/traefik.yaml
        ├── scm-github-provider.yaml                    # new: converted from platform/providers/scm_github/deploy/scm-github-provider.yaml
        ├── workload-provider.yaml                       # new: converted from platform/providers/workload/deploy/workload-provider.yaml
        ├── forager-provider.yaml                         # new: converted from platform/providers/forager/deploy/forager-provider.yaml
        ├── profile-policies.yaml                          # new: converted from platform/providers/forager/deploy/profile-policies.yaml
        ├── shared-pg.yaml                                  # new: converted from platform/providers/forager/deploy/shared-pg.yaml
        ├── registry-provider.yaml                           # new: converted from platform/providers/registry/deploy/registry-provider.yaml
        ├── aws-account-provider.yaml                         # new: converted from platform/providers/aws_account/deploy/aws-account-provider.yaml, conditional
        ├── crossplane-aws-provider.yaml                       # new: converted from platform/providers/crossplane_aws/deploy/crossplane-aws-provider.yaml, conditional
        ├── crossplane.yaml                                     # new: converted from platform/providers/crossplane_aws/deploy/crossplane.yaml, conditional
        └── provider-aws-ec2.yaml                                # new: converted from platform/providers/crossplane_aws/deploy/provider-aws-ec2.yaml, conditional

cli/src/wasp_platform/bootstrap/local.py   # modified: new _render(), CHART_DIR/CHART_NAME/CHART_TEMPLATES constants, every _deploy/_kubectl("apply", "--filename", str(...)) call site switched to render from the chart
cli/tests/test_images.py                    # modified: tests for _render() alongside the existing build/import tests
platform/docs/walkthrough/bootstrap/prerequisites.md   # modified: Helm added to both OS tables
platform/docs/reference/install.md                      # modified: Helm added to prerequisites note
.github/workflows/platform-control-plane-release.yaml   # new: builds the 8 images, packages and publishes the chart to GHCR
```

---

### Task 1: Helm as a prerequisite, checked by `init`

**Files:**
- Modify: `cli/src/wasp_platform/bootstrap/local.py:622` (the `for tool in (...)` loop inside `install()`)
- Modify: `platform/docs/walkthrough/bootstrap/prerequisites.md` (both the Ubuntu and macOS tables)
- Modify: `platform/docs/reference/install.md`
- Test: `cli/tests/test_init.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `install()` raises `local.BootstrapError` with message `"'helm' not found in PATH"` when Helm is absent, before any chart-rendering task runs — later tasks rely on Helm already being confirmed present.

- [ ] **Step 1: Write the failing test**

Add to `cli/tests/test_init.py` (the file already imports `local` and uses `monkeypatch`):

```python
def test_init_refuses_without_helm(no_install, monkeypatch):
  real_which = shutil.which
  monkeypatch.setattr(shutil, "which", lambda name: None if name == "helm" else real_which(name))
  result = run("--admin", "you@example.org", input="y\n")
  assert result.exit_code != 0
  assert "helm" in result.output
```

Add `import shutil` at the top of `cli/tests/test_init.py` if not already imported (check with `grep -n "^import shutil" cli/tests/test_init.py` first — it is not imported there today).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd cli && uv run pytest tests/test_init.py::test_init_refuses_without_helm -v`
Expected: FAIL — `no_install` fixture's `lambda **_: pytest.fail(...)` is never triggered because `install()` does not check for `helm` yet, so the CLI proceeds past the tool check (the test fails on the `no_install` assertion firing, or on exit_code being 0).

- [ ] **Step 3: Add `helm` to the tool check**

In `cli/src/wasp_platform/bootstrap/local.py`, find:

```python
  for tool in ("docker", "k3d", "kubectl", *(("aws",) if aws_profile else ())):
    if not shutil.which(tool):
      raise BootstrapError(f"'{tool}' not found in PATH")
```

(this is inside `install()`, immediately before `root = repo_root()`). Change it to:

```python
  for tool in ("docker", "k3d", "kubectl", "helm", *(("aws",) if aws_profile else ())):
    if not shutil.which(tool):
      raise BootstrapError(f"'{tool}' not found in PATH")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd cli && uv run pytest tests/test_init.py::test_init_refuses_without_helm -v`
Expected: PASS

- [ ] **Step 5: Run the full existing test_init.py suite to confirm no regression**

Run: `cd cli && uv run pytest tests/test_init.py -v`
Expected: all PASS (the new tool check must not break any existing test that mocks `shutil.which` or the tool list)

- [ ] **Step 6: Add Helm to the documented prerequisites**

In `platform/docs/walkthrough/bootstrap/prerequisites.md`, Ubuntu table (after the `kubectl` row):

```markdown
    | Helm | >= 3.14.0 | init | `helm version --short` |
```

In the same file, macOS table (after the `kubectl` row):

```markdown
    | Helm | >= 3.14.0 | init | `helm version --short` |
```

And add `helm` to the `brew install` line in that same macOS section (find the line starting `brew install colima docker docker-buildx k3d kubernetes-cli uv git gh bash` and append ` helm`).

In `platform/docs/reference/install.md`, find the prerequisites table (mirrors the walkthrough's Ubuntu table) and add the same Helm row.

- [ ] **Step 7: Commit**

```bash
git add cli/src/wasp_platform/bootstrap/local.py cli/tests/test_init.py platform/docs/walkthrough/bootstrap/prerequisites.md platform/docs/reference/install.md
git commit -m "feat(cli): require Helm as a prerequisite of platform init"
```

---

### Task 2: Chart skeleton and the 8 imaged templates

**Files:**
- Create: `platform/chart/platform-control-plane/Chart.yaml`
- Create: `platform/chart/platform-control-plane/values.yaml`
- Create: `platform/chart/platform-control-plane/templates/_helpers.tpl`
- Create: `platform/chart/platform-control-plane/templates/api/platform-api.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/local-vcluster-provider.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/scm-github-provider.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/workload-provider.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/forager-provider.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/registry-provider.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/aws-account-provider.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/crossplane-aws-provider.yaml`
- Test: manual `helm template` + `helm lint` invocations (no pytest in this task — chart rendering is validated with Helm's own tools, not pytest)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a chart renderable with `helm template platform-control-plane platform/chart/platform-control-plane --set images.<key>.tag=<tag>`; the `platform-control-plane.image` named template other tasks (and Task 3) reuse via `{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.<key>) }}`.

- [ ] **Step 1: Create `Chart.yaml`**

```yaml
apiVersion: v2
name: platform-control-plane
description: >
  Umbrella chart for the wasp-idp control plane: the Platform API, Keycloak, and the providers
  (local_vcluster, scm_github, workload, forager, registry, aws_account, crossplane_aws).
type: application
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 2: Create `values.yaml`**

```yaml
# Empty by default: local.py never sets this, so every image resolves to its bare `repository` (the
# short name k3d/Docker already has after a local build). A remote install sets this once
# (e.g. "ghcr.io/smsilva/wasp-idp") and every image below is looked up under it.
registry: ""

namespace: platform-system
authNamespace: platform-auth
resourcesNamespace: platform-resources
crossplaneNamespace: crossplane-system
ingressNamespace: platform-ingress

images:
  api:
    repository: platform-api
    tag: dev
    pullPolicy: Never
  localVclusterProvider:
    repository: local-vcluster-provider
    tag: dev
    pullPolicy: Never
  scmGithubProvider:
    repository: scm-github-provider
    tag: dev
    pullPolicy: Never
  workloadProvider:
    repository: workload-provider
    tag: dev
    pullPolicy: Never
  foragerProvider:
    repository: forager-provider
    tag: dev
    pullPolicy: Never
  registryProvider:
    repository: registry-provider
    tag: dev
    pullPolicy: Never
  awsAccountProvider:
    repository: aws-account-provider
    tag: dev
    pullPolicy: Never
  crossplaneAwsProvider:
    repository: crossplane-aws-provider
    tag: dev
    pullPolicy: Never

providers:
  awsAccount:
    enabled: false
  crossplaneAws:
    enabled: false
```

- [ ] **Step 3: Create `templates/_helpers.tpl`**

```
{{/*
Renders a full image reference, prefixed by the global `registry` when set. Takes a dict with
`registry` (the chart-level .Values.registry) and `image` (one `images.<key>` entry).
Usage: {{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.registryProvider) }}
Named templates re-bind `$`/`.` to whatever was passed to `include`, not to the chart root — hence
passing both pieces explicitly instead of reaching for `.Values` inside the helper.
*/}}
{{- define "platform-control-plane.image" -}}
{{- if .registry -}}
{{ .registry }}/{{ .image.repository }}:{{ .image.tag }}
{{- else -}}
{{ .image.repository }}:{{ .image.tag }}
{{- end -}}
{{- end -}}
```

- [ ] **Step 4: Convert `platform/api/deploy/platform-api.yaml`**

Read the source file first: `cat platform/api/deploy/platform-api.yaml`. Create `platform/chart/platform-control-plane/templates/api/platform-api.yaml` with every `namespace: platform-system` replaced by `namespace: {{ .Values.namespace }}`, every `namespace: platform-auth` replaced by `namespace: {{ .Values.authNamespace }}`, the `image: platform-api:dev` line replaced by `image: "{{ include \"platform-control-plane.image\" (dict \"registry\" .Values.registry \"image\" .Values.images.api) }}"`, and `imagePullPolicy` (there is none in the source today — add `imagePullPolicy: {{ .Values.images.api.pullPolicy }}` right after the `image:` line, matching the pattern already used in the other provider templates). Every other line (RBAC rules, labels, env vars, the readiness probe, the PVC, the Service) copied verbatim — do not change the `PLATFORM_OIDC_ISSUER`/`PLATFORM_PUBLIC_URL`/`PLATFORM_KEYCLOAK_URL` values; they stay hardcoded to the local target's addresses, as the spec's "What does not change" requires.

- [ ] **Step 5: Convert the 6 provider manifests with an image**

Each file below follows the same pattern as `platform-api.yaml` in Step 4: replace the literal `namespace:` with the matching `.Values` field, replace the `image: <name>:dev` line with the `include "platform-control-plane.image"` call plus its own `imagePullPolicy`, copy every other line verbatim (RBAC rules, labels, container args, resource limits). For the two conditional providers, wrap the whole file in a `{{- if }}`/`{{- end }}` block, since `install_aws_account`/`install_crossplane` in `local.py` only deploy them when a credential/flag says so.

Create `platform/chart/platform-control-plane/templates/providers/local-vcluster-provider.yaml` (source: `platform/providers/local_vcluster/deploy/local-vcluster-provider.yaml`):

```yaml
# Provider local_vcluster (#183): runs inside platform-local and turns each Environment into a
# vcluster (Helm release `vcluster`) in namespace env-<name>. Installed by `platform init`.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: local-vcluster-provider
  namespace: {{ .Values.namespace }}
---
# The vcluster chart creates namespaced objects plus a ClusterRole/ClusterRoleBinding per
# virtual cluster, so the provider needs broad rights. Local target only: a provider for a
# shared target would install vclusters through a narrower path (e.g. a vcluster operator).
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: local-vcluster-provider
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: local-vcluster-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: local-vcluster-provider
  namespace: {{ .Values.namespace }}
  labels:
    platform.wasp.silvios.me/provider: local_vcluster
    platform.wasp.silvios.me/capabilities: environment
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: local-vcluster-provider
  template:
    metadata:
      labels:
        app.kubernetes.io/name: local-vcluster-provider
    spec:
      serviceAccountName: local-vcluster-provider
      containers:
        - name: provider
          image: "{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.localVclusterProvider) }}"
          imagePullPolicy: {{ .Values.images.localVclusterProvider.pullPolicy }}
          args: [--namespace, {{ .Values.namespace }}]
          resources:
            requests:
              memory: 96Mi
            limits:
              memory: 256Mi
```

Create `platform/chart/platform-control-plane/templates/providers/scm-github-provider.yaml` (source: `platform/providers/scm_github/deploy/scm-github-provider.yaml`):

```yaml
# Provider scm_github (#199): validates each GitHub ScmConnection with the App's key and records the
# installation, and runs each ComponentCreation (#279) and each Build (#206). Installed by `platform
# init`. The only reader of the credential Secrets (ADR 0025).
apiVersion: v1
kind: ServiceAccount
metadata:
  name: scm-github-provider
  namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: scm-github-provider
  namespace: {{ .Values.namespace }}
rules:
  - apiGroups: [platform.wasp.silvios.me]
    resources: [scmconnections]
    verbs: [get, list, watch, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [scmconnections/status]
    verbs: [get, patch]
  - apiGroups: [""]
    resources: [secrets]
    verbs: [get]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [componentcreations]
    verbs: [get, list, watch, delete]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [componentcreations/status]
    verbs: [get, patch]
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [components]
    verbs: [get, create, update]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [builds]
    verbs: [get, list, watch, delete]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [builds/status]
    verbs: [get, patch]
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [versions]
    verbs: [get, create]
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [resources]
    verbs: [get]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: scm-github-provider
  namespace: {{ .Values.namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: scm-github-provider
subjects:
  - kind: ServiceAccount
    name: scm-github-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scm-github-provider
  namespace: {{ .Values.namespace }}
  labels:
    platform.wasp.silvios.me/provider: scm_github
    platform.wasp.silvios.me/capabilities: scm.build
    platform.wasp.silvios.me/vendor: github
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: scm-github-provider
  template:
    metadata:
      labels:
        app.kubernetes.io/name: scm-github-provider
    spec:
      serviceAccountName: scm-github-provider
      containers:
        - name: provider
          image: "{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.scmGithubProvider) }}"
          imagePullPolicy: {{ .Values.images.scmGithubProvider.pullPolicy }}
          args: [--namespace, {{ .Values.namespace }}, --workdir, /work]
          volumeMounts:
            - name: work
              mountPath: /work
          resources:
            requests:
              memory: 64Mi
            limits:
              memory: 256Mi
      volumes:
        - name: work
          emptyDir:
            sizeLimit: 512Mi
```

Create `platform/chart/platform-control-plane/templates/providers/workload-provider.yaml` (source: `platform/providers/workload/deploy/workload-provider.yaml`):

```yaml
# Provider workload (ADR 0033): applies each WorkloadRevision in the vcluster of its Environment
# (with the admin kubeconfig of Environment.status) and keeps the WorkloadInstance; turns each
# WorkloadRoute into a GAMMA HTTPRoute there (ADR 0035, #344). Works with any
# Environment that is Ready with kubeconfigData. Installed by `platform init`.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: workload-provider
  namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: workload-provider
  namespace: {{ .Values.namespace }}
rules:
  - apiGroups: [platform.wasp.silvios.me]
    resources: [workloadrevisions]
    verbs: [get, list, watch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [workloadrevisions/status]
    verbs: [get, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [workloadinstances]
    verbs: [get, list, watch, create, delete]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [workloadinstances/status]
    verbs: [get, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [workloadroutes]
    verbs: [get, list, watch, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [workloadroutes/status]
    verbs: [get, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [environments]
    verbs: [get]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [resourcerequests]
    verbs: [get, list, delete]
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [versions]
    verbs: [get]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: workload-provider
  namespace: {{ .Values.namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: workload-provider
subjects:
  - kind: ServiceAccount
    name: workload-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workload-provider
  namespace: {{ .Values.namespace }}
  labels:
    platform.wasp.silvios.me/provider: workload
    platform.wasp.silvios.me/capabilities: workload
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: workload-provider
  template:
    metadata:
      labels:
        app.kubernetes.io/name: workload-provider
    spec:
      serviceAccountName: workload-provider
      containers:
        - name: provider
          image: "{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.workloadProvider) }}"
          imagePullPolicy: {{ .Values.images.workloadProvider.pullPolicy }}
          args: [--namespace, {{ .Values.namespace }}]
          resources:
            requests:
              memory: 64Mi
            limits:
              memory: 256Mi
```

Create `platform/chart/platform-control-plane/templates/providers/forager-provider.yaml` (source: `platform/providers/forager/deploy/forager-provider.yaml`):

```yaml
# Forager (ADR 0022, 0031, #263): resolves the resources of each WorkloadRevision against the
# BindingPolicies into ResourceRequests and provisions them in the vcluster of the Environment (with
# the admin kubeconfig of Environment.status). Generated credentials live in namespace
# {{ .Values.resourcesNamespace }}, never in {{ .Values.namespace }}. Installed by `platform init`,
# with the platform default policy.
apiVersion: v1
kind: Namespace
metadata:
  name: {{ .Values.resourcesNamespace }}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: forager-provider
  namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: forager-provider
  namespace: {{ .Values.namespace }}
rules:
  - apiGroups: [platform.wasp.silvios.me]
    resources: [workloadrevisions]
    verbs: [get, list, watch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [bindingpolicies]
    verbs: [list]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [resourcerequests]
    verbs: [get, list, create, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [resourcerequests/status]
    verbs: [get, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [environments]
    verbs: [get]
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [versions, components]
    verbs: [get]
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [resources]
    verbs: [create]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: forager-provider
  namespace: {{ .Values.namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: forager-provider
subjects:
  - kind: ServiceAccount
    name: forager-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: forager-provider
  namespace: {{ .Values.resourcesNamespace }}
rules:
  - apiGroups: [""]
    resources: [secrets]
    verbs: [get, create, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: forager-provider
  namespace: {{ .Values.resourcesNamespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: forager-provider
subjects:
  - kind: ServiceAccount
    name: forager-provider
    namespace: {{ .Values.namespace }}
---
# The platform default layer: every environment provisions a dedicated postgres unless its own
# policy or the policy of its profile says otherwise, and reaches an instance from outside through its
# entry point (dns, route, ADR 0036).
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: BindingPolicy
metadata:
  name: platform-default
  namespace: {{ .Values.namespace }}
spec:
  provisioners:
    - type: postgres
      mode: provision
    - type: dns
      mode: provision
    - type: route
      mode: provision
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: forager-provider
  namespace: {{ .Values.namespace }}
  labels:
    platform.wasp.silvios.me/provider: forager
    platform.wasp.silvios.me/capabilities: resources
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: forager-provider
  template:
    metadata:
      labels:
        app.kubernetes.io/name: forager-provider
    spec:
      serviceAccountName: forager-provider
      containers:
        - name: provider
          image: "{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.foragerProvider) }}"
          imagePullPolicy: {{ .Values.images.foragerProvider.pullPolicy }}
          args: [--namespace, {{ .Values.namespace }}]
          resources:
            requests:
              memory: 64Mi
            limits:
              memory: 256Mi
```

Create `platform/chart/platform-control-plane/templates/providers/registry-provider.yaml` (source: `platform/providers/registry/deploy/registry-provider.yaml`):

```yaml
# Provider registry (ADR 0037, #365): checks that each OCIRegistry answers the OCI Distribution API
# (https://<host>/v2/) and sets Ready. Installed by `platform init`. Pull credentials come with #367.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: registry-provider
  namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: registry-provider
  namespace: {{ .Values.namespace }}
rules:
  - apiGroups: [platform.wasp.silvios.me]
    resources: [ociregistries]
    verbs: [get, list, watch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [ociregistries/status]
    verbs: [get, patch]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: registry-provider
  namespace: {{ .Values.namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: registry-provider
subjects:
  - kind: ServiceAccount
    name: registry-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: registry-provider
  namespace: {{ .Values.namespace }}
  labels:
    platform.wasp.silvios.me/provider: registry
    platform.wasp.silvios.me/capabilities: registry
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: registry-provider
  template:
    metadata:
      labels:
        app.kubernetes.io/name: registry-provider
    spec:
      serviceAccountName: registry-provider
      containers:
        - name: provider
          image: "{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.registryProvider) }}"
          imagePullPolicy: {{ .Values.images.registryProvider.pullPolicy }}
          args: [--namespace, {{ .Values.namespace }}]
          resources:
            requests:
              memory: 48Mi
            limits:
              memory: 128Mi
```

Create `platform/chart/platform-control-plane/templates/providers/aws-account-provider.yaml` (source: `platform/providers/aws_account/deploy/aws-account-provider.yaml`, wrapped in a condition):

```yaml
{{- if .Values.providers.awsAccount.enabled }}
# Provider aws_account (#193, ADR 0029): verifies the trust of each AWS CloudAccount from the
# platform base credential (Secret aws-base-credential). Installed by `platform init --aws-profile`.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: aws-account-provider
  namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: aws-account-provider
  namespace: {{ .Values.namespace }}
rules:
  - apiGroups: [platform.wasp.silvios.me]
    resources: [cloudaccounts]
    verbs: [get, list, watch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [cloudaccounts/status]
    verbs: [get, patch, update]
  - apiGroups: [""]
    resources: [configmaps]
    verbs: [create]
  - apiGroups: [""]
    resources: [configmaps]
    resourceNames: [aws-base-identity]
    verbs: [get, update, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: aws-account-provider
  namespace: {{ .Values.namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: aws-account-provider
subjects:
  - kind: ServiceAccount
    name: aws-account-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aws-account-provider
  namespace: {{ .Values.namespace }}
  labels:
    platform.wasp.silvios.me/provider: aws_account
    platform.wasp.silvios.me/capabilities: cloud-account
    platform.wasp.silvios.me/vendor: aws
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: aws-account-provider
  template:
    metadata:
      labels:
        app.kubernetes.io/name: aws-account-provider
    spec:
      serviceAccountName: aws-account-provider
      containers:
        - name: provider
          image: "{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.awsAccountProvider) }}"
          imagePullPolicy: {{ .Values.images.awsAccountProvider.pullPolicy }}
          args: [--namespace, {{ .Values.namespace }}]
          envFrom:
            - secretRef:
                name: aws-base-credential
          resources:
            requests:
              memory: 96Mi
            limits:
              memory: 256Mi
{{- end }}
```

Create `platform/chart/platform-control-plane/templates/providers/crossplane-aws-provider.yaml` (source: `platform/providers/crossplane_aws/deploy/crossplane-aws-provider.yaml`, wrapped in a condition):

```yaml
{{- if .Values.providers.crossplaneAws.enabled }}
# Provider crossplane_aws (#436, ADR 0032): a VPC per Environment in an AWS CloudAccount, through
# Crossplane, and a ProviderConfig per CloudAccount. Installed by `platform init --with-crossplane`.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: crossplane-aws-provider
  namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: crossplane-aws-provider
  namespace: {{ .Values.namespace }}
rules:
  - apiGroups: [platform.wasp.silvios.me]
    resources: [environments]
    verbs: [get, list, watch, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [environments/status]
    verbs: [get, patch]
  - apiGroups: [platform.wasp.silvios.me]
    resources: [cloudaccounts]
    verbs: [get, list]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: crossplane-aws-provider
  namespace: {{ .Values.namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: crossplane-aws-provider
subjects:
  - kind: ServiceAccount
    name: crossplane-aws-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: crossplane-aws-provider
rules:
  - apiGroups: [aws.upbound.io]
    resources: [providerconfigs]
    verbs: [get, list, create, patch, delete]
  - apiGroups: [ec2.aws.upbound.io]
    resources: [vpcs]
    verbs: [get, list, create, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: crossplane-aws-provider
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: crossplane-aws-provider
subjects:
  - kind: ServiceAccount
    name: crossplane-aws-provider
    namespace: {{ .Values.namespace }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crossplane-aws-provider
  namespace: {{ .Values.namespace }}
  labels:
    platform.wasp.silvios.me/provider: crossplane_aws
    platform.wasp.silvios.me/capabilities: environment
    platform.wasp.silvios.me/vendor: aws
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: crossplane-aws-provider
  template:
    metadata:
      labels:
        app.kubernetes.io/name: crossplane-aws-provider
    spec:
      serviceAccountName: crossplane-aws-provider
      containers:
        - name: provider
          image: "{{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.crossplaneAwsProvider) }}"
          imagePullPolicy: {{ .Values.images.crossplaneAwsProvider.pullPolicy }}
          args: [--namespace, {{ .Values.namespace }}]
          resources:
            requests:
              memory: 96Mi
            limits:
              memory: 256Mi
{{- end }}
```

- [ ] **Step 6: Lint the chart**

Run: `helm lint platform/chart/platform-control-plane`
Expected: `0 chart(s) failed` (ignore any `[INFO]` severity notices about missing `icon` — those are not failures)

- [ ] **Step 7: Render with no overrides and verify every unconditional object appears**

Run: `helm template platform-control-plane platform/chart/platform-control-plane | grep -c '^kind:'`
Expected: the count must equal the number of `kind:` occurrences across the 7 unconditional source files combined — verify with: `grep -c '^kind:' platform/api/deploy/platform-api.yaml platform/providers/local_vcluster/deploy/local-vcluster-provider.yaml platform/providers/scm_github/deploy/scm-github-provider.yaml platform/providers/workload/deploy/workload-provider.yaml platform/providers/forager/deploy/forager-provider.yaml platform/providers/registry/deploy/registry-provider.yaml | awk -F: '{sum+=$2} END {print sum}'` — the two counts must match (this is the Review Focus check: no template silently drops an object).

- [ ] **Step 8: Render with both optional providers enabled and verify they appear**

Run: `helm template platform-control-plane platform/chart/platform-control-plane --set providers.awsAccount.enabled=true --set providers.crossplaneAws.enabled=true | grep -c '^kind:'`
Expected: the previous count (Step 7) plus the `kind:` count of `platform/providers/aws_account/deploy/aws-account-provider.yaml` and `platform/providers/crossplane_aws/deploy/crossplane-aws-provider.yaml` combined.

- [ ] **Step 9: Verify the registry/tag composition in both states**

Run:
```bash
helm template platform-control-plane platform/chart/platform-control-plane | grep 'image: "registry-provider:dev"'
helm template platform-control-plane platform/chart/platform-control-plane --set registry=ghcr.io/smsilva/wasp-idp --set images.registryProvider.tag=v0.3.1 --set images.foragerProvider.tag=v0.2.0-rc.1 | grep -E 'image: "ghcr.io/smsilva/wasp-idp/(registry|forager)-provider:v0\.[32]\.'
```
Expected: the first command prints the unprefixed `registry-provider:dev` line; the second prints both images, each resolved to its own independent tag under the shared registry prefix (e.g. `ghcr.io/smsilva/wasp-idp/registry-provider:v0.3.1` and `ghcr.io/smsilva/wasp-idp/forager-provider:v0.2.0-rc.1`), confirming the `platform-control-plane.image` helper composes `<registry>/<repository>:<tag>` correctly in both the empty- and set-`registry` cases.

- [ ] **Step 10: Commit**

```bash
git add platform/chart/platform-control-plane/Chart.yaml platform/chart/platform-control-plane/values.yaml platform/chart/platform-control-plane/templates/_helpers.tpl platform/chart/platform-control-plane/templates/api platform/chart/platform-control-plane/templates/providers/local-vcluster-provider.yaml platform/chart/platform-control-plane/templates/providers/scm-github-provider.yaml platform/chart/platform-control-plane/templates/providers/workload-provider.yaml platform/chart/platform-control-plane/templates/providers/forager-provider.yaml platform/chart/platform-control-plane/templates/providers/registry-provider.yaml platform/chart/platform-control-plane/templates/providers/aws-account-provider.yaml platform/chart/platform-control-plane/templates/providers/crossplane-aws-provider.yaml
git commit -m "feat(chart): platform-control-plane umbrella chart, the 8 imaged components"
```

---

### Task 3: The 9 non-imaged templates (Keycloak, realm import, pod security, Traefik, Crossplane core, shared-pg, profile policies, Prometheus)

**Files:**
- Create: `platform/chart/platform-control-plane/templates/keycloak/keycloak.yaml`
- Create: `platform/chart/platform-control-plane/templates/keycloak/realm-import.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/pod-security.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/traefik.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/crossplane.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/provider-aws-ec2.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/shared-pg.yaml`
- Create: `platform/chart/platform-control-plane/templates/providers/profile-policies.yaml`
- Create: `platform/chart/platform-control-plane/templates/observability/prometheus.yaml`

**Interfaces:**
- Consumes: `templates/_helpers.tpl` is not needed here (none of these 9 manifests has a variable image — they use fixed upstream images like `quay.io/keycloak/keycloak:26.5.5`, `prom/prometheus:v3.5.0`, which stay hardcoded, unchanged).
- Produces: the chart's full set of 16 original manifests, ready for Task 4 to render from.

- [ ] **Step 1: Convert `keycloak.yaml`**

Read `platform/keycloak/deploy/keycloak.yaml`. Create `platform/chart/platform-control-plane/templates/keycloak/keycloak.yaml` with `namespace: platform-auth` → `{{ .Values.authNamespace }}` everywhere it appears (the `Namespace` object, the `PersistentVolumeClaim`, the `Deployment`, the `Service`). The `quay.io/keycloak/keycloak:26.5.5` image stays hardcoded (not parameterized — Keycloak's version is pinned platform-wide, not one of the 8 control-plane-built images). Every other line (the init container, the env vars including `KC_HOSTNAME`, the readiness probe, the PVC size, the Service ports) copied verbatim.

- [ ] **Step 2: Convert `realm-import.yaml`**

Read `platform/keycloak/deploy/realm-import.yaml`. Create `platform/chart/platform-control-plane/templates/keycloak/realm-import.yaml` with `namespace: platform-auth` → `{{ .Values.authNamespace }}`. The `adorsys/keycloak-config-cli:6.5.1-26.5.5` image stays hardcoded. Every env var, secretRef, and volume copied verbatim.

- [ ] **Step 3: Convert `pod-security.yaml`**

Read `platform/providers/local_vcluster/deploy/pod-security.yaml`. This file has no `namespace:` field at all (both objects are cluster-scoped: `ValidatingAdmissionPolicy` and `ValidatingAdmissionPolicyBinding`). Create `platform/chart/platform-control-plane/templates/providers/pod-security.yaml` as a byte-for-byte copy — no template expressions needed, confirmed by reading the source: every `metadata:` block in that file has only a `name:`, never a `namespace:`.

- [ ] **Step 4: Convert `traefik.yaml`**

Read `platform/providers/local_vcluster/deploy/traefik.yaml`. Create `platform/chart/platform-control-plane/templates/providers/traefik.yaml` with `targetNamespace: platform-ingress` → `targetNamespace: {{ .Values.ingressNamespace }}`. The `namespace: kube-system` of the `HelmChart` CR's own `metadata` stays hardcoded (`kube-system` is where k3s's helm-controller watches for `HelmChart` objects — not a value this chart's `namespace`/`authNamespace` values apply to). Every other field (`repo`, `chart`, `version`, `valuesContent`) copied verbatim.

- [ ] **Step 5: Convert `crossplane.yaml` and `provider-aws-ec2.yaml`**

Read `platform/providers/crossplane_aws/deploy/crossplane.yaml` and `platform/providers/crossplane_aws/deploy/provider-aws-ec2.yaml`. Neither has a `namespace:` referencing one of this chart's values (`crossplane.yaml`'s own `metadata.namespace` is `kube-system`, same reasoning as Traefik's `HelmChart`; its `targetNamespace: crossplane-system` matches `.Values.crossplaneNamespace` — change that one field to `{{ .Values.crossplaneNamespace }}`; `provider-aws-ec2.yaml`'s `Provider` CR is cluster-scoped, no namespace at all). Create both files under `platform/chart/platform-control-plane/templates/providers/`, wrapped in `{{- if .Values.providers.crossplaneAws.enabled }}` / `{{- end }}` each (Crossplane core and the AWS EC2 provider package only install when `install_crossplane` decides to, mirroring `wants_crossplane()`'s gating in `local.py`).

- [ ] **Step 6: Convert `shared-pg.yaml`**

Read `platform/providers/forager/deploy/shared-pg.yaml`. Create `platform/chart/platform-control-plane/templates/providers/shared-pg.yaml` with `namespace: platform-resources` → `{{ .Values.resourcesNamespace }}` (both the `Service` and the `StatefulSet`). The `postgres:17-alpine` image stays hardcoded. The `secretKeyRef: shared-pg-admin` reference copied verbatim (the Secret itself is generated by `install_shared_pg` in Python, unchanged — see Task 4).

- [ ] **Step 7: Convert `profile-policies.yaml`**

Read `platform/providers/forager/deploy/profile-policies.yaml`. Create `platform/chart/platform-control-plane/templates/providers/profile-policies.yaml` with `namespace: platform-system` → `{{ .Values.namespace }}`. Every other field (the `BindingPolicy`'s `spec`) copied verbatim.

- [ ] **Step 8: Convert `prometheus.yaml`**

Read `platform/observability/deploy/prometheus.yaml`. Create `platform/chart/platform-control-plane/templates/observability/prometheus.yaml` with `namespace: platform-system` → `{{ .Values.namespace }}` everywhere (the `ServiceAccount`, `ConfigMap`, `Service`, `NetworkPolicy`, `Deployment`). The `prom/prometheus:v3.5.0` image stays hardcoded. The `platform.wasp.silvios.me/config-hash: dev` annotation is left as literal `dev` in the template — `install_observability` in Python patches the rendered manifest's hash after rendering, the same two-step process it does today (see Task 4, Step 6), not something the chart computes.

- [ ] **Step 9: Lint and render the full chart**

Run: `helm lint platform/chart/platform-control-plane`
Expected: `0 chart(s) failed`

Run: `helm template platform-control-plane platform/chart/platform-control-plane --set providers.awsAccount.enabled=true --set providers.crossplaneAws.enabled=true | grep -c '^kind:'`
Expected: the sum of `kind:` occurrences across all 16 original source files — verify with: `grep -c '^kind:' platform/api/deploy/platform-api.yaml platform/keycloak/deploy/keycloak.yaml platform/keycloak/deploy/realm-import.yaml platform/providers/local_vcluster/deploy/*.yaml platform/providers/scm_github/deploy/scm-github-provider.yaml platform/providers/workload/deploy/workload-provider.yaml platform/providers/forager/deploy/*.yaml platform/providers/registry/deploy/registry-provider.yaml platform/providers/aws_account/deploy/aws-account-provider.yaml platform/providers/crossplane_aws/deploy/*.yaml platform/observability/deploy/prometheus.yaml | awk -F: '{sum+=$2} END {print sum}'` — the two counts must match.

- [ ] **Step 10: Commit**

```bash
git add platform/chart/platform-control-plane/templates/keycloak platform/chart/platform-control-plane/templates/providers/pod-security.yaml platform/chart/platform-control-plane/templates/providers/traefik.yaml platform/chart/platform-control-plane/templates/providers/crossplane.yaml platform/chart/platform-control-plane/templates/providers/provider-aws-ec2.yaml platform/chart/platform-control-plane/templates/providers/shared-pg.yaml platform/chart/platform-control-plane/templates/providers/profile-policies.yaml platform/chart/platform-control-plane/templates/observability
git commit -m "feat(chart): platform-control-plane umbrella chart, the 9 non-imaged components"
```

---

### Task 4: `local.py` renders from the chart instead of reading raw YAML

**Files:**
- Modify: `cli/src/wasp_platform/bootstrap/local.py`
- Test: `cli/tests/test_images.py` (new tests for `_render`, alongside the existing `build_images`/`import_images` tests)

**Interfaces:**
- Consumes: the chart at `platform/chart/platform-control-plane` from Tasks 2–3; `_run` (already in `local.py`) for subprocess execution.
- Produces: `_render(root: Path, template_path: str, set_values: dict[str, str] | None = None) -> str` — renders one template from the chart and returns the manifest text, for every call site in this task to pipe into `_kubectl("apply", "--filename", "-", input=...)`.

- [ ] **Step 1: Write the failing test for `_render`**

Add to `cli/tests/test_images.py` (the file already has the `cluster` fixture pattern for mocking `_run`):

```python
def test_render_calls_helm_template_show_only(monkeypatch):
  calls = []

  def run(*command, input=None, secret=False):
    calls.append(command)
    return "apiVersion: v1\nkind: ServiceAccount\n"

  monkeypatch.setattr(local, "_run", run)
  root = Path("/repo")
  manifest = local._render(root, "templates/providers/registry-provider.yaml", {"images.registryProvider.tag": "abc123"})
  assert manifest == "apiVersion: v1\nkind: ServiceAccount\n"
  assert calls == [(
    "helm", "template", "platform-control-plane", str(root / "platform" / "chart" / "platform-control-plane"),
    "--show-only", "templates/providers/registry-provider.yaml",
    "--set", "images.registryProvider.tag=abc123",
  )]


def test_render_with_no_set_values(monkeypatch):
  calls = []
  monkeypatch.setattr(local, "_run", lambda *command, input=None, secret=False: calls.append(command) or "rendered\n")
  local._render(Path("/repo"), "templates/keycloak/keycloak.yaml")
  assert calls == [(
    "helm", "template", "platform-control-plane", str(Path("/repo") / "platform" / "chart" / "platform-control-plane"),
    "--show-only", "templates/keycloak/keycloak.yaml",
  )]


def test_render_propagates_failure_on_a_bad_template_path(monkeypatch):
  """`helm template --show-only` on a path the chart does not have exits non-zero; `_run` already turns
  that into a BootstrapError (local.py:133) — `_render` must not swallow it into an empty manifest."""
  def run(*command, input=None, secret=False):
    raise local.BootstrapError("helm template … failed:\ncould not find template templates/providers/regsitry-provider.yaml in chart")

  monkeypatch.setattr(local, "_run", run)
  with pytest.raises(local.BootstrapError, match="regsitry-provider"):
    local._render(Path("/repo"), "templates/providers/regsitry-provider.yaml")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cli && uv run pytest tests/test_images.py::test_render_calls_helm_template_show_only tests/test_images.py::test_render_with_no_set_values tests/test_images.py::test_render_propagates_failure_on_a_bad_template_path -v`
Expected: FAIL with `AttributeError: module 'wasp_platform.bootstrap.local' has no attribute '_render'`

- [ ] **Step 3: Implement `_render`**

In `cli/src/wasp_platform/bootstrap/local.py`, add a `CHART_DIR` constant near the other path-shaped constants (right after `SEED_FOLDER = Path("platform") / "templates"`):

```python
CHART_DIR = Path("platform") / "chart" / "platform-control-plane"
CHART_NAME = "platform-control-plane"
```

Add `_render` right after `_deploy` (so the two sit together — `_deploy` will be rewritten in Step 4 to call `_render`):

```python
def _render(root: Path, template_path: str, set_values: dict[str, str] | None = None) -> str:
  """Renders one template of the control-plane chart, the same object `_kubectl("apply", ...)` used to
  read straight from a YAML file. `set_values` mirrors `--set key=value` (e.g. an image's tag)."""
  args = ["helm", "template", CHART_NAME, str(root / CHART_DIR), "--show-only", template_path]
  for key, value in (set_values or {}).items():
    args.extend(["--set", f"{key}={value}"])
  return _run(*args)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cli && uv run pytest tests/test_images.py::test_render_calls_helm_template_show_only tests/test_images.py::test_render_with_no_set_values tests/test_images.py::test_render_propagates_failure_on_a_bad_template_path -v`
Expected: PASS

- [ ] **Step 5: Rewrite `_deploy` to render from the chart**

Find the current `_deploy`:

```python
def _deploy(manifest_path: Path, name: str, image: str) -> None:
  manifest = manifest_path.read_text().replace(f"image: {name}:dev", f"image: {image}")
  _kubectl("apply", "--filename", "-", input=manifest)
```

Replace it with a version that renders the chart template instead of reading a file, keyed by the `images.<key>` name (not the manifest path, since the manifest's filename and the chart's values key no longer match 1:1 — e.g. `registry-provider.yaml` corresponds to `images.registryProvider`):

```python
# Maps the image constant (IMAGE, PROVIDER_IMAGE, ...) each _deploy call already passes to the chart's
# values key and template path, so this dict is the single place that pairing lives.
CHART_TEMPLATES = {
  IMAGE: ("templates/api/platform-api.yaml", "images.api"),
  PROVIDER_IMAGE: ("templates/providers/local-vcluster-provider.yaml", "images.localVclusterProvider"),
  SCM_PROVIDER_IMAGE: ("templates/providers/scm-github-provider.yaml", "images.scmGithubProvider"),
  WORKLOAD_PROVIDER_IMAGE: ("templates/providers/workload-provider.yaml", "images.workloadProvider"),
  FORAGER_PROVIDER_IMAGE: ("templates/providers/forager-provider.yaml", "images.foragerProvider"),
  REGISTRY_PROVIDER_IMAGE: ("templates/providers/registry-provider.yaml", "images.registryProvider"),
  AWS_PROVIDER_IMAGE: ("templates/providers/aws-account-provider.yaml", "images.awsAccountProvider"),
  CROSSPLANE_PROVIDER_IMAGE: ("templates/providers/crossplane-aws-provider.yaml", "images.crossplaneAwsProvider"),
}


def _deploy(root: Path, name: str, image: str) -> None:
  template_path, values_key = CHART_TEMPLATES[name]
  set_values = {f"{values_key}.tag": image.split(":", 1)[1]}
  if name == AWS_PROVIDER_IMAGE:
    set_values["providers.awsAccount.enabled"] = "true"
  if name == CROSSPLANE_PROVIDER_IMAGE:
    set_values["providers.crossplaneAws.enabled"] = "true"
  manifest = _render(root, template_path, set_values)
  _kubectl("apply", "--filename", "-", input=manifest)
```

Note the signature change: `_deploy` now takes `root: Path` where it used to take `manifest_path: Path`, since it renders from the chart (which needs the repo root) instead of reading a file path. Every call site must be updated in the next step.

- [ ] **Step 6: Update every `_deploy` and `_kubectl("apply", "--filename", str(...))` call site**

Each of these lines in `local.py` currently builds a `Path` to a `deploy/*.yaml` file; each must be replaced per the table below. Read the surrounding function first with `grep -n -B5 -A2 "<line>" cli/src/wasp_platform/bootstrap/local.py` to confirm you are editing the right call before changing it, since several functions share similar shapes.

| Current call (line, approximate) | Replace with |
|---|---|
| `_deploy(provider_dir / "deploy" / "aws-account-provider.yaml", AWS_PROVIDER_IMAGE, image)` (in `install_aws_account`, ~line 437) | `_deploy(root, AWS_PROVIDER_IMAGE, image)` — `install_aws_account`'s signature must gain a `root: Path` parameter; its caller in `init_tasks` already has `root` in scope, update the call there too |
| `_deploy(provider_dir / "deploy" / "crossplane-aws-provider.yaml", CROSSPLANE_PROVIDER_IMAGE, image)` (in `install_crossplane`, ~line 527) | `_deploy(root, CROSSPLANE_PROVIDER_IMAGE, image)` — same `root: Path` parameter addition to `install_crossplane` |
| `_deploy(provider_dir / "deploy" / manifest, name, image)` (in `deploy_provider`, ~line 559) | `_deploy(root, name, image)` — `deploy_provider`'s signature changes from `(directory, manifest, name, image)` to `(root, name, image)`; its caller (the `provider(...)` closure inside `init_tasks`) already captures `root` as a free variable, so only the lambda body changes, not `provider`'s own signature |
| `_deploy(api_dir / "deploy" / "platform-api.yaml", IMAGE, results["build images"][IMAGE])` (in `api()`, inside `init_tasks`, ~line 587) | `_deploy(root, IMAGE, results["build images"][IMAGE])` — `root` is already in scope inside `init_tasks` |
| `_kubectl("apply", "--filename", str(keycloak_dir / "deploy" / "keycloak.yaml"))` (in `deploy_keycloak`, ~line 298) | `_kubectl("apply", "--filename", "-", input=_render(root, "templates/keycloak/keycloak.yaml"))` — `deploy_keycloak`'s signature gains nothing new (it already takes `root: Path`) |
| `_kubectl("apply", "--filename", str(keycloak_dir / "deploy" / "realm-import.yaml"))` (in `import_realm`, ~line 347) | `_kubectl("apply", "--filename", "-", input=_render(root, "templates/keycloak/realm-import.yaml"))` — `import_realm` already takes `root: Path` |
| `_kubectl("apply", "--filename", str(provider_dir / "deploy" / "crossplane.yaml"))` (in `install_crossplane`, ~line 512) | `_kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/crossplane.yaml", {"providers.crossplaneAws.enabled": "true"}))` |
| `_kubectl("apply", "--filename", str(provider_dir / "deploy" / "provider-aws-ec2.yaml"))` (in `install_crossplane`, ~line 524) | `_kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/provider-aws-ec2.yaml", {"providers.crossplaneAws.enabled": "true"}))` |
| `Task("pod policy", lambda results: _kubectl("apply", "--filename", str(vcluster_dir / "deploy" / "pod-security.yaml")), needs=("CRDs",))` (in `init_tasks`, ~line 605) | `Task("pod policy", lambda results: _kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/pod-security.yaml")), needs=("CRDs",))` |
| `_kubectl("apply", "--filename", str(provider_dir / "deploy" / "traefik.yaml"))` (in `install_ingress`, ~line 649) | `_kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/traefik.yaml"))` — `install_ingress` currently takes `provider_dir: Path`; change its signature to take `root: Path` instead, and update its one call site in `init_tasks` (`Task("traefik", lambda results: install_ingress(vcluster_dir), ...)` becomes `Task("traefik", lambda results: install_ingress(root), ...)`) |
| `_kubectl("create", "--filename", str(forager_dir / "deploy" / "profile-policies.yaml"))` (in `install_profile_policies`, ~line 672) | `_kubectl("create", "--filename", "-", input=_render(root, "templates/providers/profile-policies.yaml"))` — `install_profile_policies` currently takes `forager_dir: Path`; change to `root: Path`, update its call site in `init_tasks` the same way as `install_ingress` above |
| `_kubectl("apply", "--filename", str(forager_dir / "deploy" / "shared-pg.yaml"))` (in `install_shared_pg`, ~line 684) | `_kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/shared-pg.yaml"))` — same `forager_dir` → `root` signature change, same call-site update pattern |
| `manifest = (observability_dir / "deploy" / "prometheus.yaml").read_text()` ... `_kubectl("apply", "--filename", "-", input=manifest.replace(...))` (in `install_observability`, ~line 659) | `manifest = _render(root, "templates/observability/prometheus.yaml")` then keep the existing `checksum = hashlib.sha256(...)` and `_kubectl("apply", "--filename", "-", input=manifest.replace("config-hash: dev", f"config-hash: {checksum}"))` lines unchanged — `install_observability` currently takes `observability_dir: Path`; change to `root: Path`, same call-site update pattern |

For every function whose parameter changes from a specific subdirectory (`provider_dir`, `forager_dir`, `vcluster_dir`, `observability_dir`, `keycloak_dir`) to `root`, grep its remaining body for other uses of that old parameter first (e.g. `keycloak_dir` is also used for `realm-platform.yaml`, `realm-smoke.yaml`, and the `theme` folder in `deploy_keycloak` — those stay as direct file reads, unrelated to this chart, so `deploy_keycloak` needs *both* `root` and the derived `keycloak_dir = root / "platform" / "keycloak"` kept alongside each other, not a wholesale replacement).

- [ ] **Step 7: Update `init_tasks` call sites for every signature change from Step 6**

In `init_tasks`, update the lambdas/closures for: `install_aws_account`, `install_crossplane`, `deploy_provider` (used by the `provider(...)` closure — confirm whether `provider`'s own signature needs `root` added or already has it captured, by reading `init_tasks` fully with `sed -n '563,618p' cli/src/wasp_platform/bootstrap/local.py` before editing), `install_ingress`, `install_profile_policies`, `install_shared_pg`, `install_observability`. Each lambda currently passes a specific subdirectory (e.g. `vcluster_dir`, `forager_dir`); change each to pass `root` instead, matching the new signatures from Step 6.

- [ ] **Step 8: Run the full existing test suite**

Run: `cd cli && uv run pytest tests/ -v`
Expected: all PASS — this is the regression check for every signature change in Steps 5–7. Pay particular attention to `tests/test_images.py`'s existing `test_builds_every_image`/`test_imports_every_missing_image_in_one_call`/`test_an_image_the_node_already_has_is_not_imported` (they exercise `build_images`/`import_images`, untouched by this task, but import the same module) and `tests/test_init.py` (exercises `install()` end-to-end via mocking — confirm its `installed`/`no_install` fixtures still work with the new `_render` call path, since `install()` itself calls `init_tasks(root, ...)` which now threads `root` through more functions than before).

- [ ] **Step 9: Manual smoke test against a real k3d cluster**

This step cannot be unit-tested (it exercises Helm against a live cluster) — run it by hand once:

```bash
cd /path/to/wasp-idp
platform init --admin you@example.com --yes
```

Expected: `init` completes with the same `21 / 21 steps` count and step names as before this plan (compare against a `init` run from before this plan, or against the walkthrough's documented output in `platform/docs/reference/init.md`); `kubectl --context k3d-platform-local get deployments -A` shows every Deployment the pre-chart manifests created (`platform-api`, `keycloak`, `local-vcluster-provider`, `scm-github-provider`, `workload-provider`, `forager-provider`, `registry-provider`, `prometheus`).

- [ ] **Step 10: Commit**

```bash
git add cli/src/wasp_platform/bootstrap/local.py cli/tests/test_images.py
git commit -m "feat(cli): platform init renders manifests from the control-plane chart"
```

---

### Task 5: CI workflow — build the 8 images, package and publish the chart to GHCR

**Files:**
- Create: `.github/workflows/platform-control-plane-release.yaml`

**Interfaces:**
- Consumes: the 8 Dockerfiles (`platform/api/Dockerfile`, `platform/providers/local_vcluster/Dockerfile`, `platform/providers/scm_github/Dockerfile`, `platform/providers/workload/Dockerfile`, `platform/providers/forager/Dockerfile`, `platform/providers/registry/Dockerfile`, `platform/providers/aws_account/Dockerfile`, `platform/providers/crossplane_aws/Dockerfile`); the chart at `platform/chart/platform-control-plane` from Tasks 2–3.
- Produces: 8 images at `ghcr.io/<org>/<repo>/<image-name>:<tag>` and one chart OCI artifact at `oci://ghcr.io/<org>/<repo>/charts/platform-control-plane:<chart-version>`, for a future `remote` target to reference (out of scope for this plan — see spec's "Relationship to #558").

- [ ] **Step 1: Write the workflow, modeled on the existing `platform-build.yaml` template's build job**

Read `platform/templates/python-service/content/.github/workflows/platform-build.yaml` first (already read during planning — the `build` job's `docker/setup-buildx-action`, `docker/login-action` with `secrets.GITHUB_TOKEN`, and `docker/build-push-action` steps are the pattern to follow). Create `.github/workflows/platform-control-plane-release.yaml`:

```yaml
# Builds the 8 control-plane images and packages/publishes the Helm chart to GHCR (#599), so a
# `remote` init target (future work, #558) has images and a chart to point at instead of only the
# local Docker build + k3d image import path. Triggered by a tag push or by hand.
name: platform-control-plane-release

on:
  push:
    tags:
      - 'control-plane-v*'
  workflow_dispatch:
    inputs:
      chart-version:
        description: Chart version to publish, without the leading "control-plane-v"
        required: true

jobs:
  build-images:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        include:
          - image: platform-api
            context: platform
            dockerfile: platform/api/Dockerfile
          - image: local-vcluster-provider
            context: platform/providers/local_vcluster
            dockerfile: platform/providers/local_vcluster/Dockerfile
          - image: scm-github-provider
            context: platform
            dockerfile: platform/providers/scm_github/Dockerfile
          - image: workload-provider
            context: platform/providers/workload
            dockerfile: platform/providers/workload/Dockerfile
          - image: forager-provider
            context: platform/providers/forager
            dockerfile: platform/providers/forager/Dockerfile
          - image: registry-provider
            context: platform/providers/registry
            dockerfile: platform/providers/registry/Dockerfile
          - image: aws-account-provider
            context: platform/providers/aws_account
            dockerfile: platform/providers/aws_account/Dockerfile
          - image: crossplane-aws-provider
            context: platform/providers/crossplane_aws
            dockerfile: platform/providers/crossplane_aws/Dockerfile
    steps:
      - uses: actions/checkout@v7
      - name: Compute tag
        id: tag
        run: |
          if [[ -n "${{ inputs.chart-version }}" ]]; then
            echo "tag=${{ inputs.chart-version }}" >> "${GITHUB_OUTPUT}"
          else
            echo "tag=${GITHUB_REF_NAME#control-plane-v}" >> "${GITHUB_OUTPUT}"
          fi
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v7
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.dockerfile }}
          provenance: false
          push: true
          tags: ghcr.io/${{ github.repository }}/${{ matrix.image }}:${{ steps.tag.outputs.tag }}

  publish-chart:
    needs: build-images
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v7
      - name: Compute version
        id: version
        run: |
          if [[ -n "${{ inputs.chart-version }}" ]]; then
            echo "version=${{ inputs.chart-version }}" >> "${GITHUB_OUTPUT}"
          else
            echo "version=${GITHUB_REF_NAME#control-plane-v}" >> "${GITHUB_OUTPUT}"
          fi
      - uses: azure/setup-helm@v4
        with:
          version: 'v3.14.0'
      - run: helm registry login ghcr.io --username ${{ github.actor }} --password ${{ secrets.GITHUB_TOKEN }}
      - run: helm package platform/chart/platform-control-plane --version "${{ steps.version.outputs.version }}" --app-version "${{ steps.version.outputs.version }}" --destination /tmp
      - run: helm push "/tmp/platform-control-plane-${{ steps.version.outputs.version }}.tgz" "oci://ghcr.io/${{ github.repository }}/charts"
```

- [ ] **Step 2: Validate the workflow's YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/platform-control-plane-release.yaml'))"`
Expected: no exception (confirms valid YAML before relying on GitHub Actions' own validation, which only runs on push)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/platform-control-plane-release.yaml
git commit -m "ci: build and publish the control-plane images and chart to GHCR"
```

---

## Final Validation

- [ ] Run the full test suite one more time: `cd cli && uv run pytest tests/ -v` — all PASS.
- [ ] Run `scripts/test/cli-smoke` (the fast local smoke suite, no vcluster) to confirm `init`'s behavior end-to-end is unaffected: `scripts/test/cli-smoke`.
- [ ] Confirm the chart's rendered object count still matches the original 16 manifests' combined `kind:` count (Task 3, Step 9's check, re-run once more after all tasks land).
