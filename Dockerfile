FROM python:3.10.18-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy in our code
COPY . .

# Build and install it — AUTH_TOKEN is supplied as a BuildKit secret so it
# neither lands in image history nor busts the layer cache when rotated.
RUN --mount=type=secret,id=AUTH_TOKEN \
    make pip_setup_env AUTH_TOKEN=$(cat /run/secrets/AUTH_TOKEN)

# Activate the virtual environment by setting PATH
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["uv", "run", "--no-sync"]
