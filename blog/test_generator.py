"""
Role-based automatic test generation (AI-style template engine).

Used by:
- management command generate_daily_tests
- admin "AI test yaratish" action
"""
from __future__ import annotations

import random
from datetime import date

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from blog.models import Option, Question, Test

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

TEMPLATES = {
    'оператор': [
        "{}ga oid qanday harakatlarni bajarish kerak?",
        "{}ning maksimal ruxsat etilgan qiymati qancha?",
        "{}da qaysi asbobdan foydalaniladi?",
        "{}da ishlayotganda himoya vositalaridan foydalanish kerakmi?",
        "{}da amallar tartibi qanday?",
        "Qancha vaqt ichida {} bajarilishi kerak?",
        "{}da qanday minimal masofa saqlanishi kerak?",
        "{}da favqulodda vaziyat yuz berganda nima qilish kerak?",
        "{}ning qaysi ko'rsatkichi normal hisoblanadi?",
        "{}da nechta ishchi qatnashishi kerak?",
    ],
    'наладчик': [
        "{}dagi nosozlikni qanday bartaraf etish mumkin?",
        "{}ni sozlash uchun qaysi asbob eng mos keladi?",
        "{}ni kalibrlashning to'g'ri tartibi qanday?",
        "Qaysi ko'rsatkichda {} soz hisoblanadi?",
        "{}ni ishga tushirishdan oldin qanday parametrlarni tekshirish kerak?",
        "{}ga qancha vaqtda texnik xizmat ko'rsatish kerak?",
        "{}dagi nosozlik sababini qanday aniqlash mumkin?",
        "{}ni ta'mirlash uchun qanday ehtiyot qismlar kerak?",
        "{}ni sozlashda qanday aniqlik talab qilinadi?",
        "{}da shovqinning ortishiga nima sabab bo'lishi mumkin?",
    ],
    'инженер': [
        "{}ning texnik xususiyatlari qanday?",
        "{}ning optimal ishlash samaradorligini qanday hisoblash mumkin?",
        "{}ning samaradorligiga qanday omillar ta'sir qiladi?",
        "{}ni boshqarish tizimini qanday loyihalash kerak?",
        "{}da qanday materiallardan foydalanish yaxshiroq?",
        "{}ni baholash uchun qanday tahlil usuli mos keladi?",
        "{}ning energiya samaradorligini qanday oshirish mumkin?",
        "{}da qanday innovatsion yechimlar qo'llanilishi mumkin?",
        "{}ni boshqarish tizimi bilan qanday integratsiyalash mumkin?",
        "{}ga qanday xavfsizlik standartlari qo'llaniladi?",
    ],
    'admin': [
        "{}ga kirish huquqlarini qanday sozlash kerak?",
        "{}da ma'lumotlarni himoya qilishning qanday usullari qo'llaniladi?",
        "{}ning ishlash samaradorligini oshirish uchun qanday optimallashtirishlar kerak?",
        "{}ni monitoring qilish uchun qanday vositalardan foydalanish kerak?",
        "{}ning zaxira nusxasini qanday sozlash kerak?",
        "{}da qanday aloqa protokollaridan foydalaniladi?",
        "{}da foydalanuvchi hisoblarini qanday boshqarish kerak?",
        "{}da zaiflik aniqlanganda qanday choralar ko'rish kerak?",
        "{}da jarayonlarni avtomatlashtirish uchun qanday sozlamalar kerak?",
        "{}ni miqyoslash uchun qanday usullar mos keladi?",
    ],
}

