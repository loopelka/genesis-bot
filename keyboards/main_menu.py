from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Products")],
            [KeyboardButton(text="📞 Contact"), KeyboardButton(text="ℹ️ About")],
        ],
        resize_keyboard=True
    )
    return keyboard
