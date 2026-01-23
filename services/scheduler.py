import asyncio
import logging
import schedule
import time
from datetime import datetime
from asgiref.sync import sync_to_async
from services.sender import send_lesson_block

from aiogram import Bot
from django.utils import timezone
from django.db.models import F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.models import Lesson, Enrollment, UserProgress

logger = logging.getLogger(__name__)

async def check_and_send_lessons(bot):
    now = timezone.localtime(timezone.now())
    
    # We get a list of courses that have ANY lessons available at this moment.
    active_course_ids = await sync_to_async(list)(
        Lesson.objects.filter(
            send_time__hour=now.hour,
            send_time__minute=now.minute
        ).values_list('course_id', flat=True).distinct()
    )

    if not active_course_ids:
        return

    # We only accept active subscriptions that are relevant to these courses.
    active_enrollments = await sync_to_async(list)(
        Enrollment.objects.filter(
            is_active=True,
            course_id__in=active_course_ids
        ).select_related('user', 'course')
    )

    if not active_enrollments:
        return

    for enrollment in active_enrollments:
        
        # --- MATH OF DAYS ---
        # Calculate the difference between “Now” and “Start Date”
        delta = now.date() - enrollment.start_date.date()
        
        # If “Start tomorrow”, then:
        # Rega 19.01. Now it is 19.01. delta = 0. day_number = 0 (Silence).
        # Now it is 20.01. delta = 1. day_number = 1 (First lesson).
        day_number = delta.days 
        day_number = 1 # for test, default is day_number = delta.days
        if day_number <= 0:
            continue 

        # Seeking lessons for this Day and Time
        lessons = await sync_to_async(list)(
            Lesson.objects.filter(
                course=enrollment.course,
                day_number=day_number,
                send_time__hour=now.hour,
                send_time__minute=now.minute
            )
        )

        if not lessons:
            continue

        # Check if it has already been sent (Duplicate protection)
        # Check according to the first lesson in the pack
        already_sent = await sync_to_async(
            UserProgress.objects.filter(user=enrollment.user, lesson=lessons[0]).exists
        )()
        
        if already_sent:
            continue

        try:
            await send_lesson_block(bot, enrollment.user, enrollment.course, lessons)
            
            for lesson in lessons:
                 await sync_to_async(UserProgress.objects.create)(user=enrollment.user, lesson=lesson)
                 
        except Exception as e:
            print(f"❌ Error sending block to {enrollment.user}: {e}")




async def scheduler_loop(bot: Bot):
    """
    Вічний цикл планувальника.
    """
    # 1. Перевірка уроків — кожну хвилину
    schedule.every(1).minutes.do(lambda: asyncio.create_task(check_and_send_lessons(bot)))

    logger.info("🚀 Scheduler started!")

    while True:
        schedule.run_pending()
        await asyncio.sleep(1)