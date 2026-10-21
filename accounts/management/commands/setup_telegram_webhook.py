"""Telegram webhook URL ni o‘rnatish (sozlamalar Admin paneldan).

Usage:
  python manage.py setup_telegram_webhook
  python manage.py setup_telegram_webhook --delete
"""
from django.core.management.base import BaseCommand

from accounts.telegram_bot import (
    bot_configured,
    delete_webhook,
    fetch_bot_username,
    set_webhook,
)


class Command(BaseCommand):
    help = 'Telegram webhook ni o‘rnatadi (token Admin → Telegram sozlamalarida)'

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true', help='Webhookni o‘chirish')
        parser.add_argument(
            '--url',
            default='',
            help='To‘liq webhook URL (default: BASE_URL + /accounts/telegram/webhook/)',
        )

    def handle(self, *args, **options):
        if not bot_configured():
            self.stderr.write(
                'Bot yoqilmagan. Admin → Telegram sozlamalar: token + «Yoqilgan».'
            )
            return

        if options['delete']:
            data = delete_webhook()
            self.stdout.write(str(data))
            return

        data = set_webhook(options['url'] or '')
        uname = fetch_bot_username()
        self.stdout.write(self.style.SUCCESS(f'setWebhook: {data}'))
        if uname:
            self.stdout.write(self.style.SUCCESS(f'Bot username: @{uname}'))
