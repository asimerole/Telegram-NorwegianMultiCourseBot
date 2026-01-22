from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from django.utils import timezone

from core.models import AccessCode, BotUser, Enrollment, Lesson, UserProgress
from states import Registration
from keyboards import main_menu_keyboard

router = Router()

@router.message(Registration.waiting_for_access_code)
async def process_code(message: Message, state: FSMContext):
    code_text = message.text.strip()
    user_id = message.from_user.id

    user = await sync_to_async(BotUser.objects.get)(telegram_id=user_id)

    access_code = await sync_to_async(
        lambda: AccessCode.objects.select_related('activated_by').prefetch_related('courses').filter(code=code_text).first()
    )()

    if not access_code:
        await message.answer("❌ Такой код не найден. Попробуй еще раз.")
        return

    if not access_code.is_active:
        await message.answer("⛔ Этот код уже неактивен.")
        return
    
    if access_code.activated_by:
        if access_code.activated_by.telegram_id != user_id:
            await message.answer("⛔ Ошибка! Этот код уже активирован другим человеком.")
            return
        else:
            await message.answer("⚠️ Ты уже активировал этот код ранее.")
            await state.clear()
            return
    else:
        access_code.activated_by = user
        await sync_to_async(access_code.save)()

    
    courses = await sync_to_async(list)(access_code.courses.all())

    if not courses:
        await message.answer("⚠️ К этому коду не привязано ни одного курса. Напиши администратору.")
        return

    courses_ids = [c.id for c in courses]
    
    already_enrolled = await sync_to_async(
        lambda: Enrollment.objects.filter(
            user=user, 
            course_id__in=courses_ids, 
            is_active=True
        ).exists()
    )()

    if already_enrolled:
        await message.answer(
            "⚠️ <b>У тебя уже есть доступ к этим курсам!</b>\n"
            "Повторная активация не требуется.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return

    access_code.activated_by = user
    await sync_to_async(access_code.save)()

    activated_courses_titles = []

    for course in courses:
        enrollment, created = await sync_to_async(Enrollment.objects.get_or_create)(
            user=user,
            course=course,
            defaults={'current_day': 1, 'is_active': True}
        )
        
        if not created and not enrollment.is_active:
            enrollment.is_active = True
            enrollment.current_day = 1
            enrollment.start_date = timezone.now()
            await sync_to_async(enrollment.save)()

        activated_courses_titles.append(course.title)
        
        if course.start_message:
             await message.answer(course.start_message, parse_mode="HTML")

    courses_str = "\n🔹 ".join(activated_courses_titles)
    
    await message.answer(
        f"✅ <b>Код принят!</b>\n\n"
        f"Тебе открыт доступ к курсам:\n🔹 {courses_str}\n\n"
        f"Жди первые уроки по расписанию!",
        reply_markup=main_menu_keyboard()
    )

    await state.clear()