# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN --mount=type=secret,id=proxy_ca,required=true \
    PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir uv==0.12.23
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=proxy_ca,required=true \
    SSL_CERT_FILE=/run/secrets/proxy_ca uv sync --frozen --no-dev
COPY apps apps
COPY packages packages
COPY services services
COPY scripts scripts
COPY migrations migrations
COPY alembic.ini ./
RUN chmod -R a+rX /app && useradd --uid 10001 --no-create-home halal
USER halal
CMD [".venv/bin/uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
