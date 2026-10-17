"""Admin LMS analitika — testlar, yiqilishlar, video/dars, oylik/yillik."""

from __future__ import annotations

import json
from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncMonth, TruncYear
from django.shortcuts import render
from django.utils import timezone

from blog.models import Post, Test, TestResult, VideoView
from courses.models import CompletedLesson, Enrollment

User = get_user_model()

ROLE_MAP = dict(User.ROLE_CHOICES)


def _role_label(role):
    return ROLE_MAP.get(role, role or "Noma'lum")


def _month_labels(qs, date_field, value_annots):
    rows = (
        qs.annotate(period=TruncMonth(date_field))
        .values('period')
        .annotate(**value_annots)
        .order_by('period')
    )
    labels, series = [], {k: [] for k in value_annots}
    for row in rows:
        if not row['period']:
            continue
        labels.append(row['period'].strftime('%m.%Y'))
        for k in value_annots:
            val = row[k]
            series[k].append(round(val, 1) if isinstance(val, float) else (val or 0))
    return labels, series


def _year_labels(qs, date_field, value_annots):
    rows = (
        qs.annotate(period=TruncYear(date_field))
        .values('period')
        .annotate(**value_annots)
        .order_by('period')
    )
    labels, series = [], {k: [] for k in value_annots}
    for row in rows:
        if not row['period']:
            continue
        labels.append(row['period'].strftime('%Y'))
        for k in value_annots:
            val = row[k]
            series[k].append(round(val, 1) if isinstance(val, float) else (val or 0))
    return labels, series


