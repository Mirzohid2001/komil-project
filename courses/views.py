from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.db.models import Q, Count, Avg
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .models import Course, Module, Lesson, Enrollment, CompletedLesson, CourseCategory, CourseCertificate
from accounts.models import UserActivity

import json
import uuid
import os
from django.conf import settings
from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa

def course_list(request, category_slug=None):
    """Отображение списка курсов с фильтрацией по категории"""
    categories = CourseCategory.objects.all()
    
    # Базовый запрос для опубликованных курсов
    courses = Course.objects.filter(status='published')
    
    # Фильтр по категории, если указан slug
    if category_slug:
        category = get_object_or_404(CourseCategory, slug=category_slug)
        courses = courses.filter(category=category)
    
    # Фильтры из параметров запроса
    difficulty = request.GET.get('difficulty')
    if difficulty:
        courses = courses.filter(difficulty=difficulty)
    
    price_filter = request.GET.get('price')
    if price_filter == 'free':
        courses = courses.filter(is_free=True)
    elif price_filter == 'paid':
        courses = courses.filter(is_free=False)
    
    # Сортировка
    sort = request.GET.get('sort', 'newest')
    if sort == 'newest':
        courses = courses.order_by('-created_at')
    elif sort == 'oldest':
        courses = courses.order_by('created_at')
    elif sort == 'name':
        courses = courses.order_by('title')
    elif sort == 'popular':
        courses = courses.annotate(students=Count('enrollments')).order_by('-students')
    
    # Пагинация
    paginator = Paginator(courses, 12)  # 12 курсов на страницу
    page = request.GET.get('page')
    try:
        courses = paginator.page(page)
    except PageNotAnInteger:
        courses = paginator.page(1)
    except EmptyPage:
        courses = paginator.page(paginator.num_pages)
    
    # Рекомендуемые курсы для боковой панели
    featured_courses = Course.objects.filter(status='published', is_featured=True)[:5]
    
    context = {
        'categories': categories,
        'courses': courses,
        'featured_courses': featured_courses,
        'current_category': category_slug,
        'difficulty_choices': Course.DIFFICULTY_CHOICES,
        'current_difficulty': difficulty,
        'current_price': price_filter,
        'current_sort': sort,
    }
    
    return render(request, 'courses/course_list.html', context)


def course_search(request):
    """Поиск курсов по ключевому слову"""
    query = request.GET.get('q', '')
    
    if query:
        # Поиск по названию, описанию, короткому описанию
        courses = Course.objects.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query) |
            Q(short_description__icontains=query),
            status='published'
        ).distinct()
    else:
        courses = Course.objects.none()
    
    # Пагинация
    paginator = Paginator(courses, 12)
    page = request.GET.get('page')
    try:
        courses = paginator.page(page)
    except PageNotAnInteger:
        courses = paginator.page(1)
    except EmptyPage:
        courses = paginator.page(paginator.num_pages)
    
    context = {
        'courses': courses,
        'query': query,
        'categories': CourseCategory.objects.all(),
    }
    
    return render(request, 'courses/course_search.html', context)


