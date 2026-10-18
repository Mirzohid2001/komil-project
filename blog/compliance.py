"""To‘liq compliance: testlar, hujjatlar, sertifikatlar, kurs topshiriqlari."""

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _


def _is_admin(user):
    return bool(user and getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) == 'admin')


def overdue_mandatory_tests_for_user(user):
    """Muddati o‘tgan va hali o‘tilmagan majburiy testlar."""
    from blog.models import Test, TestResult

    if not user or not getattr(user, 'is_authenticated', False) or _is_admin(user):
        return []

    today = timezone.localdate()
    qs = Test.objects.filter(
        is_active=True,
        is_mandatory=True,
        role=user.role,
    ).exclude(deadline=None).filter(deadline__lt=today)

    overdue = []
    for test in qs.order_by('deadline'):
        passed = TestResult.objects.filter(
            user=user, test=test, is_passed=True
        ).exists()
        if not passed:
            overdue.append(test)
    return overdue


def missing_document_acks_for_user(user):
    from blog.models import Document, DocumentAcknowledgment

    if not user or not getattr(user, 'is_authenticated', False) or _is_admin(user):
        return []

    docs = []
    for doc in Document.objects.filter(requires_acknowledgment=True):
        if not doc.can_user_access(user):
            continue
        if not DocumentAcknowledgment.objects.filter(document=doc, user=user).exists():
            docs.append(doc)
    return docs


def expired_certificates_for_user(user):
    """Muddati o‘tgan kategoriya va kurs sertifikatlari."""
    from accounts.models import Certificate
    from courses.models import CourseCertificate

    if not user or not getattr(user, 'is_authenticated', False) or _is_admin(user):
        return []

    today = timezone.localdate()
    items = []
    from blog.certificate_service import retest_url_for_category

    # Har kategoriya uchun faqat eng so‘nggi sertifikat tekshiriladi
    seen_categories = set()
    for cert in (
        Certificate.objects.filter(user=user)
        .exclude(valid_until=None)
        .select_related('category')
        .order_by('category_id', '-issued_at', '-id')
    ):
        if cert.category_id in seen_categories:
            continue
        seen_categories.add(cert.category_id)
        if cert.valid_until >= today:
            continue
        items.append({
            'kind': 'category',
            'title': cert.category.name,
            'valid_until': cert.valid_until,
            'url': retest_url_for_category(user, cert.category),
            'obj': cert,
        })
    for cert in CourseCertificate.objects.filter(
        enrollment__user=user
    ).exclude(valid_until=None).filter(valid_until__lt=today).select_related(
        'enrollment__course'
    ):
        items.append({
            'kind': 'course',
            'title': cert.enrollment.course.title,
            'valid_until': cert.valid_until,
            'url': reverse('courses:detail', args=[cert.enrollment.course.slug]),
            'obj': cert,
        })
    return items


def overdue_course_assignments_for_user(user):
    from courses.models import CourseAssignment

    if not user or not getattr(user, 'is_authenticated', False) or _is_admin(user):
        return []

    today = timezone.localdate()
    qs = (
        CourseAssignment.objects.filter(user=user, is_mandatory=True)
        .exclude(deadline=None)
        .filter(deadline__lt=today)
        .select_related('course')
    )
    overdue = []
    for assignment in qs:
        # Enrollment yakunlangan bo‘lsa — assignment.completed_at ni sinxronlash
        assignment.sync_completion()
        if assignment.completed_at is None:
            overdue.append(assignment)
    return overdue


def get_compliance_status(user):
    """
    Returns dict:
      blocked: bool
      tests, documents, certificates, courses: lists
      items: unified list for UI [{type, title, detail, url}]
    """
    empty = {
        'blocked': False,
        'tests': [],
        'documents': [],
        'certificates': [],
        'courses': [],
        'items': [],
    }
    if not user or not getattr(user, 'is_authenticated', False) or _is_admin(user):
        return empty

    tests = overdue_mandatory_tests_for_user(user)
    documents = missing_document_acks_for_user(user)
    certificates = expired_certificates_for_user(user)
    courses = overdue_course_assignments_for_user(user)

    items = []
    for t in tests:
        items.append({
            'type': 'test',
            'title': t.title,
            'detail': _('Deadline: %(date)s') % {'date': f'{t.deadline:%d.%m.%Y}'},
            'url': reverse('blog:test_start', args=[t.id]),
        })
    for d in documents:
        items.append({
            'type': 'document',
            'title': d.title,
            'detail': _('Document acknowledgment required'),
            'url': reverse('blog:document_detail', args=[d.id]),
        })
    for c in certificates:
        items.append({
            'type': 'certificate',
            'title': c['title'],
            'detail': _('Certificate expired: %(date)s. Retake the test.') % {
                'date': f"{c['valid_until']:%d.%m.%Y}",
            },
            'url': c['url'],
        })
    for a in courses:
        items.append({
            'type': 'course',
            'title': a.course.title,
            'detail': _('Course deadline: %(date)s') % {
                'date': f'{a.deadline:%d.%m.%Y}',
            },
            'url': reverse('courses:learn', args=[a.course.slug]),
        })

    return {
        'blocked': bool(items),
        'tests': tests,
        'documents': documents,
        'certificates': certificates,
        'courses': courses,
        'items': items,
    }


def user_has_compliance_block(user):
    return get_compliance_status(user)['blocked']
