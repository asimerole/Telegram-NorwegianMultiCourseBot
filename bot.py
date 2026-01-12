import asyncio
import logging
import os
import sys
from aiogram.fsm.storage.redis import RedisStorage 
from redis.asyncio import Redis

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "coursebot.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()

import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.scheduler import check_and_send_lessons
from config import BOT_TOKEN
from handlers import common, registration, learning, support, faq

async def main():
    # 1. Настройка Redis
    # Если запускаем в Docker, хост будет 'redis'. Если локально - 'localhost'
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis = Redis(host=redis_host, port=6379, db=0)

    ONE_MONTH = 30 * 24 * 60 * 60
    
    # 2. Инициализируем хранилище
    storage = RedisStorage(
    redis=redis,
    state_ttl=ONE_MONTH, 
    data_ttl=ONE_MONTH
)

    dp = Dispatcher(storage=storage)
                    
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    scheduler = AsyncIOScheduler()

    # Добавляем задачу: запускать check_and_send_lessons каждую минуту
    # interval=60 (секунд) - в продакшене
    # interval=10 (секунд) - для ТЕСТА, чтобы не ждать долго
    scheduler.add_job(check_and_send_lessons, 'interval', seconds=10, kwargs={'bot': bot, 'dp': dp})
    
    scheduler.start()

    # --- 3. РЕЄСТРУЄМО РОУТЕРИ ---
    # Порядок важливий! Специфічні хендлери йдуть першими, загальні - останніми.
    dp.include_router(faq.router)
    dp.include_router(support.router)
    dp.include_router(registration.router) 
    dp.include_router(common.router) 
    dp.include_router(learning.router)
    
    print("Бот запущено з модульною структурою...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    # Налаштування логування
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())