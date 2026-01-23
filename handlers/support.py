import os
from aiogram import Router, F, Bot
from aiogram.types import Message, ReactionTypeEmoji
from aiogram.fsm.context import FSMContext
from states import Support, Registration, Learning
from keyboards import main_menu_keyboard
from asgiref.sync import sync_to_async
from services.utils import get_text
from config import ADMIN_ID
from aiogram.filters import StateFilter, Command
from core.models import AccessCode, BotUser, BotSettings

router = Router()

async def get_setting(key: str):
    try:
        setting = await sync_to_async(BotSettings.objects.get)(key=key)
        return setting.value
    except BotSettings.DoesNotExist:
        return None

async def set_setting(key: str, value: str):
    await sync_to_async(BotSettings.objects.update_or_create)(
        key=key,
        defaults={'value': value}
    )

# COMMAND FOR ASSIGNING A GROUP (For admins only) 
@router.message(Command("setgroup"))
async def cmd_set_group(message: Message, bot: Bot):    
    # Verification: only the main administrator can press the command
    if message.from_user.id != int(ADMIN_ID):
        return

    # Verification: the command must be written IN THE GROUP, not in a private message.
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эту команду нужно писать в чате группы, которую вы хотите сделать техподдержкой.")
        return

    # Save the ID of this group
    group_id = str(message.chat.id)
    await set_setting("support_group_id", group_id)    
    await message.answer(f"✅ <b>Группа поддержки установлена!</b>\nID: <code>{group_id}</code>\nТеперь сообщения от учеников будут приходить сюда.")

# # User clicked the "Написати в підтримку"  button 
@router.message(F.text.in_({"🆘 Написать в поддержку", "/support"}), StateFilter('*'))
async def cmd_support(message: Message, state: FSMContext):
    text = await get_text("support_start_text", default="Напиши свой вопрос или сообщение одним текстом, и я передам его куратору. 👇")
    await message.answer(text, reply_markup=None)
    await state.set_state(Support.waiting_for_message)


# User wrote text (we are in waiting_for_message state) 
@router.message(Support.waiting_for_message)
async def process_support_message(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return

    support_group_id = await get_setting("support_group_id")

    if not support_group_id:
        await message.answer("😔 На данный момент поддержка не настроена. Попробуйте позже.")
        await state.clear()
        return
    
    chat_id_to_send = int(support_group_id)

    admin_text = (
        f"📩 <b>Новый вопрос от ученика!</b>\n"
        f"От: {message.from_user.full_name}\n"
        f"ID: <code>{message.from_user.id}</code>\n" 
        f"👇👇👇\n\n"
        f"{message.text}"
    )
    text = await get_text("question_send", default="✅ Ваше сообщение отправлено! Отвечу, как только смогу.")

    try:
        await bot.send_message(chat_id=chat_id_to_send, text=admin_text)
        await message.answer(text, reply_markup=main_menu_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка отправки (возможно бот не админ в группе): {e}", reply_markup=main_menu_keyboard())
    
    user = BotUser.objects.filter(telegram_id=message.from_user.id).first()
    
    # If the user is not in the database, it means they TRIED to enter the access code.
    # Return them to this mode!
    if not user:
        await state.set_state(Registration.waiting_for_access_code)
        await message.answer("🔄 <b>Теперь можешь снова попробовать ввести код доступа:</b>")
        return
    
    has_activated_code = await sync_to_async(
        lambda: AccessCode.objects.filter(activated_by=user).exists()
    )()
    
    # If the user exists, check whether they are taking the course
    if user.current_course:
        # If you are taking a course, switch to learning mode.
        await state.set_state(Learning.in_process)
    elif has_activated_code and not user.course_start_date:
        # If it is in the database but has not yet started the course (waiting for the code word to be entered)
        await state.set_state(Learning.waiting_for_keyword)
        text = await get_text("wait_code_text", default="🔄 Жду кодовое слово из видео.")
        await message.answer(text)
    else:
        # In other cases, we simply reset
        await state.set_state(Registration.waiting_for_access_code)
        text = await get_text("wait_keyword_text", default="🔄 Введите код доступа, чтобы продолжить:")
        await message.answer(text)

# Admin replies
# This handler will work when ADMIN replies to a message that starts with “📩”
@router.message(F.reply_to_message)
async def process_admin_reply(message: Message, bot: Bot):
    support_group_id = await get_setting("support_group_id")
    if not support_group_id:
        return
    
    if str(message.chat.id) != str(support_group_id):
        return

    replied_text = message.reply_to_message.text or ""
    if "Новый вопрос от ученика!" not in replied_text:
        return 

    try:
        lines = replied_text.split('\n')
        user_id_line = next((line for line in lines if "ID: " in line), None)
        
        if not user_id_line:
            await message.answer("❌ Не могу найти ID пользователя в сообщении.")
            return

        user_id_str = user_id_line.replace("ID: ", "").strip()
        user_id = int(user_id_str)

        answer_text = get_text("curator_answer_text", default="👩‍🏫 <b>Ответ от куратора:</b>")

        await bot.send_message(
            chat_id=user_id,
            text=f"{answer_text}\n\n{message.text}"
        )
        # await message.answer("✅ Ответ отправлен.")
        await message.react([ReactionTypeEmoji(emoji="👍")])

    except Exception as e:
        await message.answer(f"❌ Не удалось доставить ответ: {e}")