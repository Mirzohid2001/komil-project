from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.home, name='home'),
    path('category/', views.category_list, name='category_list'),
    path('category/<int:cat_id>/', views.post_list, name='post_list'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('analytics/', views.analytics_dashboard, name='analytics'),
]
