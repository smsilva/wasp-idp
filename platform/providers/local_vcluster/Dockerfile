FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
# The controller drives the vcluster Helm chart; the chart is pulled at build time, so the
# cluster needs no access to charts.loft.sh at runtime.
COPY --from=alpine/helm:3.19.0 /usr/bin/helm /usr/local/bin/helm
ARG VCLUSTER_CHART_VERSION=0.37.2
RUN mkdir -p /charts \
  && helm pull vcluster --repo https://charts.loft.sh --version "${VCLUSTER_CHART_VERSION}" --destination /charts \
  && mv /charts/vcluster-*.tgz /charts/vcluster.tgz
# The mesh of every environment (ADR 0035), installed in the vcluster once it is up: Istio and the Gateway
# API CRDs it supports (Istio 1.30 -> Gateway API 1.5), moving together.
ARG ISTIO_VERSION=1.30.5
ARG GATEWAY_API_VERSION=v1.5.1
RUN helm pull base --repo https://istio-release.storage.googleapis.com/charts --version "${ISTIO_VERSION}" --destination /charts \
  && mv /charts/base-*.tgz /charts/istio-base.tgz \
  && helm pull istiod --repo https://istio-release.storage.googleapis.com/charts --version "${ISTIO_VERSION}" --destination /charts \
  && mv /charts/istiod-*.tgz /charts/istiod.tgz \
  && mkdir -p /manifests
ADD --chmod=644 https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml /manifests/gateway-api.yaml
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}" HOME=/tmp ISTIO_VERSION=${ISTIO_VERSION} GATEWAY_API_VERSION=${GATEWAY_API_VERSION}
USER 65532
ENTRYPOINT ["local-vcluster-provider"]
