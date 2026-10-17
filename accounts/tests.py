from django.test import TestCase, Client, override_settings
from django.urls import reverse, NoReverseMatch, resolve
from django.contrib.auth import get_user_model

from accounts.forms import SignUpForm
from accounts.models import Certificate, UserActivity
from blog.models import Category

User = get_user_model()


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
