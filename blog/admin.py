from django.contrib import admin
from django.db.models import Count, F, Q
from django.utils.html import format_html
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.db.models.functions import TruncDate, TruncMonth
from datetime import datetime, timedelta
import json
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages

from .models import Category, Post, VideoView, Test, Question, Option, TestResult, UserAnswer, DocumentCategory, Document, DocumentView, DocumentDownload
from accounts.models import UserActivity, User

# Добавляем форму проверки вопросов
class QuestionValidationForm:
    def __init__(self, data=None):
        self.data = data or {}
        self.errors = {}
        
    def is_valid(self):
        return not bool(self.errors)

@staff_member_required
def validate_questions_view(request):
    """Представление для валидации логической связи между вопросами и ответами"""
    
    if request.method == 'POST':
        test_id = request.POST.get('test_id')
        if not test_id:
            messages.error(request, "Выберите тест для проверки")
            return redirect('admin:blog_test_changelist')
        
        test = Test.objects.get(id=test_id)
        questions = Question.objects.filter(test=test).prefetch_related('options')
        
        # Проверяем каждый вопрос
        invalid_questions = []
        checker = QuestionAdmin(Question, admin.site)
        
        for question in questions:
            options = list(question.options.all())
            valid_question_types = checker._check_question_type(question.text, options)
            
            # Если вопрос не проходит проверку
            if not valid_question_types:
                invalid_questions.append({
                    'id': question.id,
                    'text': question.text,
                    'options': [option.text for option in options],
                    'url': reverse('admin:blog_question_change', args=[question.id])
                })
        
        context = {
            'title': f"Результаты проверки теста: {test.title}",
            'test': test,
            'invalid_questions': invalid_questions,
            'total_questions': questions.count(),
            'invalid_count': len(invalid_questions),
            'app_label': 'blog',
            'opts': Test._meta,
            'has_permission': True,
            'site_header': admin.site.site_header,
            'site_title': admin.site.site_title,
            'index_title': admin.site.index_title,
        }
        
        return render(request, 'admin/question_validation_results.html', context)
    
    # Если GET-запрос, показываем форму выбора теста
    tests = Test.objects.all()
    
    # Проверяем, был ли передан ID теста в параметрах запроса
    pre_selected_test_id = request.GET.get('test_id')
    if pre_selected_test_id:
        # Если да, можно автоматически выбрать этот тест
        try:
            test_id = int(pre_selected_test_id)
            # Отправляем POST-запрос на проверку этого теста
            request.method = 'POST'
            request.POST = request.POST.copy()
            request.POST['test_id'] = test_id
            return validate_questions_view(request)
        except (ValueError, TypeError):
            pass  # Если ID невалидный, просто показываем форму
    
    context = {
        'title': "Проверка логической связи вопросов и ответов",
        'tests': tests,
        'app_label': 'blog',
        'opts': Test._meta,
        'has_permission': True,
        'site_header': admin.site.site_header,
        'site_title': admin.site.site_title,
        'index_title': admin.site.index_title,
    }
    
    return render(request, 'admin/question_validation_form.html', context)

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
    site_header = 'Панель управления заводом'
    site_title = 'Завод администрирование'
    index_title = 'Администрирование'
    
    def each_context(self, request):
        context = super().each_context(request)
        context['has_permission'] = request.user.is_active and request.user.is_staff and request.user.role == 'админ'
        return context

# Получаем оригинальный объект AdminSite
original_admin_site = admin.site

# Добавляем URL для аналитики
original_admin_site.get_urls = (lambda original_get_urls: 
    lambda: original_get_urls() + [
        path('blog/analytics/', analytics_view, name='blog_analytics'),
    ]
)(original_admin_site.get_urls)

class OptionInline(admin.TabularInline):
    model = Option
    extra = 4
    min_num = 2

