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

1. Package the control plane as a single Helm chart, so `local.py` installs it with `helm upgrade --install` instead of per-file `kubectl apply` plus string replacement.
2. Publish that chart, and the 8 images it references, from CI to an OCI registry — so a cluster that is not the one running `init` could eventually pull them (the `remote` target, next spec).
3. Change nothing about what gets installed or how `local` behaves today: same objects, same RBAC, same task order, same local Docker build + `k3d image import` path. Only the deploy mechanism (chart vs. raw YAML) and the addition of a publish workflow are new.

Out of scope: `Target.remote` itself, any change to ingress (Traefik stays as installed today), reworking how `local` obtains images (it keeps building locally, never pulls from the registry this spec publishes to).

## Decisions

### One umbrella chart, not one chart per component

A single chart, `platform-control-plane`, with one template per existing manifest (grouped by component as today: `api/`, `keycloak/`, `providers/<name>/`), one values tree with a key per image. `helm upgrade --install platform-control-plane ./chart --namespace platform-system -f values.yaml` replaces the whole sequence of per-file `_deploy` calls.

**Alternative considered: one chart per component (8 independent charts).** Rejected: it would require orchestrating 8 separate `helm install` calls in the right dependency order (the API needs Keycloak's realm; providers need the CRDs) — exactly the ordering `init_tasks`' `needs=(...)` graph already encodes in Python. An umbrella chart keeps that ordering in `local.py` exactly as it is; the chart only replaces the rendering/apply step, not the task graph.

### `local.py` keeps building locally; only the apply mechanism changes

`build_images`, `_cluster_images`, `import_images` (k3d-specific, Docker-based) are untouched. The chart's `values.yaml` receives the locally-built image references (`platform-api:dev-<id>`, etc.) the same way `_deploy` receives them today — as a parameter, not a change to where images come from. `local` never pulls from the registry this spec adds; it continues to need nothing but Docker and k3d, as documented in `prerequisites.md`.

### A new CI workflow builds the 8 images and packages/publishes the chart to GHCR

A new `.github/workflows/platform-control-plane-release.yaml` (name indicative), triggered on push of a tag (e.g. `control-plane-v*`) or manual dispatch:

1. Builds the 8 images from their existing Dockerfiles (`platform/api/Dockerfile`, and one per provider under `platform/providers/*/Dockerfile`, including `crossplane_aws`), tags each with the triggering tag/ref, pushes to `ghcr.io/<org>/<repo>/<image-name>`.
2. Packages the Helm chart from objective 1, pushes it as an OCI artifact to the same registry (`helm push` to `oci://ghcr.io/<org>/<repo>/charts/platform-control-plane`).

**Registry: GHCR, public.** Consistent with how the platform already publishes user-component images (`ghcr-wasp-foundry`, walkthrough) and with the repo itself being public — none of the 8 Dockerfiles embed a secret or credential (verified by reading all 8; credentials are injected at runtime via Kubernetes Secrets, never baked into the image). Accepted as the unblocking choice now; **flagged to revisit later** if the control plane's images or chart should not be publicly pullable (e.g. once providers need authenticated pulls, mirroring the open question already tracked for user-component images in issues #367/#368).

**Tag/version scheme inside the chart:** left to the implementation plan, not fixed here. The chart's own version (`Chart.yaml`) is the unit that matters for this spec — whether the 8 images inside it share one tag or version independently does not block packaging or publishing.

### What does not change

- `init_tasks()`'s task graph, dependency ordering, and step names in `local.py`.
- RBAC, namespaces, CRDs, and every object the 16 manifests create today — the chart is a repackaging, not a redesign.
- The `local` developer experience: `platform init` prerequisites, flags, and output stay as documented today.

## Open questions (do not block this spec)

- Exact chart directory layout (`platform/chart/` at the repo root vs. nested per component) — a detail for the implementation plan.
- Whether the 8 images share the chart's tag or version independently.
- Whether GHCR public stays the long-term answer once provider pull credentials exist (tracked as a revisit, not a blocker).

## Relationship to #558

Once this chart exists and is published, `Target.remote` (separate spec) reuses the same chart via `helm upgrade --install` against a kubeconfig context that is not k3d, skipping `ensure_cluster` (no cluster creation) and the local build/import steps (pulls the chart's referenced images from the registry instead). Ingress, identity (Keycloak as today), and the `remote`-specific CLI config (so a non-admin user can `platform login` against it without running `init`) are explicitly deferred to that follow-up spec.
