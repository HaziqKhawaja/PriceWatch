# Build context is the repo root (see docker-compose.yml).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /srv
COPY mock_retailers/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY mock_retailers/ ./mock_retailers/
RUN useradd --create-home app
USER app
EXPOSE 8080
CMD ["uvicorn", "mock_retailers.app:app", "--host", "0.0.0.0", "--port", "8080"]
