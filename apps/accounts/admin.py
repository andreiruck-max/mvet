from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from apps.core.services import audit

class SuperuserOnly:
    def has_module_permission(self, request): return request.user.is_active and request.user.is_superuser
    def has_view_permission(self, request, obj=None): return self.has_module_permission(request)
    def has_add_permission(self, request): return self.has_module_permission(request)
    def has_change_permission(self, request, obj=None): return self.has_module_permission(request)
    def has_delete_permission(self, request, obj=None): return False

class AuditedUserAdmin(SuperuserOnly, UserAdmin):
    def user_change_password(self, request, id, form_url=""):
        from django.db import transaction
        with transaction.atomic():
            response = super().user_change_password(request, id, form_url)
            if request.method == "POST" and response.status_code == 302:
                audit(request.user, User.objects.get(pk=id), "admin_change_password")
            return response

    def save_model(self, request, obj, form, change):
        before = {}
        if change:
            previous = User.objects.get(pk=obj.pk)
            before = {"username": previous.username, "active": previous.is_active,
                      "staff": previous.is_staff, "superuser": previous.is_superuser}
        super().save_model(request, obj, form, change)
        audit(request.user, obj, "update_user" if change else "create_user", before,
              {"username": obj.username, "active": obj.is_active, "staff": obj.is_staff,
               "superuser": obj.is_superuser})

    def save_related(self, request, form, formsets, change):
        obj = form.instance
        before = {"groups": list(obj.groups.values_list("name", flat=True)),
                  "permissions": list(obj.user_permissions.values_list("codename", flat=True))}
        super().save_related(request, form, formsets, change)
        after = {"groups": list(obj.groups.values_list("name", flat=True)),
                 "permissions": list(obj.user_permissions.values_list("codename", flat=True))}
        if before != after:
            audit(request.user, obj, "update_user_permissions", before, after)

class AuditedGroupAdmin(SuperuserOnly, admin.ModelAdmin):
    filter_horizontal = ["permissions"]
    search_fields = ["name"]

    def save_model(self, request, obj, form, change):
        before = {"name": Group.objects.get(pk=obj.pk).name} if change else {}
        super().save_model(request, obj, form, change)
        audit(request.user, obj, "update_group" if change else "create_group", before, {"name": obj.name})

    def save_related(self, request, form, formsets, change):
        obj = form.instance
        before = {"permissions": list(obj.permissions.values_list("codename", flat=True))}
        super().save_related(request, form, formsets, change)
        after = {"permissions": list(obj.permissions.values_list("codename", flat=True))}
        if before != after:
            audit(request.user, obj, "update_group_permissions", before, after)

admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, AuditedUserAdmin)
admin.site.register(Group, AuditedGroupAdmin)
