from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from core.models import Course, BotUser, Lesson, UserProgress
from states import Learning
from django.utils import timezone # Для фиксации времени старта
from keyboards import main_menu_keyboard
from services.sender import trigger_next_lesson
from asgiref.sync import sync_to_async
from services.utils import normalize_text

router = Router()

@router.message(Learning.waiting_for_keyword)
async def process_keyword(message: Message, state: FSMContext):
    # 1. Нормализуем текст (убираем пробелы, делаем маленькие буквы)
    keyword_input = message.text.strip()
    
    # 2. Ищем курс в базе (iexact = поиск без учета регистра, Test == test)
    course = Course.objects.filter(keyword__iexact=keyword_input).first()

    if not course:
        await message.answer(
            "🤔 Хм, я не знаю такого кодового слова.\n"
            "Проверь, правильно ли ты его написал, и попробуй еще раз."
        )
        return

    # 3. Достаем пользователя
    user = BotUser.objects.get(telegram_id=message.from_user.id)

    # ПРОВЕРКА: Не проходит ли он уже другой курс?
    # Если у юзера уже есть курс и он не закончен (логику окончания добавим позже)
    if user.current_course and user.current_course != course:
        await message.answer(
            f"⛔ Ты уже проходишь курс «{user.current_course.title}».\n"
            "Закончи его, прежде чем начинать новый!"
        )
        return

    # 4. Активируем курс пользователю
    user.current_course = course
    user.course_start_date = timezone.now()
    user.save()
    
    msg_text = user.current_course.start_message or "Курс начался!"
    await message.answer(msg_text,
            reply_markup=main_menu_keyboard() 
    )

    # 5. Переводим в состояние "В процессе", чтобы он не мог снова вводить слова
    await state.set_state(Learning.in_process)

# --- ЧАСТЬ 1: ОБРАБОТКА КНОПОК (QUIZ) ---
@router.callback_query(F.data.startswith("ans:"))
async def check_quiz_answer(callback: CallbackQuery, bot: Bot):
    # Разбираем callback_data="ans:ID_УРОКА:ОТВЕТ"
    # split(":", 2) означает "раздели только первые 2 двоеточия", остальное - это текст ответа
    try:
        _, lesson_id_str, selected_answer = callback.data.split(":", 2)
        lesson_id = int(lesson_id_str)
    except ValueError:
        await callback.answer("Ошибка данных кнопки.")
        return

    # Достаем урок
    try:
        lesson = Lesson.objects.get(id=lesson_id)
    except Lesson.DoesNotExist:
        await callback.answer("Урок не найден.")
        return

    selected_answer = selected_answer.strip()
    correct_answer = lesson.correct_answer.strip()
    
    is_correct = (selected_answer == correct_answer)

    if is_correct:
        # --- 1. ПРАВИЛЬНЫЙ ОТВЕТ ---
        await callback.answer("✅ Правильно!")
        await callback.message.answer(f"👍 <b>Верно!</b>\n{correct_answer}")

        # Красим кнопки (как у тебя и было)
        current_markup = callback.message.reply_markup
        new_keyboard = []
        if current_markup:
            for row in current_markup.inline_keyboard:
                new_row = []
                for btn in row:
                    if btn.text == selected_answer:
                        new_text = f"✅ {btn.text}"
                    else:
                        new_text = f"❌ {btn.text}"
                    new_row.append(InlineKeyboardButton(text=new_text, callback_data="ignore"))
                new_keyboard.append(new_row)
        
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=new_keyboard))

        user = await sync_to_async(BotUser.objects.get)(telegram_id=callback.from_user.id)
        # Важливо використати sync_to_async для запиту в БД
        _, created = await sync_to_async(UserProgress.objects.get_or_create)(user=user, lesson=lesson)
        
        # 2. Якщо ми вперше відповіли правильно (created=True) або просто хочемо пустити далі
        # Отримуємо state (його треба додати в аргументи функції)
        # Викликаємо перехід
        await trigger_next_lesson(
            bot=bot,
            user_id=user.telegram_id,
        )

    else:
        # --- 2. НЕПРАВИЛЬНЫЙ ОТВЕТ ---
        
        # 1. Получаем списки вариантов и объяснений
        # splitlines() надежнее, чем split('\n'), так как удаляет символы переноса корректно
        options = [opt.strip() for opt in lesson.quiz_options.splitlines() if opt.strip()]
        explanations = [exp.strip() for exp in lesson.error_feedback.splitlines()] # Тут пустые строки важны!

        feedback_text = "❌ Неправильно."

        # 2. Ищем индекс нажатой кнопки в списке вариантов
        try:
            # Находим, какой по счету этот вариант (0, 1, 2...)
            index = options.index(selected_answer)
            
            # 3. Проверяем, есть ли объяснение для этого индекса
            if index < len(explanations):
                specific_feedback = explanations[index]
                if specific_feedback:
                    feedback_text = f"❌ {specific_feedback}"
        except ValueError:
            # Если вдруг текст кнопки не совпал с опциями в базе (например, админ поменял текст после отправки)
            pass

        # 4. Показываем всплывающее окно (alert)
        await callback.answer(feedback_text, show_alert=True)


