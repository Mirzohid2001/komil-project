import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from blog.models import Test, Question, Option

User = get_user_model()
logger = logging.getLogger(__name__)

# Map live roles onto local fallback question buckets.
ROLE_BUCKET_MAP = {
    'admin': 'admin',
    'Оператор': 'оператор',
    'Диспетчер': 'оператор',
    'естокада': 'оператор',
    'temiryo`lchi': 'оператор',
    'охраник': 'оператор',
    'уборщик': 'оператор',
    'повар': 'оператор',
    'склад': 'оператор',
    'механик': 'наладчик',
    'электрик': 'наладчик',
    'сварщик': 'наладчик',
    'слесарь': 'наладчик',
    'КИП и А': 'наладчик',
    'технолог': 'инженер',
    'офисный-персонал': 'инженер',
}

FALLBACK_QUESTIONS = {
    'admin': [
        {
            'question': 'Qaysi autentifikatsiya turi eng xavfsiz hisoblanadi?',
            'options': [
                {'text': 'Oddiy parol', 'is_correct': False},
                {'text': 'Ikki bosqichli autentifikatsiya', 'is_correct': True},
                {'text': 'Ikkinchi omilsiz biometriya', 'is_correct': False},
                {'text': 'Eskirgan parollar', 'is_correct': False},
            ],
            'explanation': 'Ikki bosqichli autentifikatsiya qo‘shimcha himoya qatlamini beradi.',
        },
        {
            'question': 'Veb-sahifalarni xavfsiz ko‘rish uchun qaysi protokol ishlatiladi?',
            'options': [
                {'text': 'HTTP', 'is_correct': False},
                {'text': 'FTP', 'is_correct': False},
                {'text': 'HTTPS', 'is_correct': True},
                {'text': 'SMTP', 'is_correct': False},
            ],
            'explanation': 'HTTPS ma’lumotlarni shifrlaydi.',
        },
    ],
    'оператор': [
        {
            'question': 'Ish boshlashdan oldin nima qilish kerak?',
            'options': [
                {'text': 'Darhol uskunani yoqish', 'is_correct': False},
                {'text': 'Yo‘riqnoma va himoya vositalarini tekshirish', 'is_correct': True},
                {'text': 'Tekshiruvlarni o‘tkazib yuborish', 'is_correct': False},
                {'text': 'Himoya vositalarisiz ishlash', 'is_correct': False},
            ],
            'explanation': 'Xavfsizlik tekshiruvi majburiy.',
        },
        {
            'question': 'Favqulodda signal eshitilganda nima qilish kerak?',
            'options': [
                {'text': 'Ishni davom ettirish', 'is_correct': False},
                {'text': 'Ishni to‘xtatib, rahbarga xabar berish', 'is_correct': True},
                {'text': 'Signallarni e’tiborsiz qoldirish', 'is_correct': False},
                {'text': 'Faqat smena oxirida xabar berish', 'is_correct': False},
            ],
            'explanation': 'Favqulodda holatda ish to‘xtatiladi va xabar beriladi.',
        },
    ],
    'наладчик': [
        {
            'question': 'Uskunani sozlashdan oldin nima qilish kerak?',
            'options': [
                {'text': 'Elektr ta’minotini o‘chirmasdan ishlash', 'is_correct': False},
                {'text': 'Xavfsizlik choralarini ko‘rib, diagnostika o‘tkazish', 'is_correct': True},
                {'text': 'Hujjatlarsiz ishlash', 'is_correct': False},
                {'text': 'Faqat ko‘z bilan chamalab sozlash', 'is_correct': False},
            ],
            'explanation': 'Diagnostika va xavfsizlik birinchi o‘rinda.',
        },
        {
            'question': 'Nosoz qismni almashtirishda nima afzal?',
            'options': [
                {'text': 'Vaqtinchalik yechimlar', 'is_correct': False},
                {'text': 'Original ehtiyot qismlar va hujjatlashtirish', 'is_correct': True},
                {'text': 'Mos kelmaydigan detal', 'is_correct': False},
                {'text': 'Sinovsiz ishga tushirish', 'is_correct': False},
            ],
            'explanation': 'Original qism va tekshiruv sifatni ta’minlaydi.',
        },
    ],
    'инженер': [
        {
            'question': 'NPV nima?',
            'options': [
                {'text': 'Loyiha xarajatlari yig‘indisi', 'is_correct': False},
                {'text': 'Sof keltirilgan qiymat', 'is_correct': True},
                {'text': 'Valyuta kursi', 'is_correct': False},
                {'text': 'Negativ foiz', 'is_correct': False},
            ],
            'explanation': 'NPV kelajakdagi pul oqimlarining bugungi qiymatini bildiradi.',
        },
        {
            'question': 'Tizim samaradorligini oshirishda nima muhim?',
            'options': [
                {'text': 'Hisob-kitoblarni e’tiborsiz qoldirish', 'is_correct': False},
                {'text': 'Tahlil, sinov va optimallashtirish', 'is_correct': True},
                {'text': 'Eskirgan standartlarga rioya qilish', 'is_correct': False},
                {'text': 'Prototipsiz joriy etish', 'is_correct': False},
            ],
            'explanation': 'Muhandislik yechimi tahlil va sinovga asoslanadi.',
        },
    ],
}


