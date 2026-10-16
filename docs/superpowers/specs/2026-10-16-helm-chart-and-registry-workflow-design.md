# Control plane as a Helm chart, published by CI — Design

Issue [#558](https://github.com/smsilva/wasp-idp/issues/558) names the goal this unblocks: a `remote` `Target` for `platform init` that installs the control plane on an existing cluster instead of only `local` (k3d). This spec covers the prerequisite only: packaging the control plane as a Helm chart and publishing it, with its images, from CI. `Target.remote` itself is a follow-up spec, once this lands.

## Problem

`platform init --target local` deploys the control plane (the Platform API, Keycloak, and 6 providers) by reading 16 hand-written Kubernetes manifests (`platform/*/deploy/*.yaml`, `platform/providers/*/deploy/*.yaml`, ~1500 lines total) and string-replacing a placeholder image tag before `kubectl apply`:

```python
def _deploy(manifest_path: Path, name: str, image: str) -> None:
  manifest = manifest_path.read_text().replace(f"image: {name}:dev", f"image: {image}")
  _kubectl("apply", "--filename", "-", input=manifest)
```

(`cli/src/wasp_platform/bootstrap/local.py:237`)

Every image is built locally with `docker build` and imported into the k3d cluster with `k3d image import` (`_build`, `_cluster_images`, `import_images` in `local.py`); nothing is ever published anywhere. This means:

- There is no way to install the control plane without a local Docker daemon building all 8 images on every `init`.
- There is no artifact (image or chart) another cluster could pull: a future `remote` target has nothing to point at.
- Parameterizing anything across environments (image tag, namespace, resource limits) means editing 16 raw YAML files or adding more ad hoc string replacement, the way `_deploy` already does for the image.

## Objectives

1. Package the control plane as a single Helm chart covering all 16 manifests `init` applies today (not only the 8 whose image `_deploy` substitutes) — Keycloak, its realm-import Job, the pod security policy, Traefik, Crossplane and its AWS EC2 provider, shared-pg, and Prometheus included. The chart is one artifact with one version; a future `remote` target points at it and never has to enumerate 8 image/tag pairs by hand.
2. Publish that chart, and the 8 provider/API images it references, from CI to an OCI registry — so a cluster that is not the one running `init` could eventually pull them (the `remote` target, next spec).
3. Change nothing about what gets installed, in what order, or how `local`'s progress output looks today: same objects, same RBAC, same step-by-step task graph and progress card (`17 / 21 steps`, per-step logs). Only the rendering mechanism (chart templates vs. raw YAML + string replace) and the addition of a publish workflow are new.

Out of scope: `Target.remote` itself, any change to ingress (Traefik stays as installed today), reworking how `local` obtains images (it keeps building locally, never pulls from the registry this spec publishes to).

## Decisions

### One umbrella chart, covering all 16 manifests, not one chart per component

A single chart, `platform-control-plane`, with one template per existing manifest (grouped by component as today: `api/`, `keycloak/`, `providers/<name>/`, plus `observability/` for Prometheus), one values tree with a key per image (the 8 `_deploy`-managed ones) and a flag per optional piece (`providers.awsAccount.enabled`, `providers.crossplaneAws.enabled`, mirroring `--aws-profile`/`--with-crossplane` today). The 8 manifests with no variable image (Keycloak's Deployment/PVC/Service, the realm-import Job, the pod-security `ValidatingAdmissionPolicy`, Traefik's `HelmChart` CR, Crossplane's `HelmChart` CR and its `Provider` CR, shared-pg, Prometheus) convert the same way: hardcoded namespaces become `{{ .Values.namespace }}`/`{{ .Values.authNamespace }}`/`{{ .Values.resourcesNamespace }}`, everything else (RBAC rules, labels, container args, the Prometheus scrape config, the admission policy's CEL expressions) copied verbatim.

**Alternative considered: one chart per component (16 independent charts, or 8 if only the imaged ones were converted).** Rejected: it would require orchestrating many separate `helm install` calls in the right dependency order (the API needs Keycloak's realm; providers need the CRDs) — exactly the ordering `init_tasks`' `needs=(...)` graph already encodes in Python. An umbrella chart keeps that ordering in `local.py` exactly as it is; the chart only replaces the rendering/apply step, not the task graph. Converting only the 8 imaged manifests was also considered and rejected: it would leave the chart unable to stand on its own as the one artifact a `remote` target points at — the other 8 (Keycloak above all) are load-bearing parts of "the control plane", not incidental extras.

### `local.py` keeps its 21-step task graph and progress card; each step renders from the chart instead of reading a file

`build_images`, `_cluster_images`, `import_images` (k3d-specific, Docker-based) are untouched. What changes inside `_deploy` (and the other `_kubectl("apply", ...)` call sites in `local.py` — `deploy_keycloak`, `import_realm`, `apply_crds`'s pod-security line, `install_ingress`, `install_crossplane`, `install_shared_pg`, `install_observability`) is *how* each step gets its manifest: `helm template <chart> --show-only templates/<path>` renders just that one object group from the chart, piped into the same `kubectl apply -f -` the step already does. Each task in `init_tasks()` keeps its own name, its own log file, its own position in the `17 / 21 steps` progress card — this spec changes the rendering source per step, not the step graph itself.

**Alternative considered: one `helm upgrade --install` call replacing the whole task graph.** Rejected for `local`: it would collapse `init`'s ~21 named steps (each with its own log file and line in the progress card, per `reporters.py`) into one opaque Helm operation, contradicting objective 3 ("same task order... same progress card"). Kept as the expected approach for a future `remote` target, which has no equivalent per-step local progress UI to preserve.

### A new CI workflow builds the 8 images and packages/publishes the chart to GHCR

A new `.github/workflows/platform-control-plane-release.yaml` (name indicative), triggered on push of a tag (e.g. `control-plane-v*`) or manual dispatch:

1. Builds the 8 images from their existing Dockerfiles (`platform/api/Dockerfile`, and one per provider under `platform/providers/*/Dockerfile`, including `crossplane_aws`), tags each with the triggering tag/ref, pushes to `ghcr.io/<org>/<repo>/<image-name>`.
2. Packages the Helm chart from objective 1, pushes it as an OCI artifact to the same registry (`helm push` to `oci://ghcr.io/<org>/<repo>/charts/platform-control-plane`).

**Registry: GHCR, public.** Consistent with how the platform already publishes user-component images (`ghcr-wasp-foundry`, walkthrough) and with the repo itself being public — none of the 8 Dockerfiles embed a secret or credential (verified by reading all 8; credentials are injected at runtime via Kubernetes Secrets, never baked into the image). Accepted as the unblocking choice now; **flagged to revisit later** if the control plane's images or chart should not be publicly pullable (e.g. once providers need authenticated pulls, mirroring the open question already tracked for user-component images in issues #367/#368).

**Each image versions independently, under one global `registry` value.** `values.yaml` has a single `registry` field (empty by default, so a local install resolves every `images.<key>.repository` to its bare short name — exactly what `local` has today, no behavior change) plus one `images.<key>` entry per image, each with its own `repository` and `tag`. A shared template helper (`platform-control-plane.image`) composes `<registry>/<repository>:<tag>` when `registry` is set, or just `<repository>:<tag>` when it is not, so no per-provider template repeats that concatenation. This means the CI workflow (or whoever releases a provider later) can bump one image's tag without touching the other 7 or the chart's own `Chart.yaml` version — confirmed by rendering a throwaway sketch of this chart with `helm template`, setting `registry` and two independent `images.*.tag` overrides, and checking the rendered `image:` lines resolved as expected.

**Alternative considered: all 8 images share one tag (a single "control plane version").** Rejected: it would force releasing all 8 together even when only one provider changed, and does not match how the chart's own version (`Chart.yaml`) already serves as the "coherent set" unit — a second, image-level version lock would be redundant with it.

### What does not change

- `init_tasks()`'s task graph, dependency ordering, step names, and per-step logging/progress card in `local.py`.
- RBAC, namespaces, CRDs, and every object the 16 manifests create today — the chart is a repackaging, not a redesign.
- The `local` developer experience: `platform init` prerequisites, flags, and output stay as documented today.
- Keycloak's dynamic setup in Python (`deploy_keycloak`/`render_realm`/`theme_configmap`/`_apply_theme` in `local.py`): generating the admin password, building the realm JSON per `--admin` list, flattening the theme directory into a ConfigMap. These stay exactly as they are — only the static Keycloak Deployment/PVC/Service manifest moves into the chart; the dynamically-generated Secrets and ConfigMaps the Deployment consumes are still applied by this existing Python code, the same way `local.py` already separates "generate a Secret in Python" from "apply a static manifest" for other components.

## Open questions (do not block this spec)

- Exact chart directory layout (`platform/chart/` at the repo root vs. nested per component) — a detail for the implementation plan.
- Whether GHCR public stays the long-term answer once provider pull credentials exist (tracked as a revisit, not a blocker).

## Relationship to #558

Once this chart exists and is published, `Target.remote` (separate spec) installs it with a single `helm upgrade --install platform-control-plane oci://ghcr.io/<org>/<repo>/charts/platform-control-plane --version <chart-version>` against a kubeconfig context that is not k3d — the one-call install the "Alternative considered" above rejects for `local` but is exactly right for `remote`, which has no per-step local progress UI to preserve and benefits from the one-chart-one-version simplicity this spec's packaging provides. This skips `ensure_cluster` (no cluster creation) and the local build/import steps entirely (the chart's `values.yaml` `registry` and each image's `tag` point at what CI published instead). Ingress, identity (Keycloak as today), and the `remote`-specific CLI config (so a non-admin user can `platform login` against it without running `init`) are explicitly deferred to that follow-up spec.
