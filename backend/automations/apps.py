from django.apps import AppConfig


class AutomationsConfig(AppConfig):
    name = "automations"

    def ready(self) -> None:
        from automations import handlers  # noqa: F401
