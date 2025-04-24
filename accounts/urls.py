from django.urls import path
from .views import (
    signup, MyLoginView, logout_view,
    profile_view, profile_edit, change_password,
    activity_history, toggle_favorite, favorites_list
)

app_name = 'accounts'

urlpatterns = [
    path('signup/', signup, name='signup'),
    path('login/',  MyLoginView.as_view(), name='login'),
    path('logout/', logout_view, name='logout'),
    
    # Личный кабинет
    path('profile/', profile_view, name='profile'),
    path('profile/edit/', profile_edit, name='profile_edit'),
    path('profile/password/', change_password, name='change_password'),
    path('profile/activity/', activity_history, name='activity_history'),
    path('profile/favorites/', favorites_list, name='favorites'),
    
    # Избранное
    path('post/<int:post_id>/favorite/', toggle_favorite, name='toggle_favorite'),
]
