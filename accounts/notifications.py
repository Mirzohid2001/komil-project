"""Bildirishnoma yaratish va muddat eslatmalari."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from accounts.models import Notification
from blog.models import Test, TestResult

User = get_user_model()


def notify_user(user, title, message, notification_type='system', link=''):
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link or '',
    )


def send_deadline_reminders(days_ahead=(0, 3, 7)):
    """
    Yaqinlashayotgan / muddati o‘tgan majburiy testlar bo‘yicha
    kuniga bir marta (bir xil title) bildirishnoma yuboradi.
    Returns: created count
    """
    today = timezone.localdate()
    created = 0
    users = User.objects.filter(is_active=True).exclude(role='admin')

    for user in users.iterator():
        tests = Test.objects.filter(
            is_active=True,
            role=user.role,
        ).exclude(deadline=None)

        for test in tests:
            passed = TestResult.objects.filter(
                user=user, test=test, is_passed=True
            ).exists()
            if passed:
                continue

            days_left = (test.deadline - today).days
            link = reverse('blog:test_start', args=[test.id])

            if days_left < 0 and test.is_mandatory:
                title = f"Muddati o‘tgan: {test.title}"
                ntype = 'overdue'
                message = (
                    f"Majburiy test muddati o‘tgan ({test.deadline:%d.%m.%Y}). "
                    f"Iltimos, tezda topshiring."
                )
            elif days_left in days_ahead:
                title = f"Muddat: {test.title}"
                ntype = 'deadline'
                when = 'bugun' if days_left == 0 else f"{days_left} kun ichida"
                message = (
                    f"Test muddati {when} tugaydi ({test.deadline:%d.%m.%Y})."
                )
            else:
                continue

            exists_today = Notification.objects.filter(
                user=user,
                title=title,
                created_at__date=today,
            ).exists()
            if exists_today:
                continue

            notify_user(user, title, message, ntype, link)
            created += 1

    return created
