from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academy', '0006_certificate_grade_min_score'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='parent_telegram_id',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='Ota-ona Telegram ID'),
        ),
        migrations.AddField(
            model_name='student',
            name='parent_telegram_username',
            field=models.CharField(blank=True, max_length=100, verbose_name='Ota-ona Telegram username'),
        ),
        migrations.AddField(
            model_name='student',
            name='parent_name',
            field=models.CharField(blank=True, max_length=200, verbose_name='Ota-ona ismi'),
        ),
    ]
