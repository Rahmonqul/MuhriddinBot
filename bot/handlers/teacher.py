from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from asgiref.sync import sync_to_async
from datetime import date

teacher_router = Router()

DAYS_UZ = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_admin(telegram_id: int) -> bool:
    from django.conf import settings
    return telegram_id in settings.ADMIN_TELEGRAM_IDS


async def _is_teacher(telegram_id: int) -> bool:
    from academy.models import Teacher
    return await sync_to_async(
        Teacher.objects.filter(telegram_id=telegram_id, is_active=True).exists
    )()


async def _get_teacher(telegram_id: int):
    from academy.models import Teacher
    return await sync_to_async(
        lambda: Teacher.objects.filter(telegram_id=telegram_id).first()
    )()


async def _has_access(telegram_id: int) -> bool:
    return _is_admin(telegram_id) or await _is_teacher(telegram_id)


# ─── States ───────────────────────────────────────────────────────────────────

class AttendanceState(StatesGroup):
    selecting_group      = State()
    marking              = State()
    writing_topic        = State()
    reatt_select_student = State()   # Qayta davomat: o'quvchi tanlash
    entering_late_min    = State()   # Kechikish daqiqasini kiritish


# ─── Davomat olish — Guruh tanlash ───────────────────────────────────────────

@teacher_router.message(F.text == "📋 Davomat olish")
@teacher_router.message(Command('davomat'))
async def cmd_attendance(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    if not await _has_access(tg_id):
        await message.answer("⛔ Bu buyruq faqat o'qituvchi yoki admin uchun.")
        return

    await state.clear()
    from academy.models import Group

    if _is_admin(tg_id):
        # Admin — barcha guruhlar
        groups = await sync_to_async(
            lambda: list(Group.objects.filter(is_active=True).select_related('teacher'))
        )()
    else:
        # O'qituvchi — faqat o'ziniki
        teacher = await _get_teacher(tg_id)
        groups = await sync_to_async(
            lambda: list(Group.objects.filter(teacher=teacher, is_active=True))
        )()

    if not groups:
        await message.answer("Hech qanday guruh topilmadi.")
        return

    today = date.today()
    DAYS = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']

    buttons = []
    for g in groups:
        teacher_label = f" ({g.teacher.full_name})" if _is_admin(tg_id) and g.teacher else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"👥 {g.name}{teacher_label}",
                callback_data=f"att_grp_{g.id}"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"📋 *Davomat olish*\n"
        f"📅 {today.strftime('%d.%m.%Y')} — {DAYS[today.weekday()]}\n\n"
        f"Guruhni tanlang:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    await state.set_state(AttendanceState.selecting_group)


# ─── Guruh tanlandi ───────────────────────────────────────────────────────────

@teacher_router.callback_query(AttendanceState.selecting_group, F.data.startswith('att_grp_'))
async def select_group(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split('_')[-1])
    today = date.today()

    from academy.models import Group, Schedule, Lesson, Student, Attendance

    group = await sync_to_async(Group.objects.get)(id=group_id)

    # Bugun dars bor jadvallarni tekshiramiz
    all_schedules = await sync_to_async(
        lambda: list(Schedule.objects.filter(group=group))
    )()
    today_schedules = [s for s in all_schedules if today.weekday() in (s.days_of_week or [])]

    if not today_schedules:
        await callback.message.edit_text(
            f"📅 Bugun *{group.name}* guruhida dars yo'q.\n\n"
            f"Baribir davomat olmoqchimisiz?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Ha, ol", callback_data=f"att_force_{group_id}"),
                    InlineKeyboardButton(text="❌ Bekor", callback_data="att_cancel"),
                ]
            ]),
            parse_mode='Markdown'
        )
        await callback.answer()
        return

    await _start_attendance(callback, state, group, today, today_schedules[0])


