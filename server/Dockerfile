FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema para o Pillow (manipulação de imagem)
RUN apt-get update && apt-get install -y libfreetype6-dev libjpeg-dev zlib1g-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]