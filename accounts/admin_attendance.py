"""Admin — oylik kirish hisoboti."""
from django.shortcuts import render
from django.utils import timezone

from accounts.attendance import month_summary_for_users


def login_attendance_view(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get('y') or today.year)
        month = int(request.GET.get('m') or today.month)
        if not (1 <= month <= 12):
            month = today.month
    except (TypeError, ValueError):
        year, month = today.year, today.month

    data = month_summary_for_users(year, month)

    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month, prev_year = 12, year - 1
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month, next_year = 1, year + 1

    return render(request, 'admin/login_attendance.html', {
        'title': 'Kunlik kirish',
        'data': data,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'can_go_next': (year, month) < (today.year, today.month),
    })
