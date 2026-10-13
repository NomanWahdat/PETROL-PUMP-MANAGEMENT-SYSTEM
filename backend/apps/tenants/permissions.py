from rest_framework.permissions import BasePermission

from apps.common.errors import CodedError
from .models import Membership, RolePolicy, Tenant

KNOWN_PERMISSIONS = frozenset({"station.view", "station.manage", "employees.manage", "access.manage", "fuel.view", "fuel.manage", "shifts.own", "shifts.manage", "reports.operational", "reports.financial", "accounting.manage", "audit.view", "purchases.manage", "inventory.manage", "customers.manage", "cash.manage", "closing.manage"})
ROLE_PERMISSIONS = {
    "owner": KNOWN_PERMISSIONS,
    "manager": frozenset({"station.view", "employees.manage", "fuel.view", "fuel.manage", "shifts.own", "shifts.manage", "reports.operational", "purchases.manage", "inventory.manage", "customers.manage", "cash.manage", "closing.manage"}),
    "worker": frozenset({"station.view", "shifts.own"}),
    "accountant": frozenset({"station.view", "fuel.view", "reports.operational", "reports.financial", "accounting.manage", "customers.manage", "cash.manage", "closing.manage"}),
}


def effective_permissions(membership):
    policy = RolePolicy.objects.for_tenant(membership.tenant).filter(role=membership.role).first()
    permissions = set(policy.permissions if policy else ROLE_PERMISSIONS.get(membership.role, ())) & KNOWN_PERMISSIONS
    for key, enabled in membership.permission_overrides.items():
        if key in KNOWN_PERMISSIONS:
            if enabled is True:
                permissions.add(key)
            elif enabled is False:
                permissions.discard(key)
    return sorted(permissions)


def resolve_membership(request):
    # The tenant ID is persisted by login after checking membership. Never read request data/headers.
    tenant_id = request.session.get("active_tenant_id")
    if not tenant_id:
        raise CodedError("tenant_required", "No active station is assigned to this session.", 403)
    membership = Membership.all_tenants.select_related("tenant", "user").filter(
        user=request.user, user__is_active=True, tenant_id=tenant_id, is_active=True, tenant__is_active=True,
    ).first()
    if membership is None:
        raise CodedError("tenant_unavailable", "Your station access is unavailable.", 403)
    request.tenant = membership.tenant
    request.membership = membership
    return membership


def lock_tenant_access(request, permission):
    """Called inside atomic writes; recheck access after any station-lock wait."""
    tenant = Tenant.objects.select_for_update().get(pk=request.tenant.pk)
    membership = resolve_membership(request)
    permissions = effective_permissions(membership)
    allowed = any(value in permissions for value in permission) if isinstance(permission, tuple) else permission in permissions
    if not tenant.is_active or not allowed:
        raise CodedError("permission_denied", "Access denied.", 403)
    return tenant


class HasTenantPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        membership = resolve_membership(request)
        permission = view.get_required_permission(request) if hasattr(view, "get_required_permission") else getattr(view, "required_permission", "station.view")
        permissions = effective_permissions(membership)
        return any(value in permissions for value in permission) if isinstance(permission, tuple) else permission in permissions


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_active and request.user.is_superuser)
