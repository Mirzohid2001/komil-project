from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.urls import reverse
import uuid
from django.utils import timezone

User = get_user_model()

class Course(models.Model):
    """Модель курса"""
    DIFFICULTY_CHOICES = [
        ('beginner', 'Boshlang\'ich'),
        ('intermediate', 'O\'rta'),
        ('advanced', 'Yuqori')
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Qoralama'),
        ('published', 'Nashr qilingan'),
        ('archived', 'Arxivlangan')
    ]
    
    title = models.CharField(max_length=200, verbose_name="Kurs nomi")
    slug = models.SlugField(max_length=200, unique=True, verbose_name="Slug")
    description = models.TextField(verbose_name="Tavsif")
    short_description = models.CharField(max_length=255, verbose_name="Qisqa tavsif")
    cover = models.ImageField(upload_to='courses/covers/', blank=True, null=True, verbose_name="Muqova rasmi")
    category = models.ForeignKey('CourseCategory', on_delete=models.CASCADE, related_name='courses', verbose_name="Kategoriya")
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner', verbose_name="Qiyinlik darajasi")
    duration = models.PositiveIntegerField(help_text="Daqiqalardagi taxminiy davomiyligi", verbose_name="Davomiyligi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Holati")
    is_featured = models.BooleanField(default=False, verbose_name="Tavsiya etilgan")
    # Legacy fields: payments are not used in this internal factory LMS.
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Narxi (ishlatilmaydi)")
    is_free = models.BooleanField(default=True, verbose_name="Bepul (ishlatilmaydi)")
    allowed_roles = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Ruxsat berilgan rollar",
        help_text="Bo‘sh ro‘yxat = barcha rollar. Admin har doim ko‘radi.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqti")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Kurs"
        verbose_name_plural = "Kurslar"
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('courses:detail', args=[self.slug])

    def can_user_access(self, user):
        roles = self.allowed_roles or []
        if not roles:
            return True  # Umumiy kurs — mehmon ham ko‘ra oladi
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'role', None) == 'admin':
            return True
        return user.role in roles

    @classmethod
    def published_for_user(cls, user):
        qs = cls.objects.filter(status='published')
        if getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'admin':
            return qs
        # SQLite JSONField __contains ni qo‘llab-quvvatlamaydi — Python filtr
        ids = [
            c.id for c in qs.only('id', 'allowed_roles')
            if c.can_user_access(user)
        ]
        return qs.filter(id__in=ids)
    
    def total_modules(self):
        return self.modules.count()
    
    def total_lessons(self):
        return sum(module.lessons.count() for module in self.modules.all())
    
    def total_duration(self):
        """Kursning umumiy davomiyligi (daqiqalarda)"""
        total = sum(lesson.duration for module in self.modules.all() 
                   for lesson in module.lessons.all())
        return total
    
    def students_count(self):
        """Kursga ro'yxatdan o'tgan talabalar soni"""
        return self.enrollments.count()


