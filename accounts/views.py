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
from django.urls import reverse
from django.templatetags.static import static

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
    
    # Рассчитываем статистику по тестам
    test_results = user.test_results.all()
    passed_tests_count = test_results.filter(is_passed=True).count()
    failed_tests_count = test_results.filter(is_passed=False).count()
    
    # Рассчитываем средний балл по тестам
    avg_score = 0
    if test_results.exists():
        avg_score = round(sum(result.percentage for result in test_results) / test_results.count(), 1)
    
    return render(request, 'accounts/profile.html', {
        'user': user,
        'favorites': favorites,
        'activities': activities,
        'avg_score': avg_score,
        'passed_tests_count': passed_tests_count,
        'failed_tests_count': failed_tests_count,
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
    from courses.models import Enrollment, Course, CompletedLesson
    
    # Получаем записи о зачислении пользователя на курсы
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
    
    # Обновляем статус завершения для каждой записи
    for enrollment in enrollments:
        enrollment.progress()
    
    # Получаем обновленные данные
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
    
    # Статистика по курсам
    enrolled_courses_count = enrollments.count()
    completed_courses_count = enrollments.filter(is_completed=True).count()
    active_courses_count = enrollments.filter(is_completed=False).count()
    
    # Средний балл по курсам
    average_score = 0
    if enrollments.count() > 0:
        total_progress = sum(enrollment.progress() for enrollment in enrollments)
        average_score = round(total_progress / enrollments.count())
    
    # Получаем активные курсы
    active_courses = []
    for enrollment in enrollments.filter(is_completed=False):
        # Получаем уроки и завершенные уроки
        total_lessons = enrollment.course.total_lessons()
        completed_lessons = CompletedLesson.objects.filter(
            enrollment=enrollment, user=request.user
        ).count()
        
        course_data = {
            'title': enrollment.course.title,
            'url': reverse('courses:detail', args=[enrollment.course.slug]),
            'image': enrollment.course.cover,
            'teacher': 'Администратор',
            'enrollment_date': enrollment.enrolled_at,
            'progress': enrollment.progress(),
            'completed_lessons': completed_lessons,
            'total_lessons': total_lessons
        }
        active_courses.append(course_data)
    
    # Получаем завершенные курсы
    completed_courses = []
    for enrollment in enrollments.filter(is_completed=True):
        course_data = {
            'title': enrollment.course.title,
            'url': reverse('courses:detail', args=[enrollment.course.slug]),
            'image': enrollment.course.cover,
            'teacher': 'Администратор',
            'completion_date': enrollment.completed_at,
            'score': 100,
            'has_certificate': hasattr(enrollment, 'certificate'),
            'certificate_id': enrollment.certificate.certificate_id if hasattr(enrollment, 'certificate') else None
        }
        completed_courses.append(course_data)
    
    # Сортируем по дате завершения (сначала недавние)
    completed_courses.sort(key=lambda x: x['completion_date'], reverse=True)
    
    # Получаем рекомендуемые курсы (курсы, на которые пользователь не записан)
    recommended_courses = Course.objects.filter(
        status='published'
    ).exclude(
        id__in=[enrollment.course.id for enrollment in enrollments]
    )[:3]
    
    context = {
        'enrolled_courses_count': enrolled_courses_count,
        'completed_courses_count': completed_courses_count,
        'active_courses_count': active_courses_count,
        'average_score': average_score,
        'active_courses': active_courses,
        'completed_courses': completed_courses,
        'recommended_courses': recommended_courses
    }
    
    return render(request, 'accounts/learning_progress.html', context)


@login_required
def user_achievements(request):
    """Страница с достижениями пользователя"""
    # Получаем достижения пользователя
    user_achievements = UserAchievement.objects.filter(user=request.user).select_related('achievement')
    
    # Получаем все достижения для отображения прогресса
    try:
        all_achievements = Achievement.objects.all()
        
        # Группируем достижения по типам
        achievement_types = dict(Achievement.ACHIEVEMENT_TYPES)
        achievements_by_type = {}
        
        # Создаем словарь с информацией о достижениях пользователя
        for ach_type, type_name in achievement_types.items():
            achievements_of_type = []
            
            for achievement in all_achievements.filter(type=ach_type):
                try:
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
                        try:
                            progress = get_achievement_progress(request.user, achievement)
                            required_value = achievement.required_value if achievement.required_value > 0 else 1
                            progress_percentage = min(100, int(progress / required_value * 100))
                        except:
                            progress = 0
                            progress_percentage = 0
                            
                        achievements_of_type.append({
                            'achievement': achievement,
                            'user_achievement': None,
                            'is_earned': False,
                            'progress': progress_percentage,
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
                except Exception as e:
                    # Если произошла ошибка при обработке достижения, пропускаем его
                    continue
            
            if achievements_of_type:
                achievements_by_type[type_name] = achievements_of_type
        
        # Безопасный расчет показателей
        total_achievements = all_achievements.count()
        earned_achievements = user_achievements.count()
        
        try:
            completion_percentage = (earned_achievements / total_achievements * 100) if total_achievements > 0 else 0
            total_experience_gained = sum(ua.achievement.experience_reward for ua in user_achievements)
        except:
            completion_percentage = 0
            total_experience_gained = 0
        
        context = {
            'achievements_by_type': achievements_by_type,
            'total_achievements': total_achievements,
            'earned_achievements': earned_achievements,
            'completion_percentage': completion_percentage,
            'total_experience_gained': total_experience_gained
        }
    except Exception as e:
        # В случае критической ошибки возвращаем пустой контекст
        context = {
            'achievements_by_type': {},
            'total_achievements': 0,
            'earned_achievements': 0,
            'completion_percentage': 0,
            'total_experience_gained': 0,
            'error_message': 'Ошибка при загрузке достижений'
        }
    
    return render(request, 'accounts/user_achievements.html', context)


@login_required
def user_certificates(request):
    """Страница с сертификатами пользователя"""
    # Получаем сертификаты пользователя (категории)
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
    
    # Обогащаем данные сертификатов для шаблона
    enriched_certificates = []
    for cert in certificates:
        # Определяем данные для отображения в шаблоне
        enriched_cert = {
            'id': cert.id,
            'category': cert.category,
            'issued_at': cert.issued_at,
            'certificate_id': cert.certificate_id,
            'name': cert.category.name,
            'type': 'category',
            'type_display': 'Категория',
            'issue_date': cert.issued_at,
            'score': 100,
            'instructor': 'Администратор системы',
            'duration': '4 недели',
            'view_url': f"#preview-{cert.id}",
            'download_url': reverse('accounts:download_certificate', args=[cert.id]),
            'background_image': static('img/certificate-background.jpg') if os.path.exists(
                os.path.join(settings.STATIC_ROOT, 'img/certificate-background.jpg')
            ) else None
        }
        enriched_certificates.append(enriched_cert)
    
    # Получаем сертификаты курсов пользователя
    from courses.models import CourseCertificate, Enrollment, Course
    
    course_certificates = CourseCertificate.objects.filter(
        enrollment__user=request.user
    ).select_related('enrollment__course')
    
    # Добавляем сертификаты курсов
    for cert in course_certificates:
        course = cert.enrollment.course
        
        # Проверяем и получаем создателя курса, если он существует
        course_creator = 'Администратор системы'
        try:
            if hasattr(course, 'creator') and course.creator:
                if hasattr(course.creator, 'get_full_name') and course.creator.get_full_name():
                    course_creator = course.creator.get_full_name()
        except:
            pass
        
        # Форматируем продолжительность курса
        if course.duration:
            hours = course.duration // 60
            minutes = course.duration % 60
            if hours > 0:
                duration = f"{hours} час. {minutes} мин." if minutes > 0 else f"{hours} час."
            else:
                duration = f"{minutes} мин."
        else:
            duration = "Не указано"
        
        course_cert = {
            'id': f"course_{cert.id}",  # Добавляем префикс для уникальности
            'issued_at': cert.issue_date,
            'certificate_id': cert.certificate_id,
            'name': cert.title,
            'type': 'course',
            'type_display': 'Курс',
            'issue_date': cert.issue_date,
            'score': 100,
            'instructor': course_creator,
            'duration': duration,
            'view_url': reverse('courses:view_certificate', args=[cert.certificate_id]),
            'download_url': reverse('courses:download_certificate', args=[cert.certificate_id]),
            'background_image': cert.preview_image.url if cert.preview_image else None
        }
        enriched_certificates.append(course_cert)
    
    # Сортируем все сертификаты по дате выдачи (сначала новые)
    enriched_certificates.sort(key=lambda x: x['issue_date'], reverse=True)
    
    context = {
        'certificates': enriched_certificates,
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
    
    # Безопасно получаем результаты тестов
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
    ).values('timestamp__date').annotate(
        count=Count('id'),
        total_duration=Sum('duration', default=0)
    ).order_by('timestamp__date')
    
    activity_data = {
        'labels': [item['timestamp__date'].strftime('%d.%m.%Y') for item in daily_activity],
        'data': [item['total_duration'] for item in daily_activity]
    }
    
    # Получаем информацию о курсах пользователя
    from courses.models import Enrollment, Course, CompletedLesson
    
    # Получаем все записи пользователя на курсы
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
    
    # Принудительно обновляем статус завершения для каждой записи на курс
    for enrollment in enrollments:
        # Вызываем метод progress() для проверки и обновления статуса
        enrollment.progress()
    
    # Обновляем запрос после возможных изменений
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
    
    # Общая статистика по курсам
    enrolled_courses_count = enrollments.count()
    completed_courses_count = enrollments.filter(is_completed=True).count()
    active_courses_count = enrollments.filter(is_completed=False).count()
    
    # Завершенные курсы в процентном соотношении
    completed_courses_percentage = (completed_courses_count / enrolled_courses_count * 100) if enrolled_courses_count > 0 else 0
    
    # Подготовка данных о курсах для отображения в таблице
    courses_data = []
    total_scores = 0
    courses_with_scores = 0
    
    for enrollment in enrollments:
        # Получаем завершенные уроки для этой конкретной записи
        completed_lessons_count = CompletedLesson.objects.filter(
            enrollment=enrollment,
            user=request.user
        ).count()
        
        total_lessons = enrollment.course.total_lessons()
        progress_percentage = (completed_lessons_count / total_lessons * 100) if total_lessons > 0 else 0
        
        # Безопасно получаем результаты тестов пользователя по этому курсу
        try:
            course_test_results = TestResult.objects.filter(
                user=request.user,
                test__lesson__module__course=enrollment.course
            )
            
            # Средний балл по курсу
            if course_test_results.exists():
                course_score = course_test_results.aggregate(avg_score=Avg('score'))['avg_score']
                total_scores += course_score
                courses_with_scores += 1
            else:
                course_score = progress_percentage  # Если нет тестов, используем прогресс
                total_scores += course_score
                courses_with_scores += 1
        except Exception as e:
            # Если произошла ошибка при получении результатов тестов, используем прогресс
            course_score = progress_percentage
            total_scores += course_score
            courses_with_scores += 1
        
        # Безопасно получаем данные о создателе курса
        try:
            teacher = enrollment.course.creator.get_full_name() if hasattr(enrollment.course, 'creator') and enrollment.course.creator else 'Администратор'
        except:
            teacher = 'Администратор'
        
        # Информация о курсе для шаблона
        course_info = {
            'title': enrollment.course.title,
            'url': reverse('courses:detail', args=[enrollment.course.slug]),
            'teacher': teacher,
            'progress': int(progress_percentage),
            'score': int(course_score),
            'completion_date': enrollment.completed_at if enrollment.is_completed else None
        }
        
        courses_data.append(course_info)
    
    # Сортируем курсы - сначала завершенные, затем по прогрессу
    courses_data.sort(key=lambda x: (-1 if x['completion_date'] else 0, x['progress']), reverse=True)
    
    # Средний балл по всем курсам
    average_score = int(total_scores / courses_with_scores) if courses_with_scores > 0 else 0
    
    # Статистика активности по дням недели (для графика)
    # Получаем данные за последние 30 дней
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    
    # Получаем активность пользователя за последнюю неделю по дням недели
    weekly_activity = UserActivity.objects.filter(
        user=request.user,
        timestamp__range=[week_ago, now]
    ).values('timestamp__week_day').annotate(
        count=Count('id'),
        total_duration=Sum('duration', default=0)
    ).order_by('timestamp__week_day')
    
    # Словарь для преобразования номера дня недели в название
    weekdays = {
        1: 'Dushanba',
        2: 'Seshanba',
        3: 'Chorshanba',
        4: 'Payshanba',
        5: 'Juma',
        6: 'Shanba',
        7: 'Yakshanba'
    }
    
    # Создаем полный набор данных для всех дней недели (даже если нет активности)
    weekly_data = {day: 0 for day in range(1, 8)}
    for item in weekly_activity:
        day_num = item['timestamp__week_day']
        weekly_data[day_num] = item['total_duration']
    
    # Формируем данные для графика
    weekly_activity_data = {
        'labels': [weekdays[day] for day in sorted(weekly_data.keys())],
        'data': [weekly_data[day] for day in sorted(weekly_data.keys())]
    }
    
    context = {
        'user_points': request.user.experience_points,
        'user_points_percentage': min(100, request.user.experience_points / 1000 * 100),
        'view_count': view_count,
        'tests_taken': tests_taken,
        'tests_passed': tests_passed,
        'pass_rate': int(pass_rate),
        'xp_stats': xp_stats,
        'recent_achievements': recent_achievements,
        'level_ups': level_ups,
        'activity_data': activity_data,
        'enrolled_courses_count': enrolled_courses_count,
        'completed_courses_count': completed_courses_count,
        'active_courses_count': active_courses_count,
        'completed_courses_percentage': int(completed_courses_percentage),
        'courses': courses_data,
        'average_score': average_score,
        'weekly_activity': weekly_activity_data
    }
    
    return render(request, 'accounts/user_statistics.html', context)


# Вспомогательные функции

def generate_certificate_file(certificate):
    """Генерирует PDF файл сертификата"""
    try:
        # Создаем контекст для шаблона
        verification_url = f"{settings.BASE_URL}/verify-certificate/{certificate.certificate_id}"
        
        try:
            qr_code_url = generate_certificate_qr(certificate)
        except Exception:
            # В случае ошибки генерации QR-кода используем пустое значение
            qr_code_url = ""
        
        # Получаем путь к изображению подписи или используем заглушку
        signature_path = os.path.join(settings.STATIC_ROOT, 'img/signature.png')
        if os.path.exists(signature_path):
            # Если файл существует, кодируем его в base64
            try:
                with open(signature_path, 'rb') as img_file:
                    signature_data = base64.b64encode(img_file.read()).decode('utf-8')
                    signature_url = f"data:image/png;base64,{signature_data}"
            except Exception:
                signature_url = ""
        else:
            # Если файла нет, используем пустую строку
            signature_url = ""
            
        context = {
            'certificate': certificate,
            'user': certificate.user,
            'category': certificate.category,
            'date': certificate.issued_at.strftime('%d.%m.%Y'),
            'qr_code': qr_code_url,
            'qr_code_url': qr_code_url,
            'verification_url': verification_url,
            'signature_url': signature_url
        }
        
        # Получаем шаблон
        try:
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
                try:
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    
                    # Сохраняем файл
                    with open(file_path, 'wb') as f:
                        f.write(result.getvalue())
                    
                    # Обновляем поле файла в модели
                    relative_path = os.path.join('certificates', file_name)
                    certificate.certificate_file = relative_path
                    certificate.save()
                    
                    return True
                except Exception:
                    # Если не удалось сохранить файл
                    return False
        except Exception:
            # Если не удалось создать шаблон или PDF
            return False
        
        return False
    except Exception:
        # В случае любой критической ошибки
        return False

def generate_certificate_qr(certificate):
    """Генерирует QR-код для сертификата"""
    try:
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
    except Exception as e:
        # В случае любой ошибки возвращаем пустую строку
        return ""

def get_achievement_progress(user, achievement):
    """Возвращает текущий прогресс пользователя по достижению"""
    try:
        if achievement.type == 'videos_watched':
            return UserActivity.objects.filter(user=user, activity_type='view_video').count()
        
        elif achievement.type == 'tests_passed':
            try:
                return TestResult.objects.filter(user=user, is_passed=True).count()
            except:
                # Если возникла ошибка при доступе к TestResult, возвращаем 0
                return 0
        
        elif achievement.type == 'perfect_score':
            try:
                return TestResult.objects.filter(user=user, percentage=100).count()
            except:
                # Если возникла ошибка при доступе к TestResult, возвращаем 0
                return 0
        
        elif achievement.type == 'login_streak':
            # Здесь должна быть логика подсчета последовательных дней входа
            # Временно возвращаем количество логинов
            return UserActivity.objects.filter(user=user, activity_type='login').count()
        
        elif achievement.type == 'category_complete':
            try:
                return LearningProgress.objects.filter(user=user, is_completed=True).count()
            except:
                # Если возникла ошибка при доступе к LearningProgress, возвращаем 0
                return 0
        
        elif achievement.type == 'level_reached':
            return user.level
        
        return 0
    except Exception as e:
        # В случае любой другой ошибки возвращаем 0
        return 0

def check_category_completion_achievement(user):
    """Проверяет достижение по завершению категорий"""
    try:
        # Получаем количество завершенных категорий
        completed_categories = LearningProgress.objects.filter(
            user=user, is_completed=True
        ).count()
        
        # Получаем достижения по завершению категорий
        achievements = Achievement.objects.filter(
            type='category_complete'
        ).order_by('required_value')
        
        for achievement in achievements:
            try:
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
                        try:
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
                        except Exception as e:
                            # Если не удалось дать опыт или создать запись активности, продолжаем
                            pass
                    # Если достижение уже было, обновляем его значение
                    elif user_achievement.current_value < completed_categories:
                        user_achievement.current_value = completed_categories
                        user_achievement.save()
            except Exception as e:
                # Если произошла ошибка при обработке конкретного достижения, пропускаем его
                continue
    except Exception as e:
        # Если произошла критическая ошибка, просто выходим из функции
        pass
