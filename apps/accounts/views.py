from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from apps.core.services import audit

class AuditedPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change.html"
    success_url = "/"

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        audit(self.request.user, self.request.user, "change_password")
        return response