class Command(BaseCommand):
    help = 'Yangilaydi yoki yaratadi test savollarini (lokal fallback / mock)'

    def add_arguments(self, parser):
        parser.add_argument('--role', help='Faqat ko‘rsatilgan rol uchun yangilash')
        parser.add_argument(
            '--mock',
            action='store_true',
            help='Tashqi API o‘rniga lokal savollardan foydalanish',
        )

    def resolve_bucket(self, role):
        return ROLE_BUCKET_MAP.get(role, 'оператор')

    def handle(self, *args, **options):
        role = options.get('role')
        use_mock = options.get('mock', False)
        valid_roles = [r[0] for r in User.ROLE_CHOICES]

        if role and role not in valid_roles:
            self.stdout.write(self.style.ERROR(f"Noto‘g‘ri rol: {role}"))
            self.stdout.write(self.style.WARNING(f"Mavjud rollar: {', '.join(valid_roles)}"))
            return

        roles_to_update = [role] if role else valid_roles

        for current_role in roles_to_update:
            bucket = self.resolve_bucket(current_role)
            questions_data = FALLBACK_QUESTIONS.get(bucket, [])
            if not questions_data:
                self.stdout.write(
                    self.style.WARNING(f"'{current_role}' roli uchun lokal savollar yo‘q")
                )
                continue

            # Without a real external API, --mock and default path both use local data.
            source = 'mock/local' if use_mock else 'local-fallback'
            self.create_or_update_tests(current_role, questions_data)
            self.stdout.write(
                self.style.SUCCESS(
                    f"'{current_role}' testi yangilandi ({source}, {len(questions_data)} savol)"
                )
            )

    @transaction.atomic
    def create_or_update_tests(self, role, questions_data):
        role_label = dict(User.ROLE_CHOICES).get(role, role)
        test, created = Test.objects.get_or_create(
            role=role,
            title=f"Test: {role_label}",
            defaults={
                'description': f"{role_label} roli uchun bilim tekshiruvi",
                'time_limit': 30,
                'passing_score': 70,
                'is_active': True,
            },
        )

        if not created:
            test.description = f"{role_label} roli uchun bilim tekshiruvi"
            test.updated_at = timezone.now()
            test.is_active = True
            test.save()
            Question.objects.filter(test=test).delete()

        for q_data in questions_data:
            question = Question.objects.create(
                test=test,
                text=q_data['question'],
                explanation=q_data.get('explanation', ''),
            )
            for opt_data in q_data['options']:
                Option.objects.create(
                    question=question,
                    text=opt_data['text'],
                    is_correct=opt_data['is_correct'],
                )

        logger.info(
            "Test for role '%s' was %s with %s questions",
            role,
            'created' if created else 'updated',
            len(questions_data),
        )