def course_detail(request, course_slug):
    """Детальная страница курса"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Проверка записи текущего пользователя на курс
    enrollment = None
    if request.user.is_authenticated:
        try:
            enrollment = Enrollment.objects.get(user=request.user, course=course)
        except Enrollment.DoesNotExist:
            pass
    
    # Получаем модули и уроки курса
    modules = course.modules.all().prefetch_related('lessons')
    
    # Статистика курса
    total_duration = course.total_duration()
    total_students = course.students_count()
    
    # Список бесплатных уроков для предпросмотра
    free_preview_lessons = Lesson.objects.filter(module__course=course, is_free_preview=True)
    
    # Отзывы и рейтинг
    # TODO: Добавить модель отзывов и расчет рейтинга
    
    # Убираем ссылку на teacher
    instructor_other_courses = []
    
    context = {
        'course': course,
        'enrollment': enrollment,
        'modules': modules,
        'total_duration': total_duration,
        'total_students': total_students,
        'free_preview_lessons': free_preview_lessons,
        'instructor_other_courses': instructor_other_courses,
    }
    
    # Записываем активность пользователя
    if request.user.is_authenticated:
        UserActivity.objects.create(
            user=request.user,
            activity_type='view_course',
            details={'course_id': course.id, 'course_title': course.title},
            ip_address=request.META.get('REMOTE_ADDR')
        )
    
    return render(request, 'courses/course_detail.html', context)


@login_required
def course_enroll(request, course_slug):
    """Запись на курс"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Проверка, не записан ли пользователь уже
    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.info(request, f"Siz allaqachon '{course.title}' kursiga yozilgansiz.")
        return redirect('courses:learn', course_slug=course.slug)
    
    # Обработка платежа, если курс платный
    if not course.is_free:
        # TODO: Реализовать логику обработки платежей
        messages.error(request, "Tizimda to'lov qilish hozircha mavjud emas.")
        return redirect('courses:detail', course_slug=course.slug)
    
    # Создаем запись о зачислении на курс
    enrollment = Enrollment.objects.create(
        user=request.user,
        course=course
    )
    
    # Записываем активность пользователя
    UserActivity.objects.create(
        user=request.user,
        activity_type='course_enrollment',
        details={'course_id': course.id, 'course_title': course.title},
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    messages.success(request, f"Siz muvaffaqiyatli ravishda '{course.title}' kursiga yozildingiz!")
    return redirect('courses:learn', course_slug=course.slug)


@login_required
def my_courses(request):
    """Список курсов пользователя"""
    # Получаем все записи на курсы текущего пользователя
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
    
    # Разделяем на активные и завершенные курсы
    active_enrollments = enrollments.filter(is_completed=False)
    completed_enrollments = enrollments.filter(is_completed=True)
    
    # Прогресс для активных курсов
    for enrollment in active_enrollments:
        enrollment.progress_percent = enrollment.progress()
    
    # Рекомендуемые курсы
    # TODO: Улучшить алгоритм рекомендаций на основе категорий пройденных курсов
    enrolled_course_ids = enrollments.values_list('course_id', flat=True)
    recommended_courses = Course.objects.filter(status='published').exclude(
        id__in=enrolled_course_ids
    ).order_by('?')[:4]  # Случайные 4 курса, которые пользователь еще не проходил
    
    context = {
        'active_enrollments': active_enrollments,
        'completed_enrollments': completed_enrollments,
        'recommended_courses': recommended_courses,
    }
    
    return render(request, 'courses/my_courses.html', context)


@login_required
def course_learn(request, course_slug):
    """Основная страница обучения по курсу"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Проверка, записан ли пользователь на курс
    try:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
    except Enrollment.DoesNotExist:
        messages.error(request, "Kursni ko'rish uchun avval ro'yxatdan o'ting")
        return redirect('courses:detail', course_slug=course.slug)
    
    # Получаем все модули и уроки курса
    modules = course.modules.all().prefetch_related('lessons')
    
    # Список выполненных уроков
    completed_lesson_ids = CompletedLesson.objects.filter(
        enrollment=enrollment
    ).values_list('lesson_id', flat=True)
    
    # Расчет прогресса
    total_lessons = course.total_lessons()
    completed_count = len(completed_lesson_ids)
    progress_percent = int((completed_count / total_lessons) * 100) if total_lessons > 0 else 0
    
    # Определение следующего урока для продолжения обучения
    next_lesson = None
    for module in modules:
        for lesson in module.lessons.all():
            if lesson.id not in completed_lesson_ids:
                next_lesson = lesson
                break
        if next_lesson:
            break
    
    # Проверка завершения курса
    if progress_percent == 100 and not enrollment.is_completed:
        enrollment.is_completed = True
        enrollment.completed_at = timezone.now()
        enrollment.save()
        
        # Создаем сертификат о прохождении курса
        certificate = create_course_certificate(enrollment)
        
        messages.success(request, f"Tabriklaymiz! Siz '{course.title}' kursini muvaffaqiyatli yakunladingiz!")
    
    context = {
        'course': course,
        'enrollment': enrollment,
        'modules': modules,
        'completed_lesson_ids': completed_lesson_ids,
        'progress_percent': progress_percent,
        'next_lesson': next_lesson,
        'total_lessons': total_lessons,
        'completed_count': completed_count,
    }
    
    return render(request, 'courses/course_learn.html', context)


@login_required
def module_detail(request, course_slug, module_id):
    """Детальная страница модуля курса"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    module = get_object_or_404(Module, id=module_id, course=course)
    
    # Проверка, записан ли пользователь на курс
    try:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
    except Enrollment.DoesNotExist:
        messages.error(request, "Kursni ko'rish uchun avval ro'yxatdan o'ting")
        return redirect('courses:detail', course_slug=course.slug)
    
    # Получаем уроки модуля
    lessons = module.lessons.all().order_by('order')
    
    # Список выполненных уроков
    completed_lesson_ids = CompletedLesson.objects.filter(
        enrollment=enrollment
    ).values_list('lesson_id', flat=True)
    
    context = {
        'course': course,
        'module': module,
        'lessons': lessons,
        'enrollment': enrollment,
        'completed_lesson_ids': completed_lesson_ids,
    }
    
    return render(request, 'courses/module_detail.html', context)


@login_required
def lesson_detail(request, course_slug, module_id, lesson_id):
    """
    Отображает детальную информацию об уроке и проверяет, что пользователь записан на курс.
    """
    course = get_object_or_404(Course, slug=course_slug)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)
    
    # Проверяем, записан ли пользователь на курс
    if not request.user.is_authenticated:
        messages.warning(request, "Darsni ko'rish uchun avval tizimga kirishingiz kerak.")
        return redirect('accounts:login')
    
    is_enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()
    if not is_enrolled and not request.user.is_staff:
        messages.warning(request, "Bu darsni ko'rish uchun kursga yozilishingiz kerak.")
        return redirect('courses:detail', course_slug=course_slug)

    # Получаем список модулей и уроков для навигации
    modules = course.modules.prefetch_related('lessons').all()
    
    # Получаем предыдущий и следующий уроки для навигации
    lessons_flat = []
    for m in modules:
        for l in m.lessons.all():
            lessons_flat.append({
                'module': m,
                'lesson': l
            })
    
    # Находим текущий индекс
    current_index = None
    for i, item in enumerate(lessons_flat):
        if item['lesson'].id == lesson.id:
            current_index = i
            break
    
    prev_lesson = None
    next_lesson = None
    
    if current_index is not None:
        if current_index > 0:
            prev_lesson_data = lessons_flat[current_index - 1]
            prev_lesson = {
                'module': prev_lesson_data['module'],
                'id': prev_lesson_data['lesson'].id
            }
        
        if current_index < len(lessons_flat) - 1:
            next_lesson_data = lessons_flat[current_index + 1]
            next_lesson = {
                'module': next_lesson_data['module'],
                'id': next_lesson_data['lesson'].id
            }
    
    # Проверяем, отмечен ли урок как завершенный
    is_completed = CompletedLesson.objects.filter(
        user=request.user,
        lesson=lesson
    ).exists()
    
    # Получаем список завершенных уроков для отображения в навигации
    completed_lessons = CompletedLesson.objects.filter(
        user=request.user,
        lesson__module__course=course
    )
    completed_lessons_ids = [completion.lesson.id for completion in completed_lessons]
    
    # Вычисляем прогресс курса
    total_lessons = Lesson.objects.filter(module__course=course).count()
    completed_count = completed_lessons.count()
    progress = 0
    if total_lessons > 0:
        progress = round((completed_count / total_lessons) * 100)
    
    # Подготовка контекста для шаблона
    context = {
        'course': course,
        'modules': modules,
        'current_module': module,
        'lesson': lesson,
        'prev_lesson': prev_lesson,
        'next_lesson': next_lesson,
        'is_completed': is_completed,
        'completed_lessons_ids': completed_lessons_ids,
        'progress': progress,
        'module': module,  # Добавляем для совместимости с формами
        'debug_info': {
            'lesson_type': lesson.lesson_type,
            'video_url': lesson.video_url,
            'video_file': lesson.video_file.url if lesson.video_file else None,
            'has_video_url': bool(lesson.video_url),
            'has_video_file': bool(lesson.video_file)
        }
    }
    
    return render(request, 'courses/lesson_detail.html', context)


