"""
CSV orqali xodimlarni ommaviy import qilish.

CSV ustunlari (header):
  username,password,role,first_name,last_name,email,employee_id,department,shift

Misol:
  python manage.py import_users_csv /path/users.csv
  python manage.py import_users_csv /path/users.csv --dry-run
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from accounts.models import Department

User = get_user_model()
VALID_ROLES = {r[0] for r in User.ROLE_CHOICES if r[0] != 'admin'}


class Command(BaseCommand):
    help = 'CSV dan xodimlarni import qiladi'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--default-password',
            default='Demo1234!',
            help='password ustuni bo‘sh bo‘lsa',
        )

    def handle(self, *args, **options):
        path = Path(options['csv_path'])
        if not path.exists():
            raise CommandError(f'Fayl topilmadi: {path}')

        created = updated = skipped = 0
        dry = options['dry_run']

        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or 'username' not in reader.fieldnames:
                raise CommandError('CSV da username ustuni bo‘lishi shart')

            for i, row in enumerate(reader, start=2):
                username = (row.get('username') or '').strip()
                if not username:
                    skipped += 1
                    continue

                role = (row.get('role') or '').strip()
                if role not in VALID_ROLES:
                    self.stderr.write(f'[{i}] Noto‘g‘ri rol: {role!r} ({username})')
                    skipped += 1
                    continue

                dept_name = (row.get('department') or '').strip()
                department = None
                if dept_name and not dry:
                    department, _ = Department.objects.get_or_create(name=dept_name)

                password = (row.get('password') or '').strip() or options['default_password']
                defaults = {
                    'role': role,
                    'first_name': (row.get('first_name') or '').strip(),
                    'last_name': (row.get('last_name') or '').strip(),
                    'email': (row.get('email') or '').strip(),
                    'employee_id': (row.get('employee_id') or '').strip(),
                    'shift': (row.get('shift') or '').strip(),
                    'department': department,
                }

                if dry:
                    exists = User.objects.filter(username=username).exists()
                    if exists:
                        updated += 1
                    else:
                        created += 1
                    continue

                user, was_created = User.objects.get_or_create(
                    username=username,
                    defaults=defaults,
                )
                if was_created:
                    user.set_password(password)
                    user.save()
                    created += 1
                    self.stdout.write(f'  + {username} ({role})')
                else:
                    for k, v in defaults.items():
                        setattr(user, k, v)
                    if row.get('password'):
                        user.set_password(password)
                    user.save()
                    updated += 1
                    self.stdout.write(f'  ~ {username}')

        self.stdout.write(self.style.SUCCESS(
            f'Import: created={created} updated={updated} skipped={skipped}'
            + (' (dry-run)' if dry else '')
        ))
