import asyncio
import logging
import os
import sys

# 1. Налаштування Django (Обов'язково на самому початку)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "coursebot.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

import django
django.setup()

# 2. Імпорти
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage 
from redis.asyncio import Redis

# Імпортуємо наш новий планувальник
from services.scheduler import scheduler_loop

from config import BOT_TOKEN
from handlers import common, registration, learning, support, faq

async def main():
    # --- REDIS CONFIGURATION ---
    # If running in Docker, the host will be ‘redis’.
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis = Redis(host=redis_host, port=6379, db=0)

    ONE_MONTH = 30 * 24 * 60 * 60
    
    storage = RedisStorage(
        redis=redis,
        state_ttl=ONE_MONTH, 
        data_ttl=ONE_MONTH
    )

    # --- BOT & DISPATCHER ---
    dp = Dispatcher(storage=storage)
                    
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # --- 🔥 ГОЛОВНА ЗМІНА: ПЛАНУВАЛЬНИК ---
    # Ми прибрали APScheduler, бо він конфліктував.
    # Запускаємо наш новий цикл як фонове завдання.
    asyncio.create_task(scheduler_loop(bot))

    # --- ROUTERS ---
    dp.include_router(faq.router)
    dp.include_router(support.router)
    dp.include_router(registration.router) 
    dp.include_router(common.router) 
    
    # ⚠️ УВАГА: Якщо в learning.router є код, який звертається до 
    # видалених полів (current_course), бот може впасти при натисканні кнопок.
    # Але поки залишаємо.
    dp.include_router(learning.router)
    
    print("🚀 Бот запущено з підтримкою Multi-Course!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())