@teacher_router.callback_query(F.data.startswith('att_force_'))
async def force_attendance(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split('_')[-1])
    today = date.today()

    from academy.models import Group, Schedule, Lesson

    group = await sync_to_async(Group.objects.get)(id=group_id)

    # Jadval bo'lmasa ham, birinchi jadval yoki yangi lesson yaratamiz
    schedules = await sync_to_async(
        lambda: list(Schedule.objects.filter(group=group).order_by('start_time'))
    )()

    if not schedules:
        await callback.message.edit_text(
            "❌ Bu guruh uchun jadval umuman belgilanmagan.\n"
            "Admin panelda avval jadval qo'shing."
        )
        await state.clear()
        await callback.answer()
        return

    await _start_attendance(callback, state, group, today, schedules[0])


@teacher_router.callback_query(F.data == "att_cancel")
async def cancel_attendance(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Davomat bekor qilindi.")
    await callback.answer()


async def _start_attendance(callback, state, group, today, schedule):
    from academy.models import Lesson, Student, Attendance

    lesson, _ = await sync_to_async(Lesson.objects.get_or_create)(
        schedule=schedule, date=today
    )

    students = await sync_to_async(
        lambda: list(Student.objects.filter(group=group, is_active=True).order_by('full_name'))
    )()

    if not students:
        await callback.message.edit_text(
            f"*{group.name}* guruhida faol o'quvchilar yo'q.",
            parse_mode='Markdown'
        )
        await state.clear()
        await callback.answer()
        return

    # Allaqachon belgilangan o'quvchilarni aniqlaymiz
    marked_ids = await sync_to_async(
        lambda: set(
            Attendance.objects.filter(lesson=lesson)
            .values_list('student_id', flat=True)
        )
    )()

    unmarked = [s for s in students if s.id not in marked_ids]

    if not unmarked:
        await callback.message.edit_text(
            f"✅ *{group.name}* guruhining davomati allaqachon olingan.",
            parse_mode='Markdown'
        )
        await state.clear()
        await callback.answer()
        return

    await state.update_data(
        lesson_id=lesson.id,
        group_name=group.name,
        student_ids=[s.id for s in unmarked],
        all_count=len(students),
        current_idx=0,
        results=[],
    )
    await state.set_state(AttendanceState.marking)

    already = len(marked_ids)
    header = (
        f"📋 *{group.name}* — {today.strftime('%d.%m.%Y')}\n"
        f"O'quvchilar: {len(students)} ta"
    )
    if already:
        header += f" (allaqachon belgilangan: {already})"
    header += "\n\nHar bir o'quvchi uchun holatni belgilang:"

    await callback.message.edit_text(header, parse_mode='Markdown')
    await callback.answer()

    first_student = await sync_to_async(
        lambda: Student.objects.get(id=unmarked[0].id)
    )()
    await _send_student_card(callback.message, first_student, 0, len(unmarked))


# ─── O'quvchi kartasi ─────────────────────────────────────────────────────────

async def _send_student_card(message, student, idx: int, total: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Keldi",      callback_data=f"mark_present_{student.id}"),
        InlineKeyboardButton(text="⏰ Kech qoldi", callback_data=f"mark_late_{student.id}"),
        InlineKeyboardButton(text="❌ Kelmadi",    callback_data=f"mark_absent_{student.id}"),
    ]])
    await message.answer(
        f"👤 *{student.full_name}*\n"
        f"📞 {student.phone}\n"
        f"_{idx + 1} / {total}_",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


# ─── Status belgilash ─────────────────────────────────────────────────────────

@teacher_router.callback_query(
    AttendanceState.marking,
    F.data.startswith('mark_')
)
async def mark_student(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    status     = parts[1]            # present | late | absent
    student_id = int(parts[2])

    data        = await state.get_data()
    lesson_id   = data['lesson_id']
    student_ids = data['student_ids']
    current_idx = data['current_idx']
    results     = data['results']

    from academy.models import Attendance, Student

    await sync_to_async(Attendance.objects.update_or_create)(
        student_id=student_id,
        lesson_id=lesson_id,
        defaults={'status': status}
    )

    student = await sync_to_async(Student.objects.get)(id=student_id)
    emoji = {'present': '✅', 'late': '⏰', 'absent': '❌'}[status]
    results.append({'id': student_id, 'status': status})

    await callback.answer(f"{emoji} {student.full_name} — belgilandi")

    # O'quvchi lichkasiga xabar
    await _notify_student_attendance(student, status, callback.bot)

    # Keyingi o'quvchi
    next_idx = current_idx + 1
    if next_idx >= len(student_ids):
        present = sum(1 for r in results if r['status'] == 'present')
        late    = sum(1 for r in results if r['status'] == 'late')
        absent  = sum(1 for r in results if r['status'] == 'absent')

        lesson_id  = data['lesson_id']
        group_name = data['group_name']

        # Davomat yakunida 4 ta tugma
        post_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Qarzdorlarga eslatma",
                    callback_data=f"post_pay_{lesson_id}"
                ),
                InlineKeyboardButton(
                    text="📢 Kelmaganlarga xabar",
                    callback_data=f"post_absent_{lesson_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📝 Mavzu yozish",
                    callback_data=f"post_topic_{lesson_id}"
                ),
                InlineKeyboardButton(
                    text="🔄 Qayta davomat",
                    callback_data=f"reatt_{lesson_id}"
                ),
            ],
        ])

        await callback.message.answer(
            f"✅ *{group_name}* davomati yakunlandi!\n\n"
            f"✅ Keldi:       *{present}* ta\n"
            f"⏰ Kech qoldi: *{late}* ta\n"
            f"❌ Kelmadi:    *{absent}* ta\n"
            f"📝 Jami:       *{len(results)}* ta",
            reply_markup=post_keyboard,
            parse_mode='Markdown'
        )
        await state.clear()
        return

    await state.update_data(current_idx=next_idx, results=results)
    next_student = await sync_to_async(Student.objects.get)(id=student_ids[next_idx])
    await _send_student_card(callback.message, next_student, next_idx, len(student_ids))


