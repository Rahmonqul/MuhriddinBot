from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from asgiref.sync import sync_to_async

from bot.keyboards.reply import admin_keyboard

announcement_router = Router()


def _is_admin(telegram_id: int) -> bool:
    from django.conf import settings
    return telegram_id in settings.ADMIN_TELEGRAM_IDS


class AnnouncementState(StatesGroup):
    selecting_target = State()
    writing_text     = State()


# ─── Boshlash: guruh tanlash ──────────────────────────────────────────────────

@announcement_router.message(F.text == "📢 E'lon yuborish")
async def start_announcement(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    from academy.models import Group
    groups = await sync_to_async(
        lambda: list(Group.objects.filter(is_active=True).order_by('name'))
    )()

    buttons = [
        [InlineKeyboardButton(text="📢 Barcha o'quvchilarga", callback_data="ann_all")]
    ]
    for g in groups:
        count = await sync_to_async(
            lambda grp=g: grp.students.filter(is_active=True).count()
        )()
        buttons.append([
            InlineKeyboardButton(
                text=f"🏫 {g.name} ({count} ta)",
                callback_data=f"ann_group_{g.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="❌ Bekor", callback_data="ann_cancel")])

    await state.set_state(AnnouncementState.selecting_target)
    await message.answer(
        "📢 *E'lon yuborish*\n\nKimga yuborilsin?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='Markdown'
    )


# ─── Guruh / hammaga tanlash ──────────────────────────────────────────────────

@announcement_router.callback_query(AnnouncementState.selecting_target, F.data == "ann_all")
async def select_all(callback: CallbackQuery, state: FSMContext):
    await state.update_data(target='all', target_label="Barcha o'quvchilar")
    await state.set_state(AnnouncementState.writing_text)
    await callback.message.edit_text(
        "✏️ *E'lon matnini yozing:*\n\n"
        "_(Barcha faol o'quvchilarga yuboriladi)_",
        parse_mode='Markdown'
    )
    await callback.answer()


@announcement_router.callback_query(AnnouncementState.selecting_target, F.data.startswith("ann_group_"))
async def select_group(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[-1])
    from academy.models import Group
    group = await sync_to_async(Group.objects.get)(id=group_id)

    await state.update_data(target=f'group_{group_id}', target_label=group.name)
    await state.set_state(AnnouncementState.writing_text)
    await callback.message.edit_text(
        f"✏️ *E'lon matnini yozing:*\n\n"
        f"_({group.name} guruhiga yuboriladi)_",
        parse_mode='Markdown'
    )
    await callback.answer()


@announcement_router.callback_query(F.data == "ann_cancel")
async def cancel_announcement(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ E'lon bekor qilindi.")
    await callback.answer()


# ─── Matn yozish va yuborish ──────────────────────────────────────────────────

@announcement_router.message(AnnouncementState.writing_text)
async def send_announcement(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get('target', 'all')
    target_label = data.get('target_label', "Barcha o'quvchilar")
    await state.clear()

    ann_text = f"📢 *E'lon*\n\n{message.text}"

    from academy.models import Student
    if target == 'all':
        students = await sync_to_async(
            lambda: list(Student.objects.filter(is_active=True).exclude(telegram_id__isnull=True))
        )()
    else:
        group_id = int(target.split("_")[-1])
        students = await sync_to_async(
            lambda: list(
                Student.objects.filter(
                    group_id=group_id, is_active=True
                ).exclude(telegram_id__isnull=True)
            )
        )()

    sent = failed = 0
    for student in students:
        try:
            await message.bot.send_message(
                student.telegram_id, ann_text, parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            failed += 1

    result = (
        f"✅ *E'lon yuborildi!*\n\n"
        f"🎯 Manzil: *{target_label}*\n"
        f"📤 Yuborildi: *{sent}* ta\n"
    )
    if failed:
        result += f"⚠️ Yuborilmadi: *{failed}* ta\n"

    await message.answer(result, parse_mode='Markdown', reply_markup=admin_keyboard())
