from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async
from django.utils import timezone

# Імпортуємо нові моделі
from core.models import AccessCode, BotUser, Enrollment, Lesson, UserProgress
from states import Registration
from keyboards import main_menu_keyboard

# Імпортуємо функцію відправки (вона у нас в scheduler, але краще винести в окремий файл sender.py)
# Поки що припустимо, що ти скопіюєш send_lesson_content у services/sender.py або імпортуєш з scheduler
# from services.scheduler import send_lesson_content 

router = Router()

@router.message(Registration.waiting_for_access_code)
async def process_code(message: Message, state: FSMContext):
    code_text = message.text.strip()
    user_id = message.from_user.id

    # 1. Знаходимо юзера
    user = await sync_to_async(BotUser.objects.get)(telegram_id=user_id)

    # 2. Шукаємо код в базі
    # prefetch_related('courses') - одразу завантажує курси, щоб не робити 100 запитів
    access_code = await sync_to_async(
        lambda: AccessCode.objects.select_related('activated_by').prefetch_related('courses').filter(code=code_text).first()
    )()

    # --- ПЕРЕВІРКИ ---
    if not access_code:
        await message.answer("❌ Такой код не найден. Попробуй еще раз.")
        return

    if not access_code.is_active:
        await message.answer("⛔ Этот код уже неактивен.")
        return
    
    # Перевірка власника
    if access_code.activated_by:
        if access_code.activated_by.telegram_id != user_id:
            await message.answer("⛔ Ошибка! Этот код уже активирован другим человеком.")
            return
        else:
            # Якщо це той самий юзер - пропускаємо (може він випадково ввів ще раз)
            pass 
    else:
        # Активуємо код на цього юзера
        access_code.activated_by = user
        await sync_to_async(access_code.save)()

    # --- 🔥 ГОЛОВНЕ: ВІДКРИВАЄМО КУРСИ ---
    
    # Отримуємо список курсів, прив'язаних до коду
    courses = await sync_to_async(list)(access_code.courses.all())

    if not courses:
        await message.answer("⚠️ К этому коду не привязано ни одного курса. Напиши администратору.")
        return

    activated_courses_titles = []

    for course in courses:
        # Створюємо підписку (get_or_create, щоб не дублювати, якщо вже є)
        enrollment, created = await sync_to_async(Enrollment.objects.get_or_create)(
            user=user,
            course=course,
            defaults={'current_day': 1, 'is_active': True}
        )
        
        # Якщо підписка була стара і неактивна - активуємо її і скидаємо на 1 день
        if not created and not enrollment.is_active:
            enrollment.is_active = True
            enrollment.current_day = 1
            enrollment.start_date = timezone.now()
            await sync_to_async(enrollment.save)()

        activated_courses_titles.append(course.title)

        # 🚀 (ОПЦІОНАЛЬНО) Одразу надсилаємо перший урок першого дня?
        # Якщо логіка "почекати до призначеного часу", то цей блок не потрібен.
        # Але зазвичай клієнт хоче отримати щось одразу.
        # Тут треба вирішити: чи ми чекаємо часу в уроці, чи вітальний меседж.
        
        if course.start_message:
             await message.answer(course.start_message, parse_mode="HTML")

    # --- ФІНАЛ ---
    
    courses_str = "\n🔹 ".join(activated_courses_titles)
    
    await message.answer(
        f"✅ <b>Код принят!</b>\n\n"
        f"Тебе открыт доступ к курсам:\n🔹 {courses_str}\n\n"
        f"Жди первые уроки по расписанию!",
        reply_markup=main_menu_keyboard()
    )

    # Очищаємо стан, більше нічого вводити не треба
    await state.clear()