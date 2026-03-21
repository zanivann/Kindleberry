FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    libgpiod2 \
    libgpiod-dev \
    gpiod \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gpiod

COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]