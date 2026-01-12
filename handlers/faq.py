from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.filters import StateFilter
from asgiref.sync import sync_to_async
from core.models import FAQItem 

router = Router()

@sync_to_async
def get_faq_answer(item_id: int):
    try:
        return FAQItem.objects.get(id=item_id)
    except FAQItem.DoesNotExist:
        return None

# --- 1. Вход в меню (по кнопке "❓ Часто задаваемые вопросы") ---
@router.message(F.text.in_({"❓ Часто задаваемые вопросы", "/faq"}), StateFilter('*'))
async def cmd_faq(message: Message):
    kb = await get_faq_main_kb()
    if not kb:
        await message.answer("Список вопросов пока пуст.")
        return
        
    await message.answer("👇 Выберите вопрос:", reply_markup=kb)

# Колбек для навигации: передаем только ID вопроса
class FaqCallback(CallbackData, prefix="faq"):
    action: str  # 'list' или 'show'
    id: int = 0  # ID записи в БД

# Асинхронная функция для получения вопросов из базы
@sync_to_async
def get_faq_list():
    # Преобразуем QuerySet в список, чтобы безопасно использовать в асинхронке
    return list(FAQItem.objects.filter(is_visible=True).order_by('order'))

# Клавиатура списка вопросов (строится динамически)
async def get_faq_main_kb():
    builder = InlineKeyboardBuilder()
    
    # Тянем данные из БД
    items = await get_faq_list()
    
    if not items:
        return None # Если вопросов нет

    for item in items:
        builder.button(
            text=item.question,
            callback_data=FaqCallback(action="show", id=item.id)
        )
    
    builder.button(text="❌ Закрыть", callback_data="close_faq")
    builder.adjust(1)
    return builder.as_markup()

# Клавиатура "Назад"
def get_back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 К списку вопросов", callback_data=FaqCallback(action="list"))
    return builder.as_markup()

# --- 2. Показать список (кнопка "Назад") ---
@router.callback_query(FaqCallback.filter(F.action == "list"))
async def faq_list_callback(callback: CallbackQuery):
    kb = await get_faq_main_kb()
    # Редактируем текущее сообщение
    await callback.message.edit_text("👇 Выберите вопрос:", reply_markup=kb)
    await callback.answer()

# --- 3. Показать ответ ---
@router.callback_query(FaqCallback.filter(F.action == "show"))
async def faq_show_callback(callback: CallbackQuery, callback_data: FaqCallback):
    # Достаем ответ из базы по ID
    item = await get_faq_answer(callback_data.id)
    
    if not item:
        await callback.answer("Этот вопрос был удален.", show_alert=True)
        # Можно обновить список
        kb = await get_faq_main_kb()
        await callback.message.edit_text("👇 Выберите вопрос:", reply_markup=kb)
        return

    # Показываем ответ + кнопку Назад
    await callback.message.edit_text(
        text=f"<b>{item.question}</b>\n\n{item.answer}",
        reply_markup=get_back_kb()
    )
    await callback.answer()

# --- 4. Закрытие ---
@router.callback_query(F.data == "close_faq")
async def close_faq(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()