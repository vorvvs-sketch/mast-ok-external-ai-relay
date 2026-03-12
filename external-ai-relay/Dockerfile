FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8020
ENV CATALOG_PATH=/app/catalog.json

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./app.py
COPY ../backend/catalog.json ./catalog.json

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
