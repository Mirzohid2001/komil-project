from django.contrib import admin, messages
from django.utils.html import format_html
from django.db.models import Count
from django.utils.safestring import mark_safe
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import redirect
from django.urls import path, reverse

from .models import (
    User, FavoritePost, UserActivity, Achievement, UserAchievement,
    LearningProgress, Certificate, LevelUpEvent, Department, Notification,
    ComplianceAuditLog, RegistrationRequest, TelegramDialog, TelegramBotSettings,
    LoginDay,
)

class FavoritePostInline(admin.TabularInline):
    model = FavoritePost
    extra = 0
    readonly_fields = ('post', 'added_at')
    can_delete = True
    verbose_name = 'Sevimli post'
    verbose_name_plural = 'Sevimli postlar'

class UserActivityInline(admin.TabularInline):
    model = UserActivity
    extra = 0
    readonly_fields = ('activity_type', 'timestamp', 'post', 'ip_address', 'details')
    can_delete = False
    max_num = 10
    verbose_name = 'Faollik'
    verbose_name_plural = 'Faolliklar'
    
    def has_add_permission(self, request, obj=None):
        return False

class CustomUserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Zavod maʼlumotlari', {
            'fields': (
                'role', 'employee_id', 'department', 'shift',
                'profile_image', 'bio', 'phone_number',
                'telegram_id', 'telegram_username',
                'experience_points', 'level',
            ),
            'description': 'Xodimlarni faqat admin yaratadi. Rol zavod bo‘limiga mos tanlanadi.',
        }),
        ('Kunlik kirish', {
            'fields': ('attendance_calendar',),
            'description': 'Yashil — kirgan, qizil — kirmagan (ro‘yxatdan o‘tgan kundan bugungacha).',
        }),
    )
    readonly_fields = BaseUserAdmin.readonly_fields + ('attendance_calendar',)
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'password1', 'password2',
                'role', 'employee_id', 'department', 'shift',
                'first_name', 'last_name', 'email',
            ),
            'description': 'Yangi xodim — ochiq ro‘yxatdan o‘tish o‘chirilgan.',
        }),
    )
    list_display = (
        'username', 'employee_id', 'get_full_name', 'email', 'role',
        'department', 'shift', 'level', 'today_login_badge', 'is_staff', 'is_active',
    )
    list_filter = BaseUserAdmin.list_filter + ('role', 'department', 'shift', 'level')
    search_fields = BaseUserAdmin.search_fields + ('bio', 'phone_number', 'employee_id')
    list_editable = ('role', 'is_active')
    ordering = ('username',)

    def attendance_calendar(self, obj):
        if not obj or not obj.pk:
            return '—'
        from accounts.attendance import render_attendance_html
        return render_attendance_html(obj)
    attendance_calendar.short_description = 'Kirish kalendari'

    def get_queryset(self, request):
        from django.db.models import Exists, OuterRef
        from django.utils import timezone

        qs = super().get_queryset(request)
        today = timezone.localdate()
        return qs.annotate(
            _logged_today=Exists(
                LoginDay.objects.filter(user_id=OuterRef('pk'), date=today)
            )
        )

    @admin.display(description='Bugun', boolean=False)
    def today_login_badge(self, obj):
        ok = bool(getattr(obj, '_logged_today', False))
        if ok:
            return format_html(
                '<span style="background:#16a34a;color:#fff;padding:2px 8px;'
                'border-radius:999px;font-size:11px;font-weight:700;">Kirgan</span>'
            )
        return format_html(
            '<span style="background:#dc2626;color:#fff;padding:2px 8px;'
            'border-radius:999px;font-size:11px;font-weight:700;">Yo‘q</span>'
        )
    
    def profile_preview(self, obj):
        if obj.profile_image:
            return format_html('<img src="{}" width="150" height="150" style="object-fit: cover; border-radius: 50%;" />', obj.profile_image.url)
        return "Нет изображения"
    profile_preview.short_description = 'Фото профиля'
    
    def view_count(self, obj):
        count = obj.videoview_set.count()
        return format_html('<span style="color: #0066cc; font-weight: bold;">{}</span>', count)
    view_count.short_description = 'Просмотров видео'
    
    def favorite_count(self, obj):
        count = obj.favorites.count()
        return format_html('<span style="color: #e11d48; font-weight: bold;">{}</span>', count)
    favorite_count.short_description = 'Избранных'
    
    def activity_summary(self, obj):
        # Общее количество активностей
        total_activity = obj.activities.count()
        
        # Активности по типам
        activities_by_type = obj.activities.values('activity_type').annotate(count=Count('id')).order_by('-count')
        
        # Самый популярный тип активности
        most_popular_type = None
        if activities_by_type:
            most_popular_type = activities_by_type[0]
        
        # Последние 5 активностей
        recent_activities = obj.activities.all()[:5]
        
        # Количество просмотров видео за последний месяц
        from datetime import datetime, timedelta
        last_month = datetime.now() - timedelta(days=30)
        video_views_last_month = obj.videoview_set.filter(viewed_at__gte=last_month).count()
        
        # Формируем HTML для вывода сводки активности
        html = f"""
        <div style="margin-bottom: 20px;">
            <div style="display: flex; gap: 30px; margin-bottom: 20px;">
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0; color: #666;">Всего активностей</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0; color: #333;">{total_activity}</p>
                </div>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; flex: 1; text-align: center;">
                    <h4 style="margin: 0; color: #666;">Просмотров видео за месяц</h4>
                    <p style="font-size: 24px; font-weight: bold; margin: 10px 0 0; color: #0066cc;">{video_views_last_month}</p>
                </div>
            </div>
            
            <h3 style="color: #333; margin-top: 30px;">Активность по типам</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 30px;">
                <tr>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Тип активности</th>
                    <th style="text-align: right; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Количество</th>
                </tr>
        """
        
        for activity in activities_by_type:
            activity_type = dict(UserActivity.ACTIVITY_TYPES).get(activity['activity_type'], activity['activity_type'])
            html += f"""
                <tr>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity_type}</td>
                    <td style="text-align: right; padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold;">{activity['count']}</td>
                </tr>
            """
            
        html += """
            </table>
            
            <h3 style="color: #333;">Последние действия</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Тип</th>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Дата</th>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">Пост</th>
                    <th style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd; color: #666;">IP адрес</th>
                </tr>
        """
        
        for activity in recent_activities:
            activity_type = activity.get_activity_type_display()
            post_title = activity.post.title if activity.post else '-'
            html += f"""
                <tr>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity_type}</td>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity.timestamp.strftime('%d.%m.%Y %H:%M')}</td>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{post_title}</td>
                    <td style="text-align: left; padding: 10px; border-bottom: 1px solid #ddd;">{activity.ip_address or '-'}</td>
                </tr>
            """
            
        html += """
            </table>
        </div>
        """
        
        return mark_safe(html)
    activity_summary.short_description = 'Сводка активности'


class FavoritePostAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('user__username', 'post__title')
    date_hierarchy = 'added_at'


class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'activity_type', 'timestamp', 'post', 'ip_address')
    list_filter = ('activity_type', 'timestamp')
    search_fields = ('user__username', 'ip_address')
    date_hierarchy = 'timestamp'


class AchievementAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'required_value', 'experience_reward', 'is_secret')
    list_filter = ('type', 'is_secret')
    search_fields = ('name', 'description')


class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ('user', 'achievement', 'earned_at', 'current_value')
    list_filter = ('earned_at', 'achievement__type')
    search_fields = ('user__username', 'achievement__name')
    date_hierarchy = 'earned_at'


class LearningProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'last_viewed', 'is_completed', 'get_completion_percentage')
    list_filter = ('is_completed', 'last_viewed')
    search_fields = ('user__username', 'category__name')
    date_hierarchy = 'last_viewed'
    filter_horizontal = ('posts_viewed',)
    
    def get_completion_percentage(self, obj):
        return f"{obj.completion_percentage():.1f}%"
    get_completion_percentage.short_description = 'Прогресс'


class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_id', 'user', 'category', 'issued_at', 'valid_until')
    list_filter = ('issued_at', 'valid_until', 'category')
    search_fields = ('certificate_id', 'user__username', 'category__name')
    date_hierarchy = 'issued_at'


class LevelUpEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'previous_level', 'new_level', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('user__username',)
    date_hierarchy = 'timestamp'


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    date_hierarchy = 'created_at'


