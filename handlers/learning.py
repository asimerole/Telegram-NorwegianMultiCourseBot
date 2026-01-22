from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from core.models import Course, BotUser, Lesson, UserProgress
from states import Learning
from django.utils import timezone # Для фиксации времени старта
from keyboards import main_menu_keyboard
from asgiref.sync import sync_to_async
from services.utils import normalize_text

router = Router()

# --- 1. НАТИСКАННЯ КНОПКИ "✍️ Написати відповідь" ---
@router.callback_query(F.data.startswith("reply_task:"))
async def on_reply_click(callback: CallbackQuery, state: FSMContext):
    try:
        _, lesson_id_str = callback.data.split(":")
        lesson_id = int(lesson_id_str)
    except ValueError:
        await callback.answer("Ошибка кнопки.")
        return

    # Запам'ятовуємо, на який урок відповідає юзер
    await state.update_data(lesson_id=lesson_id, attempts=0)
    
    # Переводимо в режим очікування тексту
    await state.set_state(Learning.waiting_for_text_answer)

    # Робимо Reply (відповідь на повідомлення), щоб було красиво
    await callback.message.reply("✍️ <b>Напиши свой ответ на это задание:</b>")
    await callback.answer()
    
# BUTTON PROCESSING (QUIZ) 
@router.callback_query(F.data.startswith("ans:"))
async def check_quiz_answer(callback: CallbackQuery, bot: Bot):
    try:
        _, lesson_id_str, selected_answer = callback.data.split(":", 2)
        lesson_id = int(lesson_id_str)
    except ValueError:
        await callback.answer("Ошибка данных кнопки.")
        return

    try:
        lesson = Lesson.objects.get(id=lesson_id)
    except Lesson.DoesNotExist:
        await callback.answer("Урок не найден.")
        return

    selected_answer = selected_answer.strip()
    correct_answer = lesson.correct_answer.strip()
    
    is_correct = (selected_answer == correct_answer)

    if is_correct:
        # CORRECT ANSWER 
        await callback.answer("✅ Правильно!")
        await callback.message.answer(f"👍 <b>Верно!</b>\n{correct_answer}")

        # We paint the buttons
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
        # It is important to use sync_to_async for database queries.
        _, created = await sync_to_async(UserProgress.objects.get_or_create)(user=user, lesson=lesson)
    else:
        # WRONG ANSWER
        # We get lists of options and explanations.
        # splitlines() is more reliable than split(‘\n’) because it removes line breaks correctly.
        options = [opt.strip() for opt in lesson.quiz_options.splitlines() if opt.strip()]
        explanations = [exp.strip() for exp in lesson.error_feedback.splitlines()] # Тут пустые строки важны!

        feedback_text = "❌ Неправильно."

        # Search for the index of the pressed button in the list of options
        try:
            if selected_answer in options:
                index = options.index(selected_answer)
                if index < len(explanations):
                    specific_feedback = explanations[index]
                    if specific_feedback:
                        feedback_text = f"❌ {specific_feedback}"
        except ValueError:
            # If the button text does not match the options in the database (for example, the administrator changed the text after sending)
            pass

        # Display a pop-up window (alert)
        await callback.answer(feedback_text, show_alert=True)


# PROCESSING THE TEXT RESPONSE
@router.message(Learning.waiting_for_text_answer)
async def check_text_answer(message: Message, state: FSMContext, bot: Bot):
    # Let's find out which lesson the user is responding to
    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    attempts = data.get("attempts", 0) + 1
    
    if not lesson_id:
        await message.answer("Ошибка: я забыл, на какой вопрос мы отвечаем. Нажми /start.")
        await state.clear()
        return

    # We get the lesson
    try:
        lesson = await sync_to_async(Lesson.objects.get)(id=lesson_id)
    except Lesson.DoesNotExist:
        await message.answer("Урок был удален.")
        await state.clear()
        return

    # COMPARISON (we convert everything to lowercase for reliability)
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
    else:
        # If incorrect
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

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    # Just remove the loading clock
    await callback.answer()