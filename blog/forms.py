import os

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import Document

User = get_user_model()

ALLOWED_DOCUMENT_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt',
    'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov', 'zip', 'rar',
}
MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20 MB


def validate_document_file(uploaded_file):
    name = getattr(uploaded_file, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower().lstrip('.')
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            f"Ruxsat etilmagan fayl turi: .{ext or 'nomaʼlum'}. "
            f"Ruxsat etilgan: {', '.join(sorted(ALLOWED_DOCUMENT_EXTENSIONS))}"
        )
    size = getattr(uploaded_file, 'size', None)
    if size is not None and size > MAX_DOCUMENT_SIZE:
        raise ValidationError("Fayl hajmi 20 MB dan oshmasligi kerak.")


class DocumentUploadForm(forms.ModelForm):
    allowed_roles = forms.MultipleChoiceField(
        choices=User.ROLE_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Ruxsat berilgan rollar",
        help_text="Hujjatga ruxsat berilgan foydalanuvchi rollarini tanlang",
    )

    class Meta:
        model = Document
        fields = [
            'title', 'description', 'file', 'category',
            'is_public', 'allowed_roles', 'requires_acknowledgment',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].validators.append(validate_document_file)

    def clean_file(self):
        uploaded = self.cleaned_data.get('file')
        if uploaded:
            validate_document_file(uploaded)
        return uploaded


class AITestGenerateForm(forms.Form):
    """Admin: rol + son bo‘yicha avtomatik test yaratish."""

    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        label='Foydalanuvchi roli',
        help_text='Qaysi bo‘lim/rol uchun testlar yaratilsin',
    )
    count = forms.IntegerField(
        label='Nechta test yaratilsin?',
        min_value=1,
        max_value=50,
        initial=1,
        help_text='1 dan 50 gacha',
    )
    questions_per_test = forms.IntegerField(
        label='Har bir testda nechta savol?',
        min_value=5,
        max_value=50,
        initial=30,
        help_text='5 dan 50 gacha (odatiy: 30)',
    )
    use_ai = forms.BooleanField(
        label='Bepul AI ishlatilsin (Groq/Gemini)',
        required=False,
        initial=True,
        help_text=(
            'Kalit sozlangan bo‘lsa haqiqiy AI savollar yaratadi. '
            'Kalit bo‘lmasa yoki xato bo‘lsa — shablon generator ishlaydi.'
        ),
    )