class Module(models.Model):
    """Модель модуля (раздела) курса"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules', verbose_name="Kurs")
    title = models.CharField(max_length=200, verbose_name="Modul nomi")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    order = models.PositiveIntegerField(default=0, verbose_name="Tartib raqami")
    
    class Meta:
        ordering = ['order']
        verbose_name = "Modul"
        verbose_name_plural = "Modullar"
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    def total_lessons(self):
        return self.lessons.count()
    
    def total_duration(self):
        """Modulning umumiy davomiyligi (daqiqalarda)"""
        return sum(lesson.duration for lesson in self.lessons.all())


class Lesson(models.Model):
    """Модель урока"""
    LESSON_TYPES = [
        ('video', 'Video dars'),
        ('text', 'Matnli dars'),
        ('quiz', 'Test'),
        ('assignment', 'Vazifa')
    ]
    
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons', verbose_name="Modul")
    title = models.CharField(max_length=200, verbose_name="Dars nomi")
    content = models.TextField(verbose_name="Kontent")
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPES, default='video', verbose_name="Dars turi")
    video_url = models.URLField(blank=True, verbose_name="Video havolasi")
    video_file = models.FileField(upload_to='courses/videos/', blank=True, null=True, verbose_name="Video fayl")
    duration = models.PositiveIntegerField(default=0, help_text="Daqiqalardagi davomiyligi", verbose_name="Davomiyligi")
    order = models.PositiveIntegerField(default=0, verbose_name="Tartib raqami")
    is_free_preview = models.BooleanField(default=False, verbose_name="Yozilmasdan ko'rish mumkin")
    allow_comments = models.BooleanField(default=True, verbose_name="Izohlar ruxsat etilgan")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqti")
    
    class Meta:
        ordering = ['order']
        verbose_name = "Dars"
        verbose_name_plural = "Darslar"
    
    def __str__(self):
        return f"{self.module.course.title} - {self.module.title} - {self.title}"
    
    def get_absolute_url(self):
        return reverse('courses:lesson_detail', args=[
            self.module.course.slug, 
            self.module.id,
            self.id
        ])
    
    @property
    def has_attachments(self):
        """Проверяет, есть ли у урока прикрепленные файлы"""
        return self.attachments.exists()


class LessonAttachment(models.Model):
    """Модель для файлов, прикрепленных к уроку"""
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='attachments', verbose_name="Dars")
    title = models.CharField(max_length=100, verbose_name="Fayl nomi")
    file = models.FileField(upload_to='courses/attachments/', verbose_name="Fayl")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Qo'shilgan vaqti")
    
    class Meta:
        verbose_name = "Dars ilovasi"
        verbose_name_plural = "Dars ilovalari"
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.lesson.title} - {self.title}"


class LessonQuizQuestion(models.Model):
    """Dars ichidagi quiz savoli"""
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name='quiz_questions', verbose_name="Dars"
    )
    text = models.TextField(verbose_name="Savol matni")
    order = models.PositiveIntegerField(default=0, verbose_name="Tartib")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Dars quiz savoli"
        verbose_name_plural = "Dars quiz savollari"

    def __str__(self):
        return self.text[:60]


class LessonQuizOption(models.Model):
    """Dars quiz javob varianti"""
    question = models.ForeignKey(
        LessonQuizQuestion,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name="Savol",
    )
    text = models.CharField(max_length=255, verbose_name="Variant")
    is_correct = models.BooleanField(default=False, verbose_name="To'g'ri")

    class Meta:
        verbose_name = "Dars quiz varianti"
        verbose_name_plural = "Dars quiz variantlari"

    def __str__(self):
        return self.text[:60]


class LessonQuizAttempt(models.Model):
    """Foydalanuvchining dars quiz natijasi"""
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name='quiz_attempts', verbose_name="Dars"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='lesson_quiz_attempts', verbose_name="Foydalanuvchi"
    )
    score = models.PositiveIntegerField(default=0, verbose_name="To'g'ri javoblar")
    total = models.PositiveIntegerField(default=0, verbose_name="Jami savollar")
    percentage = models.FloatField(default=0, verbose_name="Foiz")
    is_passed = models.BooleanField(default=False, verbose_name="O'tdi")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-completed_at']
        verbose_name = "Dars quiz natijasi"
        verbose_name_plural = "Dars quiz natijalari"

    def __str__(self):
        return f"{self.user.username} — {self.lesson.title}: {self.percentage:.0f}%"


class LessonComment(models.Model):
    """Dars izohlari"""
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name='comments', verbose_name="Dars"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='lesson_comments', verbose_name="Foydalanuvchi"
    )
    content = models.TextField(max_length=2000, verbose_name="Izoh matni")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqt")

    class Meta:
        verbose_name = "Dars izohi"
        verbose_name_plural = "Dars izohlari"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.content[:40]}"


class Enrollment(models.Model):
    """Модель записи на курс"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments', verbose_name="Foydalanuvchi")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments', verbose_name="Kurs")
    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name="Ro'yxatdan o'tgan sana")
    is_completed = models.BooleanField(default=False, verbose_name="Yakunlangan")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Yakunlangan sana")
    
    class Meta:
        unique_together = ('user', 'course')
        verbose_name = "Kursga yozilish"
        verbose_name_plural = "Kursga yozilishlar"
    
    def __str__(self):
        return f"{self.user.username} - {self.course.title}"
    
    def progress(self):
        """Kurs bo'yicha progress foizlarda"""
        total_lessons = Lesson.objects.filter(module__course=self.course).count()
        if total_lessons == 0:
            return 0
        
        completed_lessons_count = CompletedLesson.objects.filter(
            enrollment=self,
            user=self.user
        ).count()
        
        # Проверяем соответствие между прогрессом и is_completed
        progress_percent = round((completed_lessons_count / total_lessons) * 100)
        
        # Если прогресс 100%, но курс не отмечен как завершенный, обновляем статус
        if progress_percent == 100 and not self.is_completed:
            self.is_completed = True
            self.completed_at = timezone.now()
            self.save()
            
            # Создаем сертификат о прохождении курса, если его еще нет
            from courses.services import create_course_certificate
            if not CourseCertificate.objects.filter(enrollment=self).exists():
                create_course_certificate(self)

            self.sync_course_assignments()
        
        # Если прогресс < 100%, но курс отмечен как завершенный, исправляем
        elif progress_percent < 100 and self.is_completed:
            self.is_completed = False
            self.completed_at = None
            self.save()
            self.sync_course_assignments()
        
        return progress_percent

    def sync_course_assignments(self):
        """Majburiy kurs topshirig‘ini enrollment holatiga bog‘lash."""
        if self.is_completed:
            CourseAssignment.objects.filter(
                user=self.user, course=self.course, completed_at__isnull=True
            ).update(completed_at=self.completed_at or timezone.now())
        else:
            CourseAssignment.objects.filter(
                user=self.user, course=self.course
            ).update(completed_at=None)


