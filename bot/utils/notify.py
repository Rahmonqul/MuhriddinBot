import asyncio
import calendar
import logging
from datetime import date, timedelta
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


# ─── Sync helpers (called from Django admin) ─────────────────────────────────

def bulk_send_sync(messages: list[tuple[int, str]]) -> int:
    """
    Send multiple Telegram messages synchronously (for admin actions).
    messages: list of (telegram_id, text)
    Returns count of successfully sent messages.
    """
    if not messages:
        return 0

    from django.conf import settings
    from aiogram import Bot

    async def _send():
        bot = Bot(token=settings.BOT_TOKEN)
        count = 0
        for tg_id, text in messages:
            try:
                await bot.send_message(tg_id, text, parse_mode='Markdown')
                count += 1
            except Exception:
                pass
        await bot.session.close()
        return count

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _send())
                return future.result()
        return loop.run_until_complete(_send())
    except RuntimeError:
        return asyncio.run(_send())


# ─── Async scheduler jobs ────────────────────────────────────────────────────

DAYS_UZ = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
MONTHS_UZ = ['', 'Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
              'Iyul', 'Avgust', 'Sentyabr', 'Oktyabr', 'Noyabr', 'Dekabr']


async def send_schedule_reminders(bot) -> None:
    """Har kuni 20:00 — ertangi dars uchun eslatma."""
    from academy.models import Schedule, Student

    tomorrow = date.today() + timedelta(days=1)
    weekday  = tomorrow.weekday()
    day_name = DAYS_UZ[weekday]

    all_schedules = await sync_to_async(
        lambda: list(Schedule.objects.select_related('group').all())
    )()
    schedules = [s for s in all_schedules if weekday in (s.days_of_week or [])]

    sent = 0
    for schedule in schedules:
        students = await sync_to_async(
            lambda s=schedule: list(Student.objects.filter(group=s.group, is_active=True))
        )()
        room_line = f"🚪 Xona: *{schedule.room}*\n" if schedule.room else ""
        text = (
            f"📚 *Dars eslatmasi!*\n\n"
            f"Ertaga — *{day_name}, {tomorrow.strftime('%d.%m.%Y')}* dars bor:\n\n"
            f"🏫 Guruh: *{schedule.group.name}*\n"
            f"🕐 Vaqt: *{schedule.start_time.strftime('%H:%M')} — {schedule.end_time.strftime('%H:%M')}*\n"
            f"{room_line}"
            f"\nDarsga o'z vaqtida keling! 💪"
        )
        for student in students:
            if not student.telegram_id:
                continue
            try:
                await bot.send_message(student.telegram_id, text, parse_mode='Markdown')
                sent += 1
            except Exception:
                pass

    logger.info("Dars eslatmasi: %d ta o'quvchiga yuborildi (%s)", sent, day_name)


async def check_birthdays(bot) -> None:
    """Har kuni 9:00 — bugun tug'ilgan o'quvchilarni tabriklaymiz."""
    from academy.models import Student

    today = date.today()
    students = await sync_to_async(
        lambda: list(
            Student.objects.filter(
                is_active=True,
                birth_date__month=today.month,
                birth_date__day=today.day,
            ).exclude(telegram_id__isnull=True)
        )
    )()

    sent = 0
    for student in students:
        try:
            await bot.send_message(
                student.telegram_id,
                f"🎂 Hurmatli *{student.full_name}*!\n\n"
                f"🎉 *Tug'ilgan kuningiz muborak!* 🎊\n\n"
                f"Sizga baxt, sog'lik, muvaffaqiyat\n"
                f"va yangi-yangi yutuqlar tilaymiz! 🌟\n\n"
                f"— *MathAcademy* jamoasi 💙",
                parse_mode='Markdown'
            )
            sent += 1
        except Exception:
            pass

    if sent:
        logger.info("Tug'ilgan kun: %d ta o'quvchi tabriqlandi", sent)


async def auto_create_monthly_payments(bot) -> None:
    """
    Har kuni: joriy oy uchun oylik to'lovlarni avtomatik yaratish.
    Guruhda payment_day belgilangan bo'lsa, o'sha kun due_date bo'ladi.
    """
    from academy.models import Student, Payment

    today = date.today()
    month_start = today.replace(day=1)
    created_count = 0

    students = await sync_to_async(
        lambda: list(
            Student.objects.filter(
                is_active=True,
                group__isnull=False,
                group__monthly_fee__gt=0,
            ).select_related('group')
        )
    )()

    for student in students:
        group = student.group
        last_day = calendar.monthrange(today.year, today.month)[1]
        pay_day = min(group.payment_day or 15, last_day)
        due_date = today.replace(day=pay_day)

        _, created = await sync_to_async(Payment.objects.get_or_create)(
            student=student,
            month=month_start,
            defaults={
                'amount': group.monthly_fee,
                'due_date': due_date,
                'status': 'pending',
            }
        )
        if created:
            created_count += 1

    if created_count:
        logger.info("Oylik to'lovlar: %d ta yangi to'lov yaratildi (%s)", created_count, month_start)


