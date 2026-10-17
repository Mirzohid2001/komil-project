import json
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from io import StringIO

from blog.models import (
    Category, Post, Test, Question, Option, Document, DocumentCategory, TestResult,
)
from blog.forms import DocumentUploadForm

User = get_user_model()


class AdminRoleAccessTests(TestCase):
    """Admin role must be Latin 'admin' everywhere — not Cyrillic 'админ'."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='adminuser',
            password='pass12345',
            role='admin',
        )
        self.worker = User.objects.create_user(
            username='worker',
            password='pass12345',
            role='Оператор',
        )
        self.category = Category.objects.create(name='Ops', description='Operations')
        self.operator_post = Post.objects.create(
            title='Operator lesson',
            content='Content',
            category=self.category,
            role='Оператор',
        )
        self.office_post = Post.objects.create(
            title='Office lesson',
            content='Content',
            category=self.category,
            role='офисный-персонал',
        )

    def test_admin_sees_home_as_admin(self):
        self.client.login(username='adminuser', password='pass12345')
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_admin'])
        # Admin without view_as_role sees all posts
        titles = [p.title for p in response.context['latest_posts']]
        self.assertIn('Operator lesson', titles)
        self.assertIn('Office lesson', titles)

    def test_worker_only_sees_own_role_posts(self):
        self.client.login(username='worker', password='pass12345')
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_admin'])
        titles = [p.title for p in response.context['latest_posts']]
        self.assertIn('Operator lesson', titles)
        self.assertNotIn('Office lesson', titles)

    def test_admin_can_open_any_role_post(self):
        self.client.login(username='adminuser', password='pass12345')
        response = self.client.get(
            reverse('blog:post_detail', args=[self.operator_post.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_worker_cannot_open_other_role_post(self):
        self.client.login(username='worker', password='pass12345')
        response = self.client.get(
            reverse('blog:post_detail', args=[self.office_post.id])
        )
        self.assertEqual(response.status_code, 302)

    def test_admin_can_open_analytics(self):
        self.client.login(username='adminuser', password='pass12345')
        response = self.client.get(reverse('blog:analytics'))
        self.assertEqual(response.status_code, 200)

    def test_worker_cannot_open_analytics(self):
        self.client.login(username='worker', password='pass12345')
        response = self.client.get(reverse('blog:analytics'))
        self.assertEqual(response.status_code, 302)


class QuestionCreateTests(TestCase):
    def test_question_create_without_points_field(self):
        """Import commands must not pass points= — Question has no such field."""
        test = Test.objects.create(
            title='Smoke test',
            description='desc',
            role='Оператор',
        )
        question = Question.objects.create(test=test, text='What is 2+2?')
        Option.objects.create(question=question, text='4', is_correct=True)
        Option.objects.create(question=question, text='5', is_correct=False)
        self.assertEqual(question.text, 'What is 2+2?')
        with self.assertRaises(TypeError):
            Question.objects.create(test=test, text='Bad', points=1)


class PostDefaultRoleTests(TestCase):
    def test_new_post_default_role_is_not_admin(self):
        category = Category.objects.create(name='Cat', description='d')
        post = Post(title='T', content='C', category=category)
        # Default from model field
        self.assertNotEqual(post.role, 'admin')


class DocumentAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='docadmin', password='pass12345', role='admin'
        )
        self.operator = User.objects.create_user(
            username='docop', password='pass12345', role='Оператор'
        )
        self.office = User.objects.create_user(
            username='docoffice', password='pass12345', role='офисный-персонал'
        )
        self.category = DocumentCategory.objects.create(
            name='Safety Docs', description='d'
        )
        self.doc = Document.objects.create(
            title='Restricted',
            description='secret',
            file=SimpleUploadedFile('safety.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
            category=self.category,
            allowed_roles=['Оператор'],
            is_public=False,
            uploaded_by=self.admin,
        )

    def test_operator_can_access_allowed_document(self):
        self.assertTrue(self.doc.can_user_access(self.operator))

    def test_office_cannot_access_restricted_document(self):
        self.assertFalse(self.doc.can_user_access(self.office))

    def test_admin_can_access_any_document(self):
        self.assertTrue(self.doc.can_user_access(self.admin))

    def test_public_document_accessible_to_all(self):
        self.doc.is_public = True
        self.doc.allowed_roles = []
        self.doc.save()
        self.assertTrue(self.doc.can_user_access(self.office))


class DocumentUploadValidationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='uploader', password='pass12345', role='admin'
        )
        self.category = DocumentCategory.objects.create(name='Docs', description='d')

    def test_rejects_disallowed_extension(self):
        form = DocumentUploadForm(data={
            'title': 'Bad file',
            'description': '',
            'category': self.category.id,
            'is_public': False,
            'allowed_roles': ['Оператор'],
        }, files={
            'file': SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream'),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('file', form.errors)

    def test_accepts_pdf(self):
        form = DocumentUploadForm(data={
            'title': 'Good PDF',
            'description': '',
            'category': self.category.id,
            'is_public': True,
            'allowed_roles': [],
        }, files={
            'file': SimpleUploadedFile('manual.pdf', b'%PDF-1.4', content_type='application/pdf'),
        })
        self.assertTrue(form.is_valid(), form.errors)


class DailyTestGenerationTests(TestCase):
    def test_generates_test_for_current_role_choice(self):
        out = StringIO()
        call_command(
            'generate_daily_tests',
            '--force',
            '--test_roles', 'Оператор',
            stdout=out,
        )
        test = Test.objects.filter(role='Оператор').first()
        self.assertIsNotNone(test)
        self.assertEqual(test.questions.count(), 30)
        self.assertTrue(test.questions.first().options.exists())

    def test_generates_test_for_mechanic_role(self):
        call_command('generate_daily_tests', '--force', '--test_roles', 'механик')
        test = Test.objects.filter(role='механик').first()
        self.assertIsNotNone(test)
        self.assertEqual(test.questions.count(), 30)


class TestListQueryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tester', password='pass12345', role='Оператор'
        )
        for i in range(3):
            Test.objects.create(
                title=f'Test {i}',
                description='d',
                role='Оператор',
                is_active=True,
            )
        Test.objects.create(
            title='Mechanic only',
            description='d',
            role='механик',
            is_active=True,
        )
        self.client.login(username='tester', password='pass12345')

    def test_test_list_renders(self):
        response = self.client.get(reverse('blog:test_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['tests']), 3)

    def test_admin_sees_all_role_tests(self):
        User.objects.create_user(
            username='listadmin', password='pass12345', role='admin'
        )
        self.client.login(username='listadmin', password='pass12345')
        response = self.client.get(reverse('blog:test_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['tests']), 4)


class TestAnalyticsLegacyRoleTests(TestCase):
    def test_legacy_role_does_not_crash_analytics(self):
        admin = User.objects.create_user(
            username='anadmin', password='pass12345', role='admin'
        )
        legacy = User.objects.create_user(
            username='legacy', password='pass12345', role='офисный-персонал'
        )
        # Simulate DB value outside ROLE_CHOICES (e.g. old Cyrillic admin)
        User.objects.filter(pk=legacy.pk).update(role='админ')
        test = Test.objects.create(
            title='Legacy Test', description='d', role='офисный-персонал', is_active=True
        )
        from django.utils import timezone
        TestResult.objects.create(
            user=legacy,
            test=test,
            score=5,
            percentage=50,
            is_passed=False,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        self.client.login(username='anadmin', password='pass12345')
        response = self.client.get(reverse('blog:test_analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'админ')


class DeadlineReminderTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        from datetime import timedelta

        self.user = User.objects.create_user(
            username='deaduser', password='pass12345', role='Оператор'
        )
        self.test = Test.objects.create(
            title='Muddatli test',
            description='d',
            role='Оператор',
            is_active=True,
            is_mandatory=True,
            deadline=timezone.localdate() + timedelta(days=2),
        )
        self.client.login(username='deaduser', password='pass12345')

    def test_home_shows_upcoming_deadline(self):
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Muddatli test')
        self.assertTrue(response.context['upcoming_deadlines'])


class HRReportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='hradmin', password='pass12345', role='admin', is_staff=True
        )
        self.worker = User.objects.create_user(
            username='hrworker', password='pass12345', role='Оператор'
        )
        test = Test.objects.create(
            title='HR Test', description='d', role='Оператор', is_active=True
        )
        from django.utils import timezone
        TestResult.objects.create(
            user=self.worker,
            test=test,
            score=8,
            percentage=80,
            is_passed=True,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

    def test_worker_cannot_open_hr_reports(self):
        self.client.login(username='hrworker', password='pass12345')
        response = self.client.get(reverse('blog:hr_reports'))
        self.assertEqual(response.status_code, 302)

    def test_admin_csv_export(self):
        self.client.login(username='hradmin', password='pass12345')
        response = self.client.get(reverse('blog:hr_reports') + '?export=csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn(b'HR Test', response.content)


class UpdateTestsCommandTests(TestCase):
    def test_mock_update_for_operator_role(self):
        call_command('update_tests', '--mock', '--role', 'Оператор')
        test = Test.objects.filter(role='Оператор').first()
        self.assertIsNotNone(test)
        self.assertGreaterEqual(test.questions.count(), 2)
        self.assertTrue(test.questions.first().options.exists())

    def test_rejects_unknown_role(self):
        out = StringIO()
        call_command('update_tests', '--mock', '--role', 'not-a-role', stdout=out)
        self.assertIn('Noto', out.getvalue())
        self.assertEqual(Test.objects.count(), 0)


class AutoUpdateTests(TestCase):
    def test_full_auto_update_creates_job_log(self):
        from blog.auto_update import run_full_auto_update
        from blog.models import SystemJobLog

        log = run_full_auto_update(
            trigger=SystemJobLog.TRIGGER_CLI,
            skip_daily=True,
        )
        self.assertEqual(log.status, SystemJobLog.STATUS_SUCCESS)
        self.assertTrue(Test.objects.filter(role='Оператор', is_active=True).exists())
        self.assertGreaterEqual(SystemJobLog.objects.count(), 1)

    def test_auto_update_command(self):
        out = StringIO()
        call_command('auto_update', '--skip-daily', stdout=out)
        self.assertIn('success', out.getvalue())

    def test_admin_auto_update_dashboard(self):
        admin_user = User.objects.create_user(
            username='autoupdateadmin',
            password='pass12345',
            role='admin',
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username='autoupdateadmin', password='pass12345')
        response = self.client.get(reverse('admin:auto_update_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Avto-yangilanish')



class DocumentListAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='doclistadmin', password='pass12345', role='admin'
        )
        self.office = User.objects.create_user(
            username='doclistoffice', password='pass12345', role='офисный-персонал'
        )
        category = DocumentCategory.objects.create(name='Docs2', description='d')
        self.restricted = Document.objects.create(
            title='Secret Doc',
            description='',
            file=SimpleUploadedFile('a.pdf', b'%PDF', content_type='application/pdf'),
            category=category,
            allowed_roles=['Оператор'],
            is_public=False,
            uploaded_by=self.admin,
        )

    def test_admin_sees_restricted_documents_in_list(self):
        self.client.login(username='doclistadmin', password='pass12345')
        response = self.client.get(reverse('blog:document_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.restricted, list(response.context['documents']))

    def test_office_does_not_see_restricted_documents(self):
        self.client.login(username='doclistoffice', password='pass12345')
        response = self.client.get(reverse('blog:document_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.restricted, list(response.context['documents']))


class FileSizeDisplayTests(TestCase):
    def test_get_file_size_display_does_not_mutate_field(self):
        admin = User.objects.create_user(username='sizeadmin', password='pass12345', role='admin')
        category = DocumentCategory.objects.create(name='SizeCat', description='d')
        doc = Document.objects.create(
            title='Sized',
            description='',
            file=SimpleUploadedFile('b.pdf', b'%PDF', content_type='application/pdf'),
            category=category,
            allowed_roles=[],
            is_public=True,
            uploaded_by=admin,
            file_size=2048,
        )
        display = doc.get_file_size_display()
        self.assertEqual(doc.file_size, 2048)
        self.assertIn('KB', display)


class ValidQuestionsCountTests(TestCase):
    def test_get_valid_questions_count_uses_utils_not_views(self):
        test = Test.objects.create(title='V', description='d', role='Оператор')
        q = Question.objects.create(test=test, text='Qancha vaqt kerak?')
        Option.objects.create(question=q, text='10 daqiqa', is_correct=True)
        Option.objects.create(question=q, text='1 soat', is_correct=False)
        # Should not raise ImportError / circular import
        self.assertGreaterEqual(test.get_valid_questions_count(), 0)


class AITestGenerateAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='aitestadmin',
            email='ai@example.com',
            password='pass12345',
            role='admin',
        )
        self.client.login(username='aitestadmin', password='pass12345')

    def test_ai_generate_form_page(self):
        response = self.client.get(reverse('admin:ai_generate_tests'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nechta test yaratilsin')

    def test_ai_generate_creates_requested_count(self):
        response = self.client.post(
            reverse('admin:ai_generate_tests'),
            {
                'role': 'Оператор',
                'count': 3,
                'questions_per_test': 10,
                'use_ai': False,
            },
        )
        self.assertEqual(response.status_code, 302)
        tests = Test.objects.filter(role='Оператор', title__startswith='AI test')
        self.assertEqual(tests.count(), 3)
        for t in tests:
            self.assertEqual(t.questions.count(), 10)
            self.assertEqual(t.questions.first().options.count(), 4)

    def test_ai_questions_pass_consistency_and_start_full(self):
        """AI savollari filtrga tushmasligi kerak — start to‘liq savollarni bersin."""
        from blog.test_generator import create_test_with_questions
        from blog.views import get_valid_questions

        test = create_test_with_questions(
            'Оператор', num_questions=20, title='Consistency AI'
        )
        valid = get_valid_questions(test, max_count=20)
        self.assertGreaterEqual(
            len(valid), 18,
            f'Faqat {len(valid)}/20 savol filtrdan o‘tdi',
        )
        worker = User.objects.create_user(
            username='opstart', password='pass12345', role='Оператор'
        )
        self.client.login(username='opstart', password='pass12345')
        self.client.get(reverse('blog:test_start', args=[test.id]))
        session = self.client.session['current_test']
        self.assertGreaterEqual(len(session['question_ids']), 18)

    def test_staff_non_admin_cannot_ai_generate(self):
        staff = User.objects.create_user(
            username='staffonly',
            password='pass12345',
            role='Оператор',
            is_staff=True,
        )
        self.client.login(username='staffonly', password='pass12345')
        response = self.client.get(reverse('admin:ai_generate_tests'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Test.objects.filter(title__startswith='AI test').count(), 0)


class FreeAIClientTests(TestCase):
    def test_normalize_and_parse_groq_style_response(self):
        from blog.ai_client import _extract_json_array, _normalize_questions

        raw = '''```json
        [{"text": "Qancha bosim?", "options": [
          {"text": "10 bar", "is_correct": true},
          {"text": "100 bar", "is_correct": false},
          {"text": "1 bar", "is_correct": false},
          {"text": "50 bar", "is_correct": false}
        ]}]
        ```'''
        data = _extract_json_array(raw)
        cleaned = _normalize_questions(data, 1)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(sum(1 for o in cleaned[0]['options'] if o['is_correct']), 1)

    @override_settings(AI_PROVIDER='groq', AI_API_KEY='test-key', AI_MODEL='llama-3.3-70b-versatile')
    def test_generate_via_groq_mock(self):
        from unittest.mock import patch, MagicMock
        from blog.ai_client import generate_questions_via_ai

        fake = {
            'choices': [{
                'message': {
                    'content': json.dumps([{
                        'text': 'Himoya ko‘zoynagini qachon taqish kerak?',
                        'options': [
                            {'text': 'Har doim sexda', 'is_correct': True},
                            {'text': 'Hech qachon', 'is_correct': False},
                            {'text': 'Faqat tungi smenada', 'is_correct': False},
                            {'text': 'Faqat mehmon kelganda', 'is_correct': False},
                        ],
                    }]),
                }
            }]
        }
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = fake
        with patch('blog.ai_client.requests.post', return_value=mock_resp) as post:
            qs = generate_questions_via_ai('Оператор', 1)
        self.assertEqual(len(qs), 1)
        self.assertIn('Himoya', qs[0]['text'])
        self.assertTrue(post.called)


class TestAttemptShuffleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='shuffleuser', password='pass12345', role='Оператор'
        )
        self.test = Test.objects.create(
            title='Shuffle Test',
            description='d',
            role='Оператор',
            is_active=True,
        )
        for i in range(8):
            q = Question.objects.create(
                test=self.test,
                text=f'Qancha parametr {i}?',
            )
            Option.objects.create(question=q, text=f'{i}A', is_correct=True)
            Option.objects.create(question=q, text=f'{i}B', is_correct=False)
            Option.objects.create(question=q, text=f'{i}C', is_correct=False)
            Option.objects.create(question=q, text=f'{i}D', is_correct=False)
        self.client.login(username='shuffleuser', password='pass12345')

    def test_start_stores_shuffled_option_orders(self):
        response = self.client.get(reverse('blog:test_start', args=[self.test.id]))
        self.assertEqual(response.status_code, 302)
        session = self.client.session['current_test']
        self.assertIn('option_orders', session)
        self.assertEqual(len(session['question_ids']), 8)
        # Har savol uchun 4 ta variant tartibi saqlangan
        for qid in session['question_ids']:
            order = session['option_orders'][str(qid)]
            self.assertEqual(len(order), 4)

    def test_two_attempts_can_differ_in_order(self):
        """Ikki urinishda tartib farq qilishi mumkin (yodlashni qiyinlashtirish)."""
        import random
        random.seed(1)
        self.client.get(reverse('blog:test_start', args=[self.test.id]))
        first = list(self.client.session['current_test']['question_ids'])
        first_opts = dict(self.client.session['current_test']['option_orders'])

        # Yangi sessiyani simulyatsiya qilish
        session = self.client.session
        del session['current_test']
        session.save()

        random.seed(2)
        self.client.get(reverse('blog:test_start', args=[self.test.id]))
        second = list(self.client.session['current_test']['question_ids'])
        second_opts = dict(self.client.session['current_test']['option_orders'])

        # Kamida savollar yoki variantlar tartibi farq qiladi
        differs = first != second or first_opts != second_opts
        self.assertTrue(differs)


class ComplianceGateTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        from datetime import timedelta

        self.user = User.objects.create_user(
            username='compuser', password='pass12345', role='Оператор'
        )
        self.admin = User.objects.create_user(
            username='compadmin2', password='pass12345', role='admin', is_staff=True
        )
        self.test = Test.objects.create(
            title='Majburiy overdue',
            description='d',
            role='Оператор',
            is_active=True,
            is_mandatory=True,
            deadline=timezone.localdate() - timedelta(days=1),
        )
        self.client.login(username='compuser', password='pass12345')

    def test_blocks_home_when_overdue_mandatory(self):
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/compliance', response.url)

    def test_allows_test_list(self):
        response = self.client.get(reverse('blog:test_list'))
        self.assertEqual(response.status_code, 200)

    def test_compliance_hub_lists_item(self):
        response = self.client.get(reverse('blog:compliance_hub'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Majburiy overdue')

    def test_admin_bypasses_gate(self):
        self.client.login(username='compadmin2', password='pass12345')
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 200)

    def test_unacked_document_blocks(self):
        from blog.models import DocumentCategory, Document
        from django.utils import timezone
        from datetime import timedelta

        # Overdue testni olib tashlash — faqat hujjat bloklasin
        self.test.deadline = timezone.localdate() + timedelta(days=30)
        self.test.save()

        cat = DocumentCategory.objects.create(name='CompDocCat')
        Document.objects.create(
            title='Safety Doc Gate',
            description='d',
            file='documents/a.pdf',
            category=cat,
            uploaded_by=self.user,
            is_public=True,
            requires_acknowledgment=True,
        )
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/compliance', response.url)
        hub = self.client.get(reverse('blog:compliance_hub'))
        self.assertContains(hub, 'Safety Doc Gate')

    def test_expired_certificate_blocks(self):
        from blog.models import Category
        from accounts.models import Certificate
        from django.utils import timezone
        from datetime import timedelta

        self.test.deadline = timezone.localdate() + timedelta(days=30)
        self.test.save()

        cat = Category.objects.create(name='CompCertCat', description='d')
        Certificate.objects.create(
            user=self.user,
            category=cat,
            certificate_id='GATE-CERT-001',
            valid_until=timezone.localdate() - timedelta(days=1),
        )
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/compliance', response.url)
        hub = self.client.get(reverse('blog:compliance_hub'))
        self.assertContains(hub, 'CompCertCat')

    def test_ack_document_unblocks(self):
        from blog.models import DocumentCategory, Document, DocumentAcknowledgment
        from django.utils import timezone
        from datetime import timedelta

        self.test.deadline = timezone.localdate() + timedelta(days=30)
        self.test.save()

        cat = DocumentCategory.objects.create(name='AckUnblock')
        doc = Document.objects.create(
            title='Ack Unblock Doc',
            description='d',
            file='documents/a.pdf',
            category=cat,
            uploaded_by=self.user,
            is_public=True,
            requires_acknowledgment=True,
        )
        self.assertEqual(self.client.get(reverse('blog:home')).status_code, 302)
        DocumentAcknowledgment.objects.create(document=doc, user=self.user)
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 200)


class NotificationAndCompliancePageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='compadmin', password='pass12345', role='admin', is_staff=True
        )
        self.worker = User.objects.create_user(
            username='compworker', password='pass12345', role='Оператор'
        )

    def test_notifications_page(self):
        from accounts.models import Notification
        Notification.objects.create(
            user=self.worker, title='Test', message='msg', notification_type='system'
        )
        self.client.login(username='compworker', password='pass12345')
        response = self.client.get(reverse('accounts:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test')

    def test_hr_compliance_page(self):
        self.client.login(username='compadmin', password='pass12345')
        response = self.client.get(reverse('blog:hr_compliance'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HR compliance')


class DocumentAckTests(TestCase):
    def setUp(self):
        from blog.models import DocumentCategory, Document
        self.user = User.objects.create_user(
            username='ackuser', password='pass12345', role='Оператор'
        )
        cat = DocumentCategory.objects.create(name='AckCat')
        self.doc = Document.objects.create(
            title='Safety SOP',
            description='d',
            file='documents/a.pdf',
            category=cat,
            uploaded_by=self.user,
            is_public=True,
            requires_acknowledgment=True,
        )
        self.client.login(username='ackuser', password='pass12345')

    def test_acknowledge_document(self):
        from blog.models import DocumentAcknowledgment
        response = self.client.post(
            reverse('blog:document_acknowledge', args=[self.doc.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DocumentAcknowledgment.objects.filter(
                document=self.doc, user=self.user
            ).exists()
        )
