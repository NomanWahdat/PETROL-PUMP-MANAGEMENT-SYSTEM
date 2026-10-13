from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import filters, mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import PlatformAuditLog
from apps.common.api import audit
from .models import Tenant, Membership, RolePolicy
from .permissions import IsPlatformAdmin, HasTenantPermission, ROLE_PERMISSIONS, KNOWN_PERMISSIONS, lock_tenant_access
from .serializers import TenantSerializer, RolePolicySerializer, PlatformUserSerializer


@method_decorator(never_cache, name="dispatch")
class PlatformViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends = [filters.SearchFilter]

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            raise serializers.ValidationError({"record": "A conflicting record exists."}) from exc

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            # Serialize global identity edits to protect the last active platform admin.
            list(get_user_model().objects.select_for_update().filter(is_superuser=True).order_by("pk"))
            if self.serializer_class is PlatformUserSerializer:
                tenant_ids = Membership.all_tenants.filter(user_id=kwargs["pk"], role="owner").values_list("tenant_id", flat=True)
                list(Tenant.objects.select_for_update().filter(pk__in=tenant_ids).order_by("pk"))
            elif self.serializer_class is TenantSerializer:
                list(Tenant.objects.select_for_update().filter(pk=kwargs["pk"]))
            return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save()
        PlatformAuditLog.objects.create(actor=self.request.user, action="created_" + instance._meta.model_name, object_id=str(instance.pk))

    def perform_update(self, serializer):
        instance = serializer.save()
        PlatformAuditLog.objects.create(actor=self.request.user, action="updated_" + instance._meta.model_name, object_id=str(instance.pk))


class TenantViewSet(PlatformViewSet):
    queryset = Tenant.objects.all().order_by("name")
    serializer_class = TenantSerializer
    search_fields = ["name", "slug"]


class PlatformUserViewSet(PlatformViewSet):
    queryset = get_user_model().objects.all().order_by("username")
    serializer_class = PlatformUserSerializer
    search_fields = ["username", "first_name", "last_name"]

    @action(detail=True, methods=["get", "post"])
    def memberships(self, request, pk=None):
        user = self.get_object()
        if request.method == "GET":
            records = Membership.all_tenants.filter(user=user).select_related("tenant")
            return Response({"results": [{"tenant_id": str(m.tenant_id), "name": m.tenant.name, "role": m.role, "is_active": m.is_active} for m in records]})
        tenant_id = serializers.UUIDField().run_validation(request.data.get("tenant_id"))
        role = serializers.ChoiceField(choices=Membership.Role.choices).run_validation(request.data.get("role"))
        active = serializers.BooleanField().run_validation(request.data.get("is_active", True))
        from apps.common.errors import CodedError
        from apps.employees.models import Employee
        with transaction.atomic():
            tenant = Tenant.objects.select_for_update().filter(pk=tenant_id, is_active=True).first()
            if tenant is None:
                raise CodedError("invalid", "Choose an active station.", 400)
            existing = Membership.objects.for_tenant(tenant).filter(user=user).first()
            if existing and existing.role == "owner" and (role != "owner" or not active):
                if not Membership.objects.for_tenant(tenant).filter(role="owner", is_active=True, user__is_active=True).exclude(pk=existing.pk).exists():
                    raise CodedError("invalid", "At least one active owner is required.", 400)
            membership, _ = Membership.all_tenants.update_or_create(tenant=tenant, user=user,
                defaults={"role": role, "is_active": active, "updated_by": request.user})
            Employee.all_tenants.get_or_create(tenant=tenant, membership=membership,
                defaults={"name": user.get_full_name() or user.username, "created_by": request.user})
            PlatformAuditLog.objects.create(actor=request.user, action="membership_changed", object_id=str(user.pk), changes={"tenant_id": str(tenant.pk), "role": role, "is_active": active})
        return Response({"tenant_id": str(tenant.pk), "name": tenant.name, "role": role, "is_active": active})


@method_decorator(never_cache, name="dispatch")
class RolePolicyView(APIView):
    permission_classes = [HasTenantPermission]
    required_permission = "access.manage"

    def check_owner(self, request):
        if request.membership.role != "owner":
            from apps.common.errors import CodedError
            raise CodedError("permission_denied", "Only station owners may configure role policies.", 403)

    def get(self, request):
        self.check_owner(request)
        policies = {p.role: p.permissions for p in RolePolicy.objects.for_tenant(request.tenant)}
        return Response({"known_permissions": sorted(KNOWN_PERMISSIONS), "results": [
            {"role": role, "permissions": policies.get(role, sorted(ROLE_PERMISSIONS[role]))} for role in Membership.Role.values
        ]})

    def post(self, request):
        self.check_owner(request)
        serializer = RolePolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            lock_tenant_access(request, self.required_permission)
            self.check_owner(request)
            policy, _ = RolePolicy.all_tenants.update_or_create(tenant=request.tenant, role=serializer.validated_data["role"],
                defaults={"permissions": serializer.validated_data["permissions"], "updated_by": request.user})
            audit(request, "role_policy_changed", policy, {"permissions": policy.permissions})
        return Response(serializer.data)


@method_decorator(never_cache, name="dispatch")
class PlatformStatusView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response({"tenants": Tenant.objects.count(), "active_tenants": Tenant.objects.filter(is_active=True).count(), "users": get_user_model().objects.count()})


class PlatformAuditSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.username")

    class Meta:
        model = PlatformAuditLog
        fields = ["id", "actor", "action", "object_id", "created_at"]


@method_decorator(never_cache, name="dispatch")
class PlatformAuditViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsPlatformAdmin]
    queryset = PlatformAuditLog.objects.select_related("actor").all()
    serializer_class = PlatformAuditSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["action", "actor__username"]
