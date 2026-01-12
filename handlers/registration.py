# handlers/registration.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from core.models import AccessCode, BotUser 
from states import Registration, Learning  
from asgiref.sync import sync_to_async

# Створюємо роутер (це як міні-диспетчер)
router = Router() 

@router.message(Registration.waiting_for_access_code)
async def process_code(message: Message, state: FSMContext):
    code_text = message.text.strip()

    user, created = await sync_to_async(BotUser.objects.get_or_create)(
        telegram_id=message.from_user.id,
        defaults={
            'username': message.from_user.username,
            'first_name': message.from_user.first_name
        }
    )

    access_code = await sync_to_async(
        lambda: AccessCode.objects.select_related('activated_by').filter(code=code_text).first()
    )()

    if not access_code:
        await message.answer("❌ Такой код не найден. Попробуй еще раз.")
        return

    if not access_code.is_active:
        await message.answer("⛔ Этот код уже неактивен.")
        return
    
    # В. ПРОВЕРКА ВЛАДЕЛЬЦА (Самое важное!)
    if access_code.activated_by:
        if access_code.activated_by.telegram_id != message.from_user.id:
            await message.answer("⛔ <b>Ошибка доступа!</b>\nЭтот код уже активирован другим пользователем.")
            return
        else:
            pass 
    else:
        access_code.activated_by = user
        await sync_to_async(access_code.save)()

    await message.answer("✅ <b>Код принят!</b>\n\n"
        "Теперь посмотри видео (если ты еще этого не сделал) и введи <b>кодовое слово</b> из видео."
    )

    await state.set_state(Learning.waiting_for_keyword)