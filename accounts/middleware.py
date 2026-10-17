"""To‘liq compliance gate — test, hujjat, sertifikat, kurs topshirig‘i."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


# Remediation + auth paths (boshqa LMS yopiq)
ALLOWED_PREFIXES = (
    '/accounts/login',
    '/accounts/logout',
    '/accounts/password',
    '/accounts/notifications',
    '/accounts/profile',
    '/static/',
    '/media/',
    '/admin/',
    '/verify-certificate',
    '/compliance',
    '/tests/',
    '/documents/',
    '/courses/',  # majburiy kurs topshiriqlari uchun
)


class ComplianceGateMiddleware:
    """
    Compliance muammolari bo‘lsa — umumiy LMS yopiladi.
    Faqat role=admin o‘tadi. Remediation yo‘llari ochiq.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        path = request.path or '/'

        if (
            user
            and user.is_authenticated
            and getattr(user, 'role', None) != 'admin'
            and not self._is_allowed(path)
        ):
            from blog.compliance import get_compliance_status

            status = get_compliance_status(user)
            if status['blocked']:
                hub = reverse('blog:compliance_hub')
                if path.rstrip('/') != hub.rstrip('/'):
                    n = len(status['items'])
                    messages.warning(
                        request,
                        f"Compliance: {n} ta majburiy talab bajarilmagan. Avval ularni yoping.",
                    )
                    return redirect('blog:compliance_hub')

        return self.get_response(request)

    def _is_allowed(self, path):
        return any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)
