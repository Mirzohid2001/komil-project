from django.core.management.base import BaseCommand

from accounts.models import User
from blog.test_generator import generate_daily_tests_for_roles


class Command(BaseCommand):
    help = 'Generate daily tests with 30 questions for each role'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force generation even if tests were already created today',
        )
        parser.add_argument(
            '--test_roles',
            type=str,
            nargs='+',
            help='Specific roles to generate tests for (defaults to all roles)',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        test_roles = options.get('test_roles')

        if test_roles:
            valid = {c[0] for c in User.ROLE_CHOICES}
            unknown = [r for r in test_roles if r not in valid]
            if unknown:
                self.stdout.write(
                    self.style.ERROR(f"Noma'lum rollar: {', '.join(unknown)}")
                )
                return
            roles = test_roles
        else:
            roles = None

        created = generate_daily_tests_for_roles(roles, force=force)
        if not created and not force:
            self.stdout.write(
                self.style.WARNING(
                    'Bugun uchun testlar allaqachon yaratilgan. '
                    'Qayta yaratish uchun --force parametridan foydalaning.'
                )
            )
            return

        for test in created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Test muvaffaqiyatli yaratildi: "{test.title}" '
                    f'({test.get_total_questions()} ta savol)'
                )
            )
