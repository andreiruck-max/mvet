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
        scope = getattr(user_obj, '_mvet_company_scope', None)
        if scope is not None:
            from .models import UserCompanyAccess
            if scope.group or len(scope.company_ids) != 1:
                return False
            grant = UserCompanyAccess.objects.filter(user=user_obj, company_id=scope.company_ids[0], active=True).first()
            if not grant:
                return False
            if not grant.inherit_legacy:
                return grant.rules.get(perm) is True
        if not hasattr(user_obj, '_mvet_rules'):
            from .models import AccessPolicy
            user_obj._mvet_rules = AccessPolicy.objects.filter(user=user_obj).values_list('rules', flat=True).first() or {}
        if perm in user_obj._mvet_rules:
            return user_obj._mvet_rules[perm] is True
        if perm.startswith('core.') and user_obj._mvet_rules.get('__complete__') is True:
            return False
        if super().has_perm(user_obj, perm, obj):
            return True
        code = perm.removeprefix('core.')
        if perm.startswith('core.') and code in CAPABILITIES:
            return any(self.has_perm(user_obj, 'core.'+parent) for parent in CAPABILITIES[code][1])
        return False
