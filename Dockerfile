FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY models ./models
# The postgres extra is installed in the image so one image serves both the
# SQLite default and a DATABASE_URL-driven PostgreSQL deployment.
RUN pip install --no-cache-dir ".[postgres]"
COPY dashboard ./dashboard
COPY scripts ./scripts
COPY docs ./docs
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

EXPOSE 8000
CMD ["uvicorn", "revenue_recovery.api:app", "--host", "0.0.0.0", "--port", "8000"]
