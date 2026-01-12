from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🆘 Написать в поддержку"),
                KeyboardButton(text="❓ Часто задаваемые вопросы"),
                # Можна додати ще кнопку "Мій прогрес", якщо захочеш
            ]
        ],
        resize_keyboard=True, # Щоб кнопки були маленькі і акуратні
        persistent=True       # Щоб меню не ховалося
    )
