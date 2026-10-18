"""Compliance audit jurnal — tekshiruv uchun append-only yozuvlar."""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model

User = get_user_model()


def log_compliance_event(
    *,
    event_type: str,
    actor=None,
    subject_user=None,
    object_type: str = '',
    object_id: str | int | None = None,
    message: str = '',
    payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
    request=None,
):
    """Audit yozuv yaratadi. Xato bo‘lsa asosiy oqimni buzmaydi."""
    from accounts.models import ComplianceAuditLog

    try:
        if request is not None and ip_address is None:
            ip_address = request.META.get('REMOTE_ADDR')
        if request is not None and actor is None and getattr(request, 'user', None):
            if request.user.is_authenticated:
                actor = request.user

        return ComplianceAuditLog.objects.create(
            actor=actor if getattr(actor, 'is_authenticated', True) else None,
            subject_user=subject_user,
            event_type=event_type,
            object_type=object_type or '',
            object_id=str(object_id) if object_id is not None else '',
            message=message or '',
            payload=payload or {},
            ip_address=ip_address,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Compliance audit yozilmadi')
        return None
