from django import forms
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import mark_safe
from django.db import models as db_models
from django.db.models import Count, Q, Sum
from datetime import timedelta

from .models import (
    Teacher, Group, Student, Schedule, Lesson,
    Attendance, Payment, Notification,
    ControlTest, TestResult, Certificate,
    STATUS_CONFIG, get_student_status,
)


# ─── Hafta kunlari formasi ────────────────────────────────────────────────────

DAY_CHOICES = [
    (0, 'Dushanba'),
    (1, 'Seshanba'),
    (2, 'Chorshanba'),
    (3, 'Payshanba'),
    (4, 'Juma'),
    (5, 'Shanba'),
    (6, 'Yakshanba'),
]


class ScheduleForm(forms.ModelForm):
    days_of_week = forms.MultipleChoiceField(
        choices=DAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Hafta kunlari",
    )

    class Meta:
        model = Schedule
        fields = '__all__'

    def clean_days_of_week(self):
        return [int(x) for x in self.cleaned_data['days_of_week']]


class ScheduleInlineForm(forms.ModelForm):
    days_of_week = forms.MultipleChoiceField(
        choices=DAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Hafta kunlari",
    )

    class Meta:
        model = Schedule
        fields = '__all__'

    def clean_days_of_week(self):
        return [int(x) for x in self.cleaned_data['days_of_week']]


# ─── Inlines ──────────────────────────────────────────────────────────────────

class ScheduleInline(admin.StackedInline):
    model = Schedule
    form = ScheduleInlineForm
    extra = 1
    fields = ['days_of_week', 'start_time', 'end_time', 'room']
    verbose_name = "Jadval"
    verbose_name_plural = "Dars jadvali"
    classes = ['collapse']


class StudentInline(admin.TabularInline):
    model = Student
    extra = 0
    fields = ['full_name', 'phone', 'is_active']
    readonly_fields = ['full_name', 'phone']
    can_delete = False
    show_change_link = True
    verbose_name_plural = "O'quvchilar"
    max_num = 0

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_active=True)


class AttendanceInline(admin.StackedInline):
    model = Attendance
    extra = 0
    fields = ['student', 'status', 'note']
    autocomplete_fields = ['student']
    verbose_name = "O'quvchi"
    verbose_name_plural = "Davomat"


class PaymentInline(admin.StackedInline):
    model = Payment
    extra = 0
    fields = ['month', 'amount', 'due_date', 'status', 'paid_date']
    readonly_fields = ['status']
    ordering = ['-month']
    max_num = 12
    verbose_name = "To'lov"
    verbose_name_plural = "To'lovlar"

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('-month')


class TestResultInline(admin.StackedInline):
    model = TestResult
    extra = 0
    fields = ['student', 'score', 'rank', 'note']
    readonly_fields = ['rank']
    autocomplete_fields = ['student']
    verbose_name = "Natija"
    verbose_name_plural = "O'quvchilar ballari"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('student').order_by('rank')


# ─── Teacher ──────────────────────────────────────────────────────────────────

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display  = ['full_name', 'phone', 'is_active']
    search_fields = ['full_name', 'phone']
    list_filter   = ['is_active']
    save_on_top   = True
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('full_name', 'phone', 'telegram_id', 'is_active')
        }),
    )


# ─── Group ────────────────────────────────────────────────────────────────────

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display  = ['name', 'teacher', 'student_count', 'monthly_fee', 'is_active']
    list_filter   = ['is_active', 'teacher']
    search_fields = ['name']
    save_on_top   = True
    list_per_page = 20
    inlines       = [ScheduleInline, StudentInline]
    actions       = ['create_monthly_payments_action']

    fieldsets = (
        (None, {
            'fields': ('name', 'teacher', 'is_active', 'monthly_fee', 'payment_day')
        }),
    )

    def student_count(self, obj):
        return obj.students.filter(is_active=True).count()
    student_count.short_description = "O'quvchi"

    def create_monthly_payments_action(self, request, queryset):
        from datetime import date
        today = date.today()
        month = date(today.year, today.month, 1)
        created = 0
        for group in queryset:
            for student in group.students.filter(is_active=True):
                try:
                    due = date(month.year, month.month, group.payment_day)
                except ValueError:
                    due = date(month.year, month.month, 28)
                _, was_created = Payment.objects.get_or_create(
                    student=student, month=month,
                    defaults={'amount': group.monthly_fee, 'due_date': due}
                )
                if was_created:
                    created += 1
        self.message_user(request, f"✅ {created} ta to'lov yaratildi.", messages.SUCCESS)
    create_monthly_payments_action.short_description = "Bu oy uchun to'lov yaratish"


