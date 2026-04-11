FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    build-essential \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -Ls https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock* ./

RUN uv sync --frozen

COPY . .

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

EXPOSE 10000

CMD sh -c "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"