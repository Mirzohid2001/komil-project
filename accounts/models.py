from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta


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
        ('admin', 'Admin'),
        ('офисный-персонал', 'ofis-xodimlari'),
        ('естокада', 'Ishlab-chiqarish'),
        ('Оператор', 'Operator'),
        ('Диспетчер', 'Dispatcher'),
        ('охраник', 'Qorovul'),
        ('уборщик', 'Tozalovchi'),
        ('повар', 'Oshpaz'),
        ('технолог', 'Muhandis'),
        ('сварщик', 'Payvandlovchi'),
        ('электрик', 'Elektromontyor'),
        ('механик', 'Mexanik'),
        ('КИП и А', 'KIP i A'),
        ('склад', 'Sklad'),
        ('слесарь', 'Chilangar'),
        ('temiryo`lchi', 'Temiryo`lchi'),
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
        ('view_video', 'Videoni ko‘rish'),
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
