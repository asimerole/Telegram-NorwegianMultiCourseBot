from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from core.models import BotUser
from services.utils import get_text
from states import Registration
from keyboards import main_menu_keyboard

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # 1. Create or obtain a user immediately (so as not to lose it)
    user, created = await sync_to_async(BotUser.objects.get_or_create)(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username,
            'first_name': message.from_user.first_name
        }
    )

    # 2. Receive the greeting text
    text = await get_text("welcome_text", default="Привет! Введи свой код доступа, чтобы начать обучение.")
    
    #3. Always ask for the code, even if the user already exists (in case they have purchased another course).
    await message.answer(text, reply_markup=main_menu_keyboard()) # Можна main_menu, а можна прибрати клавіатуру
    await state.set_state(Registration.waiting_for_access_code)

@router.message(Command("code"))
@router.message(F.text == "🔑 Ввести код доступа")
async def cmd_enter_code(message: Message, state: FSMContext):
    # Скидаємо поточний стан (якщо юзер писав відповідь на урок, ми це перериваємо)
    await state.clear()
    
    await message.answer(
        "🔐 <b>Введите ваш код доступа:</b>\n\n"
        "<i>Это добавит новый курс к вашему текущему обучению.</i>",
        parse_mode="HTML"
    )
    
    # Перемикаємо в режим очікування коду (той самий, що при реєстрації)
    # Він обробиться у файлі handlers/registration.py
    await state.set_state(Registration.waiting_for_access_code)