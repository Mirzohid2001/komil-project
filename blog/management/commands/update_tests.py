import json
import logging
import random
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from blog.models import Test, Question, Option, User

# Configure logging
logger = logging.getLogger(__name__)

# API endpoints for different test categories
# This is just a placeholder API - in a real implementation, you would use actual API endpoints
API_ENDPOINTS = {
    'админ': 'https://api.example.com/tests/admin',
    'бухгалтер': 'https://api.example.com/tests/accountant', 
    'естокада': 'https://api.example.com/tests/estokada',
    'финансист': 'https://api.example.com/tests/financier',
}

# Fallback test questions in case API is not accessible
FALLBACK_QUESTIONS = {
    'админ': [
        {
            'question': 'Какой тип аутентификации считается наиболее безопасным?',
            'options': [
                {'text': 'Одиночный пароль', 'is_correct': False},
                {'text': 'Двухфакторная аутентификация', 'is_correct': True},
                {'text': 'Биометрические данные без второго фактора', 'is_correct': False},
                {'text': 'Устаревшие пароли', 'is_correct': False},
            ],
            'explanation': 'Двухфакторная аутентификация добавляет второй уровень безопасности, требуя что-то, что вы знаете (пароль) и что-то, что у вас есть (например, телефон).'
        },
        {
            'question': 'Какой протокол используется для безопасного просмотра веб-страниц?',
            'options': [
                {'text': 'HTTP', 'is_correct': False},
                {'text': 'FTP', 'is_correct': False},
                {'text': 'HTTPS', 'is_correct': True},
                {'text': 'SMTP', 'is_correct': False},
            ],
            'explanation': 'HTTPS (HTTP Secure) шифрует данные, передаваемые между вашим браузером и веб-сайтом, защищая их от перехвата.'
        },
    ],
    'бухгалтер': [
        {
            'question': 'Что такое двойная запись в бухгалтерском учете?',
            'options': [
                {'text': 'Каждая операция записывается дважды для проверки', 'is_correct': False},
                {'text': 'Каждая операция отражается по дебету одного и кредиту другого счета', 'is_correct': True},
                {'text': 'Бухгалтер проверяет каждую запись дважды', 'is_correct': False},
                {'text': 'Запись, сделанная двумя бухгалтерами независимо', 'is_correct': False},
            ],
            'explanation': 'Принцип двойной записи заключается в том, что каждая операция отражается по дебету одного и кредиту другого счета в одинаковой сумме.'
        },
        {
            'question': 'Что такое актив в бухгалтерском балансе?',
            'options': [
                {'text': 'Обязательства компании', 'is_correct': False},
                {'text': 'Ресурсы, контролируемые компанией, от которых ожидается экономическая выгода', 'is_correct': True},
                {'text': 'Долги компании', 'is_correct': False},
                {'text': 'Капитал владельцев', 'is_correct': False},
            ],
            'explanation': 'Активы — это ресурсы, которыми владеет или контролирует компания, и от которых ожидается получение экономических выгод в будущем.'
        },
    ],
    'естокада': [
        {
            'question': 'Какие меры безопасности должны соблюдаться при работе на эстакаде?',
            'options': [
                {'text': 'Использование страховочных систем только при высоте более 10 метров', 'is_correct': False},
                {'text': 'Проверка оборудования раз в год', 'is_correct': False},
                {'text': 'Регулярный осмотр конструкций и использование средств индивидуальной защиты', 'is_correct': True},
                {'text': 'Работа без защитного снаряжения для ускорения процесса', 'is_correct': False},
            ],
            'explanation': 'Безопасность на эстакаде требует регулярной проверки конструкций на целостность, использования средств индивидуальной защиты, соблюдения правил работы на высоте.'
        },
        {
            'question': 'Что необходимо проверить перед началом работ на наливной эстакаде?',
            'options': [
                {'text': 'Только наличие продукта в резервуарах', 'is_correct': False},
                {'text': 'Исправность заземления, наличие средств пожаротушения, герметичность соединений', 'is_correct': True},
                {'text': 'Только погодные условия', 'is_correct': False},
                {'text': 'Наличие других работников в зоне', 'is_correct': False},
            ],
            'explanation': 'Перед началом работ на наливной эстакаде необходимо проверить исправность заземления, наличие средств пожаротушения, герметичность соединений и отсутствие утечек, работоспособность запорной арматуры.'
        },
    ],
    'финансист': [
        {
            'question': 'Что такое NPV (Net Present Value)?',
            'options': [
                {'text': 'Сумма всех затрат проекта', 'is_correct': False},
                {'text': 'Чистая приведенная стоимость - разница между приведенной стоимостью денежных поступлений и затрат', 'is_correct': True},
                {'text': 'Национальный показатель валюты', 'is_correct': False},
                {'text': 'Негативное процентное значение', 'is_correct': False},
            ],
            'explanation': 'NPV — это сумма дисконтированных значений потока платежей, приведённых к сегодняшнему дню. Положительный NPV указывает на то, что проект принесет прибыль.'
        },
        {
            'question': 'Что такое ликвидность актива?',
            'options': [
                {'text': 'Способность актива быстро конвертироваться в деньги без существенной потери стоимости', 'is_correct': True},
                {'text': 'Способность актива генерировать прибыль', 'is_correct': False},
                {'text': 'Юридический статус актива', 'is_correct': False},
                {'text': 'Физическое состояние актива', 'is_correct': False},
            ],
            'explanation': 'Ликвидность — это способность актива быть быстро проданным по рыночной цене. Чем выше ликвидность, тем быстрее можно продать актив без существенной потери в его стоимости.'
        },
    ],
}

