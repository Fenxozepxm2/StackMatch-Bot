FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-cache

COPY . .


CMD ["sh", "-c", "uv run alembic upgrade head && uv run python -m bot"]