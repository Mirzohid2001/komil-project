"""Kategoriya sertifikatini berish / muddatini uzaytirish."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.utils import timezone


def renew_or_issue_category_certificate(user, category, validity_days=365):
    """
    Muddati o‘tgan yoki yo‘q sertifikatni yangilaydi.
    Returns: (certificate, created: bool)
    """
    from accounts.models import Certificate
    from accounts.views import generate_certificate_file

    today = timezone.localdate()
    new_until = today + timedelta(days=max(1, int(validity_days or 365)))

    existing = list(
        Certificate.objects.filter(user=user, category=category).order_by('-issued_at')
    )
    if existing:
        # Barcha nusxalarni yangilash — eski muddati o‘tgan yozuv compliance ni yopmasin
        Certificate.objects.filter(user=user, category=category).update(valid_until=new_until)
        for c in existing:
            c.valid_until = new_until
        return existing[0], False

    certificate_id = f"CERT-{category.id}-{user.id}-{uuid.uuid4().hex[:8].upper()}"
    cert = Certificate.objects.create(
        user=user,
        category=category,
        certificate_id=certificate_id,
        valid_until=new_until,
    )
    try:
        generate_certificate_file(cert)
    except Exception:
        pass
    return cert, True


def retest_url_for_category(user, category):
    """Muddati o‘tgan sertifikat uchun qayta test URL (yoki kategoriya sahifasi)."""
    from django.urls import reverse
    from blog.models import Test

    qs = Test.objects.filter(
        is_active=True,
        certificate_category=category,
    )
    if getattr(user, 'role', None) and user.role != 'admin':
        qs = qs.filter(role=user.role)
    test = qs.order_by('-updated_at').first()
    if test:
        return reverse('blog:test_start', args=[test.id])
    return reverse('blog:post_list', args=[category.id])
