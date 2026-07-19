FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime

RUN groupadd -r banter && useradd -r -g banter banter

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app/ /app/app/
COPY main.py /app/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV APP_DEBUG=false
ENV APP_WEB_PORT=8001

EXPOSE 8001

USER banter

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/status')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
