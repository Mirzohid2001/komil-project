from django.contrib.auth.forms import UserCreationForm
from .models import User
from django import forms

class SignUpForm(UserCreationForm):
    first_name = forms.CharField(required=True)
    last_name  = forms.CharField(required=True)
    email      = forms.EmailField(required=True)
    role       = forms.ChoiceField(choices=User.ROLE_CHOICES)

    class Meta:
        model  = User
        fields = ['username','first_name','last_name','email','role','password1','password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form-control'


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
