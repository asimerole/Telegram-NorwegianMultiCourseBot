import asyncio
import logging
import schedule
import time
from datetime import datetime
from asgiref.sync import sync_to_async
from services.sender import send_lesson

from aiogram import Bot
from django.utils import timezone
from django.db.models import F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# Імпортуємо наші оновлені моделі
from core.models import Lesson, Enrollment, UserProgress

logger = logging.getLogger(__name__)

async def check_and_send_lessons(bot: Bot):
    """
    Головна функція розсилки.
    Запускається кожну хвилину.
    """
    # 1. Отримуємо поточний час сервера
    now = timezone.now()
    # Нам потрібні тільки години та хвилини
    current_hour = now.hour
    current_minute = now.minute
    
    # Лог для перевірки (можна закоментувати, якщо смітить в консоль)
    # logger.info(f"⏰ Tick: {current_hour}:{current_minute}")

    # 2. Шукаємо УРОКИ, які заплановані на ЦЮ хвилину
    # select_related('course') оптимізує запит, щоб не смикати базу зайвий раз
    lessons_to_send = await sync_to_async(list)(
        Lesson.objects.filter(
            send_time__hour=current_hour, 
            send_time__minute=current_minute
        ).select_related('course')
    )

    if not lessons_to_send:
        return

    logger.info(f"Found {len(lessons_to_send)} lessons scheduled for {current_hour}:{current_minute}")

    # 3. Обробляємо кожен знайдений урок
    for lesson in lessons_to_send:
        # Для кожного уроку треба знайти людей, яким він потрібен.
        # Критерії:
        # - Активна підписка (Enrollment) на ЦЕЙ курс
        # - Поточний день підписки (current_day) == дню уроку (day_number)
        
        target_enrollments = await sync_to_async(list)(
            Enrollment.objects.filter(
                course=lesson.course,
                is_active=True,
                current_day=lesson.day_number
            ).select_related('user')
        )

        if not target_enrollments:
            continue

        logger.info(f"Lesson '{lesson}' (Day {lesson.day_number}) needs to be sent to {len(target_enrollments)} users.")

        # 4. Відправляємо
        for enrollment in target_enrollments:
            user = enrollment.user
            
            # Перевірка на дублікат: чи не відправляли ми вже цей урок цьому юзеру?
            already_sent = await sync_to_async(
                UserProgress.objects.filter(user=user, lesson=lesson).exists
            )()
            
            if already_sent:
                continue

            # 🔥 ВІДПРАВКА
            try:
                await send_lesson(bot, user.telegram_id, lesson.id)
                
                # Записуємо в історію, що відправили
                await sync_to_async(UserProgress.objects.create)(user=user, lesson=lesson)
                
                logger.info(f"✅ Sent lesson {lesson.id} to user {user.telegram_id}")
                
            except Exception as e:
                logger.error(f"❌ Failed to send to {user.telegram_id}: {e}")
                # Якщо юзер заблокував бота — можна деактивувати підписку (опціонально)
                # enrollment.is_active = False
                # await sync_to_async(enrollment.save)()



async def update_days():
    """
    Запускається раз на добу (вночі).
    Переводить всі активні підписки на наступний день.
    """
    logger.info("🌙 Nightly update: Increasing days...")
    
    # Використовуємо F-об'єкт для атомарного оновлення (швидко і безпечно)
    await sync_to_async(lambda: Enrollment.objects.filter(is_active=True).update(current_day=F('current_day') + 1))()
    
    logger.info("✅ All active enrollments moved to the next day.")


async def scheduler_loop(bot: Bot):
    """
    Вічний цикл планувальника.
    """
    # 1. Перевірка уроків — кожну хвилину
    schedule.every(1).minutes.do(lambda: asyncio.create_task(check_and_send_lessons(bot)))
    
    # 2. Оновлення днів — кожного дня о 00:01
    schedule.every().day.at("00:01").do(lambda: asyncio.create_task(update_days()))

    logger.info("🚀 Scheduler started!")

    while True:
        schedule.run_pending()
        await asyncio.sleep(1)