# blog/models.py

from django.db import models
from django.contrib.auth import get_user_model  # ⚠️ qo'shamiz

User = get_user_model()                        # ⚠️ haqiqiy User klassini olamiz

class Category(models.Model):
    name        = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name

class Post(models.Model):
    ROLE_CHOICES = User.ROLE_CHOICES

    title       = models.CharField(max_length=100)
    content     = models.TextField()
    category    = models.ForeignKey(Category, on_delete=models.CASCADE)
    video       = models.FileField(upload_to='videos/', blank=True, null=True)
    ROLE_CHOICES = User.ROLE_CHOICES
    role        = models.CharField(
                    max_length=20,
                    choices=ROLE_CHOICES,
                    default='офисный-персонал',
                  )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def view_count(self):
        """Videoni ko'rishlar soni"""
        return self.videoview_set.count()
    
    def unique_viewers_count(self):
        """Nechta foydalanuvchi ko'rgani"""
        return self.videoview_set.values('user').distinct().count()

class VideoView(models.Model):
    """Video ko'rishlarni kuzatish uchun model"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        # Bir foydalanuvchi bir videoni ko'p marta ko'rishi mumkin
        ordering = ['-viewed_at']
    
    def __str__(self):
        return f"{self.user.username} watched {self.post.title} at {self.viewed_at}"

class Test(models.Model):
    """Foydalanuvchi rollari uchun testlar"""
    TYPE_KNOWLEDGE = 'knowledge'
    TYPE_SAFETY = 'safety'
    TYPE_EXAM = 'exam'
    TYPE_PRACTICE = 'practice'
    TYPE_DAILY = 'daily'
    TYPE_CHOICES = [
        (TYPE_KNOWLEDGE, 'Bilim testi'),
        (TYPE_SAFETY, 'Xavfsizlik'),
        (TYPE_EXAM, 'Imtihon'),
        (TYPE_PRACTICE, 'Mashq / trening'),
        (TYPE_DAILY, 'Kunlik test'),
    ]

    title = models.CharField(max_length=200, verbose_name="Test nomi")
    description = models.TextField(verbose_name="Test tavsifi")
    test_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_KNOWLEDGE,
        verbose_name="Test turi",
        help_text="Testning maqsadi / kategoriyasi",
    )
    role = models.CharField(
        max_length=20,
        choices=User.ROLE_CHOICES,
        verbose_name="Foydalanuvchi roli"
    )
    time_limit = models.IntegerField(default=30, verbose_name="Vaqt chegarasi (daqiqa)")
    passing_score = models.IntegerField(default=70, verbose_name="O'tish bali (%)")
    questions_per_attempt = models.PositiveIntegerField(
        default=30,
        verbose_name="Har urinishda savollar soni",
        help_text="Savol bankidan tasodifiy shuncha ta savol olinadi (bank kattaroq bo‘lsa). Kamida 1.",
    )
    certificate_category = models.ForeignKey(
        'blog.Category',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='retest_tests',
        verbose_name="Sertifikat kategoriyasi",
        help_text="Test o‘tilsa shu kategoriya sertifikati beriladi/yangilanadi.",
    )
    certificate_validity_days = models.PositiveIntegerField(
        default=365,
        verbose_name="Sertifikat amal muddati (kun)",
        help_text="Qayta testdan o‘tgach sertifikat shuncha kunga uzaytiriladi.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    is_mandatory = models.BooleanField(default=False, verbose_name="Majburiy")
    deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name="Topshirish muddati",
        help_text="Shu sanagacha topshirish kerak (ixtiyoriy)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_overdue(self):
        if not self.deadline:
            return False
        from django.utils import timezone
        return timezone.localdate() > self.deadline

    @property
    def days_until_deadline(self):
        if not self.deadline:
            return None
        from django.utils import timezone
        return (self.deadline - timezone.localdate()).days
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Test"
        verbose_name_plural = "Testlar"
    
    def __str__(self):
        return self.title
    
    def get_total_questions(self):
        """Testdagi savollar sonini qaytaradi"""
        return self.questions.count()
    
    def get_random_questions(self, count=None):
        """Savol bankidan tasodifiy to‘plam."""
        n = count if count is not None else self.questions_per_attempt
        return self.questions.order_by('?')[:n]

    def attempt_question_count(self):
        """Urinish uchun olinadigan savollar soni (bankdan kichik bo‘lmasin)."""
        total = self.get_total_questions()
        n = max(1, self.questions_per_attempt or 30)
        if total <= 0:
            return 0
        return min(n, total)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.questions_per_attempt is not None and self.questions_per_attempt < 1:
            raise ValidationError({'questions_per_attempt': 'Kamida 1 ta savol bo‘lishi kerak.'})
        if self.certificate_validity_days is not None and self.certificate_validity_days < 1:
            raise ValidationError({'certificate_validity_days': 'Kamida 1 kun bo‘lishi kerak.'})
    
    def get_valid_questions_count(self):
        """Ishlatishga yaroqli savollar soni (turiga qarab)."""
        valid_count = 0
        for question in self.questions.prefetch_related('options').all():
            if question.question_type == Question.Q_TRUE_FALSE:
                question.ensure_true_false_options()
            if question.is_answerable():
                valid_count += 1
        return valid_count
    
    def has_enough_valid_questions(self, min_count=10):
        """Testda kamida min_count ta to'g'ri savol borligini tekshiradi"""
        return self.get_valid_questions_count() >= min_count

class Question(models.Model):
    """Testlar uchun savollar"""
    Q_SINGLE = 'single'
    Q_MULTI = 'multi'
    Q_TRUE_FALSE = 'true_false'
    Q_SHORT = 'short'
    QUESTION_TYPE_CHOICES = [
        (Q_SINGLE, 'Bitta to‘g‘ri javob'),
        (Q_MULTI, 'Bir nechta to‘g‘ri javob'),
        (Q_TRUE_FALSE, 'Ha / Yo‘q'),
        (Q_SHORT, 'Qisqa yozma javob'),
    ]

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(verbose_name="Savol matni")
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default=Q_SINGLE,
        verbose_name="Savol turi",
    )
    accepted_answers = models.TextField(
        blank=True,
        verbose_name="Qabul qilinadigan javoblar",
        help_text="Faqat qisqa javob uchun: har qatorga bitta to‘g‘ri variant (registr farqi muhim emas).",
    )
    explanation = models.TextField(blank=True, null=True, verbose_name="Javob izohi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['id']
        verbose_name = "Savol"
        verbose_name_plural = "Savollar"
    
    def __str__(self):
        return self.text[:50]
    
    def get_correct_option(self):
        """To'g'ri javob variantini qaytaradi"""
        return self.options.filter(is_correct=True).first()

    def get_correct_options(self):
        return list(self.options.filter(is_correct=True))

    def accepted_answer_list(self):
        lines = []
        for line in (self.accepted_answers or '').splitlines():
            s = line.strip()
            if s:
                lines.append(s)
        return lines

    def ensure_true_false_options(self):
        """Ha/Yo‘q savol uchun 2 ta variant yaratadi (mavjud bo‘lsa tegmaydi)."""
        if self.question_type != self.Q_TRUE_FALSE:
            return
        if self.options.count() >= 2:
            return
        if self.options.exists():
            return
        Option.objects.create(question=self, text='Ha', is_correct=True)
        Option.objects.create(question=self, text='Yo‘q', is_correct=False)

    def is_answerable(self):
        """Savol to‘g‘ri sozlanganmi (testga chiqarish uchun)."""
        if self.question_type == self.Q_SHORT:
            return bool(self.accepted_answer_list())
        if self.question_type == self.Q_TRUE_FALSE:
            return self.options.count() >= 2 and self.options.filter(is_correct=True).exists()
        if self.question_type == self.Q_MULTI:
            return self.options.filter(is_correct=True).count() >= 1 and self.options.count() >= 2
        # single
        return self.options.filter(is_correct=True).exists() and self.options.count() >= 2

class Option(models.Model):
    """Savollar uchun javob variantlari"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255, verbose_name="Variant matni")
    is_correct = models.BooleanField(default=False, verbose_name="To'g'ri variant")
    
    class Meta:
        verbose_name = "Javob varianti"
        verbose_name_plural = "Javob variantlari"
    
    def __str__(self):
        return self.text

