from aiogram.fsm.state import State, StatesGroup


class FilterForm(StatesGroup):
    waiting_for_input = State()
    choosing_schedule = State()
    choosing_keywords = State()
    choosing_exp = State()
    choosing_workformat = State()

    expecting = State()