# ─── O'quvchiga xabarnoma ────────────────────────────────────────────────────

async def _notify_student_attendance(student, status: str, bot, late_minutes: int = 0):
    if not student.telegram_id:
        return

    today_str = date.today().strftime('%d.%m.%Y')

    if status == 'present':
        text = (
            f"✅ Salom, *{student.full_name}*!\n\n"
            f"Bugun *{today_str}* darsga keldingiz.\n"
            f"Davomatingiz qayd etildi. Rahmat! 💪"
        )
    elif status == 'late':
        min_str = f" (*{late_minutes} daqiqa*)" if late_minutes else ""
        text = (
            f"⏰ Salom, *{student.full_name}*!\n\n"
            f"Bugun *{today_str}* darsga kech qoldingiz{min_str}.\n"
            f"Keyinchalik vaqtida kelishga harakat qiling! 🙏"
        )
    elif status == 'absent':
        text = (
            f"❌ Salom, *{student.full_name}*!\n\n"
            f"Bugun *{today_str}* darsga kelmaganingiz qayd etildi.\n\n"
            f"Sabab bo'lsa, o'qituvchi yoki administrator bilan bog'laning. 📞"
        )
    else:
        return

    try:
        await bot.send_message(student.telegram_id, text, parse_mode='Markdown')
    except Exception as e:
        print(f"[NOTIFY] {student.full_name} ga xabar yuborib bo'lmadi: {e}")


# ─── Qayta davomat ────────────────────────────────────────────────────────────

@teacher_router.callback_query(F.data.startswith('reatt_'))
async def reatt_show_students(callback: CallbackQuery, state: FSMContext):
    """Qayta davomat — o'quvchi tanlash."""
    if not await _has_access(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q")
        return

    lesson_id = int(callback.data.split('_')[1])

    from academy.models import Lesson, Attendance, Student
    lesson = await sync_to_async(
        lambda: Lesson.objects.select_related('schedule__group').get(id=lesson_id)
    )()

    # Barcha belgilangan o'quvchilar + ularning holati
    atts = await sync_to_async(
        lambda: list(
            Attendance.objects.filter(lesson=lesson)
            .select_related('student')
            .order_by('student__full_name')
        )
    )()

    if not atts:
        await callback.answer("Hali birorta o'quvchi belgilanmagan.", show_alert=True)
        return

    buttons = []
    status_icons = {'present': '✅', 'late': '⏰', 'absent': '❌'}
    for att in atts:
        icon = status_icons.get(att.status, '❓')
        late_str = f" ({att.late_minutes} daq)" if att.late_minutes else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {att.student.full_name}{late_str}",
                callback_data=f"re_s_{lesson_id}_{att.student_id}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="✖ Yopish", callback_data="re_close")
    ])

    await state.update_data(reatt_lesson_id=lesson_id)
    await state.set_state(AttendanceState.reatt_select_student)

    await callback.message.answer(
        f"🔄 *Qayta davomat — {lesson.schedule.group.name}*\n"
        f"📅 {lesson.date.strftime('%d.%m.%Y')}\n\n"
        f"O'zgartirilsin — qaysi o'quvchi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='Markdown'
    )
    await callback.answer()


