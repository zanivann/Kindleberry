FROM python:3.9-slim

WORKDIR /app

# Instala as dependências (rpi-lgpio é essencial para o RPi 5)
RUN pip install --no-cache-dir psutil requests gpiozero rpi-lgpio

COPY agent.py .

CMD ["python", "-u", "agent.py"]