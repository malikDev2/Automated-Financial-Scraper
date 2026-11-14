FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PREFECT_LOGGING_EXTRA_LOGGERS=fin_scraper

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY sql ./sql
COPY dags ./dags

RUN useradd --create-home etl && mkdir -p /app/data && chown -R etl:etl /app
USER etl

# Registers the Prefect deployment and keeps polling for scheduled runs.
CMD ["python", "-m", "fin_scraper", "serve"]
