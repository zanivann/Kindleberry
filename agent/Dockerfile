FROM python:3.9-slim

WORKDIR /app

# Instala as dependências rigorosamente necessárias
RUN pip install --no-cache-dir psutil requests

COPY agent.py .

CMD ["python", "-u", "agent.py"]