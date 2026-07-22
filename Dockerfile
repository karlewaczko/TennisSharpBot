# Runs either the Telegram bot or the REST API, selected at `docker run` time.
# Build once, use for both:
#   docker build -t tennissharpbot .
#   docker run --env-file config/.env tennissharpbot python scripts/run_telegram_bot.py
#   docker run --env-file config/.env -p 8000:8000 tennissharpbot python scripts/run_api.py --host 0.0.0.0
#
# Data/model refresh (scripts/update_data.py) is expected to run separately
# (e.g. the GitHub Actions cron, or your own schedule) and be mounted in --
# this image does not run it automatically.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY scripts/ scripts/
COPY data/ data/
COPY models/ models/
RUN pip install --no-cache-dir -e .

CMD ["python", "scripts/run_telegram_bot.py"]