@teacher_router.callback_query(F.data == "re_close")
async def reatt_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Yopildi")


@teacher_router.callback_query(
    AttendanceState.reatt_select_student,
    F.data.startswith('re_s_')
)
async def reatt_select_student(callback: CallbackQuery, state: FSMContext):
    """O'quvchi tanlandi — yangi holat tanlash."""
    parts = callback.data.split('_')   # re_s_{lesson_id}_{student_id}
    lesson_id  = int(parts[2])
    student_id = int(parts[3])

    from academy.models import Student
    student = await sync_to_async(Student.objects.get)(id=student_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Keldi",      callback_data=f"re_p_{lesson_id}_{student_id}"),
            InlineKeyboardButton(text="⏰ Kech qoldi", callback_data=f"re_l_{lesson_id}_{student_id}"),
            InlineKeyboardButton(text="❌ Kelmadi",    callback_data=f"re_a_{lesson_id}_{student_id}"),
        ],
        [InlineKeyboardButton(text="← Orqaga", callback_data=f"reatt_{lesson_id}")],
    ])

    await callback.message.answer(
        f"👤 *{student.full_name}*\n\nYangi holatni tanlang:",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    await callback.answer()


@teacher_router.callback_query(
    AttendanceState.reatt_select_student,
    F.data.startswith('re_p_')
)
async def reatt_mark_present(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    lesson_id, student_id = int(parts[2]), int(parts[3])
    await _do_reatt(callback, state, lesson_id, student_id, 'present', 0)


@teacher_router.callback_query(
    AttendanceState.reatt_select_student,
    F.data.startswith('re_a_')
)
async def reatt_mark_absent(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    lesson_id, student_id = int(parts[2]), int(parts[3])
    await _do_reatt(callback, state, lesson_id, student_id, 'absent', 0)


@teacher_router.callback_query(
    AttendanceState.reatt_select_student,
    F.data.startswith('re_l_')
)
async def reatt_mark_late(callback: CallbackQuery, state: FSMContext):
    """Kech qoldi — daqiqa kiritishni so'raymiz."""
    parts = callback.data.split('_')
    lesson_id, student_id = int(parts[2]), int(parts[3])

    from academy.models import Student
    student = await sync_to_async(Student.objects.get)(id=student_id)

    await state.update_data(
        reatt_lesson_id=lesson_id,
        reatt_student_id=student_id,
        reatt_student_name=student.full_name,
    )
    await state.set_state(AttendanceState.entering_late_min)

    await callback.message.answer(
        f"⏰ *{student.full_name}* — kech qoldi\n\n"
        f"Necha daqiqa kech qoldi? (faqat raqam kiriting)\n"
        f"Masalan: *15*",
        parse_mode='Markdown'
    )
    await callback.answer()


@teacher_router.message(AttendanceState.entering_late_min)
async def reatt_save_late_minutes(message: Message, state: FSMContext):
    """Daqiqani qabul qilib, davomatni yangilaymiz."""
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("❗ Faqat raqam kiriting (masalan: 15)")
        return

    late_min = int(text)
    if late_min <= 0 or late_min > 180:
        await message.answer("❗ Daqiqa 1 dan 180 gacha bo'lishi kerak.")
        return

    data = await state.get_data()
    lesson_id  = data['reatt_lesson_id']
    student_id = data['reatt_student_id']
    name       = data['reatt_student_name']

    await _do_reatt(message, state, lesson_id, student_id, 'late', late_min)


async def _do_reatt(trigger, state: FSMContext, lesson_id: int, student_id: int,
                    status: str, late_minutes: int):
    """Attendance'ni yangilash va o'quvchiga xabar."""
    from academy.models import Attendance, Student

    att, _ = await sync_to_async(Attendance.objects.update_or_create)(
        student_id=student_id,
        lesson_id=lesson_id,
        defaults={'status': status, 'late_minutes': late_minutes}
    )

    student = await sync_to_async(Student.objects.get)(id=student_id)

    icons = {'present': '✅', 'late': '⏰', 'absent': '❌'}
    labels = {'present': 'Keldi', 'late': 'Kech qoldi', 'absent': 'Kelmadi'}
    icon  = icons[status]
    label = labels[status]

    late_str = f" — {late_minutes} daqiqa kechikish" if late_minutes else ""
    reply_text = f"{icon} *{student.full_name}* — {label}{late_str}\n✅ Yangilandi"

    # Bot instance olish
    bot = trigger.bot if hasattr(trigger, 'bot') else trigger.message.bot if hasattr(trigger, 'message') else None

    # O'quvchiga xabar
    if bot:
        await _notify_student_attendance(student, status, bot, late_minutes)

    await state.clear()

    if isinstance(trigger, CallbackQuery):
        await trigger.message.answer(reply_text, parse_mode='Markdown')
        await trigger.answer()
    else:
        await trigger.answer(reply_text, parse_mode='Markdown')


# ─── Post-davomat tugmalari ───────────────────────────────────────────────────

async def _remove_buttons(callback: CallbackQuery, done_text: str):
    """Tugmalarni olib tashlash va xabarni yangilash."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        current = callback.message.text or ""
        await callback.message.edit_text(current + f"\n\n{done_text}")
    except Exception:
        pass


@teacher_router.callback_query(F.data.startswith('post_pay_'))
async def post_pay_reminder(callback: CallbackQuery):
    """Guruh qarzdorlariga to'lov eslatmasi."""
    lesson_id = int(callback.data.split('_')[-1])
    await callback.answer("⏳ Eslatmalar yuborilmoqda...")

    # Tugmalarni darhol olib tashlaymiz
    await _remove_buttons(callback, "💳 _To'lov eslatmalari yuborildi_")

    from academy.models import Lesson, Student, Payment
    lesson = await sync_to_async(
        lambda: Lesson.objects.select_related('schedule__group').get(id=lesson_id)
    )()
    group = lesson.schedule.group

    students = await sync_to_async(
        lambda: list(Student.objects.filter(group=group, is_active=True))
    )()

    sent = 0
    for student in students:
        if not student.telegram_id:
            continue
        debts = await sync_to_async(
            lambda s=student: list(
                Payment.objects.filter(student=s, status__in=['pending', 'overdue'])
                .order_by('due_date')
            )
        )()
        if not debts:
            continue
        p = debts[0]
        try:
            await callback.bot.send_message(
                student.telegram_id,
                f"💳 Salom, *{student.full_name}*!\n\n"
                f"To'lov haqida eslatma:\n"
                f"📅 Muddat: *{p.due_date.strftime('%d.%m.%Y')}*\n"
                f"💰 Miqdor: *{p.amount:,.0f} so'm*\n\n"
                f"Iltimos, o'z vaqtida to'lang! 🙏",
                parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            pass

    await callback.message.answer(f"💳 {sent} ta qarzdorga to'lov eslatmasi yuborildi.")


@teacher_router.callback_query(F.data.startswith('post_absent_'))
async def post_absent_notify(callback: CallbackQuery):
    """Kelmaganlarga qo'shimcha xabar."""
    lesson_id = int(callback.data.split('_')[-1])
    await callback.answer("⏳ Xabarlar yuborilmoqda...")

    await _remove_buttons(callback, "📢 _Kelmaganlarga xabar yuborildi_")

    from academy.models import Lesson, Attendance
    lesson = await sync_to_async(
        lambda: Lesson.objects.select_related('schedule__group').get(id=lesson_id)
    )()

    absent_list = await sync_to_async(
        lambda: list(
            Attendance.objects.filter(lesson=lesson, status='absent')
            .select_related('student')
        )
    )()

    sent = 0
    for att in absent_list:
        student = att.student
        if not student.telegram_id:
            continue
        try:
            await callback.bot.send_message(
                student.telegram_id,
                f"📢 Salom, *{student.full_name}*!\n\n"
                f"Bugun *{lesson.date.strftime('%d.%m.%Y')}* darsga kelmaganingiz "
                f"qayd etildi. ❌\n\n"
                f"Sababini o'qituvchi yoki administrator bilan bog'laning.",
                parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            pass

    count = len(absent_list)
    await callback.message.answer(
        f"📢 {count} ta kelmaganidan {sent} tasiga xabar yuborildi."
    )


@teacher_router.callback_query(F.data.startswith('post_topic_'))
async def post_topic_start(callback: CallbackQuery, state: FSMContext):
    """Dars mavzusini yozish."""
    lesson_id = int(callback.data.split('_')[-1])
    await callback.answer()

    await _remove_buttons(callback, "📝 _Mavzu yozilmoqda..._")

    await state.update_data(topic_lesson_id=lesson_id)
    await state.set_state(AttendanceState.writing_topic)

    await callback.message.answer(
        "📝 *Bugungi dars mavzusini yozing:*\n"
        "_(Masalan: Kvadrat tenglamalar. Viyet teoremasi)_",
        parse_mode='Markdown'
    )


@teacher_router.message(AttendanceState.writing_topic)
async def save_lesson_topic(message: Message, state: FSMContext):
    data = await state.get_data()
    lesson_id = data.get('topic_lesson_id')
    topic = message.text.strip()
    await state.clear()

    if not lesson_id:
        await message.answer("❌ Xatolik yuz berdi.")
        return

    from academy.models import Lesson
    lesson = await sync_to_async(Lesson.objects.get)(id=lesson_id)
    lesson.topic = topic
    await sync_to_async(lesson.save)(update_fields=['topic'])

    await message.answer(
        f"✅ *Mavzu saqlandi!*\n\n"
        f"📝 {topic}",
        parse_mode='Markdown'
    )


# ─── O'qituvchi: Guruhlarim ───────────────────────────────────────────────────

@teacher_router.message(F.text == "👥 Guruhlarim")
@teacher_router.message(Command('guruhlar'))
async def cmd_groups(message: Message):
    tg_id = message.from_user.id
    if not await _is_teacher(tg_id):
        return

    teacher = await _get_teacher(tg_id)

    from academy.models import Group, Student
    groups = await sync_to_async(
        lambda: list(Group.objects.filter(teacher=teacher, is_active=True))
    )()

    if not groups:
        await message.answer("Sizga guruh biriktirilmagan.")
        return

    text = "👥 *Sizning guruhlaringiz:*\n\n"
    for g in groups:
        count = await sync_to_async(Student.objects.filter(group=g, is_active=True).count)()
        text += (
            f"🏫 *{g.name}*\n"
            f"   O'quvchilar: {count} ta\n"
            f"   Oylik to'lov: {g.monthly_fee:,.0f} so'm\n\n"
        )

    await message.answer(text, parse_mode='Markdown')


# ─── O'qituvchi: Statistika ───────────────────────────────────────────────────

@teacher_router.message(F.text == "📊 O'qituvchi statistikasi")
async def cmd_teacher_stats(message: Message):
    tg_id = message.from_user.id
    if not await _is_teacher(tg_id):
        return

    teacher = await _get_teacher(tg_id)

    from academy.models import Group, Student
    from django.db.models import Count, Q

    groups = await sync_to_async(
        lambda: list(Group.objects.filter(teacher=teacher, is_active=True))
    )()

    text = "📊 *Statistika:*\n\n"
    for g in groups:
        count = await sync_to_async(Student.objects.filter(group=g, is_active=True).count)()
        debtors = await sync_to_async(
            lambda grp=g: Student.objects.filter(
                group=grp, is_active=True, payments__status='overdue'
            ).distinct().count()
        )()
        text += (
            f"🏫 *{g.name}*\n"
            f"   👥 O'quvchilar: {count} ta\n"
            f"   🔴 Qarzdorlar: {debtors} ta\n\n"
        )

    if not groups:
        text += "_Guruhlar yo'q_"

    await message.answer(text, parse_mode='Markdown')
