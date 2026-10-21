from django.test import TestCase, Client, override_settings
from django.urls import reverse, NoReverseMatch, resolve
from django.contrib.auth import get_user_model
from django.utils import translation
from django.utils.translation import gettext

from accounts.audit import log_compliance_event
from accounts.forms import SignUpForm
from accounts.models import Certificate, ComplianceAuditLog, UserActivity
from blog.models import Category

User = get_user_model()


class I18nLocaleTests(TestCase):
    def test_home_msgid_translates_ru_and_uz(self):
        with translation.override('ru'):
            self.assertEqual(gettext('Home'), 'Главная')
        with translation.override('uz'):
            self.assertEqual(gettext('Home'), 'Bosh sahifa')

    def test_setlang_sets_language_cookie(self):
        response = self.client.post(
            '/i18n/setlang/',
            {'language': 'ru', 'next': '/'},
        )
        self.assertIn(response.status_code, (302, 303))
        cookie = response.cookies.get('django_language')
        if cookie is not None:
            self.assertEqual(cookie.value, 'ru')
        else:
            follow = self.client.get(response.url)
            self.assertEqual(follow.status_code, 200)
            self.assertEqual(
                self.client.cookies.get('django_language').value,
                'ru',
            )


class AdminPanelSmokeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='paneladmin',
            email='panel@example.com',
            password='pass12345',
            role='admin',
        )
        self.client.login(username='paneladmin', password='pass12345')

    def test_admin_dashboard_has_quick_links(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Xodim yaratish')
        self.assertContains(response, 'HR hisobot')
        self.assertContains(response, 'LMS Analitika')
        self.assertContains(response, 'zlms-quick')

    def test_lms_analytics_page(self):
        from django.utils import timezone
        from blog.models import Test, TestResult

        test = Test.objects.create(
            title='Analitika test',
            description='d',
            role='Оператор',
            is_active=True,
        )
        worker = User.objects.create_user(
            username='chartworker', password='pass12345', role='Оператор'
        )
        now = timezone.now()
        TestResult.objects.create(
            user=worker,
            test=test,
            score=5,
            percentage=50,
            is_passed=False,
            started_at=now,
            completed_at=now,
        )
        response = self.client.get(reverse('admin:lms_analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LMS Analitika')
        self.assertContains(response, 'Yiqilgan')
        self.assertContains(response, 'chartworker')

    def test_test_changelist_has_uzbek_action(self):
        response = self.client.get('/admin/blog/test/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Savollarni tekshirish')
        self.assertContains(response, 'AI test yaratish')


class SignUpSecurityTests(TestCase):
    def test_public_signup_is_closed(self):
        response = self.client.get(reverse('accounts:signup'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:login'))

    def test_cannot_create_user_via_signup_post(self):
        response = self.client.post(reverse('accounts:signup'), {
            'username': 'hacker',
            'first_name': 'Hack',
            'last_name': 'Er',
            'email': 'hack@example.com',
            'role': 'офисный-персонал',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username='hacker').exists())

    def test_signup_form_still_excludes_admin_role(self):
        form = SignUpForm()
        role_values = [value for value, _label in form.fields['role'].choices]
        self.assertNotIn('admin', role_values)


class TelegramRegistrationTests(TestCase):
    def setUp(self):
        from accounts.models import TelegramBotSettings

        self.admin = User.objects.create_superuser(
            username='tgadmin', email='tg@example.com', password='pass12345', role='admin',
        )
        TelegramBotSettings.objects.update_or_create(
            pk=1,
            defaults={
                'is_enabled': True,
                'bot_token': 'test-token',
                'bot_username': 'IsomerOilBot',
                'webhook_secret': 'secret123',
                'admin_chat_ids': '999001',
            },
        )

    def test_login_shows_telegram_cta(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 't.me/IsomerOilBot')

    def test_login_hides_cta_when_disabled(self):
        from accounts.models import TelegramBotSettings

        TelegramBotSettings.objects.filter(pk=1).update(is_enabled=False)
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 't.me/IsomerOilBot')

    def test_webhook_disabled_returns_503(self):
        from accounts.models import TelegramBotSettings

        TelegramBotSettings.objects.filter(pk=1).update(is_enabled=False)
        response = self.client.post(
            reverse('accounts:telegram_webhook'),
            data='{}',
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='secret123',
        )
        self.assertEqual(response.status_code, 503)

    def test_admin_settings_page_loads(self):
        self.client.login(username='tgadmin', password='pass12345')
        response = self.client.get(reverse('admin:accounts_telegrambotsettings_changelist'))
        self.assertEqual(response.status_code, 302)
        follow = self.client.get(response.url)
        self.assertEqual(follow.status_code, 200)
        self.assertContains(follow, 'Webhook o‘rnatish')

    def test_admin_webhook_action_requires_post(self):
        self.client.login(username='tgadmin', password='pass12345')
        response = self.client.get(reverse('admin:telegram_set_webhook'))
        self.assertEqual(response.status_code, 302)

    def test_ensure_webhook_secret_on_enable(self):
        from accounts.models import TelegramBotSettings

        cfg = TelegramBotSettings.load()
        cfg.webhook_secret = ''
        cfg.is_enabled = True
        cfg.bot_token = 'tok'
        cfg.save()
        cfg.refresh_from_db()
        self.assertTrue(len(cfg.webhook_secret) >= 16)

    def test_webhook_rejects_bad_secret(self):
        response = self.client.post(
            reverse('accounts:telegram_webhook'),
            data='{}',
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='wrong',
        )
        self.assertEqual(response.status_code, 403)

    def test_webhook_start_creates_dialog(self):
        from unittest.mock import patch
        from accounts.models import TelegramDialog

        update = {
            'message': {
                'chat': {'id': 555001},
                'from': {'id': 555001, 'username': 'ali_worker'},
                'text': '/start',
            }
        }
        with patch('accounts.telegram_bot.send_message', return_value={'ok': True}):
            response = self.client.post(
                reverse('accounts:telegram_webhook'),
                data=__import__('json').dumps(update),
                content_type='application/json',
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='secret123',
            )
        self.assertEqual(response.status_code, 200)
        dialog = TelegramDialog.objects.get(chat_id=555001)
        self.assertEqual(dialog.step, 'full_name')

    def test_approve_creates_user_and_sends_credentials(self):
        from unittest.mock import patch
        from accounts.models import RegistrationRequest
        from accounts.telegram_bot import approve_registration

        req = RegistrationRequest.objects.create(
            telegram_id=777001,
            telegram_username='worker1',
            full_name='Karimov Ali',
            employee_id='T-100',
            role='Оператор',
            phone_number='+998901112233',
            status='pending',
        )
        with patch('accounts.telegram_bot.send_message', return_value={'ok': True}) as mock_send:
            user = approve_registration(req, actor=self.admin, notify=True)
        self.assertEqual(user.first_name, 'Ali')
        self.assertEqual(user.last_name, 'Karimov')
        self.assertEqual(user.telegram_id, 777001)
        self.assertEqual(user.role, 'Оператор')
        self.assertEqual(user.employee_id, 'T-100')
        self.assertEqual(user.username, 't100')
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(req.created_user_id, user.pk)
        self.assertTrue(mock_send.called)
        first_call_text = mock_send.call_args_list[0][0][1]
        self.assertIn(user.username, first_call_text)
        self.assertIn('Parol:', first_call_text)

    def test_cyrillic_name_uses_telegram_id_username(self):
        from unittest.mock import patch
        from accounts.models import RegistrationRequest
        from accounts.telegram_bot import approve_registration

        req = RegistrationRequest.objects.create(
            telegram_id=888001,
            full_name='Каримов Али',
            role='Оператор',
            phone_number='+998901112233',
            status='pending',
        )
        with patch('accounts.telegram_bot.send_message', return_value={'ok': True}):
            user = approve_registration(req, actor=self.admin, notify=False)
        self.assertEqual(user.username, 'tg888001')
        self.assertEqual(user.last_name, 'Каримов')
        self.assertEqual(user.first_name, 'Али')

    def test_stranger_cannot_approve_via_callback(self):
        from unittest.mock import patch
        from accounts.models import RegistrationRequest
        from accounts.telegram_bot import process_update

        req = RegistrationRequest.objects.create(
            telegram_id=777002,
            full_name='Test User',
            role='Оператор',
            phone_number='+998901112233',
            status='pending',
        )
        update = {
            'callback_query': {
                'id': 'cb1',
                'data': f'approve:{req.pk}',
                'from': {'id': 111222, 'username': 'hacker'},
                'message': {'chat': {'id': 111222}},
            }
        }
        with patch('accounts.telegram_bot.send_message', return_value={'ok': True}):
            with patch('accounts.telegram_bot.answer_callback', return_value={'ok': True}) as mock_ans:
                process_update(update)
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')
        self.assertTrue(any('Faqat admin' in str(c) for c in mock_ans.call_args_list))

    def test_admin_can_approve_via_callback(self):
        from unittest.mock import patch
        from accounts.models import RegistrationRequest
        from accounts.telegram_bot import process_update

        req = RegistrationRequest.objects.create(
            telegram_id=777003,
            full_name='Worker Two',
            employee_id='W2',
            role='Оператор',
            phone_number='+998901112233',
            status='pending',
        )
        update = {
            'callback_query': {
                'id': 'cb2',
                'data': f'approve:{req.pk}',
                'from': {'id': 999001, 'username': 'realadmin'},
                'message': {'chat': {'id': 999001}},
            }
        }
        with patch('accounts.telegram_bot.send_message', return_value={'ok': True}):
            with patch('accounts.telegram_bot.answer_callback', return_value={'ok': True}):
                process_update(update)
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertTrue(User.objects.filter(telegram_id=777003).exists())

    def test_full_wizard_creates_pending_request(self):
        from unittest.mock import patch
        from accounts.models import RegistrationRequest, TelegramDialog
        from accounts.telegram_bot import process_update, SIGNUP_ROLES

        chat_id = 555100
        role_index = next(i for i, (v, _) in enumerate(SIGNUP_ROLES) if v == 'Оператор')

        def msg(text):
            return {
                'message': {
                    'chat': {'id': chat_id},
                    'from': {'id': chat_id, 'username': 'op_new'},
                    'text': text,
                }
            }

        with patch('accounts.telegram_bot.send_message', return_value={'ok': True}):
            with patch('accounts.telegram_bot.answer_callback', return_value={'ok': True}):
                process_update(msg('/start'))
                process_update(msg('Karimov Ali'))
                process_update(msg('EMP99'))
                process_update({
                    'callback_query': {
                        'id': 'r1',
                        'data': f'role:{role_index}',
                        'from': {'id': chat_id, 'username': 'op_new'},
                        'message': {'chat': {'id': chat_id}},
                    }
                })
                process_update(msg('+998901112233'))

        req = RegistrationRequest.objects.get(telegram_id=chat_id, status='pending')
        self.assertEqual(req.full_name, 'Karimov Ali')
        self.assertEqual(req.employee_id, 'EMP99')
        self.assertEqual(req.role, 'Оператор')
        self.assertEqual(req.phone_number, '+998901112233')
        self.assertEqual(TelegramDialog.objects.get(chat_id=chat_id).step, 'idle')


class CertificateVerifyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='certuser',
            password='pass12345',
            role='офисный-персонал',
        )
        self.category = Category.objects.create(name='Safety', description='Safety training')
        self.certificate = Certificate.objects.create(
            user=self.user,
            category=self.category,
            certificate_id='CERT-TEST-001',
        )

    def test_verify_certificate_url_resolves(self):
        match = resolve('/verify-certificate/CERT-TEST-001/')
        self.assertEqual(match.url_name, 'verify_certificate_detail')

    def test_accounts_verify_certificate_named_url_exists(self):
        url = reverse('accounts:verify_certificate')
        self.assertTrue(url.endswith('/verify-certificate/') or 'verify' in url)

    def test_verify_certificate_page_shows_valid_cert(self):
        response = self.client.get(
            reverse('verify_certificate_detail', kwargs={'certificate_id': 'CERT-TEST-001'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CERT-TEST-001')
        self.assertContains(response, self.user.get_full_name() or self.user.username)

    def test_verify_certificate_not_found(self):
        response = self.client.get(
            reverse('verify_certificate_detail', kwargs={'certificate_id': 'MISSING'})
        )
        self.assertEqual(response.status_code, 404)


class TemplateUrlTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tpluser',
            password='pass12345',
            role='офисный-персонал',
        )
        self.client.login(username='tpluser', password='pass12345')

    def test_achievements_page_renders_without_url_error(self):
        response = self.client.get(reverse('accounts:user_achievements'))
        self.assertEqual(response.status_code, 200)

    def test_learning_progress_page_renders(self):
        response = self.client.get(reverse('accounts:learning_progress'))
        self.assertEqual(response.status_code, 200)

    def test_certificates_page_renders(self):
        response = self.client.get(reverse('accounts:user_certificates'))
        self.assertEqual(response.status_code, 200)


class UserActivityModelTests(TestCase):
    def test_course_activity_types_are_valid(self):
        user = User.objects.create_user(username='act', password='pass12345')
        for activity_type in ('view_course', 'course_enrollment', 'view_video'):
            activity = UserActivity.objects.create(
                user=user,
                activity_type=activity_type,
                details={'ok': True},
            )
            self.assertEqual(activity.activity_type, activity_type)


class ComplianceAuditLogTests(TestCase):
    def test_log_compliance_event_creates_row(self):
        actor = User.objects.create_user(username='auditor', password='pass12345')
        subject = User.objects.create_user(username='subject', password='pass12345')
        entry = log_compliance_event(
            event_type='course_assigned',
            actor=actor,
            subject_user=subject,
            object_type='course',
            object_id=42,
            message='assigned',
            payload={'course_id': 42},
            ip_address='127.0.0.1',
        )
        self.assertIsNotNone(entry)
        self.assertEqual(ComplianceAuditLog.objects.count(), 1)
        self.assertEqual(entry.event_type, 'course_assigned')
        self.assertEqual(entry.object_id, '42')
        self.assertEqual(entry.payload['course_id'], 42)


class FavoritesListTests(TestCase):
    def setUp(self):
        from blog.models import Category, Post
        from accounts.models import FavoritePost

        self.user = User.objects.create_user(
            username='favuser', password='pass12345', role='офисный-персонал'
        )
        category = Category.objects.create(name='Cat', description='d')
        post = Post.objects.create(
            title='Fav post',
            content='c',
            category=category,
            role='офисный-персонал',
        )
        FavoritePost.objects.create(user=self.user, post=post)
        self.client.login(username='favuser', password='pass12345')

    def test_favorites_page_renders(self):
        response = self.client.get(reverse('accounts:favorites'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['favorites']), 1)
