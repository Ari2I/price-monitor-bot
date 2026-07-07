# Образ на основе Debian slim — нужен apt для системных зависимостей
# Playwright (Chromium требует набор системных библиотек).
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем Python-зависимости отдельным слоем — если requirements.txt
# не менялся, Docker переиспользует кэш и не переустанавливает всё заново.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Браузер Playwright скачиваем в каталог внутри /app, чтобы позже отдать
# его в собственность непривилегированному пользователю (см. ниже).
ENV PLAYWRIGHT_BROWSERS_PATH=/app/pw-browsers
RUN playwright install --with-deps chromium

# Копируем код приложения.
COPY . .

# Контейнер не должен работать от root без необходимости — создаём
# отдельного пользователя и передаём ему права на рабочий каталог.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