# --- ЧАСТЬ 2: ОБРАБОТКА ТЕКСТОВОГО ОТВЕТА ---
@router.message(Learning.waiting_for_text_answer)
async def check_text_answer(message: Message, state: FSMContext, bot: Bot):
    # 1. Узнаем, на какой урок юзер отвечает
    data = await state.get_data()
    lesson_id = data.get("lesson_id")

    attempts = data.get("attempts", 0) + 1
    
    if not lesson_id:
        await message.answer("Ошибка: я забыл, на какой вопрос мы отвечаем. Нажми /start.")
        await state.clear()
        return

    # 2. Достаем урок
    try:
        lesson = await sync_to_async(Lesson.objects.get)(id=lesson_id)
    except Lesson.DoesNotExist:
        await message.answer("Урок был удален.")
        await state.clear()
        return

    # 3. СРАВНИВАЕМ (приводим всё к нижнему регистру для надежности)
    user_words = normalize_text(message.text)
    correct_words = normalize_text(lesson.correct_answer)

    is_correct = (user_words == correct_words)

    if is_correct or attempts >= 3:
        user = await sync_to_async(BotUser.objects.get)(telegram_id=message.from_user.id)

        if is_correct:
            await message.answer(f"✅ <b>Абсолютно верно!</b>\nОтвет: {lesson.correct_answer}")
        else:
            await message.answer(
                f"😔 Попытки исчерпаны.\n"
                f"Правильный ответ: <b>{lesson.correct_answer}</b>\n"
                f"Идем дальше!"
            )
        
        await sync_to_async(UserProgress.objects.get_or_create)(user=user, lesson=lesson)
        await state.update_data(attempts=0)
        await state.set_state(Learning.in_process)

        await trigger_next_lesson(
            bot=bot,
            user_id=user.telegram_id,
            state=state 
        )
    else:
        # Если неправильно
        await state.update_data(attempts=attempts)
        remaining = 3 - attempts
        error_msg = f"❌ Не совсем так. Осталось попыток: {remaining}."

        hint = ""
        min_len = min(len(user_words), len(correct_words))
        for i in range(min_len):
            if user_words[i] != correct_words[i]:
                hint = f"\n💡 Ошибка начинается со слова: <b>{user_words[i]}</b> (нужно: {correct_words[i]})"
                break 

        if not hint and len(user_words) != len(correct_words):
             hint = "\n💡 Количество слов не совпадает."
            
        base_feedback = lesson.error_feedback or error_msg
        await message.answer(f"{base_feedback}{hint}")

@router.callback_query(F.data.startswith("next_lesson:"))
async def on_next_lesson(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.message.edit_text(
            text=f"{callback.message.html_text}\n\n✅ <i>Прочитано</i>",
            reply_markup=None
        )
    except Exception:
        pass 

    await trigger_next_lesson(
        bot=bot,
        user_id=callback.from_user.id,
        state=state
    )
    
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    # Просто убираем часики загрузки
    await callback.answer()