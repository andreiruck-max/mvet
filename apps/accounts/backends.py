from django.contrib.auth.backends import ModelBackend
from .permissions import CAPABILITIES


class AccessBackend(ModelBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous:
            return False
        if user_obj.is_superuser:
            return True
        if obj is not None:
            return False
        if not hasattr(user_obj, '_mvet_rules'):
            from .models import AccessPolicy
            user_obj._mvet_rules = AccessPolicy.objects.filter(user=user_obj).values_list('rules', flat=True).first() or {}
        if perm in user_obj._mvet_rules:
            return user_obj._mvet_rules[perm] is True
        if super().has_perm(user_obj, perm, obj):
            return True
        code = perm.removeprefix('core.')
        if perm.startswith('core.') and code in CAPABILITIES:
            return any(self.has_perm(user_obj, 'core.'+parent) for parent in CAPABILITIES[code][1])
        return False
