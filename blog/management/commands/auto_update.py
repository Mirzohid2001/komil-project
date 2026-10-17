from django.core.management.base import BaseCommand

from blog.auto_update import run_full_auto_update
from blog.models import SystemJobLog


class Command(BaseCommand):
    help = 'To‘liq avtomatik yangilanish: kunlik testlar + rol testlari + health'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Kunlik testlarni bugun qayta yaratish',
        )
        parser.add_argument(
            '--skip-daily',
            action='store_true',
            help='Kunlik test generatsiyasini o‘tkazib yuborish',
        )
        parser.add_argument(
            '--skip-ensure',
            action='store_true',
            help='Yetishmayotgan rol testlarini to‘ldirishni o‘tkazib yuborish',
        )

    def handle(self, *args, **options):
        log = run_full_auto_update(
            trigger=SystemJobLog.TRIGGER_CLI,
            force=options['force'],
            skip_daily=options['skip_daily'],
            skip_ensure=options['skip_ensure'],
        )
        style = {
            SystemJobLog.STATUS_SUCCESS: self.style.SUCCESS,
            SystemJobLog.STATUS_PARTIAL: self.style.WARNING,
            SystemJobLog.STATUS_FAILED: self.style.ERROR,
        }.get(log.status, self.style.NOTICE)

        self.stdout.write(style(f'[{log.status}] {log.message}'))
        steps = (log.details or {}).get('steps', [])
        for step in steps:
            mark = '✓' if step.get('ok') else '✗'
            self.stdout.write(f"  {mark} {step.get('step')}: {step}")
