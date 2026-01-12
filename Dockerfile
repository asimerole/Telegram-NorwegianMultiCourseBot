# Використовуємо легкий Python 3.11
FROM python:3.11-slim

# Забороняємо Python створювати .pyc файли і змушуємо виводити логи відразу
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Робоча папка всередині контейнера
WORKDIR /app

# Встановлюємо системні бібліотеки (потрібні для psycopg2 і Pillow)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо файл з залежностями
COPY requirements.txt .

# Встановлюємо бібліотеки Python
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь код проекту всередину
COPY . .

# Цей порт буде відкритий для Адмінки
EXPOSE 8000

# За замовчуванням запускаємо бота (але в compose ми це перевизначимо)
CMD ["python", "bot.py"]