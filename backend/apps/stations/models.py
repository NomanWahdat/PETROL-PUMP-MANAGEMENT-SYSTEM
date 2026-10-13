from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.common.models import TenantOwnedModel


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError("Use a valid IANA timezone.")


class Station(TenantOwnedModel):
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    province = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    owner_name = models.CharField(max_length=150, blank=True)
    currency = models.CharField(max_length=3, default="AFN", validators=[RegexValidator(r"^[A-Z]{3}$")])
    language = models.CharField(max_length=2, choices=[("fa", "Dari"), ("ps", "Pashto"), ("en", "English")], default="fa")
    timezone = models.CharField(max_length=50, default="Asia/Kabul", validators=[validate_timezone])
    date_format = models.CharField(max_length=30, default="yyyy-MM-dd")
    receipt_header = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant"], name="one_station_per_tenant")]


class ComplianceRecord(TenantOwnedModel):
    # Descriptive records only; no hard-coded legal interpretation or safety rules.
    title = models.CharField(max_length=200)
    authority = models.CharField(max_length=200, blank=True)
    reference = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=50, default="pending")
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.CheckConstraint(
            condition=models.Q(expiry_date__isnull=True) | models.Q(issue_date__isnull=True) | models.Q(expiry_date__gte=models.F("issue_date")),
            name="valid_compliance_dates",
        )]


class StationLogo(TenantOwnedModel):
    """Optional database-backed PNG storage for hosts without persistent files."""
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.PROTECT, related_name="stored_logo")
    path = models.CharField(max_length=300, unique=True)
    image = models.BinaryField(max_length=2 * 1024 * 1024)
