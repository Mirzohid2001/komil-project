"""Navbar / global template context."""


def zavod_extras(request):
    user = getattr(request, 'user', None)
    unread = 0
    compliance = {
        'blocked': False,
        'tests': [],
        'documents': [],
        'certificates': [],
        'courses': [],
        'items': [],
    }
    if user and user.is_authenticated:
        try:
            unread = user.notifications.filter(is_read=False).count()
        except Exception:
            unread = 0
        try:
            from blog.compliance import get_compliance_status
            compliance = get_compliance_status(user)
        except Exception:
            pass

    telegram_bot_url = ''
    try:
        from accounts.telegram_bot import bot_deep_link, bot_configured, bot_username
        # Token + yoqilgan + username (login tugmasi uchun username shart)
        if bot_configured() and bot_username():
            telegram_bot_url = bot_deep_link()
    except Exception:
        telegram_bot_url = ''

    return {
        'unread_notifications': unread,
        'compliance_status': compliance,
        # backwards-compatible alias
        'compliance_overdue_tests': compliance.get('tests') or [],
        'telegram_bot_url': telegram_bot_url,
    }
