from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.db.models import Q, Count, Avg
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_POST
from django.urls import reverse
from .models import (
    Course, Module, Lesson, Enrollment, CompletedLesson,
    CourseCategory, CourseCertificate, LessonComment,
    LessonQuizQuestion, LessonQuizOption, LessonQuizAttempt,
    CourseAssignment, LessonAssignmentSubmission,
)
from .services import create_course_certificate, generate_course_certificate_pdf
from accounts.models import UserActivity

import json
from django.conf import settings

def course_list(request, category_slug=None):
    """Отображение списка курсов с фильтрацией по категории"""
    categories = CourseCategory.objects.all()
    
    # Rol bo‘yicha filtrlangan nashr etilgan kurslar
    courses = Course.published_for_user(request.user)
    
    # Фильтр по категории, если указан slug
    if category_slug:
        category = get_object_or_404(CourseCategory, slug=category_slug)
        courses = courses.filter(category=category)
    
    # Фильтры из параметров запроса
    difficulty = request.GET.get('difficulty')
    if difficulty:
        courses = courses.filter(difficulty=difficulty)
    
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
    featured_courses = Course.published_for_user(request.user).filter(is_featured=True)[:5]
    
    context = {
        'categories': categories,
        'courses': courses,
        'featured_courses': featured_courses,
        'current_category': category_slug,
        'difficulty_choices': Course.DIFFICULTY_CHOICES,
        'current_difficulty': difficulty,
        'current_sort': sort,
    }
    
    return render(request, 'courses/course_list.html', context)


def course_search(request):
    """Поиск курсов по ключевому слову"""
    query = request.GET.get('q', '')
    
    if query:
        courses = Course.published_for_user(request.user).filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(short_description__icontains=query),
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
    course = get_object_or_404(
        Course.objects.select_related('category'),
        slug=course_slug,
        status='published',
    )

    if not course.can_user_access(request.user):
        if request.user.is_authenticated:
            messages.error(request, "Bu kurs sizning rolingiz uchun ochiq emas.")
            return redirect('courses:list')
        messages.info(request, "Bu kursga kirish uchun tizimga kiring.")
        return redirect('accounts:login')

    enrollment = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()

    modules = course.modules.all().prefetch_related('lessons')
    free_preview_lessons = Lesson.objects.filter(
        module__course=course, is_free_preview=True
    )
    related_courses = (
        Course.published_for_user(request.user).filter(category=course.category)
        .exclude(id=course.id)
        .order_by('-created_at')[:4]
    )

    is_enrolled = enrollment is not None
    is_completed = bool(enrollment and enrollment.is_completed)
    progress = enrollment.progress() if enrollment else 0
    certificate = (
        CourseCertificate.objects.filter(enrollment=enrollment).first()
        if enrollment
        else None
    )
    completed_lesson_ids = set()
    if enrollment:
        completed_lesson_ids = set(
            CompletedLesson.objects.filter(enrollment=enrollment)
            .values_list('lesson_id', flat=True)
        )

    context = {
        'course': course,
        'enrollment': enrollment,
        'modules': modules,
        'total_duration': course.total_duration(),
        'total_students': course.students_count(),
        'free_preview_lessons': free_preview_lessons,
        'related_courses': related_courses,
        'is_enrolled': is_enrolled,
        'is_completed': is_completed,
        'progress': progress,
        'certificate': certificate,
        'completed_lesson_ids': completed_lesson_ids,
    }

    if request.user.is_authenticated:
        UserActivity.objects.create(
            user=request.user,
            activity_type='view_course',
            details={'course_id': course.id, 'course_title': course.title},
            ip_address=request.META.get('REMOTE_ADDR')
        )

    return render(request, 'courses/course_detail.html', context)


@login_required
@require_POST
def course_unenroll(request, course_slug):
    """Remove current user enrollment from a course."""
    course = get_object_or_404(Course, slug=course_slug)
    deleted, _ = Enrollment.objects.filter(user=request.user, course=course).delete()
    if deleted:
        messages.success(request, f"Siz '{course.title}' kursidan chiqdingiz.")
    else:
        messages.info(request, "Siz bu kursga yozilmagansiz.")
    return redirect('courses:detail', course_slug=course.slug)