@admin.register(TelegramBotSettings)
class TelegramBotSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {
            'fields': ('is_enabled', 'bot_token', 'bot_username'),
            'description': (
                '1) @BotFather da bot yarating → tokenni yozing. '
                '2) Admin Telegram ID ni @userinfobot dan oling. '
                '3) Saqlang → «Webhook o‘rnatish» bosing. '
                'Webhook uchun serverda DJANGO_BASE_URL=https://edu-isomer.uz bo‘lishi kerak.'
            ),
        }),
        ('Xavfsizlik va adminlar', {
            'fields': ('webhook_secret', 'admin_chat_ids'),
        }),
        ('Holat', {
            'fields': ('updated_at', 'status_preview'),
        }),
    )
    readonly_fields = ('updated_at', 'status_preview')

    def has_add_permission(self, request):
        return not TelegramBotSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = TelegramBotSettings.load()
        return redirect(
            reverse('admin:accounts_telegrambotsettings_change', args=[obj.pk])
        )

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        self._preview_request = request
        return super().changeform_view(request, object_id, form_url, extra_context)

    def status_preview(self, obj):
        from django.middleware.csrf import get_token
        from accounts.telegram_bot import bot_configured, bot_deep_link, bot_username

        ok = bot_configured()
        uname = bot_username()
        link = bot_deep_link()
        color = '#15803d' if ok and uname else '#b45309'
        if ok and uname:
            text = 'Ishlashga tayyor'
        elif ok and not uname:
            text = 'Token bor, lekin username yo‘q — «Botni tekshirish» yoki webhook bosing'
        else:
            text = 'Yoqilmagan yoki token yo‘q'
        html = f'<p style="color:{color};font-weight:600;">{text}</p>'
        if not (obj.admin_chat_ids or '').strip():
            html += (
                '<p style="color:#b45309;">Admin Telegram ID bo‘sh — '
                'Telegramdan tasdiqlash ishlamaydi (faqat shu Admin panel).</p>'
            )
        if link:
            html += f'<p>Login tugmasi: <a href="{link}" target="_blank" rel="noopener">{link}</a></p>'

        req = getattr(self, '_preview_request', None)
        csrf = get_token(req) if req is not None else ''
        csrf_input = f'<input type="hidden" name="csrfmiddlewaretoken" value="{csrf}">'

        def action_form(url_name, label):
            return (
                f'<form method="post" action="{reverse(url_name)}" '
                f'style="display:inline;margin-right:0.4rem;">'
                f'{csrf_input}'
                f'<button type="submit" class="button">{label}</button>'
                f'</form>'
            )

        html += (
            '<p style="margin-top:1rem;">'
            + action_form('admin:telegram_set_webhook', 'Webhook o‘rnatish')
            + action_form('admin:telegram_test_bot', 'Botni tekshirish (getMe)')
            + action_form('admin:telegram_delete_webhook', 'Webhook o‘chirish')
            + '</p>'
        )
        return mark_safe(html)
    status_preview.short_description = 'Holat / amallar'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'actions/set-webhook/',
                self.admin_site.admin_view(self.set_webhook_view),
                name='telegram_set_webhook',
            ),
            path(
                'actions/delete-webhook/',
                self.admin_site.admin_view(self.delete_webhook_view),
                name='telegram_delete_webhook',
            ),
            path(
                'actions/test-bot/',
                self.admin_site.admin_view(self.test_bot_view),
                name='telegram_test_bot',
            ),
        ]
        return custom + urls

    def _settings_redirect(self):
        obj = TelegramBotSettings.load()
        return redirect(
            reverse('admin:accounts_telegrambotsettings_change', args=[obj.pk])
        )

    def _require_change(self, request):
        if request.method != 'POST':
            messages.error(request, 'Faqat POST orqali.')
            return False
        if not request.user.has_perm('accounts.change_telegrambotsettings'):
            messages.error(request, 'Ruxsat yo‘q.')
            return False
        return True

    def set_webhook_view(self, request):
        from accounts.telegram_bot import bot_configured, fetch_bot_username, set_webhook

        if not self._require_change(request):
            return self._settings_redirect()
        if not bot_configured():
            messages.error(request, 'Avval «Yoqilgan» ni belgilang va bot tokenini saqlang.')
            return self._settings_redirect()
        data = set_webhook()
        if data.get('ok'):
            uname = fetch_bot_username()
            messages.success(
                request,
                f'Webhook o‘rnatildi. Bot: @{uname or "—"}',
            )
        else:
            messages.error(request, f'Webhook xato: {data}')
        return self._settings_redirect()

    def delete_webhook_view(self, request):
        from accounts.telegram_bot import delete_webhook

        if not self._require_change(request):
            return self._settings_redirect()
        data = delete_webhook()
        if data.get('ok'):
            messages.success(request, 'Webhook o‘chirildi.')
        else:
            messages.error(request, f'Xato: {data}')
        return self._settings_redirect()

    def test_bot_view(self, request):
        from accounts.telegram_bot import _api, fetch_bot_username

        if not self._require_change(request):
            return self._settings_redirect()
        data = _api('getMe')
        if data.get('ok'):
            uname = fetch_bot_username()
            messages.success(request, f'Bot ishlayapti: @{uname}')
        else:
            messages.error(request, f'getMe xato: {data}')
        return self._settings_redirect()


