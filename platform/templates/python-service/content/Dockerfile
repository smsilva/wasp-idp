FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY app/ app/

USER 10001

EXPOSE ${{ values.port }}

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${{ values.port }}"]
