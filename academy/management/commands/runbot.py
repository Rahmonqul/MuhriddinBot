import asyncio
import logging
from django.core.management.base import BaseCommand

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)


class Command(BaseCommand):
    help = "Telegram botni ishga tushirish"

    def handle(self, *args, **options):
        from django.conf import settings
        from aiogram import Bot, Dispatcher
        from aiogram.fsm.storage.memory import MemoryStorage

        from bot.handlers.registration import register_router
        from bot.handlers.common import common_router
        from bot.handlers.teacher import teacher_router
        from bot.handlers.announcement import announcement_router
        from bot.handlers.payment_admin import payment_admin_router
        from bot.tasks.scheduler import setup_scheduler

        if not settings.BOT_TOKEN:
            self.stderr.write(self.style.ERROR("BOT_TOKEN .env faylida ko'rsatilmagan!"))
            return

        bot = Bot(token=settings.BOT_TOKEN)
        dp = Dispatcher(storage=MemoryStorage())

        dp.include_router(register_router)
        dp.include_router(announcement_router)
        dp.include_router(payment_admin_router)
        dp.include_router(teacher_router)
        dp.include_router(common_router)

        scheduler = setup_scheduler(bot)

        async def main():
            self.stdout.write(self.style.SUCCESS("✅ Bot ishga tushdi..."))
            scheduler.start()
            try:
                await dp.start_polling(bot)
            finally:
                scheduler.shutdown()
                await bot.session.close()

        asyncio.run(main())
