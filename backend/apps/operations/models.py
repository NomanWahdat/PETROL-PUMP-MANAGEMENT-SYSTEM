from django.db import models
from apps.common.models import TenantOwnedModel


class ScopedRecord(TenantOwnedModel):
    class Meta(TenantOwnedModel.Meta):
        abstract = True
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="%(app_label)s_%(class)s_scope")]


class DayRecord(ScopedRecord):
    day = models.ForeignKey("cash.DailyClosing", on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    class Meta(ScopedRecord.Meta):
        abstract = True


class OperationRequest(ScopedRecord):
    key = models.UUIDField()
    operation = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64)
    response = models.JSONField()
    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [models.UniqueConstraint(fields=["tenant", "key"], name="operation_request_key")]

