"""Course-domain services kept out of views to avoid circular imports."""
from __future__ import annotations

import os
import uuid
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from xhtml2pdf import pisa

from .models import (
    CompletedLesson,
    CourseCertificate,
    Enrollment,
    Lesson,
    LessonVideoProgress,
)


def generate_course_certificate_pdf(certificate):
    """Generate and attach a simple PDF for a course certificate."""
    user = certificate.enrollment.user
    course = certificate.enrollment.course
    verification_url = f"{settings.BASE_URL}/verify-certificate/{certificate.certificate_id}"
    issue_date = certificate.issue_date.strftime('%d.%m.%Y') if certificate.issue_date else ''

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          body {{ font-family: DejaVu Sans, sans-serif; text-align: center; padding: 40px; }}
          h1 {{ color: #0d6efd; margin-bottom: 8px; }}
          .name {{ font-size: 28px; margin: 24px 0 8px; }}
          .course {{ font-size: 20px; margin: 8px 0 24px; }}
          .meta {{ color: #555; font-size: 12px; margin-top: 40px; }}
        </style>
      </head>
      <body>
        <h1>SERTIFIKAT</h1>
        <p>Ushbu sertifikat quyidagi shaxsga beriladi:</p>
        <div class="name">{user.get_full_name() or user.username}</div>
        <p>quyidagi kursni muvaffaqiyatli yakunlagani uchun:</p>
        <div class="course">{course.title}</div>
        <p>{certificate.title}</p>
        <div class="meta">
          <div>Sana: {issue_date}</div>
          <div>ID: {certificate.certificate_id}</div>
          <div>Tekshirish: {verification_url}</div>
        </div>
      </body>
    </html>
    """

    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode('utf-8')), result)
    if pdf.err:
        return None

    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'certificates', 'courses'), exist_ok=True)
    file_name = f"{certificate.certificate_id}.pdf"
    relative_path = os.path.join('certificates', 'courses', file_name)
    absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)
    with open(absolute_path, 'wb') as pdf_file:
        pdf_file.write(result.getvalue())

    certificate.pdf_file.name = relative_path
    certificate.save(update_fields=['pdf_file'])
    return certificate


def create_course_certificate(enrollment):
    """Create a course completion certificate (and PDF) for an enrollment."""
    existing = CourseCertificate.objects.filter(enrollment=enrollment).first()
    if existing:
        if not existing.pdf_file:
            generate_course_certificate_pdf(existing)
        return existing

    certificate = CourseCertificate.objects.create(
        enrollment=enrollment,
        certificate_id=str(uuid.uuid4()),
        title=f"{enrollment.course.title} kursi sertifikati",
        certificate_type='course',
    )
    generate_course_certificate_pdf(certificate)
    return certificate


def upsert_video_progress(
    *,
    user,
    lesson: Lesson,
    watched_seconds: int = 0,
    duration_seconds: int = 0,
    position_seconds: int = 0,
) -> LessonVideoProgress:
    """Video ko‘rish progressini yangilash (monotonic — foiz pasaymaydi)."""
    watched_seconds = max(0, int(watched_seconds or 0))
    duration_seconds = max(0, int(duration_seconds or 0))
    position_seconds = max(0, int(position_seconds or 0))

    progress, _ = LessonVideoProgress.objects.get_or_create(
        user=user,
        lesson=lesson,
    )
    if duration_seconds > progress.duration_seconds:
        progress.duration_seconds = duration_seconds
    if not progress.duration_seconds:
        progress.duration_seconds = lesson.expected_duration_seconds()

    # Ko‘rilgan vaqt — eng yuqori pozitsiya yoki yuborilgan watched
    best_watched = max(progress.watched_seconds, watched_seconds, position_seconds)
    # Server tomonda foizni shishirishni cheklash
    if progress.duration_seconds > 0:
        best_watched = min(best_watched, progress.duration_seconds)
        position_seconds = min(position_seconds, progress.duration_seconds)
    progress.watched_seconds = best_watched
    if position_seconds > progress.last_position:
        progress.last_position = position_seconds

    progress.refresh_percent()
    if (
        lesson.watch_requirement_met(progress.percent)
        and progress.watch_completed_at is None
    ):
        progress.watch_completed_at = timezone.now()
    progress.save()
    return progress


def complete_lesson_for_user(*, user, lesson: Lesson) -> tuple[CompletedLesson | None, bool]:
    """
    Enrollment bo‘lsa darsni yakunlaydi.
    Returns (completed_lesson_or_none, created).
    """
    enrollment = Enrollment.objects.filter(
        user=user, course=lesson.module.course
    ).first()
    if not enrollment:
        return None, False

    was_course_done = enrollment.is_completed
    completed, created = CompletedLesson.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson,
        defaults={'user': user},
    )
    if not created and completed.user_id != user.id:
        completed.user = user
        completed.save(update_fields=['user'])

    # Progress / sertifikat side-effect
    enrollment.progress()
    enrollment.refresh_from_db()

    if created:
        from accounts.audit import log_compliance_event
        log_compliance_event(
            event_type='lesson_completed',
            actor=user,
            subject_user=user,
            object_type='Lesson',
            object_id=lesson.id,
            message=f'Dars yakunlandi: {lesson.title}',
            payload={
                'lesson_id': lesson.id,
                'course_id': lesson.module.course_id,
                'course_title': lesson.module.course.title,
            },
        )
        if enrollment.is_completed and not was_course_done:
            log_compliance_event(
                event_type='course_completed',
                actor=user,
                subject_user=user,
                object_type='Course',
                object_id=lesson.module.course_id,
                message=f'Kurs yakunlandi: {lesson.module.course.title}',
                payload={'course_id': lesson.module.course_id},
            )
            log_compliance_event(
                event_type='cert_issued',
                actor=user,
                subject_user=user,
                object_type='Course',
                object_id=lesson.module.course_id,
                message=f'Kurs sertifikati: {lesson.module.course.title}',
                payload={'course_id': lesson.module.course_id},
            )

    return completed, created


def maybe_auto_complete_from_watch(*, user, lesson: Lesson, progress: LessonVideoProgress) -> bool:
    """Watch foizi yetarli bo‘lsa darsni avto-yakunlash."""
    if lesson.lesson_type != 'video' or not lesson.auto_complete_on_watch:
        return False
    if not lesson.watch_requirement_met(progress.percent):
        return False
    if CompletedLesson.objects.filter(user=user, lesson=lesson).exists():
        return False
    completed, _ = complete_lesson_for_user(user=user, lesson=lesson)
    return completed is not None
