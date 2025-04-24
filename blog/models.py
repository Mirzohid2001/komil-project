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