class Command(BaseCommand):
    help = 'Обновляет базу вопросов для тестов из внешнего API'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--role',
            help='Обновить тесты только для указанной роли'
        )
        parser.add_argument(
            '--mock',
            action='store_true',
            help='Использовать локальные тестовые данные вместо API'
        )
        
    def handle(self, *args, **options):
        role = options.get('role')
        use_mock = options.get('mock', False)
        
        if role and role not in [r[0] for r in User.ROLE_CHOICES]:
            self.stdout.write(self.style.ERROR(f"Неверная роль: {role}"))
            self.stdout.write(self.style.WARNING(f"Доступные роли: {', '.join([r[0] for r in User.ROLE_CHOICES])}"))
            return
        
        roles_to_update = [role] if role else [r[0] for r in User.ROLE_CHOICES]
        
        for role in roles_to_update:
            try:
                self.stdout.write(f"Обновление тестов для роли '{role}'...")
                
                if use_mock:
                    questions_data = FALLBACK_QUESTIONS.get(role, [])
                    if not questions_data:
                        self.stdout.write(self.style.WARNING(f"Нет локальных тестовых данных для роли '{role}'"))
                        continue
                    
                    self.create_or_update_tests(role, questions_data)
                    self.stdout.write(self.style.SUCCESS(f"Тесты для роли '{role}' успешно обновлены (использованы локальные данные)"))
                else:
                    # В реальном сценарии здесь должен быть запрос к API
                    # Для демонстрации используем заглушку
                    try:
                        # Это имитация запроса к API
                        # В реальном коде здесь был бы фактический запрос к внешнему API
                        # response = requests.get(API_ENDPOINTS[role])
                        # if response.status_code == 200:
                        #     questions_data = response.json()
                        # else:
                        #     raise Exception(f"API вернул ошибку: {response.status_code}")
                        
                        # Для тестирования используем локальные данные
                        questions_data = FALLBACK_QUESTIONS.get(role, [])
                        if not questions_data:
                            self.stdout.write(self.style.WARNING(f"Нет данных для роли '{role}'"))
                            continue
                        
                        self.create_or_update_tests(role, questions_data)
                        self.stdout.write(self.style.SUCCESS(f"Тесты для роли '{role}' успешно обновлены"))
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении тестов для роли '{role}': {str(e)}")
                        self.stdout.write(self.style.ERROR(f"Ошибка: {str(e)}"))
                        
                        # Используем резервные вопросы в случае ошибки
                        fallback_questions = FALLBACK_QUESTIONS.get(role, [])
                        if fallback_questions:
                            self.stdout.write(self.style.WARNING(f"Используем резервные вопросы для роли '{role}'"))
                            self.create_or_update_tests(role, fallback_questions)
                            self.stdout.write(self.style.SUCCESS(f"Тесты для роли '{role}' успешно обновлены (использованы резервные данные)"))
                        else:
                            self.stdout.write(self.style.ERROR(f"Нет резервных данных для роли '{role}'"))
            except Exception as e:
                logger.error(f"Необработанная ошибка при обновлении тестов для роли '{role}': {str(e)}")
                self.stdout.write(self.style.ERROR(f"Необработанная ошибка: {str(e)}"))
    
    @transaction.atomic
    def create_or_update_tests(self, role, questions_data):
        """
        Создает или обновляет тесты для указанной роли на основе полученных данных
        """
        # Проверяем существует ли уже тест для этой роли
        test, created = Test.objects.get_or_create(
            role=role,
            defaults={
                'title': f"Тест для {dict(User.ROLE_CHOICES)[role]}",
                'description': f"Проверка знаний для сотрудников с ролью {dict(User.ROLE_CHOICES)[role]}",
                'time_limit': 30,  # 30 минут на тест
                'passing_score': 70,  # 70% для прохождения
                'is_active': True
            }
        )
        
        if not created:
            # Обновляем существующий тест
            test.title = f"Тест для {dict(User.ROLE_CHOICES)[role]}"
            test.description = f"Проверка знаний для сотрудников с ролью {dict(User.ROLE_CHOICES)[role]}"
            test.updated_at = timezone.now()
            test.save()
            
            # Удаляем существующие вопросы, чтобы не было дубликатов
            # В более сложном сценарии здесь может быть логика для сохранения существующих вопросов
            # и добавления только новых
            Question.objects.filter(test=test).delete()
        
        # Создаем новые вопросы
        for q_data in questions_data:
            question = Question.objects.create(
                test=test,
                text=q_data['question'],
                explanation=q_data.get('explanation', '')
            )
            
            # Создаем варианты ответов
            for opt_data in q_data['options']:
                Option.objects.create(
                    question=question,
                    text=opt_data['text'],
                    is_correct=opt_data['is_correct']
                )
        
        # Добавляем логирование
        logger.info(f"Тест для роли '{role}' был {'создан' if created else 'обновлен'} с {len(questions_data)} вопросами") 