class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'test', 'get_correct_option', 'created_at')
    list_filter = ('test', 'created_at', 'updated_at')
    search_fields = ('text', 'explanation')
    inlines = [OptionInline]
    
    def get_correct_option(self, obj):
        correct = obj.get_correct_option()
        return correct.text if correct else "Нет правильного ответа"
    get_correct_option.short_description = "Правильный ответ"
    
    def save_model(self, request, obj, form, change):
        """Сохраняем вопрос и проверяем логическую связь с вариантами ответов"""
        # Сохраняем вопрос
        super().save_model(request, obj, form, change)
        
        # Если это новый вопрос, мы не можем проверить варианты ответов,
        # так как они сохраняются в InlineFormSet после сохранения вопроса
        if not change:
            return
        
        # Проверяем наличие правильного ответа
        correct_option = obj.get_correct_option()
        if not correct_option:
            self.message_user(request, f"Внимание! У вопроса '{obj.text[:50]}...' нет правильного варианта ответа.", level=messages.WARNING)
            return
        
        # Получаем все варианты ответов
        options = list(obj.options.all())
        
        # Проверка логической связи вопроса и ответов
        valid_question_types = self._check_question_type(obj.text, options)
        if not valid_question_types:
            self.message_user(request, 
                f"Внимание! Вопрос '{obj.text[:50]}...' и варианты ответов могут не соответствовать логически.", 
                level=messages.WARNING)
    
    def _check_question_type(self, question_text, options):
        """Проверяет соответствие типа вопроса и вариантов ответов"""
        question_text = question_text.lower()
        
        # 1. Проверка на вопросы о количестве/числе
        quantity_keywords = [
            'nechta', 'qancha', 'necha', 'nechanchi', 'qanchasi', 'miqdori', 'soni',
            'nechtasi', 'qaysisi', 'nechta', 'qaysi raqam', 'necha marta', 'necha kun'
        ]
        
        is_quantity_question = any(keyword in question_text for keyword in quantity_keywords)
        
        if is_quantity_question:
            # Для вопросов о количестве варианты должны содержать числа
            has_numeric_options = False
            for option in options:
                # Проверяем, содержит ли вариант ответа числа или числовые значения
                if any(char.isdigit() for char in option.text):
                    has_numeric_options = True
                    break
            
            if not has_numeric_options:
                return False
        
        # 2. Проверка на вопросы "что нужно делать?"
        action_keywords = [
            'nima qilish kerak', 'qanday qilish kerak', 'kerak bo\'ladi', 'qilinadi',
            'bajariladi', 'amalga oshiriladi', 'qilish usuli', 'qanday amalga', 'qilish tartibi'
        ]
        
        is_action_question = any(keyword in question_text for keyword in action_keywords)
        
        if is_action_question:
            # Варианты ответов должны содержать глаголы действия
            action_verb_endings = [
                'lash', 'ish', 'ash', 'moq', 'sini', 'shni', 'tiladi', 'dirish', 'iladi'
            ]
            
            has_action_options = False
            for option in options:
                if any(option.text.lower().endswith(ending) for ending in action_verb_endings):
                    has_action_options = True
                    break
            
            if not has_action_options:
                return False
        
        # 3. Проверка на вопросы о времени
        time_keywords = [
            'qachon', 'qaysi vaqtda', 'qaysi muddatda', 'qancha vaqt', 'vaqti', 'soatda',
            'daqiqada', 'qaysi kun', 'qaysi oy', 'qaysi yil'
        ]
        
        is_time_question = any(keyword in question_text for keyword in time_keywords)
        
        if is_time_question:
            # Варианты ответов должны содержать указания на время/даты
            time_indicators = [
                'soat', 'daqiqa', 'kun', 'oy', 'yil', 'hafta', 'sana', 'muddat', 
                'boshla', 'tugash', 'yakunla', 'davomida', 'oralig\'ida'
            ]
            
            has_time_options = False
            for option in options:
                option_text = option.text.lower()
                if any(indicator in option_text for indicator in time_indicators) or any(char.isdigit() for char in option_text):
                    has_time_options = True
                    break
            
            if not has_time_options:
                return False
        
        # 4. Проверка на вопросы о месте или локации
        location_keywords = [
            'qayerda', 'qaysi joyda', 'qayerga', 'qaysi manzilda', 'joylashgan',
            'manzili', 'turadi', 'topiladi'
        ]
        
        is_location_question = any(keyword in question_text for keyword in location_keywords)
        
        if is_location_question:
            # Варианты ответов должны содержать указания на места
            location_indicators = [
                'xona', 'bino', 'markaz', 'joy', 'ko\'cha', 'viloyat', 'tuman', 'shahar', 
                'qishloq', 'mahalla', 'hudud', 'mintaqa', 'mamlakat', 'davlat'
            ]
            
            has_location_options = False
            for option in options:
                if any(indicator in option.text.lower() for indicator in location_indicators):
                    has_location_options = True
                    break
                    
            if not has_location_options:
                return False
                
        # По умолчанию, если никаких проблем не найдено, считаем что всё соответствует
        return True

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True
    readonly_fields = ('text', 'created_at')
    fields = ('text', 'created_at')
    can_delete = False
    max_num = 0

