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
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Narxi")
    is_free = models.BooleanField(default=True, verbose_name="Bepul")
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
    is_free_preview = models.BooleanField(default=False, verbose_name="Bepul ko'rish uchun")
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
            from courses.views import create_course_certificate
            if not hasattr(self, 'certificate'):
                create_course_certificate(self)
        
        # Если прогресс < 100%, но курс отмечен как завершенный, исправляем
        elif progress_percent < 100 and self.is_completed:
            self.is_completed = False
            self.completed_at = None
            self.save()
        
        return progress_percent


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
    pdf_file = models.FileField(upload_to='certificates/courses/', blank=True, null=True, verbose_name="PDF fayl")
    preview_image = models.ImageField(upload_to='certificates/preview/', blank=True, null=True, verbose_name="Ko'rish rasmi")
    certificate_type = models.CharField(max_length=20, default='course', verbose_name="Sertifikat turi")
    
    class Meta:
        verbose_name = "Kurs sertifikati"
        verbose_name_plural = "Kurs sertifikatlari"
        ordering = ['-issue_date']
    
    def __str__(self):
        return f"{self.enrollment.user.username} - {self.enrollment.course.title} sertifikati"
