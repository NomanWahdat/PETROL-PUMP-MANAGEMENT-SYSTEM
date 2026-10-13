from django.db import models
from django.conf import settings

from apps.common.models import TenantOwnedModel, TimestampedModel


class AuditLog(TenantOwnedModel):
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=100)
    # Store only explicit safe fields; never passwords, tokens or entire request payloads.
    changes = models.JSONField(default=dict, blank=True)

    class Meta(TenantOwnedModel.Meta):
        indexes = [models.Index(fields=["tenant", "created_at"], name="audit_tenant_time")]
        ordering = ["-created_at"]


class PlatformAuditLog(TimestampedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    object_id = models.CharField(max_length=100)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
