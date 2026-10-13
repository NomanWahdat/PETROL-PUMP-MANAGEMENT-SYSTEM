import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantScopeRequired(RuntimeError):
    pass


class TenantManager(models.Manager):
    def get_queryset(self):
        raise TenantScopeRequired("Use objects.for_tenant(verified_tenant), never an unscoped query.")

    def for_tenant(self, tenant):
        if tenant is None or not tenant.pk:
            raise TenantScopeRequired("A verified tenant is required.")
        return super().get_queryset().filter(tenant_id=tenant.pk)


class TenantOwnedModel(TimestampedModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="%(app_label)s_%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="%(app_label)s_%(class)s_updated",
    )
    objects = TenantManager()
    # Explicit infrastructure-only access for provisioning, migrations and verified auth lookups.
    all_tenants = models.Manager()

    def validate_tenant_links(self, *field_names):
        for name in field_names:
            related = getattr(self, name, None)
            if related is not None and related.tenant_id != self.tenant_id:
                raise ValidationError({name: "Related records must belong to the same tenant."})

    class Meta:
        abstract = True
        # Django constraint validation needs an unrestricted infrastructure manager.
        default_manager_name = "all_tenants"
        base_manager_name = "all_tenants"
