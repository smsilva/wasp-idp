FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}"
USER 65532
EXPOSE 8080
CMD ["uvicorn", "platform_api.app:build", "--factory", "--host", "0.0.0.0", "--port", "8080"]
