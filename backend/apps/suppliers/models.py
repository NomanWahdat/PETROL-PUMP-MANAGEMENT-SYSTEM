from django.db import models
from apps.operations.models import ScopedRecord


class Supplier(ScopedRecord):
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=40)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [models.UniqueConstraint(fields=["tenant", "code"], name="supplier_code")]

