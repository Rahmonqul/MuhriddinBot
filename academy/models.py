from django.db import models
from django.utils import timezone


class Teacher(models.Model):
    telegram_id = models.BigIntegerField(
        unique=True, null=True, blank=True, verbose_name="Telegram ID"
    )
    full_name = models.CharField(max_length=200, verbose_name="To'liq ism")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    is_active = models.BooleanField(default=True, verbose_name="Faol")

    class Meta:
        verbose_name = "O'qituvchi"
        verbose_name_plural = "O'qituvchilar"

    def __str__(self):
        return self.full_name


class Group(models.Model):
    name = models.CharField(max_length=100, verbose_name="Guruh nomi")
    teacher = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='groups', verbose_name="O'qituvchi"
    )
    monthly_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Oylik to'lov (so'm)"
    )
    payment_day = models.PositiveSmallIntegerField(
        default=5, verbose_name="To'lov kuni (oyning nechisi)"
    )
    description = models.TextField(blank=True, verbose_name="Tavsif")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Guruh"
        verbose_name_plural = "Guruhlar"

    def __str__(self):
        return self.name

    def active_student_count(self):
        return self.students.filter(is_active=True).count()
    active_student_count.short_description = "O'quvchilar soni"


class Student(models.Model):
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    telegram_username = models.CharField(
        max_length=100, blank=True, verbose_name="Telegram username"
    )
    full_name = models.CharField(max_length=200, verbose_name="To'liq ism")
    phone = models.CharField(max_length=20, verbose_name="Telefon")
    group = models.ForeignKey(
        Group, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students', verbose_name="Guruh"
    )
    birth_date = models.DateField(null=True, blank=True, verbose_name="Tug'ilgan sana")
    parent_telegram_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="Ota-ona Telegram ID"
    )
    parent_telegram_username = models.CharField(
        max_length=100, blank=True, verbose_name="Ota-ona Telegram username"
    )
    parent_name = models.CharField(
        max_length=200, blank=True, verbose_name="Ota-ona ismi"
    )
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name="Ro'yxatdan o'tgan")

    class Meta:
        verbose_name = "O'quvchi"
        verbose_name_plural = "O'quvchilar"

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        creating = not self.pk
        old_group_id = None
        if not creating:
            old_group_id = (
                Student.objects.filter(pk=self.pk)
                .values_list('group_id', flat=True)
                .first()
            )
        super().save(*args, **kwargs)
        # Guruhga birinchi marta qo'shilganda 3 kunlik to'lov yaratish
        if self.group_id is not None and (creating or old_group_id != self.group_id):
            self._create_first_payment()

    def _create_first_payment(self):
        from datetime import timedelta
        today = timezone.now().date()
        month_start = today.replace(day=1)
        due_date = today + timedelta(days=3)
        if self.group and self.group.monthly_fee:
            Payment.objects.get_or_create(
                student=self,
                month=month_start,
                defaults={
                    'amount': self.group.monthly_fee,
                    'due_date': due_date,
                    'status': 'pending',
                }
            )

    @property
    def has_debt(self):
        return self.payments.filter(status__in=['pending', 'overdue']).exists()

    @property
    def overdue_payments(self):
        return self.payments.filter(status='overdue')


class Schedule(models.Model):
    DAYS = [
        (0, 'Dushanba'),
        (1, 'Seshanba'),
        (2, 'Chorshanba'),
        (3, 'Payshanba'),
        (4, 'Juma'),
        (5, 'Shanba'),
        (6, 'Yakshanba'),
    ]
    DAYS_SHORT = ['Du', 'Se', 'Chor', 'Pay', 'Ju', 'Sha', 'Yak']
    DAYS_FULL  = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE,
        related_name='schedules', verbose_name="Guruh"
    )
    days_of_week = models.JSONField(
        default=list,
        verbose_name="Hafta kunlari"
    )
    start_time = models.TimeField(verbose_name="Boshlanish vaqti")
    end_time = models.TimeField(verbose_name="Tugash vaqti")
    room = models.CharField(max_length=50, blank=True, verbose_name="Xona")

    class Meta:
        verbose_name = "Dars jadvali"
        verbose_name_plural = "Dars jadvallari"
        ordering = ['start_time']

    def days_display(self):
        return ', '.join(self.DAYS_FULL[d] for d in sorted(self.days_of_week))

    def days_short_display(self):
        return '/'.join(self.DAYS_SHORT[d] for d in sorted(self.days_of_week))

    def __str__(self):
        days = self.days_short_display()
        return f"{self.group.name} — {days} {self.start_time.strftime('%H:%M')}"


