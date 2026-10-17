import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import UserActivity
from courses.models import (
    CourseCategory, Course, Module, Lesson, Enrollment,
    CourseCertificate, LessonComment, CompletedLesson,
    LessonQuizQuestion, LessonQuizOption, LessonQuizAttempt,
)

User = get_user_model()


class TrackVideoViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='learner',
            password='pass12345',
            role='офисный-персонал',
        )
        self.category = CourseCategory.objects.create(
            name='General',
            slug='general',
        )
        self.course = Course.objects.create(
            title='Course A',
            slug='course-a',
            description='Full desc',
            short_description='Short',
            category=self.category,
            duration=60,
            status='published',
            is_free=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Module 1',
            order=1,
        )
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Lesson 1',
            content='Body',
            order=1,
            duration=10,
        )
        self.client.login(username='learner', password='pass12345')

    def test_track_video_view_creates_activity(self):
        url = reverse('courses:track_video_view')
        response = self.client.post(
            url,
            data=json.dumps({'lesson_id': self.lesson.id, 'duration': 120}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        activity = UserActivity.objects.filter(user=self.user).latest('timestamp')
        self.assertEqual(activity.activity_type, 'view_video')
        self.assertEqual(activity.duration, 120)
        self.assertEqual(activity.details.get('lesson_id'), self.lesson.id)

    def test_track_video_view_requires_auth(self):
        self.client.logout()
        url = reverse('courses:track_video_view')
        response = self.client.post(
            url,
            data=json.dumps({'lesson_id': self.lesson.id, 'duration': 10}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, (401, 302, 403))

    def test_track_video_view_requires_csrf_when_not_exempt(self):
        """CSRF must not be disabled on this endpoint."""
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username='learner', password='pass12345')
        response = csrf_client.post(
            reverse('courses:track_video_view'),
            data=json.dumps({'lesson_id': self.lesson.id, 'duration': 10}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


class CourseCertificatePdfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='graduate',
            password='pass12345',
            role='офисный-персонал',
            first_name='Ali',
            last_name='Valiyev',
        )
        self.category = CourseCategory.objects.create(name='Gen', slug='gen')
        self.course = Course.objects.create(
            title='Safety Course',
            slug='safety-course',
            description='desc',
            short_description='short',
            category=self.category,
            duration=30,
            status='published',
            is_free=True,
        )
        self.enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            is_completed=True,
        )
        self.certificate = CourseCertificate.objects.create(
            enrollment=self.enrollment,
            certificate_id='COURSE-CERT-001',
            title='Safety Course sertifikati',
        )
        self.client.login(username='graduate', password='pass12345')

    def test_download_generates_pdf(self):
        response = self.client.get(
            reverse('courses:download_certificate', args=['COURSE-CERT-001'])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.certificate.refresh_from_db()
        self.assertTrue(bool(self.certificate.pdf_file))

    def test_view_certificate_page(self):
        response = self.client.get(
            reverse('courses:view_certificate', args=['COURSE-CERT-001'])
        )
        self.assertEqual(response.status_code, 200)


class CourseDetailPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='detailuser', password='pass12345', role='офисный-персонал'
        )
        self.category = CourseCategory.objects.create(name='Cat', slug='cat')
        self.course = Course.objects.create(
            title='Detail Course',
            slug='detail-course',
            description='desc',
            short_description='short',
            category=self.category,
            duration=20,
            status='published',
            is_free=True,
        )
        self.module = Module.objects.create(course=self.course, title='M1', order=1)
        Lesson.objects.create(
            module=self.module, title='L1', content='c', order=1, duration=5
        )

    def test_anonymous_detail_renders(self):
        response = self.client.get(reverse('courses:detail', args=['detail-course']))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_enrolled'])

    def test_enrolled_detail_renders_without_url_errors(self):
        Enrollment.objects.create(user=self.user, course=self.course)
        self.client.login(username='detailuser', password='pass12345')
        response = self.client.get(reverse('courses:detail', args=['detail-course']))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_enrolled'])
        self.assertContains(response, 'Davom ettirish')

    def test_unenroll(self):
        Enrollment.objects.create(user=self.user, course=self.course)
        self.client.login(username='detailuser', password='pass12345')
        response = self.client.post(reverse('courses:unenroll', args=['detail-course']))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Enrollment.objects.filter(user=self.user, course=self.course).exists()
        )

    def test_unenroll_get_is_rejected(self):
        Enrollment.objects.create(user=self.user, course=self.course)
        self.client.login(username='detailuser', password='pass12345')
        response = self.client.get(reverse('courses:unenroll', args=['detail-course']))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(
            Enrollment.objects.filter(user=self.user, course=self.course).exists()
        )

    def test_enroll_get_is_rejected(self):
        self.client.login(username='detailuser', password='pass12345')
        response = self.client.get(reverse('courses:enroll', args=['detail-course']))
        self.assertEqual(response.status_code, 405)
        self.assertFalse(
            Enrollment.objects.filter(user=self.user, course=self.course).exists()
        )

    def test_completed_lesson_checkmark_in_context(self):
        enrollment = Enrollment.objects.create(user=self.user, course=self.course)
        lesson = self.module.lessons.first()
        CompletedLesson.objects.create(
            user=self.user, lesson=lesson, enrollment=enrollment
        )
        self.client.login(username='detailuser', password='pass12345')
        response = self.client.get(reverse('courses:detail', args=['detail-course']))
        self.assertEqual(response.status_code, 200)
        self.assertIn(lesson.id, response.context['completed_lesson_ids'])


class ModuleNavigationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='modnav', password='pass12345', role='офисный-персонал'
        )
        category = CourseCategory.objects.create(name='Nav', slug='nav')
        self.course = Course.objects.create(
            title='Nav Course',
            slug='nav-course',
            description='d',
            short_description='s',
            category=category,
            duration=30,
            status='published',
            is_free=True,
        )
        self.m1 = Module.objects.create(course=self.course, title='M1', order=1)
        self.m2 = Module.objects.create(course=self.course, title='M2', order=2)
        self.m3 = Module.objects.create(course=self.course, title='M3', order=3)
        Enrollment.objects.create(user=self.user, course=self.course)
        self.client.login(username='modnav', password='pass12345')

    def test_middle_module_has_adjacent_neighbors(self):
        response = self.client.get(
            reverse('courses:module_detail', args=[self.course.slug, self.m2.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['prev_module'], self.m1)
        self.assertEqual(response.context['next_module'], self.m3)


class InternalEnrollmentTests(TestCase):
    """Factory LMS has no payments — any published course is enrollable."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='workerpay', password='pass12345', role='офисный-персонал'
        )
        category = CourseCategory.objects.create(name='Internal', slug='internal')
        self.course = Course.objects.create(
            title='Factory Safety',
            slug='factory-safety',
            description='d',
            short_description='s',
            category=category,
            duration=20,
            status='published',
            is_free=False,
            price=999999,
        )
        self.client.login(username='workerpay', password='pass12345')

    def test_can_enroll_even_if_marked_not_free(self):
        response = self.client.post(reverse('courses:enroll', args=['factory-safety']))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Enrollment.objects.filter(user=self.user, course=self.course).exists()
        )

    def test_detail_shows_enroll_not_purchase(self):
        response = self.client.get(reverse('courses:detail', args=['factory-safety']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kursga yozilish')
        self.assertNotContains(response, 'so\'m')
        self.assertNotContains(response, 'Sotib')


class QuizLessonSafeRenderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='quizuser', password='pass12345', role='офисный-персонал'
        )
        category = CourseCategory.objects.create(name='Q', slug='q')
        self.course = Course.objects.create(
            title='Quiz Course',
            slug='quiz-course',
            description='d',
            short_description='s',
            category=category,
            duration=10,
            status='published',
            is_free=True,
        )
        self.module = Module.objects.create(course=self.course, title='M', order=1)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Quiz lesson',
            content='body',
            order=1,
            duration=5,
            lesson_type='quiz',
        )
        Enrollment.objects.create(user=self.user, course=self.course)
        self.client.login(username='quizuser', password='pass12345')

    def test_empty_quiz_lesson_renders(self):
        response = self.client.get(
            reverse(
                'courses:lesson_detail',
                args=[self.course.slug, self.module.id, self.lesson.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'savollar hali qo‘shilmagan')

    def test_submit_quiz_pass_marks_complete(self):
        q = LessonQuizQuestion.objects.create(lesson=self.lesson, text='2+2?', order=1)
        correct = LessonQuizOption.objects.create(question=q, text='4', is_correct=True)
        LessonQuizOption.objects.create(question=q, text='5', is_correct=False)
        url = reverse(
            'courses:submit_quiz',
            args=[self.course.slug, self.module.id, self.lesson.id],
        )
        response = self.client.post(url, {f'question_{q.id}': str(correct.id)})
        self.assertEqual(response.status_code, 302)
        attempt = LessonQuizAttempt.objects.get(user=self.user, lesson=self.lesson)
        self.assertTrue(attempt.is_passed)
        self.assertTrue(
            CompletedLesson.objects.filter(
                user=self.user, lesson=self.lesson
            ).exists()
        )


class EnrollmentProgressCertificateTests(TestCase):
    def test_progress_100_creates_certificate_without_circular_import(self):
        user = User.objects.create_user(
            username='grad2', password='pass12345', role='офисный-персонал'
        )
        category = CourseCategory.objects.create(name='G2', slug='g2')
        course = Course.objects.create(
            title='Done Course',
            slug='done-course',
            description='d',
            short_description='s',
            category=category,
            duration=10,
            status='published',
            is_free=True,
        )
        module = Module.objects.create(course=course, title='M', order=1)
        lesson = Lesson.objects.create(
            module=module, title='L', content='c', order=1, duration=5
        )
        enrollment = Enrollment.objects.create(user=user, course=course)
        from courses.models import CompletedLesson
        CompletedLesson.objects.create(user=user, lesson=lesson, enrollment=enrollment)
        percent = enrollment.progress()
        self.assertEqual(percent, 100)
        self.assertTrue(
            CourseCertificate.objects.filter(enrollment=enrollment).exists()
        )


class LessonCommentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='commenter', password='pass12345', role='офисный-персонал'
        )
        self.category = CourseCategory.objects.create(name='C', slug='c')
        self.course = Course.objects.create(
            title='Comment Course',
            slug='comment-course',
            description='d',
            short_description='s',
            category=self.category,
            duration=10,
            status='published',
            is_free=True,
        )
        self.module = Module.objects.create(course=self.course, title='M', order=1)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Lesson',
            content='body',
            order=1,
            duration=5,
            allow_comments=True,
        )
        Enrollment.objects.create(user=self.user, course=self.course)
        self.client.login(username='commenter', password='pass12345')

    def test_add_comment(self):
        url = reverse(
            'courses:add_comment',
            args=[self.course.slug, self.module.id, self.lesson.id],
        )
        response = self.client.post(url, {'content': 'Yaxshi dars!'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LessonComment.objects.count(), 1)
        self.assertEqual(LessonComment.objects.first().content, 'Yaxshi dars!')

    def test_edit_and_delete_own_comment(self):
        comment = LessonComment.objects.create(
            lesson=self.lesson, user=self.user, content='Eski'
        )
        edit_url = reverse('courses:edit_comment', args=[comment.id])
        response = self.client.post(edit_url, {'content': 'Yangi'})
        self.assertEqual(response.status_code, 302)
        comment.refresh_from_db()
        self.assertEqual(comment.content, 'Yangi')

        delete_url = reverse('courses:delete_comment', args=[comment.id])
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LessonComment.objects.filter(id=comment.id).exists())


class CourseRoleAccessTests(TestCase):
    def setUp(self):
        from .models import CourseCategory
        cat = CourseCategory.objects.create(name='RoleCat', slug='role-cat')
        self.open_course = Course.objects.create(
            title='Open Course',
            slug='open-course',
            description='d',
            short_description='s',
            category=cat,
            duration=10,
            status='published',
            allowed_roles=[],
        )
        self.restricted = Course.objects.create(
            title='Operator Only',
            slug='op-only',
            description='d',
            short_description='s',
            category=cat,
            duration=10,
            status='published',
            allowed_roles=['Оператор'],
        )
        self.op = User.objects.create_user(
            username='oprole', password='pass12345', role='Оператор'
        )
        self.mech = User.objects.create_user(
            username='mechrole', password='pass12345', role='механик'
        )

    def test_anonymous_cannot_open_restricted(self):
        response = self.client.get(reverse('courses:detail', args=['op-only']))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_anonymous_can_open_public(self):
        response = self.client.get(reverse('courses:detail', args=['open-course']))
        self.assertEqual(response.status_code, 200)

    def test_wrong_role_blocked(self):
        self.client.login(username='mechrole', password='pass12345')
        response = self.client.get(reverse('courses:detail', args=['op-only']))
        self.assertEqual(response.status_code, 302)

    def test_correct_role_allowed(self):
        self.client.login(username='oprole', password='pass12345')
        response = self.client.get(reverse('courses:detail', args=['op-only']))
        self.assertEqual(response.status_code, 200)


class CourseAssignmentAndHomeworkTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import CourseCategory, CourseAssignment

        self.admin = User.objects.create_user(
            username='assignadmin', password='pass12345', role='admin', is_staff=True
        )
        self.worker = User.objects.create_user(
            username='assignworker', password='pass12345', role='Оператор'
        )
        cat = CourseCategory.objects.create(name='AssignCat', slug='assign-cat')
        self.course = Course.objects.create(
            title='Safety Assign',
            slug='safety-assign',
            description='d',
            short_description='s',
            category=cat,
            duration=30,
            status='published',
        )
        self.module = Module.objects.create(course=self.course, title='M1', order=1)
        self.lesson = Lesson.objects.create(
            module=self.module,
            title='Upload homework',
            content='Do it',
            lesson_type='assignment',
            order=1,
            duration=10,
        )
        self.assignment = CourseAssignment.objects.create(
            user=self.worker,
            course=self.course,
            assigned_by=self.admin,
            deadline=timezone.localdate() - timedelta(days=1),
            is_mandatory=True,
        )

    def test_assignment_auto_enrolls(self):
        self.assertTrue(
            Enrollment.objects.filter(user=self.worker, course=self.course).exists()
        )

    def test_overdue_assignment_blocks_home(self):
        self.client.login(username='assignworker', password='pass12345')
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/compliance', response.url)

    def test_submit_and_approve_assignment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import LessonAssignmentSubmission, CompletedLesson

        self.client.login(username='assignworker', password='pass12345')
        f = SimpleUploadedFile('hw.txt', b'hello homework', content_type='text/plain')
        response = self.client.post(
            reverse(
                'courses:submit_assignment',
                args=[self.course.slug, self.module.id, self.lesson.id],
            ),
            {'file': f, 'comment': 'done'},
        )
        self.assertEqual(response.status_code, 302)
        sub = LessonAssignmentSubmission.objects.get(user=self.worker, lesson=self.lesson)
        self.assertEqual(sub.status, 'pending')

        self.client.login(username='assignadmin', password='pass12345')
        response = self.client.post(
            reverse('courses:review_assignment', args=[sub.id]),
            {'action': 'approve', 'reviewer_note': 'ok'},
        )
        self.assertEqual(response.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'approved')
        self.assertTrue(
            CompletedLesson.objects.filter(user=self.worker, lesson=self.lesson).exists()
        )

    def test_completing_course_clears_assignment_block(self):
        from django.utils import timezone

        enrollment = Enrollment.objects.get(user=self.worker, course=self.course)
        enrollment.is_completed = True
        enrollment.completed_at = timezone.now()
        enrollment.save()
        enrollment.sync_course_assignments()

        self.assignment.refresh_from_db()
        self.assertIsNotNone(self.assignment.completed_at)

        self.client.login(username='assignworker', password='pass12345')
        response = self.client.get(reverse('blog:home'))
        self.assertEqual(response.status_code, 200)

    def test_staff_sees_pending_submissions_on_lesson(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import LessonAssignmentSubmission

        LessonAssignmentSubmission.objects.create(
            lesson=self.lesson,
            user=self.worker,
            file=SimpleUploadedFile('hw2.txt', b'x', content_type='text/plain'),
            status='pending',
        )
        self.client.login(username='assignadmin', password='pass12345')
        response = self.client.get(
            reverse(
                'courses:lesson_detail',
                args=[self.course.slug, self.module.id, self.lesson.id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Instruktur tekshiruvi')
        self.assertContains(response, 'assignworker')

    def test_cannot_mark_assignment_complete_without_approval(self):
        self.client.login(username='assignworker', password='pass12345')
        response = self.client.post(
            reverse(
                'courses:mark_complete',
                args=[self.course.slug, self.module.id, self.lesson.id],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            CompletedLesson.objects.filter(user=self.worker, lesson=self.lesson).exists()
        )
