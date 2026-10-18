"""Rol / bo‘lim / smena bo‘yicha ommaviy kurs topshirig‘i."""
from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth import get_user_model

from courses.models import Course, CourseAssignment

User = get_user_model()


def filter_assignees(
    *,
    role: str = '',
    department_id: int | None = None,
    shift: str = '',
    active_only: bool = True,
):
    qs = User.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    qs = qs.exclude(role='admin').exclude(is_superuser=True)
    if role:
        qs = qs.filter(role=role)
    if department_id:
        qs = qs.filter(department_id=department_id)
    if shift:
        qs = qs.filter(shift=shift)
    return qs.order_by('username')


def bulk_assign_course(
    *,
    course: Course,
    deadline: date,
    assigned_by=None,
    role: str = '',
    department_id: int | None = None,
    shift: str = '',
    is_mandatory: bool = True,
    notes: str = '',
    update_existing: bool = True,
) -> dict[str, Any]:
    """
    Tanlangan filtrdagi xodimlarga kurs tayinlaydi.
    Returns: created, updated, skipped, user_ids, filters
    """
    users = list(
        filter_assignees(role=role, department_id=department_id, shift=shift)
    )
    created = 0
    updated = 0
    skipped = 0
    user_ids: list[int] = []

    for user in users:
        assignment, was_created = CourseAssignment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'deadline': deadline,
                'is_mandatory': is_mandatory,
                'notes': notes,
                'assigned_by': assigned_by,
            },
        )
        if was_created:
            created += 1
            user_ids.append(user.id)
            continue
        if update_existing:
            changed = False
            if assignment.deadline != deadline:
                assignment.deadline = deadline
                changed = True
            if assignment.is_mandatory != is_mandatory:
                assignment.is_mandatory = is_mandatory
                changed = True
            if notes and assignment.notes != notes:
                assignment.notes = notes
                changed = True
            if assigned_by and assignment.assigned_by_id != getattr(assigned_by, 'id', None):
                assignment.assigned_by = assigned_by
                changed = True
            if changed:
                assignment.save()
                updated += 1
                user_ids.append(user.id)
            else:
                skipped += 1
        else:
            skipped += 1

    return {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'total_matched': len(users),
        'user_ids': user_ids,
        'filters': {
            'role': role or None,
            'department_id': department_id,
            'shift': shift or None,
            'deadline': deadline.isoformat(),
            'course_id': course.id,
            'course_title': course.title,
            'is_mandatory': is_mandatory,
        },
    }
