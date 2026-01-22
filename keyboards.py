from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🆘 Написать в поддержку"),
                KeyboardButton(text="❓ Часто задаваемые вопросы"),
                KeyboardButton(text="🔑 Ввести код доступа"),
                # You can add a “My Progress” button 
            ]
        ],
        resize_keyboard=True, # So that the buttons are small and neat
        persistent=True       # So that the menu does not hide
    )
