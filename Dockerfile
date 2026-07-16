FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY data/processed ./data/processed
COPY configs ./configs
EXPOSE 8000
CMD ["uvicorn", "gladiators.api:app", "--host", "0.0.0.0", "--port", "8000"]
