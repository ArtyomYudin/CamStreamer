FROM bitnamilegacy/python:3.12

LABEL authors="Artyom Yudin"

ENV TZ="Europe/Moscow" \
    PYTHONUNBUFFERED=1

SHELL ["/bin/bash", "-o", "errexit", "-o", "nounset", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get upgrade -y && \
    apt-get install ffmpeg -y && \
    apt-get clean && rm -rf /var/lib/apt/lists /var/cache/apt/archives

# set timezone
RUN if [ ! -z "${TZ}" ]; then ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime && echo "${TZ}" > /etc/timezone; fi

# Создаём пользователя и группу с UID/GID 1001 (совпадает с fsGroup в K8s)
RUN groupadd -g 1001 appuser && \
    useradd -u 1001 -g appuser -m -s /bin/bash appuser

WORKDIR /app

RUN echo "export PATH=/opt/bitnami/python/bin:${PATH}" >> /root/.bashrc
# Upgrade pip
RUN pip install --upgrade pip


COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

# Меняем владельца директории приложения на непривилегированного пользователя
RUN chown -R appuser:appuser /app

# Переключаемся на непривилегированного пользователя
USER 1001

EXPOSE 8080

CMD ["python", "-m", "app.main"]