@login_required
@require_POST
def complete_lesson(request, course_slug, lesson_id):
    """Отметить урок как выполненный"""
    course = get_object_or_404(Course, slug=course_slug)
    lesson = get_object_or_404(Lesson, id=lesson_id, module__course=course)
    
    # Получаем запись о зачислении
    try:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
    except Enrollment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Siz kursga yozilmagansiz'}, status=400)
    
    # Создаем или получаем запись о завершении урока
    completed_lesson, created = CompletedLesson.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
        defaults={'user': request.user}  # Добавляем user при создании
    )
    
    # Если запись уже существовала и не содержала user_id, обновляем её
    if not created and not hasattr(completed_lesson, 'user_id'):
        completed_lesson.user = request.user
        completed_lesson.save()
    
    # Получаем все уроки курса
    total_lessons = Lesson.objects.filter(module__course=course).count()
    # Получаем все завершенные уроки пользователя для этого курса
    completed_lessons_count = CompletedLesson.objects.filter(
        enrollment=enrollment,
        user=request.user
    ).count()
    
    # Вычисляем прогресс
    progress = 0
    if total_lessons > 0:
        progress = round((completed_lessons_count / total_lessons) * 100)
    
    # Проверяем завершение курса
    if progress == 100 and not enrollment.is_completed:
        enrollment.is_completed = True
        enrollment.completed_at = timezone.now()
        enrollment.save()
        
        # Создаем сертификат
        certificate = create_course_certificate(enrollment)
        
        # Обновляем опыт пользователя
        request.user.add_experience(200)  # Даем пользователю 200 XP за завершение курса
        
        # Записываем действие в активности пользователя
        UserActivity.objects.create(
            user=request.user,
            activity_type='profile_update',
            details={'action': 'course_completed', 'course_id': course.id, 'course_title': course.title}
        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Dars va kurs yakunlandi!',
            'progress': progress,
            'course_completed': True,
            'certificate_url': reverse('courses:view_certificate', args=[certificate.certificate_id]),
        })
    
    return JsonResponse({
        'status': 'success',
        'message': 'Dars yakunlandi!',
        'progress': progress,
        'course_completed': False,
    })


