import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from blog.models import Test, Question, Option
from accounts.models import User
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Generate daily tests with 30 questions for each role'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force generation even if tests were already created today')
        parser.add_argument('--test_roles', type=str, nargs='+', help='Specific roles to generate tests for (defaults to all roles)')

    def generate_test_questions(self, role, num_questions=30):
        """Generate test questions based on role"""
        questions = []
        
        # Different question templates based on role
        templates = {
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
                "{}da nechta ishchi qatnashishi kerak?"
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
                "{}da shovqinning ortishiga nima sabab bo'lishi mumkin?"
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
                "{}ga qanday xavfsizlik standartlari qo'llaniladi?"
            ],
            'админ': [
                "{}ga kirish huquqlarini qanday sozlash kerak?",
                "{}da ma'lumotlarni himoya qilishning qanday usullari qo'llaniladi?",
                "{}ning ishlash samaradorligini oshirish uchun qanday optimallashtirishlar kerak?",
                "{}ni monitoring qilish uchun qanday vositalardan foydalanish kerak?",
                "{}ning zaxira nusxasini qanday sozlash kerak?",
                "{}da qanday aloqa protokollaridan foydalaniladi?",
                "{}da foydalanuvchi hisoblarini qanday boshqarish kerak?",
                "{}da zaiflik aniqlanganda qanday choralar ko'rish kerak?",
                "{}da jarayonlarni avtomatlashtirish uchun qanday sozlamalar kerak?",
                "{}ni miqyoslash uchun qanday usullar mos keladi?"
            ]
        }
        
        # Different subjects based on role
        subjects = {
            'оператор': [
                "dastgohni ishga tushirish", "konveyerda ishlash", "detallar sifatini tekshirish",
                "yuklash ishlari", "payvandlash uskunalari bilan ishlash", "CNC dastgohlarida ishlash",
                "asbobni almashtirish", "xavfli materiallar bilan ishlash", "tayyor mahsulotni tekshirish",
                "detallarni transportirovka qilish", "tungi smenada ishlash", "uskunalarni favqulodda to'xtatish"
            ],
            'наладчик': [
                "frezerlash dastgohi", "tokarlik dastgohi", "payvandlash apparati", 
                "konveyer liniyasi", "o'lchov uskunalari", "gidravlik tizim", 
                "pnevmatik tizim", "elektr tizimi", "sovutish tizimi", 
                "moylash tizimi", "avtomatlashtirilgan liniya", "robot-manipulyator"
            ],
            'инженер': [
                "ishlab chiqarish liniyasi", "avtomatlashtirish tizimi", "sanoat roboti", 
                "sifat nazorati tizimi", "energiya tejamkor tizim", "ventilyatsiya tizimi", 
                "mahsulot konstruksiyasi", "texnologik jarayon", "xavfsizlik tizimi", 
                "CNC dasturiy ta'minoti", "monitoring tizimi", "muhandislik kommunikatsiyalari"
            ],
            'админ': [
                "server infratuzilmasi", "tarmoq uskunalari", "korxonani boshqarish tizimi", 
                "ma'lumotlar bazasi", "kirishni nazorat qilish tizimi", "korporativ tarmoq", 
                "videokuzatuv tizimi", "mobil qurilmalar", "bulutli xizmatlar", 
                "resurslarni hisobga olish tizimi", "masofaviy kirish", "zaxira nusxalash tizimi"
            ]
        }
        
        # If role not in templates, use operator as default
        role_templates = templates.get(role, templates['оператор'])
        role_subjects = subjects.get(role, subjects['оператор'])
        
        # Generate unique questions
        for i in range(num_questions):
            # Select random template and subject
            template = random.choice(role_templates)
            subject = random.choice(role_subjects)
            
            # Create question
            question_text = template.format(subject)
            
            # Generate options (3 wrong, 1 correct)
            correct_option = self.generate_option_text(role, subject, is_correct=True)
            
            wrong_options = []
            for _ in range(3):
                wrong_option = self.generate_option_text(role, subject, is_correct=False)
                # Ensure uniqueness
                while wrong_option in wrong_options:
                    wrong_option = self.generate_option_text(role, subject, is_correct=False)
                wrong_options.append(wrong_option)
            
            # Add to questions list
            questions.append({
                'text': question_text,
                'options': [
                    {'text': correct_option, 'is_correct': True},
                    {'text': wrong_options[0], 'is_correct': False},
                    {'text': wrong_options[1], 'is_correct': False},
                    {'text': wrong_options[2], 'is_correct': False}
                ]
            })
        
        return questions
    
    def generate_option_text(self, role, subject, is_correct=False):
        """Generate option text based on role and correctness"""
        
        # Correct answer templates
        correct_answers = {
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
                "Ish joyining tozaligini saqlash"
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
                "Nosozliklarni tahlil qilishning zamonaviy usullaridan foydalanish"
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
                "Oldindan texnik xizmat ko'rsatish tizimini joriy etish"
            ],
            'админ': [
                "Ko'p bosqichli autentifikatsiya tizimini sozlash",
                "Ma'lumotlarni shifrlash va muntazam zaxiralashni joriy etish",
                "Dasturiy ta'minotni muntazam yangilab turish va xavfsizlikni tekshirish",
                "Tizim resurslarini monitoring qilish va ishlashni optimallashtirish",
                "Muhim hodisalar haqida avtomatik xabarnomalarni sozlash",
                "Axborot xavfsizligi hodisalarini boshqarish tizimini joriy etish",
                "Xavfsizlik siyosatini ishlab chiqish va qo'llab-quvvatlash",
                "Resurslarni optimallashtirish uchun virtualizatsiyadan foydalanish",
                "Tizimni avtomatik ravishda miqyoslashni sozlash",
                "Muntazam xavfsizlik auditi va kirish sinovlarini o'tkazish"
            ]
        }
        
        # Incorrect answer templates
        incorrect_answers = {
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
                "Ruxsatsiz uskunaga o'zgartirish kiritish"
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
                "Sxemalar va texnik hujjatlarsiz ishlash"
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
                "Xalqaro sifat standartlariga e'tibor bermaslik"
            ],
            'админ': [
                "Barcha tizimlar uchun standart parollardan foydalanish",
                "Xavfsizlik yangilanishlarini e'tiborsiz qoldirish",
                "Yuqori yuklanishda monitoring tizimlarini o'chirish",
                "Zaxira nusxalarni faqat lokal saqlash",
                "Foydalanuvchilarga ortiqcha kirish huquqlarini berish",
                "Tizim xavfsizligi ogohlantirishlarini e'tiborsiz qoldirish",
                "Konfiguratsiya o'zgarishlarini hujjatlashtirishni unutish",
                "Ruxsat etilmagan dasturiy ta'minotdan foydalanish",
                "Tarmoqning segmentatsiyasiga e'tibor bermaslik",
                "Xavfsizlik auditini kechiktirish"
            ]
        }
        
        # Get the appropriate answer templates based on role
        if is_correct:
            answers = correct_answers.get(role, correct_answers['оператор'])
        else:
            answers = incorrect_answers.get(role, incorrect_answers['оператор'])
        
        return random.choice(answers)
    
    def handle(self, *args, **options):
        force = options.get('force', False)
        test_roles = options.get('test_roles')
        
        # Get today's date
        today = timezone.now().date()
        
        # Check if we already generated tests today
        if not force:
            today_tests = Test.objects.filter(
                created_at__date=today,
                title__contains="Kunlik test"
            )
            
            if today_tests.exists():
                self.stdout.write(self.style.WARNING('Bugun uchun testlar allaqachon yaratilgan. Qayta yaratish uchun --force parametridan foydalaning.'))
                return
        
        # Get all roles or specified roles
        if test_roles:
            roles = test_roles
        else:
            roles = [choice[0] for choice in User.ROLE_CHOICES]
        
        # Today's date formatted
        date_str = today.strftime("%d.%m.%Y")
        
        for role in roles:
            try:
                with transaction.atomic():
                    # Create test for this role
                    role_display = dict(User.ROLE_CHOICES).get(role, role)
                    test_title = f"Kunlik test: {role_display} ({date_str})"
                    test = Test.objects.create(
                        title=test_title,
                        description=f"Bilimlarni tekshirish uchun avtomatik yaratilgan test. Sana: {date_str}",
                        role=role,
                        passing_score=70.0,  # 70% to pass
                        time_limit=30,       # 30 minutes
                        is_active=True,
                        created_at=timezone.now()
                    )
                    
                    # Generate questions for this role
                    questions_data = self.generate_test_questions(role, 30)
                    
                    # Create questions and options
                    for q_data in questions_data:
                        question = Question.objects.create(
                            test=test,
                            text=q_data['text']
                        )
                        
                        # Randomize options order
                        options = q_data['options'].copy()
                        random.shuffle(options)
                        
                        # Create options
                        for option_data in options:
                            Option.objects.create(
                                question=question,
                                text=option_data['text'],
                                is_correct=option_data['is_correct']
                            )
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'Test muvaffaqiyatli yaratildi: "{test.title}" (30 ta savol)')
                    )
            
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'"{role}" roli uchun test yaratishda xatolik: {str(e)}')
                ) 