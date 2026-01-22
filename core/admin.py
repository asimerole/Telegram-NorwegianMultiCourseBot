import csv
from django.contrib import admin, messages
from django.contrib.auth.models import Group
from django.http import HttpResponse
from .models import BotMessage, Course, Lesson, AccessCode, BotUser, FAQItem, Enrollment

# It's a simple registration process

admin.site.unregister(Group)
admin.site.site_header = "Панель управления Multi-Bot"
admin.site.site_title = "Norwegian Course Bot"
admin.site.index_title = "Настройка курсов и подписок"

# This is a beautiful registration (to add lessons directly within the course)
class LessonInline(admin.StackedInline):
    """Shows lessons within the Course settings"""
    model = Lesson
    extra = 0
    fields = ('day_number', 'send_time', 'lesson_type', 'text')
    show_change_link = True 

class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0  
    fields = ('course', 'current_day', 'is_active', 'start_date') 
    readonly_fields = ('start_date',) 
    can_delete = True 

@admin.action(description="⚡Создать полную копию (с уроками)")
def duplicate_course(modeladmin, request, queryset):
    # queryset is a list of courses selected by the administrator with a check mark
    import random

    for original_course in queryset:
        # We keep the list of lessons until we change the course object
        original_lessons = list(original_course.lessons.all())
        
        # Cloning the COURSE itself
        # To copy an object in Django, simply set its pk (id) to None and save it.
        original_course.pk = None 
        original_course.title = f"Копия: {original_course.title}"
        
        original_course.save()          # A new course has now been created in the database.
        new_course = original_course    # For code clarity
        
        # Clone LESSONS and link them to the new course
        for lesson in original_lessons:
            lesson.pk = None            # This makes the lesson a new entry.
            lesson.course = new_course  # Link to the newly created course
            lesson.save()
            
    # Display a success message
    modeladmin.message_user(
        request, 
        f"Успешно скопировано {queryset.count()} курс(ов).", 
        messages.SUCCESS
    )

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'duration_days')            # What to show in the list table
    inlines = [LessonInline]            # Insert lessons directly into the course page
    actions = [duplicate_course]
    search_fields = ('title',)
    

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('course', 'day_number', 'send_time', 'lesson_type', 'short_text')
    list_filter = ('course', 'lesson_type', 'day_number')
    ordering = ('course', 'day_number', 'send_time')
    
    fieldsets = (
        ('Расписание', {
            'fields': ('course', 'day_number', 'send_time', 'lesson_type')
        }),
        ('Контент', {
            'fields': ('text', 'image', 'audio', 'video_note', 'file_doc')
        }),
        ('Тест / Опрос', {
            'fields': ('quiz_options', 'correct_answer', 'error_feedback'),
            'description': 'Заполнять только для тестов.'
        }),
    )

    def short_text(self, obj):
        return obj.text[:50] + "..." if obj.text else "-"
    
@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    # COLUMNS: What to display in the table
    list_display = ('first_name', 'username', 'telegram_id', 'created_at', 'get_courses_list')    
    search_fields = ('username', 'first_name', 'telegram_id')
    ordering = ('-created_at',)
    actions = ["export_as_csv"]

    inlines = [EnrollmentInline]
    
    # Export to Excel table
    @admin.action(description="Испортировать выбранные в Excel (CSV)")
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            row = writer.writerow([getattr(obj, field) for field in field_names])

        return response
    
    @admin.display(description='Курсы')
    def get_courses_list(self, obj):
        # Получаем все активные курсы юзера
        courses = obj.enrollments.filter(is_active=True)
        # Собираем их названия в строку
        return ", ".join([f"{e.course.title} (Д.{e.current_day})" for e in courses])

admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """
    A separate page to see everyone who is currently studying
    """
    list_display = ('user', 'course', 'get_status', 'is_active', 'start_date')
    list_filter = ('course', 'is_active', 'current_day')
    search_fields = ('user__username', 'user__first_name', 'user__telegram_id')
    autocomplete_fields = ['user', 'course']

    @admin.display(description='Прогресс')
    def get_status(self, obj):
        real_day = obj.get_real_day()
        if not obj.is_active:
            return "🔴 Остановил"
        if real_day > obj.course.duration_days:
            return "🏁 ЗАВЕРШИЛ"
        return f"🟢 День {obj.current_day} (Реальный: {real_day})"
    
@admin.register(FAQItem)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'order', 'is_visible')
    list_editable = ('order', 'is_visible')
    search_fields = ('question', 'answer')

@admin.register(BotMessage)
class BotMessageAdmin(admin.ModelAdmin):
    list_display = ('description', 'slug', 'text_preview')
    search_fields = ('slug', 'description', 'text')
    # Make the slug read-only if the entry already exists, so as not to break the bot
    readonly_fields = ('slug',) 

    def text_preview(self, obj):
        return obj.text[:50] + "..." if obj.text else "-"
    text_preview.short_description = "Текст"
    
    # Allow editing of slugs only when creating a new entry
    def get_readonly_fields(self, request, obj=None):
        if obj: 
            return self.readonly_fields
        return ()

@admin.register(AccessCode)
class AccessCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'get_courses', 'is_active', 'activated_by', 'created_at')
    search_fields = ('code', 'activated_by__username')
    list_filter = ('is_active',)
    
    @admin.display(description="Курсы (Пакет)")
    def get_courses(self, obj):
        courses = [c.title for c in obj.courses.all()]
        if not courses:
            return "⚠️ ПУСТОЙ (Ничего не откроет)"
        return ", ".join(courses)