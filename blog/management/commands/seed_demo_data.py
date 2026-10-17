"""
Isomer Oil LMS — demo baza to‘ldirish.

  python manage.py seed_demo_data
  python manage.py seed_demo_data --reset
"""

from __future__ import annotations

from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import User
from blog.models import (
    Category,
    Document,
    DocumentCategory,
    Option,
    Post,
    Question,
    Test,
)
from courses.models import Course, CourseCategory, Enrollment, Lesson, Module

# Minimal valid-looking PDF bytes
MINI_PDF = b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144]
/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 44 >>stream
BT /F1 12 Tf 40 100 Td (Isomer Oil LMS) Tj ET
endstream endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000361 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
440
%%EOF
"""

DEMO_PASSWORD = 'Demo1234!'


ROLE_QUESTIONS = {
    'Оператор': [
        ('Ish joyida himoya vositalari qachon kiyiladi?',
         [('Har doim smena davomida', True), ('Faqat tekshiruvda', False),
          ('Faqat tunda', False), ('Ixtiyoriy', False)]),
        ('Favqulodda signal eshitilganda nima qilinadi?',
         [('Ishni to‘xtatib, rahbarga xabar berish', True), ('Ishni davom ettirish', False),
          ('Telefon o‘yin', False), ('Hech narsa', False)]),
        ('Uskunani ishga tushirishdan oldin nima tekshiriladi?',
         [('Yo‘riqnoma va himoya', True), ('Faqat chiroq', False),
          ('Faqat telefon', False), ('Hech narsa', False)]),
        ('Neft mahsulotlari bilan ishlashda asosiy xavf nima?',
         [('Yong‘in va bug‘lar', True), ('Shovqin yo‘qligi', False),
          ('Past harorat', False), ('Yorug‘lik', False)]),
        ('Smena topshirig‘i qayerda qayd etiladi?',
         [('Jurnal / smena daftari', True), ('Shaxsiy chat', False),
          ('Og‘zaki', False), ('Hech qayerda', False)]),
    ],
    'механик': [
        ('Uskunani ta’mirlashdan oldin nima qilinadi?',
         [('Energiyani uzib, belgilash', True), ('Darhol ochish', False),
          ('Faqat yuvish', False), ('Hech narsa', False)]),
        ('Moylash grafikiga rioya qilish nima uchun muhim?',
         [('Eskirishni kamaytiradi', True), ('Rangini o‘zgartiradi', False),
          ('Faqat ko‘rinish', False), ('Kerak emas', False)]),
        ('G‘ildirak / podshipnik shovqin bersa?',
         [('To‘xtatib tekshirish', True), ('Tezlashtirish', False),
          ('E’tiborsiz', False), ('Faqat yuvish', False)]),
        ('Asboblarni saqlash tartibi?',
         [('Belgilangan joyda, toza', True), ('Ish joyida tarqoq', False),
          ('Tashqarida', False), ('Ixtiyoriy', False)]),
        ('Lockout/Tagout maqsadi nima?',
         [('Tasodifiy ishga tushishni oldini olish', True), ('Tezroq ishlash', False),
          ('Faqat hisobot', False), ('Bezash', False)]),
    ],
    'электрик': [
        ('Elektr paneldagi ishdan oldin?',
         [('Kuchlanishni o‘lchab, uzish', True), ('Qo‘l bilan tekshirish', False),
          ('Faqat ko‘rish', False), ('Hech narsa', False)]),
        ('Nam joyda qaysi himoya muhim?',
         [('Dielektrik qo‘lqop / poyabzal', True), ('Faqat kepka', False),
          ('Faqat ko‘zoynak', False), ('Hech narsa', False)]),
        ('Qisqa tutashuv belgilari?',
         [('Uchqun, hid, issiqlik', True), ('Past shovqin', False),
          ('Faqat yorug‘lik', False), ('Hech narsa', False)]),
        ('Kabel izolyatsiyasi shikastlanganda?',
         [('Almashtirish / ta’mirlash', True), ('Izolyatsiya lentasiz qoldirish', False),
          ('E’tiborsiz', False), ('Faqat bo‘yash', False)]),
        ('Yerga ulash (zazemleniye) nima uchun?',
         [('Xavfsizlik va oqim yo‘li', True), ('Chiroqni yoqish', False),
          ('Faqat bezak', False), ('Kerak emas', False)]),
    ],
    'офисный-персонал': [
        ('Korporativ parol qanday bo‘lishi kerak?',
         [('Murakkab va maxfiy', True), ('123456', False),
          ('Username bilan bir xil', False), ('Bo‘sh', False)]),
        ('Shaxsiy ma’lumotlarni qanday uzatish mumkin?',
         [('Himoyalangan kanallar orqali', True), ('Ochiq chat', False),
          ('Ijtimoiy tarmoq', False), ('USB bilan istalgan kishiga', False)]),
        ('Yong‘in chiqish yo‘llari?',
         [('Bo‘sh va belgilangan', True), ('Yopiq', False),
          ('Ombor sifatida', False), ('Ixtiyoriy', False)]),
        ('Ichki hujjatlar qayerda saqlanadi?',
         [('Rasmiy tizim / LMS', True), ('Shaxsiy telefon', False),
          ('Ochiq disk', False), ('Hech qayerda', False)]),
        ('Mehmon zavodga kirganda?',
         [('Ro‘yxatdan o‘tkazish va kuzatuv', True), ('Erkin yurish', False),
          ('Faqat salom', False), ('Hech narsa', False)]),
    ],
    'технолог': [
        ('Texnologik reglament nima?',
         [('Jarayonning majburiy tartibi', True), ('Ixtiyoriy maslahat', False),
          ('Faqat reklama', False), ('Moliyaviy hisobot', False)]),
        ('Sifat nazorati qachon o‘tkaziladi?',
         [('Jarayon davomida va oxirida', True), ('Faqat yilda bir marta', False),
          ('Hech qachon', False), ('Faqat shikoyatda', False)]),
        ('Parametr chegara qiymatidan chiqsa?',
         [('To‘xtatish / tuzatish', True), ('E’tiborsiz', False),
          ('Tezlashtirish', False), ('Yashirish', False)]),
        ('Namuna olish tartibi?',
         [('Standart bo‘yicha', True), ('Tasodifan', False),
          ('Faqat ko‘z bilan', False), ('Kerak emas', False)]),
        ('Xavfsizlik pasporti nima uchun?',
         [('Mahsulot xavfini tushuntirish', True), ('Faqat bezak', False),
          ('Narx belgilash', False), ('Kerak emas', False)]),
    ],
}


GENERIC_Q = [
    ('Ish joyida xavfsizlik qoidalari majburiymi?',
     [('Ha', True), ('Yo‘q', False), ('Faqat tungi smenada', False), ('Ixtiyoriy', False)]),
    ('Baxtsiz hodisa sodir bo‘lsa birinchi qadam?',
     [('Xabar berish va yordam chaqirish', True), ('Yashirish', False),
      ('Ishni davom ettirish', False), ('Uyga ketish', False)]),
    ('PPE (himoya vositalari) nima?',
     [('Shaxsiy himoya jihozlari', True), ('Kompyuter dasturi', False),
      ('Oshxona asbobi', False), ('Transport', False)]),
    ('Yong‘in o‘chirish vositasi qayerda bo‘lishi kerak?',
     [('Oson ochiladigan joyda', True), ('Yopiq omborda', False),
      ('Uyda', False), ('Kerak emas', False)]),
    ('Ichki yo‘riqnoma qayerdan o‘qiladi?',
     [('LMS / hujjatlar bo‘limidan', True), ('Ijtimoiy tarmoqdan', False),
      ('Faqat og‘zaki', False), ('Hech qayerdan', False)]),
]


class Command(BaseCommand):
    help = 'Demo ma’lumotlar: xodimlar, kurslar, materiallar, hujjatlar, testlar'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Demo obyektlarni o‘chirib qayta yaratish (admin tashqari demo userlar)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self._reset_demo()

        admin = self._ensure_admin()
        users = self._seed_users()
        self._seed_tests()
        cats = self._seed_material_categories()
        self._seed_posts(cats)
        doc_cats = self._seed_document_categories()
        self._seed_documents(admin, doc_cats)
        course_cats = self._seed_course_categories()
        courses = self._seed_courses(course_cats)
        self._seed_enrollments(users, courses)

        self.stdout.write(self.style.SUCCESS('\n=== Demo baza tayyor ==='))
        self.stdout.write(f'Admin: admin / (mavjud parol) yoki yangi: {DEMO_PASSWORD}')
        self.stdout.write(f'Demo xodimlar paroli: {DEMO_PASSWORD}')
        self.stdout.write('Misollar: operator01, mexanik01, ofis01, elektr01')

    def _reset_demo(self):
        User.objects.filter(username__endswith='01').exclude(username='admin').delete()
        Post.objects.all().delete()
        Category.objects.all().delete()
        Document.objects.all().delete()
        DocumentCategory.objects.all().delete()
        Course.objects.all().delete()
        CourseCategory.objects.all().delete()
        # Keep tests structure but clear weak demo titles later
        self.stdout.write(self.style.WARNING('Demo kontent tozalandi'))

    def _ensure_admin(self):
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
                'first_name': 'Isomer',
                'last_name': 'Admin',
                'email': 'admin@isomer.local',
            },
        )
        if created:
            admin.set_password(DEMO_PASSWORD)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f'Admin yaratildi: admin / {DEMO_PASSWORD}'))
        else:
            admin.role = 'admin'
            admin.is_staff = True
            admin.is_superuser = True
            admin.save(update_fields=['role', 'is_staff', 'is_superuser'])
        return admin

    def _seed_users(self):
        demo_users = [
            ('operator01', 'Оператор', 'Ali', 'Operator'),
            ('dispatcher01', 'Диспетчер', 'Dilshod', 'Dispatcher'),
            ('mexanik01', 'механик', 'Bekzod', 'Mexanik'),
            ('elektr01', 'электрик', 'Sardor', 'Elektrik'),
            ('texnolog01', 'технолог', 'Nodira', 'Texnolog'),
            ('ofis01', 'офисный-персонал', 'Madina', 'Ofis'),
            ('sklad01', 'склад', 'Jasur', 'Sklad'),
            ('qorovul01', 'охраник', 'Olim', 'Qorovul'),
            ('payvand01', 'сварщик', 'Rustam', 'Payvandchi'),
            ('ishlab01', 'естокада', 'Aziz', 'Ishlab'),
        ]
        created = []
        for username, role, first, last in demo_users:
            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={
                    'role': role,
                    'first_name': first,
                    'last_name': last,
                    'email': f'{username}@isomer.local',
                    'bio': f'{last} — Isomer Oil demo xodimi',
                    'phone_number': '+998901112233',
                },
            )
            if was_created:
                user.set_password(DEMO_PASSWORD)
                user.save()
                self.stdout.write(f'  + user {username} ({role})')
            else:
                user.role = role
                user.save(update_fields=['role'])
            created.append(user)
        return created

    def _seed_tests(self):
        today = timezone.localdate()
        for role_key, role_label in User.ROLE_CHOICES:
            if role_key == 'admin':
                continue
            qs = ROLE_QUESTIONS.get(role_key, GENERIC_Q)
            title = f'{role_label} — bilim tekshiruvi'
            test, created = Test.objects.get_or_create(
                role=role_key,
                title=title,
                defaults={
                    'description': f'{role_label} uchun xavfsizlik va kasbiy bilim testi.',
                    'time_limit': 20,
                    'passing_score': 70,
                    'is_active': True,
                    'is_mandatory': role_key in ('Оператор', 'механик', 'электрик'),
                    'deadline': today + timedelta(days=14),
                },
            )
            if not created and test.questions.count() >= 5:
                continue
            if not created:
                test.questions.all().delete()
                test.is_mandatory = role_key in ('Оператор', 'механик', 'электрик')
                test.deadline = today + timedelta(days=14)
                test.is_active = True
                test.save()

            for text, options in qs:
                q = Question.objects.create(test=test, text=text, explanation='Yo‘riqnomaga asosan.')
                for opt_text, is_correct in options:
                    Option.objects.create(question=q, text=opt_text, is_correct=is_correct)
            self.stdout.write(f'  + test: {title} ({len(qs)} savol)')

    def _seed_material_categories(self):
        data = [
            ('Xavfsizlik', 'Mehnat muhofazasi va yong‘in xavfsizligi'),
            ('Texnologiya', 'Ishlab chiqarish jarayonlari'),
            ('Sifat', 'Sifat nazorati va standartlar'),
            ('Umumiy', 'Korxona ichki tartiblari'),
        ]
        cats = []
        for name, desc in data:
            cat, _ = Category.objects.get_or_create(name=name, defaults={'description': desc})
            cats.append(cat)
        return cats

    def _seed_posts(self, cats):
        posts = [
            ('Yong‘in xavfsizligi qoidalari', cats[0], 'Оператор',
             'Yong‘in o‘chirish vositalari joylashuvi, evakuatsiya yo‘llari va signal tartibi. Har bir xodim yo‘riqnomani bilishi shart.'),
            ('Shaxsiy himoya vositalari (PPE)', cats[0], 'механик',
             'Kass, ko‘zoynak, qo‘lqop va maxsus poyabzal. Ish joyiga kirishdan oldin tekshiring.'),
            ('Neft mahsulotlari bilan ishlash', cats[1], 'Оператор',
             'Bug‘lar, issiqlik va yong‘in xavfi. Ventilyatsiya va yerlashuv talablari.'),
            ('Sifat nazorati namunalari', cats[2], 'технолог',
             'Namuna olish, labaratoriya topshirig‘i va chegara qiymatlari haqida qisqa yo‘riqnoma.'),
            ('Ofis axborot xavfsizligi', cats[3], 'офисный-персонал',
             'Parollar, hujjatlar maxfiyligi va mehmonlarni kuzatish tartibi.'),
            ('Elektr panellarida ishlash', cats[1], 'электрик',
             'Kuchlanishni o‘chirish, belgilash va o‘lchash tartibi. Lockout/Tagout.'),
            ('Ombor tartibi', cats[3], 'склад',
             'Saqlash zonasi, yorliqlar va yuklash xavfsizligi.'),
            ('Smena topshirig‘i', cats[3], 'Диспетчер',
             'Smena jurnalini to‘ldirish, ogohlantirishlar va aloqa kanallari.'),
        ]
        for title, cat, role, content in posts:
            Post.objects.get_or_create(
                title=title,
                category=cat,
                role=role,
                defaults={'content': content},
            )
        self.stdout.write(f'  + materiallar: {len(posts)} post')

    def _seed_document_categories(self):
        data = [
            ('Yo‘riqnomalar', 'Ish tartibi va xavfsizlik', 'fas fa-book'),
            ('Texnik', 'Uskuna va texnologiya', 'fas fa-cogs'),
            ('Sifat', 'Standartlar va shakllar', 'fas fa-check-double'),
            ('Buyruqlar', 'Ichki buyruqlar', 'fas fa-file-alt'),
        ]
        cats = []
        for name, desc, icon in data:
            cat, _ = DocumentCategory.objects.get_or_create(
                name=name, defaults={'description': desc, 'icon': icon}
            )
            cats.append(cat)
        return cats

    def _seed_documents(self, admin, cats):
        docs = [
            ('Mehnat muhofazasi yo‘riqnomasi', cats[0], True, [],
             'Barcha xodimlar uchun ochiq asosiy yo‘riqnoma.'),
            ('Operator smena tartibi', cats[0], False, ['Оператор', 'Диспетчер'],
             'Operator va dispatcher uchun smena qoidalari.'),
            ('Mexanik uskunalar bo‘yicha qo‘llanma', cats[1], False, ['механик', 'слесарь'],
             'Asosiy uskunalarni sozlash va moylash.'),
            ('Elektr xavfsizligi', cats[1], False, ['электрик', 'КИП и А'],
             'Elektr ishlari uchun majburiy qoidalar.'),
            ('Sifat nazorati shakli', cats[2], False, ['технолог', 'офисный-персонал'],
             'Namuna olish va hisobot shakli.'),
            ('Ichki tartib-qoida', cats[3], True, [],
             'Korxona ichki tartib-qoidalari.'),
        ]
        for title, cat, is_public, roles, desc in docs:
            if Document.objects.filter(title=title).exists():
                continue
            doc = Document(
                title=title,
                description=desc,
                category=cat,
                is_public=is_public,
                allowed_roles=roles,
                uploaded_by=admin,
                file_type='pdf',
            )
            doc.file.save(f'{slugify(title) or "doc"}.pdf', ContentFile(MINI_PDF), save=False)
            doc.save()
            self.stdout.write(f'  + hujjat: {title}')

    def _seed_course_categories(self):
        data = [
            ('Xavfsizlik', 'Mehnat muhofazasi kurslari'),
            ('Ishlab chiqarish', 'Texnologik jarayonlar'),
            ('Texnik xizmat', 'Mexanika va elektr'),
        ]
        cats = []
        for name, desc in data:
            cat, _ = CourseCategory.objects.get_or_create(
                name=name,
                defaults={'description': desc, 'slug': slugify(name) or 'cat'},
            )
            if not cat.slug:
                cat.slug = slugify(name) or f'cat-{cat.pk}'
                cat.save(update_fields=['slug'])
            cats.append(cat)
        return cats

    def _seed_courses(self, cats):
        specs = [
            {
                'title': 'Zavod xavfsizligi asoslari',
                'slug': 'zavod-xavfsizligi-asoslari',
                'short': 'PPE, yong‘in, evakuatsiya',
                'desc': 'Barcha xodimlar uchun majburiy kirish kursi. Himoya vositalari, signalizatsiya va favqulodda harakatlar.',
                'category': cats[0],
                'difficulty': 'beginner',
                'featured': True,
                'modules': [
                    ('Kirish', [
                        ('Korxona xavfsizlik madaniyati', 'text', 8,
                         '<p>Isomer Oil da xavfsizlik birinchi o‘rinda. Har bir xodim yo‘riqnomani bilishi shart.</p>'),
                        ('PPE tanlash', 'text', 10,
                         '<p>Kass, ko‘zoynak, qo‘lqop, maxsus kiyim. Ish turiga qarab tanlang.</p>'),
                    ]),
                    ('Favqulodda holatlar', [
                        ('Signal va evakuatsiya', 'text', 12,
                         '<p>Signal eshitilganda ishni to‘xtating, yig‘ilish nuqtasiga boring, rahbarga xabar bering.</p>'),
                        ('Yong‘in o‘chirish asoslari', 'text', 15,
                         '<p>O‘chirgich turlari, joylashuvi va ishlatish tartibi.</p>'),
                    ]),
                ],
            },
            {
                'title': 'Operator smena kursi',
                'slug': 'operator-smena-kursi',
                'short': 'Smena, jurnal, uskunalar',
                'desc': 'Operatorlar uchun smena topshirig‘i, jurnal yuritish va asosiy uskunalar bilan ishlash.',
                'category': cats[1],
                'difficulty': 'intermediate',
                'featured': True,
                'modules': [
                    ('Smena tartibi', [
                        ('Smena qabul qilish', 'text', 10,
                         '<p>Oldingi smenadan holatni oling, jurnalni o‘qing, nosozliklarni tekshiring.</p>'),
                        ('Nazorat parametrlari', 'text', 12,
                         '<p>Bosim, harorat va daraja ko‘rsatkichlarini kuzating.</p>'),
                    ]),
                ],
            },
            {
                'title': 'Mexanik texnik xizmat',
                'slug': 'mexanik-texnik-xizmat',
                'short': 'Moylash, Lockout, diagnostika',
                'desc': 'Mexaniklar uchun reja asosida texnik xizmat va xavfsiz ta’mirlash.',
                'category': cats[2],
                'difficulty': 'intermediate',
                'featured': False,
                'modules': [
                    ('Asoslar', [
                        ('Lockout/Tagout', 'text', 14,
                         '<p>Energiyani uzing, qulflang, belgilang. Ish tugaguncha olib tashlamang.</p>'),
                        ('Moylash grafigi', 'text', 10,
                         '<p>Moy turi, davriylik va qayd etish tartibi.</p>'),
                    ]),
                ],
            },
            {
                'title': 'Elektr xavfsizligi',
                'slug': 'elektr-xavfsizligi',
                'short': 'Panel, o‘lchash, himoya',
                'desc': 'Elektromontyorlar uchun asosiy xavfsizlik va o‘lchash amaliyoti.',
                'category': cats[2],
                'difficulty': 'advanced',
                'featured': True,
                'modules': [
                    ('Xavfsiz ish', [
                        ('Kuchlanishni tekshirish', 'text', 12,
                         '<p>Multimetr bilan tekshiring. Nam joyda dielektrik himoya majburiy.</p>'),
                        ('Yerga ulash', 'text', 10,
                         '<p>Zazemleniye tekshiruvi va kontakt sifatini nazorat qiling.</p>'),
                    ]),
                ],
            },
        ]
        courses = []
        for spec in specs:
            course, created = Course.objects.get_or_create(
                slug=spec['slug'],
                defaults={
                    'title': spec['title'],
                    'description': spec['desc'],
                    'short_description': spec['short'],
                    'category': spec['category'],
                    'difficulty': spec['difficulty'],
                    'duration': 60,
                    'status': 'published',
                    'is_featured': spec['featured'],
                    'is_free': True,
                    'price': 0,
                },
            )
            if created or not course.modules.exists():
                if not created:
                    course.modules.all().delete()
                for m_idx, (m_title, lessons) in enumerate(spec['modules'], start=1):
                    module = Module.objects.create(
                        course=course, title=m_title, description=m_title, order=m_idx
                    )
                    for l_idx, (l_title, l_type, dur, content) in enumerate(lessons, start=1):
                        Lesson.objects.create(
                            module=module,
                            title=l_title,
                            content=content,
                            lesson_type=l_type,
                            duration=dur,
                            order=l_idx,
                            is_free_preview=(m_idx == 1 and l_idx == 1),
                        )
                self.stdout.write(f'  + kurs: {course.title}')
            courses.append(course)
        return courses

    def _seed_enrollments(self, users, courses):
        by_role = {u.role: u for u in users}
        pairs = [
            ('Оператор', 'operator-smena-kursi'),
            ('Оператор', 'zavod-xavfsizligi-asoslari'),
            ('механик', 'mexanik-texnik-xizmat'),
            ('механик', 'zavod-xavfsizligi-asoslari'),
            ('электрик', 'elektr-xavfsizligi'),
            ('офисный-персонал', 'zavod-xavfsizligi-asoslari'),
            ('технолог', 'zavod-xavfsizligi-asoslari'),
        ]
        slug_map = {c.slug: c for c in courses}
        for role, slug in pairs:
            user = by_role.get(role)
            course = slug_map.get(slug)
            if not user or not course:
                continue
            Enrollment.objects.get_or_create(user=user, course=course)
        self.stdout.write('  + enrollments yaratildi')
