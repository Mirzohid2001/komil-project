from django.contrib.auth.forms import UserCreationForm
from .models import User
from django import forms

class SignUpForm(UserCreationForm):
    # Admin role must never be self-assigned during public registration.
    SIGNUP_ROLE_CHOICES = [
        (value, label) for value, label in User.ROLE_CHOICES if value != 'admin'
    ]

    first_name = forms.CharField(required=True, label='Ismingiz')
    last_name  = forms.CharField(required=True, label='Familiyangiz')
    email      = forms.EmailField(required=True, label='Email manzilingiz')
    role       = forms.ChoiceField(choices=SIGNUP_ROLE_CHOICES, label='Rolni tanlang')

    class Meta:
        model  = User
        fields = ['username','first_name','last_name','email','role','password1','password2']
        labels = {
            'username': 'Foydalanuvchi nomi',
            'password1': 'Parol',
            'password2': 'Parolni tasdiqlang',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form-control'
        # Переопределение названий полей для паролей
        self.fields['password1'].label = 'Parol'
        self.fields['password2'].label = 'Parolni tasdiqlang'
        self.fields['role'].choices = self.SIGNUP_ROLE_CHOICES

    def clean_role(self):
        role = self.cleaned_data['role']
        if role == 'admin':
            raise forms.ValidationError("Admin rolini ro'yxatdan o'tish orqali tanlab bo'lmaydi.")
        return role


class ProfileUpdateForm(forms.ModelForm):
    """Форма для обновления профиля пользователя"""
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'profile_image', 'bio', 'phone_number')
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != 'bio':
                field.widget.attrs['class'] = 'form-control'
            if field_name == 'profile_image':
                field.widget.attrs['class'] = 'form-control-file'

    def clean_profile_image(self):
        import os

        image = self.cleaned_data.get('profile_image')
        if not image or not getattr(image, 'name', None):
            return image

        ext = os.path.splitext(image.name)[1].lower().lstrip('.')
        if ext not in self.ALLOWED_IMAGE_EXTENSIONS:
            raise forms.ValidationError(
                "Faqat jpg, jpeg, png, gif yoki webp formatdagi rasmlar ruxsat etiladi."
            )
        if getattr(image, 'size', 0) > self.MAX_IMAGE_SIZE:
            raise forms.ValidationError("Profil rasmi 5 MB dan oshmasligi kerak.")
        return image