# ─── Student ──────────────────────────────────────────────────────────────────

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display  = ['full_name', 'phone', 'group', 'total_late_min', 'status_info', 'is_active']
    list_filter   = ['is_active', 'group']
    search_fields = ['full_name', 'phone']
    readonly_fields = ['telegram_id', 'telegram_username', 'registered_at',
                       'status_info', 'total_late_min_detail',
                       'parent_telegram_id', 'parent_telegram_username']
    save_on_top   = True
    list_per_page = 20
    list_select_related = ['group']
    inlines       = [PaymentInline]
    actions       = ['send_payment_reminder', 'deactivate_students']

    fieldsets = (
        ("Shaxsiy", {
            'fields': ('full_name', 'phone', 'birth_date', 'group', 'is_active')
        }),
        ("Holat", {
            'fields': ('status_info', 'total_late_min_detail'),
        }),
        ("Telegram", {
            'fields': ('telegram_id', 'telegram_username', 'registered_at'),
            'classes': ('collapse',),
        }),
        ("Ota-ona", {
            'fields': ('parent_name', 'parent_telegram_id', 'parent_telegram_username'),
            'classes': ('collapse',),
        }),
    )

    def status_info(self, obj):
        key, emoji, label = get_student_status(obj)
        descs = {
            'green':  "Davomat, nazorat va to'lovlar yaxshi",
            'yellow': "Bir ko'rsatkich o'rtacha, e'tibor bering",
            'red':    "Ko'rsatkichlar yomon, gaplashing",
            'black':  "Jiddiy muammolar bor",
        }
        return f"{emoji} {label} — {descs[key]}"
    status_info.short_description = "Holat"

    def total_late_min(self, obj):
        from django.db.models import Sum
        total = obj.attendances.filter(status='late').aggregate(
            t=Sum('late_minutes')
        )['t'] or 0
        if total == 0:
            return "—"
        return f"⏰ {total} daq"
    total_late_min.short_description = "Kechikish"

    def total_late_min_detail(self, obj):
        from django.db.models import Sum, Count
        stats = obj.attendances.filter(status='late').aggregate(
            total_min=Sum('late_minutes'),
            count=Count('id'),
        )
        total = stats['total_min'] or 0
        count = stats['count'] or 0
        if total == 0:
            return "Kechikish qayd etilmagan"
        hours = total // 60
        mins  = total % 60
        time_str = f"{hours} soat {mins} daqiqa" if hours else f"{mins} daqiqa"
        return f"{count} marta kechikkan, jami {time_str}"
    total_late_min_detail.short_description = "Umumiy kechikish"

    def send_payment_reminder(self, request, queryset):
        from bot.utils.notify import bulk_send_sync
        msgs = []
        for s in queryset.filter(telegram_id__isnull=False):
            debts = list(s.payments.filter(status__in=['pending', 'overdue']))
            if debts:
                p = debts[0]
                msgs.append((s.telegram_id,
                    f"Salom, {s.full_name}!\n\n"
                    f"To'lov eslatmasi:\n"
                    f"Muddat: {p.due_date.strftime('%d.%m.%Y')}\n"
                    f"Miqdor: {p.amount:,.0f} so'm\n\n"
                    f"Iltimos, o'z vaqtida to'lang!"
                ))
        count = bulk_send_sync(msgs)
        self.message_user(request, f"✅ {count} ta eslatma yuborildi.", messages.SUCCESS)
    send_payment_reminder.short_description = "To'lov eslatmasi yuborish"

    def deactivate_students(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} ta o'quvchi o'chirildi.", messages.WARNING)
    deactivate_students.short_description = "O'chirilgan deb belgilash"


# ─── Schedule ─────────────────────────────────────────────────────────────────

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    form          = ScheduleForm
    list_display  = ['group', 'days_str', 'start_time', 'end_time', 'room']
    list_filter   = ['group']
    search_fields = ['group__name']
    save_on_top   = True

    fieldsets = (
        (None, {
            'fields': ('group', 'days_of_week', 'start_time', 'end_time', 'room')
        }),
    )

    def days_str(self, obj):
        names = ['Du', 'Se', 'Chor', 'Pay', 'Ju', 'Sha', 'Yak']
        return ' / '.join(names[d] for d in sorted(obj.days_of_week or []))
    days_str.short_description = "Kunlar"


