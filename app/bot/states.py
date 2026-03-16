from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    enter_invite = State()


class CreateOrderStates(StatesGroup):
    choose_city = State()
    service_type = State()
    cleaning_type = State()
    address = State()
    scheduled_at = State()
    area_sqm = State()
    rooms_count = State()
    bathrooms_count = State()
    detergents_on_site = State()
    vacuum_on_site = State()
    ladder_on_site = State()
    equipment_required = State()
    work_scope = State()
    access_notes = State()
    client_name = State()
    client_phone = State()
    client_contact_method = State()
    price = State()
    comment = State()
    confirm = State()


class PhotoStates(StatesGroup):
    choose_kind = State()
    upload = State()


class AdminStates(StatesGroup):
    add_or_update_city = State()
