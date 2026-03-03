from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """
        Import signals when the app is ready.
        This ensures signal handlers are registered.
        """
        import accounts.signals