# ─── Lesson ───────────────────────────────────────────────────────────────────

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display  = ['group_name', 'date', 'topic', 'att_summary', 'is_cancelled']
    list_filter   = ['schedule__group', 'date', 'is_cancelled']
    search_fields = ['topic', 'schedule__group__name']
    date_hierarchy = 'date'
    save_on_top   = True
    list_per_page = 20
    list_select_related = ['schedule__group']
    inlines       = [AttendanceInline]
    actions       = ['notify_absent_students']

    fieldsets = (
        (None, {
            'fields': ('schedule', 'date', 'topic', 'is_cancelled', 'note')
        }),
    )

    def group_name(self, obj):
        return obj.schedule.group.name
    group_name.short_description = "Guruh"

    def att_summary(self, obj):
        c = obj.attendances.aggregate(
            p=Count('id', filter=Q(status='present')),
            l=Count('id', filter=Q(status='late')),
            a=Count('id', filter=Q(status='absent')),
        )
        if not (c['p'] + c['l'] + c['a']):
            return '—'
        return f"✅{c['p']} ⏰{c['l']} ❌{c['a']}"
    att_summary.short_description = "Davomat"


# ─── Attendance ───────────────────────────────────────────────────────────────

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ['student', 'group_name', 'lesson_date', 'status', 'late_minutes']
    list_filter   = ['status', 'lesson__schedule__group', 'lesson__date']
    search_fields = ['student__full_name']
    date_hierarchy = 'lesson__date'
    list_per_page  = 25
    list_select_related = ['student', 'lesson__schedule__group']

    def group_name(self, obj):
        return obj.lesson.schedule.group.name
    group_name.short_description = "Guruh"

    def lesson_date(self, obj):
        return obj.lesson.date.strftime('%d.%m.%Y')
    lesson_date.short_description = "Sana"
    lesson_date.admin_order_field = 'lesson__date'


# ─── Payment ──────────────────────────────────────────────────────────────────

MONTHS_UZ = ['', 'Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
              'Iyul', 'Avgust', 'Sentyabr', 'Oktyabr', 'Noyabr', 'Dekabr']

