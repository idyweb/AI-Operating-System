FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (Docker layer caching — deps rarely change)
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps in container)
RUN uv sync --frozen --no-dev

# Copy source
COPY . .

# Install package in editable mode so importlib.metadata works
RUN uv pip install -e . --no-deps

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000