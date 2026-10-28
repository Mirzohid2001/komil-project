"""Auth signallari — kirish kunini yozish."""
import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def track_login_day(sender, request, user, **kwargs):
    """Har qanday login (sayt + admin) — kunlik attendance."""
    try:
        from accounts.attendance import record_login_day
        record_login_day(user)
    except Exception:
        logger.exception('LoginDay yozilmadi: user_id=%s', getattr(user, 'pk', None))
