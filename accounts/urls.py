from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from .views import (
    signup, MyLoginView, logout_view,
    profile_view, profile_edit, change_password,
    activity_history, toggle_favorite, favorites_list,
    learning_progress, user_achievements, user_certificates,
    download_certificate, user_statistics, verify_certificate,
    notifications_list, notification_mark_read, notifications_mark_all_read,
)

app_name = 'accounts'

urlpatterns = [
    path('signup/', signup, name='signup'),
    path('login/',  MyLoginView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    path('verify-certificate/', verify_certificate, name='verify_certificate'),
    path(
        'verify-certificate/<str:certificate_id>/',
        verify_certificate,
        name='verify_certificate_detail',
    ),

    # Parol tiklash
    path(
        'password/reset/',
        auth_views.PasswordResetView.as_view(
            template_name='accounts/password_reset.html',
            email_template_name='accounts/password_reset_email.html',
            subject_template_name='accounts/password_reset_subject.txt',
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password/reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password/reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    # Личный кабинет
    path('profile/', profile_view, name='profile'),
    path('profile/edit/', profile_edit, name='profile_edit'),
    path('profile/password/', change_password, name='change_password'),
    path('profile/activity/', activity_history, name='activity_history'),
    path('profile/favorites/', favorites_list, name='favorites'),
    path('notifications/', notifications_list, name='notifications'),
    path('notifications/<int:pk>/read/', notification_mark_read, name='notification_read'),
    path('notifications/read-all/', notifications_mark_all_read, name='notifications_read_all'),
    
    # Избранное
    path('post/<int:post_id>/favorite/', toggle_favorite, name='toggle_favorite'),
    
    # Новые маршруты для прогресса обучения и геймификации
    path('profile/progress/', learning_progress, name='learning_progress'),
    path('profile/achievements/', user_achievements, name='user_achievements'),
    path('profile/certificates/', user_certificates, name='user_certificates'),
    path('profile/certificates/<int:certificate_id>/download/', download_certificate, name='download_certificate'),
    path('profile/statistics/', user_statistics, name='user_statistics'),
]