@login_required
@require_POST
def mark_lesson_incomplete(request, course_slug, module_id, lesson_id):
    """Отметить урок как не выполненный"""
    course = get_object_or_404(Course, slug=course_slug)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)
    
    # Получаем запись о зачислении
    try:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
        
        # Удаляем запись о завершении урока, если она существует
        CompletedLesson.objects.filter(
            enrollment=enrollment,
            lesson=lesson
        ).delete()
        
        # Если курс был отмечен как завершенный, а теперь прогресс не 100%, снимаем отметку
        if enrollment.is_completed:
            # Пересчитываем прогресс
            progress = enrollment.progress()
            
            if progress < 100:
                enrollment.is_completed = False
                enrollment.completed_at = None
                enrollment.save()
                # Опционально: удаляем сертификат
                CourseCertificate.objects.filter(enrollment__user=request.user, enrollment__course=course).delete()
    except Enrollment.DoesNotExist:
        # Если пользователь каким-то образом не записан на курс, просто игнорируем
        pass
    
    messages.success(request, "Dars tugallanmagan deb belgilandi")
    return redirect('courses:lesson_detail', course_slug=course_slug, module_id=module_id, lesson_id=lesson_id)


@login_required
@require_POST
def mark_lesson_complete(request, course_slug, module_id, lesson_id):
    """Отметить урок как выполненный"""
    course = get_object_or_404(Course, slug=course_slug)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)
    
    # Получаем запись о зачислении
    try:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
        
        # Создаем запись о завершении урока с указанием пользователя
        completed_lesson, created = CompletedLesson.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
            defaults={'user': request.user}  # Явно указываем пользователя
        )
        
        # Если запись уже существовала и не содержала user_id, обновляем её
        if not created and not hasattr(completed_lesson, 'user_id'):
            completed_lesson.user = request.user
            completed_lesson.save()
        
        # Обновляем состояние завершения курса
        # Получаем все уроки курса
        total_lessons = Lesson.objects.filter(module__course=course).count()
        # Получаем все завершенные уроки пользователя для этого курса
        completed_lessons_count = CompletedLesson.objects.filter(
            enrollment=enrollment,
            user=request.user
        ).count()
        
        # Вычисляем прогресс
        progress = 0
        if total_lessons > 0:
            progress = round((completed_lessons_count / total_lessons) * 100)
        
        # Если все уроки завершены (прогресс 100%), отмечаем курс как завершенный
        if progress == 100 and not enrollment.is_completed:
            enrollment.is_completed = True
            enrollment.completed_at = timezone.now()
            enrollment.save()
            
            # Создаем сертификат о прохождении курса
            certificate = create_course_certificate(enrollment)
            messages.success(request, f"Tabriklaymiz! Siz '{course.title}' kursini muvaffaqiyatli yakunladingiz!")
            
            # Обновляем опыт пользователя
            request.user.add_experience(200)  # Даем пользователю 200 XP за завершение курса
            
            # Записываем действие в активности пользователя
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_update',
                details={'action': 'course_completed', 'course_id': course.id, 'course_title': course.title}
            )
    except Enrollment.DoesNotExist:
        # Если пользователь каким-то образом не записан на курс, просто игнорируем
        pass
    
    messages.success(request, "Dars muvaffaqiyatli tugallandi")
    return redirect('courses:lesson_detail', course_slug=course_slug, module_id=module_id, lesson_id=lesson_id)


