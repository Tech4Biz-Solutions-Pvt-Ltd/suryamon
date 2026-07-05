FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY suryamon_simulator ./suryamon_simulator
RUN pip install --no-cache-dir .
EXPOSE 1502
CMD ["python", "-m", "suryamon_simulator.simulator"]
