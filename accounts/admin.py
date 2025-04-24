from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from django.utils.safestring import mark_safe
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, FavoritePost, UserActivity

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

class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'get_role_display', 'is_staff', 'date_joined', 'last_login', 'view_count', 'favorite_count')
    list_filter = ('role', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    readonly_fields = ('date_joined', 'last_login', 'profile_preview', 'activity_summary')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Личная информация', {'fields': ('first_name', 'last_name', 'email', 'role', 'bio', 'phone_number')}),
        ('Медиа', {'fields': ('profile_image', 'profile_preview')}),
        ('Активность', {'fields': ('activity_summary',)}),
        ('Права доступа', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined'), 'classes': ('collapse',)}),
    )
    
    inlines = [FavoritePostInline, UserActivityInline]
    
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
    list_filter = ('added_at', 'user__role')
    search_fields = ('user__username', 'post__title')
    date_hierarchy = 'added_at'


class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'timestamp', 'post_title', 'ip_address')
    list_filter = ('activity_type', 'timestamp', 'user__role')
    search_fields = ('user__username', 'post__title', 'ip_address')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'activity_type', 'timestamp', 'post', 'ip_address', 'details')
    
    def post_title(self, obj):
        if obj.post:
            return obj.post.title
        return "-"
    post_title.short_description = 'Пост'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


# Регистрируем модели с кастомными админками
admin.site.register(User, UserAdmin)
admin.site.register(FavoritePost, FavoritePostAdmin)
admin.site.register(UserActivity, UserActivityAdmin)
