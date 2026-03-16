from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    enter_invite = State()


class CreateOrderStates(StatesGroup):
    choose_city = State()
    service_type = State()
    cleaning_type = State()
    address = State()
    scheduled_at = State()
    area_rooms = State()
    detergents_on_site = State()
    equipment_required = State()
    work_scope = State()
    client_name = State()
    client_phone = State()
    price = State()
    comment = State()
    confirm = State()


class PhotoStates(StatesGroup):
    choose_kind = State()
    upload = State()
