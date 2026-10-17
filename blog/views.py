from django.shortcuts import render, get_object_or_404, redirect
from .models import (
    Category, Post, VideoView, Test, Question, Option, TestResult, UserAnswer,
    DocumentCategory, Document, DocumentView, DocumentDownload, DocumentAcknowledgment,
)
from django.contrib.auth.decorators import login_required
from accounts.models import UserActivity, LearningProgress, Certificate, UserAchievement, Achievement
from accounts.views import check_category_completion_achievement, generate_certificate_file
from django.db.models import Count, Q, Avg, Max, Min, Sum
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
import json
from datetime import datetime, timedelta
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.utils import timezone
from io import BytesIO, StringIO
import csv
import random
from django.db import models
import uuid

User = get_user_model()


def _deadline_tests_for_user(user):
    """Mandatory / deadline tests for reminders (role-scoped)."""
    today = timezone.localdate()
    qs = Test.objects.filter(is_active=True).exclude(deadline=None)
    if user.role != 'admin':
        qs = qs.filter(role=user.role)
    qs = qs.order_by('deadline')
    upcoming = []
    overdue = []
    for test in qs:
        passed = TestResult.objects.filter(
            user=user, test=test, is_passed=True
        ).exists()
        if passed:
            continue
        item = {
            'test': test,
            'days_left': test.days_until_deadline,
            'is_overdue': test.is_overdue,
            'is_mandatory': test.is_mandatory,
        }
        if test.deadline < today:
            overdue.append(item)
        else:
            upcoming.append(item)
    return upcoming, overdue


