from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "resources"
    verbose_name = "Learning resources & vector search"

    def ready(self) -> None:
        import resources.signals  # noqa: F401
