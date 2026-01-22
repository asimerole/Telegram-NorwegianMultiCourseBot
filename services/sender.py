import os
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from asgiref.sync import sync_to_async
from django.db.models import F
from core.models import Lesson, UserProgress, BotUser
from aiogram.fsm.context import FSMContext
from states import Learning
from services.utils import finish_course


def get_answer_btn(lesson_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Написать ответ", callback_data=f"reply_task:{lesson_id}")    
    return builder.as_markup()

async def send_lesson(bot: Bot, chat_id: int, lesson_id: int):
    try:
        lesson = await sync_to_async(Lesson.objects.get)(id=lesson_id)
    except Lesson.DoesNotExist:
        print(f"❌ Помилка: Урок {lesson_id} не знайдено.")
        return False

    # Media dispatch
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

    # Forming the KEYBOARD
    keyboard = None
    
    # OPTION A: This is a QUIZ (test)
    if lesson.lesson_type == 'quiz' and lesson.quiz_options:
        options = lesson.quiz_options.splitlines() 
        buttons = []
        for opt in options:
            opt = opt.strip()
            if not opt: continue
            short_opt = opt[:20]
            cb_data = f"ans:{lesson.id}:{short_opt}" 
            buttons.append([InlineKeyboardButton(text=opt, callback_data=cb_data)])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # OPTION B: This is THEORY, click the “Next” button.
    if lesson.lesson_type == 'text_input':
        keyboard = get_answer_btn(lesson.id)

    # Sending TEXT
    text_to_send = lesson.text
    if not text_to_send:
        # Якщо тексту в уроці немає, але є завдання - пишемо заглушку
        if lesson.lesson_type == 'text_input':
            text_to_send += "\n\n✍️ <b>Напиши ответ в сообщении ниже:</b>"
        elif lesson.lesson_type == 'quiz':
            text_to_send = "Тест:"
        else:
            text_to_send = "Материал урока:"
       
    try:
        await bot.send_message(chat_id, text_to_send, reply_markup=keyboard)
        return True
    except Exception as e:
        print(f"❌ Не удалось отправить сообщение: {e}")
        return False
    