class TestResult(models.Model):
    """Foydalanuvchilarning test natijalari"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='test_results')
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='results')
    score = models.FloatField(verbose_name="Ball miqdori")
    percentage = models.FloatField(verbose_name="To'g'ri javoblar foizi")
    is_passed = models.BooleanField(default=False, verbose_name="Test o'tilgan")
    started_at = models.DateTimeField(verbose_name="Boshlangan vaqt")
    completed_at = models.DateTimeField(verbose_name="Yakunlangan vaqt")
    
    class Meta:
        ordering = ['-completed_at']
        verbose_name = "Test natijasi"
        verbose_name_plural = "Test natijalari"
    
    def __str__(self):
        return f"{self.user.username} - {self.test.title} - {self.percentage}%"
    
    def get_duration(self):
        """Testning davomiyligini daqiqalarda qaytaradi"""
        duration = self.completed_at - self.started_at
        return round(duration.total_seconds() / 60, 2)

class UserAnswer(models.Model):
    """Foydalanuvchining savollarga javoblari"""
    test_result = models.ForeignKey(TestResult, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(
        Option, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name="Tanlangan variant",
    )
    selected_option_ids = models.JSONField(
        default=list, blank=True, verbose_name="Tanlangan variantlar (multi)"
    )
    text_answer = models.CharField(
        max_length=500, blank=True, verbose_name="Yozma javob"
    )
    is_correct = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Foydalanuvchi javobi"
        verbose_name_plural = "Foydalanuvchi javoblari"
    
    def __str__(self):
        return f"{self.test_result.user.username} - {self.question.text[:30]}"

    def display_selected(self):
        q = self.question
        if q.question_type == Question.Q_SHORT:
            return self.text_answer or '—'
        ids = set(self.selected_option_ids or [])
        if q.question_type == Question.Q_MULTI and ids:
            texts = [
                o.text for o in q.options.all()
                if o.id in ids or str(o.id) in {str(x) for x in ids}
            ]
            return ', '.join(texts) if texts else '—'
        if self.selected_option_id:
            return self.selected_option.text
        return '—'

    def display_correct(self):
        q = self.question
        if q.question_type == Question.Q_SHORT:
            return ', '.join(q.accepted_answer_list()) or '—'
        if q.question_type == Question.Q_MULTI:
            return ', '.join(o.text for o in q.get_correct_options()) or '—'
        correct = q.get_correct_option()
        return correct.text if correct else '—'

# Document Management Models
class DocumentCategory(models.Model):
    """Document categories for organizing uploaded files"""
    name = models.CharField(max_length=100, verbose_name="Kategoriya nomi")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    icon = models.CharField(max_length=50, default="fas fa-folder", verbose_name="Ikonka")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqt")
    
    class Meta:
        verbose_name = "Hujjat kategoriyasi"
        verbose_name_plural = "Hujjat kategoriyalari"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def documents_count(self):
        """Kategoriyadagi hujjatlar soni"""
        return self.documents.count()

class Document(models.Model):
    """Document model for file uploads with role-based access control"""
    DOCUMENT_TYPES = [
        ('pdf', 'PDF'),
        ('doc', 'Word'),
        ('docx', 'Word'),
        ('xls', 'Excel'),
        ('xlsx', 'Excel'),
        ('ppt', 'PowerPoint'),
        ('pptx', 'PowerPoint'),
        ('txt', 'Text'),
        ('jpg', 'Image'),
        ('jpeg', 'Image'),
        ('png', 'Image'),
        ('gif', 'Image'),
        ('mp4', 'Video'),
        ('avi', 'Video'),
        ('mov', 'Video'),
        ('zip', 'Archive'),
        ('rar', 'Archive'),
        ('other', 'Boshqa'),
    ]
    
    title = models.CharField(max_length=200, verbose_name="Hujjat nomi")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    file = models.FileField(upload_to='documents/', verbose_name="Fayl")
    category = models.ForeignKey(DocumentCategory, on_delete=models.CASCADE, related_name='documents', verbose_name="Kategoriya")
    
    # Role-based access control
    allowed_roles = models.JSONField(default=list, verbose_name="Ruxsat berilgan rollar")
    is_public = models.BooleanField(default=False, verbose_name="Barcha foydalanuvchilar uchun ochiq")
    
    # Metadata
    file_size = models.PositiveIntegerField(blank=True, null=True, verbose_name="Fayl hajmi (bayt)")
    file_type = models.CharField(max_length=10, blank=True, verbose_name="Fayl turi")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Yuklagan foydalanuvchi")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuklangan vaqt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqt")
    
    # Statistics
    download_count = models.PositiveIntegerField(default=0, verbose_name="Yuklab olishlar soni")
    view_count = models.PositiveIntegerField(default=0, verbose_name="Ko'rishlar soni")
    requires_acknowledgment = models.BooleanField(
        default=False,
        verbose_name="Tasdiqlash talab qilinadi",
        help_text="Xodim hujjatni o‘qib, tanishganini tasdiqlashi kerak",
    )
    
    class Meta:
        verbose_name = "Hujjat"
        verbose_name_plural = "Hujjatlar"
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Auto-detect file type from extension
        if self.file and not self.file_type:
            import os
            file_extension = os.path.splitext(self.file.name)[1].lower().lstrip('.')
            self.file_type = file_extension if file_extension in dict(self.DOCUMENT_TYPES) else 'other'
        
        # Auto-calculate file size
        if self.file and not self.file_size:
            try:
                self.file_size = self.file.size
            except:
                pass
        
        super().save(*args, **kwargs)
    
    def get_file_type_display(self):
        """Return human-readable file type"""
        return dict(self.DOCUMENT_TYPES).get(self.file_type, 'Boshqa')
    
    def get_file_size_display(self):
        """Return human-readable file size"""
        if not self.file_size:
            return "Noma'lum"

        size = float(self.file_size)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def can_user_access(self, user):
        """Check if user can access this document"""
        if not user or not getattr(user, 'is_authenticated', False):
            return self.is_public
        if self.is_public:
            return True
        if getattr(user, 'role', None) == 'admin' or getattr(user, 'is_staff', False):
            return True
        if user.role in (self.allowed_roles or []):
            return True
        return False
    
    def increment_view_count(self):
        """Increment view count"""
        self.view_count += 1
        self.save(update_fields=['view_count'])
    
    def increment_download_count(self):
        """Increment download count"""
        self.download_count += 1
        self.save(update_fields=['download_count'])

class DocumentView(models.Model):
    """Track document views for analytics"""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='views')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_views')
    viewed_at = models.DateTimeField(auto_now_add=True, verbose_name="Ko'rilgan vaqt")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")
    
    class Meta:
        verbose_name = "Hujjat ko'rish"
        verbose_name_plural = "Hujjat ko'rishlar"
        ordering = ['-viewed_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.document.title} - {self.viewed_at}"

class DocumentDownload(models.Model):
    """Track document downloads for analytics"""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='downloads')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_downloads')
    downloaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuklab olingan vaqt")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")
    
    class Meta:
        verbose_name = "Hujjat yuklab olish"
        verbose_name_plural = "Hujjat yuklab olishlar"
        ordering = ['-downloaded_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.document.title} - {self.downloaded_at}"


class DocumentAcknowledgment(models.Model):
    """Xodim hujjat bilan tanishganini tasdiqlashi."""
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='acknowledgments', verbose_name="Hujjat"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='document_acknowledgments', verbose_name="Foydalanuvchi"
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True, verbose_name="Tasdiqlangan vaqt")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP manzil")

    class Meta:
        unique_together = ('document', 'user')
        ordering = ['-acknowledged_at']
        verbose_name = "Hujjat tasdiqi"
        verbose_name_plural = "Hujjat tasdiqlari"

    def __str__(self):
        return f"{self.user.username} · {self.document.title}"


class SystemJobLog(models.Model):
    """Avtomatik yangilanish / cron ishlarining jurnali."""

    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_PARTIAL = 'partial'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Ishlamoqda'),
        (STATUS_SUCCESS, 'Muvaffaqiyatli'),
        (STATUS_FAILED, 'Xato'),
        (STATUS_PARTIAL, 'Qisman'),
    ]

    TRIGGER_CRON = 'cron'
    TRIGGER_MANUAL = 'manual'
    TRIGGER_CLI = 'cli'
    TRIGGER_CHOICES = [
        (TRIGGER_CRON, 'Cron'),
        (TRIGGER_MANUAL, 'Admin qo‘lda'),
        (TRIGGER_CLI, 'CLI'),
    ]

    job_name = models.CharField(max_length=80, verbose_name='Ish nomi', db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
        verbose_name='Holat',
    )
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default=TRIGGER_CRON,
        verbose_name='Ishga tushirish',
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Boshlangan')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='Tugagan')
    message = models.TextField(blank=True, verbose_name='Xabar')
    details = models.JSONField(default=dict, blank=True, verbose_name='Tafsilotlar')
    triggered_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='system_jobs',
        verbose_name='Ishga tushirgan',
    )

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Tizim ishi (avto-yangilanish)'
        verbose_name_plural = 'Tizim ishlari (avto-yangilanish)'

    def __str__(self):
        return f'{self.job_name} · {self.get_status_display()} · {self.started_at}'

    @property
    def duration_seconds(self):
        if not self.finished_at:
            return None
        return max(0, (self.finished_at - self.started_at).total_seconds())

