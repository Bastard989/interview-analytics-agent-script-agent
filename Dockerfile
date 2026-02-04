# syntax=docker/dockerfile:1

############################
# Builder stage
############################
FROM python:3.11-slim AS builder

ARG DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND}

WORKDIR /app

# Build deps only (compile wheels if needed)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      libpq-dev \
      pkg-config \
      make \
 && rm -rf /var/lib/apt/lists/*

# Build wheels for faster + reproducible installs
COPY requirements.txt pyproject.toml ./
RUN python -m pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


############################
# Runtime stage
############################
FROM python:3.11-slim AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND}
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime deps only
# ffmpeg нужен твоему пайплайну (в коде есть вызовы ffmpeg)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      ffmpeg \
      libpq5 \
      openssl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
 && rm -rf /wheels

# App source
COPY . .

# Install project package (src/ layout)
RUN python -m pip install --no-cache-dir .

EXPOSE 8010

# compose переопределяет CMD для воркеров, тут дефолт для api-gateway
CMD ["python", "-m", "apps.api_gateway.main"]

COPY ops /app/ops
