FROM python:3.11-slim

# Установка ffmpeg и зависимостей
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY server.py streamer.py ./

# Порты для камер
EXPOSE 9996 9997 9998 9999

# Запуск
CMD ["python", "server.py"]