_STATUS_COLORS = {
    'paid':    ('#28a745', 'white', "✅ To'landi"),
    'pending': ('#ffc107', '#333',  '⏳ Kutilmoqda'),
    'overdue': ('#dc3545', 'white', "🔴 Muddati o'tdi"),
    'partial': ('#17a2b8', 'white', '🟡 Qisman'),
}


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    change_list_template = 'admin/academy/payment/change_list.html'

    list_display  = ['student', 'group_name', 'month_str', 'amount_str', 'status_badge', 'due_date_str']
    list_filter   = ['status', 'student__group', 'month']
    search_fields = ['student__full_name', 'student__phone']
    date_hierarchy = 'due_date'
    save_on_top   = True
    list_per_page  = 25
    list_select_related = ['student__group']
    autocomplete_fields = ['student']
    actions       = ['mark_as_paid', 'mark_as_partial', 'send_debt_reminder', 'mark_as_overdue']

    fieldsets = (
        (None, {
            'fields': ('student', 'month', 'amount', 'due_date', 'status')
        }),
        ("To'lov tafsilotlari", {
            'fields': ('paid_amount', 'paid_date', 'note'),
        }),
    )

    # ─── List columns ───────────────────────────────────────────────────────

    def group_name(self, obj):
        return obj.student.group.name if obj.student.group else '—'
    group_name.short_description = "Guruh"
    group_name.admin_order_field = 'student__group__name'

    def month_str(self, obj):
        return f"{MONTHS_UZ[obj.month.month]} {obj.month.year}"
    month_str.short_description = "Oy"
    month_str.admin_order_field = 'month'

    def amount_str(self, obj):
        return f"{obj.amount:,.0f} so'm"
    amount_str.short_description = "Summa"
    amount_str.admin_order_field = 'amount'

    def status_badge(self, obj):
        bg, fg, label = _STATUS_COLORS.get(obj.status, ('#6c757d', 'white', obj.status))
        return mark_safe(
            f'<span style="background:{bg};color:{fg};padding:3px 10px;'
            f'border-radius:12px;font-size:12px;white-space:nowrap;">{label}</span>'
        )
    status_badge.short_description = "Holat"
    status_badge.admin_order_field = 'status'

    def due_date_str(self, obj):
        today = timezone.now().date()
        d = obj.due_date
        label = d.strftime('%d.%m.%Y')
        if obj.status in ('pending', 'overdue') and d < today:
            days = (today - d).days
            return mark_safe(
                f'<span style="color:#dc3545;font-weight:bold;">'
                f'⚠️ {label} ({days} kun kech)</span>'
            )
        if obj.status == 'pending' and (d - today).days <= 3:
            return mark_safe(f'<span style="color:#856404;font-weight:bold;">⏰ {label}</span>')
        return label
    due_date_str.short_description = "Muddat"
    due_date_str.admin_order_field = 'due_date'

    # ─── Changelist view: oylik hisobot yuqorida ko'rinadi ──────────────────

    def changelist_view(self, request, extra_context=None):
        today = timezone.now().date()
        month_start = today.replace(day=1)
        upcoming_cutoff = today + timedelta(days=3)

        stats = []
        total_paid = total_pending = total_overdue = 0

        for group in Group.objects.filter(is_active=True).order_by('name'):
            row = Payment.objects.filter(
                student__group=group, month=month_start
            ).aggregate(
                total_cnt=Count('id'),
                paid_cnt=Count('id', filter=Q(status='paid')),
                pending_cnt=Count('id', filter=Q(status='pending')),
                overdue_cnt=Count('id', filter=Q(status='overdue')),
                paid_sum=Sum('paid_amount', filter=Q(status='paid')),
                pending_sum=Sum('amount', filter=Q(status='pending')),
                overdue_sum=Sum('amount', filter=Q(status='overdue')),
                upcoming_cnt=Count('id', filter=Q(
                    status='pending',
                    due_date__range=[today, upcoming_cutoff],
                )),
            )
            row['group_name'] = group.name
            row['paid_sum']    = row['paid_sum']    or 0
            row['pending_sum'] = row['pending_sum'] or 0
            row['overdue_sum'] = row['overdue_sum'] or 0
            stats.append(row)
            total_paid    += row['paid_sum']
            total_pending += row['pending_sum']
            total_overdue += row['overdue_sum']

        extra_context = extra_context or {}
        extra_context.update({
            'payment_stats':  stats,
            'current_month':  f"{MONTHS_UZ[today.month]} {today.year}",
            'total_paid':     total_paid,
            'total_pending':  total_pending,
            'total_overdue':  total_overdue,
            'total_expected': total_paid + total_pending + total_overdue,
        })
        return super().changelist_view(request, extra_context=extra_context)

    # ─── Admin actions ───────────────────────────────────────────────────────

    def mark_as_paid(self, request, queryset):
        today = timezone.now().date()
        updated = queryset.exclude(status='paid').update(
            status='paid', paid_date=today,
            paid_amount=db_models.F('amount')
        )
        self.message_user(request, f"✅ {updated} ta to'langan deb belgilandi.", messages.SUCCESS)
    mark_as_paid.short_description = "✅ To'liq to'langan deb belgilash"

    def mark_as_partial(self, request, queryset):
        today = timezone.now().date()
        updated = 0
        for p in queryset.exclude(status='paid'):
            if p.paid_amount and p.paid_amount > 0:
                p.status = 'partial'
                p.paid_date = today
                p.save(update_fields=['status', 'paid_date'])
                updated += 1
        if updated:
            self.message_user(request, f"🟡 {updated} ta qisman to'langan deb belgilandi.", messages.SUCCESS)
        else:
            self.message_user(
                request,
                "⚠️ Qisman to'lash uchun avval 'To'langan miqdor' maydonini to'ldiring.",
                messages.WARNING
            )
    mark_as_partial.short_description = "🟡 Qisman to'langan deb belgilash"

    def send_debt_reminder(self, request, queryset):
        from bot.utils.notify import bulk_send_sync
        msgs = []
        for p in queryset.select_related('student', 'student__group'):
            s = p.student
            if s.telegram_id:
                msgs.append((s.telegram_id,
                    f"💳 Salom, *{s.full_name}*!\n\n"
                    f"🏫 Guruh: *{s.group.name if s.group else '—'}*\n"
                    f"💰 Miqdor: *{p.amount:,.0f} so'm*\n"
                    f"📅 Muddat: *{p.due_date.strftime('%d.%m.%Y')}*\n\n"
                    f"Iltimos, imkon qadar tezroq to'lang! 🙏"
                ))
        count = bulk_send_sync(msgs)
        self.message_user(request, f"✅ {count} ta eslatma yuborildi.", messages.SUCCESS)
    send_debt_reminder.short_description = "📩 Eslatma yuborish"

    def mark_as_overdue(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='overdue')
        self.message_user(request, f"🔴 {updated} ta muddati o'tgan deb belgilandi.", messages.WARNING)
    mark_as_overdue.short_description = "🔴 Muddati o'tgan deb belgilash"