@login_required
@require_POST
def course_enroll(request, course_slug):
    """Запись на курс"""
    course = get_object_or_404(Course, slug=course_slug, status='published')

    if not course.can_user_access(request.user):
        messages.error(request, "Bu kurs sizning rolingiz uchun ochiq emas.")
        return redirect('courses:list')
    
    # Проверка, не записан ли пользователь уже
    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.info(request, f"Siz allaqachon '{course.title}' kursiga yozilgansiz.")
        return redirect('courses:learn', course_slug=course.slug)
    
    # Ichki zavod loyihasi — barcha kurslar bepul, to'lov yo'q.
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
    enrollments = Enrollment.objects.filter(user=request.user).select_related(
        'course', 'certificate'
    )
    assignments = (
        CourseAssignment.objects.filter(user=request.user)
        .select_related('course')
        .order_by('deadline')
    )
    for a in assignments:
        a.sync_completion()
    
    # Разделяем на активные и завершенные курсы
    active_enrollments = enrollments.filter(is_completed=False)
    completed_enrollments = enrollments.filter(is_completed=True)
    
    # Прогресс для активных курсов
    for enrollment in active_enrollments:
        enrollment.progress_percent = enrollment.progress()
    
    # Рекомендуемые курсы
    # TODO: Улучшить алгоритм рекомендаций на основе категорий пройденных курсов
    enrolled_course_ids = enrollments.values_list('course_id', flat=True)
    recommended_courses = Course.published_for_user(request.user).exclude(
        id__in=enrolled_course_ids
    ).order_by('?')[:4]
    
    context = {
        'active_enrollments': active_enrollments,
        'completed_enrollments': completed_enrollments,
        'recommended_courses': recommended_courses,
        'assignments': assignments,
    }
    
    return render(request, 'courses/my_courses.html', context)


@login_required
@require_POST
def submit_assignment(request, course_slug, module_id, lesson_id):
    """Amaliy vazifa faylini yuklash."""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)

    if lesson.lesson_type != 'assignment':
        messages.error(request, "Bu dars amaliy vazifa emas.")
        return redirect('courses:lesson_detail', course_slug, module_id, lesson_id)

    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.error(request, "Avval kursga yoziling.")
        return redirect('courses:detail', course_slug=course_slug)

    uploaded = request.FILES.get('file')
    if not uploaded:
        messages.error(request, "Fayl tanlang.")
        return redirect('courses:lesson_detail', course_slug, module_id, lesson_id)

    comment = (request.POST.get('comment') or '').strip()
    LessonAssignmentSubmission.objects.create(
        lesson=lesson,
        user=request.user,
        file=uploaded,
        comment=comment,
        status=LessonAssignmentSubmission.STATUS_PENDING,
    )
    messages.success(request, "Vazifa yuborildi. Instruktur tasdiğini kuting.")
    return redirect('courses:lesson_detail', course_slug, module_id, lesson_id)


@login_required
@require_POST
def review_assignment(request, submission_id):
    """Admin/staff: vazifani tasdiqlash yoki rad etish."""
    if request.user.role != 'admin' and not request.user.is_staff:
        messages.error(request, "Ruxsat yo‘q.")
        return redirect('courses:list')

    submission = get_object_or_404(
        LessonAssignmentSubmission.objects.select_related('lesson__module__course', 'user'),
        pk=submission_id,
    )
    action = request.POST.get('action')
    note = (request.POST.get('reviewer_note') or '').strip()
    lesson = submission.lesson
    course = lesson.module.course

    if action == 'approve':
        submission.status = LessonAssignmentSubmission.STATUS_APPROVED
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.reviewer_note = note
        submission.save()
        enrollment = Enrollment.objects.filter(user=submission.user, course=course).first()
        if enrollment:
            CompletedLesson.objects.get_or_create(
                enrollment=enrollment,
                lesson=lesson,
                defaults={'user': submission.user},
            )
            enrollment.progress()
        messages.success(request, "Vazifa tasdiqlandi — dars yakunlandi.")
    elif action == 'reject':
        submission.status = LessonAssignmentSubmission.STATUS_REJECTED
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.reviewer_note = note
        submission.save()
        messages.warning(request, "Vazifa rad etildi.")
    else:
        messages.error(request, "Noto‘g‘ri amal.")

    return redirect(
        'courses:lesson_detail',
        course_slug=course.slug,
        module_id=lesson.module_id,
        lesson_id=lesson.id,
    )