class Lesson(models.Model):
    schedule = models.ForeignKey(
        Schedule, on_delete=models.CASCADE,
        related_name='lessons', verbose_name="Jadval"
    )
    date = models.DateField(verbose_name="Sana")
    topic = models.CharField(max_length=300, blank=True, verbose_name="Mavzu")
    is_cancelled = models.BooleanField(default=False, verbose_name="Bekor qilindi")
    note = models.TextField(blank=True, verbose_name="Eslatma")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dars"
        verbose_name_plural = "Darslar"
        unique_together = ['schedule', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.schedule.group.name} — {self.date.strftime('%d.%m.%Y')}"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', '✅ Keldi'),
        ('late', '⏰ Kech qoldi'),
        ('absent', '❌ Kelmadi'),
    ]
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='attendances', verbose_name="O'quvchi"
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='attendances', verbose_name="Dars"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="Holat")
    late_minutes = models.PositiveSmallIntegerField(
        default=0, verbose_name="Kechikish (daqiqa)"
    )
    note = models.TextField(blank=True, verbose_name="Izoh")
    marked_at = models.DateTimeField(auto_now_add=True, verbose_name="Belgilangan vaqt")
    notified = models.BooleanField(default=False, verbose_name="Xabarnoma yuborildi")

    class Meta:
        verbose_name = "Davomat"
        verbose_name_plural = "Davomat"
        unique_together = ['student', 'lesson']

    def __str__(self):
        return f"{self.student.full_name} — {self.lesson} — {self.get_status_display()}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', "⏳ Kutilmoqda"),
        ('paid', "✅ To'langan"),
        ('overdue', "🔴 Muddati o'tgan"),
        ('partial', "🟡 Qisman to'langan"),
    ]
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='payments', verbose_name="O'quvchi"
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Miqdor (so'm)"
    )
    paid_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="To'langan miqdor (so'm)"
    )
    due_date = models.DateField(verbose_name="To'lov muddati")
    paid_date = models.DateField(null=True, blank=True, verbose_name="To'langan sana")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending',
        verbose_name="Holat"
    )
    month = models.DateField(verbose_name="To'lov oyi")
    note = models.TextField(blank=True, verbose_name="Izoh")
    reminder_sent = models.BooleanField(default=False, verbose_name="Eslatma yuborildi")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ['-due_date']
        unique_together = ['student', 'month']

    def __str__(self):
        return f"{self.student.full_name} — {self.month.strftime('%Y-%m')} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        today = timezone.now().date()
        if self.status not in ('paid', 'partial') and self.due_date < today:
            self.status = 'overdue'
        super().save(*args, **kwargs)


class ControlTest(models.Model):
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE,
        related_name='tests', verbose_name="Guruh"
    )
    title = models.CharField(max_length=200, verbose_name="Mavzu/Nomi")
    date = models.DateField(verbose_name="Sana")
    max_score = models.PositiveSmallIntegerField(default=100, verbose_name="Maksimal ball")
    min_score = models.PositiveSmallIntegerField(
        default=0, verbose_name="Minimal ball (sertifikat uchun)",
        help_text="Bu balldan past bo'lganlarga o'rin ham, sertifikat ham berilmaydi"
    )

    class Meta:
        verbose_name = "Nazorat ishi"
        verbose_name_plural = "Nazorat ishlari"
        ordering = ['-date']

    def __str__(self):
        return f"{self.group.name} — {self.title} ({self.date.strftime('%d.%m.%Y')})"


_GRADE_RANGES = [
    (range(1, 4),   'A+'),
    (range(4, 7),   'A'),
    (range(7, 10),  'B+'),
    (range(10, 13), 'B'),
    (range(13, 16), 'C+'),
    (range(16, 19), 'C'),
]


def _rank_to_grade(rank):
    if rank is None:
        return None
    for r, g in _GRADE_RANGES:
        if rank in r:
            return g
    return None


class TestResult(models.Model):
    test = models.ForeignKey(
        ControlTest, on_delete=models.CASCADE,
        related_name='results', verbose_name="Nazorat ishi"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='test_results', verbose_name="O'quvchi"
    )
    score = models.PositiveSmallIntegerField(verbose_name="Ball")
    rank = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="O'rin")
    note = models.TextField(blank=True, verbose_name="Izoh")

    class Meta:
        verbose_name = "Test natijasi"
        verbose_name_plural = "Test natijalari"
        unique_together = ['test', 'student']
        ordering = ['rank', '-score']

    def __str__(self):
        return f"{self.student.full_name} — {self.test.title}: {self.score}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        min_score = self.test.min_score

        # Minimal ballga yetmagan o'quvchilarga rank=None
        TestResult.objects.filter(test=self.test, score__lt=min_score).update(rank=None)

        # Minimal ballga yetganlarni ballga qarab o'rinlarga joylashtirish
        eligible_pks = list(
            TestResult.objects
            .filter(test=self.test, score__gte=min_score)
            .order_by('-score', 'pk')
            .values_list('pk', flat=True)
        )
        for i, pk in enumerate(eligible_pks, 1):
            TestResult.objects.filter(pk=pk).update(rank=i)

        # Barcha natijalar uchun sertifikatlarni yangilash
        all_results = list(
            TestResult.objects.filter(test=self.test).select_related('student', 'test')
        )
        for result in all_results:
            grade = _rank_to_grade(result.rank)
            if grade:
                Certificate.objects.update_or_create(
                    test_result=result,
                    defaults={
                        'student': result.student,
                        'rank': result.rank,
                        'grade': grade,
                        'issued_date': result.test.date,
                    }
                )
            else:
                Certificate.objects.filter(test_result=result).delete()


