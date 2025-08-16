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
                    default=ROLE_CHOICES[0][0]
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
    title = models.CharField(max_length=200, verbose_name="Test nomi")
    description = models.TextField(verbose_name="Test tavsifi")
    role = models.CharField(
        max_length=20,
        choices=User.ROLE_CHOICES,
        verbose_name="Foydalanuvchi roli"
    )
    time_limit = models.IntegerField(default=30, verbose_name="Vaqt chegarasi (daqiqa)")
    passing_score = models.IntegerField(default=70, verbose_name="O'tish bali (%)")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Test"
        verbose_name_plural = "Testlar"
    
    def __str__(self):
        return self.title
    
    def get_total_questions(self):
        """Testdagi savollar sonini qaytaradi"""
        return self.questions.count()
    
    def get_random_questions(self, count=30):
        """Tasodifiy savollar to'plamini qaytaradi"""
        return self.questions.order_by('?')[:count]
    
    def get_valid_questions_count(self):
        """Logik aloqaga ega bo'lgan savollar sonini qaytaradi"""
        from blog.views import check_question_options_consistency
        valid_count = 0
        for question in self.questions.prefetch_related('options').all():
            options = list(question.options.all())
            if options and question.get_correct_option() and check_question_options_consistency(question.text, options):
                valid_count += 1
        return valid_count
    
    def has_enough_valid_questions(self, min_count=10):
        """Testda kamida min_count ta to'g'ri savol borligini tekshiradi"""
        return self.get_valid_questions_count() >= min_count

class Question(models.Model):
    """Testlar uchun savollar"""
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(verbose_name="Savol matni")
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
    selected_option = models.ForeignKey(Option, on_delete=models.CASCADE)
    is_correct = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Foydalanuvchi javobi"
        verbose_name_plural = "Foydalanuvchi javoblari"
    
    def __str__(self):
        return f"{self.test_result.user.username} - {self.question.text[:30]}"

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
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024.0:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024.0
        return f"{self.file_size:.1f} TB"
    
    def can_user_access(self, user):
        """Check if user can access this document"""
        if self.is_public:
            return True
        if user.role in self.allowed_roles:
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
