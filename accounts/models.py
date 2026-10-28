from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Department(models.Model):
    """Zavod bo‘limi / sex."""
    name = models.CharField(max_length=120, unique=True, verbose_name="Bo‘lim nomi")
    code = models.CharField(max_length=20, blank=True, verbose_name="Kod")

    class Meta:
        ordering = ['name']
        verbose_name = "Bo‘lim"
        verbose_name_plural = "Bo‘limlar"

    def __str__(self):
        return self.name


class User(AbstractUser):
    SHIFT_CHOICES = [
        ('', '—'),
        ('A', 'Smena A'),
        ('B', 'Smena B'),
        ('C', 'Smena C'),
        ('day', 'Kunduzgi'),
        ('night', 'Tungi'),
    ]

    ROLE_CHOICES = [
        ('admin', _('Admin')),
        ('офисный-персонал', _('Office staff')),
        ('естокада', _('Production')),
        ('Оператор', _('Operator')),
        ('Диспетчер', _('Dispatcher')),
        ('охраник', _('Security guard')),
        ('уборщик', _('Cleaner')),
        ('повар', _('Cook')),
        ('технолог', _('Engineer')),
        ('сварщик', _('Welder')),
        ('электрик', _('Electrician')),
        ('механик', _('Mechanic')),
        ('КИП и А', _('Instrumentation')),
        ('склад', _('Warehouse')),
        ('слесарь', _('Fitter')),
        ('temiryo`lchi', _('Railway worker')),
    ]
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='офисный-персонал',
        verbose_name="Foydalanuvchi roli"
    )
    employee_id = models.CharField(
        max_length=40, blank=True, db_index=True, verbose_name="Tabel raqami"
    )
    department = models.ForeignKey(
        'Department',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='employees',
        verbose_name="Bo‘lim",
    )
    shift = models.CharField(
        max_length=10, choices=SHIFT_CHOICES, blank=True, default='', verbose_name="Smena"
    )
    
    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True, verbose_name="Profil rasmi")
    bio = models.TextField(max_length=500, blank=True, verbose_name="Qisqacha ma'lumot")
    phone_number = models.CharField(max_length=20, blank=True, verbose_name="Telefon raqami")
    telegram_id = models.BigIntegerField(
        null=True, blank=True, unique=True, db_index=True,
        verbose_name="Telegram ID",
    )
    telegram_username = models.CharField(
        max_length=64, blank=True, verbose_name="Telegram username",
    )

    experience_points = models.IntegerField(default=0, verbose_name="Tajriba ballari")
    level = models.IntegerField(default=1, verbose_name="Daraja")

    class Meta:
        verbose_name = 'Foydalanuvchi'
        verbose_name_plural = 'Foydalanuvchilar'

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def add_experience(self, points):
        self.experience_points += points
        next_level_threshold = self.level * self.level * 100
        if self.experience_points >= next_level_threshold:
            self.level += 1
            LevelUpEvent.objects.create(
                user=self,
                new_level=self.level
            )
        self.save()


class FavoritePost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites', verbose_name="Foydalanuvchi")
    post = models.ForeignKey('blog.Post', on_delete=models.CASCADE, verbose_name="Post")
    added_at = models.DateTimeField(auto_now_add=True, verbose_name="Qo‘shilgan vaqt")
    
    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-added_at']
        verbose_name = "Sevimli post"
        verbose_name_plural = "Sevimli postlar"
    
    def __str__(self):
        return f"{self.user.username} - {self.post.title}"


