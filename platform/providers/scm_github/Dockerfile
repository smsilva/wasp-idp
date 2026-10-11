# Built with platform/ as the context (`docker build --file providers/scm_github/Dockerfile platform`):
# the provider depends on the template library in libs/templates (#279) and the Score gate in libs/score
# (#291) by path.
FROM python:3.12-slim
# git fetches the template content at its registered ref (wasp_templates.source.fetch).
RUN apt-get update \
  && apt-get install --yes --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app/providers/scm_github
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
COPY libs/templates /app/libs/templates
COPY libs/score /app/libs/score
COPY providers/scm_github/pyproject.toml providers/scm_github/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY providers/scm_github/src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/providers/scm_github/.venv/bin:${PATH}" HOME=/tmp
USER 65532
ENTRYPOINT ["scm-github-provider"]
