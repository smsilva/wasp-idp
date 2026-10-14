FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
# The uv cache outlives the layer: a lock change downloads only the wheels that changed (#443).
RUN --mount=type=cache,target=/root/.cache/uv \
  UV_LINK_MODE=copy uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
  UV_LINK_MODE=copy uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}" HOME=/tmp
USER 65532
ENTRYPOINT ["forager-provider"]
