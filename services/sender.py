import os
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from asgiref.sync import sync_to_async
from django.db.models import F
from core.models import Lesson, UserProgress, BotUser
from aiogram.fsm.context import FSMContext
from states import Learning
from services.utils import get_next_available_lesson, finish_course


def get_next_btn(lesson_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="Далее ➡️", callback_data=f"next_lesson:{lesson_id}")
    return builder.as_markup()

async def trigger_next_lesson(bot: Bot, user_id: int, state: FSMContext = None):
    # Зверни увагу: ми прибрали аргументи current_day і current_time_slot, вони більше не потрібні
    
    user = await sync_to_async(BotUser.objects.get)(telegram_id=user_id)
    
    # 1. Шукаємо наступний доступний урок
    next_lesson = await get_next_available_lesson(user)

    # 2. Якщо урок є і час настав
    if next_lesson:
        need_next_btn = (next_lesson.lesson_type == 'theory')

        if next_lesson.lesson_type == 'text_input' and state:
            await state.set_state(Learning.waiting_for_text_answer)
            # ВАЖЛИВО: Використовуємо update_data, зберігаємо в Redis
            await state.update_data(lesson_id=next_lesson.id)
        
        # Відправляємо
        await send_lesson(bot, user_id, next_lesson.id, add_next_btn=need_next_btn)
        
        # ЗАПИСУЄМО ПРОГРЕС ВІДРАЗУ
        # (Бо trigger викликається після дії користувача, тут це безпечно)
        if next_lesson.lesson_type == 'theory':
            await sync_to_async(UserProgress.objects.create)(user=user, lesson=next_lesson) 
            
        return

    # 3. Якщо уроку немає (або курс закінчено, або треба чекати наступного слоту)
    
    # Перевіримо, чи це фініш курсу (чи взагалі залишились непройдені уроки?)
    # Логіка проста: якщо get_next_available_lesson повернув None, це або "чекай", або "кінець".
    
    has_more_lessons = await sync_to_async(Lesson.objects.filter(
        course=user.current_course
    ).exclude(
        id__in=UserProgress.objects.filter(user=user).values('lesson_id')
    ).exists)()

    if not has_more_lessons:
        # Уроків взагалі немає -> Фініш
        await finish_course(bot, user, state=state)
    else:
        # Уроки є, але ще не настав час
        # Можна написати гарне повідомлення
        await bot.send_message(
            user_id, 
            f"🏁 <b>На данный момент заданий больше нет!</b>\nОтдыхай. Скоро придет новое."
        )

async def send_lesson(bot: Bot, chat_id: int, lesson_id: int, add_next_btn: bool = False):
    try:
        lesson = await sync_to_async(Lesson.objects.get)(id=lesson_id)
    except Lesson.DoesNotExist:
        print(f"❌ Помилка: Урок {lesson_id} не знайдено.")
        return False

    # 1. Відправка МЕДІА
    try:
        if lesson.image:
            await bot.send_photo(chat_id, FSInputFile(lesson.image.path))
        if lesson.audio:
            await bot.send_audio(chat_id, FSInputFile(lesson.audio.path))
        if lesson.video_note:
            await bot.send_video_note(chat_id, FSInputFile(lesson.video_note.path))
        if lesson.file_doc:
            await bot.send_document(chat_id, FSInputFile(lesson.file_doc.path))
    except Exception as e:
        print(f"⚠️ Ошибка медиа: {e}")

    # 2. Формуємо КЛАВІАТУРУ
    keyboard = None
    
    # ВАРИАНТ А: Это КВИЗ (тест)
    if lesson.lesson_type == 'quiz' and lesson.quiz_options:
        options = lesson.quiz_options.splitlines() # Лучше использовать splitlines()
        buttons = []
        for opt in options:
            opt = opt.strip()
            if not opt: continue
            # Обрезаем длинный текст для callback_data
            short_opt = opt[:20]
            cb_data = f"ans:{lesson.id}:{short_opt}" 
            buttons.append([InlineKeyboardButton(text=opt, callback_data=cb_data)])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # ВАРИАНТ Б: Это ТЕОРИЯ и нас попросили кнопку "Далее"
    elif add_next_btn:
        keyboard = get_next_btn(lesson.id)

    # 3. Відправка ТЕКСТУ
    text_to_send = lesson.text or "Задание:"
    
    if lesson.lesson_type == 'text_input':
        text_to_send += "\n\n✍️ <b>Напиши ответ в сообщении ниже:</b>"

    try:
        await bot.send_message(chat_id, text_to_send, reply_markup=keyboard)
        return True
    except Exception as e:
        print(f"❌ Не удалось отправить сообщение: {e}")
        return False
    