SUBJECTS = {
    'оператор': [
        "dastgohni ishga tushirish", "konveyerda ishlash", "detallar sifatini tekshirish",
        "yuklash ishlari", "payvandlash uskunalari bilan ishlash", "CNC dastgohlarida ishlash",
        "asbobni almashtirish", "xavfli materiallar bilan ishlash", "tayyor mahsulotni tekshirish",
        "detallarni transportirovka qilish", "tungi smenada ishlash", "uskunalarni favqulodda to'xtatish",
    ],
    'наладчик': [
        "frezerlash dastgohi", "tokarlik dastgohi", "payvandlash apparati",
        "konveyer liniyasi", "o'lchov uskunalari", "gidravlik tizim",
        "pnevmatik tizim", "elektr tizimi", "sovutish tizimi",
        "moylash tizimi", "avtomatlashtirilgan liniya", "robot-manipulyator",
    ],
    'инженер': [
        "ishlab chiqarish liniyasi", "avtomatlashtirish tizimi", "sanoat roboti",
        "sifat nazorati tizimi", "energiya tejamkor tizim", "ventilyatsiya tizimi",
        "mahsulot konstruksiyasi", "texnologik jarayon", "xavfsizlik tizimi",
        "CNC dasturiy ta'minoti", "monitoring tizimi", "muhandislik kommunikatsiyalari",
    ],
    'admin': [
        "server infratuzilmasi", "tarmoq uskunalari", "korxonani boshqarish tizimi",
        "ma'lumotlar bazasi", "kirishni nazorat qilish tizimi", "korporativ tarmoq",
        "videokuzatuv tizimi", "mobil qurilmalar", "bulutli xizmatlar",
        "resurslarni hisobga olish tizimi", "masofaviy kirish", "zaxira nusxalash tizimi",
    ],
}

CORRECT_ANSWERS = {
    'оператор': [
        "Yo'riqnomaga rioya qilish va himoya vositalaridan foydalanish",
        "Ishga tushirishdan oldin barcha parametrlarni tekshirish",
        "Rahbarga xabar berish va ishni to'xtatish",
        "Harakatlarni qat'iy ketma-ketlikda bajarish",
        "Maxsus asbobdan foydalanish",
        "Ruxsat etilgan yuklamadan oshirmaslik",
        "Xavfsizlik texnikasiga rioya qilish",
        "Hamkasblar bilan harakatlarni muvofiqlashtirish",
        "Asboblar ko'rsatkichlarini muntazam tekshirib turish",
        "Ish joyining tozaligini saqlash",
    ],
    'наладчик': [
        "Elektr kontaktlarini tekshirish va eskirgan detallarni almashtirish",
        "Ishdan oldin o'lchov asboblarini kalibrlash",
        "Aniq sozlash uchun maxsus asboblardan foydalanish",
        "Tizimni iflosliklardan tozalash va filtrlarni almashtirish",
        "Detallarning texnik talablarga muvofiqligini tekshirish",
        "Qismlarga ajratish va yig'ish ketma-ketligiga qat'iy rioya qilish",
        "Eskirgan qismlarni original ehtiyot qismlar bilan almashtirish",
        "Parametrlarni texnik xususiyatlarga muvofiq sozlash",
        "Ishga tushirishdan oldin barcha tizimlarga diagnostika o'tkazish",
        "Nosozliklarni tahlil qilishning zamonaviy usullaridan foydalanish",
    ],
    'инженер': [
        "Tizimni to'liq tahlil qilish va parametrlarni optimallashtirish",
        "Barcha omillarni hisobga olgan holda texnik yechim ishlab chiqish",
        "Parametrlarni hisoblash uchun kompyuter modellashtiridan foydalanish",
        "Avtomatlashtirilgan nazorat tizimini integratsiyalash",
        "Energiya tejamkor komponentlar va texnologiyalarni joriy etish",
        "Innovatsion materiallar va texnologiyalarni qo'llash",
        "Ish jarayonlarini standartlarga muvofiq optimallashtirish",
        "Monitoring va boshqarish uchun kompleks tizim ishlab chiqish",
        "Stressga chidamlilikni sinash va tahlil qilish",
        "Oldindan texnik xizmat ko'rsatish tizimini joriy etish",
    ],
    'admin': [
        "Ko'p bosqichli autentifikatsiya tizimini sozlash",
        "Ma'lumotlarni shifrlash va muntazam zaxiralashni joriy etish",
        "Dasturiy ta'minotni muntazam yangilab turish va xavfsizlikni tekshirish",
        "Tizim resurslarini monitoring qilish va ishlashni optimallashtirish",
        "Muhim hodisalar haqida avtomatik xabarnomalarni sozlash",
        "Axborot xavfsizligi hodisalarini boshqarish tizimini joriy etish",
        "Xavfsizlik siyosatini ishlab chiqish va qo'llab-quvvatlash",
        "Resurslarni optimallashtirish uchun virtualizatsiyadan foydalanish",
        "Tizimni avtomatik ravishda miqyoslashni sozlash",
        "Muntazam xavfsizlik auditi va kirish sinovlarini o'tkazish",
    ],
}

