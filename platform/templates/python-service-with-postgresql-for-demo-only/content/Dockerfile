FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY app/ app/

# The version and commit the home page shows; platform-build.yaml passes them.
ARG APP_VERSION=dev
ARG APP_COMMIT=unknown
ENV APP_VERSION=${APP_VERSION} \
    APP_COMMIT=${APP_COMMIT}

USER 10001

EXPOSE ${{ values.port }}

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${{ values.port }}"]
