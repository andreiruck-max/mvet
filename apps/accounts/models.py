from django.conf import settings
from django.db import models


class AccessPolicy(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rules = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class UserCompanyAccess(models.Model):
    """Explicit company grant; legacy capabilities can only be inherited by company 1."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    company = models.ForeignKey('core.Company', on_delete=models.PROTECT)
    active = models.BooleanField(default=True)
    inherit_legacy = models.BooleanField(default=False)
    rules = models.JSONField(default=dict, blank=True)
    can_view_group = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'company'], name='unique_user_company_access'),
            models.CheckConstraint(condition=models.Q(inherit_legacy=False) | models.Q(company_id=1),
                                   name='company_access_legacy_primary_only'),
        ]
