from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.common.models import TenantOwnedModel, TimestampedModel


class Tenant(TimestampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    # Only server-generated private storage paths may be saved here.
    logo_path = models.CharField(max_length=300, blank=True)
    primary_color = models.CharField(max_length=7, default="#215b48", validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$")])
    secondary_color = models.CharField(max_length=7, default="#64748b", validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$")])

    def __str__(self):
        return self.name


class Membership(TenantOwnedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        WORKER = "worker", "Worker"
        ACCOUNTANT = "accountant", "Accountant"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    # Validated allow/deny overrides. A richer role editor belongs to phase 2.
    permission_overrides = models.JSONField(default=dict, blank=True)

    def clean(self):
        from .permissions import KNOWN_PERMISSIONS
        if not isinstance(self.permission_overrides, dict) or any(
            key not in KNOWN_PERMISSIONS or type(value) is not bool
            for key, value in self.permission_overrides.items()
        ):
            raise ValidationError({"permission_overrides": "Use known permission names and boolean values."})

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="membership_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "user"], name="unique_tenant_user"),
            models.CheckConstraint(condition=models.Q(role__in=["owner", "manager", "worker", "accountant"]), name="valid_membership_role"),
        ]


class RolePolicy(TenantOwnedModel):
    role = models.CharField(max_length=20, choices=Membership.Role.choices)
    permissions = models.JSONField(default=list)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "role"], name="unique_tenant_role_policy")]
