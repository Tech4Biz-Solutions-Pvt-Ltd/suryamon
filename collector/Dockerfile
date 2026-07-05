FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY suryamon_collector ./suryamon_collector
RUN pip install --no-cache-dir .
EXPOSE 9101
CMD ["python", "-m", "suryamon_collector.collector"]
