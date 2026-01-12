import csv
from django.contrib import admin, messages
from django.contrib.auth.models import Group
from django.http import HttpResponse
from .models import BotMessage, Course, Lesson, AccessCode, BotUser, FAQItem

# Це проста реєстрація
admin.site.register(AccessCode)

admin.site.unregister(Group)
admin.site.site_header = "Панель управления Ботом"
admin.site.site_title = "Norwegian Course Bot"
admin.site.index_title = "Настройка курсов"

# Це красива реєстрація (щоб уроки додавати прямо всередині курсу)
class LessonInline(admin.StackedInline):
    model = Lesson
    extra = 1 

@admin.action(description="⚡Создать полную копию (с уроками)")
def duplicate_course(modeladmin, request, queryset):
    # queryset - це список курсів, які вибрав админ галочкою
    
    for original_course in queryset:
        # 1. Зберігаємо список уроків, поки ми ще не змінили об'єкт курсу
        original_lessons = list(original_course.lessons.all())
        
        # 2. Клонуємо сам КУРС
        # Щоб скопіювати об'єкт в Django, достатньо скинути його pk (id) в None і зберегти
        original_course.pk = None 
        original_course.title = f"Копия: {original_course.title}"
        
        # Додаємо випадковий хвіст до ключового слова, бо воно unique (має бути унікальним)
        import random
        original_course.keyword = f"{original_course.keyword}_copy_{random.randint(100, 999)}"
        
        original_course.save() # Тепер у базі створився новий курс
        new_course = original_course # Для ясності коду
        
        # 3. Клонуємо УРОКИ і прив'язуємо до нового курсу
        for lesson in original_lessons:
            lesson.pk = None # Це робить урок новим записом
            lesson.course = new_course # Прив'язуємо до новоствореного курсу
            lesson.save()
            
    # Виводимо повідомлення про успіх
    modeladmin.message_user(
        request, 
        f"Успешно скопировано {queryset.count()} курс(ов). Не забудьте изменить кодовые слова!", 
        messages.SUCCESS
    )

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'keyword') # Що показувати в таблиці списку
    inlines = [LessonInline] # Вставляємо уроки прямо в сторінку курсу

    actions = [duplicate_course]
    

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('course', 'day_number', 'time_slot', 'lesson_type', 'short_text')
    list_filter = ('course', 'lesson_type', 'day_number')
    
    # Групуємо поля для краси
    fieldsets = (
        ('Розклад та Тип', {
            'fields': ('course', 'day_number', 'time_slot', 'lesson_type')
        }),
        ('Контент (Медиа)', {
            'fields': ('text', 'image', 'audio', 'video_note', 'file_doc')
        }),
        ('Настройка Теста/Задания', {
            'fields': ('quiz_options', 'correct_answer', 'error_feedback'),
            'description': 'Заполнять ТОЛЬКО если выбран тип "Тест" или "Ввести ответ". Для теории оставить пустым.'
        }),
    )

    def short_text(self, obj):
        return obj.text[:50] + "..." if obj.text else "-"
    
@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    # 1. СТОВПЧИКИ: Що показувати в таблиці
    list_display = ('first_name', 'username', 'telegram_id', 'get_status_display', 'current_course', 'course_start_date', 'created_at')

    readonly_fields = ('course_start_date', 'created_at')

    # 2. ФІЛЬТРИ: Бокова панель праворуч 
    list_filter = ('current_course', 'created_at')
    
    # 3. ПОШУК: Рядок пошуку зверху
    search_fields = ('username', 'first_name', 'telegram_id')
    
    # 4. СОРТУВАННЯ: За замовчуванням нові зверху
    ordering = ('-created_at',)

    # 5. КУЛЬКУЛЯТОР (Додаткова логіка для стовпчика "Статус")
    @admin.display(description='Этап обучения')
    def get_status_display(self, obj):
        # 1. Якщо курсу немає
        if not obj.current_course:
            return "⚪ Только зашёл"
        
        # 2. Якщо курс є, але дата старту не задана (баг або очікування)
        if not obj.course_start_date:
            return "🟡 Ждет старта"

        # 3. Рахуємо реальний день
        day = obj.get_real_day()

        # 4. Красиве відображення
        if day > 5: # Якщо курс 5 днів
            return "🏁 ЗАВЕРШИЛ"
        elif day < 1:
            return "🕒 Скоро старт"
        else:
            return f"🟢 День {day}"
    
    actions = ["export_as_csv"]
    
    # 6. Експорт в ексель таблицю
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
    
@admin.register(FAQItem)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'order', 'is_visible')
    list_editable = ('order', 'is_visible')
    search_fields = ('question', 'answer')

@admin.register(BotMessage)
class BotMessageAdmin(admin.ModelAdmin):
    list_display = ('description', 'slug', 'text_preview')
    search_fields = ('slug', 'description', 'text')
    # Делаем slug только для чтения, если запись уже создана, чтобы не сломать бота
    readonly_fields = ('slug',) 

    def text_preview(self, obj):
        return obj.text[:50] + "..." if obj.text else "-"
    text_preview.short_description = "Текст"
    
    # Разрешаем редактировать slug только при создании новой записи
    def get_readonly_fields(self, request, obj=None):
        if obj: # редактирование существующей
            return self.readonly_fields
        return ()