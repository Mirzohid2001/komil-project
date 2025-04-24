from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.home, name='home'),
    path('category/', views.category_list, name='category_list'),
    path('category/<int:cat_id>/', views.post_list, name='post_list'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('analytics/', views.analytics_dashboard, name='analytics'),
    
    # Маршруты для тестирования
    path('tests/', views.test_list, name='test_list'),
    path('tests/start/<int:test_id>/', views.test_start, name='test_start'),
    path('tests/question/', views.test_question, name='test_question'),
    path('tests/finish/', views.test_finish, name='test_finish'),
    path('tests/result/<int:result_id>/', views.test_result, name='test_result'),
    path('tests/history/', views.test_history, name='test_history'),
    path('tests/analytics/', views.test_analytics, name='test_analytics'),
]
