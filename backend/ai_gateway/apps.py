from django.apps import AppConfig


class AiGatewayConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ai_gateway"

    def ready(self) -> None:
        from ai_gateway import handlers  # noqa: F401
