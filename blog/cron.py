"""django-crontab entrypoints. Activate: python manage.py crontab add"""

import logging

from django.core.management import call_command

logger = logging.getLogger('blog.auto_update')


def generate_daily_tests_job():
    """Legacy: faqat kunlik testlar (01:00 o‘rniga full_auto_update ishlatiladi)."""
    call_command('generate_daily_tests')


def full_auto_update_job():
    """Har kuni tungi to‘liq avto-yangilanish."""
    from blog.auto_update import run_full_auto_update
    from blog.models import SystemJobLog

    logger.info('Cron: full_auto_update_job started')
    log = run_full_auto_update(trigger=SystemJobLog.TRIGGER_CRON, force=False)
    logger.info('Cron: full_auto_update_job finished status=%s', log.status)


def midday_ensure_tests_job():
    """Kunduzi yetishmayotgan rol testlarini tekshirish (AI/kunliksiz)."""
    from blog.auto_update import run_full_auto_update
    from blog.models import SystemJobLog

    logger.info('Cron: midday_ensure_tests_job started')
    log = run_full_auto_update(
        trigger=SystemJobLog.TRIGGER_CRON,
        force=False,
        skip_daily=True,
    )
    logger.info('Cron: midday_ensure_tests_job finished status=%s', log.status)


def deadline_notifications_job():
    """Har kuni ertalab muddat eslatmalari."""
    from accounts.notifications import send_deadline_reminders

    logger.info('Cron: deadline_notifications_job started')
    created = send_deadline_reminders()
    logger.info('Cron: deadline_notifications_job finished created=%s', created)