class TestAdmin(admin.ModelAdmin):
    list_display = ('title', 'role', 'get_question_count', 'get_valid_questions_count', 'passing_score', 'is_active', 'updated_at')
    list_filter = ('role', 'is_active', 'created_at', 'updated_at')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at', 'valid_questions_info')
    inlines = [QuestionInline]
    change_list_template = 'admin/test_changelist.html'
    
    def get_question_count(self, obj):
        return obj.get_total_questions()
    get_question_count.short_description = "Количество вопросов"
    
    def get_valid_questions_count(self, obj):
        valid_count = obj.get_valid_questions_count()
        total = obj.get_total_questions()
        
        if total == 0:
            return "0"
        
        percent = (valid_count / total) * 100
        if percent < 50:
            return format_html('<span style="color: #dc3545; font-weight: bold;">{} ({}%)</span>', valid_count, int(percent))
        elif percent < 80:
            return format_html('<span style="color: #ffc107; font-weight: bold;">{} ({}%)</span>', valid_count, int(percent))
        else:
            return format_html('<span style="color: #28a745; font-weight: bold;">{} ({}%)</span>', valid_count, int(percent))
    get_valid_questions_count.short_description = "Логичных вопросов"
    
    def valid_questions_info(self, obj):
        valid_count = obj.get_valid_questions_count()
        total = obj.get_total_questions()
        
        if total == 0:
            return "Нет вопросов в тесте"
        
        percent = (valid_count / total) * 100
        
        html = f"""
        <div style="margin-bottom: 20px;">
            <h3>Информация о логической связи вопросов и ответов</h3>
            <div style="display: flex; gap: 20px; margin-bottom: 20px;">
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0;">Всего вопросов</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0;">{total}</p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0;">Логически корректных</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0; color: {self._get_color_for_percent(percent)};">
                        {valid_count} ({int(percent)}%)
                    </p>
                </div>
            </div>
            
            <div style="margin-bottom: 20px;">
                <h4>Состояние логической связи:</h4>
        """
        
        if percent < 50:
            html += """
                <div style="border-left: 4px solid #dc3545; padding: 10px; background-color: #f8d7da;">
                    <strong style="color: #721c24;">Критическое</strong> - Большинство вопросов не имеют логической связи с ответами. 
                    Тест может быть некорректным для пользователей.
                </div>
            """
        elif percent < 80:
            html += """
                <div style="border-left: 4px solid #ffc107; padding: 10px; background-color: #fff3cd;">
                    <strong style="color: #856404;">Требует внимания</strong> - Часть вопросов не имеет логической связи с ответами. 
                    Рекомендуется проверить некорректные вопросы.
                </div>
            """
        else:
            html += """
                <div style="border-left: 4px solid #28a745; padding: 10px; background-color: #d4edda;">
                    <strong style="color: #155724;">Хорошее</strong> - Большинство вопросов имеют правильную логическую связь с ответами.
                </div>
            """
        
        html += """
            </div>
            
            <div>
                <a href="{}" class="button" style="margin-right: 10px;">Проверить вопросы</a>
            </div>
        </div>
        """.format(reverse('admin:question_validation') + f'?test_id={obj.id}')
        
        return mark_safe(html)
    valid_questions_info.short_description = "Логическая связь вопросов и ответов"
    
    def _get_color_for_percent(self, percent):
        if percent < 50:
            return "#dc3545"  # красный
        elif percent < 80:
            return "#ffc107"  # желтый
        else:
            return "#28a745"  # зеленый
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            ('Основная информация', {
                'fields': ('title', 'description', 'role')
            }),
            ('Настройки теста', {
                'fields': ('time_limit', 'passing_score', 'is_active')
            }),
            ('Даты', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',),
            }),
        ]
        
        # Добавляем поле информации о вопросах только если тест уже создан
        if obj:
            fieldsets.insert(1, ('Валидация логики', {
                'fields': ('valid_questions_info',),
            }))
        
        return fieldsets
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('validate-questions/', validate_questions_view, name='question_validation'),
        ]
        return custom_urls + urls

class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    readonly_fields = ('question', 'selected_option', 'is_correct')
    can_delete = False
    max_num = 0

class TestResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'test', 'score', 'percentage', 'is_passed', 'get_duration', 'completed_at')
    list_filter = ('is_passed', 'completed_at', 'user__role', 'test')
    search_fields = ('user__username', 'test__title')
    readonly_fields = ('user', 'test', 'score', 'percentage', 'is_passed', 'started_at', 'completed_at', 'get_duration')
    inlines = [UserAnswerInline]
    
    def get_duration(self, obj):
        return f"{obj.get_duration()} мин."
    get_duration.short_description = "Продолжительность"

# Register test-related models
admin.site.register(Test, TestAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(TestResult, TestResultAdmin)

# Document Management Admin
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'documents_count', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    list_filter = ('created_at', 'updated_at')
    ordering = ('name',)
    
    def documents_count(self, obj):
        return obj.documents_count()
    documents_count.short_description = 'Hujjatlar soni'

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'file_type', 'file_size_display', 'uploaded_by', 'uploaded_at', 'download_count', 'view_count', 'is_public')
    list_filter = ('category', 'file_type', 'is_public', 'uploaded_at', 'uploaded_by__role')
    search_fields = ('title', 'description', 'uploaded_by__username')
    readonly_fields = ('file_size', 'file_type', 'uploaded_at', 'updated_at', 'download_count', 'view_count')
    date_hierarchy = 'uploaded_at'
    ordering = ('-uploaded_at',)
    
    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('title', 'description', 'file', 'category')
        }),
        ('Ruxsatlar', {
            'fields': ('is_public', 'allowed_roles'),
            'description': 'Hujjatga ruxsat berilgan foydalanuvchi rollarini tanlang'
        }),
        ('Meta ma\'lumotlar', {
            'fields': ('file_size', 'file_type', 'uploaded_by', 'uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Statistika', {
            'fields': ('download_count', 'view_count'),
            'classes': ('collapse',)
        }),
    )
    
    def get_form(self, request, obj=None, **kwargs):
        """Get the form and customize the allowed_roles field"""
        form = super().get_form(request, obj, **kwargs)
        
        # Customize the allowed_roles field to use checkboxes
        from django import forms
        from accounts.models import User
        
        form.base_fields['allowed_roles'] = forms.MultipleChoiceField(
            choices=User.ROLE_CHOICES,
            widget=forms.CheckboxSelectMultiple(),
            required=False,
            label="Ruxsat berilgan rollar",
            help_text="Hujjatga ruxsat berilgan foydalanuvchi rollarini tanlang"
        )
        
        # Set initial value if editing existing document
        if obj and obj.allowed_roles:
            form.base_fields['allowed_roles'].initial = obj.allowed_roles
        
        return form
    
    def save_model(self, request, obj, form, change):
        """Save the model and handle the allowed_roles field"""
        if not change:  # Only set uploaded_by on creation
            obj.uploaded_by = request.user
        
        # Handle allowed_roles field - convert list to JSON
        if 'allowed_roles' in form.cleaned_data:
            obj.allowed_roles = form.cleaned_data['allowed_roles']
        
        super().save_model(request, obj, form, change)
    
    def file_size_display(self, obj):
        return obj.get_file_size_display()
    file_size_display.short_description = 'Fayl hajmi'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category', 'uploaded_by')

class DocumentViewAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'user_role', 'viewed_at', 'ip_address')
    list_filter = ('user__role', 'viewed_at', 'document__category')
    search_fields = ('document__title', 'user__username', 'ip_address')
    date_hierarchy = 'viewed_at'
    readonly_fields = ('document', 'user', 'viewed_at', 'ip_address')
    
    def user_role(self, obj):
        return obj.user.get_role_display()
    user_role.short_description = 'Foydalanuvchi roli'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

class DocumentDownloadAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'user_role', 'downloaded_at', 'ip_address')
    list_filter = ('user__role', 'downloaded_at', 'document__category')
    search_fields = ('document__title', 'user__username', 'ip_address')
    date_hierarchy = 'downloaded_at'
    readonly_fields = ('document', 'user', 'downloaded_at', 'ip_address')
    
    def user_role(self, obj):
        return obj.user.get_role_display()
    user_role.short_description = 'Foydalanuvchi roli'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

# Register document models
admin.site.register(DocumentCategory, DocumentCategoryAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(DocumentView, DocumentViewAdmin)
admin.site.register(DocumentDownload, DocumentDownloadAdmin)
