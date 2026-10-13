from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, models, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import filters, serializers, viewsets

from apps.audit.models import AuditLog
from apps.tenants.permissions import HasTenantPermission, lock_tenant_access
from .serializers import ExactDecimal


def validated_save(instance):
    try:
        instance.full_clean()
        instance.save()
    except ModelValidationError as exc:
        raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc


def audit(request, action, instance, changes=None):
    AuditLog.all_tenants.create(
        tenant=request.tenant, created_by=request.user, action=action,
        object_type=instance._meta.label_lower, object_id=str(instance.pk), changes=changes or {},
    )


class TenantSerializer(serializers.ModelSerializer):
    serializer_field_mapping = {**serializers.ModelSerializer.serializer_field_mapping,
                                models.DecimalField: ExactDecimal}

    def create(self, validated_data):
        instance = self.Meta.model(**validated_data)
        validated_save(instance)
        return instance

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        validated_save(instance)
        return instance


@method_decorator(never_cache, name="dispatch")
class TenantViewSet(viewsets.ModelViewSet):
    permission_classes = [HasTenantPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]
    read_permission = "fuel.view"
    write_permission = "fuel.manage"

    def get_required_permission(self, request):
        return self.read_permission if request.method in {"GET", "HEAD", "OPTIONS"} else self.write_permission

    def get_queryset(self):
        queryset = self.serializer_class.Meta.model.objects.for_tenant(self.request.tenant).order_by("-created_at")
        active = self.request.query_params.get("is_active")
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                # One station lock serializes configuration edits and relationship validation.
                lock_tenant_access(request, self.get_required_permission(request))
                return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            raise serializers.ValidationError({"record": "A conflicting record already exists."}) from exc

    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                lock_tenant_access(request, self.get_required_permission(request))
                return super().update(request, *args, **kwargs)
        except IntegrityError as exc:
            raise serializers.ValidationError({"record": "This change conflicts with another record."}) from exc

    def perform_create(self, serializer):
        instance = serializer.save(tenant=self.request.tenant, created_by=self.request.user)
        audit(self.request, "created", instance)

    def perform_update(self, serializer):
        before = dict(serializer.__class__(serializer.instance, context=serializer.context).data)
        instance = serializer.save(updated_by=self.request.user)
        audit(self.request, "updated", instance, {"before": before, "after": dict(serializer.data)})
