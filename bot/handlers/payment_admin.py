import logging
from datetime import date

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from asgiref.sync import sync_to_async

from bot.keyboards.reply import admin_keyboard

logger = logging.getLogger(__name__)
payment_admin_router = Router()

MONTHS_UZ = ['', 'Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
             'Iyul', 'Avgust', 'Sentyabr', 'Oktyabr', 'Noyabr', 'Dekabr']


def _remaining(p: dict) -> int:
    """Payment dict yoki object uchun qolgan summa."""
    if isinstance(p, dict):
        return int((p.get('amount') or 0) - (p.get('paid_amount') or 0))
    return int((p.amount or 0) - (p.paid_amount or 0))


class MarkPayState(StatesGroup):
    entering_amount = State()   # data key: payment_id


async def _is_admin(telegram_id: int) -> bool:
    from academy.models import BotAdmin
    return await sync_to_async(BotAdmin.is_admin)(telegram_id)


# ─── Entry point ─────────────────────────────────────────────────────────────

@payment_admin_router.message(F.text == "💵 To'lov qabul")
async def payment_admin_start(message: Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
        return
    await state.clear()
    await _show_groups(message)


async def _show_groups(message: Message):
    from academy.models import Group, Payment
    groups = await sync_to_async(
        lambda: list(Group.objects.filter(is_active=True).order_by('name'))
    )()

    rows = []
    for g in groups:
        payments = await sync_to_async(
            lambda gp=g: list(Payment.objects.filter(
                student__group=gp, status__in=['pending', 'overdue', 'partial']
            ).values('status', 'amount', 'paid_amount'))
        )()
        if payments:
            remaining = sum(_remaining(p) for p in payments)
            rows.append((g, len(payments), remaining))

    if not rows:
        await message.answer(
            "✅ Hozirda barcha to'lovlar to'langan yoki to'lovlar yo'q.",
            reply_markup=admin_keyboard()
        )
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"🏫 {g.name} — {cnt} ta ({remaining:,.0f} so'm qoldi)",
            callback_data=f"apm_g_{g.pk}"
        )]
        for g, cnt, remaining in rows
    ]
    buttons.append([InlineKeyboardButton(text="❌ Bekor", callback_data="apm_x")])

    await message.answer(
        "💵 *To'lov qabul qilish*\n\nQaysi guruhni tanlaysiz?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


# ─── Group selected → show students ──────────────────────────────────────────

@payment_admin_router.callback_query(F.data.startswith("apm_g_"))
async def cb_group_selected(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer()
        return

    group_id = int(callback.data.split("_")[-1])
    from academy.models import Student, Payment
    from django.db.models import Count

    students = await sync_to_async(
        lambda: list(
            Student.objects.filter(
                group_id=group_id, is_active=True
            ).order_by('full_name')
        )
    )()

    rows = []
    for s in students:
        payments = await sync_to_async(
            lambda st=s: list(Payment.objects.filter(
                student=st, status__in=['pending', 'overdue', 'partial']
            ).values('status', 'amount', 'paid_amount'))
        )()
        if payments:
            remaining = sum(_remaining(p) for p in payments)
            rows.append((s, len(payments), remaining))

    if not rows:
        await callback.message.edit_text("✅ Bu guruhda to'lanmagan to'lov yo'q.")
        await callback.answer()
        return

    buttons = []
    for s, cnt, remaining in rows:
        buttons.append([InlineKeyboardButton(
            text=f"👤 {s.full_name} — {cnt} ta ({remaining:,.0f} so'm qoldi)",
            callback_data=f"apm_s_{s.pk}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="apm_back")])
    buttons.append([InlineKeyboardButton(text="❌ Bekor", callback_data="apm_x")])

    await callback.message.edit_text(
        "👤 *O'quvchi tanlang:*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


# ─── Student selected → show their payments ───────────────────────────────────

@payment_admin_router.callback_query(F.data.startswith("apm_s_"))
async def cb_student_selected(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer()
        return

    student_id = int(callback.data.split("_")[-1])
    from academy.models import Payment

    payments = await sync_to_async(
        lambda: list(
            Payment.objects.filter(
                student_id=student_id,
                status__in=['pending', 'overdue', 'partial'],
            ).select_related('student', 'student__group')
            .order_by('-month')[:6]
        )
    )()

    if not payments:
        await callback.message.edit_text("✅ Bu o'quvchida to'lanmagan to'lov yo'q.")
        await callback.answer()
        return

    student_name = payments[0].student.full_name
    buttons = []
    for p in payments:
        month_label = f"{MONTHS_UZ[p.month.month]} {p.month.year}"
        rem = int(p.amount - (p.paid_amount or 0))
        if p.status == 'pending':
            status_em = '⏳'
        elif p.status == 'overdue':
            status_em = '🔴'
        else:
            status_em = '🟡'
        buttons.append([InlineKeyboardButton(
            text=f"{status_em} {month_label} — {rem:,} so'm qoldi",
            callback_data=f"apm_p_{p.pk}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="apm_back")])
    buttons.append([InlineKeyboardButton(text="❌ Bekor", callback_data="apm_x")])

    await callback.message.edit_text(
        f"💳 *{student_name}* — to'lovni tanlang:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


# ─── Payment selected → show action choices ───────────────────────────────────

@payment_admin_router.callback_query(F.data.startswith("apm_p_"))
async def cb_payment_selected(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer()
        return

    payment_id = int(callback.data.split("_")[-1])
    from academy.models import Payment

    payment = await sync_to_async(
        lambda: Payment.objects.select_related('student', 'student__group').get(pk=payment_id)
    )()

    month_label = f"{MONTHS_UZ[payment.month.month]} {payment.month.year}"
    already_paid = payment.paid_amount or 0
    remaining    = int(payment.amount - already_paid)

    status_labels = {
        'pending': '⏳ Kutilmoqda',
        'overdue': "🔴 Muddati o'tdi",
        'partial': '🟡 Qisman to\'langan',
    }
    status_label = status_labels.get(payment.status, payment.status)

    text = (
        f"💳 *To'lov ma'lumoti:*\n\n"
        f"👤 O'quvchi: *{payment.student.full_name}*\n"
        f"🏫 Guruh: *{payment.student.group.name if payment.student.group else '—'}*\n"
        f"📅 Oy: *{month_label}*\n"
        f"💰 Umumiy summa: *{int(payment.amount):,} so'm*\n"
    )
    if already_paid:
        text += (
            f"✅ To'langan: *{int(already_paid):,} so'm*\n"
            f"⏳ Qolgan: *{remaining:,} so'm*\n"
        )
    text += (
        f"📆 Muddat: *{payment.due_date.strftime('%d.%m.%Y')}*\n"
        f"📊 Holat: *{status_label}*\n\n"
        f"Qanday belgilaysiz?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ To'liq to'landi ({remaining:,} so'm)",
            callback_data=f"apm_full_{payment_id}"
        )],
        [InlineKeyboardButton(
            text="🟡 Qisman to'landi (yangi miqdor kiriting)",
            callback_data=f"apm_part_{payment_id}"
        )],
        [InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"apm_s_{payment.student_id}")],
        [InlineKeyboardButton(text="❌ Bekor", callback_data="apm_x")],
    ])

    await callback.message.edit_text(text, parse_mode='Markdown', reply_markup=kb)
    await callback.answer()


# ─── Mark as fully paid ───────────────────────────────────────────────────────

@payment_admin_router.callback_query(F.data.startswith("apm_full_"))
async def cb_mark_full_paid(callback: CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer()
        return

    payment_id = int(callback.data.split("_")[-1])
    from academy.models import Payment

    payment = await sync_to_async(
        lambda: Payment.objects.select_related('student', 'student__group').get(pk=payment_id)
    )()

    today = date.today()
    payment.status     = 'paid'
    payment.paid_date  = today
    payment.paid_amount = payment.amount
    await sync_to_async(payment.save)(update_fields=['status', 'paid_date', 'paid_amount'])

    student = payment.student
    month_label = f"{MONTHS_UZ[payment.month.month]} {payment.month.year}"

    # O'quvchiga xabar
    if student.telegram_id:
        try:
            await callback.bot.send_message(
                student.telegram_id,
                f"✅ *To'lovingiz qabul qilindi!*\n\n"
                f"🏫 Guruh: *{student.group.name if student.group else '—'}*\n"
                f"📅 Oy: *{month_label}*\n"
                f"💰 Miqdor: *{payment.amount:,.0f} so'm*\n"
                f"📆 Sana: *{today.strftime('%d.%m.%Y')}*\n\n"
                f"Rahmat! 🙏",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning("Student notify failed: %s", e)

    await callback.message.edit_text(
        f"✅ *To'liq to'landi deb belgilandi!*\n\n"
        f"👤 {student.full_name}\n"
        f"📅 {month_label} — {payment.amount:,.0f} so'm\n\n"
        f"O'quvchiga xabar yuborildi.",
        parse_mode='Markdown'
    )
    await callback.answer("✅ To'landi!")
    await state.clear()


# ─── Mark as partial: ask amount ─────────────────────────────────────────────

@payment_admin_router.callback_query(F.data.startswith("apm_part_"))
async def cb_mark_partial_start(callback: CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer()
        return

    payment_id = int(callback.data.split("_")[-1])
    from academy.models import Payment

    payment = await sync_to_async(
        lambda: Payment.objects.select_related('student').get(pk=payment_id)
    )()

    already = int(payment.paid_amount or 0)
    rem     = _remaining(payment)

    await state.set_state(MarkPayState.entering_amount)
    await state.update_data(payment_id=payment_id)

    already_line = f"✅ Avval to'langan: *{already:,} so'm*\n" if already else ""
    await callback.message.edit_text(
        f"🟡 *Qisman to'lash*\n\n"
        f"👤 {payment.student.full_name}\n"
        f"💰 Umumiy summa: *{int(payment.amount):,} so'm*\n"
        f"{already_line}"
        f"⏳ Qolgan summa: *{rem:,} so'm*\n\n"
        f"Bu safar qancha to'landi? (so'mda kiriting):\n"
        f"_Masalan: {rem // 2 or rem}_",
        parse_mode='Markdown'
    )
    await callback.answer()


@payment_admin_router.message(MarkPayState.entering_amount)
async def cb_partial_amount_entered(message: Message, state: FSMContext):
    if not await _is_admin(message.from_user.id):
        return

    text = message.text.replace(' ', '').replace(',', '').replace('.', '')
    if not text.isdigit():
        await message.answer("❌ Raqam kiriting. Masalan: *150000*", parse_mode='Markdown')
        return

    new_amount = int(text)
    data = await state.get_data()
    payment_id = data['payment_id']

    from academy.models import Payment
    payment = await sync_to_async(
        lambda: Payment.objects.select_related('student', 'student__group').get(pk=payment_id)
    )()

    rem = _remaining(payment)
    if new_amount <= 0 or new_amount > rem:
        await message.answer(
            f"❌ Miqdor 0 dan katta va qolgan summa ({rem:,} so'm) dan oshmasligi kerak.",
            parse_mode='Markdown'
        )
        return

    today = date.today()
    old_paid     = int(payment.paid_amount or 0)
    total_paid   = old_paid + new_amount
    new_remaining = int(payment.amount) - total_paid

    if new_remaining <= 0:
        # To'liq to'landi
        payment.status      = 'paid'
        payment.paid_amount = payment.amount
        payment.paid_date   = today
    else:
        payment.status      = 'partial'
        payment.paid_amount = total_paid
        payment.paid_date   = today

    await sync_to_async(payment.save)(update_fields=['status', 'paid_amount', 'paid_date'])

    student = payment.student
    month_label = f"{MONTHS_UZ[payment.month.month]} {payment.month.year}"

    # O'quvchiga xabar
    if student.telegram_id:
        try:
            if payment.status == 'paid':
                student_msg = (
                    f"✅ *To'lovingiz to'liq qabul qilindi!*\n\n"
                    f"🏫 Guruh: *{student.group.name if student.group else '—'}*\n"
                    f"📅 Oy: *{month_label}*\n"
                    f"💰 Jami: *{int(payment.amount):,} so'm*\n"
                    f"📆 Sana: *{today.strftime('%d.%m.%Y')}*\n\nRahmat! 🙏"
                )
            else:
                student_msg = (
                    f"🟡 *Qisman to'lov qabul qilindi!*\n\n"
                    f"🏫 Guruh: *{student.group.name if student.group else '—'}*\n"
                    f"📅 Oy: *{month_label}*\n"
                    f"✅ Bu safar: *{new_amount:,} so'm*\n"
                    f"💵 Jami to'landi: *{total_paid:,} so'm*\n"
                    f"⏳ Qoldi: *{new_remaining:,} so'm*\n\n"
                    f"Qolgan summani ham to'lashni unutmang! 🙏"
                )
            await message.bot.send_message(student.telegram_id, student_msg, parse_mode='Markdown')
        except Exception as e:
            logger.warning("Student notify failed: %s", e)

    await state.clear()
    if payment.status == 'paid':
        result_text = (
            f"✅ *To'liq to'landi!*\n\n"
            f"👤 {student.full_name} — {month_label}\n"
            f"💰 Jami: *{int(payment.amount):,} so'm*"
        )
    else:
        result_text = (
            f"🟡 *Qisman to'landi!*\n\n"
            f"👤 {student.full_name} — {month_label}\n"
            f"✅ Bu safar: *{new_amount:,} so'm*\n"
            f"💵 Jami to'landi: *{total_paid:,} so'm*\n"
            f"⏳ Qoldi: *{new_remaining:,} so'm*"
        )
    await message.answer(result_text, parse_mode='Markdown', reply_markup=admin_keyboard())


# ─── Cancel / Back ───────────────────────────────────────────────────────────

@payment_admin_router.callback_query(F.data == "apm_x")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.")
    await callback.answer()


@payment_admin_router.callback_query(F.data == "apm_back")
async def cb_back(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await _show_groups(callback.message)
