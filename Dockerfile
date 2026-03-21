FROM python:3.11-slim

ARG USERNAME=appuser
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# System packages
RUN apt-get update && \
    apt-get install --no-install-recommends -y ffmpeg rubberband-cli imagemagick curl unzip fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh && \
    sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-6/policy.xml 2>/dev/null; \
    sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-7/policy.xml 2>/dev/null; true

# Create non-root user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd -s /bin/bash --uid $USER_UID --gid $USER_GID -m $USERNAME

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies as root, then hand ownership to appuser
WORKDIR /app
COPY --chown=$USERNAME:$USERNAME pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project && \
    chown -R $USERNAME:$USERNAME /app

COPY --chown=$USERNAME:$USERNAME . .

USER $USERNAME
