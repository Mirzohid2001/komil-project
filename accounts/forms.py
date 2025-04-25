from django.contrib.auth.forms import UserCreationForm
from .models import User
from django import forms

class SignUpForm(UserCreationForm):
    first_name = forms.CharField(required=True, label='Ismingiz')
    last_name  = forms.CharField(required=True, label='Familiyangiz')
    email      = forms.EmailField(required=True, label='Email manzilingiz')
    role       = forms.ChoiceField(choices=User.ROLE_CHOICES, label='Rolni tanlang')

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


class ProfileUpdateForm(forms.ModelForm):
    """Форма для обновления профиля пользователя"""
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
