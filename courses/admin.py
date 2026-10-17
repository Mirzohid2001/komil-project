from django.contrib import admin
from .models import (
    Course, Module, Lesson, Enrollment,
    CompletedLesson, CourseCategory, CourseCertificate,
    LessonAttachment, LessonComment,
    LessonQuizQuestion, LessonQuizOption, LessonQuizAttempt,
    CourseAssignment, LessonAssignmentSubmission,
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
    # price/is_free kept in DB for compatibility but hidden — internal factory LMS, no payments.
    list_display = ['title', 'category', 'difficulty', 'status', 'is_featured', 'created_at']
    list_filter = ['status', 'difficulty', 'category', 'is_featured']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_editable = ['status', 'is_featured']
    exclude = ['price', 'is_free']
    inlines = [ModuleInline]
    fieldsets = (
        ('Asosiy', {
            'fields': ('title', 'slug', 'short_description', 'description', 'cover', 'category'),
        }),
        ('Sozlamalar', {
            'fields': ('difficulty', 'duration', 'status', 'is_featured', 'allowed_roles'),
        }),
    )

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


class LessonQuizOptionInline(admin.TabularInline):
    model = LessonQuizOption
    extra = 2


class LessonQuizQuestionInline(admin.StackedInline):
    model = LessonQuizQuestion
    extra = 1
    show_change_link = True


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'lesson_type', 'duration', 'order', 'is_free_preview', 'has_video')
    list_filter = ('lesson_type', 'is_free_preview', 'module__course')
    search_fields = ('title', 'content', 'module__title', 'module__course__title')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [LessonAttachmentInline, LessonQuizQuestionInline]
    fieldsets = (
        ('Asosiy maʼlumot', {
            'fields': (
                'module', 'title', 'lesson_type', 'content',
                'duration', 'order', 'is_free_preview', 'allow_comments',
            )
        }),
        ('Video', {
            'fields': ('video_url', 'video_file'),
            'classes': ('collapse',),
            'description': 'Video fayl yuklang yoki tashqi video URL kiriting. Quiz uchun pastda savollar qo‘shing.',
        }),
        ('Meta', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_video(self, obj):
        return bool(obj.video_url or obj.video_file)
    has_video.short_description = "Video bor"
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


@admin.register(CourseAssignment)
class CourseAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'course', 'deadline', 'is_mandatory',
        'assigned_by', 'assigned_at', 'completed_at', 'is_overdue',
    )
    list_filter = ('is_mandatory', 'deadline', 'course', 'assigned_at')
    search_fields = ('user__username', 'course__title', 'notes')
    autocomplete_fields = ('user', 'course', 'assigned_by')
    date_hierarchy = 'deadline'

    def save_model(self, request, obj, form, change):
        if not obj.assigned_by_id:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(LessonAssignmentSubmission)
class LessonAssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'status', 'submitted_at', 'reviewed_by', 'reviewed_at')
    list_filter = ('status', 'submitted_at', 'lesson__module__course')
    search_fields = ('user__username', 'lesson__title', 'comment')
    readonly_fields = ('submitted_at',)
    actions = ['approve_selected', 'reject_selected']

    @admin.action(description='Tanlanganlarni tasdiqlash')
    def approve_selected(self, request, queryset):
        from django.utils import timezone
        from .models import CompletedLesson, Enrollment
        n = 0
        for sub in queryset.exclude(status='approved'):
            sub.status = 'approved'
            sub.reviewed_by = request.user
            sub.reviewed_at = timezone.now()
            sub.save()
            enrollment = Enrollment.objects.filter(user=sub.user, course=sub.lesson.module.course).first()
            if enrollment:
                CompletedLesson.objects.get_or_create(
                    enrollment=enrollment,
                    lesson=sub.lesson,
                    defaults={'user': sub.user},
                )
                enrollment.progress()
            n += 1
        self.message_user(request, f'{n} ta vazifa tasdiqlandi.')

    @admin.action(description='Tanlanganlarni rad etish')
    def reject_selected(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f'{updated} ta vazifa rad etildi.')

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


@admin.register(LessonComment)
class LessonCommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'created_at')
    list_filter = ('lesson__module__course', 'created_at')
    search_fields = ('user__username', 'content', 'lesson__title')
    date_hierarchy = 'created_at'


@admin.register(LessonQuizQuestion)
class LessonQuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'lesson', 'order')
    list_filter = ('lesson__module__course',)
    search_fields = ('text', 'lesson__title')
    inlines = [LessonQuizOptionInline]


@admin.register(LessonQuizAttempt)
class LessonQuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'lesson', 'score', 'total', 'percentage', 'is_passed', 'completed_at')
    list_filter = ('is_passed', 'lesson__module__course', 'completed_at')
    search_fields = ('user__username', 'lesson__title')
