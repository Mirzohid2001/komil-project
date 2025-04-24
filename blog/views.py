from django.shortcuts import render, get_object_or_404
from .models import Category, Post, VideoView
from django.contrib.auth.decorators import login_required
from accounts.models import UserActivity
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def home(request):
    view_as_role = request.GET.get('view_as_role')
    is_admin = request.user.role == 'админ'
    posts_query = Post.objects.order_by('-created_at')

    if is_admin:
        if view_as_role: 
            posts_query = posts_query.filter(role=view_as_role)
    else:
        posts_query = posts_query.filter(role=request.user.role)
    
    latest_posts = posts_query[:5]
    
    roles = None
    if is_admin:
        roles = User.ROLE_CHOICES
    
    return render(request, 'blog/home.html', {
        'latest_posts': latest_posts,
        'is_admin': is_admin,
        'roles': roles,
        'selected_role': view_as_role
    })

@login_required
def category_list(request):
    categories = Category.objects.all()
    return render(request, 'blog/category_list.html', {'categories': categories})


@login_required
def post_list(request, cat_id):
    category = get_object_or_404(Category, id=cat_id)
    
    posts = Post.objects.filter(category=category).order_by('-created_at')
    
    role_filter = request.GET.get('role')
    date_from   = request.GET.get('from')
    date_to     = request.GET.get('to')
    is_admin = request.user.role == 'админ'
    
    if role_filter and is_admin:
        posts = posts.filter(role=role_filter)
    elif not is_admin:
        posts = posts.filter(role=request.user.role)
    
    # Применяем фильтры по дате
    if date_from:
        posts = posts.filter(created_at__date__gte=date_from)
    if date_to:
        posts = posts.filter(created_at__date__lte=date_to)

    context = {
        'category': category,
        'posts': posts,
        'roles': User.ROLE_CHOICES,   
        'selected_role': role_filter,
        'from': date_from,
        'to': date_to,
        'is_admin': is_admin,  # Передаем флаг админа для шаблона
    }
    return render(request, 'blog/post_list.html', context)

