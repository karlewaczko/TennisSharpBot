# Runs the Telegram bot, the REST API, or the data updater loop, selected at
# `docker run`/compose time -- see docker-compose.yml for the easiest path
# (`docker compose up -d --build`), or run standalone:
#   docker build -t tennissharpbot .
#   docker run --env-file config/.env tennissharpbot python scripts/run_telegram_bot.py
#   docker run --env-file config/.env -p 8000:8000 tennissharpbot python scripts/run_api.py --host 0.0.0.0
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY scripts/ scripts/
COPY docker/ docker/
COPY data/ data/
COPY models/ models/
RUN pip install --no-cache-dir -e . && chmod +x docker/*.sh

CMD ["python", "scripts/run_telegram_bot.py"]