INCORRECT_ANSWERS = {
    'оператор': [
        "Tekshiruvlarni o'tkazib yuborish hisobiga jarayonni tezlashtirish",
        "Qulay bo'lishi uchun himoya vositalarisiz ishlash",
        "Tavsiya etilgandan yuklamani oshirish",
        "Ogohlantiruvchi signallarni e'tiborsiz qoldirish",
        "Mos kelmaydigan asbobdan foydalanish",
        "Amallar ketma-ketligini buzish",
        "Uskunani qarovsiz qoldirish",
        "Muntazam texnik xizmat ko'rsatishga e'tibor bermaslik",
        "Asboblar nosoz bo'lganda ishlash",
        "Ruxsatsiz uskunaga o'zgartirish kiritish",
    ],
    'наладчик': [
        "To'liq ta'mirlash o'rniga vaqtinchalik yechimlardan foydalanish",
        "Sozlashdan keyin sinov bosqichini o'tkazib yuborish",
        "Original detallarni o'xshash detallar bilan almashtirish",
        "Kichik nosozliklarni e'tiborsiz qoldirish",
        "Bajarilgan ishlarni hujjatlashtirishni unutish",
        "Parametrlarni aniq o'lchamsiz \"ko'z bilan chamalab\" sozlash",
        "Tizimning elektr ta'minotini o'chirmasdan ishlash",
        "Vaqtni tejash uchun diagnostika bosqichlarini o'tkazib yuborish",
        "Maxsus bo'lmagan asboblardan foydalanish",
        "Sxemalar va texnik hujjatlarsiz ishlash",
    ],
    'инженер': [
        "Optimallashtirishsiz mavjud yechimni takrorlash",
        "Yuklanish va mustahkamlik hisoblarini e'tiborsiz qoldirish",
        "Energiya tejaydigan talablarni e'tiborsiz qoldirish",
        "Eskirgan texnologiyalar va standartlardan foydalanish",
        "Materiallar va komponentlarda tejash",
        "Prototipni sinash bosqichini o'tkazib yuborish",
        "Ekologik talablarni e'tiborsiz qoldirish",
        "Foydalanuvchilar talablarini hisobga olmasdan ishlab chiqish",
        "Xavflarni tahlil qilish va chidamlilikni tekshirmaslik",
        "Xalqaro sifat standartlariga e'tibor bermaslik",
    ],
    'admin': [
        "Barcha tizimlar uchun standart parollardan foydalanish",
        "Xavfsizlik yangilanishlarini e'tiborsiz qoldirish",
        "Yuqori yuklanishda monitoring tizimlarini o'chirish",
        "Zaxira nusxalarni faqat lokal saqlash",
        "Foydalanuvchilarga ortiqcha kirish huquqlarini berish",
        "Tizim xavfsizligi ogohlantirishlarini e'tiborsiz qoldirish",
        "Konfiguratsiya o'zgarishlarini hujjatlashtirishni unutish",
        "Ruxsat etilmagan dasturiy ta'minotdan foydalanish",
        "Tarmoqning segmentatsiyasiga e'tibor bermaslik",
        "Xavfsizlik auditini kechiktirish",
    ],
}


