FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY config /app/config

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn family_financial_compass.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --app-dir src"]