@login_required
def get_course_progress(request, course_slug):
    """AJAX API для получения прогресса по курсу"""
    course = get_object_or_404(Course, slug=course_slug)
    
    try:
        enrollment = Enrollment.objects.get(user=request.user, course=course)
        progress = enrollment.progress()
        
        # Получаем выполненные уроки
        completed_lessons = CompletedLesson.objects.filter(
            enrollment=enrollment
        ).values_list('lesson_id', flat=True)
        
        return JsonResponse({
            'status': 'success',
            'progress': progress,
            'completed_lessons': list(completed_lessons),
            'is_completed': enrollment.is_completed,
        })
    except Enrollment.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Siz kursga yozilmagansiz',
        }, status=400)


@login_required
def view_certificate(request, certificate_id):
    """Просмотр сертификата"""
    certificate = get_object_or_404(
        CourseCertificate,
        certificate_id=certificate_id
    )
    
    # Проверяем, что сертификат принадлежит пользователю или пользователь - администратор
    if certificate.enrollment.user != request.user and not request.user.is_staff:
        messages.error(request, "Sizda bu sertifikatni ko'rish huquqi yo'q")
        return redirect('accounts:dashboard')
    
    # Проверяем возможно устаревший сертификат
    if not certificate.enrollment.is_completed:
        messages.warning(request, "Bu sertifikat faol emas, chunki kurs tugallanmagan")
    
    context = {
        'certificate': certificate,
        'course': certificate.enrollment.course,
        'user': certificate.enrollment.user,
    }
    
    return render(request, 'courses/certificate.html', context)


@login_required
def download_certificate(request, certificate_id):
    """Скачивание PDF-файла сертификата"""
    certificate = get_object_or_404(CourseCertificate, certificate_id=certificate_id)
    
    # Проверка, что сертификат принадлежит пользователю
    if certificate.enrollment.user != request.user:
        raise Http404("Sertifikat topilmadi")
    
    # Если файл сертификата уже существует, возвращаем его
    if certificate.pdf_file:
        response = HttpResponse(certificate.pdf_file.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{certificate.certificate_id}.pdf"'
        return response
    
    # Если файла нет, создаем его
    # TODO: Создание PDF сертификата
    # В реальном проекте здесь будет логика для создания PDF
    
    # Временно возвращаем пустой PDF
    response = HttpResponse("Sertifikat hali yaratilmagan", content_type='text/plain')
    return response


# Вспомогательные функции

def create_course_certificate(enrollment):
    """Создание сертификата о прохождении курса"""
    # Генерируем уникальный ID сертификата
    certificate_id = str(uuid.uuid4())
    
    # Создаем запись о сертификате
    certificate = CourseCertificate.objects.create(
        enrollment=enrollment,
        certificate_id=certificate_id,
        title=f"{enrollment.course.title} kursi sertifikati",
        certificate_type='course'
    )
    
    # TODO: Генерация PDF файла сертификата
    # В реальном проекте здесь будет логика для создания PDF и превью
    
    return certificate


# Временные заглушки для функций комментариев

@login_required
@require_POST
def add_comment_placeholder(request, course_slug, module_id, lesson_id):
    """Временная заглушка для добавления комментария"""
    messages.info(request, "Izohlar funktsiyasi hozircha mavjud emas")
    return redirect('courses:lesson_detail', course_slug=course_slug, module_id=module_id, lesson_id=lesson_id)


@login_required
def edit_comment_placeholder(request, comment_id):
    """Временная заглушка для редактирования комментария"""
    messages.info(request, "Izohlar tahrirlash funktsiyasi hozircha mavjud emas")
    return redirect(request.META.get('HTTP_REFERER', 'courses:list'))


@login_required
@require_POST
def delete_comment_placeholder(request, comment_id):
    """Временная заглушка для удаления комментария"""
    messages.info(request, "Izohlar o'chirish funktsiyasi hozircha mavjud emas")
    return redirect(request.META.get('HTTP_REFERER', 'courses:list'))


@require_POST
@csrf_exempt
def track_video_view(request):
    """Track video view duration and save it to UserActivity"""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Требуется авторизация'}, status=401)
    
    try:
        data = json.loads(request.body)
        duration = data.get('duration', 0)
        lesson_id = data.get('lesson_id')
        
        if not lesson_id:
            return JsonResponse({'status': 'error', 'message': 'ID урока не указан'}, status=400)
        
        lesson = get_object_or_404(Lesson, id=lesson_id)
        
        # Создаем запись об активности пользователя
        UserActivity.objects.create(
            user=request.user,
            activity_type='video_view',
            content_object=lesson,
            duration=duration
        )
        
        return JsonResponse({'status': 'success', 'message': 'Просмотр видео записан'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
