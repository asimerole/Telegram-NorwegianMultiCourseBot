import os
from aiogram import Router, F, Bot
from aiogram.types import Message, ReactionTypeEmoji
from aiogram.fsm.context import FSMContext
from states import Support, Registration, Learning
from keyboards import main_menu_keyboard
from asgiref.sync import sync_to_async
from config import ADMIN_ID
from aiogram.filters import StateFilter, Command
from core.models import BotUser, BotSettings

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

#--- 0. КОМАНДА ДЛЯ НАЗНАЧЕНИЯ ГРУППЫ (Только для админа) ---
@router.message(Command("setgroup"))
async def cmd_set_group(message: Message, bot: Bot):    
    # 1. Проверка: команду может нажать только главный админ
    if message.from_user.id != int(ADMIN_ID):
        return

    # 2. Проверка: команда должна быть написана В ГРУППЕ, а не в личке
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эту команду нужно писать в чате группы, которую вы хотите сделать техподдержкой.")
        return

    # 3. Сохраняем ID этой группы
    group_id = str(message.chat.id)
    await set_setting("support_group_id", group_id)    
    await message.answer(f"✅ <b>Группа поддержки установлена!</b>\nID: <code>{group_id}</code>\nТеперь сообщения от учеников будут приходить сюда.")

# --- 1. Юзер натиснув кнопку "Написати в підтримку" ---
@router.message(F.text.in_({"🆘 Написать в поддержку", "/support"}), StateFilter('*'))
async def cmd_support(message: Message, state: FSMContext):
    await message.answer(
        "Напиши свой вопрос или сообщение одним текстом, и я передам его куратору. 👇",
        reply_markup=None 
    )
    await state.set_state(Support.waiting_for_message)


# --- 2. Юзер написав текст (ми в стані waiting_for_message) ---
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

    try:
        await bot.send_message(chat_id=chat_id_to_send, text=admin_text)
        await message.answer("✅ Ваше сообщение отправлено! Отвечу, как только смогу.", reply_markup=main_menu_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка отправки (возможно бот не админ в группе): {e}", reply_markup=main_menu_keyboard())
    
    user = BotUser.objects.filter(telegram_id=message.from_user.id).first()
    print(user)
    if not user:
        # Если юзера нет в базе, значит он ПЫТАЛСЯ ввести код доступа
        # Возвращаем его в этот режим!
        await state.set_state(Registration.waiting_for_access_code)
        await message.answer("🔄 <b>Теперь можешь снова попробовать ввести код доступа:</b>")
    
    else:
        # Если юзер есть, проверяем, проходит ли он курс
        if user.current_course:
            # Если на курсе - переводим в режим обучения
            await state.set_state(Learning.in_process)
        elif not user.course_start_date:
            # Если есть в базе, но еще не начал курс (ждет ввода кодового слова)
            await state.set_state(Learning.waiting_for_keyword)
            await message.answer("🔄 Жду кодовое слово из видео.")
        else:
            # В других случаях просто сбрасываем
            await state.clear()
    # Повертаємось в звичайний режим (але стан Learning.in_process ми тут не ставимо, 
    # бо юзер може бути і не на курсі. state.clear() просто зніме стан сапорту)

# --- 3. Адмін відповідає (Reply) ---
# Цей хендлер спрацює, коли АДМІН робить Reply на повідомлення, яке починається з "📩"
@router.message(F.reply_to_message)
async def process_admin_reply(message: Message, bot: Bot):
    support_group_id = await get_setting("support_group_id")
    if not support_group_id:
        return
    
    if str(message.chat.id) != str(support_group_id):
        return

    # Перевіряємо, чи це відповідь на тікет (шукаємо ключові слова)
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

        await bot.send_message(
            chat_id=user_id,
            text=f"👩‍🏫 <b>Ответ от куратора:</b>\n\n{message.text}"
        )
        # await message.answer("✅ Ответ отправлен.")
        await message.react([ReactionTypeEmoji(emoji="👍")])

    except Exception as e:
        await message.answer(f"❌ Не удалось доставить ответ: {e}")