def resolve_bucket(role: str) -> str:
    return ROLE_BUCKET_MAP.get(role, 'оператор')


def generate_option_text(bucket: str, subject: str, is_correct: bool = False) -> str:
    pool = CORRECT_ANSWERS if is_correct else INCORRECT_ANSWERS
    answers = pool.get(bucket, pool['оператор'])
    return random.choice(answers)


def _detect_question_kind(question_text: str) -> str:
    """Match blog.utils.check_question_options_consistency categories."""
    q = question_text.lower()
    quantity_keywords = (
        'nechta', 'qancha', 'necha', 'nechanchi', 'qanchasi', 'miqdori', 'soni',
        'nechtasi', 'qaysi raqam', 'necha marta', 'necha kun',
        'qiymati qancha', 'qanday qiymat',
    )
    time_keywords = (
        'qachon', 'qaysi vaqtda', 'qaysi muddatda', 'qancha vaqt', 'vaqti',
        'soatda', 'daqiqada', 'qaysi kun', 'qaysi oy', 'qaysi yil',
    )
    action_keywords = (
        "nima qilish kerak", "qanday qilish kerak", "kerak bo'ladi", 'qilinadi',
        'bajariladi', 'amalga oshiriladi', 'qilish usuli', 'qanday amalga',
        'qilish tartibi',
    )
    location_keywords = (
        'qayerda', 'qaysi joyda', 'qayerga', 'qaysi manzilda', 'joylashgan',
        'manzili', 'turadi', 'topiladi',
    )
    # Time before quantity: "qancha vaqt" contains "qancha"
    if any(k in q for k in time_keywords):
        return 'time'
    if any(k in q for k in quantity_keywords):
        return 'quantity'
    if any(k in q for k in action_keywords):
        return 'action'
    if any(k in q for k in location_keywords):
        return 'location'
    return 'general'


def _build_options_for_kind(kind: str, bucket: str, subject: str) -> list[dict]:
    """Options that pass the consistency filter for the question kind."""
    if kind == 'quantity':
        nums = [2, 3, 5, 10, 15, 20, 30, 50, 100]
        correct = random.choice(nums)
        wrongs = random.sample([n for n in nums if n != correct], 3)
        return [
            {'text': f'{correct} (ruxsat etilgan qiymat)', 'is_correct': True},
            {'text': f'{wrongs[0]} (noto‘g‘ri qiymat)', 'is_correct': False},
            {'text': f'{wrongs[1]} (ortiqcha yuklama)', 'is_correct': False},
            {'text': f'{wrongs[2]} (yetarli emas)', 'is_correct': False},
        ]
    if kind == 'time':
        variants = [
            ('15 daqiqa', True),
            ('1 soat', False),
            ('3 kun', False),
            ('1 hafta', False),
            ('30 daqiqa', False),
            ('2 soat', False),
            ('1 oy', False),
        ]
        random.shuffle(variants)
        # Ensure exactly one correct
        correct_pool = [v for v in variants if v[0] in ('15 daqiqa', '30 daqiqa')]
        wrong_pool = [v[0] for v in variants if v[0] not in ('15 daqiqa', '30 daqiqa')]
        correct = random.choice(correct_pool)[0] if correct_pool else '15 daqiqa'
        wrongs = random.sample(wrong_pool, 3)
        return [
            {'text': correct, 'is_correct': True},
            {'text': wrongs[0], 'is_correct': False},
            {'text': wrongs[1], 'is_correct': False},
            {'text': wrongs[2], 'is_correct': False},
        ]
    if kind == 'location':
        places = [
            ('ishxona', True),
            ('omborxona binosi', False),
            ('sex hududi', False),
            ('yordamchi xona', False),
            ('nazorat markazi', False),
        ]
        random.shuffle(places)
        correct = 'ishxona'
        wrongs = [p[0] for p in places if p[0] != correct][:3]
        return [
            {'text': correct, 'is_correct': True},
            {'text': wrongs[0], 'is_correct': False},
            {'text': wrongs[1], 'is_correct': False},
            {'text': wrongs[2], 'is_correct': False},
        ]

    # action / general — matnli variantlar (fe'l bilan tugashi kerak bo‘lishi mumkin)
    correct_option = generate_option_text(bucket, subject, is_correct=True)
    wrong_options = []
    for _ in range(3):
        wrong = generate_option_text(bucket, subject, is_correct=False)
        attempts = 0
        while wrong in wrong_options or wrong == correct_option:
            wrong = generate_option_text(bucket, subject, is_correct=False)
            attempts += 1
            if attempts > 20:
                wrong = f'{wrong} qilish'
                break
        wrong_options.append(wrong)

    if kind == 'action':
        # Consistency checker looks for verb-like endings
        def _ensure_action(text: str) -> str:
            endings = ('lash', 'ish', 'ash', 'moq', 'sini', 'shni', 'tiladi', 'dirish', 'iladi')
            if any(text.lower().endswith(e) for e in endings):
                return text
            return f'{text} qilish'

        correct_option = _ensure_action(correct_option)
        wrong_options = [_ensure_action(w) for w in wrong_options]

    return [
        {'text': correct_option, 'is_correct': True},
        {'text': wrong_options[0], 'is_correct': False},
        {'text': wrong_options[1], 'is_correct': False},
        {'text': wrong_options[2], 'is_correct': False},
    ]


