from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    waiting_for_access_code = State()

class Learning(StatesGroup):
    in_process = State()
    waiting_for_text_answer = State()

class Support(StatesGroup):
    waiting_for_message = State()