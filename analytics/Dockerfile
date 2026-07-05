FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY suryamon_analytics ./suryamon_analytics
RUN pip install --no-cache-dir .
CMD ["python", "-m", "suryamon_analytics.service"]
