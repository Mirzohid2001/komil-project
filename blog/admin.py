from django.contrib import admin
from django.db.models import Count, F, Q
from django.utils.html import format_html
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.db.models.functions import TruncDate, TruncMonth
from datetime import datetime, timedelta
import json
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required

from .models import Category, Post, VideoView
from accounts.models import UserActivity, User

class VideoViewInline(admin.TabularInline):
    model = VideoView
    extra = 0
    readonly_fields = ('user', 'viewed_at', 'ip_address')
    can_delete = False
    fields = ('user', 'viewed_at', 'ip_address')
    max_num = 20
    verbose_name = 'Просмотр видео'
    verbose_name_plural = 'Просмотры видео'
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user')

class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'role', 'created_at', 'has_video', 'view_count_display', 'unique_viewers_display')
    list_filter = ('category', 'role', 'created_at')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at', 'video_preview', 'analytics_data')
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'content', 'category', 'role')
        }),
        ('Медиа', {
            'fields': ('video', 'video_preview'),
        }),
        ('Аналитика просмотров', {
            'fields': ('analytics_data',),
            'classes': ('collapse',),
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    inlines = [VideoViewInline]
    
    def has_video(self, obj):
        return bool(obj.video)
    has_video.boolean = True
    has_video.short_description = 'Видео'
    
    def view_count_display(self, obj):
        count = obj.view_count()
        return format_html('<span style="color: #0066cc; font-weight: bold;">{}</span>', count)
    view_count_display.short_description = 'Просмотры'
    
    def unique_viewers_display(self, obj):
        count = obj.unique_viewers_count()
        return format_html('<span style="color: #009933; font-weight: bold;">{}</span>', count)
    unique_viewers_display.short_description = 'Уникальные зрители'
    
    def video_preview(self, obj):
        if obj.video:
            return format_html('<video width="320" height="240" controls><source src="{}" type="video/mp4"></video>', obj.video.url)
        return "Нет видео"
    video_preview.short_description = 'Предпросмотр видео'
    
    def analytics_data(self, obj):
        if not obj.video:
            return "Для этого поста нет видео"
        
        # Количество просмотров
        view_count = obj.view_count()
        unique_viewers = obj.unique_viewers_count()
        
        # Получаем данные о просмотрах по дням за последние 30 дней
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        
        views_by_day = (VideoView.objects
                       .filter(post=obj, viewed_at__date__range=[start_date, end_date])
                       .annotate(date=TruncDate('viewed_at'))
                       .values('date')
                       .annotate(count=Count('id'))
                       .order_by('date'))
        
        # Получаем данные по популярным часам просмотра
        views_by_hour = (VideoView.objects
                        .filter(post=obj)
                        .annotate(hour=F('viewed_at__hour'))
                        .values('hour')
                        .annotate(count=Count('id'))
                        .order_by('hour'))
        
        # Получаем данные по ролям зрителей
        views_by_role = (VideoView.objects
                        .filter(post=obj)
                        .values('user__role')
                        .annotate(count=Count('id'))
                        .order_by('-count'))
        
        # Формируем HTML для вывода аналитики
        html = f"""
        <div style="margin-bottom: 20px;">
            <h3 style="color: #333;">Общая статистика</h3>
            <div style="display: flex; gap: 40px; margin-bottom: 20px;">
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0; color: #0066cc;">Всего просмотров</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0;">{view_count}</p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0; color: #009933;">Уникальных зрителей</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0;">{unique_viewers}</p>
                </div>
            </div>
            
            <h3 style="color: #333; margin-top: 30px;">Просмотры по дням</h3>
            <div style="height: 200px; margin-bottom: 30px;">
                <div style="display: flex; height: 180px; align-items: flex-end; gap: 5px; overflow-x: auto; padding-bottom: 10px;">
        """
        
        max_count = max([item['count'] for item in views_by_day], default=1)
        for item in views_by_day:
            date_str = item['date'].strftime('%d.%m')
            height_percent = (item['count'] / max_count) * 100
            html += f"""
                    <div style="display: flex; flex-direction: column; align-items: center; min-width: 40px;">
                        <div style="height: {height_percent}%; width: 30px; background: linear-gradient(to top, #4f46e5, #ec489a); border-radius: 4px;"></div>
                        <span style="font-size: 10px; margin-top: 5px;">{date_str}</span>
                        <span style="font-size: 10px; font-weight: bold;">{item['count']}</span>
                    </div>
            """
        
        html += """
                </div>
            </div>
            
            <div style="display: flex; gap: 40px;">
                <div style="flex: 1;">
                    <h3 style="color: #333;">Просмотры по часам</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <th style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">Час</th>
                            <th style="text-align: right; padding: 8px; border-bottom: 1px solid #ddd;">Просмотры</th>
                        </tr>
        """
        
        for item in views_by_hour:
            hour = item['hour']
            hour_display = f"{hour}:00 - {hour+1}:00"
            html += f"""
                        <tr>
                            <td style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">{hour_display}</td>
                            <td style="text-align: right; padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">{item['count']}</td>
                        </tr>
            """
        
        html += """
                    </table>
                </div>
                
                <div style="flex: 1;">
                    <h3 style="color: #333;">Просмотры по ролям</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <th style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">Роль</th>
                            <th style="text-align: right; padding: 8px; border-bottom: 1px solid #ddd;">Просмотры</th>
                        </tr>
        """
        
        for item in views_by_role:
            role = dict(obj.ROLE_CHOICES).get(item['user__role'], item['user__role'])
            html += f"""
                        <tr>
                            <td style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">{role}</td>
                            <td style="text-align: right; padding: 8px; border-bottom: 1px solid #ddd; font-weight: bold;">{item['count']}</td>
                        </tr>
            """
        
        html += """
                    </table>
                </div>
            </div>
            
            <div style="margin-top: 20px;">
                <h3 style="color: #333;">Последние просмотры</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <th style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">Пользователь</th>
                        <th style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">Дата и время</th>
                        <th style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">IP адрес</th>
                    </tr>
        """
        
        recent_views = VideoView.objects.filter(post=obj).select_related('user')[:10]
        for view in recent_views:
            html += f"""
                    <tr>
                        <td style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">{view.user.username} ({view.user.get_role_display()})</td>
                        <td style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">{view.viewed_at.strftime('%d.%m.%Y %H:%M')}</td>
                        <td style="text-align: left; padding: 8px; border-bottom: 1px solid #ddd;">{view.ip_address or 'Н/Д'}</td>
                    </tr>
            """
        
        html += """
                </table>
            </div>
        </div>
        """
        
        return mark_safe(html)
    analytics_data.short_description = 'Аналитика просмотров'

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'post_count', 'video_count', 'total_views')
    search_fields = ('name', 'description')
    
    def post_count(self, obj):
        count = Post.objects.filter(category=obj).count()
        if count > 0:
            url = reverse('admin:blog_post_changelist') + f'?category__id__exact={obj.id}'
            return format_html('<a href="{}">{} постов</a>', url, count)
        return '0 постов'
    post_count.short_description = 'Количество постов'
    
    def video_count(self, obj):
        count = Post.objects.filter(category=obj, video__isnull=False).count()
        if count > 0:
            url = reverse('admin:blog_post_changelist') + f'?category__id__exact={obj.id}&has_video__exact=1'
            return format_html('<a href="{}">{} видео</a>', url, count)
        return '0 видео'
    video_count.short_description = 'Видео'
    
    def total_views(self, obj):
        # Получаем все посты категории с видео
        posts_with_video = Post.objects.filter(category=obj, video__isnull=False)
        # Считаем просмотры
        view_count = VideoView.objects.filter(post__in=posts_with_video).count()
        return format_html('<span style="color: #0066cc; font-weight: bold;">{}</span>', view_count)
    total_views.short_description = 'Всего просмотров'

class VideoViewAdmin(admin.ModelAdmin):
    list_display = ('post', 'user', 'user_role', 'viewed_at', 'ip_address')
    list_filter = ('user__role', 'viewed_at', 'post__category')
    search_fields = ('post__title', 'user__username', 'ip_address')
    date_hierarchy = 'viewed_at'
    readonly_fields = ('post', 'user', 'viewed_at', 'ip_address')
    
    def user_role(self, obj):
        return obj.user.get_role_display()
    user_role.short_description = 'Роль пользователя'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

# Регистрируем модели с кастомными админками
admin.site.register(Category, CategoryAdmin)
admin.site.register(Post, PostAdmin)
admin.site.register(VideoView, VideoViewAdmin)

# Функция представления для страницы аналитики
@staff_member_required
def analytics_view(request):
    # Период аналитики
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    # Общая статистика
    video_posts_count = Post.objects.filter(video__isnull=False).count()
    total_views = VideoView.objects.count()
    unique_viewers = VideoView.objects.values('user').distinct().count()
    
    # Просмотры по дням
    views_by_day = (VideoView.objects
                  .filter(viewed_at__date__range=[start_date, end_date])
                  .annotate(date=TruncDate('viewed_at'))
                  .values('date')
                  .annotate(count=Count('id'))
                  .order_by('date'))
    
    daily_data = {
        'labels': [item['date'].strftime('%d.%m.%Y') for item in views_by_day],
        'data': [item['count'] for item in views_by_day]
    }
    
    # Просмотры по месяцам
    views_by_month = (VideoView.objects
                    .annotate(month=TruncMonth('viewed_at'))
                    .values('month')
                    .annotate(count=Count('id'))
                    .order_by('month'))
    
    monthly_data = {
        'labels': [item['month'].strftime('%m.%Y') for item in views_by_month],
        'data': [item['count'] for item in views_by_month]
    }
    
    # Просмотры по ролям
    views_by_role = (VideoView.objects
                   .values('user__role')
                   .annotate(count=Count('id'))
                   .order_by('-count'))
    
    role_data = {
        'labels': [dict(Post.ROLE_CHOICES).get(item['user__role'], item['user__role']) for item in views_by_role],
        'data': [item['count'] for item in views_by_role]
    }
    
    # Топ-5 видео
    top_videos = (Post.objects
                 .filter(video__isnull=False)
                 .annotate(view_count=Count('videoview'))
                 .order_by('-view_count')[:5])
    
    # Топ-5 пользователей
    top_viewers = (User.objects
                  .annotate(view_count=Count('videoview'))
                  .order_by('-view_count')[:5])
    
    # Активность пользователей за последнюю неделю
    week_ago = datetime.now() - timedelta(days=7)
    activities = (UserActivity.objects
                .filter(timestamp__gte=week_ago)
                .values('activity_type')
                .annotate(count=Count('id'))
                .order_by('-count'))
    
    activity_labels = [dict(UserActivity.ACTIVITY_TYPES).get(item['activity_type']) for item in activities]
    activity_data = [item['count'] for item in activities]
    
    context = {
        'title': 'Аналитика просмотров',
        'video_posts_count': video_posts_count,
        'total_views': total_views,
        'unique_viewers': unique_viewers,
        'daily_data_json': json.dumps(daily_data),
        'monthly_data_json': json.dumps(monthly_data),
        'role_data_json': json.dumps(role_data),
        'top_videos': top_videos,
        'top_viewers': top_viewers,
        'activity_labels': json.dumps(activity_labels),
        'activity_data': json.dumps(activity_data),
    }
    
    return render(request, 'admin/blog/analytics.html', context)

# Переопределяем админку для регистрации URL аналитики
class BlogAdminSite(admin.AdminSite):
    pass

# Получаем оригинальный объект AdminSite
original_admin_site = admin.site

# Добавляем URL для аналитики
original_admin_site.get_urls = (lambda original_get_urls: 
    lambda: original_get_urls() + [
        path('blog/analytics/', analytics_view, name='blog_analytics'),
    ]
)(original_admin_site.get_urls)
