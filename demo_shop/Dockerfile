FROM python:3.13-slim

# Bring in the uv binary from its official image (same version as your Mac)
COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /bin/

# Use the image's Python, never download another one
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 1) Install dependencies only. This layer is cached until pyproject/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

# 2) Copy the code and install the project itself
COPY . .
RUN uv sync --locked --no-dev

# Put the environment's programs (like uvicorn) on the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Cloud Run sends traffic to port 8080 by default
CMD ["uvicorn", "demo_shop.main:app", "--host", "0.0.0.0", "--port", "8080"]