from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from apps.core.services import audit

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    audit(user, user, "login")

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is not None:
        audit(user, user, "logout")
