FROM python:3.11-slim

WORKDIR /app

# Instala apenas o necessário para o hardware do Pi 5
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libfreetype6-dev \
    libjpeg-dev \
    zlib1g-dev \
    libgpiod-dev \
    gpiod \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Precisamos do gpiod para o python também
RUN pip install --no-cache-dir -r requirements.txt gpiod

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]