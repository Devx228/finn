# FINN API image. Runs on any Docker host; PORT is set by the host
# (Hugging Face Spaces expects 7860, Render/Koyeb inject $PORT).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=7860

# Hugging Face Spaces runs containers as uid 1000.
RUN useradd -m -u 1000 finn
WORKDIR /app

COPY pyproject.toml ./
COPY finn ./finn
RUN pip install .

USER finn
EXPOSE 7860
CMD ["sh", "-c", "finn migrate && uvicorn finn.api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
