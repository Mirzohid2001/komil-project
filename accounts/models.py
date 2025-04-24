from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [
        ('админ', 'Админ'),
        ('бухгалтер', 'Бухгалтер'),
        ('естокада',   'Естокада'),
        ('финансист',  'Финансист'),
    ]
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='Бухгалтер'
    )
    
    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class FavoritePost(models.Model):
    """Модель для сохранения избранных постов пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    post = models.ForeignKey('blog.Post', on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-added_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.post.title}"


class UserActivity(models.Model):
    """Модель для отслеживания активности пользователя"""
    ACTIVITY_TYPES = [
        ('login', 'Вход в систему'),
        ('logout', 'Выход из системы'),
        ('view_post', 'Просмотр поста'),
        ('view_video', 'Просмотр видео'),
        ('profile_update', 'Обновление профиля'),
        ('favorite_add', 'Добавление в избранное'),
        ('favorite_remove', 'Удаление из избранного'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    post = models.ForeignKey('blog.Post', on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'User Activities'
    
    def __str__(self):
        return f"{self.user.username} - {self.get_activity_type_display()} - {self.timestamp}"

