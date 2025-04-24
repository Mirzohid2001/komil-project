from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from django.utils.safestring import mark_safe
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, FavoritePost, UserActivity, Achievement, UserAchievement, LearningProgress, Certificate, LevelUpEvent

class FavoritePostInline(admin.TabularInline):
    model = FavoritePost
    extra = 0
    readonly_fields = ('post', 'added_at')
    can_delete = True
    verbose_name = 'Избранный пост'
    verbose_name_plural = 'Избранные посты'

class UserActivityInline(admin.TabularInline):
    model = UserActivity
    extra = 0
    readonly_fields = ('activity_type', 'timestamp', 'post', 'ip_address', 'details')
    can_delete = False
    max_num = 10
    verbose_name = 'Активность пользователя'
    verbose_name_plural = 'Активность пользователя'
    
    def has_add_permission(self, request, obj=None):
        return False

class CustomUserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Дополнительные данные', {
            'fields': ('role', 'profile_image', 'bio', 'phone_number', 'experience_points', 'level')
        }),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'level', 'experience_points')
    list_filter = BaseUserAdmin.list_filter + ('role', 'level')
    search_fields = BaseUserAdmin.search_fields + ('bio', 'phone_number')
    
    def profile_preview(self, obj):
        if obj.profile_image:
            return format_html('<img src="{}" width="150" height="150" style="object-fit: cover; border-radius: 50%;" />', obj.profile_image.url)
        return "Нет изображения"
    profile_preview.short_description = 'Фото профиля'
    
    def view_count(self, obj):
        count = obj.videoview_set.count()
        return format_html('<span style="color: #0066cc; font-weight: bold;">{}</span>', count)
    view_count.short_description = 'Просмотров видео'
    
    def favorite_count(self, obj):
        count = obj.favorites.count()
        return format_html('<span style="color: #e11d48; font-weight: bold;">{}</span>', count)
    favorite_count.short_description = 'Избранных'
    
    def activity_summary(self, obj):
        # Общее количество активностей
        total_activity = obj.activities.count()
        
        # Активности по типам
        activities_by_type = obj.activities.values('activity_type').annotate(count=Count('id')).order_by('-count')
        
        # Самый популярный тип активности
        most_popular_type = None
        if activities_by_type:
            most_popular_type = activities_by_type[0]
        
        # Последние 5 активностей
        recent_activities = obj.activities.all()[:5]
        
        # Количество просмотров видео за последний месяц
        from datetime import datetime, timedelta
        last_month = datetime.now() - timedelta(days=30)
        video_views_last_month = obj.videoview_set.filter(viewed_at__gte=last_month).count()
        
        # Формируем HTML для вывода сводки активности
        html = f"""
        <div style="margin-bottom: 20px;">
            <div style="display: flex; gap: 30px; margin-bottom: 20px;">
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0; color: #666;">Всего активностей</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0; color: #333;">{total_activity}</p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0; color: #666;">Просмотров видео за месяц</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0; color: #0066cc;">{video_views_last_month}</p>
                </div>
            </div>
            
            <h3 style="color: #333; margin-top: 30px;">Активность по типам</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px;">
                <tr>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Тип активности</th>
                    <th style="text-align: right; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Количество</th>
                </tr>
        """
        
        for activity in activities_by_type:
            activity_type = dict(UserActivity.ACTIVITY_TYPES).get(activity['activity_type'], activity['activity_type'])
            html += f"""
                <tr>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity_type}</td>
                    <td style="text-align: right; padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold;">{activity['count']}</td>
                </tr>
            """
            
        html += """
            </table>
            
            <h3 style="color: #333;">Последние действия</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Тип</th>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Дата</th>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Пост</th>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">IP адрес</th>
                </tr>
        """
        
        for activity in recent_activities:
            activity_type = activity.get_activity_type_display()
            post_title = activity.post.title if activity.post else '-'
            html += f"""
                <tr>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity_type}</td>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity.timestamp.strftime('%d.%m.%Y %H:%M')}</td>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{post_title}</td>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity.ip_address or '-'}</td>
                </tr>
            """
            
        html += """
            </table>
        </div>
        """
        
        return mark_safe(html)
    activity_summary.short_description = 'Сводка активности'


class FavoritePostAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('user__username', 'post__title')
    date_hierarchy = 'added_at'


class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'timestamp', 'post', 'ip_address')
    list_filter = ('activity_type', 'timestamp')
    search_fields = ('user__username', 'ip_address')
    date_hierarchy = 'timestamp'


class AchievementAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'required_value', 'experience_reward', 'is_secret')
    list_filter = ('type', 'is_secret')
    search_fields = ('name', 'description')


class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ('user', 'achievement', 'earned_at', 'current_value')
    list_filter = ('earned_at', 'achievement__type')
    search_fields = ('user__username', 'achievement__name')
    date_hierarchy = 'earned_at'


class LearningProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'last_viewed', 'is_completed', 'get_completion_percentage')
    list_filter = ('is_completed', 'last_viewed')
    search_fields = ('user__username', 'category__name')
    date_hierarchy = 'last_viewed'
    filter_horizontal = ('posts_viewed',)
    
    def get_completion_percentage(self, obj):
        return f"{obj.completion_percentage():.1f}%"
    get_completion_percentage.short_description = 'Прогресс'


class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_id', 'user', 'category', 'issued_at')
    list_filter = ('issued_at', 'category')
    search_fields = ('certificate_id', 'user__username', 'category__name')
    date_hierarchy = 'issued_at'


class LevelUpEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'previous_level', 'new_level', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('user__username',)
    date_hierarchy = 'timestamp'


# Регистрируем модели с кастомными админками
admin.site.register(User, CustomUserAdmin)
admin.site.register(FavoritePost, FavoritePostAdmin)
admin.site.register(UserActivity, UserActivityAdmin)
admin.site.register(Achievement, AchievementAdmin)
admin.site.register(UserAchievement, UserAchievementAdmin)
admin.site.register(LearningProgress, LearningProgressAdmin)
admin.site.register(Certificate, CertificateAdmin)
admin.site.register(LevelUpEvent, LevelUpEventAdmin)
