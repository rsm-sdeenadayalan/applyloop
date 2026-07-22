FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml README.md ./
COPY applyloop ./applyloop
RUN uv pip install --system .
COPY config ./config
CMD ["applyloop-web"]
