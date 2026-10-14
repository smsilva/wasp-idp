# Built with platform/ as the context (`docker build --file api/Dockerfile platform`): the API depends
# on the template library in libs/templates (#204) and the Score gate in libs/score (#291) by path.
FROM python:3.12-slim
WORKDIR /app/api
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
COPY libs/templates /app/libs/templates
COPY libs/score /app/libs/score
COPY api/pyproject.toml api/uv.lock ./
# The uv cache outlives the layer: a lock change downloads only the wheels that changed (#443).
RUN --mount=type=cache,target=/root/.cache/uv \
  UV_LINK_MODE=copy uv sync --frozen --no-dev --no-install-project
COPY api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
  UV_LINK_MODE=copy uv sync --frozen --no-dev
ENV PATH="/app/api/.venv/bin:${PATH}"
USER 65532
EXPOSE 8080
CMD ["uvicorn", "platform_api.app:build", "--factory", "--host", "0.0.0.0", "--port", "8080"]
