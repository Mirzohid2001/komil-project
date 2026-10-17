"""
Zavod LMS — to‘liq avtomatik yangilanish pipeline.

Ishga tushirish:
  python manage.py auto_update
  python manage.py auto_update --force
  Cron: blog.cron.full_auto_update_job
"""

from __future__ import annotations

import logging
import traceback
from datetime import timedelta
from io import StringIO
from typing import Any

from django.core.management import call_command
from django.db.models import Count
from django.utils import timezone

from accounts.models import User
from blog.models import SystemJobLog, Test

logger = logging.getLogger('blog.auto_update')

JOB_FULL = 'full_auto_update'
JOB_DAILY_TESTS = 'generate_daily_tests'
JOB_ENSURE_TESTS = 'ensure_role_tests'
JOB_HEALTH = 'system_health'


def _finish(log: SystemJobLog, status: str, message: str, details: dict | None = None):
    log.status = status
    log.message = message
    if details is not None:
        log.details = details
    log.finished_at = timezone.now()
    log.save(update_fields=['status', 'message', 'details', 'finished_at'])


def step_generate_daily_tests(*, force: bool = False) -> dict[str, Any]:
    """Kunlik testlarni yaratish (rol bo‘yicha)."""
    out = StringIO()
    args = []
    if force:
        args.append('--force')
    call_command('generate_daily_tests', *args, stdout=out)
    today = timezone.localdate()
    created_count = Test.objects.filter(
        created_at__date=today,
        title__contains='Kunlik test',
    ).count()
    return {
        'ok': True,
        'step': JOB_DAILY_TESTS,
        'created_today': created_count,
        'output': out.getvalue().strip()[:2000],
        'forced': force,
    }


def step_ensure_role_tests() -> dict[str, Any]:
    """Faol testi yo‘q rollar uchun lokal savollar bilan test ta’minlash."""
    roles = [c[0] for c in User.ROLE_CHOICES]
    missing = []
    for role in roles:
        has_active = Test.objects.filter(role=role, is_active=True).annotate(
            qcount=Count('questions')
        ).filter(qcount__gt=0).exists()
        if not has_active:
            missing.append(role)

    if not missing:
        return {
            'ok': True,
            'step': JOB_ENSURE_TESTS,
            'updated_roles': [],
            'message': 'Barcha rollarda faol test mavjud',
        }

    out = StringIO()
    for role in missing:
        call_command('update_tests', '--mock', '--role', role, stdout=out)

    return {
        'ok': True,
        'step': JOB_ENSURE_TESTS,
        'updated_roles': missing,
        'output': out.getvalue().strip()[:2000],
        'message': f"{len(missing)} ta rol uchun test yangilandi",
    }


def step_system_health() -> dict[str, Any]:
    """Qisqa tizim holati — monitoring uchun."""
    today = timezone.localdate()
    active_tests = Test.objects.filter(is_active=True).count()
    tests_without_questions = (
        Test.objects.filter(is_active=True)
        .annotate(qcount=Count('questions'))
        .filter(qcount=0)
        .count()
    )
    overdue_mandatory = Test.objects.filter(
        is_active=True,
        is_mandatory=True,
        deadline__lt=today,
    ).count()
    roles_covered = (
        Test.objects.filter(is_active=True)
        .values('role')
        .annotate(qcount=Count('questions'))
        .filter(qcount__gt=0)
        .count()
    )
    return {
        'ok': tests_without_questions == 0,
        'step': JOB_HEALTH,
        'active_tests': active_tests,
        'tests_without_questions': tests_without_questions,
        'overdue_mandatory': overdue_mandatory,
        'roles_covered': roles_covered,
        'roles_total': len(User.ROLE_CHOICES),
    }


def run_full_auto_update(
    *,
    trigger: str = SystemJobLog.TRIGGER_CRON,
    force: bool = False,
    user=None,
    skip_daily: bool = False,
    skip_ensure: bool = False,
) -> SystemJobLog:
    """
    To‘liq avto-yangilanish:
      1) kunlik testlar
      2) yetishmayotgan rol testlarini ta’minlash
      3) health check
    """
    log = SystemJobLog.objects.create(
        job_name=JOB_FULL,
        status=SystemJobLog.STATUS_RUNNING,
        trigger=trigger,
        triggered_by=user if getattr(user, 'is_authenticated', False) else None,
        message='Avto-yangilanish boshlandi…',
        details={'force': force},
    )
    steps: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        if not skip_daily:
            try:
                steps.append(step_generate_daily_tests(force=force))
            except Exception as exc:
                logger.exception('generate_daily_tests failed')
                errors.append(f'daily: {exc}')
                steps.append({
                    'ok': False,
                    'step': JOB_DAILY_TESTS,
                    'error': str(exc),
                    'trace': traceback.format_exc()[-1500:],
                })

        if not skip_ensure:
            try:
                steps.append(step_ensure_role_tests())
            except Exception as exc:
                logger.exception('ensure_role_tests failed')
                errors.append(f'ensure: {exc}')
                steps.append({
                    'ok': False,
                    'step': JOB_ENSURE_TESTS,
                    'error': str(exc),
                    'trace': traceback.format_exc()[-1500:],
                })

        try:
            steps.append(step_system_health())
        except Exception as exc:
            logger.exception('system_health failed')
            errors.append(f'health: {exc}')
            steps.append({'ok': False, 'step': JOB_HEALTH, 'error': str(exc)})

        failed = [s for s in steps if not s.get('ok', False)]
        details = {'steps': steps, 'force': force, 'errors': errors}

        if not failed:
            _finish(
                log,
                SystemJobLog.STATUS_SUCCESS,
                'Avto-yangilanish muvaffaqiyatli yakunlandi.',
                details,
            )
        elif len(failed) == len(steps):
            _finish(
                log,
                SystemJobLog.STATUS_FAILED,
                'Avto-yangilanish muvaffaqiyatsiz: ' + '; '.join(errors)[:500],
                details,
            )
        else:
            _finish(
                log,
                SystemJobLog.STATUS_PARTIAL,
                'Avto-yangilanish qisman bajarildi: ' + '; '.join(errors)[:500],
                details,
            )
    except Exception as exc:
        logger.exception('full_auto_update crashed')
        _finish(
            log,
            SystemJobLog.STATUS_FAILED,
            f'Kritik xato: {exc}',
            {'steps': steps, 'trace': traceback.format_exc()[-2000:]},
        )

    return log


def latest_job_summary(limit: int = 10) -> dict[str, Any]:
    """Admin panel uchun qisqa holat."""
    latest = SystemJobLog.objects.filter(job_name=JOB_FULL).first()
    recent = list(SystemJobLog.objects.all()[:limit])
    running = SystemJobLog.objects.filter(status=SystemJobLog.STATUS_RUNNING).exists()
    return {
        'latest': latest,
        'recent': recent,
        'running': running,
        'success_7d': SystemJobLog.objects.filter(
            job_name=JOB_FULL,
            status=SystemJobLog.STATUS_SUCCESS,
            started_at__gte=timezone.now() - timedelta(days=7),
        ).count(),
        'failed_7d': SystemJobLog.objects.filter(
            job_name=JOB_FULL,
            status__in=[SystemJobLog.STATUS_FAILED, SystemJobLog.STATUS_PARTIAL],
            started_at__gte=timezone.now() - timedelta(days=7),
        ).count(),
    }
