from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


def start_keyboard() -> ReplyKeyboardMarkup:
    """Ro'yxatdan o'tmagan yangi foydalanuvchilar uchun"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Ro'yxatdan o'tish")],
            [KeyboardButton(text="📝 Ariza qoldirish")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def role_keyboard() -> ReplyKeyboardMarkup:
    """Ro'yxatdan o'tishda rol tanlash uchun"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎓 O'quvchi sifatida")],
            [KeyboardButton(text="👨‍👩‍👧 Ota-ona sifatida")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_keyboard() -> ReplyKeyboardMarkup:
    """Ro'yxatdan o'tgan o'quvchilar uchun"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📅 Dars jadvali"),
                KeyboardButton(text="📝 Nazorat ishlari"),
            ],
            [
                KeyboardButton(text="💳 To'lov jadvali"),
                KeyboardButton(text="📊 Davomatim"),
            ],
            [
                KeyboardButton(text="🏆 Yutuqlarim"),
                KeyboardButton(text="👤 Profilim"),
            ],
        ],
        resize_keyboard=True,
    )


def teacher_keyboard() -> ReplyKeyboardMarkup:
    """O'qituvchilar uchun"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 Davomat olish"),
                KeyboardButton(text="👥 Guruhlarim"),
            ],
            [
                KeyboardButton(text="📅 Dars jadvali"),
                KeyboardButton(text="📊 O'qituvchi statistikasi"),
            ],
        ],
        resize_keyboard=True,
    )


def admin_keyboard() -> ReplyKeyboardMarkup:
    """Admin uchun"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 Davomat olish"),
                KeyboardButton(text="📢 E'lon yuborish"),
            ],
            [KeyboardButton(text="👥 O'quvchilar holati")],
            [
                KeyboardButton(text="💰 Barcha to'lovlar"),
                KeyboardButton(text="💵 To'lov qabul"),
            ],
            [KeyboardButton(text="📊 Guruhlar & Statistika")],
        ],
        resize_keyboard=True,
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamimni yuborish", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