class UserActivity(models.Model):
    ACTIVITY_TYPES = [
        ('login', 'Tizimga kirish'),
        ('logout', 'Tizimdan chiqish'),
        ('view_post', 'Postni ko‘rish'),
        ('view_video', 'Material videosi'),
        ('view_lesson_video', 'Kurs videosi'),
        ('view_course', 'Kursni ko‘rish'),
        ('course_enrollment', 'Kursga yozilish'),
        ('profile_update', 'Profilni yangilash'),
        ('favorite_add', 'Sevimlilarga qo‘shish'),
        ('favorite_remove', 'Sevimlilardan o‘chirish'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities', verbose_name="Foydalanuvchi")
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES, verbose_name="Faollik turi")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Vaqti")
    post = models.ForeignKey('blog.Post', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Post")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")
    details = models.JSONField(null=True, blank=True, verbose_name="Qo‘shimcha ma’lumotlar")
    duration = models.PositiveIntegerField(default=0, help_text="Faollik davomiyligi (daqiqalarda)", verbose_name="Davomiyligi")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Foydalanuvchi faolligi"
        verbose_name_plural = 'Foydalanuvchi faolliklari'
    
    def __str__(self):
        return f"{self.user.username} - {self.get_activity_type_display()} - {self.timestamp}"


class LoginDay(models.Model):
    """Foydalanuvchi tizimga kirgan kunlar (attendance)."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='login_days', verbose_name="Foydalanuvchi",
    )
    date = models.DateField(db_index=True, verbose_name="Sana")
    first_login_at = models.DateTimeField(verbose_name="Birinchi kirish")
    login_count = models.PositiveIntegerField(default=1, verbose_name="Kirishlar soni")

    class Meta:
        ordering = ['-date']
        verbose_name = "Kirish kuni"
        verbose_name_plural = "Kirish kunlari"
        constraints = [
            models.UniqueConstraint(fields=['user', 'date'], name='uniq_user_login_day'),
        ]
        indexes = [
            models.Index(fields=['date', 'user']),
        ]

    def __str__(self):
        return f"{self.user.username} · {self.date}"


class Achievement(models.Model):
    ACHIEVEMENT_TYPES = [
        ('videos_watched', 'Videolarni tomosha qilish'),
        ('tests_passed', 'Testlardan o‘tish'),
        ('perfect_score', 'Mukammal natija'),
        ('login_streak', 'Ketma-ket kirishlar'),
        ('category_complete', 'Kategoriya yakunlandi'),
        ('level_reached', 'Darajaga erishildi'),
    ]
    
    name = models.CharField(max_length=100, verbose_name="Nomi")
    description = models.TextField(verbose_name="Tavsif")
    type = models.CharField(max_length=30, choices=ACHIEVEMENT_TYPES, verbose_name="Turi")
    icon = models.ImageField(upload_to='achievement_icons/', verbose_name="Belgi")
    required_value = models.IntegerField(verbose_name="Talab qilinadigan qiymat")
    experience_reward = models.IntegerField(default=50, verbose_name="Tajriba mukofoti")
    is_secret = models.BooleanField(default=False, verbose_name="Yashirin yutuq")
    
    class Meta:
        verbose_name = "Yutuq"
        verbose_name_plural = "Yutuqlar"
    
    def __str__(self):
        return self.name


class UserAchievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='achievements', verbose_name="Foydalanuvchi")
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, verbose_name="Yutuq")
    earned_at = models.DateTimeField(auto_now_add=True, verbose_name="Olingan vaqt")
    current_value = models.IntegerField(default=0, verbose_name="Joriy qiymat")
    
    class Meta:
        unique_together = ('user', 'achievement')
        ordering = ['-earned_at']
        verbose_name = "Foydalanuvchi yutug‘i"
        verbose_name_plural = "Foydalanuvchi yutuqlari"
    
    def __str__(self):
        return f"{self.user.username} - {self.achievement.name}"


class LearningProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='learning_progress', verbose_name="Foydalanuvchi")
    category = models.ForeignKey('blog.Category', on_delete=models.CASCADE, verbose_name="Kategoriya")
    posts_viewed = models.ManyToManyField('blog.Post', related_name='viewed_by_progress', verbose_name="Ko‘rilgan postlar")
    last_viewed = models.DateTimeField(auto_now=True, verbose_name="Oxirgi ko‘rish")
    is_completed = models.BooleanField(default=False, verbose_name="Kategoriya tugallandi")
    
    class Meta:
        unique_together = ('user', 'category')
        verbose_name = "O‘rganish jarayoni"
        verbose_name_plural = "O‘rganish jarayonlari"
    
    def __str__(self):
        return f"{self.user.username} - {self.category.name}"
    
    def completion_percentage(self):
        total_posts = self.category.post_set.count()
        if total_posts == 0:
            return 0
        viewed_posts = self.posts_viewed.count()
        return (viewed_posts / total_posts) * 100


class Certificate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates', verbose_name="Foydalanuvchi")
    category = models.ForeignKey('blog.Category', on_delete=models.CASCADE, verbose_name="Kategoriya")
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="Berilgan sana")
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Amal qilish muddati",
        help_text="Bo‘sh bo‘lsa — berilgan kundan 1 yil",
    )
    certificate_id = models.CharField(max_length=50, unique=True, verbose_name="Sertifikat raqami")
    certificate_file = models.FileField(upload_to='certificates/', null=True, blank=True, verbose_name="Sertifikat fayli")
    
    class Meta:
        ordering = ['-issued_at']
        verbose_name = "Sertifikat"
        verbose_name_plural = "Sertifikatlar"
    
    def __str__(self):
        return f"Sertifikat #{self.certificate_id} - {self.user.username} - {self.category.name}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.valid_until:
            base = self.issued_at.date() if self.issued_at else timezone.localdate()
            self.valid_until = base + timedelta(days=365)
            Certificate.objects.filter(pk=self.pk).update(valid_until=self.valid_until)

    @property
    def is_expired(self):
        if not self.valid_until:
            return False
        return timezone.localdate() > self.valid_until

    @property
    def days_until_expiry(self):
        if not self.valid_until:
            return None
        return (self.valid_until - timezone.localdate()).days


class Notification(models.Model):
    """In-app bildirishnoma (muddat, majburiy test, tizim)."""
    TYPE_CHOICES = [
        ('deadline', 'Muddat eslatmasi'),
        ('overdue', 'Muddati o‘tgan'),
        ('certificate', 'Sertifikat'),
        ('system', 'Tizim'),
        ('document', 'Hujjat'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifications', verbose_name="Foydalanuvchi"
    )
    title = models.CharField(max_length=200, verbose_name="Sarlavha")
    message = models.TextField(verbose_name="Matn")
    notification_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default='system', verbose_name="Turi"
    )
    link = models.CharField(max_length=255, blank=True, verbose_name="Havola")
    is_read = models.BooleanField(default=False, verbose_name="O‘qilgan")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bildirishnoma"
        verbose_name_plural = "Bildirishnomalar"
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class LevelUpEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='level_up_events', verbose_name="Foydalanuvchi")
    previous_level = models.IntegerField(verbose_name="Oldingi daraja")
    new_level = models.IntegerField(verbose_name="Yangi daraja")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Daraja oshirilgan vaqt")
    
    class Meta:
        verbose_name = "Daraja oshirish"
        verbose_name_plural = "Daraja oshirishlar"
    
    def __str__(self):
        return f"{self.user.username} darajasi {self.new_level} ga oshdi"
    
    def save(self, *args, **kwargs):
        if not self.pk:
            self.previous_level = self.new_level - 1
        super().save(*args, **kwargs)


class TelegramBotSettings(models.Model):
    """Singleton — Telegram bot sozlamalari (Admin paneldan)."""
    is_enabled = models.BooleanField(
        default=False,
        verbose_name="Yoqilgan",
        help_text="Login sahifada Telegram tugmasi va webhook ishlashi uchun yoqing.",
    )
    bot_token = models.CharField(
        max_length=255, blank=True, verbose_name="Bot token",
        help_text="@BotFather dan /newbot → token.",
    )
    bot_username = models.CharField(
        max_length=64, blank=True, verbose_name="Bot username",
        help_text="Masalan: IsomerOilBot (@ siz).",
    )
    webhook_secret = models.CharField(
        max_length=128, blank=True, verbose_name="Webhook secret",
        help_text="Tasodifiy maxfiy so‘z. Bo‘sh qoldirsangiz saqlashda avtomatik yaratiladi.",
    )
    admin_chat_ids = models.CharField(
        max_length=500, blank=True, verbose_name="Admin Telegram ID lar",
        help_text="Vergul bilan. Masalan: 123456789,987654321. @userinfobot orqali oling.",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan")

    class Meta:
        verbose_name = "Telegram sozlamalar"
        verbose_name_plural = "Telegram sozlamalar"

    def __str__(self):
        status = 'yoqilgan' if self.is_enabled and self.bot_token else 'o‘chiq'
        name = self.bot_username or '—'
        return f'Telegram bot (@{name}) · {status}'

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.bot_username:
            self.bot_username = self.bot_username.lstrip('@').strip()
        if self.bot_token:
            self.bot_token = self.bot_token.strip()
        if self.admin_chat_ids:
            self.admin_chat_ids = ','.join(
                p.strip() for p in self.admin_chat_ids.split(',') if p.strip()
            )
        generated_secret = False
        if self.is_enabled and self.bot_token and not (self.webhook_secret or '').strip():
            import secrets as _secrets
            self.webhook_secret = _secrets.token_urlsafe(24)
            generated_secret = True
        update_fields = kwargs.get('update_fields')
        if generated_secret and update_fields is not None:
            kwargs['update_fields'] = list(set(list(update_fields) + ['webhook_secret']))
        super().save(*args, **kwargs)

    def ensure_webhook_secret(self) -> str:
        """Webhook uchun secret borligini kafolatlaydi."""
        if (self.webhook_secret or '').strip():
            return self.webhook_secret.strip()
        import secrets as _secrets
        self.webhook_secret = _secrets.token_urlsafe(24)
        self.save(update_fields=['webhook_secret', 'updated_at'])
        return self.webhook_secret

    def delete(self, *args, **kwargs):
        # Singleton — o‘chirishga ruxsat bermaymiz
        return

    @classmethod
    def load(cls) -> 'TelegramBotSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TelegramDialog(models.Model):
    """Telegram bot suhbat holati (registratsiya wizard)."""
    STEP_CHOICES = [
        ('idle', 'Idle'),
        ('full_name', 'FIO'),
        ('employee_id', 'Tabel'),
        ('role', 'Rol'),
        ('phone', 'Telefon'),
    ]

    chat_id = models.BigIntegerField(unique=True, db_index=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    step = models.CharField(max_length=20, choices=STEP_CHOICES, default='idle')
    draft = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram dialog"
        verbose_name_plural = "Telegram dialoglar"

    def __str__(self):
        return f"chat:{self.chat_id} · {self.step}"


class RegistrationRequest(models.Model):
    """Telegram orqali kelgan ro‘yxatdan o‘tish so‘rovi — admin tasdiqlaydi."""
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan'),
    ]

    telegram_id = models.BigIntegerField(db_index=True, verbose_name="Telegram ID")
    telegram_username = models.CharField(max_length=64, blank=True, verbose_name="Telegram")
    full_name = models.CharField(max_length=200, verbose_name="F.I.O.")
    employee_id = models.CharField(max_length=40, blank=True, verbose_name="Tabel raqami")
    role = models.CharField(max_length=20, choices=User.ROLE_CHOICES, verbose_name="Rol")
    phone_number = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending',
        db_index=True, verbose_name="Holat",
    )
    created_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='registration_source', verbose_name="Yaratilgan foydalanuvchi",
    )
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reviewed_registrations', verbose_name="Ko‘rib chiqqan",
    )
    review_note = models.CharField(max_length=255, blank=True, verbose_name="Izoh")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Ko‘rib chiqilgan")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ro‘yxatdan o‘tish so‘rovi"
        verbose_name_plural = "Ro‘yxatdan o‘tish so‘rovlari"
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['telegram_id', 'status']),
        ]

    def __str__(self):
        return f"{self.full_name} · {self.get_status_display()}"


class ComplianceAuditLog(models.Model):
    """Tekshiruv uchun compliance hodisalari jurnali."""
    EVENT_CHOICES = [
        ('course_assigned', 'Kurs tayinlandi'),
        ('course_bulk_assigned', 'Ommaviy kurs tayinlandi'),
        ('course_completed', 'Kurs yakunlandi'),
        ('doc_acknowledged', 'Hujjat tasdiqlandi'),
        ('test_passed', 'Test o‘tdi'),
        ('test_failed', 'Test yiqildi'),
        ('cert_issued', 'Sertifikat berildi'),
        ('cert_renewed', 'Sertifikat yangilandi'),
        ('lesson_completed', 'Dars yakunlandi'),
        ('assignment_approved', 'Vazifa tasdiqlandi'),
        ('registration_requested', 'Registratsiya so‘rovi'),
        ('registration_approved', 'Registratsiya tasdiqlandi'),
        ('registration_rejected', 'Registratsiya rad etildi'),
    ]

    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_actions',
        verbose_name="Amal qilgan",
    )
    subject_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_subjects',
        verbose_name="Xodim",
    )
    event_type = models.CharField(
        max_length=40, choices=EVENT_CHOICES, db_index=True, verbose_name="Hodisa"
    )
    object_type = models.CharField(max_length=60, blank=True, verbose_name="Obyekt turi")
    object_id = models.CharField(max_length=64, blank=True, verbose_name="Obyekt ID")
    message = models.CharField(max_length=500, blank=True, verbose_name="Izoh")
    payload = models.JSONField(default=dict, blank=True, verbose_name="Tafsilotlar")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Vaqt")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Audit jurnal"
        verbose_name_plural = "Audit jurnal"
        indexes = [
            models.Index(fields=['event_type', '-created_at']),
            models.Index(fields=['subject_user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} · {self.created_at:%Y-%m-%d %H:%M}"
