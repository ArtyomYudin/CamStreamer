FROM bitnamilegacy/python:3.12

LABEL authors="Artyom Yudin"

ENV TZ="Europe/Moscow" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект (кроме .dockerignore)
COPY . /app

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

EXPOSE 8080

CMD ["python", "-m", "app.main"]
