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
