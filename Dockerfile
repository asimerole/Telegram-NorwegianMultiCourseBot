# We use lightweight Python 3.11
FROM python:3.11-slim

# We prohibit Python from creating .pyc files and force it to output logs immediately.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Working folder inside the container
WORKDIR /app

# Install system libraries (required for psycopg2 and Pillow)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the file with dependencies
COPY requirements.txt .

# Installing Python libraries
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project code inside
COPY . .

# This port will be open for Admin
EXPOSE 8000

# By default, we launch the bot (but we will override this in compose)
CMD ["python", "bot.py"]