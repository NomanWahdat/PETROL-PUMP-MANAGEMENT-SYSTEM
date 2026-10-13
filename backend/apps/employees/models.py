from django.db import models

from apps.common.models import TenantOwnedModel


class Employee(TenantOwnedModel):
    membership = models.OneToOneField("tenants.Membership", on_delete=models.PROTECT, related_name="employee")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    joined_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def clean(self):
        self.validate_tenant_links("membership")
