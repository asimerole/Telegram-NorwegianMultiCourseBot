from aiogram import Bot
from aiogram import Dispatcher
from django.utils import timezone
from asgiref.sync import sync_to_async
from core.models import BotUser, Lesson, UserProgress
from services.sender import send_lesson
from datetime import timedelta
from services.utils import get_next_available_lesson, finish_course

async def check_and_send_lessons(bot: Bot, dp: Dispatcher):
    now_local = timezone.localtime(timezone.now())
    
    # Отримуємо активних юзерів
    active_users = await sync_to_async(list)(
        BotUser.objects.exclude(current_course__isnull=True).exclude(course_start_date__isnull=True)
    )

    for user in active_users:
        # --- 1. Hard Deadline Check (Чи не прострочив курс) ---
        course_duration = user.current_course.duration_days
        # Даємо буфер +1 день, щоб довчити
        deadline = user.course_start_date + timedelta(days=course_duration + 1)
        
        if now_local > deadline:
            await finish_course(bot, user, dp)
            continue

        last_progress = await sync_to_async(lambda: UserProgress.objects.filter(
            user=user
        ).order_by('-sent_at').first())()

        if last_progress:
            # Якщо юзер щось проходив менше ніж 5 хвилин тому — не чіпаємо його.
            # Хай працює механізм кнопок (trigger_next_lesson).
            time_since_last = now_local - timezone.localtime(last_progress.sent_at)
            if time_since_last.total_seconds() < 300: 
                continue

        # --- 2. Шукаємо наступний урок ---
        next_lesson = await get_next_available_lesson(user)
        
        if not next_lesson:
            continue # Або уроків немає, або ще рано

        # --- 3. ВАЖЛИВА ЛОГІКА "NETFLIX" ---
        # Планувальник має відправляти урок ТІЛЬКИ якщо це "Стартовий урок блоку".
        # Якщо це 2-ге або 3-тє повідомлення всередині блоку (наприклад, тест після відео),
        # то юзер має отримати його через кнопку "Далі", а не автоматично.
        
        # Перевіряємо: чи цей урок ПЕРШИЙ у своєму слоті?
        # Шукаємо попередній урок за порядком
        prev_lesson = await sync_to_async(lambda: Lesson.objects.filter(
            course=user.current_course,
            day_number=next_lesson.day_number,
            time_slot=next_lesson.time_slot,
            id__lt=next_lesson.id # ID менше поточного
        ).exists())()

        # Якщо prev_lesson = True, значить наш урок НЕ перший у блоці. 
        # Значить, чекаємо, поки юзер натисне кнопку на попередньому. Планувальник мовчить.
        if prev_lesson:
            continue

        # Якщо ми тут — значить це перший урок нового блоку (або нового дня), і час настав.
        # Відправляємо!
        
        need_next_btn = (next_lesson.lesson_type == 'theory')
        success = await send_lesson(bot, user.telegram_id, next_lesson.id, add_next_btn=need_next_btn)
        
        if success:
            await sync_to_async(UserProgress.objects.create)(user=user, lesson=next_lesson)