class CompletedLesson(models.Model):
    """Модель для отслеживания пройденных уроков"""
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        related_name='completed_lessons',
        verbose_name='Foydalanuvchi'
    )
    lesson = models.ForeignKey(
        Lesson, 
        on_delete=models.CASCADE,
        related_name='completions',
        verbose_name='Dars'
    )
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='completed_lessons',
        verbose_name='Kursga yozilish'
    )
    completed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Yakunlangan sana'
    )

    class Meta:
        verbose_name = 'Yakunlangan dars'
        verbose_name_plural = 'Yakunlangan darslar'
        unique_together = ('enrollment', 'lesson')
        ordering = ['-completed_at']

    def __str__(self):
        return f"{self.enrollment.user.username} - '{self.lesson.title}' darsini yakunladi"


class CourseCategory(models.Model):
    """Модель категории курсов"""
    name = models.CharField(max_length=100, verbose_name="Kategoriya nomi")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="Slug")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    icon = models.CharField(max_length=50, blank=True, verbose_name="Ikonka kodi")
    
    class Meta:
        verbose_name = "Kurs kategoriyasi"
        verbose_name_plural = "Kurs kategoriyalari"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('courses:category', args=[self.slug])
    
    def courses_count(self):
        return self.courses.count()


class CourseCertificate(models.Model):
    """Модель сертификата о прохождении курса"""
    enrollment = models.OneToOneField(
        Enrollment, 
        on_delete=models.CASCADE, 
        related_name='certificate', 
        verbose_name="Kursga yozilish"
    )
    certificate_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4, verbose_name="Sertifikat ID")
    title = models.CharField(max_length=200, verbose_name="Sertifikat nomi")
    issue_date = models.DateTimeField(auto_now_add=True, verbose_name="Berilgan sana")
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Amal qilish muddati",
        help_text="Bo‘sh bo‘lsa — berilgan kundan 1 yil",
    )
    pdf_file = models.FileField(upload_to='certificates/courses/', blank=True, null=True, verbose_name="PDF fayl")
    preview_image = models.ImageField(upload_to='certificates/preview/', blank=True, null=True, verbose_name="Ko'rish rasmi")
    certificate_type = models.CharField(max_length=20, default='course', verbose_name="Sertifikat turi")
    
    class Meta:
        verbose_name = "Kurs sertifikati"
        verbose_name_plural = "Kurs sertifikatlari"
        ordering = ['-issue_date']
    
    def __str__(self):
        return f"{self.enrollment.user.username} - {self.enrollment.course.title} sertifikati"

    def save(self, *args, **kwargs):
        from datetime import timedelta
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.valid_until:
            base = self.issue_date.date() if self.issue_date else timezone.localdate()
            self.valid_until = base + timedelta(days=365)
            CourseCertificate.objects.filter(pk=self.pk).update(valid_until=self.valid_until)

    @property
    def is_expired(self):
        if not self.valid_until:
            return False
        return timezone.localdate() > self.valid_until