@login_required
def home(request):
    view_as_role = request.GET.get('view_as_role')
    is_admin = request.user.role == 'admin'
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

    upcoming_deadlines, overdue_deadlines = _deadline_tests_for_user(request.user)
    
    return render(request, 'blog/home.html', {
        'latest_posts': latest_posts,
        'is_admin': is_admin,
        'roles': roles,
        'selected_role': view_as_role,
        'upcoming_deadlines': upcoming_deadlines[:5],
        'overdue_deadlines': overdue_deadlines[:5],
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
    is_admin = request.user.role == 'admin'
    
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
    if request.user.role != 'admin' and post.role != request.user.role:
        # Перенаправляем на страницу категорий, если пользователь не имеет доступа
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
        
        # Добавляем очки опыта пользователю за просмотр видео
        request.user.add_experience(5)
        
        # Проверяем достижение по просмотру видео
        check_video_watching_achievement(request.user)
    else:
        # Добавляем очки опыта пользователю за просмотр текстового материала
        request.user.add_experience(2)
    
    # Создаем запись активности
    UserActivity.objects.create(
        user=request.user,
        activity_type=activity_type,
        post=post,
        ip_address=ip
    )
    
    # Обновляем прогресс обучения по категории
    learning_progress, created = LearningProgress.objects.get_or_create(
        user=request.user,
        category=post.category
    )
    
    # Добавляем пост в список просмотренных, если его там еще нет
    if post not in learning_progress.posts_viewed.all():
        learning_progress.posts_viewed.add(post)
        
        # Проверяем, завершена ли категория после добавления этого поста
        total_posts = Post.objects.filter(category=post.category).count()
        viewed_posts = learning_progress.posts_viewed.count()
        
        # Если все посты категории просмотрены, отмечаем категорию как завершенную
        if viewed_posts == total_posts and total_posts > 0:
            learning_progress.is_completed = True
            learning_progress.save()
            
            # Добавляем очки опыта за завершение категории
            request.user.add_experience(50)
            
            # Проверяем, нужно ли выдать сертификат
            if not Certificate.objects.filter(user=request.user, category=post.category).exists():
                certificate_id = f"CERT-{post.category.id}-{request.user.id}-{uuid.uuid4().hex[:8].upper()}"
                certificate = Certificate.objects.create(
                    user=request.user,
                    category=post.category,
                    certificate_id=certificate_id
                )
                generate_certificate_file(certificate)
                
                # Проверяем достижение "Завершение категории"
                check_category_completion_achievement(request.user)
                
                messages.success(
                    request, 
                    f"Поздравляем! Вы завершили категорию '{post.category.name}' и получили сертификат."
                )
    
    # Video ko'rganlar ro'yxati
    video_views = None
    if request.user.role == 'admin':  # Faqat adminlar ko'rishlar ro'yxatini ko'ra oladi
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
    if request.user.role != 'admin':
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
    end_date = timezone.localdate()
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
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    period = request.GET.get('period', 'day')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    now = timezone.now()
    
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

@login_required
def test_list(request):
    """Список доступных тестов для текущего пользователя"""
    from collections import defaultdict

    is_admin = request.user.role == 'admin'
    view_as_role = request.GET.get('role', '').strip() if is_admin else ''

    tests_qs = Test.objects.filter(is_active=True)
    if is_admin:
        if view_as_role:
            tests_qs = tests_qs.filter(role=view_as_role)
        tests = list(tests_qs.order_by('role', 'title'))
    else:
        tests = list(tests_qs.filter(role=request.user.role).order_by('title'))

    results = list(
        TestResult.objects.filter(user=request.user).order_by('-completed_at')
    )

    results_by_test = defaultdict(list)
    for result in results:
        results_by_test[result.test_id].append(result)

    test_status = {}
    for test in tests:
        test_results = results_by_test.get(test.id, [])
        best_result = max(test_results, key=lambda r: r.percentage) if test_results else None
        test_status[test.id] = {
            'attempts': len(test_results),
            'best_result': best_result,
            'last_attempt': test_results[0] if test_results else None,
        }

    total_tests_taken = len(results)
    tests_passed = sum(1 for r in results if r.is_passed)
    avg_score = (
        sum(r.percentage for r in results) / total_tests_taken
        if total_tests_taken
        else 0
    )

    upcoming_deadlines, overdue_deadlines = _deadline_tests_for_user(request.user)
    # Admin: show compact strip only (full list is below)
    upcoming_limit = 4 if is_admin else 8
    overdue_limit = 4 if is_admin else 8

    context = {
        'tests': tests,
        'test_status': test_status,
        'total_tests_taken': total_tests_taken,
        'tests_passed': tests_passed,
        'pass_rate': tests_passed / total_tests_taken * 100 if total_tests_taken > 0 else 0,
        'avg_score': avg_score,
        'upcoming_deadlines': upcoming_deadlines[:upcoming_limit],
        'overdue_deadlines': overdue_deadlines[:overdue_limit],
        'upcoming_more': max(0, len(upcoming_deadlines) - upcoming_limit),
        'overdue_more': max(0, len(overdue_deadlines) - overdue_limit),
        'is_admin': is_admin,
        'roles': User.ROLE_CHOICES if is_admin else None,
        'selected_role': view_as_role,
        'tests_count': len(tests),
    }

    return render(request, 'blog/test_list.html', context)

@login_required
def test_start(request, test_id):
    """Начало тестирования"""
    test = get_object_or_404(Test, id=test_id)
    
    # Проверяем, соответствует ли тест роли пользователя
    if test.role != request.user.role and request.user.role != 'admin':
        messages.error(request, "У вас нет доступа к этому тесту")
        return redirect('blog:test_list')
    
    # Проверяем, активен ли тест
    if not test.is_active:
        messages.error(request, "Этот тест в настоящее время недоступен")
        return redirect('blog:test_list')
    
    # Проверяем предварительно количество вопросов в тесте
    total_questions = test.get_total_questions()
    if total_questions == 0:
        messages.error(request, "В этом тесте нет вопросов")
        return redirect('blog:test_list')
    
    # Получаем вопросы для теста с проверкой на логическую связь
    filtered_questions = get_valid_questions(test, max_count=30)

    # Если нет логически правильных вопросов, возвращаем ошибку
    if not filtered_questions:
        messages.error(request, "В тесте недостаточно корректных вопросов. Пожалуйста, обратитесь к администратору.")
        return redirect('blog:test_list')

    # Har urinishda savollar tartibini aralashtiramiz (yodlab olishning oldini olish).
    random.shuffle(filtered_questions)
    max_questions = min(30, len(filtered_questions))
    questions = filtered_questions[:max_questions]

    # Har savol uchun variantlar tartibini ham shu urinish uchun belgilaymiz.
    option_orders = {}
    for question in questions:
        opt_ids = list(question.options.values_list('id', flat=True))
        random.shuffle(opt_ids)
        option_orders[str(question.id)] = opt_ids

    # Создаем сессионные данные для теста
    request.session['current_test'] = {
        'test_id': test.id,
        'started_at': timezone.now().isoformat(),
        'question_ids': [q.id for q in questions],
        'current_question': 0,
        'answers': {},
        'max_questions': max_questions,
        'option_orders': option_orders,
    }
    
    # Записываем начало теста в активность пользователя
    UserActivity.objects.create(
        user=request.user,
        activity_type='view_post',  # Используем существующий тип
        details={
            'action': 'test_start', 
            'test_id': test.id,
            'test_title': test.title,
            'questions_count': max_questions
        },
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    # Перенаправляем на первый вопрос
    return redirect('blog:test_question')

def get_valid_questions(test, max_count=30):
    """
    Получает вопросы теста с проверкой логической связи между 
    вопросами и вариантами ответов.
    
    Аргументы:
        test: объект Test, для которого нужно получить вопросы
        max_count: максимальное количество вопросов для проверки
    
    Возвращает:
        list: список объектов Question, прошедших проверку
    """
    # Barcha katalog savollarini olamiz, keyin aralashtiramiz —
    # doim bir xil birinchi N ta savol chiqib qolmasin.
    all_questions = list(
        Question.objects.filter(test=test).prefetch_related('options')
    )
    random.shuffle(all_questions)

    if not all_questions:
        return []

    # Список для хранения корректных вопросов
    valid_questions = []

    # Проверка каждого вопроса на соответствие с его вариантами ответов
    for question in all_questions:
        options = list(question.options.all())
        
        # Пропускаем вопросы без вариантов ответов
        if not options:
            continue
        
        # Проверяем, есть ли у вопроса правильный вариант ответа
        correct_option = question.get_correct_option()
        if not correct_option:
            continue
        
        # Запускаем проверку логической связи
        if check_question_options_consistency(question.text, options):
            valid_questions.append(question)
            
            # Если у нас уже достаточно вопросов, завершаем поиск
            if len(valid_questions) >= max_count:
                break
    
    return valid_questions

# Re-export for compatibility; implementation lives in blog.utils
from blog.utils import check_question_options_consistency  # noqa: F401,E402


def _test_time_remaining_seconds(test_data, test):
    """Qolgan soniyalar; muddat tugasa 0."""
    started = datetime.fromisoformat(test_data['started_at'])
    if timezone.is_naive(started):
        started = timezone.make_aware(started, timezone.get_current_timezone())
    elapsed = (timezone.now() - started).total_seconds()
    limit = max(1, int(test.time_limit or 30)) * 60
    return max(0, int(limit - elapsed))


@login_required
def test_question(request):
    """Отображение текущего вопроса теста"""
    # Проверяем, есть ли активный тест
    if 'current_test' not in request.session:
        messages.error(request, "Нет активного теста")
        return redirect('blog:test_list')
    
    test_data = request.session['current_test']
    test = get_object_or_404(Test, id=test_data['test_id'])

    remaining = _test_time_remaining_seconds(test_data, test)
    if remaining <= 0:
        messages.warning(request, "Vaqt tugadi — test yakunlandi.")
        return redirect('blog:test_finish')
    
    # Проверка на корректность индекса текущего вопроса
    current_idx = test_data.get('current_question', 0)
    question_ids = test_data.get('question_ids', [])
    total_questions = len(question_ids)
    
    if current_idx < 0 or current_idx >= total_questions:
        messages.error(request, "Ошибка при загрузке вопроса")
        return redirect('blog:test_list')
    
    # Получаем текущий вопрос
    question_id = question_ids[current_idx]
    question = get_object_or_404(Question.objects.prefetch_related('options'), id=question_id)

    # Variantlar tartibi — shu urinish uchun sessionda saqlangan (har kirishda yangi).
    options_by_id = {opt.id: opt for opt in question.options.all()}
    stored_order = (test_data.get('option_orders') or {}).get(str(question_id))
    if stored_order:
        options = [options_by_id[oid] for oid in stored_order if oid in options_by_id]
        # Yangi qo'shilgan variantlar bo'lsa — oxiriga qo'shamiz
        missing = [opt for oid, opt in options_by_id.items() if oid not in set(stored_order)]
        if missing:
            random.shuffle(missing)
            options.extend(missing)
    else:
        options = list(options_by_id.values())
        random.shuffle(options)
        test_data.setdefault('option_orders', {})[str(question_id)] = [o.id for o in options]
        request.session['current_test'] = test_data

    # Вычисляем прогресс
    progress = (current_idx + 1) / total_questions * 100

    # Проверяем, был ли отправлен ответ
    if request.method == 'POST':
        selected_option_id = request.POST.get('option')

        if not selected_option_id:
            messages.error(request, "Пожалуйста, выберите вариант ответа")
        else:
            try:
                # Сохраняем ответ в сессии
                selected_id = int(selected_option_id)
                test_data['answers'][str(question_id)] = selected_id
                request.session['current_test'] = test_data

                # Переходим к следующему вопросу или завершаем тест
                if current_idx + 1 < total_questions:
                    test_data['current_question'] = current_idx + 1
                    request.session['current_test'] = test_data
                    return redirect('blog:test_question')
                else:
                    # Завершаем тест
                    return redirect('blog:test_finish')
            except (ValueError, TypeError):
                messages.error(request, "Некорректный формат ответа")

    context = {
        'test': test,
        'question': question,
        'options': options,
        'current': current_idx + 1,
        'total': total_questions,
        'progress': progress,
        'time_limit': test.time_limit,
        'time_remaining': remaining,
        'started_at': datetime.fromisoformat(test_data['started_at']),
    }

    return render(request, 'blog/test_question.html', context)

@login_required
def test_finish(request):
    """Завершение тестирования и сохранение результатов"""
    # Проверяем, есть ли активный тест
    if 'current_test' not in request.session:
        messages.error(request, "Нет активного теста")
        return redirect('blog:test_list')
    
    test_data = request.session['current_test']
    test = get_object_or_404(Test, id=test_data['test_id'])

    # Server-side timer: vaqt tugagan bo‘lsa ham natija saqlanadi
    timed_out = _test_time_remaining_seconds(test_data, test) <= 0
    
    # Получаем все вопросы теста и правильные ответы
    question_ids = test_data['question_ids']
    total_questions = len(question_ids)
    
    # Получаем все вопросы из базы данных одним запросом
    questions_db = Question.objects.filter(id__in=question_ids).prefetch_related('options')
    questions_dict = {q.id: q for q in questions_db}
    
    # Получаем все опции из базы одним запросом
    options_ids = list(map(int, test_data['answers'].values()))
    options_db = Option.objects.filter(id__in=options_ids)
    options_dict = {o.id: o for o in options_db}
    
    # Создаем объект результата теста
    test_result = TestResult.objects.create(
        user=request.user,
        test=test,
        score=0,  # Временное значение
        percentage=0,  # Временное значение
        is_passed=False,  # Временное значение
        started_at=datetime.fromisoformat(test_data['started_at']),
        completed_at=timezone.now()
    )
    
    # Проверяем ответы и создаем записи об ответах пользователя
    correct_answers = 0
    user_answers = []
    
    for question_id_str, answer_id_str in test_data['answers'].items():
        question_id = int(question_id_str)
        answer_id = int(answer_id_str)
        
        if question_id not in questions_dict:
            continue  # Пропускаем, если вопрос не найден
            
        question = questions_dict[question_id]
        selected_option = options_dict.get(answer_id)

        if not selected_option or selected_option.question_id != question_id:
            continue  # Noto‘g‘ri / o‘chirilgan variant — hisobga olinmaydi

        # Получаем правильный вариант для вопроса
        correct_option = question.get_correct_option()

        if not correct_option:
            continue  # Пропускаем, если нет правильного варианта

        is_correct = (selected_option.id == correct_option.id)
        
        if is_correct:
            correct_answers += 1
        
        # Создаем запись об ответе (добавляем в список для массовой вставки)
        user_answers.append(
            UserAnswer(
                test_result=test_result,
                question=question,
                selected_option=selected_option,
                is_correct=is_correct
            )
        )
    
    # Массовое создание записей ответов
    if user_answers:
        UserAnswer.objects.bulk_create(user_answers)
    
    # Обновляем результат теста
    score = correct_answers
    percentage = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    is_passed = percentage >= test.passing_score
    
    test_result.score = score
    test_result.percentage = percentage
    test_result.is_passed = is_passed
    test_result.save()
    
    # Записываем информацию о прохождении теста в активность пользователя
    UserActivity.objects.create(
        user=request.user,
        activity_type='view_post',  # Используем существующий тип
        details={
            'action': 'test_completed',
            'test_id': test.id,
            'test_title': test.title,
            'score': score,
            'percentage': percentage,
            'is_passed': is_passed
        },
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    # Даем пользователю опыт в зависимости от результата
    if is_passed:
        # Опыт за успешное прохождение
        if percentage == 100:
            # Идеальный результат
            request.user.add_experience(50)
            # Проверяем достижение "Идеальный результат теста"
            check_perfect_score_achievement(request.user)
        else:
            # Обычный успешный результат
            request.user.add_experience(25)
    else:
        # Небольшой опыт за попытку
        request.user.add_experience(5)
    
    # Проверяем достижение "Прохождение тестов"
    check_tests_passed_achievement(request.user)
    
    # Очищаем данные о текущем тесте в сессии
    del request.session['current_test']
    
    # Перенаправляем на страницу с результатами
    return redirect('blog:test_result', result_id=test_result.id)

@login_required
def test_result(request, result_id):
    """Отображение результатов теста"""
    # Получаем результат теста с предзагрузкой связанных данных
    result = get_object_or_404(
        TestResult.objects.select_related('user', 'test'),
        id=result_id
    )
    
    # Проверяем, принадлежит ли результат текущему пользователю
    if result.user != request.user and request.user.role != 'admin':
        messages.error(request, "У вас нет доступа к этому результату")
        return redirect('blog:test_list')
    
    # Получаем ответы пользователя с дополнительной предзагрузкой для оптимизации
    answers = result.answers.select_related(
        'question', 
        'selected_option'
    ).prefetch_related(
        'question__options'
    ).order_by('id')
    
    # Считаем статистику
    total_questions = answers.count()
    correct_answers = sum(1 for answer in answers if answer.is_correct)
    incorrect_answers = total_questions - correct_answers
    
    # Группируем данные для более удобного отображения
    grouped_result = {
        'summary': {
            'total': total_questions,
            'correct': correct_answers,
            'incorrect': incorrect_answers,
            'percentage': result.percentage,
            'is_passed': result.is_passed,
            'duration': result.get_duration(),
            'passing_score': result.test.passing_score,
        },
        'test': result.test,
        'user': result.user,
        'completed_at': result.completed_at,
    }
    
    context = {
        'result': result,
        'answers': answers,
        'total_questions': total_questions,
        'correct_answers': correct_answers,
        'incorrect_answers': incorrect_answers,
        'percentage': result.percentage,
        'is_passed': result.is_passed,
        'duration': result.get_duration(),
        'grouped_result': grouped_result,
    }
    
    return render(request, 'blog/test_result.html', context)

@login_required
def test_history(request):
    """История прохождения тестов пользователем"""
    # Получаем все результаты пользователя
    results = TestResult.objects.filter(user=request.user).order_by('-completed_at')
    
    # Считаем статистику
    total_tests = results.count()
    tests_passed = results.filter(is_passed=True).count()
    avg_score = results.aggregate(avg=Avg('percentage'))['avg'] or 0
    best_score = results.aggregate(max=Max('percentage'))['max'] or 0
    worst_score = results.aggregate(min=Min('percentage'))['min'] or 0
    
    # Статистика по времени
    avg_duration = results.aggregate(
        avg=Avg(models.F('completed_at') - models.F('started_at'))
    )['avg'] or 0
    avg_duration_minutes = avg_duration.total_seconds() / 60 if avg_duration else 0
    
    # Группируем результаты по тестам
    tests_data = {}
    for result in results:
        if result.test.id not in tests_data:
            tests_data[result.test.id] = {
                'test': result.test,
                'attempts': 0,
                'passed': 0,
                'avg_score': 0,
                'best_result': None,
                'results': []
            }
        
        data = tests_data[result.test.id]
        data['attempts'] += 1
        if result.is_passed:
            data['passed'] += 1
        data['results'].append(result)
        
        # Обновляем лучший результат
        if data['best_result'] is None or result.percentage > data['best_result'].percentage:
            data['best_result'] = result
    
    # Рассчитываем средний балл для каждого теста
    for test_id, data in tests_data.items():
        if data['attempts'] > 0:
            total_score = sum(r.percentage for r in data['results'])
            data['avg_score'] = total_score / data['attempts']
    
    context = {
        'results': results,
        'total_tests': total_tests,
        'tests_passed': tests_passed,
        'pass_rate': tests_passed / total_tests * 100 if total_tests > 0 else 0,
        'avg_score': avg_score,
        'best_score': best_score,
        'worst_score': worst_score,
        'avg_duration_minutes': avg_duration_minutes,
        'tests_data': tests_data,
    }
    
    return render(request, 'blog/test_history.html', context)

@login_required
def test_analytics(request):
    """Аналитика тестирования (только для админов)"""
    # Проверка доступа - только для администраторов
    if request.user.role != 'admin':
        messages.error(request, "У вас нет доступа к этой странице")
        return redirect('blog:home')
    
    # Получаем все результаты тестов
    results = TestResult.objects.all().select_related('user', 'test')
    
    # Общая статистика
    total_tests_taken = results.count()
    total_users = results.values('user').distinct().count()
    total_tests = Test.objects.count()
    
    # Статистика по ролям
    role_stats = TestResult.objects.values('user__role').annotate(
        count=Count('id'),
        passed=Count('id', filter=Q(is_passed=True)),
        avg_score=Avg('percentage')
    ).order_by('user__role')
    
    # Преобразуем для отображения в шаблоне
    for stat in role_stats:
        role_key = stat['user__role']
        stat['role_display'] = dict(User.ROLE_CHOICES).get(role_key, role_key or 'Noma\'lum')
        stat['pass_rate'] = stat['passed'] / stat['count'] * 100 if stat['count'] > 0 else 0
    
    # Топ-5 тестов по сложности (низкий процент прохождения)
    hardest_tests = Test.objects.annotate(
        attempts=Count('results'),
        passed=Count('results', filter=Q(results__is_passed=True)),
        avg_score=Avg('results__percentage')
    ).filter(attempts__gt=0).order_by('avg_score')[:5]
    
    # Топ-5 тестов по легкости (высокий процент прохождения)
    easiest_tests = Test.objects.annotate(
        attempts=Count('results'),
        passed=Count('results', filter=Q(results__is_passed=True)),
        avg_score=Avg('results__percentage')
    ).filter(attempts__gt=0).order_by('-avg_score')[:5]
    
    # Топ-5 пользователей по среднему баллу
    top_users = User.objects.annotate(
        tests_taken=Count('test_results'),
        avg_score=Avg('test_results__percentage')
    ).filter(tests_taken__gt=0).order_by('-avg_score')[:5]
    
    # Данные для графика по дням
    end_date = timezone.localdate()
    start_date = end_date - timedelta(days=30)
    
    tests_by_day = TestResult.objects.filter(
        completed_at__date__range=[start_date, end_date]
    ).annotate(
        date=TruncDate('completed_at')
    ).values('date').annotate(
        count=Count('id'),
        passed=Count('id', filter=Q(is_passed=True)),
        avg_score=Avg('percentage')
    ).order_by('date')
    
    # Преобразуем данные для графика
    daily_data = {
        'labels': [item['date'].strftime('%d.%m.%Y') for item in tests_by_day],
        'datasets': [
            {
                'label': 'Количество тестов',
                'data': [item['count'] for item in tests_by_day],
                'borderColor': '#4f46e5',
                'backgroundColor': 'rgba(79, 70, 229, 0.2)',
            },
            {
                'label': 'Пройдено тестов',
                'data': [item['passed'] for item in tests_by_day],
                'borderColor': '#10b981',
                'backgroundColor': 'rgba(16, 185, 129, 0.2)',
            },
            {
                'label': 'Средний балл (%)',
                'data': [round(item['avg_score'] or 0, 1) for item in tests_by_day],
                'borderColor': '#f59e0b',
                'backgroundColor': 'rgba(245, 158, 11, 0.2)',
                'yAxisID': 'y1',
            }
        ]
    }
    
    context = {
        'total_tests_taken': total_tests_taken,
        'total_users': total_users,
        'total_tests': total_tests,
        'role_stats': role_stats,
        'hardest_tests': hardest_tests,
        'easiest_tests': easiest_tests,
        'top_users': top_users,
        'daily_data_json': json.dumps(daily_data),
    }
    
    return render(request, 'blog/test_analytics.html', context)

# Вспомогательные функции для проверки достижений

def check_video_watching_achievement(user):
    """Проверяет достижение по просмотру видео"""
    # Получаем количество просмотренных видео
    videos_watched = UserActivity.objects.filter(user=user, activity_type='view_video').count()
    
    # Получаем достижения по просмотру видео
    achievements = Achievement.objects.filter(
        type='videos_watched'
    ).order_by('required_value')
    
    for achievement in achievements:
        # Если пользователь достиг требуемого значения
        if videos_watched >= achievement.required_value:
            # Создаем запись о достижении, если её еще нет
            user_achievement, created = UserAchievement.objects.get_or_create(
                user=user,
                achievement=achievement,
                defaults={'current_value': videos_watched}
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
            elif user_achievement.current_value < videos_watched:
                user_achievement.current_value = videos_watched
                user_achievement.save()

def check_perfect_score_achievement(user):
    """Проверяет достижение за идеальные результаты тестов"""
    # Получаем количество тестов с идеальным результатом
    perfect_scores = TestResult.objects.filter(user=user, percentage=100).count()
    
    # Получаем достижения за идеальные результаты
    achievements = Achievement.objects.filter(
        type='perfect_score'
    ).order_by('required_value')
    
    for achievement in achievements:
        # Если пользователь достиг требуемого значения
        if perfect_scores >= achievement.required_value:
            # Создаем запись о достижении, если её еще нет
            user_achievement, created = UserAchievement.objects.get_or_create(
                user=user,
                achievement=achievement,
                defaults={'current_value': perfect_scores}
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
            elif user_achievement.current_value < perfect_scores:
                user_achievement.current_value = perfect_scores
                user_achievement.save()

def check_tests_passed_achievement(user):
    """Проверяет достижение за прохождение тестов"""
    # Получаем количество успешно пройденных тестов
    tests_passed = TestResult.objects.filter(user=user, is_passed=True).count()
    
    # Получаем достижения за прохождение тестов
    achievements = Achievement.objects.filter(
        type='tests_passed'
    ).order_by('required_value')
    
    for achievement in achievements:
        # Если пользователь достиг требуемого значения
        if tests_passed >= achievement.required_value:
            # Создаем запись о достижении, если её еще нет
            user_achievement, created = UserAchievement.objects.get_or_create(
                user=user,
                achievement=achievement,
                defaults={'current_value': tests_passed}
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
            elif user_achievement.current_value < tests_passed:
                user_achievement.current_value = tests_passed
                user_achievement.save()

# Document Management Views
@login_required
def document_list(request):
    """List all documents user has access to"""
    is_admin = request.user.role == 'admin' or request.user.is_staff
    documents = Document.objects.select_related(
        'category', 'uploaded_by'
    ).order_by('-uploaded_at')

    category_id = request.GET.get('category')
    if category_id:
        documents = documents.filter(category_id=category_id)

    # Filter in Python so role checks work on SQLite and PostgreSQL alike.
    if not is_admin:
        documents = [doc for doc in documents if doc.can_user_access(request.user)]
    else:
        documents = list(documents)

    categories = DocumentCategory.objects.all()

    context = {
        'documents': documents,
        'categories': categories,
        'selected_category': category_id,
        'is_admin': is_admin,
    }

    return render(request, 'blog/document_list.html', context)

@login_required
def document_detail(request, document_id):
    """View document details and track view"""
    document = get_object_or_404(Document, id=document_id)
    
    # Check if user can access this document
    if not document.can_user_access(request.user):
        messages.error(request, "Sizga bu hujjatga ruxsat yo'q")
        return redirect('blog:document_list')
    
    # Track view
    document.increment_view_count()
    DocumentView.objects.create(
        document=document,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR')
    )

    acknowledged = DocumentAcknowledgment.objects.filter(
        document=document, user=request.user
    ).exists()
    
    context = {
        'document': document,
        'is_admin': request.user.role == 'admin',
        'acknowledged': acknowledged,
    }
    
    return render(request, 'blog/document_detail.html', context)


@login_required
def document_acknowledge(request, document_id):
    """Xodim hujjat bilan tanishganini tasdiqlaydi."""
    if request.method != 'POST':
        return redirect('blog:document_detail', document_id=document_id)

    document = get_object_or_404(Document, id=document_id)
    if not document.can_user_access(request.user):
        messages.error(request, "Sizga bu hujjatga ruxsat yo'q")
        return redirect('blog:document_list')

    if not document.requires_acknowledgment:
        messages.info(request, "Bu hujjat uchun tasdiq talab qilinmaydi.")
        return redirect('blog:document_detail', document_id=document.id)

    DocumentAcknowledgment.objects.get_or_create(
        document=document,
        user=request.user,
        defaults={'ip_address': request.META.get('REMOTE_ADDR')},
    )
    messages.success(request, "Hujjat bilan tanishganingiz tasdiqlandi.")
    return redirect('blog:document_detail', document_id=document.id)

@login_required
def document_download(request, document_id):
    """Download document and track download"""
    document = get_object_or_404(Document, id=document_id)
    
    # Check if user can access this document
    if not document.can_user_access(request.user):
        messages.error(request, "Sizga bu hujjatga ruxsat yo'q")
        return redirect('blog:document_list')
    
    # Track download
    document.increment_download_count()
    DocumentDownload.objects.create(
        document=document,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    # Return file for download
    from django.http import FileResponse
    import os
    
    file_path = document.file.path
    if os.path.exists(file_path):
        response = FileResponse(open(file_path, 'rb'))
        response['Content-Type'] = 'application/octet-stream'
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response
    else:
        messages.error(request, "Fayl topilmadi")
        return redirect('blog:document_detail', document_id=document_id)

@login_required
def document_upload(request):
    """Admin view for uploading documents"""
    from .forms import DocumentUploadForm

    if request.user.role != 'admin':
        messages.error(request, "Sizga bu sahifaga ruxsat yo'q")
        return redirect('blog:home')

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.uploaded_by = request.user
            document.allowed_roles = form.cleaned_data['allowed_roles']
            document.save()

            messages.success(request, f"Hujjat '{document.title}' muvaffaqiyatli yuklandi")
            return redirect('blog:document_list')
        messages.error(request, "Xatolik yuz berdi. Iltimos, ma'lumotlarni tekshiring")
    else:
        form = DocumentUploadForm()

    return render(request, 'blog/document_upload.html', {'form': form})

@login_required
def document_analytics(request):
    """Admin view for document analytics"""
    # Check if user is admin
    if request.user.role != 'admin':
        messages.error(request, "Sizga bu sahifaga ruxsat yo'q")
        return redirect('blog:home')
    
    # Get analytics data
    total_documents = Document.objects.count()
    total_views = DocumentView.objects.count()
    total_downloads = DocumentDownload.objects.count()
    
    # Views by category
    views_by_category = (DocumentView.objects
                        .values('document__category__name')
                        .annotate(count=Count('id'))
                        .order_by('-count'))
    
    # Downloads by category
    downloads_by_category = (DocumentDownload.objects
                            .values('document__category__name')
                            .annotate(count=Count('id'))
                            .order_by('-count'))
    
    # Most viewed documents
    most_viewed = (Document.objects
                  .annotate(view_count=Count('views'))
                  .order_by('-view_count')[:10])
    
    # Most downloaded documents
    most_downloaded = (Document.objects
                      .annotate(download_count=Count('downloads'))
                      .order_by('-download_count')[:10])
    
    # Views by user role
    views_by_role = (DocumentView.objects
                    .values('user__role')
                    .annotate(count=Count('id'))
                    .order_by('-count'))
    
    context = {
        'total_documents': total_documents,
        'total_views': total_views,
        'total_downloads': total_downloads,
        'views_by_category': views_by_category,
        'downloads_by_category': downloads_by_category,
        'most_viewed': most_viewed,
        'most_downloaded': most_downloaded,
        'views_by_role': views_by_role,
    }
    
    return render(request, 'blog/document_analytics.html', context)


@login_required
def hr_reports(request):
    """Admin HR report page + CSV/PDF export by role."""
    if request.user.role != 'admin' and not request.user.is_staff:
        messages.error(request, "Sizga bu sahifaga ruxsat yo'q")
        return redirect('blog:home')

    role = request.GET.get('role', '')
    export = request.GET.get('export', '')

    results = TestResult.objects.select_related('user', 'test').order_by(
        '-completed_at'
    )
    if role:
        results = results.filter(user__role=role)

    if export == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="hr_test_report.csv"'
        response.write('\ufeff')  # Excel UTF-8 BOM
        writer = csv.writer(response)
        writer.writerow([
            'Foydalanuvchi', 'Ism', 'Rol', 'Test', 'Ball %', 'O\'tdi', 'Sana',
        ])
        for r in results:
            writer.writerow([
                r.user.username,
                r.user.get_full_name(),
                r.user.get_role_display(),
                r.test.title,
                f'{r.percentage:.1f}',
                'Ha' if r.is_passed else "Yo'q",
                r.completed_at.strftime('%d.%m.%Y %H:%M'),
            ])
        return response

    if export == 'pdf':
        from xhtml2pdf import pisa
        rows_html = ''.join(
            f'<tr>'
            f'<td>{r.user.username}</td>'
            f'<td>{r.user.get_full_name()}</td>'
            f'<td>{r.user.get_role_display()}</td>'
            f'<td>{r.test.title}</td>'
            f'<td>{r.percentage:.1f}%</td>'
            f'<td>{"Ha" if r.is_passed else "Yoq"}</td>'
            f'<td>{r.completed_at.strftime("%d.%m.%Y")}</td>'
            f'</tr>'
            for r in results[:500]
        )
        html = f"""
        <html><head><meta charset="utf-8"/>
        <style>
          body {{ font-family: DejaVu Sans, sans-serif; font-size: 11px; }}
          table {{ width: 100%; border-collapse: collapse; }}
          th, td {{ border: 1px solid #ccc; padding: 4px; text-align: left; }}
          th {{ background: #eee; }}
        </style></head><body>
        <h2>HR test hisoboti</h2>
        <p>Rol filtri: {role or "barcha"}</p>
        <table>
          <thead>
            <tr>
              <th>User</th><th>Ism</th><th>Rol</th><th>Test</th>
              <th>%</th><th>O'tdi</th><th>Sana</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        </body></html>
        """
        result_buf = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode('utf-8')), result_buf)
        if pdf.err:
            messages.error(request, "PDF yaratib bo'lmadi")
            return redirect('blog:hr_reports')
        response = HttpResponse(result_buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="hr_test_report.pdf"'
        return response

    by_role = (
        results.values('user__role')
        .annotate(
            attempts=Count('id'),
            passed=Count('id', filter=Q(is_passed=True)),
            avg_score=Avg('percentage'),
        )
        .order_by('user__role')
    )

    return render(request, 'blog/hr_reports.html', {
        'results': results[:100],
        'by_role': by_role,
        'roles': User.ROLE_CHOICES,
        'selected_role': role,
        'total_results': results.count(),
    })


@login_required
def hr_compliance(request):
    """Birlashtirilgan HR compliance: majburiy testlar, hujjat tasdiqlari, sertifikat muddati."""
    if request.user.role != 'admin' and not request.user.is_staff:
        messages.error(request, "Sizga bu sahifaga ruxsat yo'q")
        return redirect('blog:home')

    today = timezone.localdate()
    role = request.GET.get('role', '')
    users = User.objects.filter(is_active=True).exclude(role='admin').select_related('department')
    if role:
        users = users.filter(role=role)

    mandatory_tests = list(
        Test.objects.filter(is_active=True, is_mandatory=True).exclude(deadline=None)
    )
    ack_docs = list(Document.objects.filter(requires_acknowledgment=True))

    rows = []
    non_compliant = 0
    for user in users:
        overdue = []
        for test in mandatory_tests:
            if test.role != user.role:
                continue
            if test.deadline and test.deadline < today:
                passed = TestResult.objects.filter(
                    user=user, test=test, is_passed=True
                ).exists()
                if not passed:
                    overdue.append(test)

        missing_acks = []
        for doc in ack_docs:
            if not doc.can_user_access(user):
                continue
            if not DocumentAcknowledgment.objects.filter(document=doc, user=user).exists():
                missing_acks.append(doc)

        from accounts.models import Certificate as CatCert
        from courses.models import CourseCertificate

        cat_certs = list(
            CatCert.objects.filter(user=user, valid_until__isnull=False)
            .filter(valid_until__lte=today + timedelta(days=30))
            .select_related('category')[:5]
        )
        course_certs = list(
            CourseCertificate.objects.filter(
                enrollment__user=user, valid_until__isnull=False
            )
            .filter(valid_until__lte=today + timedelta(days=30))
            .select_related('enrollment__course')[:5]
        )
        expiring_certs = []
        for c in cat_certs:
            expiring_certs.append({
                'title': c.category.name,
                'valid_until': c.valid_until,
                'is_expired': c.is_expired,
            })
        for c in course_certs:
            expiring_certs.append({
                'title': c.enrollment.course.title,
                'valid_until': c.valid_until,
                'is_expired': c.is_expired,
            })

        has_expired_cert = any(c['is_expired'] for c in expiring_certs)
        ok = not overdue and not missing_acks and not has_expired_cert
        if not ok:
            non_compliant += 1

        rows.append({
            'user': user,
            'overdue_tests': overdue,
            'missing_acks': missing_acks,
            'expiring_certs': expiring_certs,
            'is_compliant': ok,
        })

    export = request.GET.get('export', '')
    if export == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="hr_compliance.csv"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow([
            'Tabel', 'User', 'Ism', 'Rol', 'Bo‘lim', 'Smena',
            'Muddati o‘tgan testlar', 'Tasdiqlanmagan hujjatlar', 'Holat',
        ])
        for row in rows:
            u = row['user']
            writer.writerow([
                u.employee_id or '',
                u.username,
                u.get_full_name(),
                u.get_role_display(),
                u.department.name if u.department_id else '',
                u.get_shift_display() if u.shift else '',
                '; '.join(t.title for t in row['overdue_tests']),
                '; '.join(d.title for d in row['missing_acks']),
                'OK' if row['is_compliant'] else 'Muammo',
            ])
        return response

    return render(request, 'blog/hr_compliance.html', {
        'rows': rows,
        'roles': User.ROLE_CHOICES,
        'selected_role': role,
        'total_users': len(rows),
        'non_compliant': non_compliant,
        'compliant': len(rows) - non_compliant,
    })


@login_required
def compliance_hub(request):
    """Xodim uchun barcha compliance talablari markazi."""
    from blog.compliance import get_compliance_status

    status = get_compliance_status(request.user)
    return render(request, 'blog/compliance_hub.html', {
        'compliance': status,
    })