# ─── ControlTest ──────────────────────────────────────────────────────────────

@admin.register(ControlTest)
class ControlTestAdmin(admin.ModelAdmin):
    list_display  = ['title', 'group', 'date', 'max_score', 'min_score', 'participant_count']
    list_filter   = ['group', 'date']
    search_fields = ['title', 'group__name']
    date_hierarchy = 'date'
    save_on_top   = True
    list_per_page  = 15
    ordering       = ['-date']
    inlines        = [TestResultInline]
    actions        = ['prepare_results']

    fieldsets = (
        (None, {
            'fields': ('group', 'title', 'date', 'max_score', 'min_score')
        }),
    )

    def participant_count(self, obj):
        return obj.results.count()
    participant_count.short_description = "Ishtirokchi"

    def prepare_results(self, request, queryset):
        created = 0
        for test in queryset:
            for student in Student.objects.filter(group=test.group, is_active=True):
                _, was_created = TestResult.objects.get_or_create(
                    test=test, student=student, defaults={'score': 0}
                )
                if was_created:
                    created += 1
        self.message_user(
            request,
            f"✅ {created} ta qator yaratildi. Endi balllarni kiriting.",
            messages.SUCCESS
        )
    prepare_results.short_description = "Guruh o'quvchilarini ro'yxatga tayyorlash"


# ─── TestResult ───────────────────────────────────────────────────────────────

@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display  = ['student', 'test', 'score', 'rank_str']
    list_filter   = ['test__group', 'test']
    search_fields = ['student__full_name']
    list_per_page  = 25
    save_on_top   = True
    list_select_related = ['student', 'test']
    autocomplete_fields = ['student']
    readonly_fields    = ['rank']

    fieldsets = (
        (None, {
            'fields': ('test', 'student', 'score', 'rank', 'note')
        }),
    )

    def rank_str(self, obj):
        if obj.rank is None:
            return '—'
        medals = {1: '🥇', 2: '🥈', 3: '🥉'}
        medal = medals.get(obj.rank, '')
        return f"{medal} {obj.rank}-o'rin"
    rank_str.short_description = "O'rin"
    rank_str.admin_order_field = 'rank'


# ─── Certificate ──────────────────────────────────────────────────────────────

@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display  = ['grade_str', 'rank_str', 'student', 'test_title', 'score_str', 'issued_date']
    list_filter   = ['grade', 'test_result__test__group']
    search_fields = ['student__full_name']
    list_per_page  = 20
    list_select_related = ['student', 'test_result__test__group']
    ordering       = ['-issued_date', 'rank']

    def test_title(self, obj):
        return obj.test_result.test.title
    test_title.short_description = "Nazorat ishi"

    def grade_str(self, obj):
        grade_emoji = {'A+': '🌟', 'A': '⭐', 'B+': '💫', 'B': '✨', 'C+': '🎖️', 'C': '🎗️'}
        em = grade_emoji.get(obj.grade, '🏅')
        return f"{em} {obj.grade}"
    grade_str.short_description = "Daraja"
    grade_str.admin_order_field = 'grade'

    def rank_str(self, obj):
        medals = {1: '🥇', 2: '🥈', 3: '🥉'}
        return f"{medals.get(obj.rank, '🏅')} {obj.rank}-o'rin"
    rank_str.short_description = "O'rin"
    rank_str.admin_order_field = 'rank'

    def score_str(self, obj):
        r = obj.test_result
        pct = int(r.score / r.test.max_score * 100) if r.test.max_score else 0
        return f"{r.score}/{r.test.max_score} ({pct}%)"
    score_str.short_description = "Ball"


# ─── Notification ─────────────────────────────────────────────────────────────

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ['student', 'get_type_display', 'is_sent', 'created_at']
    list_filter   = ['type', 'is_sent']
    search_fields = ['student__full_name']
    readonly_fields = ['sent_at', 'created_at', 'is_sent']
    list_per_page  = 20
