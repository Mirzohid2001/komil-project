import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from blog.models import Test, Question, Option
from datetime import datetime

class Command(BaseCommand):
    help = 'Import tests from Google Sheets'

    def add_arguments(self, parser):
        parser.add_argument('--sheet_id', type=str, help='Google Sheet ID')
        parser.add_argument('--credentials', type=str, help='Path to credentials.json file')
        parser.add_argument('--test_role', type=str, default='оператор', help='Role for the test')

    def handle(self, *args, **options):
        sheet_id = options['sheet_id']
        credentials_path = options['credentials']
        test_role = options['test_role']
        
        if not sheet_id:
            self.stdout.write(self.style.ERROR('Please provide a Google Sheet ID'))
            return
            
        if not credentials_path:
            self.stdout.write(self.style.ERROR('Please provide a path to credentials.json file'))
            return
            
        try:
            # Setup credentials
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
            client = gspread.authorize(credentials)
            
            # Open the spreadsheet
            sheet = client.open_by_key(sheet_id)
            
            # Get the first worksheet with test info
            test_info_worksheet = sheet.get_worksheet(0)
            test_data = test_info_worksheet.get_all_records()
            
            if not test_data:
                self.stdout.write(self.style.ERROR('No test data found in the first worksheet'))
                return
                
            test_info = test_data[0]
            
            # Get the second worksheet with questions
            questions_worksheet = sheet.get_worksheet(1)
            questions_data = questions_worksheet.get_all_records()
            
            if not questions_data:
                self.stdout.write(self.style.ERROR('No questions found in the second worksheet'))
                return
                
            with transaction.atomic():
                # Create test
                test = Test.objects.create(
                    title=test_info.get('title', 'Imported Test'),
                    description=test_info.get('description', 'Imported from Google Sheets'),
                    role=test_role,
                    passing_score=float(test_info.get('passing_score', 70)),
                    time_limit=int(test_info.get('time_limit', 30)),
                    is_active=True,
                    created_at=timezone.now()
                )
                
                # Create questions and options
                for q_data in questions_data:
                    question_text = q_data.get('question')
                    if not question_text:
                        continue
                        
                    question = Question.objects.create(
                        test=test,
                        text=question_text,
                        points=int(q_data.get('points', 1))
                    )
                    
                    # Add options
                    for i in range(1, 5):  # Assuming maximum 4 options
                        option_text = q_data.get(f'option_{i}')
                        if not option_text:
                            continue
                            
                        is_correct = q_data.get(f'correct_{i}') in ('True', 'true', '1', 'yes', 'Yes', True)
                        
                        Option.objects.create(
                            question=question,
                            text=option_text,
                            is_correct=is_correct
                        )
                
            self.stdout.write(
                self.style.SUCCESS(f'Successfully imported test: "{test.title}" with {len(questions_data)} questions')
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error importing test: {str(e)}')) 