FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install uv — pinned for reproducible builds (matches CI-era uv)
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv

# Dependency layer: only pyproject + lock invalidate it
# (README.md is required by hatchling's readme metadata, so it goes in this layer too)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY collector ./collector
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --no-create-home statless \
    && mkdir -p /app/data && chown -R statless:statless /app
USER statless

# GeoIP2 DB + SQLite file live here (mount a volume in production)
VOLUME /app/data
EXPOSE 8000

# Run the installed venv entrypoint directly (not `uv run`): the non-root user
# has no home directory for uv's cache, and this also skips uv's startup cost.
# The `statless` script applies STATLESS_HOST/STATLESS_PORT.
CMD ["/app/.venv/bin/statless"]
