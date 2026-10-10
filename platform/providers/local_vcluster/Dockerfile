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
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}" HOME=/tmp
USER 65532
ENTRYPOINT ["local-vcluster-provider"]
