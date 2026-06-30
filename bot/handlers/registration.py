import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from asgiref.sync import sync_to_async

from bot.keyboards.reply import (
    main_keyboard, phone_keyboard, teacher_keyboard,
    admin_keyboard, start_keyboard, role_keyboard, remove_keyboard,
)

logger = logging.getLogger(__name__)
register_router = Router()


# ─── States ───────────────────────────────────────────────────────────────────

class RegisterState(StatesGroup):
    waiting_role        = State()
    waiting_name        = State()
    waiting_phone       = State()
    # parent-only states
    waiting_child_phone = State()
    waiting_parent_name = State()


class ArizaState(StatesGroup):
    waiting_name  = State()
    waiting_phone = State()
    waiting_group = State()


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _is_admin(telegram_id: int) -> bool:
    from academy.models import BotAdmin
    return await sync_to_async(BotAdmin.is_admin)(telegram_id)


async def _notify_admins(bot, text: str, reply_markup=None):
    from django.conf import settings
    admin_ids = settings.ADMIN_TELEGRAM_IDS
    print(f"[DEBUG] _notify_admins: bot={bot}, admin_ids={admin_ids}")

    if not admin_ids:
        print("[DEBUG] ADMIN_TELEGRAM_IDS bo'sh!")
        return

    if bot is None:
        print("[DEBUG] bot=None! Bu jiddiy muammo.")
        return

    for admin_id in admin_ids:
        print(f"[DEBUG] {admin_id} ga yuborilmoqda, matn: {text[:50]}...")
        try:
            await bot.send_message(admin_id, text, reply_markup=reply_markup)
            print(f"[DEBUG] ✅ {admin_id} ga yuborildi!")
        except Exception as e:
            print(f"[DEBUG] ❌ XATOLIK {admin_id}: {type(e).__name__}: {e}")


# ─── /start ───────────────────────────────────────────────────────────────────

@register_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    from academy.models import Student, Teacher

    tg_id = message.from_user.id

    # Admin
    if await _is_admin(tg_id):
        await message.answer(
            "Assalomu alaykum, *Admin*! 👑\n\n"
            "Boshqaruv paneliga xush kelibsiz!",
            reply_markup=admin_keyboard(),
            parse_mode='Markdown'
        )
        return

    # O'qituvchi
    is_teacher = await sync_to_async(
        Teacher.objects.filter(telegram_id=tg_id, is_active=True).exists
    )()
    if is_teacher:
        teacher = await sync_to_async(
            Teacher.objects.filter(telegram_id=tg_id).first
        )()
        await message.answer(
            f"Assalomu alaykum, *{teacher.full_name}*! 👨‍🏫\n\n"
            f"O'qituvchi paneliga xush kelibsiz!",
            reply_markup=teacher_keyboard(),
            parse_mode='Markdown'
        )
        return

    # Ota-ona sifatida bog'langan (parent_telegram_id orqali)
    from django.db.models import Q as DjQ
    student = await sync_to_async(
        lambda: Student.objects.filter(
            DjQ(telegram_id=tg_id) | DjQ(parent_telegram_id=tg_id)
        ).select_related('group').first()
    )()
    if student:
        is_parent = student.parent_telegram_id == tg_id and student.telegram_id != tg_id
        name = student.parent_name if is_parent else student.full_name
        greeting = f"Assalomu alaykum, *{name}*! 👋\n\n"
        if is_parent:
            greeting += f"👤 Farzand: *{student.full_name}*\n"
        if student.group:
            greeting += (
                f"🏫 Guruh: {student.group.name}\n\n"
                f"Menyudan birini tanlang:"
            )
        else:
            greeting += (
                f"⏳ Arizangiz ko'rib chiqilmoqda.\n"
                f"Administrator guruhni belgilagach xabar keladi."
            )
        await message.answer(greeting, reply_markup=main_keyboard(), parse_mode='Markdown')
        return

    # Yangi foydalanuvchi — 2 ta tugma
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "📐 *MathAcademy* botiga xush kelibsiz!\n\n"
        "Quyidagilardan birini tanlang:",
        reply_markup=start_keyboard(),
        parse_mode='Markdown'
    )


