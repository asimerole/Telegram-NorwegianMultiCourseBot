# handlers/common.py
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from core.models import BotUser, Lesson
from services.utils import get_text
from states import Registration, Learning
from services.sender import send_lesson
from keyboards import main_menu_keyboard

router = Router()

# OLD
# @router.message(Command("start")) 
# async def cmd_start(message: Message, state: FSMContext):
#     # Перевірка юзера
#     user_exists = BotUser.objects.filter(telegram_id=message.from_user.id).exists()
    
#     if user_exists:
#         await message.answer("Ты уже с нами!")
#     else:
#         await message.answer("Привет! Введи кодовое доступа.", reply_markup=main_menu_keyboard())
#         await state.set_state(Registration.waiting_for_access_code)

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # 'welcome_text' — это slug, который ты должен создать в админке
    text = await get_text("welcome_text", default="Привет! (текст настраивается в админке). \n\nКлюч приветствия: <b>welcome_text</b>")
    # Перевірка юзера
    user_exists = BotUser.objects.filter(telegram_id=message.from_user.id).exists()
    
    if user_exists:
        await message.answer("Ты уже с нами!")
    else:
        await message.answer(text, reply_markup=main_menu_keyboard())
        await state.set_state(Registration.waiting_for_access_code)

@router.message(Command("test"))
async def cmd_test_lesson(message: Message, command: CommandObject, bot, state: FSMContext): 
    """
    Команда для тестування: /test <ID_УРОКУ>
    Наприклад: /test 1
    """
    # Перевірка: чи передав ти аргумент
    if command.args is None:
        await message.answer("Помилка: вкажи ID уроку. Наприклад: <code>/test 1</code>")
        return

    try:
        lesson_id = int(command.args)
    
        # 1. Отправляем урок
        success = await send_lesson(bot, message.chat.id, lesson_id)
        
        if success:
            # 2. Если это вопрос с ручным вводом - включаем режим ожидания
            # Нам нужно достать урок, чтобы проверить его тип
            # (Да, это второй запрос в БД, но это надежно)
            lesson = Lesson.objects.get(id=lesson_id)
            
            if lesson.lesson_type == 'text_input':
                await state.set_state(Learning.waiting_for_text_answer)
                # Запоминаем ID урока, чтобы потом проверить ответ именно на него
                await state.update_data(current_lesson_id=lesson.id)
                
                await message.answer("ℹ️ <i>Бот ждет твой ответ текстом...</i>")
    except ValueError:
        await message.answer("ID має бути числом.")
        return