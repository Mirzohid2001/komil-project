from django.contrib import admin
from .models import (
    Course, Module, Lesson, Enrollment, 
    CompletedLesson, CourseCategory, CourseCertificate,
    LessonAttachment
)

@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'courses_count')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)
    ordering = ['name']

class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'difficulty', 'status', 'price', 'is_free', 'is_featured', 'created_at']
    list_filter = ['status', 'difficulty', 'category', 'is_free', 'is_featured']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_editable = ['status', 'is_featured', 'is_free', 'price']
    inlines = [ModuleInline]

class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'total_lessons')
    list_filter = ('course',)
    search_fields = ('title', 'course__title')
    inlines = [LessonInline]

class LessonAttachmentInline(admin.TabularInline):
    model = LessonAttachment
    extra = 1

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'lesson_type', 'duration', 'order', 'is_free_preview', 'has_video')
    list_filter = ('lesson_type', 'is_free_preview', 'module__course')
    search_fields = ('title', 'content', 'module__title', 'module__course__title')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [LessonAttachmentInline]
    fieldsets = (
        ('Основная информация', {
            'fields': ('module', 'title', 'lesson_type', 'content', 'duration', 'order', 'is_free_preview', 'allow_comments')
        }),
        ('Видео', {
            'fields': ('video_url', 'video_file'),
            'classes': ('collapse',),
            'description': 'Загрузите видео файл или укажите URL для внешнего видео'
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_video(self, obj):
        return bool(obj.video_url or obj.video_file)
    has_video.short_description = "Имеет видео"
    has_video.boolean = True

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'enrolled_at', 'is_completed', 'completed_at', 'progress')
    list_filter = ('is_completed', 'enrolled_at')
    search_fields = ('user__username', 'course__title')
    date_hierarchy = 'enrolled_at'
    
    def progress(self, obj):
        return f"{obj.progress()}%"
    progress.short_description = "Progress"

@admin.register(CompletedLesson)
class CompletedLessonAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'completed_at')
    list_filter = ('lesson__module__course', 'completed_at')
    search_fields = ('user__username', 'lesson__title')
    date_hierarchy = 'completed_at'

@admin.register(CourseCertificate)
class CourseCertificateAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'certificate_id', 'issue_date')
    list_filter = ('issue_date',)
    search_fields = ('enrollment__user__username', 'enrollment__course__title', 'certificate_id')
    date_hierarchy = 'issue_date'
    readonly_fields = ('certificate_id',)

@admin.register(LessonAttachment)
class LessonAttachmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'file', 'created_at')
    list_filter = ('lesson__module__course',)
    search_fields = ('title', 'lesson__title')
