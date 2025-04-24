from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    path('', views.course_list, name='list'),
    path('category/<slug:category_slug>/', views.course_list, name='category'),
    path('search/', views.course_search, name='search'),
    path('my-courses/', views.my_courses, name='my_courses'),
    path('<slug:course_slug>/', views.course_detail, name='detail'),
    path('<slug:course_slug>/enroll/', views.course_enroll, name='enroll'),
    path('<slug:course_slug>/learn/', views.course_learn, name='learn'),
    path('<slug:course_slug>/module/<int:module_id>/', views.module_detail, name='module_detail'),
    path('<slug:course_slug>/module/<int:module_id>/lesson/<int:lesson_id>/', views.lesson_detail, name='lesson_detail'),
    path('<slug:course_slug>/lesson/<int:lesson_id>/complete/', views.complete_lesson, name='complete_lesson'),
    path('<slug:course_slug>/module/<int:module_id>/lesson/<int:lesson_id>/mark-complete/', views.mark_lesson_complete, name='mark_complete'),
    path('<slug:course_slug>/module/<int:module_id>/lesson/<int:lesson_id>/mark-incomplete/', views.mark_lesson_incomplete, name='mark_incomplete'),
    path('certificate/<str:certificate_id>/', views.view_certificate, name='view_certificate'),
    path('certificate/<str:certificate_id>/download/', views.download_certificate, name='download_certificate'),
    path('api/course/<slug:course_slug>/progress/', views.get_course_progress, name='get_course_progress'),
    path('<slug:course_slug>/module/<int:module_id>/lesson/<int:lesson_id>/comment/', views.add_comment_placeholder, name='add_comment'),
    path('comment/<int:comment_id>/edit/', views.edit_comment_placeholder, name='edit_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment_placeholder, name='delete_comment'),
    path('api/track-video-view/', views.track_video_view, name='track_video_view'),
] 