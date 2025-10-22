FROM bitnamilegacy/python:3.12

LABEL authors="Artyom Yudin"

ENV TZ="Europe/Moscow" \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get upgrade -y && \
    apt-get install ffmpeg -y && \
    apt-get clean && rm -rf /var/lib/apt/lists /var/cache/apt/archives

WORKDIR /app

# Сначала зависимости
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект (кроме .dockerignore)
COPY . /app

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

EXPOSE 80

CMD ["python", "-m", "app.main"]
