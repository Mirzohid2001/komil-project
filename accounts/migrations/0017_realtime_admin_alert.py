from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_login_day_attendance'),
    ]

    operations = [
        migrations.CreateModel(
            name='RealtimeAdminAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(
                    choices=[
                        ('reg_started', 'Bot registratsiya boshlandi'),
                        ('reg_pending', 'Tasdiqlash kutilmoqda'),
                    ],
                    db_index=True,
                    max_length=32,
                )),
                ('title', models.CharField(max_length=200)),
                ('body', models.CharField(blank=True, max_length=500)),
                ('link', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'Admin bildirishnoma',
                'verbose_name_plural': 'Admin bildirishnomalar',
                'ordering': ['-id'],
            },
        ),
    ]