# ─── RO'YXATDAN O'TISH — Boshlash ────────────────────────────────────────────

@register_router.message(F.text == "✅ Ro'yxatdan o'tish")
async def register_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✅ *Ro'yxatdan o'tish*\n\n"
        "Siz kimning nomidan ro'yxatdan o'tyapsiz?",
        reply_markup=role_keyboard(),
        parse_mode='Markdown'
    )
    await state.set_state(RegisterState.waiting_role)


@register_router.message(
    RegisterState.waiting_role,
    F.text.in_(["🎓 O'quvchi sifatida", "👨‍👩‍👧 Ota-ona sifatida"])
)
async def register_role(message: Message, state: FSMContext):
    role = "student" if "O'quvchi" in message.text else "parent"
    await state.update_data(role=role)

    if role == "student":
        await message.answer(
            "🎓 *O'quvchi sifatida ro'yxat*\n\n"
            "O'quvchining to'liq ismini kiriting:\n"
            "_(Masalan: Aliyev Bobur Ilyosovich)_",
            reply_markup=remove_keyboard(),
            parse_mode='Markdown'
        )
        await state.set_state(RegisterState.waiting_name)
    else:
        await message.answer(
            "👨‍👩‍👧 *Ota-ona sifatida ro'yxat*\n\n"
            "Farzandingizning telefon raqamini kiriting:\n"
            "_(Masalan: +998901234567)_",
            reply_markup=phone_keyboard(),
            parse_mode='Markdown'
        )
        await state.set_state(RegisterState.waiting_child_phone)


@register_router.message(RegisterState.waiting_role)
async def register_role_wrong(message: Message):
    await message.answer(
        "⚠️ Iltimos, quyidagi tugmalardan birini tanlang:",
        reply_markup=role_keyboard()
    )


@register_router.message(RegisterState.waiting_name)
async def register_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 5 or len(name.split()) < 2:
        await message.answer(
            "⚠️ Iltimos, *to'liq ism va familiyani* kiriting:\n"
            "_(Masalan: Aliyev Bobur)_",
            parse_mode='Markdown'
        )
        return
    await state.update_data(full_name=name)
    await message.answer(
        f"✅ Ism: *{name}*\n\nTelefon raqamingizni yuboring:",
        reply_markup=phone_keyboard(),
        parse_mode='Markdown'
    )
    await state.set_state(RegisterState.waiting_phone)


# ─── OTA-ONA: farzand telefon raqami orqali bog'lash ─────────────────────────

@register_router.message(RegisterState.waiting_child_phone, F.contact)
async def parent_child_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone
    await _find_child_by_phone(message, state, phone)


@register_router.message(RegisterState.waiting_child_phone, F.text)
async def parent_child_phone_text(message: Message, state: FSMContext):
    raw = message.text.strip().replace(' ', '').replace('-', '')
    if not raw.startswith('+'):
        raw = '+998' + raw.lstrip('0')
    if len(raw) < 10:
        await message.answer("⚠️ Noto'g'ri raqam. Qayta kiriting (+998XXXXXXXXX):")
        return
    await _find_child_by_phone(message, state, raw)


async def _find_child_by_phone(message: Message, state: FSMContext, phone: str):
    from academy.models import Student
    child = await sync_to_async(
        lambda: Student.objects.filter(phone=phone).select_related('group').first()
    )()
    if not child:
        await message.answer(
            "❌ *Bu telefon raqamli o'quvchi topilmadi.*\n\n"
            "Farzandingiz avval ro'yxatdan o'tgan bo'lishi kerak.\n"
            "Raqamni tekshirib, qayta kiriting:",
            parse_mode='Markdown'
        )
        return
    await state.update_data(child_id=child.id, child_name=child.full_name)
    await message.answer(
        f"✅ O'quvchi topildi: *{child.full_name}*\n\n"
        f"Endi sizning (ota-ona) to'liq ismingizni kiriting:\n"
        f"_(Masalan: Aliyev Ilyos Yusupovich)_",
        reply_markup=remove_keyboard(),
        parse_mode='Markdown'
    )
    await state.set_state(RegisterState.waiting_parent_name)


