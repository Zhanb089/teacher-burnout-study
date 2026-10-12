# Pinned base image: fixed Python minor+patch version and Debian release
FROM python:3.11.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install exact dependency versions first (better layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config.yaml ./config.yaml
COPY src ./src
COPY data ./data

# Default command: run the pipeline on the sample data
CMD ["python", "src/benchmark.py", "--config", "config.yaml"]
