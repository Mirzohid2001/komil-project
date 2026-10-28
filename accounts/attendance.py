"""Kunlik tizimga kirish (attendance) — yashil/qizil kalendar."""
from __future__ import annotations

import calendar
import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.safestring import mark_safe


def local_date(value=None) -> date:
    """datetime / date → mahalliy sana."""
    if value is None:
        return timezone.localdate()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone()).date()
    return timezone.localdate()


def record_login_day(user, when=None):
    """Login bo‘lganda kun yozuvini yaratadi / yangilaydi (race-safe)."""
    from accounts.models import LoginDay

    when = when or timezone.now()
    day = local_date(when)

    with transaction.atomic():
        try:
            obj, created = LoginDay.objects.get_or_create(
                user=user,
                date=day,
                defaults={'first_login_at': when, 'login_count': 1},
            )
        except IntegrityError:
            obj = LoginDay.objects.select_for_update().get(user=user, date=day)
            created = False
        if not created:
            LoginDay.objects.filter(pk=obj.pk).update(login_count=F('login_count') + 1)
            obj.refresh_from_db()
    return obj


def login_dates_for_user(user, start: date, end: date) -> set[date]:
    from accounts.models import LoginDay

    return set(
        LoginDay.objects.filter(user=user, date__gte=start, date__lte=end)
        .values_list('date', flat=True)
    )


def build_month_calendar(user, year: int | None = None, month: int | None = None) -> dict[str, Any]:
    """Bir oy uchun kalendar katakchalari.

    status: present | absent | future | before | empty
    """
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month
    # ekstremal yilni cheklash
    year = max(2000, min(year, today.year + 1))
    month = max(1, min(month, 12))

    join_day = local_date(user.date_joined) if user.date_joined else today
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    present = login_dates_for_user(user, first, last)

    cal = calendar.Calendar(firstweekday=0)  # Du=0
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        row = []
        for day in week:
            if day.month != month:
                row.append({'date': day, 'day': day.day, 'status': 'empty', 'in_month': False})
                continue
            if day > today:
                status = 'future'
            elif day < join_day:
                status = 'before'
            elif day in present:
                status = 'present'
            else:
                status = 'absent'
            row.append({
                'date': day,
                'day': day.day,
                'status': status,
                'in_month': True,
                'is_today': day == today,
            })
        weeks.append(row)

    present_count = sum(
        1 for d in present if first <= d <= min(last, today) and d >= join_day
    )
    tracked_end = min(last, today)
    tracked_days = 0
    d = max(first, join_day)
    while d <= tracked_end:
        tracked_days += 1
        d += timedelta(days=1)
    absent_count = max(0, tracked_days - present_count)

    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    return {
        'year': year,
        'month': month,
        'weeks': weeks,
        'present_count': present_count,
        'absent_count': absent_count,
        'tracked_days': tracked_days,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'can_go_next': (year, month) < (today.year, today.month),
        'weekday_labels': ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'],
        'month_title': date(year, month, 1),
    }


def render_attendance_html(user, year: int | None = None, month: int | None = None) -> str:
    """Admin uchun oddiy HTML kalendar."""
    data = build_month_calendar(user, year, month)
    title = data['month_title'].strftime('%B %Y')
    heads = ''.join(
        f'<th style="padding:4px;font-size:11px;">{h}</th>' for h in data['weekday_labels']
    )
    rows = []
    colors = {
        'present': '#16a34a',
        'absent': '#dc2626',
        'future': '#e5e7eb',
        'before': '#f3f4f6',
        'empty': 'transparent',
    }
    texts = {
        'present': '#fff',
        'absent': '#fff',
        'future': '#9ca3af',
        'before': '#d1d5db',
        'empty': 'transparent',
    }
    for week in data['weeks']:
        cells = []
        for cell in week:
            st = cell['status']
            if st == 'empty':
                cells.append('<td style="padding:2px;"></td>')
                continue
            border = '2px solid #111' if cell.get('is_today') else '1px solid #ddd'
            cells.append(
                f'<td title="{cell["date"].isoformat()} · {st}" '
                f'style="padding:2px;text-align:center;">'
                f'<span style="display:inline-block;width:28px;height:28px;line-height:28px;'
                f'border-radius:6px;background:{colors[st]};color:{texts[st]};'
                f'font-size:12px;font-weight:600;border:{border};">'
                f'{cell["day"]}</span></td>'
            )
        rows.append('<tr>' + ''.join(cells) + '</tr>')

    legend = (
        '<div style="margin-top:8px;font-size:12px;">'
        '<span style="color:#16a34a;font-weight:700;">●</span> Kirgan &nbsp; '
        '<span style="color:#dc2626;font-weight:700;">●</span> Kirmagan &nbsp; '
        f'({data["present_count"]} / {data["tracked_days"]} kun)'
        '</div>'
    )
    table = (
        f'<div style="max-width:320px;">'
        f'<div style="font-weight:700;margin-bottom:6px;">{title}</div>'
        f'<table style="border-collapse:collapse;width:100%;"><thead><tr>{heads}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>{legend}</div>'
    )
    return mark_safe(table)


def month_summary_for_users(year: int | None = None, month: int | None = None):
    """Admin hisobot: har bir user uchun present/absent."""
    from django.contrib.auth import get_user_model
    from accounts.models import LoginDay

    User = get_user_model()
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month
    year = max(2000, min(year, today.year + 1))
    month = max(1, min(month, 12))
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    end = min(last, today)

    days_by_user: dict[int, set[date]] = defaultdict(set)
    for uid, d in (
        LoginDay.objects.filter(date__gte=first, date__lte=end)
        .values_list('user_id', 'date')
    ):
        days_by_user[uid].add(d)

    today_present = set(
        LoginDay.objects.filter(date=today).values_list('user_id', flat=True)
    )
    rows = []
    for user in User.objects.filter(is_active=True).order_by('username'):
        join_day = local_date(user.date_joined)
        start = max(first, join_day)
        tracked = 0
        d = start
        while d <= end:
            tracked += 1
            d += timedelta(days=1)
        present = sum(1 for day in days_by_user.get(user.pk, ()) if start <= day <= end)
        rows.append({
            'user': user,
            'present': present,
            'absent': max(0, tracked - present),
            'tracked': tracked,
            'today': user.pk in today_present,
        })
    return {
        'year': year,
        'month': month,
        'month_title': first,
        'rows': rows,
    }
