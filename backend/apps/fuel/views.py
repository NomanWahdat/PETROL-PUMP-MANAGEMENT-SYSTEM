from rest_framework import mixins, viewsets
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from apps.common.api import TenantViewSet, audit
from apps.tenants.permissions import HasTenantPermission
from .models import FuelPriceHistory
from .serializers import FuelProductSerializer, FuelPriceHistorySerializer, TankSerializer, PumpSerializer, NozzleSerializer


class FuelProductViewSet(TenantViewSet):
    serializer_class = FuelProductSerializer
    search_fields = ["name", "code"]

    def record_price(self, product, reason):
        FuelPriceHistory.all_tenants.create(tenant=self.request.tenant, product=product,
            purchase_price=product.purchase_price, selling_price=product.selling_price,
            reason=reason, created_by=self.request.user)

    def perform_create(self, serializer):
        reason = serializer.validated_data.pop("price_reason", "")
        super().perform_create(serializer)
        self.record_price(serializer.instance, reason)

    def perform_update(self, serializer):
        old = (serializer.instance.purchase_price, serializer.instance.selling_price)
        reason = serializer.validated_data.pop("price_reason", "")
        super().perform_update(serializer)
        if old != (serializer.instance.purchase_price, serializer.instance.selling_price):
            self.record_price(serializer.instance, reason)
            audit(self.request, "price_changed", serializer.instance)


class TankViewSet(TenantViewSet):
    serializer_class = TankSerializer


class PumpViewSet(TenantViewSet):
    serializer_class = PumpSerializer
    search_fields = ["name", "number"]


class NozzleViewSet(TenantViewSet):
    serializer_class = NozzleSerializer
    search_fields = ["number", "pump__name"]


@method_decorator(never_cache, name="dispatch")
class FuelPriceHistoryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = FuelPriceHistorySerializer
    permission_classes = [HasTenantPermission]
    required_permission = "fuel.manage"

    def get_queryset(self):
        queryset = FuelPriceHistory.objects.for_tenant(self.request.tenant).order_by("-created_at")
        product = self.request.query_params.get("product")
        if product:
            from rest_framework import serializers
            product = serializers.UUIDField().run_validation(product)
            queryset = queryset.filter(product_id=product)
        return queryset