@login_required
def post_detail(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    
    # Проверка доступа: только админы могут видеть посты любой роли
    if request.user.role != 'админ' and post.role != request.user.role:
        # Перенаправляем на страницу категорий, если пользователь не имеет доступа
        from django.shortcuts import redirect
        from django.contrib import messages
        messages.error(request, "У вас нет доступа к этому посту")
        return redirect('blog:category_list')
    
    # Получаем IP адрес пользователя
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    # Записываем просмотр поста в активность пользователя
    activity_type = 'view_post'
    if post.video:
        activity_type = 'view_video'
        
        # Записываем просмотр видео
        VideoView.objects.create(
            post=post,
            user=request.user,
            ip_address=ip
        )
    
    # Создаем запись активности
    UserActivity.objects.create(
        user=request.user,
        activity_type=activity_type,
        post=post,
        ip_address=ip
    )
    
    # Video ko'rganlar ro'yxati
    video_views = None
    if request.user.role == 'админ':  # Faqat adminlar ko'rishlar ro'yxatini ko'ra oladi
        video_views = post.videoview_set.all()[:20]  # Oxirgi 20 ta ko'rish
    
    # Statistikani hisoblash
    context = {
        'post': post,
        'view_count': post.view_count(),
        'unique_viewers': post.unique_viewers_count(),
        'video_views': video_views,
        # Проверяем, добавлен ли пост в избранное
        'is_favorite': hasattr(request.user, 'favorites') and request.user.favorites.filter(post=post).exists(),
    }
    
    return render(request, 'blog/post_detail.html', context)

@login_required
def analytics_dashboard(request):
    """Страница аналитики просмотров видео"""
    # Проверка доступа - только для администраторов
    if request.user.role != 'админ':
        from django.shortcuts import redirect
        from django.contrib import messages
        messages.error(request, "У вас нет доступа к аналитике")
        return redirect('blog:home')
    
    # Получаем общее количество постов с видео
    video_posts = Post.objects.filter(video__isnull=False)
    video_posts_count = video_posts.count()
    
    # Общее количество просмотров всех видео
    total_views = VideoView.objects.count()
    
    # Общее количество уникальных зрителей
    unique_viewers = VideoView.objects.values('user').distinct().count()
    
    # Получаем топ-5 видео по количеству просмотров
    top_videos = video_posts.annotate(
        view_count=Count('videoview')
    ).order_by('-view_count')[:5]
    
    # Получаем топ-5 пользователей по количеству просмотров
    top_viewers = User.objects.annotate(
        view_count=Count('videoview')
    ).order_by('-view_count')[:5]
    
    # Получаем данные для графика просмотров по дням за последние 30 дней
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    
    # Данные для графика по дням
    views_by_day = VideoView.objects.filter(
        viewed_at__date__range=[start_date, end_date]
    ).annotate(
        date=TruncDate('viewed_at')
    ).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    # Преобразуем данные для графика по дням
    daily_data = {
        'labels': [item['date'].strftime('%d.%m.%Y') for item in views_by_day],
        'data': [item['count'] for item in views_by_day]
    }
    
    # Данные для графика по ролям
    views_by_role = VideoView.objects.values(
        'user__role'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    role_data = {
        'labels': [dict(User.ROLE_CHOICES).get(item['user__role'], item['user__role']) for item in views_by_role],
        'data': [item['count'] for item in views_by_role]
    }
    
    # Данные для графика по неделям
    views_by_week = VideoView.objects.filter(
        viewed_at__date__range=[start_date - timedelta(days=30), end_date]
    ).annotate(
        week=TruncWeek('viewed_at')
    ).values('week').annotate(
        count=Count('id')
    ).order_by('week')
    
    weekly_data = {
        'labels': [f"Неделя {item['week'].strftime('%d.%m.%Y')}" for item in views_by_week],
        'data': [item['count'] for item in views_by_week]
    }
    
    context = {
        'video_posts_count': video_posts_count,
        'total_views': total_views,
        'unique_viewers': unique_viewers,
        'top_videos': top_videos,
        'top_viewers': top_viewers,
        'daily_data_json': json.dumps(daily_data),
        'role_data_json': json.dumps(role_data),
        'weekly_data_json': json.dumps(weekly_data),
    }
    
    return render(request, 'blog/analytics.html', context)


@login_required
def analytics_data(request):
    """API для получения данных аналитики"""
    if request.user.role != 'админ':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    period = request.GET.get('period', 'day')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    now = datetime.now()
    
    # Определяем временной период
    if not start_date or not end_date:
        if period == 'day':
            start_date = (now - timedelta(days=30)).date()
            end_date = now.date()
        elif period == 'week':
            start_date = (now - timedelta(weeks=12)).date()
            end_date = now.date()
        elif period == 'month':
            start_date = (now - timedelta(days=365)).date()
            end_date = now.date()
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Получаем данные в зависимости от периода
    if period == 'day':
        views = VideoView.objects.filter(
            viewed_at__date__range=[start_date, end_date]
        ).annotate(
            period=TruncDate('viewed_at')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')
        
        data = {
            'labels': [item['period'].strftime('%d.%m.%Y') for item in views],
            'data': [item['count'] for item in views]
        }
    
    elif period == 'week':
        views = VideoView.objects.filter(
            viewed_at__date__range=[start_date, end_date]
        ).annotate(
            period=TruncWeek('viewed_at')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')
        
        data = {
            'labels': [f"Неделя {item['period'].strftime('%d.%m.%Y')}" for item in views],
            'data': [item['count'] for item in views]
        }
    
    elif period == 'month':
        views = VideoView.objects.filter(
            viewed_at__date__range=[start_date, end_date]
        ).annotate(
            period=TruncMonth('viewed_at')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')
        
        data = {
            'labels': [item['period'].strftime('%m.%Y') for item in views],
            'data': [item['count'] for item in views]
        }
    
    return JsonResponse(data)
