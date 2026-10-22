
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-cache

COPY . .

RUN uv sync --frozen --no-cache

CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run python -m bot"]