async def send_payment_reminders(bot) -> None:
    """
    Har kuni 9:00 — to'lov eslatmalari:
      1) Muddati o'tgan pending → overdue qilish
      2) Kelayotgan 3 kun ichida to'lovlar uchun kunlik eslatma
      3) Muddati o'tgan to'lovlar uchun kunlik eslatma (max 14 kun)
    """
    from academy.models import Payment

    today = date.today()

    # 1. Muddati o'tgan pending → overdue
    await sync_to_async(
        lambda: Payment.objects.filter(status='pending', due_date__lt=today).update(status='overdue')
    )()

    # 2. Kelayotgan to'lovlar: bugundan 3 kungacha
    upcoming = await sync_to_async(
        lambda: list(
            Payment.objects.filter(
                status='pending',
                due_date__range=[today, today + timedelta(days=3)],
                student__telegram_id__isnull=False,
            ).select_related('student', 'student__group')
        )
    )()

    for payment in upcoming:
        student = payment.student
        days_left = (payment.due_date - today).days
        if days_left == 0:
            urgency = "🚨 *Bugun oxirgi kun!*"
        elif days_left == 1:
            urgency = "⚠️ Ertaga muddat tugaydi — 1 kun qoldi"
        elif days_left == 2:
            urgency = "⏰ 2 kun qoldi"
        else:
            urgency = f"⏰ {days_left} kun qoldi"

        student_text = (
            f"💳 *To'lov eslatmasi*\n\n"
            f"Salom, {student.full_name}!\n\n"
            f"🏫 Guruh: *{student.group.name}*\n"
            f"💰 Summa: *{payment.amount:,.0f} so'm*\n"
            f"📅 Muddat: *{payment.due_date.strftime('%d.%m.%Y')}*\n"
            f"{urgency}\n\n"
            f"O'z vaqtida to'lashni unutmang! 🙏"
        )
        if student.telegram_id:
            try:
                await bot.send_message(student.telegram_id, student_text, parse_mode='Markdown')
            except Exception as e:
                logger.debug("Upcoming reminder failed for %s: %s", student.full_name, e)

        if student.parent_telegram_id:
            parent_name = student.parent_name or "Hurmatli ota-ona"
            parent_text = (
                f"💳 *To'lov eslatmasi*\n\n"
                f"Salom, {parent_name}!\n\n"
                f"👤 Farzand: *{student.full_name}*\n"
                f"🏫 Guruh: *{student.group.name}*\n"
                f"💰 Summa: *{payment.amount:,.0f} so'm*\n"
                f"📅 Muddat: *{payment.due_date.strftime('%d.%m.%Y')}*\n"
                f"{urgency}\n\n"
                f"O'z vaqtida to'lashni unutmang! 🙏"
            )
            try:
                await bot.send_message(student.parent_telegram_id, parent_text, parse_mode='Markdown')
            except Exception as e:
                logger.debug("Upcoming reminder (parent) failed for %s: %s", student.full_name, e)

    # 3. Muddati o'tgan to'lovlar (14 kundan oshmaganlar)
    cutoff = today - timedelta(days=14)
    overdue = await sync_to_async(
        lambda: list(
            Payment.objects.filter(
                status='overdue',
                due_date__gte=cutoff,
            ).select_related('student', 'student__group')
        )
    )()

    for payment in overdue:
        student = payment.student
        days_late = (today - payment.due_date).days

        student_text = (
            f"🔴 *Muddati o'tgan to'lov!*\n\n"
            f"Salom, {student.full_name}!\n\n"
            f"🏫 Guruh: *{student.group.name}*\n"
            f"💰 Summa: *{payment.amount:,.0f} so'm*\n"
            f"📅 Muddat: *{payment.due_date.strftime('%d.%m.%Y')}*\n"
            f"({days_late} kun kechikdi)\n\n"
            f"Iltimos, tezroq to'lang yoki administrator bilan bog'laning! ❗"
        )
        if student.telegram_id:
            try:
                await bot.send_message(student.telegram_id, student_text, parse_mode='Markdown')
            except Exception as e:
                logger.debug("Overdue reminder failed for %s: %s", student.full_name, e)

        if student.parent_telegram_id:
            parent_name = student.parent_name or "Hurmatli ota-ona"
            parent_text = (
                f"🔴 *Muddati o'tgan to'lov!*\n\n"
                f"Salom, {parent_name}!\n\n"
                f"👤 Farzand: *{student.full_name}*\n"
                f"🏫 Guruh: *{student.group.name}*\n"
                f"💰 Summa: *{payment.amount:,.0f} so'm*\n"
                f"📅 Muddat: *{payment.due_date.strftime('%d.%m.%Y')}*\n"
                f"({days_late} kun kechikdi)\n\n"
                f"Iltimos, tezroq to'lang yoki administrator bilan bog'laning! ❗"
            )
            try:
                await bot.send_message(student.parent_telegram_id, parent_text, parse_mode='Markdown')
            except Exception as e:
                logger.debug("Overdue reminder (parent) failed for %s: %s", student.full_name, e)

    logger.info(
        "To'lov eslatmalari: %d kelayotgan, %d muddati o'tgan",
        len(upcoming), len(overdue)
    )
