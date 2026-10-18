from datetime import datetime

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path

from accounts.models import Department, User
from accounts.audit import log_compliance_event
from .bulk_assign import bulk_assign_course, filter_assignees
from .models import (
    Course, Module, Lesson, Enrollment,
    CompletedLesson, CourseCategory, CourseCertificate,
    LessonAttachment, LessonComment,
    LessonQuizQuestion, LessonQuizOption, LessonQuizAttempt,
    CourseAssignment, LessonAssignmentSubmission, LessonVideoProgress,
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
    list_display = (
        'title', 'module', 'lesson_type', 'duration', 'order',
        'is_free_preview', 'min_watch_percent', 'has_video_display',
    )
    list_filter = ('lesson_type', 'is_free_preview', 'auto_complete_on_watch', 'module__course')
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
            'fields': (
                'video_url', 'video_file',
                'min_watch_percent', 'auto_complete_on_watch',
            ),
            'description': (
                'Video fayl yoki YouTube/Vimeo URL. '
                'Minimal ko‘rish foizi — darsni yakunlash sharti.'
            ),
        }),
        ('Meta', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(boolean=True, description='Video bor')
    def has_video_display(self, obj):
        return obj.has_video

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
    change_list_template = 'admin/courses/courseassignment_changelist.html'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'bulk-assign/',
                self.admin_site.admin_view(self.bulk_assign_view),
                name='courses_courseassignment_bulk_assign',
            ),
        ]
        return custom + urls

    def save_model(self, request, obj, form, change):
        if not obj.assigned_by_id:
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)
        if not change:
            log_compliance_event(
                event_type='course_assigned',
                actor=request.user,
                subject_user=obj.user,
                object_type='CourseAssignment',
                object_id=obj.pk,
                message=f'{obj.course.title} → {obj.user.username}',
                payload={
                    'course_id': obj.course_id,
                    'deadline': obj.deadline.isoformat() if obj.deadline else None,
                    'is_mandatory': obj.is_mandatory,
                },
                request=request,
            )

    def bulk_assign_view(self, request):
        if not request.user.has_perm('courses.add_courseassignment'):
            messages.error(request, 'Ommaviy topshiriq uchun ruxsat yo‘q.')
            return redirect('admin:courses_courseassignment_changelist')

        courses = Course.objects.filter(status='published').order_by('title')
        departments = Department.objects.all()
        roles = [(v, l) for v, l in User.ROLE_CHOICES if v != 'admin']
        shifts = User.SHIFT_CHOICES

        form_data = {
            'course': request.POST.get('course', ''),
            'deadline': request.POST.get('deadline', ''),
            'role': request.POST.get('role', ''),
            'department': request.POST.get('department', ''),
            'shift': request.POST.get('shift', ''),
            'notes': request.POST.get('notes', ''),
            'is_mandatory': request.method != 'POST' or request.POST.get('is_mandatory') == '1',
        }
        preview_count = None

        if request.method == 'POST':
            course_id = request.POST.get('course')
            deadline_raw = request.POST.get('deadline')
            role = request.POST.get('role') or ''
            department_raw = request.POST.get('department') or ''
            shift = request.POST.get('shift') or ''
            notes = request.POST.get('notes') or ''
            is_mandatory = request.POST.get('is_mandatory') == '1'
            department_id = int(department_raw) if department_raw.isdigit() else None

            if not course_id or not deadline_raw:
                messages.error(request, 'Kurs va muddat majburiy.')
            elif not (role or department_id or shift):
                messages.error(
                    request,
                    'Kamida bitta filtr tanlang: rol, bo‘lim yoki smena.',
                )
            else:
                try:
                    deadline = datetime.strptime(deadline_raw, '%Y-%m-%d').date()
                    course = Course.objects.get(pk=course_id)
                except (ValueError, Course.DoesNotExist):
                    messages.error(request, 'Kurs yoki muddat noto‘g‘ri.')
                else:
                    if request.POST.get('preview'):
                        preview_count = filter_assignees(
                            role=role,
                            department_id=department_id,
                            shift=shift,
                        ).count()
                    elif request.POST.get('assign'):
                        result = bulk_assign_course(
                            course=course,
                            deadline=deadline,
                            assigned_by=request.user,
                            role=role,
                            department_id=department_id,
                            shift=shift,
                            is_mandatory=is_mandatory,
                            notes=notes,
                        )
                        log_compliance_event(
                            event_type='course_bulk_assigned',
                            actor=request.user,
                            object_type='Course',
                            object_id=course.id,
                            message=(
                                f'Ommaviy: {course.title} — '
                                f'+{result["created"]} yangi, '
                                f'{result["updated"]} yangilandi'
                            ),
                            payload=result,
                            request=request,
                        )
                        messages.success(
                            request,
                            (
                                f'Tayinlandi: {result["created"]} yangi, '
                                f'{result["updated"]} yangilandi, '
                                f'{result["skipped"]} o‘tkazib yuborildi '
                                f'(filtr: {result["total_matched"]} xodim).'
                            ),
                        )
                        return redirect('admin:courses_courseassignment_changelist')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Ommaviy kurs topshirig‘i',
            'courses': courses,
            'departments': departments,
            'roles': roles,
            'shifts': shifts,
            'form_data': form_data,
            'preview_count': preview_count,
            'opts': self.model._meta,
        }
        return render(request, 'admin/courses/bulk_assign.html', context)


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
            log_compliance_event(
                event_type='assignment_approved',
                actor=request.user,
                subject_user=sub.user,
                object_type='LessonAssignmentSubmission',
                object_id=sub.pk,
                message=f'Vazifa tasdiqlandi: {sub.lesson.title}',
                payload={'lesson_id': sub.lesson_id},
                request=request,
            )
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


@admin.register(LessonVideoProgress)
class LessonVideoProgressAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'lesson', 'percent', 'watched_seconds',
        'duration_seconds', 'last_position', 'watch_completed_at', 'updated_at',
    )
    list_filter = ('percent', 'lesson__module__course', 'updated_at')
    search_fields = ('user__username', 'lesson__title')
    readonly_fields = ('created_at', 'updated_at', 'watch_completed_at')
    date_hierarchy = 'updated_at'
    autocomplete_fields = ('user', 'lesson')

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
