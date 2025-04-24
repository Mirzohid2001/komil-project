import os
import json
import httplib2
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from blog.models import Test, Question, Option

class Command(BaseCommand):
    help = 'Import tests from Google Forms'

    def add_arguments(self, parser):
        parser.add_argument('--form_id', type=str, help='Google Form ID')
        parser.add_argument('--credentials', type=str, help='Path to credentials.json file')
        parser.add_argument('--test_title', type=str, help='Custom title for the test')
        parser.add_argument('--test_description', type=str, help='Custom description for the test')
        parser.add_argument('--test_role', type=str, default='оператор', help='Role for the test')
        parser.add_argument('--passing_score', type=float, default=70, help='Passing score percentage')
        parser.add_argument('--time_limit', type=int, default=30, help='Time limit in minutes')

    def handle(self, *args, **options):
        form_id = options['form_id']
        credentials_path = options['credentials']
        test_role = options['test_role']
        
        if not form_id:
            self.stdout.write(self.style.ERROR('Please provide a Google Form ID'))
            return
            
        if not credentials_path:
            self.stdout.write(self.style.ERROR('Please provide a path to credentials.json file'))
            return
            
        try:
            # Setup credentials
            scope = ['https://www.googleapis.com/auth/forms.body.readonly']
            credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
            http = credentials.authorize(httplib2.Http())
            service = build('forms', 'v1', http=http)
            
            # Get form data
            form = service.forms().get(formId=form_id).execute()
            
            if not form:
                self.stdout.write(self.style.ERROR('Form not found'))
                return
                
            # Get form items (questions)
            items = form.get('items', [])
            
            if not items:
                self.stdout.write(self.style.ERROR('No questions found in the form'))
                return
                
            with transaction.atomic():
                # Create test
                test = Test.objects.create(
                    title=options['test_title'] or form.get('info', {}).get('title', 'Imported Test'),
                    description=options['test_description'] or form.get('info', {}).get('description', 'Imported from Google Forms'),
                    role=test_role,
                    passing_score=options['passing_score'],
                    time_limit=options['time_limit'],
                    is_active=True,
                    created_at=timezone.now()
                )
                
                # Process items/questions
                for item in items:
                    # Skip non-question items
                    if 'questionItem' not in item:
                        continue
                        
                    question_item = item.get('questionItem', {})
                    question_text = item.get('title', '')
                    
                    if not question_text:
                        continue
                        
                    # Create question
                    question = Question.objects.create(
                        test=test,
                        text=question_text,
                        points=1  # Default points value
                    )
                    
                    # Process question options
                    if 'choiceQuestion' in question_item:
                        choices = question_item['choiceQuestion'].get('options', [])
                        correct_indexes = question_item['choiceQuestion'].get('correctAnswers', [])
                        
                        for i, choice in enumerate(choices):
                            option_text = choice.get('value', '')
                            is_correct = i in correct_indexes
                            
                            if option_text:
                                Option.objects.create(
                                    question=question,
                                    text=option_text,
                                    is_correct=is_correct
                                )
                
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully imported test: "{test.title}" with {len(items)} questions')
                )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error importing test: {str(e)}')) 