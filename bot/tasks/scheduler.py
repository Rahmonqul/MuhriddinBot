from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


def setup_scheduler(bot) -> AsyncIOScheduler:
    from bot.utils.notify import (
        send_schedule_reminders,
        check_birthdays,
        auto_create_monthly_payments,
        send_payment_reminders,
    )

    scheduler = AsyncIOScheduler(timezone='Asia/Tashkent')

    # 00:05 har kuni — joriy oy uchun to'lovlarni avtomatik yaratish
    scheduler.add_job(
        auto_create_monthly_payments,
        CronTrigger(hour=0, minute=5),
        args=[bot],
        id='auto_create_payments',
        replace_existing=True,
    )

    # 09:00 har kuni — tug'ilgan kun tabriglari
    scheduler.add_job(
        check_birthdays,
        CronTrigger(hour=9, minute=0),
        args=[bot],
        id='birthday_check',
        replace_existing=True,
    )

    # 09:10 har kuni — to'lov eslatmalari (kelayotgan + muddati o'tgan)
    scheduler.add_job(
        send_payment_reminders,
        CronTrigger(hour=9, minute=10),
        args=[bot],
        id='payment_reminders',
        replace_existing=True,
    )

    # 20:00 har kuni — ertangi dars eslatmasi
    scheduler.add_job(
        send_schedule_reminders,
        CronTrigger(hour=20, minute=0),
        args=[bot],
        id='schedule_reminders',
        replace_existing=True,
    )

    return scheduler