class Certificate(models.Model):
    GRADE_CHOICES = [
        ('A+', "A+ (1-3 o'rin)"),
        ('A',  "A (4-6 o'rin)"),
        ('B+', "B+ (7-9 o'rin)"),
        ('B',  "B (10-12 o'rin)"),
        ('C+', "C+ (13-15 o'rin)"),
        ('C',  "C (16-18 o'rin)"),
    ]
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='certificates', verbose_name="O'quvchi"
    )
    test_result = models.OneToOneField(
        TestResult, on_delete=models.CASCADE,
        related_name='certificate', verbose_name="Test natijasi"
    )
    rank = models.PositiveSmallIntegerField(verbose_name="O'rin")
    grade = models.CharField(max_length=3, choices=GRADE_CHOICES, verbose_name="Daraja")
    issued_date = models.DateField(verbose_name="Berilgan sana")

    class Meta:
        verbose_name = "Sertifikat"
        verbose_name_plural = "Sertifikatlar"
        ordering = ['-issued_date', 'rank']

    def __str__(self):
        grade_emoji = {'A+': '🌟', 'A': '⭐', 'B+': '💫', 'B': '✨', 'C+': '🎖️', 'C': '🎗️'}
        em = grade_emoji.get(self.grade, '🏅')
        return (
            f"{em} {self.grade} — {self.student.full_name} — "
            f"{self.test_result.test.title} ({self.issued_date.strftime('%d.%m.%Y')})"
        )


# ─── Student status hisoblash ─────────────────────────────────────────────────

STATUS_CONFIG = {
    'green':  ('🟢', 'Yaxshi',    '#28a745'),
    'yellow': ('🟡', "O'rta",     '#ffc107'),
    'red':    ('🔴', 'Yomon',     '#dc3545'),
    'black':  ('⚫', 'Juda yomon','#343a40'),
}


def get_student_status(student):
    """
    Davomat, so'nggi nazorat ishi va to'lov holatiga qarab o'quvchi rangini qaytaradi.
    Returns: (key, emoji, label)
    """
    from datetime import date, timedelta
    from django.db.models import Count, Q as DQ

    from django.db.models import Sum

    thirty_ago = date.today() - timedelta(days=30)
    att = student.attendances.filter(lesson__date__gte=thirty_ago).aggregate(
        total=Count('id'),
        present=Count('id', filter=DQ(status__in=['present', 'late'])),
        late_min_sum=Sum('late_minutes'),
    )
    total = att['total']
    att_pct = (att['present'] / total * 100) if total > 0 else 100
    total_late_min = att['late_min_sum'] or 0

    last_result = (
        student.test_results
        .select_related('test')
        .order_by('-test__date')
        .first()
    )
    test_pct = (last_result.score / last_result.test.max_score * 100) if last_result else 100

    overdue_count = student.payments.filter(status='overdue').count()
    has_pending = student.payments.filter(status='pending').exists()

    # Kechikish daqiqalari: 30dan oshsa sariq, 90dan oshsa qizil omil
    late_factor = (
        'black' if total_late_min >= 180 else
        'red'   if total_late_min >= 90  else
        'yellow' if total_late_min >= 30 else
        'green'
    )

    if overdue_count >= 2 or att_pct < 40 or test_pct < 30 or late_factor == 'black':
        key = 'black'
    elif overdue_count >= 1 or att_pct < 60 or test_pct < 50 or late_factor == 'red':
        key = 'red'
    elif has_pending or att_pct < 80 or test_pct < 70 or late_factor == 'yellow':
        key = 'yellow'
    else:
        key = 'green'

    emoji, label, _ = STATUS_CONFIG[key]
    return key, emoji, label


class Notification(models.Model):
    TYPE_CHOICES = [
        ('payment_reminder', "To'lov eslatmasi"),
        ('payment_overdue', "To'lov muddati o'tdi"),
        ('schedule_reminder', "Dars eslatmasi"),
        ('attendance_absent', "Davomat — kelmadi"),
        ('attendance_late', "Davomat — kech qoldi"),
        ('general', "Umumiy xabar"),
    ]
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name='notifications', verbose_name="O'quvchi"
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, verbose_name="Turi")
    message = models.TextField(verbose_name="Xabar matni")
    is_sent = models.BooleanField(default=False, verbose_name="Yuborildi")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Yuborilgan vaqt")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Xabarnoma"
        verbose_name_plural = "Xabarnomalar"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.full_name} — {self.get_type_display()}"
