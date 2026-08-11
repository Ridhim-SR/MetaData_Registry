FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/data_services /app/data_services
COPY src/data_services/sample_data /app/sample_data

ENV PYTHONPATH=/app
ENV WATERMARK_FILE=/app/state/watermark.txt

VOLUME ["/app/state"]

CMD ["python", "-m", "data_services.pipelines.run"]