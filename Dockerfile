FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files first for layer caching
COPY pyproject.toml .python-version ./

# Install dependencies
RUN uv sync --no-dev

# Copy application code
COPY reviewray/ reviewray/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uv", "run", "uvicorn", "reviewray.main:app", "--host", "0.0.0.0", "--port", "8000"]
