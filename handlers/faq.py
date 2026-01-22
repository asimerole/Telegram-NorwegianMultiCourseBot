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

# Enter the menu (by clicking the "❓ Часто задаваемые вопросы" button) 
@router.message(F.text.in_({"❓ Часто задаваемые вопросы", "/faq"}), StateFilter('*'))
async def cmd_faq(message: Message):
    kb = await get_faq_main_kb()
    if not kb:
        await message.answer("Список вопросов пока пуст.")
        return
        
    await message.answer("👇 Выберите вопрос:", reply_markup=kb)

# Callback for navigation: only pass the question ID
class FaqCallback(CallbackData, prefix="faq"):
    action: str  # 'list' or 'show'
    id: int = 0  # Database record ID

# Asynchronous function for retrieving questions from the database
@sync_to_async
def get_faq_list():
    # Convert QuerySet to a list for safe use in asynchronous operations
    return list(FAQItem.objects.filter(is_visible=True).order_by('order'))

# Question list keyboard (built dynamically)
async def get_faq_main_kb():
    builder = InlineKeyboardBuilder()
    items = await get_faq_list()
    
    if not items:
        return None

    for item in items:
        builder.button(
            text=item.question,
            callback_data=FaqCallback(action="show", id=item.id)
        )
    
    builder.button(text="❌ Закрыть", callback_data="close_faq")
    builder.adjust(1)
    return builder.as_markup()

# Back Keyboard
def get_back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 К списку вопросов", callback_data=FaqCallback(action="list"))
    return builder.as_markup()

# Show list ("Назад" button) 
@router.callback_query(FaqCallback.filter(F.action == "list"))
async def faq_list_callback(callback: CallbackQuery):
    kb = await get_faq_main_kb()
    # Editing the current message
    await callback.message.edit_text("👇 Выберите вопрос:", reply_markup=kb)
    await callback.answer()

# Show answer 
@router.callback_query(FaqCallback.filter(F.action == "show"))
async def faq_show_callback(callback: CallbackQuery, callback_data: FaqCallback):
    # Retrieve the answer from the database by ID
    item = await get_faq_answer(callback_data.id)
    
    if not item:
        await callback.answer("Этот вопрос был удален.", show_alert=True)
        kb = await get_faq_main_kb()
        await callback.message.edit_text("👇 Выберите вопрос:", reply_markup=kb)
        return

    # Show answer + Back button
    await callback.message.edit_text(
        text=f"<b>{item.question}</b>\n\n{item.answer}",
        reply_markup=get_back_kb()
    )
    await callback.answer()

# Close 
@router.callback_query(F.data == "close_faq")
async def close_faq(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()