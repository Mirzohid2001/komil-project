from django.contrib.auth import login, logout, update_session_auth_hash
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse, FileResponse
from .models import User, FavoritePost, UserActivity, Achievement, UserAchievement, LearningProgress, Certificate, LevelUpEvent
from blog.models import Post, Category, Test, TestResult
from django.db.models import Count, Q, Sum, Avg
from django.utils import timezone
from datetime import timedelta, datetime
import json
import uuid
import os
from django.conf import settings
from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa
import qrcode
from PIL import Image, ImageDraw, ImageFont
import base64

from .forms import SignUpForm, ProfileUpdateForm


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            # Записываем активность пользователя
            UserActivity.objects.create(
                user=user,
                activity_type='login',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return redirect('blog:home')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})


class MyLoginView(LoginView):
    template_name = 'accounts/login.html'
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Записываем активность пользователя
        UserActivity.objects.create(
            user=self.request.user,
            activity_type='login',
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
        
        return response


def logout_view(request):
    # Записываем активность пользователя перед выходом
    if request.user.is_authenticated:
        UserActivity.objects.create(
            user=request.user,
            activity_type='logout',
            ip_address=request.META.get('REMOTE_ADDR')
        )
    
    logout(request)
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """Просмотр профиля пользователя"""
    user = request.user
    
    # Получаем избранные посты
    favorites = FavoritePost.objects.filter(user=user)
    
    # Получаем историю активности
    activities = UserActivity.objects.filter(user=user)[:10]  # последние 10 активностей
    
    return render(request, 'accounts/profile.html', {
        'user': user,
        'favorites': favorites,
        'activities': activities,
    })


@login_required
def profile_edit(request):
    """Редактирование профиля пользователя"""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            
            # Записываем активность пользователя
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_update',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, 'Профиль успешно обновлен')
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    
    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
def change_password(request):
    """Изменение пароля пользователя"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Обновляем сессию чтобы пользователь не вылетел
            update_session_auth_hash(request, user)
            
            # Записываем активность пользователя
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_update',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'action': 'password_change'}
            )
            
            messages.success(request, 'Ваш пароль успешно изменен')
            return redirect('accounts:profile')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def activity_history(request):
    """Просмотр истории активности пользователя"""
    activities = UserActivity.objects.filter(user=request.user)
    
    # Пагинация
    paginator = Paginator(activities, 20)  # по 20 записей на страницу
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'accounts/activity_history.html', {'page_obj': page_obj})


@login_required
def toggle_favorite(request, post_id):
    """Добавление/удаление поста в/из избранное"""
    post = get_object_or_404(Post, id=post_id)
    favorite, created = FavoritePost.objects.get_or_create(user=request.user, post=post)
    
    if created:
        # Если запись создана - пост добавлен в избранное
        activity_type = 'favorite_add'
        messages.success(request, 'Пост добавлен в избранное')
    else:
        # Если запись уже существовала - удаляем из избранного
        favorite.delete()
        activity_type = 'favorite_remove'
        messages.info(request, 'Пост удален из избранного')
    
    # Записываем активность пользователя
    UserActivity.objects.create(
        user=request.user,
        activity_type=activity_type,
        post=post,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    # Возвращаем пользователя на ту же страницу
    return redirect(request.META.get('HTTP_REFERER', 'blog:home'))


@login_required
def favorites_list(request):
    """Просмотр списка избранных постов"""
    favorites = FavoritePost.objects.filter(user=request.user)
    
    return render(request, 'accounts/favorites.html', {'favorites': favorites})


@login_required
def learning_progress(request):
    """Страница с прогрессом обучения по категориям"""
    # Получаем все категории и прогресс пользователя
    categories = Category.objects.all()
    
    # Получаем или создаем записи о прогрессе для каждой категории
    progress_by_category = {}
    
    for category in categories:
        progress, created = LearningProgress.objects.get_or_create(
            user=request.user,
            category=category
        )
        
        # Получаем все посты в категории
        posts = Post.objects.filter(category=category)
        
        # Считаем количество просмотренных постов в категории
        viewed_posts = progress.posts_viewed.all()
        
        # Проверяем, завершена ли категория
        total_posts = posts.count()
        is_completed = (viewed_posts.count() == total_posts) and total_posts > 0
        
        # Если категория не отмечена как завершенная, но все посты просмотрены,
        # обновляем статус и проверяем выдачу сертификата
        if is_completed and not progress.is_completed:
            progress.is_completed = True
            progress.save()
            
            # Проверяем, нужно ли выдать сертификат
            if not Certificate.objects.filter(user=request.user, category=category).exists():
                # Генерируем уникальный ID сертификата
                certificate_id = f"CERT-{category.id}-{request.user.id}-{uuid.uuid4().hex[:8].upper()}"
                
                # Создаем сертификат
                certificate = Certificate.objects.create(
                    user=request.user,
                    category=category,
                    certificate_id=certificate_id
                )
                
                # Генерируем файл сертификата
                generate_certificate_file(certificate)
                
                # Даем пользователю очки опыта за завершение категории
                request.user.add_experience(200)
                
                # Проверяем достижение "Завершение категории"
                check_category_completion_achievement(request.user)
                
                messages.success(
                    request, 
                    f"Поздравляем! Вы завершили категорию '{category.name}' и получили сертификат."
                )
        
        # Собираем данные для отображения
        progress_by_category[category.id] = {
            'category': category,
            'progress': progress,
            'viewed_count': viewed_posts.count(),
            'total_count': total_posts,
            'percentage': progress.completion_percentage(),
            'is_completed': progress.is_completed,
            'posts': [
                {
                    'post': post,
                    'is_viewed': post in viewed_posts
                }
                for post in posts
            ]
        }
    
    context = {
        'progress_by_category': progress_by_category,
    }
    
    return render(request, 'accounts/learning_progress.html', context)


@login_required
def user_achievements(request):
    """Страница с достижениями пользователя"""
    # Получаем достижения пользователя
    user_achievements = UserAchievement.objects.filter(user=request.user).select_related('achievement')
    
    # Получаем все достижения для отображения прогресса
    all_achievements = Achievement.objects.all()
    
    # Группируем достижения по типам
    achievement_types = dict(Achievement.ACHIEVEMENT_TYPES)
    achievements_by_type = {}
    
    # Создаем словарь с информацией о достижениях пользователя
    for ach_type, type_name in achievement_types.items():
        achievements_of_type = []
        
        for achievement in all_achievements.filter(type=ach_type):
            # Проверяем, получено ли достижение пользователем
            user_achievement = next(
                (ua for ua in user_achievements if ua.achievement.id == achievement.id), 
                None
            )
            
            # Если достижение получено
            if user_achievement:
                achievements_of_type.append({
                    'achievement': achievement,
                    'user_achievement': user_achievement,
                    'is_earned': True,
                    'progress': 100,
                    'earned_at': user_achievement.earned_at
                })
            # Если достижение не получено, но не является секретным
            elif not achievement.is_secret:
                # Получаем текущий прогресс пользователя для этого достижения
                progress = get_achievement_progress(request.user, achievement)
                achievements_of_type.append({
                    'achievement': achievement,
                    'user_achievement': None,
                    'is_earned': False,
                    'progress': min(100, int(progress / achievement.required_value * 100)),
                    'current_value': progress,
                    'required_value': achievement.required_value
                })
            # Если достижение секретное и не получено, не показываем детали
            elif achievement.is_secret:
                achievements_of_type.append({
                    'achievement': {
                        'name': '???',
                        'description': 'Секретное достижение',
                        'icon': '/static/img/secret_achievement.png'
                    },
                    'user_achievement': None,
                    'is_earned': False,
                    'is_secret': True,
                    'progress': 0
                })
        
        if achievements_of_type:
            achievements_by_type[type_name] = achievements_of_type
    
    context = {
        'achievements_by_type': achievements_by_type,
        'total_achievements': all_achievements.count(),
        'earned_achievements': user_achievements.count(),
        'completion_percentage': (user_achievements.count() / all_achievements.count() * 100) if all_achievements.count() > 0 else 0,
        'total_experience_gained': sum(ua.achievement.experience_reward for ua in user_achievements)
    }
    
    return render(request, 'accounts/user_achievements.html', context)


@login_required
def user_certificates(request):
    """Страница с сертификатами пользователя"""
    # Получаем сертификаты пользователя
    certificates = Certificate.objects.filter(user=request.user).select_related('category')
    
    # Получаем категории, для которых нет сертификатов
    completed_categories = LearningProgress.objects.filter(
        user=request.user, is_completed=True
    ).values_list('category_id', flat=True)
    
    certificated_categories = Certificate.objects.filter(
        user=request.user
    ).values_list('category_id', flat=True)
    
    # Категории, по которым есть прогресс, но нет сертификатов
    missing_certificates = []
    for cat_id in completed_categories:
        if cat_id not in certificated_categories:
            category = Category.objects.get(id=cat_id)
            missing_certificates.append(category)
    
    context = {
        'certificates': certificates,
        'missing_certificates': missing_certificates
    }
    
    return render(request, 'accounts/user_certificates.html', context)


@login_required
def download_certificate(request, certificate_id):
    """Скачивание сертификата"""
    certificate = get_object_or_404(Certificate, id=certificate_id, user=request.user)
    
    # Если файл сертификата отсутствует, создаем его
    if not certificate.certificate_file:
        generate_certificate_file(certificate)
        certificate.refresh_from_db()
    
    # Возвращаем файл сертификата
    if certificate.certificate_file:
        return FileResponse(
            open(certificate.certificate_file.path, 'rb'),
            as_attachment=True,
            filename=f"certificate_{certificate.certificate_id}.pdf"
        )
    
    # Если что-то пошло не так, возвращаем ошибку
    messages.error(request, "Не удалось скачать сертификат. Пожалуйста, попробуйте позже.")
    return redirect('accounts:user_certificates')


@login_required
def user_statistics(request):
    """Страница со статистикой пользователя"""
    # Общая статистика
    view_count = UserActivity.objects.filter(
        user=request.user, 
        activity_type__in=['view_post', 'view_video']
    ).count()
    
    test_results = TestResult.objects.filter(user=request.user)
    tests_taken = test_results.count()
    tests_passed = test_results.filter(is_passed=True).count()
    pass_rate = tests_passed / tests_taken * 100 if tests_taken > 0 else 0
    
    # Статистика по XP
    xp_stats = {
        'total': request.user.experience_points,
        'level': request.user.level,
        'next_level_threshold': request.user.level * request.user.level * 100,
        'progress_to_next': min(100, request.user.experience_points / (request.user.level * request.user.level * 100) * 100)
    }
    
    # История достижений
    recent_achievements = UserAchievement.objects.filter(
        user=request.user
    ).select_related('achievement').order_by('-earned_at')[:5]
    
    # История повышения уровня
    level_ups = LevelUpEvent.objects.filter(user=request.user).order_by('-timestamp')[:5]
    
    # Статистика активности по времени (для графика)
    # Получаем данные за последние 30 дней
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)
    
    daily_activity = UserActivity.objects.filter(
        user=request.user,
        timestamp__range=[start_date, end_date]
    ).values('timestamp__date').annotate(count=Count('id')).order_by('timestamp__date')
    
    activity_data = {
        'labels': [item['timestamp__date'].strftime('%d.%m.%Y') for item in daily_activity],
        'data': [item['count'] for item in daily_activity]
    }
    
    context = {
        'view_count': view_count,
        'tests_taken': tests_taken,
        'tests_passed': tests_passed,
        'pass_rate': pass_rate,
        'xp_stats': xp_stats,
        'recent_achievements': recent_achievements,
        'level_ups': level_ups,
        'activity_data_json': json.dumps(activity_data),
        'certificates_count': Certificate.objects.filter(user=request.user).count(),
        'achievements_count': UserAchievement.objects.filter(user=request.user).count(),
        'categories_completed': LearningProgress.objects.filter(user=request.user, is_completed=True).count(),
        'avg_test_score': test_results.aggregate(avg=Avg('percentage'))['avg'] or 0
    }
    
    return render(request, 'accounts/user_statistics.html', context)


# Вспомогательные функции

def generate_certificate_file(certificate):
    """Генерирует PDF файл сертификата"""
    # Создаем контекст для шаблона
    context = {
        'certificate': certificate,
        'user': certificate.user,
        'category': certificate.category,
        'date': certificate.issued_at.strftime('%d.%m.%Y'),
        'qr_code': generate_certificate_qr(certificate)
    }
    
    # Получаем шаблон
    template = get_template('accounts/certificate_template.html')
    html = template.render(context)
    
    # Создаем PDF
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        # Сохраняем PDF в поле файла сертификата
        file_name = f"certificate_{certificate.certificate_id}.pdf"
        file_path = os.path.join(settings.MEDIA_ROOT, 'certificates', file_name)
        
        # Создаем директорию, если не существует
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Сохраняем файл
        with open(file_path, 'wb') as f:
            f.write(result.getvalue())
        
        # Обновляем поле файла в модели
        relative_path = os.path.join('certificates', file_name)
        certificate.certificate_file = relative_path
        certificate.save()
        
        return True
    
    return False

def generate_certificate_qr(certificate):
    """Генерирует QR-код для сертификата"""
    # Создаем QR-код с ссылкой для проверки сертификата
    verification_url = f"{settings.BASE_URL}/verify-certificate/{certificate.certificate_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)
    
    # Создаем изображение QR-кода
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Конвертируем изображение в base64 для вставки в HTML
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def get_achievement_progress(user, achievement):
    """Возвращает текущий прогресс пользователя по достижению"""
    if achievement.type == 'videos_watched':
        return UserActivity.objects.filter(user=user, activity_type='view_video').count()
    
    elif achievement.type == 'tests_passed':
        return TestResult.objects.filter(user=user, is_passed=True).count()
    
    elif achievement.type == 'perfect_score':
        return TestResult.objects.filter(user=user, percentage=100).count()
    
    elif achievement.type == 'login_streak':
        # Здесь должна быть логика подсчета последовательных дней входа
        # Временно возвращаем количество логинов
        return UserActivity.objects.filter(user=user, activity_type='login').count()
    
    elif achievement.type == 'category_complete':
        return LearningProgress.objects.filter(user=user, is_completed=True).count()
    
    elif achievement.type == 'level_reached':
        return user.level
    
    return 0

def check_category_completion_achievement(user):
    """Проверяет достижение по завершению категорий"""
    # Получаем количество завершенных категорий
    completed_categories = LearningProgress.objects.filter(
        user=user, is_completed=True
    ).count()
    
    # Получаем достижения по завершению категорий
    achievements = Achievement.objects.filter(
        type='category_complete'
    ).order_by('required_value')
    
    for achievement in achievements:
        # Если пользователь достиг требуемого значения
        if completed_categories >= achievement.required_value:
            # Создаем запись о достижении, если её еще нет
            user_achievement, created = UserAchievement.objects.get_or_create(
                user=user,
                achievement=achievement,
                defaults={'current_value': completed_categories}
            )
            
            # Если достижение было только что получено
            if created:
                # Даем пользователю опыт
                user.add_experience(achievement.experience_reward)
                
                # Записываем информацию о событии
                UserActivity.objects.create(
                    user=user,
                    activity_type='favorite_add',  # Используем существующий тип
                    details={
                        'action': 'achievement_earned',
                        'achievement_id': achievement.id,
                        'achievement_name': achievement.name,
                        'reward': achievement.experience_reward
                    }
                )
            # Если достижение уже было, обновляем его значение
            elif user_achievement.current_value < completed_categories:
                user_achievement.current_value = completed_categories
                user_achievement.save()