@login_required
def course_learn(request, course_slug):
    """Основная страница обучения по курсу"""
    course = get_object_or_404(Course, slug=course_slug, status='published')
    
    # Проверка, записан ли пользователь на курс
    try:
        enrollment = Enrollment.objects.select_related('certificate').get(
            user=request.user, course=course
        )
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
        enrollment.sync_course_assignments()
        
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

    siblings = list(course.modules.all().order_by('order'))
    prev_module = None
    next_module = None
    for idx, sibling in enumerate(siblings):
        if sibling.id == module.id:
            if idx > 0:
                prev_module = siblings[idx - 1]
            if idx + 1 < len(siblings):
                next_module = siblings[idx + 1]
            break
    
    context = {
        'course': course,
        'module': module,
        'lessons': lessons,
        'enrollment': enrollment,
        'completed_lesson_ids': completed_lesson_ids,
        'prev_module': prev_module,
        'next_module': next_module,
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
    
    comments = (
        LessonComment.objects.filter(lesson=lesson)
        .select_related('user')
        .order_by('-created_at')
    )
    quiz_questions = (
        LessonQuizQuestion.objects.filter(lesson=lesson)
        .prefetch_related('answers')
        .order_by('order', 'id')
    )
    last_quiz_attempt = (
        LessonQuizAttempt.objects.filter(lesson=lesson, user=request.user)
        .order_by('-completed_at')
        .first()
    )

    assignment_submission = None
    pending_assignment_submissions = []
    can_review_assignment = (
        request.user.role == 'admin' or request.user.is_staff
    )
    if lesson.lesson_type == 'assignment':
        assignment_submission = (
            LessonAssignmentSubmission.objects.filter(lesson=lesson, user=request.user)
            .order_by('-submitted_at')
            .first()
        )
        if can_review_assignment:
            pending_assignment_submissions = list(
                LessonAssignmentSubmission.objects.filter(
                    lesson=lesson,
                    status=LessonAssignmentSubmission.STATUS_PENDING,
                )
                .select_related('user')
                .order_by('submitted_at')
            )

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
        'module': module,
        'comments': comments,
        'quiz_questions': quiz_questions,
        'last_quiz_attempt': last_quiz_attempt,
        'assignment_submission': assignment_submission,
        'pending_assignment_submissions': pending_assignment_submissions,
        'can_review_assignment': can_review_assignment,
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
def submit_quiz(request, course_slug, module_id, lesson_id):
    course = get_object_or_404(Course, slug=course_slug)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)

    if not (
        request.user.is_staff
        or request.user.role == 'admin'
        or Enrollment.objects.filter(user=request.user, course=course).exists()
    ):
        messages.error(request, "Quiz topshirish uchun kursga yozilishingiz kerak.")
        return redirect('courses:detail', course_slug=course_slug)

    questions = list(
        LessonQuizQuestion.objects.filter(lesson=lesson).prefetch_related('answers')
    )
    if not questions:
        messages.warning(request, "Bu darsda quiz savollari yo‘q.")
        return redirect(
            'courses:lesson_detail',
            course_slug=course_slug,
            module_id=module_id,
            lesson_id=lesson_id,
        )

    correct = 0
    total = len(questions)
    for question in questions:
        selected_id = request.POST.get(f'question_{question.id}')
        if not selected_id:
            continue
        try:
            option = question.answers.get(id=int(selected_id))
        except (LessonQuizOption.DoesNotExist, ValueError, TypeError):
            continue
        if option.is_correct:
            correct += 1

    percentage = (correct / total * 100) if total else 0
    is_passed = percentage >= 70
    LessonQuizAttempt.objects.create(
        lesson=lesson,
        user=request.user,
        score=correct,
        total=total,
        percentage=percentage,
        is_passed=is_passed,
    )

    if is_passed:
        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()
        if enrollment:
            CompletedLesson.objects.get_or_create(
                enrollment=enrollment,
                lesson=lesson,
                defaults={'user': request.user},
            )
            enrollment.progress()
        messages.success(
            request,
            f"Quiz topshirildi: {correct}/{total} ({percentage:.0f}%). Dars yakunlandi.",
        )
    else:
        messages.warning(
            request,
            f"Quiz natijasi: {correct}/{total} ({percentage:.0f}%). O‘tish uchun kamida 70% kerak.",
        )

    return redirect(
        'courses:lesson_detail',
        course_slug=course_slug,
        module_id=module_id,
        lesson_id=lesson_id,
    )


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
        enrollment.sync_course_assignments()
        
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

    if lesson.lesson_type == 'assignment':
        approved = LessonAssignmentSubmission.objects.filter(
            lesson=lesson,
            user=request.user,
            status=LessonAssignmentSubmission.STATUS_APPROVED,
        ).exists()
        if not approved and request.user.role != 'admin' and not request.user.is_staff:
            messages.error(
                request,
                "Amaliy vazifa uchun fayl yuklang va instruktur tasdiğini kuting.",
            )
            return redirect(
                'courses:lesson_detail',
                course_slug=course_slug,
                module_id=module_id,
                lesson_id=lesson_id,
            )
    
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
            enrollment.sync_course_assignments()
            
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
        CourseCertificate.objects.select_related(
            'enrollment__user', 'enrollment__course'
        ),
        certificate_id=certificate_id
    )
    
    # Проверяем, что сертификат принадлежит пользователю или пользователь - администратор
    if (
        certificate.enrollment.user != request.user
        and not request.user.is_staff
        and request.user.role != 'admin'
    ):
        messages.error(request, "Sizda bu sertifikatni ko'rish huquqi yo'q")
        return redirect('accounts:profile')
    
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
    certificate = get_object_or_404(
        CourseCertificate.objects.select_related(
            'enrollment__user', 'enrollment__course'
        ),
        certificate_id=certificate_id,
    )
    
    # Проверка, что сертификат принадлежит пользователю
    if (
        certificate.enrollment.user != request.user
        and not request.user.is_staff
        and request.user.role != 'admin'
    ):
        raise Http404("Sertifikat topilmadi")
    
    if not certificate.pdf_file:
        generate_course_certificate_pdf(certificate)
        certificate.refresh_from_db()

    if not certificate.pdf_file:
        return HttpResponse("Sertifikat yaratib bo'lmadi", content_type='text/plain', status=500)

    certificate.pdf_file.open('rb')
    try:
        response = HttpResponse(certificate.pdf_file.read(), content_type='application/pdf')
    finally:
        certificate.pdf_file.close()
    response['Content-Disposition'] = f'attachment; filename="{certificate.certificate_id}.pdf"'
    return response


