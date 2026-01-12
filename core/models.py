from django.utils import timezone
from django.db import models
from django.utils.safestring import mark_safe

class Course(models.Model):
    title = models.CharField("Название курса", max_length=100)
    keyword = models.CharField("Кодовое слово (из видео)", max_length=50, unique=True)
    description = models.TextField("Описание (для админа)", blank=True)
    
    def __str__(self):
        return f"{self.title} [{self.keyword}]"

    class Meta:
        verbose_name = "Мини-курс"
        verbose_name_plural = "Мини-курс"
    
    start_message = models.TextField(
        "Уведомление по окончанию курса", 
        blank=True, 
        default=
            f"🚀 <b>Отлично! Ти записан на курс.</b>\n\n"
            f"📅 <b>Расписание:</b>\n"
            f"Материалы будут приходить каждый день в <b>10:00, 14:00 та 18:00</b>.\n\n"
            f"⏳ <b>Старт:</b> Твой первый день начнётся <b>ЗАВТРА в 10:00</b>.\n"
            f"Сегодня ты можешь отдыхать и готовится!"
    )

    finish_message = models.TextField(
        "Уведомление по окончанию курса", 
        blank=True, 
        default="Поздравляю! Ти прошёл курс. Теперь ты можешь вводить кодовое слово другого курса 😜"
    )
    
    # щоб знати скільки днів триває курс (або вираховувати автоматично)
    duration_days = models.PositiveIntegerField("Тривалість (днів)", default=5)

class Lesson(models.Model):
    TYPE_CHOICES = [
        ('theory', '📚 Просто теория (читать/смотреть)'),
        ('quiz', '✅ Тест (кнопки с вариантами)'),
        ('text_input', '✍️ Вписать правильный ответ вручную'),
        # ('image_quiz', '🖼 Выбор картинки'), # Можна додати пізніше, якщо встигнеш
    ]

    TIME_CHOICES = [
        (10, '10:00'),
        (12, '12:00'),
        (18, '18:00'),
    ]
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name="К какому курсу", related_name='lessons')
    day_number = models.PositiveIntegerField("День выдачи (1-31)", default=1)
    time_slot = models.IntegerField("Время выдачи", choices=TIME_CHOICES)
    
    lesson_type = models.CharField("Тип задания", max_length=20, choices=TYPE_CHOICES, default='theory')

    # Контент уроку
    text = models.TextField("Текст сообщения", blank=True)
    image = models.ImageField("Картинка", upload_to='lessons/images/', blank=True, null=True)
    audio = models.FileField("Аудио", upload_to='lessons/audio/', blank=True, null=True)
    video_note = models.FileField("Видео (кружочек/файл)", upload_to='lessons/video/', blank=True, null=True)
    file_doc = models.FileField("Документ (PDF)", upload_to='lessons/docs/', blank=True, null=True)

    # --- ПОЛЯ ДЛЯ ТЕСТІВ ---
    # Для Quiz: Замовниця пише варіанти через Enter (новий рядок)
    quiz_options = models.TextField(
        "Варианты ответов (каждый с новой строки)", 
        blank=True, 
        help_text=mark_safe("Только для ТЭСТА. Напиши варианты например<br>" 
            "Apple<br>" 
            "Banana<br>" 
            "Orange"
        )
    )
    
    # Правильна відповідь (Текст кнопки або слово для ручного вводу)
    correct_answer = models.CharField("Правильный ответ", max_length=255, blank=True, help_text="Точний текст правильного варианта или слова")
    
    # Повідомлення, якщо відповів неправильно
    error_feedback = models.TextField(
        "Пояснения к ответам (каждое с новой строки)", 
        blank=True, 
        help_text=mark_safe("ВАЖНО: Количество строк должно совпадать с вариантами ответов!<br>"
                  "1 строка объясняет 1-й вариант, 2-я - 2-й и т.д.<br>"
                  "Для правильного ответа можно оставить строку пустой или написать 'Верно!'.")
    )

    def __str__(self):
        return f"{self.course.title} - День {self.day_number} в {self.time_slot}:00"

    class Meta:
        verbose_name = "Урок/Задания"
        verbose_name_plural = "Уроки"
        ordering = ['day_number', 'time_slot', 'id']

class AccessCode(models.Model):
    code = models.CharField("Код доступа", max_length=20, unique=True)
    is_active = models.BooleanField("Активный?", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # null=True, blank=True — потому что изначально код ничей (ни кем не активирован)
    activated_by = models.ForeignKey(
        'BotUser', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Кем активирован",
        related_name="activated_codes"
    )

    def __str__(self):
        owner = f" ({self.activated_by.first_name})" if self.activated_by else ""
        return f"{self.code}{owner}"

    class Meta:
        verbose_name = "Код доступа"
        verbose_name_plural = "Коды доступа"

class BotUser(models.Model):
    telegram_id = models.BigIntegerField("Telegram ID", unique=True)
    username = models.CharField("Username", max_length=255, blank=True, null=True)
    first_name = models.CharField("Имя", max_length=255, blank=True, null=True)
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)
    
    # Зв'язок з поточним курсом (може бути пустим, якщо ще не ввів кодове слово)
    current_course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Активный курс")
    course_start_date = models.DateTimeField("Дата начала курса", null=True)
    current_course_day = models.IntegerField("Текущий день (кэш)", default=0)

    def __str__(self):
        return f"{self.first_name} ({self.telegram_id})"
    
    def get_real_day(self):
        if not self.course_start_date:
            return 0
        delta = timezone.now() - self.course_start_date
        return delta.days + 1

    class Meta:
        verbose_name = "Пользователь бота"
        verbose_name_plural = "Пользователи бота"

class UserProgress(models.Model):
    user = models.ForeignKey(BotUser, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} -> {self.lesson} ({self.sent_at.date()})"
    
class FAQItem(models.Model):
    question = models.CharField("Вопрос (на кнопке)", max_length=255)
    answer = models.TextField("Ответ (в сообщении)")
    order = models.IntegerField("Порядок сортировки", default=0, help_text="Чем меньше число, тем выше кнопка")
    is_visible = models.BooleanField("Показывать в боте?", default=True)

    class Meta:
        verbose_name = "Вопрос-Ответ"
        verbose_name_plural = "FAQ (Вопросы и ответы)"
        ordering = ['order', 'id']

    def __str__(self):
        return self.question
    
class BotMessage(models.Model):
    slug = models.SlugField(
        "Техническое имя (Ключ)", 
        unique=True, 
        help_text="НЕ МЕНЯТЬ! Это имя используется в коде (например: start_message)"
    )
    text = models.TextField("Текст сообщения", help_text="Поддерживает HTML теги (<b>жирный</b>, <i>курсив</i>)")
    description = models.CharField("Где используется (для админа)", max_length=255, blank=True)

    class Meta:
        verbose_name = "Текст бота"
        verbose_name_plural = "Тексты бота (Приветствие, Ошибки)"

    def __str__(self):
        return f"{self.slug} ({self.description})"
    
class BotSettings(models.Model):
    key = models.CharField(max_length=50, unique=True, verbose_name="Название настройки")
    value = models.CharField(max_length=255, verbose_name="Значение")

    def __str__(self):
        return f"{self.key}: {self.value}"

    class Meta:
        verbose_name = "Настройка бота"
        verbose_name_plural = "Настройки бота"