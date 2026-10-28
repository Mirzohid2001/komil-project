from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    label = 'accounts'
    verbose_name = 'Foydalanuvchilar'

    def ready(self):
        import accounts.signals  # noqa: F401