def build_template_question_payloads(role: str, num_questions: int = 30) -> list[dict]:
    """Mahalliy shablon generator (AI kaliti bo‘lmasa yoki AI xato bersa)."""
    from blog.utils import check_question_options_consistency

    class _Opt:
        def __init__(self, text):
            self.text = text

    bucket = resolve_bucket(role)
    role_templates = TEMPLATES.get(bucket, TEMPLATES['оператор'])
    role_subjects = SUBJECTS.get(bucket, SUBJECTS['оператор'])
    questions = []

    for _ in range(num_questions):
        template = random.choice(role_templates)
        subject = random.choice(role_subjects)
        question_text = template.format(subject)
        kind = _detect_question_kind(question_text)
        options = _build_options_for_kind(kind, bucket, subject)

        if not check_question_options_consistency(
            question_text, [_Opt(o['text']) for o in options]
        ):
            fallback_kind = 'quantity' if kind == 'quantity' else 'time'
            if kind not in ('quantity', 'time'):
                fallback_kind = 'quantity'
            options = _build_options_for_kind(fallback_kind, bucket, subject)

        random.shuffle(options)
        questions.append({'text': question_text, 'options': options})

    return questions


def build_question_payloads(
    role: str,
    num_questions: int = 30,
    *,
    use_ai: bool = True,
) -> list[dict]:
    """
    Avval bepul AI (Groq/Gemini), bo‘lmasa shablon.
    AI qisman qaytarsa — yetishmaganini shablon bilan to‘ldiradi.
    """
    questions: list[dict] = []
    source = 'template'

    if use_ai:
        try:
            from blog.ai_client import ai_is_configured, generate_questions_via_ai

            if ai_is_configured():
                questions = generate_questions_via_ai(role, num_questions)
                source = 'ai'
        except Exception:
            questions = []
            source = 'template'

    if len(questions) < num_questions:
        need = num_questions - len(questions)
        questions.extend(build_template_question_payloads(role, need))
        if source == 'ai' and need:
            source = 'ai+template'
        elif source != 'ai':
            source = 'template'

    for q in questions:
        random.shuffle(q['options'])

    # Chaqiruvchiga manba haqida signal (ixtiyoriy)
    build_question_payloads.last_source = source  # type: ignore[attr-defined]
    return questions[:num_questions]


