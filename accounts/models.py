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
    
    # Поля для геймификации
    experience_points = models.IntegerField(default=0, verbose_name="Очки опыта")
    level = models.IntegerField(default=1, verbose_name="Уровень")
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    def add_experience(self, points):
        """Добавляет опыт пользователю и повышает уровень при достижении порогов"""
        self.experience_points += points
        
        # Проверка на повышение уровня (формула: уровень^2 * 100)
        next_level_threshold = self.level * self.level * 100
        if self.experience_points >= next_level_threshold:
            self.level += 1
            # Создаем событие повышения уровня
            LevelUpEvent.objects.create(
                user=self,
                new_level=self.level
            )
        
        self.save()


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


# Новые модели для геймификации и прогресса обучения

class Achievement(models.Model):
    """Модель для достижений пользователей"""
    ACHIEVEMENT_TYPES = [
        ('videos_watched', 'Просмотр видео'),
        ('tests_passed', 'Прохождение тестов'),
        ('perfect_score', 'Идеальный результат'),
        ('login_streak', 'Серия входов'),
        ('category_complete', 'Завершение категории'),
        ('level_reached', 'Достижение уровня'),
    ]
    
    name = models.CharField(max_length=100, verbose_name="Название")
    description = models.TextField(verbose_name="Описание")
    type = models.CharField(max_length=30, choices=ACHIEVEMENT_TYPES, verbose_name="Тип")
    icon = models.ImageField(upload_to='achievement_icons/', verbose_name="Иконка")
    required_value = models.IntegerField(verbose_name="Требуемое значение")
    experience_reward = models.IntegerField(default=50, verbose_name="Награда опытом")
    is_secret = models.BooleanField(default=False, verbose_name="Секретное достижение")
    
    def __str__(self):
        return self.name


class UserAchievement(models.Model):
    """Модель для связи пользователя с полученными достижениями"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='achievements')
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True, verbose_name="Получено")
    current_value = models.IntegerField(default=0, verbose_name="Текущее значение")
    
    class Meta:
        unique_together = ('user', 'achievement')
        ordering = ['-earned_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.achievement.name}"


class LearningProgress(models.Model):
    """Модель для отслеживания прогресса обучения по категориям"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='learning_progress')
    category = models.ForeignKey('blog.Category', on_delete=models.CASCADE)
    posts_viewed = models.ManyToManyField('blog.Post', related_name='viewed_by_progress')
    last_viewed = models.DateTimeField(auto_now=True, verbose_name="Последний просмотр")
    is_completed = models.BooleanField(default=False, verbose_name="Категория завершена")
    
    class Meta:
        unique_together = ('user', 'category')
    
    def __str__(self):
        return f"{self.user.username} - {self.category.name}"
    
    def completion_percentage(self):
        """Возвращает процент прохождения категории"""
        total_posts = self.category.post_set.count()
        if total_posts == 0:
            return 0
        viewed_posts = self.posts_viewed.count()
        return (viewed_posts / total_posts) * 100


class Certificate(models.Model):
    """Модель для сертификатов о прохождении обучения"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    category = models.ForeignKey('blog.Category', on_delete=models.CASCADE)
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата выдачи")
    certificate_id = models.CharField(max_length=50, unique=True, verbose_name="Номер сертификата")
    certificate_file = models.FileField(upload_to='certificates/', null=True, blank=True)
    
    class Meta:
        ordering = ['-issued_at']
    
    def __str__(self):
        return f"Сертификат #{self.certificate_id} - {self.user.username} - {self.category.name}"


class LevelUpEvent(models.Model):
    """Модель для отслеживания повышения уровня пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='level_up_events')
    previous_level = models.IntegerField(verbose_name="Предыдущий уровень")
    new_level = models.IntegerField(verbose_name="Новый уровень")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время повышения")
    
    def __str__(self):
        return f"{self.user.username} повысил уровень до {self.new_level}"
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Если объект создается впервые
            self.previous_level = self.new_level - 1
        super().save(*args, **kwargs)