@register_router.message(RegisterState.waiting_parent_name)
async def parent_name_entered(message: Message, state: FSMContext):
    from academy.models import Student
    name = message.text.strip()
    if len(name) < 3:
        await message.answer("⚠️ Iltimos, to'liq ismingizni kiriting:")
        return
    data = await state.get_data()
    child_id = data['child_id']
    child_name = data['child_name']
    await state.clear()

    child = await sync_to_async(Student.objects.get)(id=child_id)
    child.parent_telegram_id = message.from_user.id
    child.parent_telegram_username = message.from_user.username or ''
    child.parent_name = name
    await sync_to_async(child.save)(update_fields=['parent_telegram_id', 'parent_telegram_username', 'parent_name'])

    await message.answer(
        f"✅ *Muvaffaqiyatli bog'landi!*\n\n"
        f"👤 Farzand: *{child_name}*\n"
        f"👨‍👩‍👧 Ota-ona: *{name}*\n\n"
        f"Endi siz farzandingiz ma'lumotlarini ko'ra olasiz.",
        reply_markup=main_keyboard(),
        parse_mode='Markdown'
    )


@register_router.message(RegisterState.waiting_phone, F.contact)
async def register_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone
    await _finalize_registration(message, state, phone)


@register_router.message(RegisterState.waiting_phone, F.text)
async def register_phone_text(message: Message, state: FSMContext):
    raw = message.text.strip().replace(' ', '').replace('-', '')
    if not raw.startswith('+'):
        raw = '+998' + raw.lstrip('0')
    if len(raw) < 10:
        await message.answer("⚠️ Noto'g'ri raqam. Qayta kiriting (+998XXXXXXXXX):")
        return
    await _finalize_registration(message, state, raw)


async def _finalize_registration(message: Message, state: FSMContext, phone: str):
    from academy.models import Student

    data = await state.get_data()
    full_name = data['full_name']
    role = data.get('role', 'student')
    print(f"[DEBUG] _finalize_registration: name={full_name}, phone={phone}, role={role}")
    await state.clear()

    student, created = await sync_to_async(Student.objects.get_or_create)(
        telegram_id=message.from_user.id,
        defaults={
            'full_name': full_name,
            'phone': phone,
            'telegram_username': message.from_user.username or '',
        }
    )
    student.full_name = full_name
    student.phone = phone
    student.telegram_username = message.from_user.username or ''
    await sync_to_async(student.save)()
    print(f"[DEBUG] Student {'yaratildi' if created else 'yangilandi'}: id={student.id}")

    role_label = "O'quvchi" if role == "student" else "Ota-ona"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Qabul", callback_data=f"reg_approve_{student.id}"),
        InlineKeyboardButton(text="❌ O'tmen", callback_data=f"reg_reject_{student.id}"),
    ]])

    admin_text = (
        f"Yangi royxatdan otish!\n\n"
        f"Ism: {full_name}\n"
        f"Tel: {phone}\n"
        f"Turi: {role_label}\n"
        f"Telegram: @{message.from_user.username or '-'} (ID: {message.from_user.id})"
    )
    print(f"[DEBUG] Admin matn: {admin_text}")
    await _notify_admins(message.bot, admin_text, reply_markup=keyboard)

    await message.answer(
        f"✅ *Ma'lumotlaringiz qabul qilindi!*\n\n"
        f"👤 Ism: {full_name}\n"
        f"📞 Tel: {phone}\n\n"
        f"⏳ Administrator ko'rib chiqib, guruhga biriktiradi.\n"
        f"Xabarnoma lichkangizga keladi.",
        reply_markup=main_keyboard(),
        parse_mode='Markdown'
    )


