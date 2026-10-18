FROM python:3.13-slim
WORKDIR /app
COPY requirements-api.lock pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements-api.lock && pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home memory && mkdir /data && chown memory:memory /data
USER 10001:10001
ENV MEMORY_DB=/data/memory.db PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]
CMD ["uvicorn", "memory_engine.api:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
