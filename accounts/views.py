from django.contrib.auth import login, logout, update_session_auth_hash
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from django.core.paginator import Paginator

from .forms import SignUpForm, ProfileUpdateForm
from .models import User, FavoritePost, UserActivity
from blog.models import Post


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            # Записываем активность пользователя
            UserActivity.objects.create(
                user=user,
                activity_type='login',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return redirect('blog:home')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})


class MyLoginView(LoginView):
    template_name = 'accounts/login.html'
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Записываем активность пользователя
        UserActivity.objects.create(
            user=self.request.user,
            activity_type='login',
            ip_address=self.request.META.get('REMOTE_ADDR')
        )
        
        return response


def logout_view(request):
    # Записываем активность пользователя перед выходом
    if request.user.is_authenticated:
        UserActivity.objects.create(
            user=request.user,
            activity_type='logout',
            ip_address=request.META.get('REMOTE_ADDR')
        )
    
    logout(request)
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """Просмотр профиля пользователя"""
    user = request.user
    
    # Получаем избранные посты
    favorites = FavoritePost.objects.filter(user=user)
    
    # Получаем историю активности
    activities = UserActivity.objects.filter(user=user)[:10]  # последние 10 активностей
    
    return render(request, 'accounts/profile.html', {
        'user': user,
        'favorites': favorites,
        'activities': activities,
    })


@login_required
def profile_edit(request):
    """Редактирование профиля пользователя"""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            
            # Записываем активность пользователя
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_update',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, 'Профиль успешно обновлен')
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    
    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
def change_password(request):
    """Изменение пароля пользователя"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Обновляем сессию чтобы пользователь не вылетел
            update_session_auth_hash(request, user)
            
            # Записываем активность пользователя
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_update',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'action': 'password_change'}
            )
            
            messages.success(request, 'Ваш пароль успешно изменен')
            return redirect('accounts:profile')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def activity_history(request):
    """Просмотр истории активности пользователя"""
    activities = UserActivity.objects.filter(user=request.user)
    
    # Пагинация
    paginator = Paginator(activities, 20)  # по 20 записей на страницу
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'accounts/activity_history.html', {'page_obj': page_obj})


@login_required
def toggle_favorite(request, post_id):
    """Добавление/удаление поста в/из избранное"""
    post = get_object_or_404(Post, id=post_id)
    favorite, created = FavoritePost.objects.get_or_create(user=request.user, post=post)
    
    if created:
        # Если запись создана - пост добавлен в избранное
        activity_type = 'favorite_add'
        messages.success(request, 'Пост добавлен в избранное')
    else:
        # Если запись уже существовала - удаляем из избранного
        favorite.delete()
        activity_type = 'favorite_remove'
        messages.info(request, 'Пост удален из избранного')
    
    # Записываем активность пользователя
    UserActivity.objects.create(
        user=request.user,
        activity_type=activity_type,
        post=post,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    # Возвращаем пользователя на ту же страницу
    return redirect(request.META.get('HTTP_REFERER', 'blog:home'))


@login_required
def favorites_list(request):
    """Просмотр списка избранных постов"""
    favorites = FavoritePost.objects.filter(user=request.user)
    
    return render(request, 'accounts/favorites.html', {'favorites': favorites})
