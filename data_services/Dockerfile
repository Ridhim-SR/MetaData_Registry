FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src

ENV PYTHONPATH=/app:/app/src
ENV WATERMARK_FILE=/app/state/watermark.txt

VOLUME ["/app/state"]

CMD ["python", "-m", "src.pipelines.run"]