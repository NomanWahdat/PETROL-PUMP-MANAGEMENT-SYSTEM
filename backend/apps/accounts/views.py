from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.middleware.csrf import get_token
from django.middleware.csrf import rotate_token
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ModelValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.common.errors import CodedError
from apps.tenants.models import Membership
from apps.tenants.permissions import effective_permissions, resolve_membership


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


def identity(user, membership=None):
    from apps.employees.models import Employee
    employee = Employee.objects.for_tenant(membership.tenant).filter(membership=membership).first() if membership else None
    return {
        "id": str(user.id), "username": user.username, "display_name": employee.name if employee else user.get_full_name() or user.username,
        "language": user.preferred_language, "is_superadmin": user.is_superuser,
        "tenant": {"id": str(membership.tenant_id), "name": membership.tenant.name} if membership else None,
        "role": membership.role if membership else "superadmin" if user.is_superuser else "unassigned",
        "permissions": effective_permissions(membership) if membership else [],
    }


@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            raise CodedError("invalid_credentials", "Incorrect username or password.", 401)
        memberships = list(Membership.all_tenants.filter(
            user=user, is_active=True, tenant__is_active=True,
        ).select_related("tenant").order_by("created_at"))
        membership = memberships[0] if len(memberships) == 1 and not user.is_superuser else None
        if not memberships and not user.is_superuser:
            raise CodedError("tenant_unavailable", "Your station access is unavailable.", 403)
        with transaction.atomic():
            login(request, user)
            if membership:
                request.session["active_tenant_id"] = str(membership.tenant_id)
                AuditLog.all_tenants.create(tenant=membership.tenant, created_by=user, action="login", object_type="user", object_id=str(user.id))
            if user.is_superuser:
                from apps.audit.models import PlatformAuditLog
                PlatformAuditLog.objects.create(actor=user, action="login", object_id=str(user.pk))
        return Response({"user": identity(user, membership), "csrf_token": get_token(request)})


@method_decorator(never_cache, name="dispatch")
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = resolve_membership(request) if request.session.get("active_tenant_id") else None
        if not membership and not request.user.is_superuser and not Membership.all_tenants.filter(user=request.user, is_active=True, tenant__is_active=True).exists():
            raise CodedError("tenant_unavailable", "Your station access is unavailable.", 403)
        return Response({"user": identity(request.user, membership)})


@method_decorator(never_cache, name="dispatch")
class MembershipsView(APIView):
    def get(self, request):
        memberships = Membership.all_tenants.filter(user=request.user, is_active=True, tenant__is_active=True).select_related("tenant")
        return Response({"results": [{"id": str(m.tenant_id), "name": m.tenant.name, "role": m.role} for m in memberships]})


class SelectTenantView(APIView):
    def post(self, request):
        tenant_id = serializers.UUIDField().run_validation(request.data.get("tenant_id"))
        membership = Membership.all_tenants.select_related("tenant").filter(user=request.user, tenant_id=tenant_id, is_active=True, tenant__is_active=True).first()
        if membership is None:
            raise CodedError("tenant_unavailable", "Your station access is unavailable.", 403)
        request.session.cycle_key()
        request.session["active_tenant_id"] = str(membership.tenant_id)
        rotate_token(request)
        AuditLog.all_tenants.create(tenant=membership.tenant, created_by=request.user, action="tenant_selected", object_type="user", object_id=str(request.user.pk))
        return Response({"user": identity(request.user, membership), "csrf_token": get_token(request)})


class PlatformContextView(APIView):
    def post(self, request):
        from apps.tenants.permissions import IsPlatformAdmin
        if not IsPlatformAdmin().has_permission(request, self):
            raise CodedError("permission_denied", "Access denied.", 403)
        request.session.cycle_key()
        request.session.pop("active_tenant_id", None)
        rotate_token(request)
        return Response({"user": identity(request.user), "csrf_token": get_token(request)})


class PasswordView(APIView):
    def post(self, request):
        current = serializers.CharField(max_length=256, trim_whitespace=False).run_validation(request.data.get("current_password"))
        password = serializers.CharField(max_length=256, trim_whitespace=False).run_validation(request.data.get("new_password"))
        if not request.user.check_password(current):
            raise CodedError("invalid_credentials", "Incorrect current password.", 400)
        try:
            validate_password(password, request.user)
        except ModelValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages}) from exc
        with transaction.atomic():
            request.user.set_password(password)
            request.user.save(update_fields=["password"])
            update_session_auth_hash(request, request.user)
            if request.session.get("active_tenant_id"):
                membership = Membership.all_tenants.filter(user=request.user, tenant_id=request.session["active_tenant_id"]).first()
                if membership:
                    AuditLog.all_tenants.create(tenant=membership.tenant, created_by=request.user, action="password_changed", object_type="user", object_id=str(request.user.pk))
            if request.user.is_superuser:
                from apps.audit.models import PlatformAuditLog
                PlatformAuditLog.objects.create(actor=request.user, action="password_changed", object_id=str(request.user.pk))
        rotate_token(request)
        return Response({"csrf_token": get_token(request)})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Logout must work even if tenant access was revoked since login.
        with transaction.atomic():
            membership = Membership.all_tenants.filter(user=request.user, tenant_id=request.session.get("active_tenant_id")).first()
            if membership:
                AuditLog.all_tenants.create(tenant_id=membership.tenant_id, created_by=request.user, action="logout", object_type="user", object_id=str(request.user.id))
            if request.user.is_superuser:
                from apps.audit.models import PlatformAuditLog
                PlatformAuditLog.objects.create(actor=request.user, action="logout", object_id=str(request.user.pk))
            logout(request)
        return Response(status=204)
