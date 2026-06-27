from django.core.management.base import BaseCommand
from datetime import date


class Command(BaseCommand):
    help = "Joriy oy uchun barcha faol o'quvchilarga to'lov yozuvlari yaratish"

    def add_arguments(self, parser):
        parser.add_argument(
            '--month', type=str,
            help="Oy (YYYY-MM formatida, standart: joriy oy)"
        )

    def handle(self, *args, **options):
        from academy.models import Student, Payment

        if options['month']:
            year, month = map(int, options['month'].split('-'))
            target_month = date(year, month, 1)
        else:
            today = date.today()
            target_month = date(today.year, today.month, 1)

        students = Student.objects.filter(
            is_active=True, group__isnull=False
        ).select_related('group')

        created = skipped = 0
        for student in students:
            group = student.group
            if not group or group.monthly_fee <= 0:
                continue
            try:
                due = date(target_month.year, target_month.month, group.payment_day)
            except ValueError:
                due = date(target_month.year, target_month.month, 28)

            _, was_created = Payment.objects.get_or_create(
                student=student,
                month=target_month,
                defaults={
                    'amount': group.monthly_fee,
                    'due_date': due,
                    'status': 'pending',
                }
            )
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{target_month.strftime('%Y-%m')} uchun: "
                f"yaratildi={created}, mavjud={skipped}"
            )
        )