# ─── ARIZA QOLDIRISH ──────────────────────────────────────────────────────────

@register_router.message(F.text == "📝 Ariza qoldirish")
async def ariza_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📝 *Ariza qoldirish*\n\n"
        "To'liq ismingizni kiriting:\n"
        "_(Masalan: Aliyev Bobur Ilyosovich)_",
        reply_markup=remove_keyboard(),
        parse_mode='Markdown'
    )
    await state.set_state(ArizaState.waiting_name)


@register_router.message(ArizaState.waiting_name)
async def ariza_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 5 or len(name.split()) < 2:
        await message.answer(
            "⚠️ Iltimos, *to'liq ism va familiyani* kiriting:",
            parse_mode='Markdown'
        )
        return
    await state.update_data(full_name=name)
    await message.answer(
        f"✅ Ism: *{name}*\n\nTelefon raqamingizni yuboring:",
        reply_markup=phone_keyboard(),
        parse_mode='Markdown'
    )
    await state.set_state(ArizaState.waiting_phone)


@register_router.message(ArizaState.waiting_phone, F.contact)
async def ariza_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone
    await _ariza_ask_group(message, state, phone)


@register_router.message(ArizaState.waiting_phone, F.text)
async def ariza_phone_text(message: Message, state: FSMContext):
    raw = message.text.strip().replace(' ', '').replace('-', '')
    if not raw.startswith('+'):
        raw = '+998' + raw.lstrip('0')
    if len(raw) < 10:
        await message.answer("⚠️ Noto'g'ri raqam. Qayta kiriting:")
        return
    await _ariza_ask_group(message, state, raw)


async def _ariza_ask_group(message: Message, state: FSMContext, phone: str):
    from academy.models import Group
    await state.update_data(phone=phone)

    groups = await sync_to_async(
        lambda: list(Group.objects.filter(is_active=True).order_by('name'))
    )()

    days_short = ['Du', 'Se', 'Chor', 'Pay', 'Ju', 'Sha', 'Yak']
    text = "🏫 *Qaysi guruhga qiziqasiz?*\n\n"

    if groups:
        text += "Mavjud guruhlar:\n\n"
        for g in groups:
            schedules = await sync_to_async(
                lambda grp=g: list(grp.schedules.all().order_by('start_time'))
            )()
            if schedules:
                s = schedules[0]
                days_str = '/'.join(days_short[d] for d in sorted(s.days_of_week or []))
                time_str = s.start_time.strftime('%H:%M')
                text += f"• *{g.name}* — {days_str} soat {time_str}\n"
            else:
                text += f"• *{g.name}*\n"
        text += "\n"

    text += "Qaysi guruh yoki vaqt qulayligini yozing:"

    await message.answer(text, reply_markup=remove_keyboard(), parse_mode='Markdown')
    await state.set_state(ArizaState.waiting_group)


@register_router.message(ArizaState.waiting_group)
async def ariza_group(message: Message, state: FSMContext):
    data = await state.get_data()
    full_name = data['full_name']
    phone = data['phone']
    desired_group = message.text.strip()
    await state.clear()
    print(f"[DEBUG] ariza_group: name={full_name}, phone={phone}, group={desired_group}")

    admin_text = (
        f"Yangi ariza!\n\n"
        f"Ism: {full_name}\n"
        f"Tel: {phone}\n"
        f"Guruh: {desired_group}\n"
        f"Telegram: @{message.from_user.username or '-'} (ID: {message.from_user.id})"
    )
    print(f"[DEBUG] Ariza admin matn: {admin_text}")
    await _notify_admins(message.bot, admin_text)

    await message.answer(
        "✅ *Arizangiz qabul qilindi!*\n\n"
        "Administrator tez orada siz bilan bog'lanadi. 📞",
        reply_markup=start_keyboard(),
        parse_mode='Markdown'
    )