@admin.register(RegistrationRequest)
class RegistrationRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'full_name', 'role', 'employee_id', 'phone_number',
        'telegram_username', 'status', 'created_user', 'created_at', 'reviewed_at',
    )
    list_filter = ('status', 'role', 'created_at')
    search_fields = ('full_name', 'employee_id', 'phone_number', 'telegram_username', 'telegram_id')
    readonly_fields = (
        'telegram_id', 'telegram_username', 'full_name', 'employee_id', 'role',
        'phone_number', 'status', 'created_user', 'reviewed_by', 'review_note',
        'created_at', 'reviewed_at',
    )
    actions = ('approve_selected', 'reject_selected')
    date_hierarchy = 'created_at'

    @admin.action(description='Tanlanganlarni tasdiqlash (login Telegramga)')
    def approve_selected(self, request, queryset):
        from accounts.telegram_bot import approve_registration

        ok = 0
        for req in queryset.filter(status='pending'):
            try:
                approve_registration(req, actor=request.user, notify=True)
                ok += 1
            except Exception as exc:
                self.message_user(request, f'#{req.pk}: {exc}', level='error')
        self.message_user(request, f'{ok} ta so‘rov tasdiqlandi.')

    @admin.action(description='Tanlanganlarni rad etish')
    def reject_selected(self, request, queryset):
        from accounts.telegram_bot import reject_registration

        ok = 0
        for req in queryset.filter(status='pending'):
            try:
                reject_registration(req, actor=request.user, notify=True)
                ok += 1
            except Exception as exc:
                self.message_user(request, f'#{req.pk}: {exc}', level='error')
        self.message_user(request, f'{ok} ta so‘rov rad etildi.')

    def has_add_permission(self, request):
        return False


@admin.register(TelegramDialog)
class TelegramDialogAdmin(admin.ModelAdmin):
    list_display = ('chat_id', 'telegram_username', 'step', 'updated_at')
    list_filter = ('step',)
    search_fields = ('chat_id', 'telegram_username')
    readonly_fields = ('chat_id', 'telegram_username', 'step', 'draft', 'updated_at')

    def has_add_permission(self, request):
        return False


@admin.register(LoginDay)
class LoginDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'user', 'login_count', 'first_login_at')
    list_filter = ('date',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__employee_id')
    date_hierarchy = 'date'
    readonly_fields = ('user', 'date', 'first_login_at', 'login_count')
    ordering = ('-date', 'user__username')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ComplianceAuditLog)
class ComplianceAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'event_type', 'actor', 'subject_user',
        'message', 'object_type', 'object_id', 'ip_address',
    )
    list_filter = ('event_type', 'created_at', 'object_type')
    search_fields = (
        'message', 'actor__username', 'subject_user__username',
        'object_id', 'ip_address',
    )
    date_hierarchy = 'created_at'
    readonly_fields = (
        'actor', 'subject_user', 'event_type', 'object_type', 'object_id',
        'message', 'payload', 'ip_address', 'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Регистрируем модели с кастомными админками
admin.site.register(User, CustomUserAdmin)
admin.site.register(FavoritePost, FavoritePostAdmin)
admin.site.register(UserActivity, UserActivityAdmin)
admin.site.register(Achievement, AchievementAdmin)
admin.site.register(UserAchievement, UserAchievementAdmin)
admin.site.register(LearningProgress, LearningProgressAdmin)
admin.site.register(Certificate, CertificateAdmin)
admin.site.register(LevelUpEvent, LevelUpEventAdmin)

# Admin URL: /admin/login-attendance/
from accounts.admin_attendance import login_attendance_view

_prev_admin_get_urls = admin.site.get_urls


def _admin_urls_with_attendance():
    custom = [
        path(
            'login-attendance/',
            admin.site.admin_view(login_attendance_view),
            name='login_attendance',
        ),
    ]
    return custom + _prev_admin_get_urls()


admin.site.get_urls = _admin_urls_with_attendance
