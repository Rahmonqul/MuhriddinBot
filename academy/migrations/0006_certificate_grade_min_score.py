from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academy', '0005_attendance_late_minutes'),
    ]

    operations = [
        migrations.AddField(
            model_name='controltest',
            name='min_score',
            field=models.PositiveSmallIntegerField(
                default=0,
                verbose_name='Minimal ball (sertifikat uchun)',
                help_text="Bu balldan past bo'lganlarga o'rin ham, sertifikat ham berilmaydi",
            ),
        ),
        migrations.AddField(
            model_name='certificate',
            name='grade',
            field=models.CharField(
                max_length=3,
                choices=[
                    ('A+', "A+ (1-3 o'rin)"),
                    ('A',  "A (4-6 o'rin)"),
                    ('B+', "B+ (7-9 o'rin)"),
                    ('B',  "B (10-12 o'rin)"),
                    ('C+', "C+ (13-15 o'rin)"),
                    ('C',  "C (16-18 o'rin)"),
                ],
                verbose_name='Daraja',
                default='A+',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='certificate',
            name='rank',
            field=models.PositiveSmallIntegerField(verbose_name="O'rin"),
        ),
    ]