@login_required
@require_POST
def add_comment(request, course_slug, module_id, lesson_id):
    course = get_object_or_404(Course, slug=course_slug)
    module = get_object_or_404(Module, id=module_id, course=course)
    lesson = get_object_or_404(Lesson, id=lesson_id, module=module)

    if not lesson.allow_comments:
        messages.error(request, "Bu dars uchun izohlar o‘chirilgan.")
        return redirect('courses:lesson_detail', course_slug=course_slug, module_id=module_id, lesson_id=lesson_id)

    if not (
        request.user.is_staff
        or request.user.role == 'admin'
        or Enrollment.objects.filter(user=request.user, course=course).exists()
    ):
        messages.error(request, "Izoh qoldirish uchun kursga yozilishingiz kerak.")
        return redirect('courses:detail', course_slug=course_slug)

    content = (request.POST.get('content') or '').strip()
    if not content:
        messages.error(request, "Izoh matni bo‘sh bo‘lishi mumkin emas.")
    elif len(content) > 2000:
        messages.error(request, "Izoh 2000 belgidan oshmasligi kerak.")
    else:
        LessonComment.objects.create(lesson=lesson, user=request.user, content=content)
        messages.success(request, "Izoh qo‘shildi.")

    return redirect('courses:lesson_detail', course_slug=course_slug, module_id=module_id, lesson_id=lesson_id)


@login_required
def edit_comment(request, comment_id):
    comment = get_object_or_404(
        LessonComment.objects.select_related('lesson__module__course', 'user'),
        id=comment_id,
    )
    if comment.user != request.user:
        messages.error(request, "Bu izohni tahrirlash huquqingiz yo‘q.")
        return redirect('courses:list')

    lesson = comment.lesson
    course = lesson.module.course
    module = lesson.module

    if request.method == 'POST':
        content = (request.POST.get('content') or '').strip()
        if not content:
            messages.error(request, "Izoh matni bo‘sh bo‘lishi mumkin emas.")
        elif len(content) > 2000:
            messages.error(request, "Izoh 2000 belgidan oshmasligi kerak.")
        else:
            comment.content = content
            comment.save(update_fields=['content', 'updated_at'])
            messages.success(request, "Izoh yangilandi.")
            return redirect(
                'courses:lesson_detail',
                course_slug=course.slug,
                module_id=module.id,
                lesson_id=lesson.id,
            )

    return render(request, 'courses/edit_comment.html', {
        'comment': comment,
        'course': course,
        'module': module,
        'lesson': lesson,
    })


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(
        LessonComment.objects.select_related('lesson__module__course', 'user'),
        id=comment_id,
    )
    if comment.user != request.user and request.user.role != 'admin' and not request.user.is_staff:
        messages.error(request, "Bu izohni o‘chirish huquqingiz yo‘q.")
        return redirect('courses:list')

    lesson = comment.lesson
    course = lesson.module.course
    module = lesson.module
    comment.delete()
    messages.success(request, "Izoh o‘chirildi.")
    return redirect(
        'courses:lesson_detail',
        course_slug=course.slug,
        module_id=module.id,
        lesson_id=lesson.id,
    )


@login_required
@require_POST
def track_video_view(request):
    """Track video view duration and save it to UserActivity"""
    try:
        data = json.loads(request.body)
        duration = data.get('duration', 0)
        lesson_id = data.get('lesson_id')
        
        if not lesson_id:
            return JsonResponse({'status': 'error', 'message': 'ID урока не указан'}, status=400)
        
        lesson = get_object_or_404(Lesson, id=lesson_id)
        
        UserActivity.objects.create(
            user=request.user,
            activity_type='view_video',
            duration=duration,
            details={
                'lesson_id': lesson.id,
                'lesson_title': lesson.title,
                'course_slug': lesson.module.course.slug,
            },
        )
        
        return JsonResponse({'status': 'success', 'message': 'Просмотр видео записан'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
