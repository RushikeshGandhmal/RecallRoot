FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY recallgraph ./recallgraph
RUN uv sync --frozen --no-dev

RUN mkdir -p /app/data \
    && addgroup --system recallgraph && adduser --system --ingroup recallgraph recallgraph \
    && chown -R recallgraph:recallgraph /app
USER recallgraph

EXPOSE 8000
CMD ["uvicorn", "recallgraph.main:app", "--host", "0.0.0.0", "--port", "8000"]