class CourseAssignment(models.Model):
    """Admin xodimga majburiy kursni muddat bilan tayinlaydi."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='course_assignments', verbose_name="Xodim"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignments', verbose_name="Kurs"
    )
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_courses',
        verbose_name="Tayinlagan",
    )
    deadline = models.DateField(verbose_name="Topshirish muddati")
    is_mandatory = models.BooleanField(default=True, verbose_name="Majburiy")
    notes = models.TextField(blank=True, verbose_name="Izoh")
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name="Tayinlangan")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Yakunlangan")

    class Meta:
        unique_together = ('user', 'course')
        ordering = ['deadline', '-assigned_at']
        verbose_name = "Kurs topshirig‘i"
        verbose_name_plural = "Kurs topshiriqlari"

    def __str__(self):
        return f"{self.user.username} → {self.course.title} ({self.deadline})"

    @property
    def is_overdue(self):
        if self.completed_at or not self.deadline:
            return False
        return timezone.localdate() > self.deadline

    def ensure_enrollment(self):
        Enrollment.objects.get_or_create(user=self.user, course=self.course)

    def sync_completion(self):
        enrollment = Enrollment.objects.filter(user=self.user, course=self.course).first()
        if enrollment and enrollment.is_completed:
            if not self.completed_at:
                self.completed_at = enrollment.completed_at or timezone.now()
                CourseAssignment.objects.filter(pk=self.pk).update(completed_at=self.completed_at)
        elif self.completed_at and enrollment and not enrollment.is_completed:
            CourseAssignment.objects.filter(pk=self.pk).update(completed_at=None)
            self.completed_at = None

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating:
            self.ensure_enrollment()


class LessonAssignmentSubmission(models.Model):
    """Amaliy vazifa — fayl yuklash va instruktur tasdiqi."""
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Kutilmoqda'),
        (STATUS_APPROVED, 'Tasdiqlangan'),
        (STATUS_REJECTED, 'Rad etilgan'),
    ]

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name='assignment_submissions', verbose_name="Dars"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='assignment_submissions', verbose_name="Xodim"
    )
    file = models.FileField(upload_to='courses/assignments/', verbose_name="Fayl")
    comment = models.TextField(blank=True, verbose_name="Izoh")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="Holat"
    )
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuborilgan")
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_assignments',
        verbose_name="Tekshirgan",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tekshirilgan")
    reviewer_note = models.TextField(blank=True, verbose_name="Tekshiruvchi izohi")

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = "Vazifa topshirig‘i"
        verbose_name_plural = "Vazifa topshiriqlari"

    def __str__(self):
        return f"{self.user.username} — {self.lesson.title} ({self.get_status_display()})"
