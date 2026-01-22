import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Telegram admin user id
ADMIN_ID = int(os.getenv("ADMIN_ID"))