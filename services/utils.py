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

# Кэшируем тексты, чтобы не долбить базу при каждом сообщении
# (В продакшене лучше использовать Redis, но пока хватит и словаря)
MESSAGES_CACHE = {}

@sync_to_async
def get_text(slug: str, default: str = None) -> str:
    """
    Получает текст из базы по слагу.
    Если текста нет в базе — возвращает default или сам slug.
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
    Шукає наступний урок, який юзер ще НЕ отримав, 
    АЛЕ перевіряє, чи настав час для цього уроку.
    """
    if not user.current_course or not user.course_start_date:
        return None

    # 1. Знаходимо ID всіх пройдених уроків
    # (Використовуємо sync_to_async, бо Django ORM синхронний)
    completed_lessons_ids = await sync_to_async(list)(
        UserProgress.objects.filter(user=user).values_list('lesson_id', flat=True)
    )

    # 2. Шукаємо ПЕРШИЙ урок поточного курсу, якого немає в completed_lessons_ids
    # Сортуємо по дню, часу і ID, щоб йти строго по порядку
    next_lesson = await sync_to_async(lambda: Lesson.objects.filter(
        course=user.current_course
    ).exclude(
        id__in=completed_lessons_ids
    ).order_by('day_number', 'time_slot', 'id').first())()

    if not next_lesson:
        return None  # Уроків більше немає, курс пройдено

    # 3. ПЕРЕВІРКА ЧАСУ (Time Gate)
    # Коли цей урок має відкритися теоретично?
    # Формула: Дата_Старту + (День_Уроку - 1) + Година_Уроку
    
    start_local = timezone.localtime(user.course_start_date)
    
    # Скільки днів треба додати до старту. 
    # Якщо урок в День 1, то додаємо 0 днів. День 2 -> +1 день.
    days_offset = next_lesson.day_number
    
    # Створюємо дату відкриття уроку
    unlock_time = start_local + timedelta(days=days_offset)
    # Замінюємо годину на слот уроку (хвилини 0, секунди 0)
    unlock_time = unlock_time.replace(hour=next_lesson.time_slot, minute=0, second=0, microsecond=0)

    now = timezone.localtime(timezone.now())

    # Якщо поточний час МЕНШИЙ за час відкриття — урок ще недоступний
    if now < unlock_time:
        return None

    return next_lesson

async def finish_course(bot: Bot, user: BotUser, dp: Dispatcher = None, state: FSMContext = None):
    """
    Універсальна функція завершення.
    Приймає:
    - dp: якщо викликаємо з Планувальника (background task).
    - state: якщо викликаємо з Хендлера (user interaction).
    """
    # 1. Повідомлення
    msg_text = user.current_course.finish_message or "Час вийшов! Курс завершено."
    try:
        await bot.send_message(user.telegram_id, msg_text)
    except Exception:
        pass
    
    # 2. Очищення БД
    user.current_course = None
    user.course_start_date = None
    await sync_to_async(user.save)()

    # 3. РОБОТА ЗІ СТЕЙТОМ (FSM)
    # Сценарій А: У нас вже є state (виклик з trigger_next_lesson)
    if state:
        await state.set_state(Learning.waiting_for_keyword)
        await state.set_data({}) # Чистимо сміття
    
    # Сценарій Б: У нас немає state, але є dp (виклик з check_and_send_lessons)
    elif dp:
        state_key = StorageKey(
            bot_id=bot.id,
            chat_id=user.telegram_id,
            user_id=user.telegram_id
        )
        # Створюємо контекст вручну через dp.storage
        ctx = FSMContext(storage=dp.storage, key=state_key)
        await ctx.set_state(Learning.waiting_for_keyword)
        await ctx.set_data({})