# ─── ADMIN CALLBACKS: Qabul / O'tmen / Guruh tanlash ─────────────────────────

@register_router.callback_query(F.data.startswith('reg_approve_'))
async def admin_approve(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Sizda ruxsat yo'q.", show_alert=True)
        return

    student_id = int(callback.data.split('_')[-1])
    from academy.models import Student, Group

    student = await sync_to_async(
        lambda: Student.objects.select_related('group').get(id=student_id)
    )()
    groups = await sync_to_async(
        lambda: list(Group.objects.filter(is_active=True).order_by('name'))
    )()

    if not groups:
        await callback.answer("Guruhlar mavjud emas! Avval guruh yarating.", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"🏫 {g.name}",
            callback_data=f"reg_group_{student_id}_{g.id}"
        )]
        for g in groups
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"✅ *{student.full_name}* qabul qilindi.\n\n"
        f"📞 Tel: {student.phone}\n\n"
        f"Qaysi guruhga biriktirmoqchisiz?",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    await callback.answer()


@register_router.callback_query(F.data.startswith('reg_reject_'))
async def admin_reject(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Sizda ruxsat yo'q.", show_alert=True)
        return

    student_id = int(callback.data.split('_')[-1])
    from academy.models import Student

    student = await sync_to_async(Student.objects.get)(id=student_id)

    await callback.message.edit_text(
        f"❌ *{student.full_name}* — ariza rad etildi.",
        parse_mode='Markdown'
    )

    try:
        await callback.bot.send_message(
            student.telegram_id,
            "❌ Afsuski, arizangiz qabul qilinmadi.\n\n"
            "Batafsil ma'lumot uchun akademiya bilan bog'laning.\n"
            "Qayta urinish uchun /start bosing.",
        )
        # O'quvchini DBdan o'chirish (qayta ro'yxatdan o'tishi uchun)
        await sync_to_async(student.delete)()
    except Exception:
        pass

    await callback.answer("Rad etildi.")


@register_router.callback_query(F.data.startswith('reg_group_'))
async def admin_assign_group(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Sizda ruxsat yo'q.", show_alert=True)
        return

    parts = callback.data.split('_')
    student_id = int(parts[2])
    group_id   = int(parts[3])

    from academy.models import Student, Group, Schedule

    student = await sync_to_async(Student.objects.get)(id=student_id)
    group   = await sync_to_async(
        lambda: Group.objects.prefetch_related('schedules').get(id=group_id)
    )()

    student.group = group
    await sync_to_async(student.save)(update_fields=['group'])

    schedules = await sync_to_async(
        lambda: list(
            Schedule.objects.filter(group=group).order_by('start_time')
        )
    )()

    DAYS = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
    schedule_text = ""
    for s in schedules:
        room = f" (🚪 {s.room})" if s.room else ""
        days_str = ', '.join(DAYS[d] for d in sorted(s.days_of_week or []))
        schedule_text += (
            f"  📌 *{days_str}*"
            f" — {s.start_time.strftime('%H:%M')}–{s.end_time.strftime('%H:%M')}{room}\n"
        )

    if not schedule_text:
        schedule_text = "  _Jadval hali belgilanmagan_"

    await callback.message.edit_text(
        f"✅ *{student.full_name}* → *{group.name}* guruhiga biriktirildi.",
        parse_mode='Markdown'
    )
    await callback.answer(f"✅ {group.name} guruhiga biriktirildi!")

    try:
        await callback.bot.send_message(
            student.telegram_id,
            f"🎉 *Tabriklaymiz, {student.full_name}!*\n\n"
            f"Siz *{group.name}* guruhiga qabul qilindingiz!\n\n"
            f"📅 *Dars jadvali:*\n{schedule_text}\n\n"
            f"Darsga o'z vaqtida kelishingizni so'raymiz! 💪",
            reply_markup=main_keyboard(),
            parse_mode='Markdown'
        )
    except Exception:
        pass
