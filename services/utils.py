from asgiref.sync import sync_to_async
from core.models import BotMessage, BotUser, Lesson, UserProgress
from aiogram import Bot
import re 
from datetime import timedelta
from django.utils import timezone
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.context import FSMContext
from aiogram import Dispatcher

from states import Learning

@sync_to_async
def get_text(slug: str, default: str = None) -> str:
    """
    Retrieves text from the database based on the slug.
    If the text is not in the database, returns default or the slug itself.
    """
    try:
        msg = BotMessage.objects.get(slug=slug)
        return msg.text
    except BotMessage.DoesNotExist:
        return default if default else f"[Текст не задан: {slug}]"
    
def normalize_text(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.split()

async def get_next_available_lesson(user: BotUser) -> Lesson | None:
    """
    Searches for the next lesson that the user has NOT yet received, 
    BUT checks whether it is time for that lesson.
    """
    if not user.current_course or not user.course_start_date:
        return None

    # Find the IDs of all completed lessons
    completed_lessons_ids = await sync_to_async(list)(
        UserProgress.objects.filter(user=user).values_list('lesson_id', flat=True)
    )

    # Search for the FIRST lesson of the current course that is not in completed_lessons_ids
    # Sort by day, time, and ID to go strictly in order
    next_lesson = await sync_to_async(lambda: Lesson.objects.filter(
        course=user.current_course
    ).exclude(
        id__in=completed_lessons_ids
    ).order_by('day_number', 'time_slot', 'id').first())()

    if not next_lesson:
        return None  # No more lessons, course completed

    # TIME CHECK (Time Gate)
    # When should this lesson theoretically open?
    # Formula: Start_Date + (Lesson_Day - 1) + Lesson_Time
    start_local = timezone.localtime(user.course_start_date)
    
    # How many days to add to the start date. 
    # If the lesson is on Day 1, add 0 days. Day 2 -> +1 day.
    days_offset = next_lesson.day_number 
    
    # Setting the date for the start of the lesson
    unlock_time = start_local + timedelta(days=days_offset)
    # Replace the hour with the lesson slot (minutes 0, seconds 0)
    unlock_time = unlock_time.replace(hour=next_lesson.time_slot, minute=0, second=0, microsecond=0)

    now = timezone.localtime(timezone.now())

    # If the current time is LESS than the opening time, the lesson is not yet available.
    if now < unlock_time:
        return None

    return next_lesson

async def finish_course(bot: Bot, user: BotUser, dp: Dispatcher = None, state: FSMContext = None):
    """
    Universal completion function.
    Accepts:
    - dp: if called from the Scheduler (background task).
    - state: if called from the Handler (user interaction).
    """
    # Message
    msg_text = user.current_course.finish_message or "Час вийшов! Курс завершено."
    try:
        await bot.send_message(user.telegram_id, msg_text)
    except Exception:
        pass
    
    # Database cleanup
    user.current_course = None
    user.course_start_date = None
    await sync_to_async(user.save)()

    # WORKING WITH STATES (FSM)
    # Scenario A: We already have a state (call from trigger_next_lesson)
    if state:
        await state.set_state(Learning.waiting_for_keyword)
        await state.set_data({}) # Чистимо сміття
    
    # We don't have state, but we have dp (call from check_and_send_lessons)
    elif dp:
        state_key = StorageKey(
            bot_id=bot.id,
            chat_id=user.telegram_id,
            user_id=user.telegram_id
        )
        # Creating context manually via dp.storage
        ctx = FSMContext(storage=dp.storage, key=state_key)
        await ctx.set_state(Learning.waiting_for_keyword)
        await ctx.set_data({})