# default attribute for tests / admin messages
build_question_payloads.last_source = 'template'  # type: ignore[attr-defined]


def create_test_with_questions(
    role: str,
    *,
    title: str | None = None,
    description: str | None = None,
    num_questions: int = 30,
    passing_score: int = 70,
    time_limit: int = 30,
    is_active: bool = True,
    use_ai: bool = True,
) -> Test:
    """Create one Test + questions/options for a role."""
    valid_roles = {c[0] for c in User.ROLE_CHOICES}
    if role not in valid_roles:
        raise ValueError(f"Noma'lum rol: {role}")

    role_display = dict(User.ROLE_CHOICES).get(role, role)
    today = timezone.localdate()
    date_str = today.strftime('%d.%m.%Y')
    title = title or f"AI test: {role_display} ({date_str})"
    description = description or (
        f"Rol bo‘yicha avtomatik yaratilgan test ({role_display}). "
        f"Sana: {date_str}."
    )

    payloads = build_question_payloads(role, num_questions, use_ai=use_ai)
    source = getattr(build_question_payloads, 'last_source', 'template')
    if source.startswith('ai') and 'Groq' not in description and 'Gemini' not in description:
        description = f"{description} Manba: {source}."

    with transaction.atomic():
        test = Test.objects.create(
            title=title,
            description=description,
            role=role,
            passing_score=passing_score,
            time_limit=time_limit,
            is_active=is_active,
        )
        for q_data in payloads:
            question = Question.objects.create(test=test, text=q_data['text'])
            for option_data in q_data['options']:
                Option.objects.create(
                    question=question,
                    text=option_data['text'],
                    is_correct=option_data['is_correct'],
                )
    return test


def generate_tests_for_role(
    role: str,
    count: int,
    *,
    questions_per_test: int = 30,
    title_prefix: str = 'AI test',
    use_ai: bool = True,
) -> list[Test]:
    """Create `count` tests for one role. Returns created Test list."""
    if count < 1 or count > 50:
        raise ValueError('Testlar soni 1–50 oralig‘ida bo‘lishi kerak')
    if questions_per_test < 5 or questions_per_test > 50:
        raise ValueError('Savollar soni 5–50 oralig‘ida bo‘lishi kerak')

    role_display = dict(User.ROLE_CHOICES).get(role, role)
    stamp = timezone.now().strftime('%d.%m.%Y %H:%M')
    created = []
    for i in range(1, count + 1):
        test = create_test_with_questions(
            role,
            title=f"{title_prefix}: {role_display} #{i} ({stamp})",
            description=(
                f"Avtomatik (AI) yaratilgan test. Rol: {role_display}. "
                f"Partiya: {stamp}."
            ),
            num_questions=questions_per_test,
            use_ai=use_ai,
        )
        created.append(test)
    return created


def generate_daily_tests_for_roles(
    roles: list[str] | None = None,
    *,
    force: bool = False,
    today: date | None = None,
) -> list[Test]:
    """Legacy daily generator used by cron / management command."""
    today = today or timezone.localdate()
    if not force:
        if Test.objects.filter(
            created_at__date=today,
            title__contains='Kunlik test',
        ).exists():
            return []

    roles = roles or [c[0] for c in User.ROLE_CHOICES]
    date_str = today.strftime('%d.%m.%Y')
    created = []
    for role in roles:
        role_display = dict(User.ROLE_CHOICES).get(role, role)
        try:
            test = create_test_with_questions(
                role,
                title=f"Kunlik test: {role_display} ({date_str})",
                description=(
                    f"Bilimlarni tekshirish uchun avtomatik yaratilgan test. "
                    f"Sana: {date_str}"
                ),
                num_questions=30,
            )
            created.append(test)
        except Exception:
            # Bitta rol xatosi boshqalarini to‘xtatmasin
            continue
    return created
