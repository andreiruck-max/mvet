from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["occurred_at", "actor", "entity", "entity_id", "operation"]
    list_filter = ["operation", "entity"]
    search_fields = ["entity_id", "actor__username"]
    readonly_fields = ["actor", "occurred_at", "entity", "entity_id", "operation", "before", "after"]
    list_per_page = 50

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

admin.site.site_header = "MVet 1.0 · Administração"
admin.site.site_title = "Mercadovet"
admin.site.index_title = "Usuários, permissões e auditoria"
