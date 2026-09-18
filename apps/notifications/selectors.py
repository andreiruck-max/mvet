from django.db.models import Exists, OuterRef
from django.urls import reverse
from .models import Notification, NotificationRead, NotificationPreference, AlertConfiguration


def allowed_kinds(user):
    if not user.is_authenticated or not user.is_active:
        return []
    permissions = {
        'STOCK': ('view_stock',),
        'MARGIN': ('view_margins',),
        'DUE': ('operate_finance', 'view_finance'),
        'BACKUP': ('manage_alerts',),
    }
    return [kind for kind, perms in permissions.items() if any(user.has_perm('core.' + p) for p in perms)]


def visible(user):
    kinds = allowed_kinds(user)
    disabled = set(NotificationPreference.objects.filter(user=user, enabled=False).values_list('kind', flat=True)) if user.is_authenticated else set()
    config = AlertConfiguration.objects.filter(pk=1).first()
    kinds = [k for k in kinds if k not in disabled and config and getattr(config, k.lower())]
    reads = NotificationRead.objects.filter(user=user, notification=OuterRef('pk'), revision=OuterRef('revision')) if user.is_authenticated else NotificationRead.objects.none()
    return Notification.objects.filter(kind__in=kinds).annotate(is_read=Exists(reads))


def destination(notification):
    routes = {'STOCK': 'product_detail', 'MARGIN': 'sale_detail', 'DUE': 'financial_title'}
    if notification.kind == 'BACKUP':
        return reverse('notification_configuration')
    return reverse(routes[notification.kind], args=[notification.entity_id])
