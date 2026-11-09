"""Admin panel real-time alertlar (Telegram registratsiya)."""
from __future__ import annotations

from django.urls import reverse

from accounts.models import RealtimeAdminAlert, RegistrationRequest


def push_admin_alert(*, kind: str, title: str, body: str = '', link: str = '') -> RealtimeAdminAlert:
    return RealtimeAdminAlert.objects.create(
        kind=kind,
        title=title[:200],
        body=(body or '')[:500],
        link=(link or '')[:255],
    )


def push_registration_started(*, telegram_id: int, username: str = '') -> RealtimeAdminAlert:
    who = f'@{username}' if username else f'ID {telegram_id}'
    try:
        link = reverse('admin:accounts_registrationrequest_changelist')
    except Exception:
        link = '/admin/accounts/registrationrequest/'
    return push_admin_alert(
        kind=RealtimeAdminAlert.KIND_REG_STARTED,
        title='Botga yangi zapusk',
        body=f'{who} registratsiyani boshladi. So‘rov kelgach tasdiqlang.',
        link=link,
    )


def push_registration_pending(req: RegistrationRequest) -> RealtimeAdminAlert:
    try:
        link = reverse('admin:accounts_registrationrequest_change', args=[req.pk])
    except Exception:
        link = f'/admin/accounts/registrationrequest/{req.pk}/change/'
    role = ''
    try:
        role = req.get_role_display()
    except Exception:
        role = req.role
    return push_admin_alert(
        kind=RealtimeAdminAlert.KIND_REG_PENDING,
        title='Tasdiqlash kerak',
        body=f'{req.full_name} · {role} · so‘rov #{req.pk}',
        link=link,
    )


def alerts_since(since_id: int = 0, *, limit: int = 20) -> list[RealtimeAdminAlert]:
    qs = RealtimeAdminAlert.objects.all()
    if since_id > 0:
        qs = qs.filter(id__gt=since_id)
    return list(qs.order_by('id')[:limit])