def build_lms_analytics(year=None):
    """Barcha chart/table ma'lumotlarini yig‘adi."""
    now = timezone.now()
    today = timezone.localdate()

    results = TestResult.objects.select_related('user', 'test')
    videos = VideoView.objects.select_related('user', 'post')
    lessons = CompletedLesson.objects.select_related('user', 'lesson', 'lesson__module__course')

    if year:
        results = results.filter(completed_at__year=year)
        videos = videos.filter(viewed_at__year=year)
        lessons = lessons.filter(completed_at__year=year)

    total_attempts = results.count()
    passed = results.filter(is_passed=True).count()
    failed = results.filter(is_passed=False).count()
    avg_score = results.aggregate(v=Avg('percentage'))['v'] or 0
    video_views = videos.count()
    unique_viewers = videos.values('user').distinct().count()
    lesson_done = lessons.count()
    course_done = Enrollment.objects.filter(is_completed=True)
    if year:
        course_done = course_done.filter(completed_at__year=year)
    course_done_n = course_done.count()

    # --- Charts: monthly / yearly tests ---
    month_labels, month_series = _month_labels(
        results,
        'completed_at',
        {
            'total': Count('id'),
            'passed': Count('id', filter=Q(is_passed=True)),
            'failed': Count('id', filter=Q(is_passed=False)),
            'avg': Avg('percentage'),
        },
    )
    year_labels, year_series = _year_labels(
        TestResult.objects.all() if not year else results,
        'completed_at',
        {
            'total': Count('id'),
            'passed': Count('id', filter=Q(is_passed=True)),
            'failed': Count('id', filter=Q(is_passed=False)),
            'avg': Avg('percentage'),
        },
    )

    # Video monthly
    v_month_labels, v_month_series = _month_labels(
        videos, 'viewed_at', {'total': Count('id')}
    )
    # Lesson completions monthly
    l_month_labels, l_month_series = _month_labels(
        lessons, 'completed_at', {'total': Count('id')}
    )

    # Per-test stats
    if year:
        year_f = Q(results__completed_at__year=year)
        test_stats = list(
            Test.objects.annotate(
                attempts=Count('results', filter=year_f),
                passed_n=Count(
                    'results',
                    filter=Q(results__is_passed=True) & year_f,
                ),
                avg_score=Avg('results__percentage', filter=year_f),
            )
            .filter(attempts__gt=0)
            .order_by('-attempts')[:15]
        )
    else:
        test_stats = list(
            Test.objects.annotate(
                attempts=Count('results'),
                passed_n=Count('results', filter=Q(results__is_passed=True)),
                avg_score=Avg('results__percentage'),
            )
            .filter(attempts__gt=0)
            .order_by('-attempts')[:15]
        )

    test_chart = {
        'labels': [t.title[:40] for t in test_stats],
        'avg': [round(t.avg_score or 0, 1) for t in test_stats],
        'attempts': [t.attempts for t in test_stats],
        'passed': [t.passed_n for t in test_stats],
        'failed': [t.attempts - t.passed_n for t in test_stats],
    }

    # Role stats
    role_rows = list(
        results.values('user__role')
        .annotate(
            total=Count('id'),
            passed=Count('id', filter=Q(is_passed=True)),
            avg=Avg('percentage'),
        )
        .order_by('-total')
    )
    role_chart = {
        'labels': [_role_label(r['user__role']) for r in role_rows],
        'total': [r['total'] for r in role_rows],
        'passed': [r['passed'] for r in role_rows],
        'failed': [r['total'] - r['passed'] for r in role_rows],
        'avg': [round(r['avg'] or 0, 1) for r in role_rows],
    }

    # Top videos (blog posts)
    top_videos = list(
        Post.objects.filter(video__isnull=False)
        .annotate(
            view_count=Count(
                'videoview',
                filter=Q(videoview__viewed_at__year=year) if year else Q(),
            )
        )
        .filter(view_count__gt=0)
        .order_by('-view_count')[:10]
    )

    # Tables
    recent_results = list(
        results.order_by('-completed_at')[:40]
    )
    failed_results = list(
        results.filter(is_passed=False).order_by('-completed_at')[:40]
    )
    recent_videos = list(
        videos.order_by('-viewed_at')[:40]
    )
    recent_lessons = list(
        lessons.order_by('-completed_at')[:40]
    )

    # Last 12 months activity spark (combined)
    start_12 = today.replace(day=1) - timedelta(days=365)
    activity_month_labels, activity_series = _month_labels(
        TestResult.objects.filter(completed_at__date__gte=start_12),
        'completed_at',
        {
            'tests': Count('id'),
            'passed': Count('id', filter=Q(is_passed=True)),
        },
    )

    available_years = list(
        TestResult.objects.dates('completed_at', 'year', order='DESC')
    )
    available_years = [d.year for d in available_years]

    return {
        'kpis': {
            'total_attempts': total_attempts,
            'passed': passed,
            'failed': failed,
            'pass_rate': round((passed / total_attempts * 100) if total_attempts else 0, 1),
            'avg_score': round(avg_score, 1),
            'video_views': video_views,
            'unique_viewers': unique_viewers,
            'lesson_done': lesson_done,
            'course_done': course_done_n,
        },
        'charts': {
            'monthly_tests': {
                'labels': month_labels,
                'total': month_series.get('total', []),
                'passed': month_series.get('passed', []),
                'failed': month_series.get('failed', []),
                'avg': month_series.get('avg', []),
            },
            'yearly_tests': {
                'labels': year_labels,
                'total': year_series.get('total', []),
                'passed': year_series.get('passed', []),
                'failed': year_series.get('failed', []),
                'avg': year_series.get('avg', []),
            },
            'monthly_videos': {
                'labels': v_month_labels,
                'total': v_month_series.get('total', []),
            },
            'monthly_lessons': {
                'labels': l_month_labels,
                'total': l_month_series.get('total', []),
            },
            'by_test': test_chart,
            'by_role': role_chart,
            'activity_12m': {
                'labels': activity_month_labels,
                'tests': activity_series.get('tests', []),
                'passed': activity_series.get('passed', []),
            },
        },
        'tables': {
            'recent_results': recent_results,
            'failed_results': failed_results,
            'recent_videos': recent_videos,
            'recent_lessons': recent_lessons,
            'test_stats': test_stats,
            'top_videos': top_videos,
        },
        'available_years': available_years,
        'selected_year': year,
        'generated_at': now,
    }


@staff_member_required
def lms_analytics_view(request):
    if getattr(request.user, 'role', None) != 'admin' and not request.user.is_superuser:
        from django.contrib import messages
        from django.shortcuts import redirect

        messages.error(request, "Faqat admin analitika ko‘ra oladi.")
        return redirect('admin:index')

    year_raw = request.GET.get('year', '').strip()
    year = int(year_raw) if year_raw.isdigit() else None

    data = build_lms_analytics(year=year)
    context = {
        **admin.site.each_context(request),
        'title': 'LMS Analitika',
        'kpis': data['kpis'],
        'tables': data['tables'],
        'available_years': data['available_years'],
        'selected_year': data['selected_year'],
        'generated_at': data['generated_at'],
        'charts_json': json.dumps(data['charts'], ensure_ascii=False),
    }
    return render(request, 'admin/lms_analytics.html', context)
